"""Root-owned APT staging tests, using subprocess fakes (never runs APT)."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import lifecycle


class PrivilegedPackageTests(unittest.TestCase):
    def run_root_code(self, source, expected, run, metadata):
        fake_argv = ['-c', expected, 'test-package', '1.0', str(source)]
        with patch.object(sys, 'argv', fake_argv), \
             patch.object(os, 'geteuid', return_value=0), \
             patch.object(subprocess, 'check_output', side_effect=[
                 'Package: test-package\nVersion: 1.0\nArchitecture: all\n', 'amd64\n'
             ]) as check_output, \
             patch.object(subprocess, 'run', side_effect=run):
            exec(compile(lifecycle.SECURE_INSTALL_CODE, '<verified-root-helper>', 'exec'),
                 {'__name__': '__main__'})
            return check_output

    def test_install_uses_only_root_owned_staged_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            original = Path(temp) / 'source.deb'
            original.write_bytes(b'known approved test content')
            seen = []
            def run(args, **kwargs):
                if '--simulate' in args:
                    return subprocess.CompletedProcess(args, 0, 'Inst test-package [0] (1.0)\n', '')
                staged = Path(args[-1])
                self.assertNotEqual(staged, original)
                self.assertEqual(staged.read_bytes(), original.read_bytes())
                self.assertEqual(staged.stat().st_uid, os.getuid())
                self.assertFalse(staged.stat().st_mode & 0o022)
                seen.append(tuple(args))
                return subprocess.CompletedProcess(args, 0, '', '')
            self.run_root_code(original, hashlib.sha256(original.read_bytes()).hexdigest(), run, None)
            self.assertEqual(len(seen), 1)

    def test_changed_package_rejected_before_any_apt(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source.deb'
            expected = hashlib.sha256(b'approved content').hexdigest()
            source.write_bytes(b'attacker changed content after approval')
            with patch.object(subprocess, 'run', side_effect=AssertionError('APT MUST NOT run')):
                with self.assertRaises(SystemExit) as outcome:
                    self.run_root_code(source, expected, lambda *args, **kw: None, None)
            self.assertEqual(outcome.exception.code, 1)

    def test_symlink_package_rejected_without_truncating_target(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'target'
            target.write_bytes(b'unchanged')
            link = Path(temp) / 'untrusted.deb'
            link.symlink_to(target)
            with self.assertRaises(SystemExit) as outcome:
                self.run_root_code(link, hashlib.sha256(b'unchanged').hexdigest(),
                                   lambda *args, **kw: None, None)
            self.assertEqual(outcome.exception.code, 1)
            self.assertEqual(target.read_bytes(), b'unchanged')

    def test_real_install_command_does_not_pass_user_deb_to_apt(self):
        args = lifecycle.command('link-provider', True)
        self.assertIn('/usr/bin/python3', args)
        self.assertIn('-I', args)
        self.assertIn('O_NOFOLLOW', args[args.index('-c')+1])
        self.assertTrue(args[-1].endswith('.deb'))
        self.assertNotIn('/usr/bin/apt-get', args)


if __name__ == '__main__':
    unittest.main()
