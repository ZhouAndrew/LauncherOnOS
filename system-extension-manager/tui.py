#!/usr/bin/python3
"""Manage extensions, manual security updates and HomeBackUp on a local console."""
import argparse
import fcntl
import getpass
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys
import termios
import textwrap
import warnings

try:
    import curses
except ImportError:
    curses = None

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


def rich_display(mode):
    term = os.environ.get('TERM', '')
    if (curses is None or mode == 'plain' or not sys.stdout.isatty() or not term or term == 'dumb'
            or (mode == 'auto' and ('NO_COLOR' in os.environ or not sys.stdin.isatty()))):
        return False
    try:
        curses.setupterm(term, sys.stdout.fileno())
        return curses.tigetstr('bold') == b'\x1b[1m' and bool(curses.tigetstr('sgr0'))
    except (OSError, curses.error):
        return False


def line(message, indent=''):
    width = max(12, min(78, shutil.get_terminal_size((80, 24)).columns) - 1)
    print(textwrap.fill(message, width=width, initial_indent=indent,
                        subsequent_indent=indent))


def can_navigate():
    columns, rows = shutil.get_terminal_size((0, 0))
    return (sys.stdin.isatty() and rows >= 8 and columns >= 28
            and all(curses.tigetstr(name) for name in ('cup', 'el', 'kcuu1', 'kcud1')))


def navigate(screen, title, choices, back):
    entries = [(f'0. {back}', None)]
    entries.extend((f'{number}. {label}', value)
                   for number, (label, value) in enumerate(choices, 1))
    selected = 0
    offset = 0
    while True:
        rows, columns = screen.getmaxyx()
        if rows < 8 or columns < 28:
            return False, None
        # Keep the full label of the selected action readable on narrow screens.
        detail = textwrap.wrap(entries[selected][0], width=columns - 1)
        visible = rows - 4 - len(detail)
        if visible < 1:
            return False, None
        offset = min(max(selected - visible + 1, offset), selected)
        screen.erase()
        screen.addnstr(0, 0, title, columns - 1, curses.A_BOLD)
        for row, (label, _) in enumerate(entries[offset:offset + visible], 2):
            screen.addnstr(row, 0, label, columns - 1,
                           curses.A_REVERSE if offset + row - 2 == selected else 0)
        for row, label in enumerate(detail, rows - 2 - len(detail)):
            screen.addnstr(row, 0, label, columns - 1, curses.A_BOLD)
        screen.addnstr(rows - 1, 0, 'Up/Down, Enter, Esc: menu', columns - 1)
        screen.refresh()
        key = screen.getch()
        if key in (10, 13, curses.KEY_ENTER):
            return True, entries[selected][1]
        if key in (27, 9):
            return False, None
        if key == curses.KEY_DOWN:
            selected = min(selected + 1, len(entries) - 1)
        elif key == curses.KEY_UP:
            selected = max(selected - 1, 0)
        elif key in (curses.KEY_HOME, curses.KEY_END):
            selected = 0 if key == curses.KEY_HOME else len(entries) - 1
        elif ord('0') <= key <= ord('9') and key - ord('0') < len(entries):
            return True, entries[key - ord('0')][1]


def choose(title, choices, back='Back', *, rich=False, result=''):
    feedback = ''
    while True:
        navigation = rich and can_navigate()
        heading = f'\x1b[1m{title}\x1b[0m' if rich else title
        print(f'\n{heading}', flush=True)
        compact = shutil.get_terminal_size((80, 24)).columns <= 32
        indent = '' if compact else '  '
        for number, (label, _) in enumerate(choices, 1):
            line(f'{number}. {label}', indent)
        back_label = f'0. {back} (or Enter alone)' if compact else f'0. {back}'
        line(back_label, indent)
        if navigation:
            line('Type m for an arrow-key menu.', '  ')
        if result:
            print()
            for row in result.splitlines():
                line(row)
        if feedback:
            line(feedback)
        if not compact:
            line(f'Press Enter alone for {back.lower()}.')
        line('Enter a number and press Enter.')
        choice = input('Choice: ').strip()
        feedback = ''
        if choice.lower() == 'm' and navigation:
            try:
                accepted, value = curses.wrapper(navigate, title, choices, back)
                if accepted:
                    return value
            except curses.error:
                feedback = 'Arrow-key menu unavailable. Use the numbers shown.'
            continue
        if choice in ('', '0'):
            return None
        for number, (_, value) in enumerate(choices, 1):
            if choice == str(number):
                return value
        feedback = (f'Use a number from 0 to {len(choices)}.' if compact
                    else f'That choice is unavailable. Use a number from 0 to {len(choices)}.')

