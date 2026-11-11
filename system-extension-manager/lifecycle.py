"""Debian extension lifecycle, verified source builds, and a multi-tool manager."""
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading

from execution import OperationLog, LogPanel, new_log_file, scrollable_tree, show_log_history

# Security status reflects the hardened source; installed old packages are
# NOT upgraded until the user explicitly installs the corresponding release.
DEB_INSTALL_WARNING = 'SECURITY: Verified extension bytes are copied into a root-owned temporary directory, rehashed, resimulated and installed from that private copy. APT repository/plan changes and package maintainer scripts still require review.'
PORTABLE_IMPORT_WARNING = 'SECURITY: The portable updater requires explicit approval and uses a root-owned SHA-256-verified source copy with isolated Python imports (-I). Kernel/NVIDIA/firmware/boot upgrades remain excluded. No updater service is installed.'
BACKUP_LOCK_WARNING = 'SECURITY: HomeBackUp 0.1.6 uses no-follow root-owned lock files and guarded lock directories; unsafe locks stop execution. Backup retention remains destructive after successful verification. Older installed versions are not automatically changed.'
MINT_TOOLBOX_RETIRED_WARNING = ('DO NOT USE MINT TOOLBOX: retired/unsafe legacy project. '
                                'Never run, install, upgrade, rebuild, or restore Mint Toolbox. '
                                'The legacy mint-toolbox/ source tree must remain untouched. '
                                'System Extension Manager is a separate maintained application.')


def security_warning(item, *, installing=False):
    if item.get('kind') == 'portable':
        return PORTABLE_IMPORT_WARNING
    if item['id'] == 'homebackup':
        return BACKUP_LOCK_WARNING + ('\n' + DEB_INSTALL_WARNING if installing else '')
    return DEB_INSTALL_WARNING

ROOT = Path(__file__).resolve().parent

SAFETY_NOTICE = (
    'Safety information (shown only once):\n\n'
    'Install / Uninstall affects all users; portable tools need no installation.\n'
    'A HomeBackUp installation does not prove a backup timer is running; old archives may be pruned.\n'
    'Anki imports publish WordPress posts and can overwrite existing content; back up WordPress first.\n'
    'ZIP keeps originals by default; optional Trash moves are not atomic.\n'
    'Security Updates is manual in a terminal: leave it open until completion. Kernel/driver changes are excluded.\n\n'
    'Review these notes later with Safety notes...'
)


def safety_notice_path():
    state_home = Path(os.environ.get('XDG_STATE_HOME') or (Path.home() / '.local/state'))
    return state_home / 'system-extension-manager' / 'safety-notice-v1.ack'


def show_one_time_safety_notice(window, showinfo=None):
    from tkinter import messagebox
    path = safety_notice_path()
    if path.is_file():
        return False
    (showinfo or messagebox.showinfo)('Safety notes', SAFETY_NOTICE, parent=window)
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_text('acknowledged\n', encoding='utf-8')
    except OSError:
        pass
    return True



# The privileged process opens the source package ONCE with O_NOFOLLOW,
# copies those exact bytes into a root-owned private directory, checks the
# approved SHA-256 against that copy, simulates APT again and installs ONLY
# the staged copy. A user/attacker changing the original pathname after
# verification cannot change the bytes handed to privileged APT.
SECURE_INSTALL_CODE = r"""
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

def fail(message):
    print('SECURITY ERROR: ' + message, file=sys.stderr, flush=True)
    raise SystemExit(1)

if len(sys.argv) != 5:
    fail('Expected approved SHA-256, package name, version and source path.')
expected, package, version, source = sys.argv[1:]
if not re.fullmatch(r'[0-9a-f]{64}', expected):
    fail('Invalid approved package checksum.')
if not re.fullmatch(r'[a-z0-9][a-z0-9+.-]+', package):
    fail('Invalid package name.')
if not version or any(ord(c) < 33 or ord(c) > 126 for c in version):
    fail('Invalid package version.')
if os.geteuid() != 0:
    fail('This transaction requires explicit administrator authorization.')
environment = {
    'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8',
    'LC_ALL': 'C.UTF-8', 'DEBIAN_FRONTEND': 'noninteractive',
}
try:
    with tempfile.TemporaryDirectory(prefix='mint-extension-install-') as directory:
        target = Path(directory) / 'verified.deb'
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        digest = hashlib.sha256()
        with os.fdopen(fd, 'rb') as original, target.open('xb') as staged:
            meta = os.fstat(original.fileno())
            if not stat.S_ISREG(meta.st_mode):
                fail('Approved package is not a regular file.')
            while True:
                block = original.read(1024 * 1024)
                if not block:
                    break
                digest.update(block)
                staged.write(block)
            staged.flush()
            os.fsync(staged.fileno())
        if digest.hexdigest() != expected:
            fail('Package changed since approval; aborted before APT.')
        metadata = subprocess.check_output(
            ['/usr/bin/dpkg-deb', '-f', str(target), 'Package', 'Version', 'Architecture'],
            env=environment, text=True, timeout=20,
        )
        fields = dict(line.split(': ', 1) for line in metadata.splitlines())
        arch = subprocess.check_output(
            ['/usr/bin/dpkg', '--print-architecture'],
            text=True, env=environment, timeout=10,
        ).strip()
        if (fields.get('Package') != package or fields.get('Version') != version
                or fields.get('Architecture') not in ('all', arch)):
            fail('Verified package identity / architecture mismatch.')
        args = [
            '/usr/bin/apt-get', '-o', 'Dpkg::Use-Pty=0', '-o', 'APT::Color=0',
            'install', '--no-install-recommends', '--no-remove', '-y', str(target),
        ]
        trial = subprocess.run(
            [args[0], '--simulate', *args[1:]], env=environment,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=120, check=True,
        )
        print(trial.stdout, end='', flush=True)
        for line in trial.stdout.splitlines():
            parts = line.split()
            if not parts:
                continue
            if parts[0] in ('Remv', 'Purg'):
                fail('APT proposed a removal: ' + line)
            if parts[0] == 'Inst' and len(parts) > 1:
                name = parts[1].lower().split(':')[0]
                if (name.startswith(('linux-', 'nvidia-', 'libnvidia-',
                                      'grub', 'shim', 'initramfs', 'dkms'))
                        or 'nvidia' in name or 'firmware' in name):
                    fail('Kernel/driver/firmware changes require separate review: ' + name)
        print('Verified staged package: ' + package + ' ' + version, flush=True)
        result = subprocess.run(args, env=environment, check=False)
        if result.returncode:
            fail('APT install failed; the system state may be partial.')
except (OSError, ValueError, subprocess.SubprocessError) as exc:
    fail(str(exc))
"""


