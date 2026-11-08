"""Security regressions for the optional manager .deb build (no installation)."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build as manager_build


class ManagerPackageSafetyTests(unittest.TestCase):
    def test_rejects_path_traversal_and_symlinks(self):
        with self.assertRaisesRegex(ValueError, 'escapes'):
            manager_build.checked_source('../outside')
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            link = ROOT / Path(temporary).name / 'source-link'
            link.symlink_to(ROOT / 'manager.py')
            with self.assertRaisesRegex(ValueError, 'linked'):
                manager_build.checked_source(str(link.relative_to(ROOT)))

    def test_untracked_private_file_is_not_shipped(self):
        # The build must not archive unknown checkout files or test-created
        # credentials, even though they live inside the source directory.
        with tempfile.TemporaryDirectory() as temporary:
            marker = ROOT / '.audit-do-not-ship-test-secret'
            if marker.exists():
                self.skipTest('Refusing to overwrite an existing private marker')
            try:
                marker.write_text('fake credential for regression only\n')
                output = manager_build.build_manager(Path(temporary))
                unpacked = Path(temporary) / 'unpacked'
                subprocess.run(['dpkg-deb', '-x', str(output), str(unpacked)],
                               check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                installed = unpacked / 'usr/share/system-extension-manager'
                self.assertTrue((installed / 'manager.py').is_file())
                self.assertTrue((installed / 'sources/security-updates/security_updates.py').is_file())
                self.assertTrue((installed / 'packages/mint-link-provider-extension_0.2.1_all.deb').is_file())
                self.assertFalse((installed / marker.name).exists())
                self.assertFalse((installed / 'tests').exists())
            finally:
                marker.unlink(missing_ok=True)

    def test_refuses_modified_pinned_source_before_packaging(self):
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = Path(temporary) / 'checkout'
            shutil.copytree(ROOT, snapshot, ignore=shutil.ignore_patterns(
                'dist', '__pycache__', 'tests', 'build-mint-homebackup-extension'))
            pinned = snapshot / 'sources/security-updates/security_updates.py'
            pinned.write_bytes(pinned.read_bytes() + b'\n# changed after catalog creation\n')
            with patch.object(manager_build, 'ROOT', snapshot):
                with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                    manager_build.build_manager(Path(temporary) / 'out')


if __name__ == '__main__':
    unittest.main()