def confirm(summary):
    print()
    line(summary)
    line('Type yes to continue.')
    line('Press Enter to cancel.')
    try:
        if sys.stdin.isatty():
            termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
        if input('Your answer: ').strip().lower() == 'yes':
            return True
    except EOFError:
        pass
    except (OSError, termios.error):
        print('Could not read a fresh answer.')
    print('Cancelled.')
    return False


def package_log(label, operation):
    with_log = OperationLog(label, emit=lambda text: None)
    print(f'Working. The result will appear here.\nLog: {with_log.path}', flush=True)
    try:
        return operation(with_log)
    finally:
        with_log.close()


def extension_rows():
    return [(item, lifecycle.extension_state(item)) for item in lifecycle.plugins()
            if item.get('kind') != 'portable']


def status_json():
    rows = [{'id': item['id'], 'package': item['package'],
             'bundled_version': item['version'], **state}
            for item, state in extension_rows()]
    print(json.dumps({'schema_version': 1, 'extensions': rows}, ensure_ascii=True))
    return int(any(row['state'].startswith('Unknown:') for row in rows))


def package_label(state):
    if state['state'].startswith('Enabled: '):
        return 'Installed: ' + state['state'].removeprefix('Enabled: ')
    if state['state'] == 'Disabled':
        return 'Not installed'
    return state['state']


def extensions(*, rich=False, read_only=False):
    result = ''
    while True:
        choices = [(item['name'] + ': ' + package_label(state), (item, state))
                   for item, state in extension_rows()]
        title = 'Extensions (view only)' if read_only else 'Extensions'
        selected = choose(title, choices, back='Exit' if read_only else 'Back',
                          rich=rich, result=result)
        if selected is None:
            return
        item, state = selected
        result = ''
        if state['state'].startswith('Unknown:'):
            result = (f"Could not check {item['name']}. The list has been checked again. "
                      'If the status is still unknown, try again later.')
            continue
        print()
        line(item['description'])
        if read_only:
            input('Press Enter to return. ')
            continue
        actions = [(label, key) for key, label in (
            ('install', 'Install ' + item['version']),
            ('update', 'Update to ' + item['version']),
            ('remove', 'Uninstall'),
        ) if state[key]]
        action = choose(item['name'], actions, rich=rich) if actions else None
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
    result = subprocess.run(['/usr/bin/python3', '-I', str(script), '--interactive'],
                            env=environment, check=False)
    if result.returncode:
        line('Security updates did not finish.')
        line('Check the update message and log above before retrying.')
        line(f'Exit code: {result.returncode}.')
        choices = [('Check software package status (read only)', True)]
        status = ''
        while choose('After an update failure', choices, result=status):
            status = package_audit()


def package_audit():
    try:
        audit = subprocess.run(['/usr/bin/dpkg', '--audit'], capture_output=True,
                               text=True, errors='replace', timeout=15, check=False,
                               env={**os.environ, 'LC_ALL': 'C.UTF-8'})
    except (OSError, subprocess.TimeoutExpired):
        return 'Could not check software packages. Try the check again later.'
    for row in (audit.stdout + audit.stderr).splitlines():
        if row.strip():
            line(row)
    if audit.returncode or audit.stderr.strip():
        return 'Could not confirm the package state. Review the check output above.'
    if audit.stdout.strip():
        return 'Some packages need attention. Ask for help before installing updates.'
    return ('No incomplete packages found. Fix the original issue before trying again.')


BACKUP_STATUS_LABELS = {
    '每月定时器安装状态：': 'Monthly schedule: ',
    '每月定时器运行状态：': 'Monthly schedule activity: ',
    '旧定时器状态：': 'Previous schedule: ',
    '备份磁盘挂载：': 'Backup drive: ',
    '已挂载正确磁盘': 'Ready',
    '未挂载或 UUID 不符': 'Missing or wrong drive',
}


def backup_status_text(text):
    for original, english in BACKUP_STATUS_LABELS.items():
        text = text.replace(original, english)
    return text