def reject_retired_mint_toolbox(item):
    """Fail closed if a catalog entry tries to revive the abandoned app.

    Standalone extensions (e.g. ZIP and Trash) are not the Mint Toolbox app.
    Do not inspect or modify the preserved legacy project directory.
    """
    if item.get('id', '').casefold() == 'mint-toolbox' or (
        item.get('name', '').strip().casefold() == 'mint toolbox'
    ) or item.get('package', '').casefold() == 'mint-toolbox':
        raise ValueError(MINT_TOOLBOX_RETIRED_WARNING)
    launch = item.get('launch', [])
    if isinstance(launch, list) and launch:
        executable = Path(str(launch[0])).name.casefold()
        if executable in ('mint-toolbox', 'mint-toolbox.py', 'mint_toolbox'):
            raise ValueError(MINT_TOOLBOX_RETIRED_WARNING)
    for path in (item.get('script'), item.get('deb')):
        if isinstance(path, str) and 'mint-toolbox' in Path(path).parts:
            raise ValueError(MINT_TOOLBOX_RETIRED_WARNING)


def plugins():
    rows = json.loads((ROOT / 'extensions.json').read_text('utf-8'))
    ids, packages = set(), set()
    for item in rows:
        reject_retired_mint_toolbox(item)
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', item['id']) or item['id'] in ids:
            raise ValueError('Invalid or duplicate extension ID')
        if item.get('kind') == 'portable':
            if not isinstance(item.get('script'), str) or not item['script'].startswith('sources/'):
                raise ValueError('Invalid portable script path')
            if 'package' in item or 'deb' in item or 'source' in item:
                raise ValueError('Portable tools cannot declare installable packages')
        else:
            if not re.fullmatch(r'[a-z0-9][a-z0-9+.-]+', item['package']) or item['package'] in packages:
                raise ValueError('Invalid or duplicate package name')
            packages.add(item['package'])
        ids.add(item['id'])
    return rows


def plugin(key):
    for item in plugins():
        if item['id'] == key:
            return item
    raise ValueError('Unknown extension: ' + key)


def package_status(package, log=None):
    if log is not None:
        result = log.run(['/usr/bin/dpkg-query', '-W', '-f=${Status}\n${Version}', package], check=False)
    else:
        result = subprocess.run(['/usr/bin/dpkg-query', '-W', '-f=${Status}\n${Version}', package],
                            capture_output=True, text=True, timeout=15)
    if result.returncode == 1:
        return ('absent', None)
    if result.returncode:
        raise RuntimeError('Cannot read package status: ' + result.stderr)
    lines = result.stdout.splitlines()
    if len(lines) != 2:
        raise RuntimeError('Unexpected package status format')
    return tuple(lines)


def installed_version(package):
    status, version = package_status(package)
    return version if status == 'install ok installed' else None


def state_text(package):
    status, version = package_status(package)
    if status == 'install ok installed':
        return 'Enabled: ' + version
    if status == 'absent' or status.endswith(' ok config-files'):
        return 'Disabled'
    return 'Incomplete installation: ' + status


