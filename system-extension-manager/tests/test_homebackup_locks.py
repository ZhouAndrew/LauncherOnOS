"""HomeBackUp locking security regressions; never runs real backups."""
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'sources/homebackup/safe_lock.py'
spec = importlib.util.spec_from_file_location('homebackup_safe_lock', SOURCE)
safe_lock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(safe_lock)


class SafeLockTests(unittest.TestCase):
    def test_source_uses_no_follow_and_never_truncates(self):
        content = SOURCE.read_text()
        self.assertIn('os.O_NOFOLLOW', content)
        self.assertIn('stat.S_ISREG', content)
        self.assertIn('meta.st_uid != 0', content)
        self.assertNotIn('os.O_TRUNC', content)

    def test_symlink_lock_target_is_not_truncated(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'lock'
            target = Path(temp) / 'unrelated-root-data'
            target.write_bytes(b'contents survive')
            path.symlink_to(target)
            real_fstat = os.fstat
            def fake_fstat(fd):
                stat_data = real_fstat(fd)
                return SimpleNamespace(st_uid=0, st_mode=stat_data.st_mode,
                                       st_nlink=stat_data.st_nlink)
            with patch.dict(safe_lock.LOCKS, {8: str(path)}), \
                 patch.object(os, 'geteuid', return_value=0), \
                 patch.object(os, 'fstat', side_effect=fake_fstat):
                with self.assertRaises(OSError):
                    safe_lock.locked_exec(['8', str(path), '/usr/bin/bash', '/bin/true'])
            self.assertEqual(target.read_bytes(), b'contents survive')

    @unittest.skipIf(os.getuid() == 0, 'test requires a non-root directory')
    def test_untrusted_directory_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'lock'
            with patch.dict(safe_lock.LOCKS, {8: str(path)}), \
                 patch.object(os, 'geteuid', return_value=0):
                with self.assertRaisesRegex(PermissionError, 'directory'):
                    safe_lock.locked_exec(['8', str(path), '/usr/bin/bash', '/bin/true'])
            self.assertFalse(path.exists())

    def test_existing_multilink_file_refused_without_truncation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'lock'
            source = Path(temp) / 'file'
            source.write_bytes(b'preserve')
            os.link(source, path)
            real_fstat = os.fstat
            def fake_fstat(fd):
                info = real_fstat(fd)
                return SimpleNamespace(st_uid=0, st_mode=info.st_mode,
                                       st_nlink=info.st_nlink)
            with patch.dict(safe_lock.LOCKS, {8: str(path)}), \
                 patch.object(os, 'geteuid', return_value=0), \
                 patch.object(os, 'fstat', side_effect=fake_fstat):
                with self.assertRaisesRegex(PermissionError, 'owner, type or link'):
                    safe_lock.locked_exec(['8', str(path), '/usr/bin/bash', '/bin/true'])
            self.assertEqual(source.read_bytes(), b'preserve')


if __name__ == '__main__':
    unittest.main()
