#!/usr/bin/python3
"""Opt-in security updates for Ubuntu Noble-based Linux Mint; no scheduler."""
# SECURITY WARNING: show this before importing any same-directory-shadowable modules.
import sys
PRIVILEGED_IMPORT_WARNING = 'WARNING - UNFIXED PRIVILEGED PYTHON IMPORT RISK: The portable updater verifies only its main file; sudo Python may load extra modules from the same directory. Use a private trusted source copy and directory. Do not authorize a modified or shared writable copy. This warning is not a fix.'
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


# SECURITY WARNING: same-directory imports and reopening a writable script during sudo
# are NOT isolated by the main-file checksum. The following notice is disclosure only.
LOCK = '/run/lock/mint-security-updates.lock'
APT = '/usr/bin/apt-get'
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


def scan():
    ensure_host()
    import apt
    import apt_pkg
    apt_pkg.init()
    held = set(command(['/usr/bin/apt-mark', 'showhold']).splitlines())
    cache = apt.Cache()
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
    output = command([APT, '--simulate', *APT_OPTIONS, 'install', *specs])
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
        args = [APT, '-y', *APT_OPTIONS, '-o', 'Dpkg::Options::=--force-confold', 'install', *specs]
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
    import apt
    cache = apt.Cache()
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
        print('Refreshing APT indexes; no packages will be installed...', flush=True)
        print(command([APT, '-o', 'DPkg::Lock::Timeout=0',
                       '-o', 'APT::Update::Error-Mode=any',
                       '-o', 'Acquire::http::Timeout=30', '-o', 'Acquire::https::Timeout=30',
                       '-o', 'Acquire::Retries=2', 'update']), flush=True)
        print('APT index refresh completed.', flush=True)


def interactive():
    """Refresh and inspect updates in a real terminal; install only after explicit approval."""
    if os.geteuid() == 0:
        raise SafetyError('Run this interactive command as your normal desktop user.')
    if not sys.stdin.isatty():
        raise SafetyError('An interactive terminal is required. No background operation is allowed.')
    warn_privileged_import()
    script = str(Path(__file__).resolve())
    print('=== Manual security updates (Linux Mint 22.x) ===', flush=True)
    print('Kernel / NVIDIA / DKMS / firmware / boot components are protected.', flush=True)
    print('No timers, background upgrades, autoremove or reboot will be configured.', flush=True)
    # WARNING: closing the terminal can interrupt APT; there is no automatic rollback.
    print('Keep this terminal open until the operation finishes.', flush=True)
    print('Updates can restart services. Interrupted installs cannot be automatically rolled back.\n', flush=True)
    print('Refreshing package indexes; sudo may request your password...', flush=True)
    if subprocess.call(['sudo', '/usr/bin/python3', script, '--refresh-root']):
        raise SafetyError('APT index refresh failed or was cancelled; nothing was installed.')
    wanted, frozen = scan()
    print('Eligible security updates: {} (protected packages: {})'.format(len(wanted), len(frozen)), flush=True)
    if not wanted:
        print('No eligible security updates. Nothing to install.', flush=True)
        return
    for name, version in wanted.items():
        print('  {} -> {}'.format(name, version), flush=True)
    print('\nSimulating APT transaction...', flush=True)
    simulate(wanted)
    print('Simulation approved: no additions, removals or unapproved upgrades.', flush=True)
    print('Type UPDATE to install these updates. Any other input cancels.', flush=True)
    if input('Confirm [UPDATE]: ').strip() != 'UPDATE':
        print('Cancelled; no packages installed.', flush=True)
        return
    if subprocess.call(['sudo', '/usr/bin/python3', script,
                        '--apply-root', '--expect', digest(wanted)]):
        raise SafetyError('Update failed or was cancelled. A partial installation may exist; inspect the output.')
    print('Update completed and verified.', flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
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
        if args.refresh_root:
            refresh()
        elif args.apply_root:
            if not args.expect or not re.fullmatch('[0-9a-f]{64}', args.expect):
                raise SafetyError('Missing or invalid approved update fingerprint.')
            apply(args.expect)
        elif args.refresh:
            return subprocess.call(['sudo', '/usr/bin/python3', str(Path(__file__).resolve()), '--refresh-root'])
        elif args.interactive:
            interactive()
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
            return subprocess.call(['sudo', '/usr/bin/python3', str(Path(__file__).resolve()),
                                    '--apply-root', '--expect', digest(wanted)])
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
