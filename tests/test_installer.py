import os
from pathlib import Path
import subprocess
import tempfile
import unittest

INSTALLER = Path(__file__).resolve().parents[1] / 'install.sh'


class InstallerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.binary = self.home / '.local/bin/launcheronos'
        self.env = dict(os.environ, HOME=str(self.home))

    def run_install(self, *arguments):
        return subprocess.run(['bash', str(INSTALLER), *arguments],
                              env=self.env, capture_output=True, text=True)

    def test_initial_install_and_explicit_upgrade(self):
        self.assertEqual(self.run_install().returncode, 0)
        self.assertTrue(self.binary.is_file())
        self.assertNotEqual(self.run_install().returncode, 0)
        self.assertEqual(self.run_install('--upgrade').returncode, 0)
        backups = list(self.binary.parent.glob('launcheronos.backup.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), self.binary.read_bytes())

    def test_upgrade_never_replaces_foreign_file(self):
        self.binary.parent.mkdir(parents=True)
        self.binary.write_text('I am not LauncherOnOS')
        self.assertNotEqual(self.run_install('--upgrade').returncode, 0)
        self.assertEqual(self.binary.read_text(), 'I am not LauncherOnOS')


if __name__ == '__main__':
    unittest.main()