def extension_state(item):
    if item.get('kind') == 'portable':
        try:
            portable_script(item)
            return dict(state='Ready (no installation required)', installed=None,
                        install=False, remove=False, update=False)
        except (OSError, ValueError) as exc:
            return dict(state='Unknown: ' + str(exc), installed=None,
                        install=False, remove=False, update=False)
    try:
        status, version = package_status(item['package'])
        if status == 'install ok installed':
            newer = subprocess.run(['/usr/bin/dpkg', '--compare-versions', version, 'lt', item['version']]).returncode == 0
            return dict(state='Enabled: ' + version + (' (Update available)' if newer else ''), installed=version,
                        install=False, remove=True, update=newer)
        if status == 'absent' or status.endswith(' ok config-files'):
            return dict(state='Disabled', installed=None, install=True, remove=False, update=False)
        return dict(state='Incomplete: ' + status, installed=version, install=False, remove=True, update=False)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        return dict(state='Unknown: ' + str(exc), installed=None, install=False, remove=False, update=False)


def verify_deb(item, deb, expected_hash=None, log=None):
    if not deb.is_file() or deb.is_symlink():
        raise ValueError('Debian package is missing or is a symbolic link')
    if expected_hash and hashlib.sha256(deb.read_bytes()).hexdigest() != expected_hash:
        raise ValueError('Debian package checksum verification failed')
    metadata = ['/usr/bin/dpkg-deb', '-f', str(deb), 'Package', 'Version', 'Architecture']
    architecture = ['/usr/bin/dpkg', '--print-architecture']
    if log is None:
        info = subprocess.run(metadata, check=True, capture_output=True, text=True, timeout=15).stdout
        arch = subprocess.check_output(architecture, text=True, timeout=15).strip()
    else:
        info = log.run(metadata).stdout
        arch = log.run(architecture).stdout.strip()
    fields = dict(line.split(': ', 1) for line in info.splitlines())
    if fields.get('Package') != item['package'] or fields.get('Version') != item['version']:
        raise ValueError('Package name or version does not match the extension catalog')
    if fields.get('Architecture') not in ('all', arch):
        raise ValueError('Incompatible package architecture. Use Build from source if available.')
    return fields


def bundled_deb(item, log=None):
    path = ROOT / item['deb']
    if not path.resolve().is_relative_to(ROOT):
        raise ValueError('Package path escapes the application directory')
    verify_deb(item, path, item['sha256'], log)
    return path


def command(key, enable, deb=None, log=None):
    item = plugin(key)
    if item.get('kind') == 'portable':
        raise ValueError('Portable tools run directly; choose Run in Terminal (or --open).')
    if enable:
        if deb is None:
            deb = bundled_deb(item, log)
            approved_hash = item['sha256']
        else:
            deb = Path(deb)
            verify_deb(item, deb, log=log)
            approved_hash = hashlib.sha256(deb.read_bytes()).hexdigest()
        args = ['/usr/bin/python3', '-I', '-c', SECURE_INSTALL_CODE,
                approved_hash, item['package'], item['version'], str(deb)]
    else:
        args = ['/usr/bin/apt-get', '-o', 'Dpkg::Use-Pty=0', '-o', 'APT::Color=0',
                'remove', '-y', item['package']]
    return args if os.geteuid() == 0 else ['/usr/bin/pkexec', *args]


def build_source(item, log):
    if item.get('kind') == 'portable':
        raise ValueError('Portable tools require no package build or installation.')
    if os.geteuid() == 0:
        raise ValueError('Source builds must run as a regular user. Start System Extension Manager without sudo.')
    recipe = item.get('source')
    if not recipe:
        raise ValueError('No source build recipe is available for this extension')
    # Only reviewed local sources are supported; there is no arbitrary URL execution.
    dependencies = recipe.get('requires', [])
    missing = [name for name in dependencies if not shutil.which(name)]
    if missing:
        raise ValueError('Missing build tools: ' + ', '.join(missing) + '. Install them and retry.')
    base = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'system-extension-manager/builds'
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    stage = Path(tempfile.mkdtemp(prefix=item['id'] + '-', dir=base))
    source = stage / 'source'
    output = stage / 'output'
    source.mkdir()
    output.mkdir()
    log.stage('Verifying pinned source files')
    for relative, checksum in recipe['files'].items():
        path = ROOT / relative
        dest = source / relative
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT) or not dest.resolve().is_relative_to(source):
            raise ValueError('Invalid source file path: ' + relative)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != checksum:
            raise ValueError('Source checksum verification failed: ' + relative)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    log.stage('Building as the current regular user')
    args = [str(output) if arg == '{output}' else arg for arg in recipe['argv']]
    log.run(args, cwd=source)
    artifacts = list(output.glob('*.deb'))
    if len(artifacts) != 1:
        raise ValueError('Source recipe must produce exactly one Debian package')
    verify_deb(item, artifacts[0], log=log)
    log.write('Built package: ' + str(artifacts[0]) + '\n')
    return artifacts[0]


