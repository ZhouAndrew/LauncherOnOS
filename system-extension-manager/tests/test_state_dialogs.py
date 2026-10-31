import subprocess
import unittest
from unittest.mock import Mock, patch
import lifecycle
import native_dialogs


class StateTests(unittest.TestCase):
    def test_legacy_installed_version_is_enabled_and_updatable(self):
        with patch.object(lifecycle, 'package_status', return_value=('install ok installed', '0.3.0')):
            state = lifecycle.extension_state(lifecycle.plugin('zip-trash'))
        self.assertTrue(state['remove'])
        self.assertTrue(state['update'])
        self.assertFalse(state['install'])
        self.assertIn('0.3.0', state['state'])

    def test_duplicate_actions_never_invoke_apt(self):
        for enabled, status in [(True, ('install ok installed', '0.3.0')), (False, ('absent', None))]:
            log = Mock()
            with patch.object(lifecycle, 'package_status', return_value=status), patch.object(lifecycle, 'command') as command:
                lifecycle.change('zip-trash', enabled, log)
                command.assert_not_called()
                log.run.assert_not_called()

    def test_unknown_state_blocks_all_actions(self):
        with patch.object(lifecycle, 'package_status', side_effect=RuntimeError('database error')):
            state = lifecycle.extension_state(lifecycle.plugin('zip-trash'))
        self.assertTrue(state['state'].startswith('Unknown'))
        self.assertFalse(any(state[key] for key in ['install', 'remove', 'update']))

    def test_native_cancel_does_not_open_fallback(self):
        with patch.object(native_dialogs.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '[]', '')):
            self.assertEqual(native_dialogs.askdirectory(), '')

    def test_native_paths_preserve_unicode_spaces_and_newlines(self):
        import json
        paths = ['/tmp/a b.pdf', '/tmp/中文\nname.pdf']
        with patch.object(native_dialogs.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, json.dumps(paths), '')):
            self.assertEqual(native_dialogs.askopenfilenames(), tuple(paths))
