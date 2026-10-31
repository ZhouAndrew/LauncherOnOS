import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import system_plugins as plugins
import zip_trash


class ZipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.trashed = []

    def run_command(self, args, **kwargs):
        if args[:2] == ['/usr/bin/gio', 'trash']:
            self.trashed.append(Path(args[-1]))
            return subprocess.CompletedProcess(args, 0)
        return subprocess.run(args, **kwargs)

    def test_unicode_spaces_quotes_hidden_and_empty_dirs(self):
        folder = self.root / '中文 " $ folder'
        folder.mkdir()
        (folder / '.hidden').write_bytes(b'\x00secret')
        (folder / 'empty').mkdir()
        other = self.root / '-option.txt'
        other.write_text('second')
        target = zip_trash.archive_and_trash([folder, other], self.run_command)
        self.assertTrue(target.is_file())
        self.assertEqual(self.trashed, [folder, other])

    def test_read_access_time_change_does_not_block_snapshot(self):
        from types import SimpleNamespace
        path = self.root / 'file'
        path.write_text('original')
        real_lstat = Path.lstat
        counter = [0]
        def lstat(chosen):
            info = real_lstat(chosen)
            counter[0] += 1
            values = {name: getattr(info, name) for name in dir(info) if name.startswith('st_')}
            values['st_atime'] += counter[0]
            return SimpleNamespace(**values)
        with patch.object(Path, 'lstat', lstat):
            self.assertEqual(zip_trash.snapshot([path]), {'file': hashlib.sha256(b'original').hexdigest()})

    def test_never_overwrites(self):
        path = self.root / 'file'
        path.write_text('original')
        (self.root / 'file.zip').write_text('keep')
        target = zip_trash.archive_and_trash([path], self.run_command)
        self.assertEqual(target.name, 'file (1).zip')
        self.assertEqual((self.root / 'file.zip').read_text(), 'keep')

    def test_zip_failure_preserves_original(self):
        path = self.root / 'file'
        path.write_text('original')
        def fail(args, **kwargs):
            raise subprocess.CalledProcessError(1, args)
        with self.assertRaises(subprocess.CalledProcessError):
            zip_trash.archive_and_trash([path], fail)
        self.assertTrue(path.exists())
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_unzip_failure_never_trashes(self):
        path = self.root / 'file'
        path.write_text('original')
        def fail(args, **kwargs):
            if args[0] == '/usr/bin/unzip':
                raise subprocess.CalledProcessError(1, args)
            return self.run_command(args, **kwargs)
        with self.assertRaises(subprocess.CalledProcessError):
            zip_trash.archive_and_trash([path], fail)
        self.assertEqual(self.trashed, [])
        self.assertTrue(path.exists())

    def test_changed_source_never_trashes(self):
        path = self.root / 'file'
        path.write_text('original')
        def mutate(args, **kwargs):
            result = self.run_command(args, **kwargs)
            if args[0] == '/usr/bin/unzip':
                path.write_text('changed')
            return result
        with self.assertRaises(ValueError):
            zip_trash.archive_and_trash([path], mutate)
        self.assertEqual(self.trashed, [])

    def test_links_rejected(self):
        path = self.root / 'link'
        path.symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):
            zip_trash.archive_and_trash([path], self.run_command)
        self.assertEqual(self.trashed, [])

    def test_trash_failure_keeps_verified_zip(self):
        path = self.root / 'file'
        path.write_text('original')
        def fail(args, **kwargs):
            if args[0] == '/usr/bin/gio':
                raise subprocess.CalledProcessError(1, args)
            return self.run_command(args, **kwargs)
        with self.assertRaisesRegex(RuntimeError, 'ZIP saved'):
            zip_trash.archive_and_trash([path], fail)
        self.assertTrue((self.root / 'file.zip').is_file())
        self.assertTrue(path.exists())


class ManagerTests(unittest.TestCase):
    def test_real_bundled_deb_metadata_and_hash(self):
        args = plugins.command('zip-trash', True)
        self.assertIn('/usr/bin/apt-get', args)
        self.assertTrue(args[-1].endswith('.deb'))
        self.assertEqual(plugins.command('zip-trash', False)[-1], 'mint-toolbox-extension-zip-trash')

    def test_tampered_deb_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'bad.deb').write_text('bad')
            item = dict(plugins.plugin('zip-trash'), deb='bad.deb', sha256='0' * 64)
            with patch.object(plugins, 'ROOT', root), patch.object(plugins, 'plugin', return_value=item):
                with self.assertRaisesRegex(ValueError, 'checksum verification failed'):
                    plugins.command('zip-trash', True)

    def test_success_requires_readback(self):
        with patch.object(plugins, 'command', return_value=['/usr/bin/apt-get', 'install', 'test']), \
             patch.object(plugins, 'package_status', return_value=('absent', None)), \
             patch.object(plugins.OperationLog, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')):
            with self.assertRaisesRegex(RuntimeError, 'readback'):
                plugins.change('zip-trash', True)
            self.assertIsNone(plugins.change('zip-trash', False))

    def test_incomplete_install_is_not_disabled(self):
        with patch.object(plugins, 'command', return_value=['/usr/bin/apt-get', 'install', 'test']), \
             patch.object(plugins, 'package_status', return_value=('install ok unpacked', '0.4.0')), \
             patch.object(plugins.OperationLog, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')):
            self.assertIn('Incomplete', plugins.state_text('test'))
            with self.assertRaises(RuntimeError):
                plugins.change('zip-trash', False)

    @unittest.skipUnless(Path('/usr/bin/gio').exists(), 'GIO is unavailable')
    def test_real_trash_roundtrip(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / 'data'
            data.mkdir()
            source = root / 'original.txt'
            source.write_text('recoverable')
            with patch.dict(os.environ, {'XDG_DATA_HOME': str(data)}):
                archive = zip_trash.archive_and_trash([source])
            self.assertFalse(source.exists())
            self.assertTrue(archive.exists())
            trashed = list((data / 'Trash/files').iterdir())
            self.assertEqual(len(trashed), 1)
            self.assertEqual(trashed[0].read_text(), 'recoverable')

    def test_cancelled_install_is_failure(self):
        with patch.object(plugins, 'command', return_value=['/usr/bin/apt-get', 'install', 'test']), \
             patch.object(plugins, 'package_status', return_value=('absent', None)), \
             patch.object(plugins.OperationLog, 'run', return_value=subprocess.CompletedProcess([], 126, '', 'cancelled')):
            with self.assertRaises(RuntimeError):
                plugins.change('zip-trash', True)


if __name__ == '__main__':
    unittest.main()
