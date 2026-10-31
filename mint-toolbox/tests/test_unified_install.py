import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import toolbox


class UnifiedInstallTests(unittest.TestCase):
    def test_complete_deb_contains_working_main_and_anki_entries(self):
        deb = ROOT / 'dist/mint-toolbox_0.5.0_all.deb'
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(['dpkg-deb', '-x', str(deb), tmp], check=True)
            stage = Path(tmp)
            app = stage / 'usr/share/mint-toolbox'
            for name in ['toolbox.py', 'anki_import.py', 'execution.py', 'system_plugins.py',
                         'originals/anki-time-travel.sh', 'system-plugins.json', 'catalog.json']:
                self.assertTrue((app / name).is_file(), name)
            self.assertTrue(list((app / 'debs').glob('*.deb')))
            command = stage / 'usr/bin/mint-toolbox'
            self.assertTrue(command.stat().st_mode & 0o111)
            self.assertIn('/usr/share/mint-toolbox/toolbox.py', command.read_text())
            desktop = (stage / 'usr/share/applications/mint-toolbox.desktop').read_text()
            self.assertIn('Exec=/usr/bin/mint-toolbox --gui', desktop)
            for args, expected in [(['--list'], 'anki-time-travel.sh'),
                                   (['--anki', '--help'], '--choose'),
                                   (['--plugin-list'], 'zip-trash')]:
                result = subprocess.run([sys.executable, str(app / 'toolbox.py'), *args],
                    capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected, result.stdout)


@unittest.skipUnless(os.environ.get('DISPLAY'), 'requires a graphical environment')
class UnifiedGuiTests(unittest.TestCase):
    def test_main_tool_action_opens_integrated_child_window(self):
        import tkinter as tk
        from tkinter import ttk
        real_tk = tk.Tk
        seen = []
        errors = []
        def create():
            root = real_tk()
            def descendants(parent):
                for widget in parent.winfo_children():
                    yield widget
                    yield from descendants(widget)
            def check():
                try:
                    listing = next(w for w in descendants(root) if isinstance(w, tk.Listbox))
                    index = next(i for i in range(listing.size()) if 'Historical Anki PDF' in listing.get(i))
                    listing.selection_set(index)
                    listing.event_generate('<<ListboxSelect>>')
                    root.update()
                    button = next(w for w in descendants(root) if isinstance(w, ttk.Button)
                                  and w.cget('text') == 'Import historical Anki PDF into WordPress')
                    button.invoke()
                    root.update()
                    children = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
                    self.assertEqual(len(children), 1)
                    self.assertIn('Mint Toolbox', children[0].title())
                    labels = [w.cget('text') for w in descendants(children[0]) if isinstance(w, ttk.Button)]
                    self.assertIn('Import to WordPress', labels)
                    self.assertIn('Copy log', labels)
                    seen.append(True)
                except Exception as exc:
                    errors.append(exc)
                finally:
                    root.destroy()
            root.after(150, check)
            return root
        with patch('tkinter.Tk', create):
            toolbox.launch_gui()
        if errors:
            raise errors[0]
        self.assertEqual(seen, [True])


if __name__ == '__main__':
    unittest.main()