def change(key, enable, log=None, from_source=False, update=False):
    owned = log is None
    log = log or OperationLog(key)
    try:
        item = plugin(key)
        if item.get('kind') == 'portable':
            raise ValueError('Portable tools require no installation; use Run in Terminal.')
        log.stage(('Enable' if enable else 'Disable') + ': ' + item['name'])
        if from_source and not enable:
            raise ValueError('Source builds are only valid for enabling an extension')
        current_status, current_version = package_status(item['package'], log)
        installed = current_status == 'install ok installed'
        absent = current_status == 'absent' or current_status.endswith(' ok config-files')
        if update:
            if not enable or not installed:
                raise ValueError('Update requires an installed extension')
            if subprocess.run(['/usr/bin/dpkg', '--compare-versions', current_version, 'lt', item['version']]).returncode != 0:
                log.stage('Already up to date; no package operation performed')
                return current_version
        elif enable and installed:
            log.stage('Already installed: ' + current_version + '; use Update for a newer version')
            return current_version
        elif not enable and absent:
            log.stage('Not installed; no package operation performed')
            return None
        elif enable and not absent:
            raise ValueError('Incomplete installation; remove the extension before installing again')
        if enable:
            log.stage(security_warning(item, installing=True))
        deb = build_source(item, log) if from_source else None
        args = command(key, enable, deb, log) if from_source else command(key, enable, log=log)
        # Dependency resolution errors are displayed before the authorized install.
        log.stage('Checking package changes without changing the system')
        # Preflight before administrator authorization. The privileged
        # installation helper repeats the same check on the root-owned copy.
        if enable:
            simulated_deb = str(deb if from_source else ROOT / item['deb'])
            simulation = [
                '/usr/bin/apt-get', '--simulate', '-o', 'Dpkg::Use-Pty=0',
                '-o', 'APT::Color=0', 'install', '--no-install-recommends',
                '--no-remove', '-y', simulated_deb,
            ]
        else:
            simulation = ['/usr/bin/apt-get', '--simulate', '-o', 'Dpkg::Use-Pty=0',
                          '-o', 'APT::Color=0', 'remove', '-y', item['package']]
        plan = log.run(simulation)
        for line in plan.stdout.splitlines():
            parts = line.split()
            if len(parts) < 2 or parts[0] not in ('Inst', 'Remv'):
                continue
            package = parts[1].split(':')[0]
            if parts[0] == 'Remv' and (enable or package != item['package']):
                raise ValueError('Refusing unrelated package removal: ' + package)
            if parts[0] == 'Inst' and re.match(r'^(linux-|nvidia-|libnvidia-)', package):
                raise ValueError('Kernel/driver changes require separate manual review: ' + package)
        if enable and installed and item['id'] == 'homebackup':
            # An upgrade first executes the OLD package's maintenance scripts.
            # Version 0.1.3 cannot enforce the new shutdown policy itself.
            log.stage('Checking that HomeBackUp is stopped before upgrading old maintenance scripts')
            for unit in ('mint-homebackup-extension.timer', 'mint-homebackup-extension.service'):
                state = log.run(['/usr/bin/systemctl', 'show', '--property=ActiveState', '--value', unit]).stdout.strip()
                if state not in ('inactive', 'failed'):
                    raise ValueError('Stop the HomeBackUp timer and active backup service before updating: ' + unit + ' is ' + state)
            timer = log.run(['/usr/bin/systemctl', 'is-enabled', 'mint-homebackup-extension.timer'], check=False).stdout.strip()
            if timer not in ('disabled', 'masked'):
                raise ValueError('Disable the HomeBackUp monthly timer before updating; current state: ' + timer)
        log.stage('Installing package' if enable else 'Removing package')
        result = log.run(args, check=False)
        log.stage('Reading package status back from dpkg')
        status, version = package_status(item['package'], log)
        log.write(f'Package state: {status}; version: {version or "none"}\n')
        correct = (status == 'install ok installed' and version == item['version']) if enable else (status == 'absent' or status.endswith(' ok config-files'))
        if result.returncode or not correct:
            raise RuntimeError('Operation failed or package status readback did not match')
        log.stage('Completed successfully')
        return version
    except Exception as exc:
        log.stage('FAILED: ' + str(exc))
        raise
    finally:
        if owned:
            log.close()


