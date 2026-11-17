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
                patch('sys.stderr') as error, patch('sys.stdout') as output:
            self.assertEqual(tui.main(), 0)
        error.write.assert_any_call('Error: APT is busy')
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
                    os.write(master, b'1\n\n')
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
                    read_until(b'Enter a number')
                    os.write(master, b'm\n')
                    read_until(b'Up/Down')
                    os.write(master, b'\x1bOB\n')
                    output = read_until(b'Enter a number')
                    self.assertIn(b'Nemo verified', output)
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
                         'HomeBackUp - Installed: 0.1.3 (Update available)')
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
