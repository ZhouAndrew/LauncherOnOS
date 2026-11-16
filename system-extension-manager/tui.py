#!/usr/bin/python3
"""Manage extensions, manual security updates and HomeBackUp on a local console."""
import argparse
import fcntl
import getpass
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import warnings

INSTALLED = Path('/usr/share/system-extension-manager')
ENTRY = INSTALLED / 'tui.py'
BACKUP = Path('/usr/lib/mint-homebackup-extension/admin')
SUDO = '/usr/bin/sudo'
SYSTEM_PATH = '/usr/sbin:/usr/bin:/sbin:/bin'


def local_console():
    """Check the actual foreground Linux virtual terminal, not session variables."""
    try:
        devices = [os.fstat(fd) for fd in (0, 1, 2)]
        device = devices[0].st_rdev
        if not all(stat.S_ISCHR(info.st_mode) and info.st_rdev == device
                   for info in devices):
            return False
        vt = os.minor(device)
        if os.major(device) != 4 or not 1 <= vt <= 63:
            return False
        # Fields after the executable name start at field 3 (state).
        tty_number = Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()[4]
        if int(tty_number) != device or os.tcgetpgrp(0) != os.getpgrp():
            return False
        active, _, _ = struct.unpack('HHH', fcntl.ioctl(0, 0x5603, bytes(6)))  # VT_GETSTATE
        return active == vt
    except (OSError, ValueError, IndexError):
        return False


def trusted_file(path):
    """Verify the installed entry and its ancestors before administrator work."""
    if path.resolve() != path or not path.is_file():
        raise ValueError(f'Install the manager package first. Expected {path}.')
    for entry in (path, *path.parents):
        info = entry.stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError(f'Administrator operations require a root-owned, protected path: {entry}')


def package_operation(action, key):
    """Root entry for fixed catalog operations, invoked by system sudo."""
    if os.geteuid() != 0:
        raise ValueError('Administrator authorization is required.')
    trusted_file(ENTRY)
    item = lifecycle.plugin(key)
    if item.get('kind') == 'portable':
        raise ValueError('This tool has no extension package.')
    if action == 'remove':
        # dpkg removes only this package and refuses unsatisfied dependencies.
        command = ['/usr/bin/dpkg', '--remove', item['package']]
    else:
        command = lifecycle.command(key, True)
    return subprocess.call(command, env={
        'PATH': SYSTEM_PATH, 'LC_ALL': 'C.UTF-8',
        'DEBIAN_FRONTEND': 'noninteractive',
    })


class ConsoleAuthorization:
    def run(self, key, enable, _approved, log):
        return log.run([SUDO, '/usr/bin/python3', '-I', str(ENTRY),
                        '--package-operation', 'install' if enable else 'remove', key],
                       check=False)


def require_installed():
    if Path(__file__).resolve() != ENTRY:
        raise ValueError('Install the manager package to perform administrator operations. '
                         'The source checkout can show extension status.')
    if not local_console():
        raise ValueError('Switch back to the local virtual console before continuing.')
    trusted_file(ENTRY)


def choose(title, choices, back='Back'):
    while True:
        print(f'\n{title}', flush=True)
        for number, (label, _) in enumerate(choices, 1):
            print(f'  {number}. {label}')
        print(f'  0. {back}')
        choice = input('Select a number [0]: ').strip()
        if choice in ('', '0'):
            return None
        for number, (_, value) in enumerate(choices, 1):
            if choice == str(number):
                return value
        print('Choose one of the numbers shown.')


def confirm(summary):
    print('\n' + summary)
    if input('Continue? [y/N] ').strip().lower() in ('y', 'yes'):
        return True
    print('Cancelled.')
    return False


def package_log(label, operation):
    with_log = OperationLog(label, emit=lambda text: None)
    print(f'Working. The result will appear here.\nLog: {with_log.path}', flush=True)
    try:
        return operation(with_log)
    finally:
        with_log.close()


def extensions():
    while True:
        items = [(item, lifecycle.extension_state(item)) for item in lifecycle.plugins()
                 if item.get('kind') != 'portable']
        choices = [(item['name'] + ' — ' + state['state'], (item, state))
                   for item, state in items]
        selected = choose('Extensions', choices)
        if selected is None:
            return
        item, state = selected
        print(f"\n{item['description']}")
        actions = [(label, key) for key, label in (
            ('install', 'Install ' + item['version']),
            ('update', 'Update to ' + item['version']),
            ('remove', 'Uninstall'),
        ) if state[key]]
        action = choose(item['name'], actions) if actions else None
        if action:
            try:
                require_installed()
                detail = ' This affects all users.'
                if item['id'] == 'homebackup' and action in ('update', 'remove'):
                    detail += ' Check the backup service and schedule first.'
                if confirm(f"{action.capitalize()} {item['name']}?{detail}"):
                    version = package_log(item['name'], lambda log: lifecycle.change(
                        item['id'], action != 'remove', log, update=action == 'update',
                        admin=ConsoleAuthorization(),
                    ))
                    print(f"Verified: {item['name']} " + ('is absent.' if version is None
                                                           else f'{version} is installed.'))
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
                print(f'Error: {exc}', file=sys.stderr)