def update_all_plan(log=None):
    """Return installed extensions strictly older than their verified bundled releases.

    Missing/disabled extensions are never installed. Incomplete dpkg states
    are treated as blockers rather than repaired implicitly.
    """
    updates = []
    for item in plugins():
        if item.get('kind') == 'portable':
            continue
        status, current = package_status(item['package'], log)
        if status == 'absent' or status.endswith(' ok config-files'):
            continue
        if status != 'install ok installed':
            raise RuntimeError('Incomplete installation blocks Update All: ' + item['package'] + ': ' + status)
        compare = subprocess.run(['/usr/bin/dpkg', '--compare-versions', current, 'lt', item['version']],
                                 capture_output=True, text=True, timeout=15)
        if compare.returncode not in (0, 1):
            raise RuntimeError('Cannot compare versions for ' + item['package'] + ': ' + compare.stderr.strip())
        if compare.returncode == 0:
            # Check every selected package before any installation is attempted.
            bundled_deb(item, log)
            updates.append((item, current))
    return updates


def update_all(log=None, *, include_security=True):
    """One opt-in batch: upgrade installed outdated extensions, then open
    Security Updates for a separately approved, kernel-safe APT transaction.

    No absent extension is enabled. No automatic update service is created.
    """
    if os.geteuid() == 0:
        raise ValueError('Run Update All as the normal desktop user, not as root.')
    owned = log is None
    log = log or OperationLog('Update All')
    updated = []
    try:
        log.stage('Planning one-time updates for installed extensions only')
        planned = update_all_plan(log)
        if include_security:
            # Verify the portable script and terminal support before changing packages.
            updater = portable_script(plugin('security-updates'))
            terminal_command(updater, transcript=Path('/dev/null'))
        for item, previous in planned:
            log.stage('Upgrade ' + item['name'] + ': ' + previous + ' -> ' + item['version'])
        if not planned:
            log.stage('No installed extensions need an update (none installed or already current)')
        for item, previous in planned:
            try:
                result = change(item['id'], True, log, update=True)
            except Exception as exc:
                log.stage('UPDATE ALL STOPPED after ' + str(len(updated)) + ' successful upgrades. '
                          'No remaining extensions or Security Updates were started.')
                raise RuntimeError('Update All stopped at ' + item['name'] + ': ' + str(exc)) from exc
            if result == item['version']:
                updated.append(item['id'])
            else:
                log.stage('Skipped: ' + item['name'] + ' is no longer older than the bundled version')
        if include_security:
            log.stage('Opening the manual security-updates review terminal. '
                      'APT installation requires its own explicit UPDATE approval.')
            open_extension('security-updates', log)
        log.stage('Batch finished: upgraded ' + str(len(updated)) + ' extension(s). '
                  + ('Security update review terminal launched; its outcome is recorded separately.'
                     if include_security else 'Security updates were not requested.'))
        return dict(updated=updated, security_review_started=include_security)
    except Exception as exc:
        log.stage('UPDATE ALL FAILED: ' + str(exc))
        raise
    finally:
        if owned:
            log.close()


def filter_plugins(items, query='', status_filter='All'):
    query = query.casefold().strip()
    return [item for item in items
            if query in ' '.join(str(item.get(k, '')) for k in ('id', 'name', 'description', 'package')).casefold()
            and (status_filter == 'All' or item['state'].startswith(status_filter))]


def portable_script(item):
    relative = item['script']
    path = ROOT / relative
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(ROOT):
        raise ValueError('Portable tool source is missing, linked or escapes manager directory')
    if hashlib.sha256(path.read_bytes()).hexdigest() != item.get('sha256'):
        raise ValueError('Portable tool checksum mismatch; use a trusted unchanged source copy')
    return path


# The terminal process has its own transcript. The GUI's launch log must
# not claim that starting a terminal means that the update succeeded.
PORTABLE_TERMINAL_WRAPPER = r"""
logfile=$1
shift
printf 'Security Updates terminal session started.\n' | /usr/bin/tee -a -- "$logfile"
"$@" 2>&1 | /usr/bin/tee -a -- "$logfile"
statuses=("${PIPESTATUS[@]}")
code=${statuses[0]}
if (( statuses[1] != 0 )); then
    printf 'ERROR: Could not save all terminal output (tee exit code %s).\n' "${statuses[1]}" >&2
    if (( code == 0 )); then code=${statuses[1]}; fi
fi
printf 'Exit code: %s\n' "$code" | /usr/bin/tee -a -- "$logfile"
printf '\nFull output log: %s\n' "$logfile"
if [[ -t 0 ]]; then
    printf 'Press Enter to close this terminal... '
    IFS= read -r _ || true
fi
exit "$code"
"""


def new_terminal_transcript():
    fd, path = new_log_file('security-updates-terminal-')
    os.close(fd)
    return path


