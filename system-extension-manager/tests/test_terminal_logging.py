"""Terminal launch regression tests. Never run the real updater or apt."""
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import lifecycle


class PortableTerminalLoggingTests(unittest.TestCase):
    def test_launch_uses_transcript_and_retains_interactive_terminal(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {'XDG_STATE_HOME': temp}):
                with patch.object(lifecycle.shutil, 'which', side_effect=lambda name: '/usr/bin/x-terminal-emulator' if name == 'x-terminal-emulator' else None):
                    args = lifecycle.terminal_command(Path('/tmp/test folder/updater.py'))
            self.assertEqual(args[:4], ['/usr/bin/x-terminal-emulator', '-e', '/bin/bash', '-c'])
            self.assertEqual(args[-3:], ['/usr/bin/python3', '/tmp/test folder/updater.py', '--interactive'])
            self.assertIn('Press Enter to close this terminal', args[4])
            self.assertIn('PIPESTATUS', args[4])
            transcript = Path(args[-4])
            self.assertTrue(transcript.is_file())
            self.assertEqual(stat.S_IMODE(transcript.stat().st_mode), 0o600)
            self.assertTrue(transcript.is_relative_to(Path(temp) / 'system-extension-manager/logs'))

    def test_both_outputs_and_actual_nonzero_exit_are_saved(self):
        with tempfile.TemporaryDirectory() as temp:
            transcript = Path(temp) / 'update.log'
            transcript.touch(mode=0o600)
            child = [sys.executable, '-c',
                     'import sys; print("normal output", flush=True); print("traceback on stderr", file=sys.stderr, flush=True); sys.exit(27)']
            cmd = ['/bin/bash', '-c', lifecycle.PORTABLE_TERMINAL_WRAPPER, 'portable-security-updates', str(transcript), *child]
            result = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 27, result.stderr + result.stdout)
            log = transcript.read_text(encoding='utf-8')
            self.assertIn('normal output', log)
            self.assertIn('traceback on stderr', log)
            self.assertIn('Exit code: 27', log)

    def test_zero_exit_is_logged_without_calling_apt(self):
        with tempfile.TemporaryDirectory() as temp:
            transcript = Path(temp) / 'update.log'
            transcript.touch(mode=0o600)
            cmd = ['/bin/bash', '-c', lifecycle.PORTABLE_TERMINAL_WRAPPER,
                   'portable-security-updates', str(transcript), '/usr/bin/true']
            result = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Exit code: 0', transcript.read_text(encoding='utf-8'))

    def test_manager_captures_terminal_emulator_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {'XDG_STATE_HOME': temp}), \
                 patch.object(lifecycle.shutil, 'which', side_effect=lambda name: '/usr/bin/x-terminal-emulator' if name == 'x-terminal-emulator' else None), \
                 patch.object(lifecycle.subprocess, 'Popen') as popen:
                from unittest.mock import Mock
                log = Mock()
                lifecycle.open_extension('security-updates', log)
                popen.assert_called_once()
                self.assertEqual(popen.call_args.kwargs['stderr'], subprocess.STDOUT)
                self.assertNotEqual(popen.call_args.kwargs['stdout'], subprocess.DEVNULL)
                output_log = popen.call_args.kwargs['stdout']
                self.assertEqual(stat.S_IMODE(os.fstat(output_log.fileno()).st_mode), 0o600) if not output_log.closed else None
                self.assertTrue(any('Terminal stdout/stderr and exit status:' in call.args[0]
                                    for call in log.stage.call_args_list))


if __name__ == '__main__':
    unittest.main()
