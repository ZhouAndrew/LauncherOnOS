#!/usr/bin/python3
"""Opt-in security updates for Ubuntu Noble-based Linux Mint; no scheduler."""
# SECURITY WARNING: show this before importing any same-directory-shadowable modules.
import sys
PRIVILEGED_IMPORT_WARNING = 'SECURITY: Privileged updates use a root-owned checksum-verified snapshot and isolated Python (-I). A modified checkout or failed verification stops execution. Use only a trusted source copy.'
_warning_shown = False

def warn_privileged_import():
    global _warning_shown
    if not _warning_shown:
        print(PRIVILEGED_IMPORT_WARNING, file=sys.stderr, flush=True)
        _warning_shown = True

if __name__ == '__main__':
    warn_privileged_import()

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile


# The root entry point is fixed in argv; it never imports sibling modules or
# executes the original user-writable script after authorization. The expected
# checksum comes from the interpreter's already-loaded unprivileged source.
ROOT_BOOTSTRAP = r"""
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

def stop(message):
    print('SECURITY ERROR: ' + message, file=sys.stderr, flush=True)
    raise SystemExit(1)

if os.geteuid() != 0 or not sys.flags.isolated:
    stop('Use sudo with isolated Python for the root bootstrap.')
if len(sys.argv) not in (4, 6):
    stop('Invalid root update request.')
expected, source = sys.argv[1:3]
args = sys.argv[3:]
if not re.fullmatch('[0-9a-f]{64}', expected):
    stop('Invalid approved source checksum.')
if args not in (['--refresh-root'], ['--interactive-root']) and not (
        len(args) == 3 and args[:2] == ['--apply-root', '--expect']
        and re.fullmatch('[0-9a-f]{64}', args[2])):
    stop('Root launcher accepts only approved update actions.')
try:
    with tempfile.TemporaryDirectory(prefix='mint-security-verified-') as directory:
        target = Path(directory) / 'security_updates.py'
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        checksum = hashlib.sha256()
        with os.fdopen(fd, 'rb') as input_file, target.open('xb') as output:
            stat_data = os.fstat(input_file.fileno())
            if not stat.S_ISREG(stat_data.st_mode):
                stop('Refusing a nonregular updater source.')
            while True:
                data = input_file.read(1024 * 1024)
                if not data:
                    break
                checksum.update(data)
                output.write(data)
            output.flush()
            os.fsync(output.fileno())
        if checksum.hexdigest() != expected:
            stop('Updater changed after approval; no root update executed.')
        # Python -I isolates module imports from the script directory and
        # PYTHONPATH; the private directory is root-owned and mode 0700.
        env = {
            'PATH': '/usr/sbin:/usr/bin:/sbin:/bin',
            'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
            'DEBIAN_FRONTEND': 'noninteractive',
        }
        result = subprocess.run(['/usr/bin/python3', '-I', str(target), *args],
                                env=env, check=False)
        raise SystemExit(result.returncode)
except (OSError, ValueError, subprocess.SubprocessError) as exc:
    stop(str(exc))
"""


