import os
from pathlib import Path
import pty
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import lifecycle
import tui


class ConsoleTests(unittest.TestCase):
    def test_redirected_input_cannot_start_even_with_console_environment(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / 'tui.py')], input='1\n', text=True,
            capture_output=True, env={**os.environ, 'XDG_SESSION_TYPE': 'tty'},
            timeout=5,
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn('Ctrl+Alt+F3', completed.stderr)

    def test_real_pseudoterminal_cannot_start(self):
        master, slave = pty.openpty()
        try:
            completed = subprocess.run(
                [sys.executable, str(ROOT / 'tui.py')],
                stdin=slave, stdout=slave, stderr=slave, timeout=5,
            )
            self.assertEqual(completed.returncode, 1)
            self.assertIn(b'Ctrl+Alt+F3', os.read(master, 4096))
        finally:
            os.close(master)
            os.close(slave)

    def test_failed_task_returns_to_menu_and_enter_exits(self):
        with patch.object(tui, 'local_console', return_value=True), \
                patch.object(tui.os, 'geteuid', return_value=1000), \
                patch.object(sys, 'argv', ['tui.py']), \
                patch('builtins.input', side_effect=['3', '']), \
                patch.object(tui, 'security_updates', side_effect=ValueError('APT is busy')), \
                patch('sys.stdout') as output:
            self.assertEqual(tui.main(), 0)
        output.write.assert_any_call('Error: APT is busy')
        self.assertEqual(output.write.call_args_list.count(
            unittest.mock.call('\nSystem Extension Manager')), 2)

    def test_extension_update_defaults_to_cancel(self):
        plan = [({'name': 'ZIP and Trash', 'version': '2'}, '1')]
        with patch.object(lifecycle, 'update_all_plan', return_value=plan), \
                patch.object(tui, 'require_installed'), \
                patch.object(lifecycle, 'update_all') as update, \
                patch('builtins.input', return_value=''), patch('sys.stdout'):
            tui.update_extensions()
        update.assert_not_called()

    def test_stale_approved_plan_does_not_apply_changes(self):
        with patch.object(lifecycle.os, 'geteuid', return_value=1000), \
                patch.object(lifecycle, 'update_all_plan', return_value=[]), \
                patch.object(lifecycle, 'change') as change:
            with self.assertRaisesRegex(ValueError, 'versions changed'):
                lifecycle.update_all(unittest.mock.Mock(), include_security=False,
                                     plan=[({'id': 'zip-trash'}, '1')])
        change.assert_not_called()

    def test_plain_and_rich_browse_on_real_pseudo_terminal(self):
        for term, mode, bold in (('dumb', 'rich', False),
                                 ('sem-unknown-terminal', 'rich', False),
                                 ('xterm', 'rich', True),
                                 ('xterm', 'plain', False)):
            with self.subTest(term=term, mode=mode):
                master, slave = pty.openpty()
                try:
                    os.write(master, b'1\n\n\n')
                    completed = subprocess.run(
                        [sys.executable, str(ROOT / 'tui.py'),
                         '--browse', '--display', mode],
                        stdin=slave, stdout=slave, stderr=slave, timeout=10,
                        env={**os.environ, 'TERM': term, 'COLUMNS': '40'},
                    )
                    self.assertEqual(completed.returncode, 0)
                    output = os.read(master, 8192)
                    self.assertIn(b'Extensions (view only)', output)
                    self.assertIn(b'ZIP and Trash', output)
                    self.assertNotIn(b'Uninstall', output)
                    self.assertEqual(b'\x1b[1m' in output, bold)
                finally:
                    os.close(master)
                    os.close(slave)

    def test_json_status_is_readable_without_a_terminal(self):
        import json

        completed = subprocess.run(
            [sys.executable, str(ROOT / 'tui.py'), '--status-json'],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report['schema_version'], 1)
        self.assertEqual({row['id'] for row in report['extensions']},
                         {'zip-trash', 'anki-time-travel', 'homebackup', 'link-provider'})

    def test_navigation_restores_numbered_output_on_real_terminal(self):
        import fcntl
        import select
        import struct
        import termios
        import time

        master, slave = pty.openpty()
        try:
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 10, 40, 0, 0))
            with subprocess.Popen(
                [sys.executable, str(ROOT / 'tui.py'), '--browse', '--display', 'rich'],
                stdin=slave, stdout=slave, stderr=slave,
                env={**os.environ, 'TERM': 'xterm'},
            ) as process:
                def read_until(fragment):
                    deadline = time.monotonic() + 5
                    observed = b''
                    while fragment not in observed:
                        if not select.select([master], [], [], max(0, deadline - time.monotonic()))[0]:
                            self.fail(f'Did not see {fragment!r} in {observed!r}')
                        observed += os.read(master, 4096)
                    return observed

                try:
                    read_until(b'Choice:')
                    os.write(master, b'm\n')
                    read_until(b'Up/Down')
                    os.write(master, b'\x1bOB\n')
                    output = read_until(b'Press Enter to return.')
                    self.assertIn(b'Nemo verified', output)
                    self.assertNotIn(b'Choice:', output)
                    os.write(master, b'\n')
                    read_until(b'Choice:')
                    os.write(master, b'\n')
                    self.assertEqual(process.wait(timeout=5), 0)
                finally:
                    if process.poll() is None:
                        process.kill()
        finally:
            os.close(master)
            os.close(slave)

    def test_browse_labels_package_installation_not_timer_state(self):
        item = {'name': 'HomeBackUp'}
        installed = {'state': 'Enabled: 0.1.3 (Update available)'}
        with patch.object(tui, 'extension_rows', return_value=[(item, installed)]), \
                patch.object(tui, 'choose', return_value=None) as choose:
            tui.extensions(read_only=True)
        self.assertEqual(choose.call_args.args[1][0][0],
                         'HomeBackUp: Installed: 0.1.3 (Update available)')
        self.assertEqual(tui.package_label({'state': 'Disabled'}), 'Not installed')

    def test_backup_result_stays_next_to_the_input_prompt(self):
        import contextlib
        import io

        scenarios = [
            ('yes', 0, '', 'Backup succeeded. The new archive was verified.'),
            ('yes', 1, '未挂载或 UUID 不符', 'Connect or mount the correct backup drive'),
            ('', None, '', 'Cancelled. No changes made.'),
        ]
        for answer, code, status_text, message in scenarios:
            with self.subTest(code=code):
                output = io.StringIO()
                responses = [
                    (subprocess.CompletedProcess([], code, ''), '/logs/backup.log'),
                    (subprocess.CompletedProcess([], 0, status_text), '/logs/status.log'),
                ]
                with patch.object(tui, 'require_installed'), patch.object(tui, 'trusted_file'), \
                        patch.object(lifecycle, 'installed_version', return_value='0.1.6'), \
                        patch('sys.stdin', io.StringIO(f'2\n{answer}\n\n')), \
                        patch.object(tui, 'backup_command', side_effect=responses) as backup, \
                        contextlib.redirect_stdout(output):
                    tui.homebackup()
                screen = output.getvalue()
                self.assertIn('may delete older', ' '.join(screen.split()))
                footer = screen.rsplit('0. Back', 1)[-1]
                self.assertIn(message, ' '.join(footer.split()))
                self.assertIn('Enter a number', footer)
                self.assertEqual(backup.call_count, {None: 0, 0: 1, 1: 2}[code])
                if code is not None:
                    self.assertIn('/logs/backup.log', footer)

    def test_multi_line_paste_cannot_confirm_menu_action(self):
        import select
        import time

        for answer, accepted in ((b'\n', False), (b'yes\n', True)):
            with self.subTest(accepted=accepted):
                master, slave = pty.openpty()
                try:
                    child = (
                        "import tui; menu = tui.choose('Menu', [('Demo', 'demo')]); "
                        "print('Approved:', tui.confirm('Apply demo?') if menu else False)"
                    )
                    with subprocess.Popen(
                        [sys.executable, '-c', child], cwd=ROOT,
                        stdin=slave, stdout=slave, stderr=slave,
                    ) as process:
                        def read_until(fragment):
                            end = time.monotonic() + 5
                            captured = b''
                            while fragment not in captured:
                                if not select.select([master], [], [], max(0, end - time.monotonic()))[0]:
                                    self.fail(f'Missing {fragment!r} in {captured!r}')
                                captured += os.read(master, 4096)
                            return captured

                        try:
                            read_until(b'Choice:')
                            os.write(master, b'1\nyes\n')
                            read_until(b'Your answer: ')
                            os.write(master, answer)
                            read_until(f'Approved: {accepted}'.encode())
                            self.assertEqual(process.wait(timeout=5), 0)
                        finally:
                            if process.poll() is None:
                                process.kill()
                finally:
                    os.close(master)
                    os.close(slave)

    def test_backup_status_shows_plain_language_beside_menu_prompt(self):
        import contextlib
        import io

        status = ('每月定时器安装状态：disabled\n每月定时器运行状态：inactive\n'
                  '备份磁盘挂载：未挂载或 UUID 不符\n')
        result = subprocess.CompletedProcess([], 0, status)
        output = io.StringIO()
        with patch.object(tui, 'require_installed'), patch.object(tui, 'trusted_file'), \
                patch.object(lifecycle, 'installed_version', return_value='0.1.6'), \
                patch('sys.stdin', io.StringIO('1\n\n')), \
                patch.object(tui, 'backup_command', return_value=(result, '/logs/status.log')), \
                contextlib.redirect_stdout(output):
            tui.homebackup()
        footer = ' '.join(output.getvalue().rsplit('0. Back', 1)[-1].split())
        self.assertIn('Backup drive: Connect or mount the backup drive.', footer)
        self.assertIn('Monthly backups: Off', footer)
        self.assertIn('Enter a number', footer)
        self.assertIn('Monthly backups: On', tui.backup_status_summary(
            '每月定时器安装状态：enabled\n每月定时器运行状态：active\n'))
        self.assertIn('Monthly backups: Could not verify', tui.backup_status_summary(''))

    def test_monthly_setup_asks_only_when_saved_password_cannot_be_used(self):
        import contextlib
        import io

        for code, message, answer, expected in (
            (0, '', 'fixture', 0),
            (1, '尚未保存 Borg 密码；请先执行设置。', 'fixture', 0),
            (1, '已存 Borg 密码无效。', '', 2),
            (1, 'HomeBackUp 未挂载。', 'fixture', 1),
        ):
            with self.subTest(message=message):
                first = subprocess.CompletedProcess([], code, message)
                enrolled = subprocess.CompletedProcess([], 0)
                with patch.object(tui.os, 'geteuid', return_value=0), \
                        patch.object(tui, 'trusted_file'), \
                        patch.object(tui.subprocess, 'run', side_effect=[first, enrolled]) as run, \
                        patch.object(tui.getpass, 'getpass', return_value=answer) as ask, \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(tui.enroll_backup(), expected)
                self.assertEqual(run.call_args_list[0].args[0][-1], 'use-existing')
                self.assertEqual(ask.call_count, int('Borg' in message))
                if run.call_count == 2:
                    self.assertEqual(run.call_args.args[0][-1], 'enroll')
                    self.assertEqual(run.call_args.kwargs['input'], 'fixture\n')

    def test_package_audit_distinguishes_clean_incomplete_and_unavailable(self):
        import contextlib
        import io

        for code, stdout, stderr, label in (
            (0, '', '', 'No incomplete packages found'),
            (0, 'Package is unpacked', '', 'Some packages need attention'),
            (1, '', 'Database unreadable', 'Could not confirm'),
        ):
            result = subprocess.CompletedProcess([], code, stdout, stderr)
            with patch.object(tui.subprocess, 'run', return_value=result) as run, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertIn(label, tui.package_audit())
            self.assertEqual(run.call_args.args[0], ['/usr/bin/dpkg', '--audit'])

    def test_read_only_backup_lists_need_no_confirmation(self):
        import contextlib
        import io

        for selection, action, message in (
            ('3', 'list', 'Saved backups are listed above.'),
            ('4', 'preview', 'No backups were deleted.'),
        ):
            with self.subTest(action=action):
                output = io.StringIO()
                reply = (subprocess.CompletedProcess([], 0, 'fixture'), '/logs/backup.log')
                with patch.object(tui, 'require_installed'), patch.object(tui, 'trusted_file'), \
                        patch.object(lifecycle, 'installed_version', return_value='0.1.6'), \
                        patch('sys.stdin', io.StringIO(selection + '\n\n')), \
                        patch.object(tui, 'confirm') as confirm, \
                        patch.object(tui, 'backup_command', return_value=reply) as command, \
                        contextlib.redirect_stdout(output):
                    tui.homebackup()
                confirm.assert_not_called()
                self.assertEqual(command.call_args.args[0], action)
                self.assertIn(message, output.getvalue())
                self.assertIn('/logs/backup.log', output.getvalue())

    def test_backup_failures_give_the_relevant_next_step(self):
        for message, next_step in (
            ('请先设置 Borg 仓库密码。', 'Choose Turn on monthly backups'),
            ('找不到原有 Borg 仓库；不会新建仓库。', 'correct drive'),
            ('旧 homebackup-monthly.timer 已启用', 'switching schedules'),
            ('解密验证失败，保持旧密码不变。', 'drive and backup password'),
        ):
            with self.subTest(message=message):
                self.assertIn(next_step, tui.backup_failure(message))

    def test_invalid_choice_guidance_stays_near_prompt(self):
        import contextlib
        import io

        output = io.StringIO()
        with patch('sys.stdin', io.StringIO('9\n1\n')), contextlib.redirect_stdout(output):
            self.assertEqual(tui.choose('Menu', [('View status', 'status')]), 'status')
        last_prompt = output.getvalue().rsplit('0. Back', 1)[-1]
        self.assertIn('That choice is unavailable.', last_prompt)
        self.assertIn('Press Enter alone for back.', last_prompt)

    def test_small_browse_menu_keeps_first_choice_visible_after_invalid_input(self):
        import contextlib
        import io

        output = io.StringIO()
        rows = [(dict(name=name), dict(state='Disabled')) for name in
                ('ZIP and Trash', 'Anki Time Travel', 'HomeBackUp', 'Link Provider')]
        with patch.object(tui.shutil, 'get_terminal_size', return_value=os.terminal_size((32, 10))), \
                patch.object(tui, 'extension_rows', return_value=rows), \
                patch('sys.stdin', io.StringIO('9\n\n')), contextlib.redirect_stdout(output):
            tui.extensions(read_only=True)
        for page in output.getvalue().split('Choice: ')[:-1]:
            self.assertIn('1. ZIP and Trash', '\n'.join((page + 'Choice: ').splitlines()[-10:]))

    def test_python_update_plan_and_json_agree(self):
        import contextlib
        import io
        import json

        output = io.StringIO()
        plan = [({'id': 'sample', 'version': '2'}, '1')]
        with patch.object(tui.lifecycle, 'update_all_plan', return_value=plan), \
                contextlib.redirect_stdout(output):
            expected = tui.extension_update_plan()
            self.assertEqual(tui.main(['--update-plan-json']), 0)
        self.assertEqual(json.loads(output.getvalue()), expected)
        self.assertEqual(expected['updates'][0]['available'], '2')

    def test_admin_task_requires_console_and_opens_selected_task(self):
        with patch.object(tui, 'local_console', return_value=False), \
                patch.object(tui, 'update_extensions', return_value=None) as update:
            with self.assertRaisesRegex(ValueError, 'Ctrl\\+Alt\\+F3'):
                tui.main(['--task', 'updates'])
            update.assert_not_called()
        with patch.object(tui, 'local_console', return_value=True), \
                patch.object(tui.os, 'geteuid', return_value=1000), \
                patch.object(tui, 'update_extensions', return_value=None) as update, \
                patch.object(tui, 'choose') as choose:
            self.assertEqual(tui.main(['--task', 'updates']), 0)
            update.assert_called_once()
            choose.assert_not_called()

    def test_no_updates_stays_visible_at_the_next_main_menu_prompt(self):
        import contextlib
        import io

        output = io.StringIO()
        with patch.object(tui, 'local_console', return_value=True), \
                patch.object(tui.os, 'geteuid', return_value=1000), \
                patch.object(tui.lifecycle, 'update_all_plan', return_value=[]), \
                patch('sys.stdin', io.StringIO('2\n\n')), \
                contextlib.redirect_stdout(output):
            self.assertEqual(tui.main(['--display', 'plain']), 0)
        footer = output.getvalue().rsplit('0. Exit', 1)[-1]
        self.assertIn('Installed extensions are up to date.', footer)
        self.assertIn('Choice:', footer)
