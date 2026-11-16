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
