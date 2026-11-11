"""First-run safety note is acknowledged after dismissal and never repeated."""
import tempfile
import unittest
from unittest.mock import Mock, patch
import lifecycle


class SafetyNoticeTests(unittest.TestCase):
    def test_acknowledge_once(self):
        with tempfile.TemporaryDirectory() as home, patch.dict('os.environ', {'XDG_STATE_HOME': home}):
            dialog = Mock()
            self.assertTrue(lifecycle.show_one_time_safety_notice(None, showinfo=dialog))
            self.assertFalse(lifecycle.show_one_time_safety_notice(None, showinfo=dialog))
            dialog.assert_called_once()
            self.assertTrue(lifecycle.safety_notice_path().is_file())
            self.assertNotIn('Mint Toolbox', lifecycle.SAFETY_NOTICE)

    def test_failed_dialog_does_not_acknowledge(self):
        with tempfile.TemporaryDirectory() as home, patch.dict('os.environ', {'XDG_STATE_HOME': home}):
            with self.assertRaises(RuntimeError):
                lifecycle.show_one_time_safety_notice(None, showinfo=Mock(side_effect=RuntimeError('dialog failed')))
            self.assertFalse(lifecycle.safety_notice_path().exists())