def terminal_command(script, transcript=None):
    # Bash preserves the Python exit status through tee and waits for Enter.
    # Positional arguments prevent shell injection through file paths.
    transcript = Path(transcript) if transcript is not None else new_terminal_transcript()
    argv = ['/bin/bash', '-c', PORTABLE_TERMINAL_WRAPPER,
            'portable-security-updates', str(transcript),
            '/usr/bin/python3', str(script), '--interactive']
    terminal = shutil.which('x-terminal-emulator')
    if terminal:
        return [terminal, '-e', *argv]
    for name, flag in [
        ('xfce4-terminal', ['--disable-server', '--execute']),
        ('gnome-terminal', ['--']),
        ('mate-terminal', ['--']),
        ('konsole', ['-e']),
        ('xterm', ['-e']),
    ]:
        executable = shutil.which(name)
        if executable:
            return [executable, *flag, *argv]
    raise ValueError('No compatible graphical terminal found. No changes were made.')


def launch_command(key, *, transcript=None):
    item = plugin(key)
    if item.get('kind') == 'portable':
        return terminal_command(portable_script(item), transcript=transcript)
    if installed_version(item['package']) is None:
        raise ValueError('Enable / Install this extension before opening it')
    args = item.get('launch')
    if not args:
        raise ValueError('This extension is used through its system integration and has no application window')
    if not isinstance(args, list) or not args or not Path(args[0]).is_absolute():
        raise ValueError('Invalid extension launch command')
    if not Path(args[0]).is_file() or not os.access(args[0], os.X_OK):
        raise ValueError('The installed extension executable is missing; reinstall the extension')
    return args

def open_extension(key, log=None):
    owned = log is None
    log = log or OperationLog('Open: ' + key)
    try:
        item = plugin(key)
        portable = item.get('kind') == 'portable'
        transcript = new_terminal_transcript() if portable else None
        args = launch_command(key, transcript=transcript)
        if portable:
            log.stage(PORTABLE_IMPORT_WARNING)
            import shlex
            log.stage('Launching terminal for ' + item['name'] + ' (no package installation)')
            log.stage('Terminal stdout/stderr and exit status: ' + str(transcript))
            log.write('$ ' + shlex.join(args) + '\n')
            # The terminal emulator's own startup errors are also saved.
            with transcript.open('a', encoding='utf-8') as terminal_output:
                subprocess.Popen(args, start_new_session=True, stdin=subprocess.DEVNULL,
                                 stdout=terminal_output, stderr=subprocess.STDOUT)
            log.stage('Terminal launch requested. Check the transcript for the actual result.')
        else:
            log.stage('Opening ' + item['name'])
            log.run(args)
            log.stage('Extension window closed')
    except Exception as exc:
        log.stage('FAILED: ' + str(exc))
        raise
    finally:
        if owned:
            log.close()


def build_manager_package(output_dir, log=None):
    from version import VERSION
    owned = log is None
    log = log or OperationLog('Build manager package')
    output_dir = Path(output_dir).expanduser().resolve()
    try:
        log.stage('Building an optional manager package; no installation will run')
        log.run([sys.executable, str(ROOT / 'build.py'), '--package', '--output-dir', str(output_dir)])
        artifact = output_dir / f'system-extension-manager_{VERSION}_all.deb'
        verify_deb({'package': 'system-extension-manager', 'version': VERSION}, artifact, log=log)
        log.stage('Package ready: ' + str(artifact))
        return artifact
    except Exception as exc:
        log.stage('FAILED: ' + str(exc))
        raise
    finally:
        if owned:
            log.close()