def update_extensions():
    planned = lifecycle.update_all_plan()
    if not planned:
        print('No installed extensions need an update.')
        return
    for item, previous in planned:
        print(f"  {item['name']}: {previous} -> {item['version']}")
    require_installed()
    if confirm('Apply these bundled extension updates?'):
        result = package_log('Update installed extensions', lambda log: lifecycle.update_all(
            log, include_security=False, admin=ConsoleAuthorization(), plan=planned))
        print(f"Verified updates: {len(result['updated'])}.")
        for reason in result['deferred'].values():
            print(f'Deferred: {reason}')


def security_updates():
    require_installed()
    script = lifecycle.portable_script(lifecycle.plugin('security-updates'))
    trusted_file(script)
    # The existing updater handles sudo, exact-plan confirmation and its transcript.
    environment = {**os.environ, 'PATH': SYSTEM_PATH}
    environment.pop('SEM_SECURITY_TRANSCRIPT', None)
    subprocess.run(['/usr/bin/python3', '-I', str(script), '--interactive'],
                   env=environment, check=True)


def homebackup():
    require_installed()
    item = lifecycle.plugin('homebackup')
    version = lifecycle.installed_version(item['package'])
    if version is None or subprocess.run(
            ['/usr/bin/dpkg', '--compare-versions', version, 'lt', item['version']],
            check=False).returncode != 1:
        print(f"Install or update HomeBackUp to the bundled version ({item['version']}) in Extensions.")
        return
    trusted_file(BACKUP)
    choices = [
        ('View disk and schedule status', ('status', '')),
        ('Start backup', ('run', 'The backup can apply the configured archive retention.')),
        ('List backup archives', ('list', 'List the archives in the existing Borg repository.')),
        ('Preview archive retention', ('preview', 'Preview the archives selected for removal.')),
        ('Check archive structure', ('check', 'Check archive structure.')),
        ('Verify file data', ('verify-data', 'Read and verify archived data. This can take a long time.')),
        ('Enable monthly backups', ('enable', 'A missed backup may start immediately.')),
        ('Stop backups and disable the monthly timer', ('disable', 'This can interrupt an active backup.')),
        ('Set Borg passphrase and enable monthly backups', (
            'enroll', 'After validating the passphrase, HomeBackUp will enable monthly backups.')),
    ]
    environment = {**os.environ, 'PATH': SYSTEM_PATH, 'SYSTEMD_PAGER': 'cat'}
    while selected := choose('HomeBackUp', choices):
        action, summary = selected
        try:
            if action == 'status':
                subprocess.run([str(BACKUP), action], env=environment, check=True)
            elif confirm(summary):
                require_installed()
                if action == 'enroll':
                    subprocess.run([SUDO, '/usr/bin/python3', '-I', str(ENTRY),
                                    '--enroll-backup'], check=True)
                else:
                    subprocess.run([SUDO, str(BACKUP), action], check=True)
                if action in ('enroll', 'enable', 'disable'):
                    subprocess.run([str(BACKUP), 'status'], env=environment, check=True)
                print('HomeBackUp operation finished.')
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            print(f'HomeBackUp operation failed: {exc}', file=sys.stderr)


def enroll_backup():
    if os.geteuid() != 0:
        raise ValueError('Administrator authorization is required.')
    trusted_file(ENTRY)
    trusted_file(BACKUP)
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        try:
            secret = getpass.getpass('Borg repository passphrase (hidden): ')
        except getpass.GetPassWarning:
            raise ValueError('A terminal with hidden input is required.') from None
    if not secret or '\n' in secret or '\r' in secret:
        raise ValueError('Enter a nonempty, single-line Borg passphrase.')
    return subprocess.run([str(BACKUP), 'enroll'], input=secret + '\n', text=True,
                          env={'PATH': SYSTEM_PATH, 'LC_ALL': 'C.UTF-8'}).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    internal = parser.add_mutually_exclusive_group()
    internal.add_argument('--package-operation', nargs=2, help=argparse.SUPPRESS)
    internal.add_argument('--enroll-backup', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.package_operation is not None:
        action, key = args.package_operation
        if action not in ('install', 'remove'):
            parser.error('invalid package operation')
        return package_operation(action, key)
    if args.enroll_backup:
        return enroll_backup()
    if not local_console():
        raise ValueError('Open a local Linux console with Ctrl+Alt+F3, sign in and run '
                         'system-extension-manager-tui there.')
    if os.geteuid() == 0:
        raise ValueError('Start the TUI without sudo. It requests authorization when needed.')
    choices = [
        ('Extensions and package status', extensions),
        ('Update installed extensions', update_extensions),
        ('Review system security updates', security_updates),
        ('HomeBackUp', homebackup),
    ]
    while operation := choose('System Extension Manager', choices, back='Exit'):
        try:
            operation()
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            print(f'Error: {exc}', file=sys.stderr)
    return 0


# With -I the installed entry must explicitly load its sibling modules.
# The packaged launcher uses the fixed root-owned path above.
if Path(__file__).resolve() == ENTRY:
    for name in ('tui.py', 'lifecycle.py', 'execution.py', 'extensions.json'):
        trusted_file(INSTALLED / name)
    sys.path.insert(0, str(INSTALLED))
import lifecycle
from execution import OperationLog


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (EOFError, KeyboardInterrupt):
        print('\nConsole closed.')
    except (OSError, ValueError, RuntimeError) as exc:
        sys.exit(f'Error: {exc}')
