import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / 'mint-toolbox'))
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('anki_time_travel_app', ROOT.parent / 'mint-toolbox/anki_import.py')
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class EntryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.site = self.root / 'WordPress site'
        self.site.mkdir()
        (self.site / 'wp-config.php').touch()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        wp = self.bin / 'wp'
        wp.write_text('#!/bin/sh\nif [ "$1" = core ]; then exit 0; fi\nprintf "WP_STUB_CALLED\\n" >&2\nexit 23\n')
        wp.chmod(0o755)
        self.env = {**os.environ, 'PATH': str(self.bin) + os.pathsep + os.environ['PATH'],
                    'XDG_CONFIG_HOME': str(self.root / 'config'), 'XDG_STATE_HOME': str(self.root / 'state')}
        self.env.pop('DISPLAY', None)
        self.env.pop('WAYLAND_DISPLAY', None)
        self.env.pop('WP_PATH', None)

    def call(self, *args, path=ROOT / 'app.py'):
        return subprocess.run([sys.executable, str(path), *map(str, args)], cwd=self.root,
                              env=self.env, capture_output=True, text=True, timeout=10)

    def test_help_without_wordpress_or_gui(self):
        result = self.call('--help')
        self.assertEqual(result.returncode, 0)
        self.assertIn('--choose', result.stdout)
        self.assertIn('--gui', result.stdout)

    def test_check_does_not_run_wordpress(self):
        result = self.call('--check', '--wp-path', self.site)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('WP_STUB_CALLED', result.stdout + result.stderr)

    def test_terminal_import_shows_live_failure_and_saves_log(self):
        pdf = self.root / 'anki-stats-2026-10-27@22-58-46-1.pdf'
        pdf.write_bytes(b'%PDF fixture')
        result = self.call('--wp-path', self.site, pdf.name)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('WP_STUB_CALLED', result.stdout)
        self.assertIn('Exit code:', result.stdout)
        self.assertIn(str(pdf), result.stdout)
        logs = list((self.root / 'state/mint-toolbox/logs').glob('*.log'))
        self.assertEqual(len(logs), 1)
        self.assertIn('WP_STUB_CALLED', logs[0].read_text())
        self.assertTrue(pdf.exists())

    def test_settings_and_precedence(self):
        with patch.dict(os.environ, self.env, clear=True):
            app.save_settings(self.site)
            self.assertEqual(app.wordpress_path(), self.site)
            with patch.dict(os.environ, {'WP_PATH': '/env/path'}):
                self.assertEqual(app.wordpress_path(), Path('/env/path'))
                self.assertEqual(app.wordpress_path('/explicit/path'), Path('/explicit/path'))
            self.assertEqual(app.config_path().stat().st_mode & 0o777, 0o600)

    def test_choose_returns_to_terminal(self):
        with patch.object(app, 'choose_files', return_value=[]), patch.object(app, 'show_gui') as gui:
            self.assertEqual(app.main(['--choose', '--wp-path', str(self.site)]), 0)
            gui.assert_not_called()

    def test_installed_payload_has_cli_and_desktop_entries(self):
        deb = next((ROOT / 'dist').glob('*.deb'))
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(['dpkg-deb', '-x', str(deb), tmp], check=True)
            stage = Path(tmp)
            command = stage / 'usr/bin/anki-time-travel'
            self.assertTrue(command.stat().st_mode & 0o111)
            self.assertIn('/usr/lib/anki-time-travel/app.py', command.read_text())
            desktop = (stage / 'usr/share/applications/anki-time-travel.desktop').read_text()
            self.assertIn('Exec=anki-time-travel --gui %F', desktop)
            self.assertIn('Terminal=false', desktop)
            installed_app = stage / 'usr/lib/anki-time-travel/app.py'
            result = self.call('--check', '--wp-path', self.site, path=installed_app)
            self.assertEqual(result.returncode, 0, result.stderr)


@unittest.skipUnless(os.environ.get('DISPLAY'), 'requires a graphical environment')
class DesktopTests(unittest.TestCase):
    def test_desktop_selection_and_terminal_chooser(self):
        import tkinter as tk
        from tkinter import ttk
        actual_tk = tk.Tk
        seen = []
        def make_window():
            window = actual_tk()
            def inspect():
                try:
                    def descendants(widget):
                        for child in widget.winfo_children():
                            yield child
                            yield from descendants(child)
                    widgets = list(descendants(window))
                    listing = next(w for w in widgets if isinstance(w, tk.Listbox))
                    self.assertEqual(listing.size(), 1)
                    buttons = [w.cget('text') for w in widgets if isinstance(w, ttk.Button)]
                    self.assertIn('Add PDFs...', buttons)
                    self.assertIn('Import to WordPress', buttons)
                    self.assertIn('Copy log', buttons)
                    seen.append(True)
                finally:
                    window.destroy()
            window.after(100, inspect)
            return window
        with patch('tkinter.Tk', make_window):
            app.show_gui(['/tmp/anki-stats-2026-10-27@22-58-46.pdf'], Path('/tmp/site'))
        self.assertEqual(seen, [True])
        with patch('tkinter.filedialog.askopenfilenames', return_value=('/tmp/selected.pdf',)):
            self.assertEqual(app.choose_files(), ['/tmp/selected.pdf'])


if __name__ == '__main__':
    unittest.main()