def show_gui(parent=None):
    import tkinter as tk
    from tkinter import ttk, messagebox
    import native_dialogs as filedialog
    window = tk.Toplevel(parent) if parent else tk.Tk()
    window.title('System Extension Manager')
    window.geometry('1100x760')
    window.columnconfigure(0, weight=1)
    window.rowconfigure(2, weight=1)
    window.rowconfigure(5, weight=1)
    header = ttk.Frame(window)
    header.grid(row=0, sticky='ew', padx=12, pady=(8, 0))
    ttk.Label(header, text='ACTIVE / MAINTAINED - System Extension Manager', foreground='#17633b').pack(fill='x')
    bar = ttk.Frame(window)
    bar.grid(row=1, sticky='ew', padx=12, pady=(8, 0))
    ttk.Label(bar, text='Search').pack(side='left')
    query, status = tk.StringVar(), tk.StringVar(value='All')
    ttk.Entry(bar, textvariable=query, width=1).pack(side='left', fill='x', expand=True, padx=8)
    ttk.Combobox(bar, textvariable=status, values=['All', 'Ready', 'Enabled', 'Disabled', 'Incomplete', 'Unknown'], state='readonly', width=12).pack(side='left')
    def open_history():
        if 'log_history' in window.children:
            history = window.children['log_history']
            history.deiconify()
            history.lift()
            history.focus_set()
        else:
            show_log_history(window)

    ttk.Button(bar, text='Log History...', command=open_history).pack(side='left', padx=(8, 0))
    ttk.Button(bar, text='Safety notes...', command=lambda: messagebox.showinfo(
        'Safety notes', SAFETY_NOTICE, parent=window)).pack(side='left', padx=(8, 0))
    listing = ttk.Frame(window)
    listing.grid(row=2, sticky='nsew', padx=12, pady=(8, 0))
    columns = ('name', 'version', 'state', 'source')
    tree = ttk.Treeview(listing, columns=columns, show='headings', selectmode='browse', height=2)
    for col, title, width in [('name', 'Tool', 180), ('version', 'Bundled version', 125), ('state', 'System status', 290), ('source', 'Source build', 110)]:
        tree.heading(col, text=title)
        tree.column(col, width=width, minwidth=width)
    scrollable_tree(listing, tree)

    details = ttk.Frame(window)
    details.grid(row=3, sticky='ew', padx=12, pady=(6, 4))
    description = tk.StringVar(value='Select an extension to view its description.')
    description_label = ttk.Label(details, textvariable=description, justify='left')
    description_label.pack(fill='x')

    buttons = ttk.Frame(window)
    buttons.grid(row=4, sticky='ew', padx=12)
    panel = LogPanel(window)
    panel.text.configure(width=1, height=2)
    panel.frame.grid(row=5, sticky='nsew', padx=12, pady=(8, 10))
    events = queue.Queue()
    busy = [False]
    rows = []
    def selected():
        values = tree.selection()
        return next((r for r in rows if values and r['id'] == values[0]), None)
    def render(*_):
        old = tree.selection()
        tree.delete(*tree.get_children())
        for item in filter_plugins(rows, query.get(), status.get()):
            tree.insert('', 'end', iid=item['id'], values=(item['name'], item['version'], item['state'], 'Not needed' if item.get('kind') == 'portable' else ('Available' if item.get('source') else 'Unavailable')))
        if old and tree.exists(old[0]):
            tree.selection_set(old)
        update_selection()
    def refresh():
        nonlocal rows
        rows = plugins()
        for row in rows:
            row.update(extension_state(row))
        render()
    def update_selection(*_):
        item = selected()
        description.set(item['description'] if item else 'Select an extension to view its description.')
        schedule_minimum_height()
        for control in operation_buttons:
            control.configure(state='normal' if item and not busy[0] else 'disabled')
        install_button.configure(state='normal' if item and item['install'] and not busy[0] else 'disabled')
        remove_button.configure(state='normal' if item and item['remove'] and not busy[0] else 'disabled')
        update_button.configure(state='normal' if item and item['update'] and not busy[0] else 'disabled')
        source_button.configure(state='normal' if item and item.get('source') and item['install'] and not busy[0] else 'disabled')
        portable = bool(item and item.get('kind') == 'portable')
        open_button.configure(text='Run in Terminal' if portable else 'Open')
        open_ready = bool(item and (
            (portable and item['state'].startswith('Ready'))
            or (item.get('launch') and item['state'].startswith('Enabled'))
        ))
        open_button.configure(state='normal' if open_ready and not busy[0] else 'disabled')
        package_button.configure(state='disabled' if busy[0] else 'normal')
        update_all_button.configure(state='disabled' if busy[0] else 'normal')
    def operate(enable, from_source=False, launch=False, update=False):
        item = selected()
        if not item or busy[0]:
            return
        label = 'Update' if update else ('Run in Terminal' if item.get('kind') == 'portable' else 'Open') if launch else ('Build from source and install' if from_source else ('Enable / Install' if enable else 'Disable / Uninstall'))
        if not launch and not messagebox.askyesno(
            label, label + ': ' + item['name']
            + '\n\nThis changes system-wide packages. Administrator authorization may be required. Proceed?',
            parent=window):
            return
        busy[0] = True
        refresh_button.configure(state='disabled')
        update_selection()
        def worker():
            log = None
            error = None
            try:
                log = OperationLog(item['id'] + ': ' + label, lambda text: events.put(('line', text)))
                if launch:
                    open_extension(item['id'], log)
                else:
                    change(item['id'], enable, log, from_source, update=update)
            except Exception as exc:
                error = str(exc)
            finally:
                if log:
                    log.close()
                events.put(('done', error))
        threading.Thread(target=worker, daemon=False).start()
    def update_everything():
        if busy[0]:
            return
        try:
            planned = update_all_plan()
            # Fail early if the security helper is changed or no terminal exists.
            terminal_command(portable_script(plugin('security-updates')), transcript=Path('/dev/null'))
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            messagebox.showerror('Update All unavailable', str(exc), parent=window)
            return
        summary = ('\n'.join('  ' + item['name'] + ': ' + old + ' -> ' + item['version']
                             for item, old in planned)
                   if planned else '  No installed extensions require an upgrade.')
        prompt = (
            'One-time Update All (manual; no recurring jobs):\n\n'
            + summary
            + '\n\nOnly already-installed, older extensions are updated. '
              'Disabled extensions stay disabled. Existing versions are rechecked before each action.\n\n'
              'Afterwards, Security Updates opens a terminal for separate package review '
              'and explicit UPDATE confirmation. Kernel/NVIDIA/DKMS/firmware/boot upgrades remain excluded.\n\n'
              'Package updates may require administrator authorization. A failure stops the batch; '
              'successful earlier updates are not rolled back. All output is logged.\n\nProceed?'
        )
        if not messagebox.askyesno('Update All', prompt, parent=window):
            return
        busy[0] = True
        refresh_button.configure(state='disabled')
        update_selection()
        def worker():
            log = None
            error = None
            try:
                log = OperationLog('Update All', lambda line: events.put(('line', line)))
                update_all(log, include_security=True)
            except Exception as exc:
                error = str(exc)
            finally:
                if log:
                    log.close()
                events.put(('done', error))
        threading.Thread(target=worker, daemon=False).start()

    def package_manager():
        if busy[0]:
            return
        folder = filedialog.askdirectory(parent=window, title='Choose output folder for the optional manager package')
        if not folder:
            return
        busy[0] = True
        refresh_button.configure(state='disabled')
        update_selection()
        def worker():
            error = None
            log = None
            try:
                log = OperationLog('Build manager package', lambda text: events.put(('line', text)))
                build_manager_package(folder, log)
            except Exception as exc:
                error = str(exc)
            finally:
                if log:
                    log.close()
                events.put(('done', error))
        threading.Thread(target=worker, daemon=False).start()

    poll_job = None

    def poll():
        nonlocal poll_job
        try:
            for _ in range(200):
                kind, value = events.get_nowait()
                if kind == 'line':
                    panel.append(value)
                else:
                    busy[0] = False
                    refresh_button.configure(state='normal')
                    refresh()
                    if value:
                        panel.append('Operation failed: ' + value + '\n')
        except queue.Empty:
            pass
        poll_job = window.after(75, poll)
    install_button = ttk.Button(buttons, text='Enable / Install', command=lambda: operate(True))
    remove_button = ttk.Button(buttons, text='Disable / Uninstall', command=lambda: operate(False))
    source_button = ttk.Button(buttons, text='Build from source...', command=lambda: operate(True, True))
    open_button = ttk.Button(buttons, text='Open', width=17, command=lambda: operate(True, launch=True))
    update_button = ttk.Button(buttons, text='Update', command=lambda: operate(True, update=True))
    update_all_button = ttk.Button(buttons, text='Update All', command=update_everything)
    operation_buttons = [install_button, remove_button, update_button, source_button, open_button]
    refresh_button = ttk.Button(buttons, text='Refresh status', command=refresh)
    package_button = ttk.Button(buttons, text='Build Package...', command=package_manager)
    actions = [*operation_buttons, update_all_button, refresh_button, package_button]
    gap = 6
    action_widths = [button.winfo_reqwidth() + gap for button in actions]
    columns = len(actions) // 2
    compact_width = sum(max(a, b) for a, b in zip(action_widths[:columns], action_widths[columns:]))
    min_width = max(560, compact_width + 24)
    action_columns = None
    layout_width = None
    minimum_update = None

    def schedule_minimum_height():
        nonlocal minimum_update
        if minimum_update is not None:
            window.after_cancel(minimum_update)

        def update_minimum_height():
            nonlocal minimum_update
            minimum_update = None
            height = max(520, window.winfo_reqheight())
            if window.minsize() != (min_width, height):
                window.minsize(min_width, height)

        minimum_update = window.after_idle(update_minimum_height)

    def resize(_event=None):
        nonlocal action_columns, layout_width
        if _event is not None and _event.widget is not window:
            if _event.widget.master is window:
                schedule_minimum_height()
            return
        available = max(min_width, window.winfo_width()) - 24
        if available == layout_width:
            return
        layout_width = available
        for label in (description_label,):
            label.configure(wraplength=available)
        count = len(actions) if sum(action_widths) <= available else columns
        if count != action_columns:
            action_columns = count
            for index, button in enumerate(actions):
                row, column = divmod(index, count)
                button.grid(row=row, column=column, sticky='ew', padx=(0, gap), pady=(0, 4))
        schedule_minimum_height()

    window.minsize(min_width, 520)
    window.bind('<Configure>', resize)
    resize()
    tree.bind('<<TreeviewSelect>>', update_selection)
    query.trace_add('write', render)
    status.trace_add('write', render)
    def close():
        if busy[0]:
            messagebox.showinfo('Operation running', 'Wait for the current operation to finish. Its log is saved automatically.', parent=window)
        else:
            window.destroy()
    def cancel_callbacks(event):
        if event.widget is window:
            for callback in (poll_job, minimum_update):
                if callback is not None:
                    window.after_cancel(callback)

    window.bind('<Destroy>', cancel_callbacks)
    window.protocol('WM_DELETE_WINDOW', close)
    refresh()
    poll_job = window.after(75, poll)
    window.after_idle(lambda: show_one_time_safety_notice(window))
    if parent is None:
        window.mainloop()
    return window
