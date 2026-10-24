import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

SRC = Path(__file__).resolve().parents[1] / 'launcheronos.py'


class LauncherTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = dict(os.environ, LAUNCHERONOS_HOME=str(self.root / 'app'))
        self.script = self.root / 'hello.sh'
        self.script.write_text('#!/usr/bin/env bash\n# Safe test script\necho hello\n')

    def cli(self, *args):
        return subprocess.run([sys.executable, str(SRC), *args], env=self.env,
                              text=True, capture_output=True)

    def test_managed_install_run_export_uninstall(self):
        self.assertEqual(self.cli('install', str(self.script)).returncode, 0)
        self.assertIn('hello', self.cli('run', 'hello').stdout)
        archive = self.root / 'backup.tar.gz'
        self.assertEqual(self.cli('export', 'all', str(archive)).returncode, 0)
        with tarfile.open(archive) as tf:
            self.assertIn('manifest.json', tf.getnames())
            self.assertIn('tools/hello.sh', tf.getnames())
        self.assertEqual(self.cli('uninstall', 'hello').returncode, 0)
        self.assertTrue(self.script.exists(), 'Original script must remain')

    def test_external_register_keeps_source(self):
        self.assertEqual(self.cli('register', str(self.script)).returncode, 0)
        self.assertEqual(self.cli('uninstall', 'hello').returncode, 0)
        self.assertTrue(self.script.exists())

    def test_changed_managed_copy_is_protected(self):
        self.assertEqual(self.cli('install', str(self.script)).returncode, 0)
        managed = self.root / 'app/tools/hello.sh'
        managed.write_text('changed')
        self.assertNotEqual(self.cli('uninstall', 'hello').returncode, 0)
        self.assertTrue(managed.exists())

    def test_duplicate_install_is_blocked(self):
        self.assertEqual(self.cli('install', str(self.script)).returncode, 0)
        self.assertNotEqual(self.cli('install', str(self.script)).returncode, 0)


if __name__ == '__main__':
    unittest.main()