def backup_status_summary(output):
    entries = dict(row.split(': ', 1) for row in backup_status_text(output).splitlines() if ': ' in row)
    schedule = entries.get('Monthly schedule')
    active = entries.get('Monthly schedule activity')
    if schedule in ('enabled', 'enabled-runtime'):
        monthly = 'On' if active == 'active' else 'Enabled, but not running'
    elif schedule in ('disabled', 'masked', 'masked-runtime'):
        monthly = 'Off' if active in ('inactive', 'failed') else 'Off for startup, timer still running'
    else:
        monthly = 'Could not verify'
    drive = entries.get('Backup drive')
    if drive == 'Missing or wrong drive':
        drive = 'Connect or mount the backup drive.'
    elif drive != 'Ready':
        drive = 'Could not verify.'
    return f'Backup drive: {drive}\nMonthly backups: {monthly}'


def backup_output(text):
    for row in backup_status_text(text).splitlines():
        if row and row.isascii() and all(c.isprintable() or c == '\t' for c in row):
            line(row.expandtabs(4))


def backup_command(action, argv):
    def run(log):
        result = log.run(argv, env={
            'PATH': SYSTEM_PATH, 'SYSTEMD_PAGER': 'cat', 'SYSTEMD_COLORS': '0',
        }, check=False)
        return result, log.path

    result, path = package_log('HomeBackUp: ' + action, run)
    backup_output(result.stdout)
    return result, path


def backup_failure(output):
    if 'Backup setup cancelled.' in output:
        return 'Cancelled. Monthly backup settings did not change.'
    if '解密验证失败，保持旧密码不变。' in output:
        return 'Could not unlock the backup. Check the drive and backup password, then try again.'
    if any(message in output for message in (
            '请先设置 Borg 仓库密码。', '尚未保存 Borg 密码；请先执行设置。')):
        return 'Backup setup is needed. Choose Turn on monthly backups to set it up.'
    if '找不到原有 Borg 仓库' in output:
        return 'The backup folder was not found on this drive. Check that the correct drive is connected.'
    if '旧 homebackup-monthly.timer 已启用' in output:
        return 'An older monthly backup schedule is still on. Ask for help switching schedules before trying again.'
    if any(message in output for message in (
            'HomeBackUp 未挂载。', '备份目标 UUID 不符。', '未挂载或 UUID 不符')):
        return 'Failed. Connect or mount the correct backup drive, then try again.'
    return 'Failed. See the operation log for details.'


def homebackup(*, rich=False):
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
        ('Check if the drive is ready and monthly backups are on', ('status', '')),
        ('Start backup', ('run', 'Start backup? After checking the new backup, this may delete older backups.')),
        ('List saved backups', ('list', 'Show the backups already saved on the drive.')),
        ('See which old backups would be deleted', ('preview', 'Show what cleanup would delete. Nothing will be deleted.')),
        ('Quick check of saved backups', ('check', 'Check backup records without reading every saved file.')),
        ('Check every saved file (slow)', ('verify-data', 'Read and verify all saved file data. This can take a long time.')),
        ('Turn on monthly backups', (
            'enable', 'Turn on monthly backups? If a backup was missed, one may start now.')),
        ('Stop backups and turn off monthly backups', (
            'disable', 'Turn off monthly backups? This can interrupt a backup that is running.')),
    ]
    result = ''
    while selected := choose('HomeBackUp', choices, rich=rich, result=result):
        action, summary = selected
        try:
            if action == 'status':
                status, path = backup_command(action, [str(BACKUP), action])
                result = (f'{backup_failure(status.stdout)}\nLog: {path}'
                          if status.returncode else backup_status_summary(status.stdout))
                continue
            if action not in ('list', 'preview') and not confirm(summary):
                result = 'Cancelled. No changes made.'
                continue
            require_installed()
            if action == 'enable':
                args = [SUDO, '/usr/bin/python3', '-I', str(ENTRY), '--enroll-backup']
            else:
                args = [SUDO, str(BACKUP), action]
            operation, path = backup_command(action, args)
            if operation.returncode:
                result = backup_failure(operation.stdout)
                if action == 'run' and result.startswith('Failed. See'):
                    try:
                        status, _ = backup_command('status', [str(BACKUP), 'status'])
                    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                        pass  # Keep the original failure if the status probe also fails.
                    else:
                        if status.returncode == 0:
                            result = backup_failure(status.stdout)
                result += f'\nLog: {path}'
                continue
            if action in ('enable', 'disable'):
                status, _ = backup_command('status', [str(BACKUP), 'status'])
                result = (backup_status_summary(status.stdout) if not status.returncode
                          else 'Could not verify whether monthly backups are on or off.')
            elif action == 'run':
                result = f'Backup succeeded. The new archive was verified.\nLog: {path}'
            else:
                completed = {
                    'list': 'Saved backups are listed above.',
                    'preview': 'Cleanup preview is above. No backups were deleted.',
                    'check': 'Quick check passed. Backup records are readable.',
                    'verify-data': 'File data check passed.',
                }
                result = f'{completed[action]}\nLog: {path}'
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            print(f'HomeBackUp operation failed: {exc}', file=sys.stderr)
            result = 'HomeBackUp could not finish. See the error above.'


