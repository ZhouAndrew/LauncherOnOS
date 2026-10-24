import os
from concurrent.futures import ThreadPoolExecutor
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


    def test_invalid_id_cannot_delete_another_tool(self):
        self.assertEqual(self.cli('install', str(self.script)).returncode, 0)
        self.assertNotEqual(self.cli('uninstall', 'hello!!!').returncode, 0)
        self.assertTrue((self.root / 'app/tools/hello.sh').exists())

    def test_broken_export_does_not_publish_partial_archive(self):
        self.assertEqual(self.cli('install', str(self.script)).returncode, 0)
        (self.root / 'app/tools/hello.sh').write_text('modified')
        archive = self.root / 'partial.tar.gz'
        self.assertNotEqual(self.cli('export', 'all', str(archive)).returncode, 0)
        self.assertFalse(archive.exists())
        self.assertEqual(list(self.root.glob('.launcheronos-*')), [])

    def test_export_does_not_replace_existing_destination(self):
        self.assertEqual(self.cli('install', str(self.script)).returncode, 0)
        archive = self.root / 'existing.tar.gz'
        archive.write_text('keep me')
        self.assertNotEqual(self.cli('export', 'all', str(archive)).returncode, 0)
        self.assertEqual(archive.read_text(), 'keep me')

    def test_register_symlink_while_install_rejects_it(self):
        link = self.root / 'shortcut.sh'
        link.symlink_to(self.script)
        self.assertEqual(self.cli('register', str(link)).returncode, 0)
        self.assertIn('shortcut', self.cli('list').stdout)
        self.assertNotEqual(self.cli('install', str(link)).returncode, 0)
        self.assertEqual(self.cli('uninstall', 'shortcut').returncode, 0)
        self.assertTrue(link.is_symlink())
        self.assertTrue(self.script.exists())

    def test_executable_python_suffix_respects_shebang(self):
        script = self.root / 'not_python.py'
        script.write_text('#!/bin/sh\necho shebang-used\n')
        script.chmod(0o700)
        self.assertEqual(self.cli('install', str(script)).returncode, 0)
        run = self.cli('run', 'not_python')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('shebang-used', run.stdout)

    def test_changed_managed_tool_refuses_to_run(self):
        self.assertEqual(self.cli('install', str(self.script)).returncode, 0)
        (self.root / 'app/tools/hello.sh').write_text('changed')
        self.assertNotEqual(self.cli('run', 'hello').returncode, 0)

    def test_registry_is_not_world_readable(self):
        self.assertEqual(self.cli('install', str(self.script)).returncode, 0)
        registry = self.root / 'app/registry.json'
        self.assertEqual(registry.stat().st_mode & 0o077, 0)

    def test_non_ascii_filename_gets_safe_tool_id(self):
        other = self.root / '工具.sh'
        other.write_text('#!/bin/sh\necho ok\n')
        result = self.cli('install', str(other))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.strip().startswith('tool-'))

    def test_parallel_installs_keep_all_entries(self):
        scripts = []
        for i in range(8):
            file = self.root / f'parallel{i}.sh'
            file.write_text('#!/bin/sh\nexit 0\n')
            scripts.append(file)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda file: self.cli('install', str(file)), scripts))
        self.assertTrue(all(result.returncode == 0 for result in results),
                        [result.stderr for result in results])
        listing = self.cli('list').stdout
        self.assertEqual(len(listing.strip().splitlines()), 8)

    def test_duplicate_export_not_overwritten(self):
        self.assertEqual(self.cli('install', str(self.script)).returncode, 0)
        archive = self.root / 'backup.tar.gz'
        self.assertEqual(self.cli('export', 'all', str(archive)).returncode, 0)
        original = archive.read_bytes()
        self.assertNotEqual(self.cli('export', 'all', str(archive)).returncode, 0)
        self.assertEqual(archive.read_bytes(), original)


    def test_console_accepts_commands_instead_of_numbered_menu(self):
        result = subprocess.run(
            [sys.executable, str(SRC), 'menu'],
            env=self.env, text=True, input='help\nlist\nexit\n',
            capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('launcheronos>', result.stdout)
        self.assertIn('manual FILE.md', result.stdout)

    def test_manual_delegates_rendering_to_existing_glow(self):
        manual = self.root / 'guide.md'
        manual.write_text('# Guide\n')
        glow = self.root / 'glow'
        glow.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
        glow.chmod(0o755)
        env = dict(self.env, PATH=str(self.root))
        result = subprocess.run(
            [sys.executable, str(SRC), 'manual', str(manual)],
            env=env, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ['-p', str(manual)])

if __name__ == '__main__':
    unittest.main()