def privileged_action(*args, transcript=None):
    source = Path(__file__).resolve()
    # The root helper will compare these approved bytes with an fd-opened
    # snapshot and refuses replacements before invoking privileged code.
    approved = hashlib.sha256(source.read_bytes()).hexdigest()
    command_line = [
        'sudo', '/usr/bin/python3', '-I', '-c', ROOT_BOOTSTRAP,
        approved, str(source), *args,
    ]
    if transcript is None:
        return subprocess.call(command_line)
    with subprocess.Popen(command_line, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as process:
        while chunk := process.stdout.read1(8192):
            transcript.write(chunk)
            transcript.flush()
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
        return process.wait()


def require_isolated_root_copy():
    if os.geteuid() != 0:
        raise SafetyError('Root privileges required.')
    path = Path(__file__).resolve()
    parent = path.parent.stat()
    script = path.stat()
    if (not sys.flags.isolated or parent.st_uid != 0
            or parent.st_mode & 0o022 or script.st_uid != 0
            or script.st_mode & 0o022):
        raise SafetyError('Root actions require a root-owned isolated source snapshot.')


LOCK = '/run/lock/mint-security-updates.lock'
APT = '/usr/bin/apt-get'
APT_STATE = Path('/var/lib/system-extension-manager-security')
KEYRING = '/usr/share/keyrings/ubuntu-archive-keyring.gpg'
APT_SCOPE = {
    'Dir::Etc::sourcelist': str(APT_STATE / 'ubuntu.list'),
    'Dir::Etc::sourceparts': '-',
    'Dir::State::lists': str(APT_STATE / 'lists'),
    'Dir::Cache::pkgcache': '',
    'Dir::Cache::srcpkgcache': '',
    'Acquire::AllowInsecureRepositories': 'false',
    'Acquire::AllowDowngradeToInsecureRepositories': 'false',
}
APT_SCOPE_OPTIONS = [arg for key, value in APT_SCOPE.items()
                     for arg in ('-o', key + '=' + value)]
APT_OPTIONS = [
    '-o', 'DPkg::Lock::Timeout=0',
    '-o', 'Acquire::http::Timeout=30', '-o', 'Acquire::https::Timeout=30',
    '-o', 'Acquire::Retries=2',
    '-o', 'APT::Get::AllowUnauthenticated=false',
    '-o', 'Dpkg::Use-Pty=0',
    '--no-remove', '--only-upgrade', '--no-install-recommends',
]


class SafetyError(RuntimeError):
    pass


def open_update_lock():
    # /run/lock may be writable by other users: never follow a planted symlink.
    fd = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1:
            raise SafetyError('Unsafe update lock ownership/type; no changes made.')
        os.fchmod(fd, 0o600)
        return os.fdopen(fd, 'a+', encoding='utf-8')
    except BaseException:
        os.close(fd)
        raise


def command(argv, *, env=None):
    # Simulation parsing must not depend on the user's display language.
    env = dict(os.environ if env is None else env, LC_ALL='C.UTF-8', LANG='C.UTF-8')
    result = subprocess.run(argv, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, env=env, check=False)
    if result.returncode:
        raise SafetyError('Command failed (exit {}): {}\n{}'.format(
            result.returncode, ' '.join(argv), result.stdout))
    return result.stdout


def protected(name):
    name = name.lower().split(':', 1)[0]
    if 'nvidia' in name or 'cuda' in name:
        return True
    if 'firmware' in name or 'microcode' in name:
        return True
    return name.startswith((
        'linux-', 'nvidia-', 'libnvidia-', 'xserver-xorg-video-nvidia',
        'cuda-', 'grub', 'shim', 'initramfs', 'dracut',
        'firmware-', 'fwupd', 'virtualbox-', 'zfs-', 'libkmod',
    )) or name in {
        'dkms', 'nvidia', 'grub', 'shim', 'mokutil', 'kmod',
        'intel-microcode', 'amd64-microcode', 'bcmwl-kernel-source',
    } or bool(re.search(r'(^|[-_])dkms($|[-_])', name))


def ensure_host():
    data = {}
    for line in Path('/etc/os-release').read_text().splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            data[key] = value.strip('"')
    if data.get('ID') != 'linuxmint' or data.get('UBUNTU_CODENAME') != 'noble':
        raise SafetyError('Supported OS: Ubuntu Noble-based Linux Mint 22.x only.')


def check_dpkg():
    result = command(['/usr/bin/dpkg', '--audit'])
    if result.strip():
        raise SafetyError('Incomplete dpkg transaction; repair separately:\n' + result)


def check_locks():
    locks = [p for p in (
        '/var/lib/dpkg/lock-frontend', '/var/lib/dpkg/lock',
        '/var/lib/apt/lists/lock', '/var/cache/apt/archives/lock',
    ) if Path(p).exists()]
    if not locks:
        return
    result = subprocess.run(['/usr/bin/fuser', *locks],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode == 0:
        raise SafetyError('An APT/dpkg process is already running; no locks were removed.')
    if result.returncode != 1:
        raise SafetyError('Cannot safely determine APT/dpkg lock ownership.')


def prepare_apt_scope():
    if not Path(KEYRING).is_file():
        raise SafetyError('Ubuntu archive signing keyring is missing.')
    for directory in (APT_STATE, APT_STATE / 'lists'):
        directory.mkdir(mode=0o755, exist_ok=True)
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise SafetyError('Unsafe APT directory: ' + str(directory))
    with tempfile.NamedTemporaryFile(mode='w', encoding='ascii', dir=APT_STATE,
                                     delete=False) as stream:
        temporary = Path(stream.name)
        try:
            for host, suite in (
                ('archive.ubuntu.com', 'noble'),
                ('archive.ubuntu.com', 'noble-updates'),
                ('security.ubuntu.com', 'noble-security'),
            ):
                stream.write(f'deb [signed-by={KEYRING}] https://{host}/ubuntu '
                             f'{suite} main restricted universe multiverse\n')
            stream.flush()
            os.fchmod(stream.fileno(), 0o644)
            temporary.replace(APT_STATE / 'ubuntu.list')
        finally:
            temporary.unlink(missing_ok=True)


def scoped_cache():
    import apt
    import apt_pkg
    apt_pkg.init()
    if not Path(APT_SCOPE['Dir::Etc::sourcelist']).is_file():
        raise SafetyError('Refresh official Ubuntu indexes before checking for updates.')
    for key, value in APT_SCOPE.items():
        apt_pkg.config.set(key, value)
    return apt.Cache()


def scan():
    ensure_host()
    import apt_pkg
    held = set(command(['/usr/bin/apt-mark', 'showhold']).splitlines())
    cache = scoped_cache()
    wanted, frozen = {}, {}
    for pkg in cache:
        if not pkg.is_installed:
            continue
        name, installed = pkg.name, pkg.installed.version
        if protected(name):
            frozen[name] = installed
            continue
        if name in held or name.split(':', 1)[0] in held:
            continue
        for version in pkg.versions:
            if apt_pkg.version_compare(version.version, installed) <= 0:
                continue
            origins = version.origins
            if not origins or not all(o.trusted and o.origin == 'Ubuntu' for o in origins):
                continue
            if not any(o.archive == 'noble-security' for o in origins):
                continue
            if name not in wanted or apt_pkg.version_compare(version.version, wanted[name]) > 0:
                wanted[name] = version.version
    return dict(sorted(wanted.items())), frozen


def digest(packages):
    encoded = json.dumps(packages, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def simulate(packages):
    specs = [name + '=' + version for name, version in sorted(packages.items())]
    output = command([APT, *APT_SCOPE_OPTIONS, '--simulate', *APT_OPTIONS, 'install', *specs])
    installed = {}
    for line in output.splitlines():
        if line.startswith(('Remv ', 'Purg ')):
            raise SafetyError('APT proposed removal: ' + line)
        if line.startswith('Inst '):
            match = re.match(r'^Inst\s+(\S+)\s+\[([^\]]+)\]\s+\((\S+)(?:\s|\))', line)
            if not match:
                raise SafetyError('APT proposed a new or unknown installation: ' + line)
            name, _, version = match.groups()
            if name in installed or protected(name) or packages.get(name) != version:
                raise SafetyError('APT proposed an unapproved upgrade: ' + line)
            installed[name] = version
        if line.startswith('Conf '):
            match = re.match(r'^Conf\s+(\S+)\s+\((\S+)(?:\s|\))', line)
            if not match:
                raise SafetyError('APT proposed an unknown configuration: ' + line)
            name, version = match.groups()
            if packages.get(name) != version or protected(name):
                raise SafetyError('APT proposed an unapproved configuration: ' + line)
    if installed != packages:
        raise SafetyError('APT simulation did not match the approved security updates.')
    return specs


def apply(expected):
    if os.geteuid() != 0:
        raise SafetyError('Root authorization required for installation.')
    with open_update_lock() as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SafetyError('Another manual security update is already running.') from None
        check_locks()
        check_dpkg()
        packages, frozen = scan()
        if digest(packages) != expected:
            raise SafetyError('Security update plan changed. Check again; no changes made.')
        if not packages:
            print('No eligible security updates; nothing changed.', flush=True)
            return
        specs = simulate(packages)
        check_locks()
        check_dpkg()
        print('Simulation passed: {} approved upgrades, no new packages or removals.'.format(len(specs)), flush=True)
        env = dict(os.environ, DEBIAN_FRONTEND='noninteractive',
                   NEEDRESTART_MODE='l', APT_LISTCHANGES_FRONTEND='none')
        print('Installing approved security updates...', flush=True)
        args = [APT, *APT_SCOPE_OPTIONS, '-y', *APT_OPTIONS, '-o', 'Dpkg::Options::=--force-confold', 'install', *specs]
        result = subprocess.run(args, env=env, check=False)
        if result.returncode:
            raise SafetyError('APT exited with {}; installation may be partial.'.format(result.returncode))
        installed, frozen_after = scan_installed(packages, frozen)
        if installed or frozen_after:
            raise SafetyError('Post-install verification failed: ' + str(installed + frozen_after))
        check_dpkg()
        print('Verified {} security updates; protected package versions unchanged.'.format(len(packages)), flush=True)
        print('No timers, holds, autoremove or reboots were configured.', flush=True)


def scan_installed(packages, frozen):
    cache = scoped_cache()
    mismatches, protected_changes = [], []
    for name, version in packages.items():
        actual = cache[name].installed.version if cache[name].is_installed else None
        if actual != version:
            mismatches.append('{}: expected {}, found {}'.format(name, version, actual))
    for name, version in frozen.items():
        actual = cache[name].installed.version if cache[name].is_installed else None
        if actual != version:
            protected_changes.append('PROTECTED {}: {} -> {}'.format(name, version, actual))
    return mismatches, protected_changes


def refresh():
    if os.geteuid() != 0:
        raise SafetyError('Root authorization required to refresh APT indexes.')
    ensure_host()
    with open_update_lock() as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SafetyError('Another manual security update is already running.') from None
        check_locks()
        check_dpkg()
        prepare_apt_scope()
        print('Refreshing official Ubuntu indexes; no packages will be installed...', flush=True)
        print(command([APT, *APT_SCOPE_OPTIONS, '-o', 'DPkg::Lock::Timeout=0',
                       '-o', 'APT::Update::Error-Mode=any',
                       '-o', 'Acquire::http::Timeout=30', '-o', 'Acquire::https::Timeout=30',
                       '-o', 'Acquire::Retries=2', 'update']), flush=True)
        print('APT index refresh completed.', flush=True)


def result_directory():
    base = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state')
    return base / 'system-extension-manager/logs'


def show_results():
    paths = sorted(result_directory().glob('security-updates-standalone-*.log'),
                   key=lambda path: path.name, reverse=True)
    for path in paths:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as log:
            if not stat.S_ISREG(os.fstat(log.fileno()).st_mode):
                continue
            print(f'\n=== {path.name} ===')
            for line in log:
                print(line.decode('utf-8', errors='replace'), end='')
    if not paths:
        print('No standalone Security Updates runs recorded.')


def interactive():
    if os.geteuid() == 0 or not sys.stdin.isatty():
        raise SafetyError('Run Security Updates as your desktop user in an interactive terminal.')
    warn_privileged_import()
    print('Authorizing this manual session. Installation still requires UPDATE.', flush=True)
    if os.environ.get('SEM_SECURITY_TRANSCRIPT') == '1':
        return privileged_action('--interactive-root')

    from datetime import datetime
    folder = result_directory()
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    prefix = 'security-updates-standalone-' + datetime.now().strftime('%Y%m%d-%H%M%S-')
    with tempfile.NamedTemporaryFile(dir=folder, prefix=prefix, suffix='.log',
                                     delete=False) as log:
        print('Run log: ' + log.name, flush=True)
        code = privileged_action('--interactive-root', transcript=log)
        log.write(f'\nExit code: {code}\n'.encode())
    return code


def interactive_root():
    if not sys.stdin.isatty():
        raise SafetyError('An interactive terminal is required.')
    print('=== Manual security updates (Linux Mint 22.x) ===', flush=True)
    print('Kernel / NVIDIA / DKMS / firmware / boot components are protected.', flush=True)
    print('Keep this terminal open. Updates can restart services.', flush=True)
    refresh()
    wanted, frozen = scan()
    print('Eligible security updates: {} (protected packages: {})'.format(len(wanted), len(frozen)), flush=True)
    if not wanted:
        print('No eligible security updates. Nothing to install.', flush=True)
        return
    for name, version in wanted.items():
        print('  {} -> {}'.format(name, version), flush=True)
    simulate(wanted)
    try:
        approval = input('Type UPDATE to install, or press Enter to cancel: ').strip()
    except EOFError:
        approval = ''
    if approval != 'UPDATE':
        print('Cancelled; no packages installed.', flush=True)
        return
    apply(digest(wanted))
    print('Update completed and verified.', flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--results', action='store_true', help='show saved standalone run results')
    group.add_argument('--interactive-root', action='store_true', help=argparse.SUPPRESS)
    group.add_argument('--interactive', action='store_true', help='refresh, review and approve updates in a terminal')
    group.add_argument('--check', action='store_true', help='read-only scan of cached APT metadata')
    group.add_argument('--refresh', action='store_true', help='refresh APT package indexes with explicit authorization')
    group.add_argument('--apply', action='store_true', help='manually install only safe eligible security updates')
    group.add_argument('--refresh-root', action='store_true', help=argparse.SUPPRESS)
    group.add_argument('--apply-root', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--json', action='store_true', help='machine-readable --check output')
    parser.add_argument('--expect', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    warn_privileged_import()
    try:
        if args.results:
            show_results()
        elif args.interactive_root:
            require_isolated_root_copy()
            interactive_root()
        elif args.refresh_root:
            require_isolated_root_copy()
            refresh()
        elif args.apply_root:
            require_isolated_root_copy()
            if not args.expect or not re.fullmatch('[0-9a-f]{64}', args.expect):
                raise SafetyError('Missing or invalid approved update fingerprint.')
            apply(args.expect)
        elif args.refresh:
            return privileged_action('--refresh-root')
        elif args.interactive:
            return interactive()
        elif args.apply:
            wanted, _ = scan()
            if not wanted:
                print('No eligible security updates.')
                return 0
            print('Requested security updates:')
            for name, version in wanted.items():
                print('  {} -> {}'.format(name, version))
            simulate(wanted)
            if not sys.stdin.isatty() or input('Type UPDATE to install: ').strip() != 'UPDATE':
                print('Cancelled; no packages installed.')
                return 0
            return privileged_action('--apply-root', '--expect', digest(wanted))
        elif args.check:
            wanted, frozen = scan()
            data = {'packages': wanted, 'digest': digest(wanted), 'protected_count': len(frozen)}
            if args.json:
                print(json.dumps(data, sort_keys=True))
            else:
                print('{} eligible Ubuntu security updates; {} protected packages.'.format(len(wanted), len(frozen)))
                for name, version in wanted.items():
                    print('  {} -> {}'.format(name, version))
        else:
            parser.print_help()
        return 0
    except (SafetyError, OSError, ImportError, subprocess.SubprocessError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
