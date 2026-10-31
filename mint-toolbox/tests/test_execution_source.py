import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from execution import OperationLog
import system_plugins as plugins


class ExecutionTests(unittest.TestCase):
    def test_output_streams_before_process_exits_and_log_is_private(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_STATE_HOME': tmp}):
            seen = threading.Event()
            output = []
            def emit(line):
                output.append(line)
                if line == 'first\n':
                    seen.set()
            log = OperationLog('streaming test', emit)
            worker = threading.Thread(target=lambda: log.run([sys.executable, '-u', '-c',
                'import time; print("first", flush=True); time.sleep(2); print("last")']))
            worker.start()
            self.assertTrue(seen.wait(1.5), 'Output was buffered until completion')
            self.assertTrue(worker.is_alive())
            worker.join(5)
            self.assertFalse(worker.is_alive())
            log.close()
            text = log.path.read_text()
            self.assertIn('Exit code: 0', text)
            self.assertIn('first\nlast\n', text)
            self.assertEqual(stat.S_IMODE(log.path.stat().st_mode), 0o600)

    def test_failure_captures_stderr_and_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_STATE_HOME': tmp}):
            log = OperationLog('error test', lambda line: None)
            with self.assertRaises(subprocess.CalledProcessError):
                log.run([sys.executable, '-c', 'import sys; print("problem", file=sys.stderr); sys.exit(7)'])
            log.close()
            self.assertIn('problem', log.path.read_text())
            self.assertIn('Exit code: 7', log.path.read_text())

    def test_filter_multiple_extensions(self):
        rows = [dict(id='one', name='First tool', description='zip', package='a', state='Enabled: 1'),
                dict(id='two', name='Second tool', description='media', package='b', state='Disabled'),
                dict(id='three', name='Third tool', description='zip', package='c', state='Incomplete installation')]
        self.assertEqual(len(plugins.filter_plugins(rows)), 3)
        self.assertEqual([p['id'] for p in plugins.filter_plugins(rows, 'zip')], ['one', 'three'])
        self.assertEqual([p['id'] for p in plugins.filter_plugins(rows, '', 'Disabled')], ['two'])


class SourceTests(unittest.TestCase):
    def test_real_source_build_runs_as_regular_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.chmod(0o777)
            item = plugins.plugin('zip-trash')
            for name in [*item['source']['files'], 'system_plugins.py']:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            (root / 'item.json').write_text(json.dumps(item))
            code = '''import json, os
from pathlib import Path
from execution import OperationLog
import system_plugins as p
assert os.geteuid() != 0
log = OperationLog('source build')
deb = p.build_source(json.loads(Path('item.json').read_text()), log)
assert deb.exists()
print('SOURCE_BUILD_OK')
log.close()
'''
            opts = {'user': 65534, 'group': 65534, 'extra_groups': []} if os.geteuid() == 0 else {}
            try:
                result = subprocess.run([sys.executable, '-c', code], cwd=root,
                    env={**os.environ, 'XDG_CACHE_HOME': str(root / 'cache'), 'XDG_STATE_HOME': str(root / 'state')},
                    text=True, capture_output=True, timeout=30, **opts)
            except PermissionError:
                if os.geteuid() != 0:
                    raise
                self.skipTest('Container does not permit switching from root to a regular user; CI runs as a regular user')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('SOURCE_BUILD_OK', result.stdout)

    def test_changed_source_is_rejected_before_build(self):
        item = plugins.plugin('zip-trash')
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_CACHE_HOME': tmp}):
            altered = dict(item, source={**item['source'], 'files': {'zip_trash.py': '0' * 64}})
            with patch.object(plugins.os, 'geteuid', return_value=1000):
                with self.assertRaisesRegex(ValueError, 'Source checksum'):
                    plugins.build_source(altered, object_with_stage())

    def test_architecture_mismatch_explains_source_option(self):
        item = plugins.plugin('zip-trash')
        with patch.object(plugins.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0,
                f'Package: {item["package"]}\nVersion: {item["version"]}\nArchitecture: arm64\n', '')), \
             patch.object(plugins.subprocess, 'check_output', return_value='amd64\n'):
            with self.assertRaisesRegex(ValueError, 'Build from source'):
                plugins.verify_deb(item, ROOT / item['deb'])


class object_with_stage:
    def stage(self, message):
        pass


@unittest.skipUnless(os.environ.get('DISPLAY'), 'requires a graphical environment')
class MultipleToolsGuiTests(unittest.TestCase):
    def test_multirow_search_status_and_description(self):
        import tkinter as tk
        from tkinter import ttk
        root = tk.Tk()
        root.withdraw()
        item = plugins.plugin('zip-trash')
        rows = [dict(item, id='tool-' + str(n), name='Tool ' + str(n), package='test-' + str(n)) for n in range(3)]
        with patch.object(plugins, 'plugins', return_value=rows), patch.object(plugins, 'state_text', return_value='Disabled'):
            window = plugins.show_gui(root)
            root.update()
            def children(parent):
                for child in parent.winfo_children():
                    yield child
                    yield from children(child)
            tree = next(w for w in children(window) if isinstance(w, ttk.Treeview))
            self.assertEqual(len(tree.get_children()), 3)
            entry = next(w for w in children(window) if isinstance(w, ttk.Entry))
            entry.insert(0, 'Tool 1')
            root.update()
            self.assertEqual(tree.get_children(), ('tool-1',))
            tree.selection_set('tool-1')
            tree.event_generate('<<TreeviewSelect>>')
            root.update()
            labels = [w.cget('text') for w in children(window) if isinstance(w, ttk.Label)]
            self.assertIn(item['description'], labels)
            combo = next(w for w in children(window) if isinstance(w, ttk.Combobox))
            combo.set('Enabled')
            root.update()
            self.assertEqual(tree.get_children(), ())
            window.destroy()
        root.destroy()


if __name__ == '__main__':
    unittest.main()