def enroll_backup():
    if os.geteuid() != 0:
        raise ValueError('Administrator authorization is required.')
    trusted_file(ENTRY)
    trusted_file(BACKUP)
    environment = {'PATH': SYSTEM_PATH, 'LC_ALL': 'C.UTF-8'}
    existing = subprocess.run([str(BACKUP), 'use-existing'], text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              env=environment, check=False)
    if not existing.returncode:
        print('Monthly backups are on. Used the saved backup password.', flush=True)
        return 0
    if not any(message in existing.stdout for message in (
            '尚未保存 Borg 密码；请先执行设置。', '已存 Borg 密码无效。')):
        print(existing.stdout, end='', flush=True)
        return existing.returncode

    print('Enter the password for this backup drive.', flush=True)
    print('This is separate from your Linux login password.', flush=True)
    print('Press Enter to cancel.', flush=True)
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        try:
            secret = getpass.getpass('Backup password: ')
        except (EOFError, KeyboardInterrupt):
            secret = ''
        except getpass.GetPassWarning:
            raise ValueError('A terminal with hidden input is required.') from None
    if not secret:
        print('Backup setup cancelled.', flush=True)
        return 2
    if '\n' in secret or '\r' in secret:
        raise ValueError('Enter the backup password on one line.')
    return subprocess.run([str(BACKUP), 'enroll'], input=secret + '\n', text=True,
                          env=environment).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--display', choices=('auto', 'plain', 'rich'), default='auto',
                        help='terminal display style (default: auto)')
    internal = parser.add_mutually_exclusive_group()
    internal.add_argument('--browse', action='store_true',
                          help='view extension status in any interactive terminal')
    internal.add_argument('--status-json', action='store_true',
                          help='write versioned extension status as JSON without prompts')
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
    if args.status_json:
        return status_json()
    rich = rich_display(args.display)
    if args.browse:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise ValueError('Use an interactive terminal for --browse, or use --status-json.')
        extensions(rich=rich, read_only=True)
        return 0
    if not local_console():
        raise ValueError(
            'To open the management menu:\n'
            '1. Press Ctrl+Alt+F3 to open the Linux console.\n'
            '2. Sign in with your Linux username and password.\n'
            '3. Type system-extension-manager-tui and press Enter.\n'
            'To return to the desktop, try Ctrl+Alt+F1, F2, or F7.\n'
            'To view status here, run system-extension-manager-tui --browse.'
        )
    if os.geteuid() == 0:
        raise ValueError('Start the TUI without sudo. It requests authorization when needed.')
    choices = [
        ('View, install or remove extensions', lambda: extensions(rich=rich)),
        ('Update installed extensions', update_extensions),
        ('Review system security updates', security_updates),
        ('Back up or check your files (HomeBackUp)', lambda: homebackup(rich=rich)),
    ]
    while operation := choose('System Extension Manager', choices, back='Exit', rich=rich):
        try:
            operation()
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            print(f'Error: {exc}', file=sys.stderr)
            print('You can choose another task or exit.')
    return 0


# With -I the installed entry must explicitly load its sibling modules.
# The packaged launcher uses the fixed root-owned path above.
if Path(__file__).resolve() == ENTRY:
    try:
        for name in ('tui.py', 'lifecycle.py', 'execution.py', 'extensions.json'):
            trusted_file(INSTALLED / name)
    except (OSError, ValueError) as exc:
        sys.exit(f'Error: {exc}')
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
