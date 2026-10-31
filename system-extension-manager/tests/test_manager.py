import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import lifecycle
import manager


class CatalogTests(unittest.TestCase):
    def test_two_real_extensions_have_valid_bundled_debs_and_pinned_sources(self):
        import hashlib
        rows = lifecycle.plugins()
        self.assertEqual({row['id'] for row in rows}, {'zip-trash', 'anki-time-travel'})
        for row in rows:
            deb = lifecycle.bundled_deb(row)
            info = lifecycle.verify_deb(row, deb)
            self.assertEqual(info['Package'], row['package'])
            for name, sha in row['source']['files'].items():
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), sha)
        self.assertEqual(lifecycle.plugin('anki-time-travel')['launch'], ['/usr/bin/anki-time-travel', '--gui'])

    def test_anki_enabled_by_its_actual_package_state(self):
        result = subprocess.CompletedProcess([], 0, 'install ok installed\n0.1.2', '')
        with patch.object(lifecycle.subprocess, 'run', return_value=result):
            self.assertEqual(lifecycle.state_text('anki-time-travel'), 'Enabled: 0.1.2')

    def test_install_and_remove_only_selected_extension_with_readback(self):
        args = lifecycle.command('anki-time-travel', True)
        self.assertTrue(args[-1].endswith('anki-time-travel_0.1.3_all.deb'))
        log = Mock()
        log.run.return_value = subprocess.CompletedProcess([], 0, '', '')
        with patch.object(lifecycle, 'command', return_value=args), \
             patch.object(lifecycle, 'package_status', return_value=('install ok installed', '0.1.3')):
            self.assertEqual(lifecycle.change('anki-time-travel', True, log), '0.1.3')
        self.assertEqual(log.run.call_count, 2)
        removal = lifecycle.command('anki-time-travel', False)
        self.assertEqual(removal[-1], 'anki-time-travel')
        with patch.object(lifecycle, 'command', return_value=removal), \
             patch.object(lifecycle, 'package_status', return_value=('absent', None)):
            lifecycle.change('anki-time-travel', False, log)

    def test_failed_readback_is_not_success(self):
        log = Mock()
        log.run.return_value = subprocess.CompletedProcess([], 0, '', '')
        with patch.object(lifecycle, 'command', return_value=['/usr/bin/apt-get', 'install', 'test']), \
             patch.object(lifecycle, 'package_status', return_value=('absent', None)):
            with self.assertRaisesRegex(RuntimeError, 'readback'):
                lifecycle.change('anki-time-travel', True, log)

    def test_open_requires_an_installed_extension(self):
        with patch.object(lifecycle, 'installed_version', return_value=None):
            with self.assertRaisesRegex(ValueError, 'Enable / Install'):
                lifecycle.launch_command('anki-time-travel')
        with patch.object(lifecycle, 'installed_version', return_value='0.1.2'), \
             patch.object(Path, 'is_file', return_value=True), patch.object(lifecycle.os, 'access', return_value=True):
            self.assertEqual(lifecycle.launch_command('anki-time-travel'), ['/usr/bin/anki-time-travel', '--gui'])

    def test_cli_install_failure_returns_an_error_without_a_traceback(self):
        with patch.object(lifecycle, 'change', side_effect=subprocess.CalledProcessError(100, ['apt-get'])):
            self.assertEqual(manager.main(['--enable', 'anki-time-travel']), 1)

    def test_cli_lists_both_extensions(self):
        result = subprocess.run([sys.executable, str(ROOT / 'manager.py'), '--list'],
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('anki-time-travel\tAnki Time Travel', result.stdout)
        self.assertIn('zip-trash\tZIP and Trash', result.stdout)

    def test_source_runs_without_installing_or_packaging_manager(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / 'source'
            shutil.copytree(ROOT, app, ignore=shutil.ignore_patterns('dist', '__pycache__'))
            for command in (['bash', str(app / 'run.sh'), '--list'],
                            [sys.executable, str(app / 'build.py')]):
                result = subprocess.run(command, cwd=tmp, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((app / 'dist').exists())
            self.assertFalse(list(app.glob('system-extension-manager*.deb')))
            self.assertEqual(len(list((app / 'packages').glob('*.deb'))), 2)

    def test_manager_packaging_requires_explicit_cli_request(self):
        with patch.object(lifecycle, 'build_manager_package') as build:
            self.assertEqual(manager.main(['--list']), 0)
            build.assert_not_called()
            self.assertEqual(manager.main(['--build-package', '--output-dir', '/tmp/optional-package']), 0)
            build.assert_called_once_with(Path('/tmp/optional-package'))

    def test_both_source_recipes_build_as_regular_user(self):
        code = '''import lifecycle
from execution import OperationLog
import os
assert os.geteuid() != 0
log = OperationLog('source recipe verification', lambda line: None)
for row in lifecycle.plugins():
    artifact = lifecycle.build_source(row, log)
    assert artifact.is_file()
log.close()
print('BOTH_RECIPES_OK')
'''
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.chmod(0o777)
            # Use a readable staged source snapshot independent of host workspace permissions.
            import shutil
            for name in ['lifecycle.py', 'execution.py', 'extensions.json', 'sources']:
                src, dst = ROOT / name, root / name
                if src.is_dir():
                    shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__'))
                else:
                    shutil.copyfile(src, dst)
            opts = dict(user=65534, group=65534, extra_groups=[]) if os.geteuid() == 0 else {}
            try:
                result = subprocess.run([sys.executable, '-c', code], cwd=root,
                    env={**os.environ, 'XDG_STATE_HOME': str(root / 'state'), 'XDG_CACHE_HOME': str(root / 'cache')},
                    capture_output=True, text=True, timeout=30, **opts)
            except PermissionError:
                if os.geteuid() != 0:
                    raise
                self.skipTest('Host cannot switch from root; CI runs as a regular user')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('BOTH_RECIPES_OK', result.stdout)


@unittest.skipUnless(os.environ.get('DISPLAY'), 'requires a graphical environment')
class ManagerGuiTests(unittest.TestCase):
    def test_real_anki_row_has_install_remove_open_and_live_launch_log(self):
        import tkinter as tk
        from tkinter import ttk
        parent = tk.Tk()
        parent.withdraw()
        errors = []
        with patch.object(lifecycle, 'state_text', side_effect=lambda package: 'Enabled: 0.1.2' if package == 'anki-time-travel' else 'Disabled'), \
             patch.object(lifecycle, 'launch_command', return_value=['/bin/true']):
            window = lifecycle.show_gui(parent)
            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)
            tree = next(w for w in descendants(window) if isinstance(w, ttk.Treeview))
            self.assertEqual(set(tree.get_children()), {'zip-trash', 'anki-time-travel'})
            tree.selection_set('anki-time-travel')
            tree.event_generate('<<TreeviewSelect>>')
            parent.update()
            buttons = {w.cget('text'): w for w in descendants(window) if isinstance(w, ttk.Button)}
            for text in ['Enable / Install', 'Disable / Uninstall', 'Build from source...', 'Open', 'Build Package...']:
                self.assertIn(text, buttons)
            with patch('tkinter.filedialog.askdirectory', return_value=''), patch.object(lifecycle, 'build_manager_package') as build:
                buttons['Build Package...'].invoke()
                build.assert_not_called()
            self.assertEqual(str(buttons['Open'].cget('state')), 'normal')
            buttons['Open'].invoke()
            def check():
                try:
                    texts = [w.get('1.0', 'end') for w in descendants(window) if isinstance(w, tk.Text)]
                    self.assertTrue(any('/bin/true' in text and 'Exit code: 0' in text for text in texts))
                    self.assertEqual(window.title(), 'System Extension Manager')
                except Exception as exc:
                    errors.append(exc)
                finally:
                    parent.quit()
            parent.after(800, check)
            parent.mainloop()
            window.destroy()
        parent.destroy()
        if errors:
            raise errors[0]


if __name__ == '__main__':
    unittest.main()
