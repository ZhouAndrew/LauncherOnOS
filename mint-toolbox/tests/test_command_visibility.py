"""The user's filters and full command text must remain under user control."""
import contextlib
import io
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import toolbox
import extensions


class CommandVisibilityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        p = patch.dict(os.environ, {
            'XDG_CONFIG_HOME': str(self.home / 'config'),
            'XDG_CACHE_HOME': str(self.home / 'cache'),
        })
        p.start()
        self.addCleanup(p.stop)

    def test_filter_catalog_is_pure_and_independent_of_status_mutation(self):
        all_items = toolbox.catalog()
        before = toolbox.filter_catalog(all_items, category_filter='全部',
                                        status_filter='可用', query='pdf')
        self.assertTrue(before)
        original = [(row['id'], row['lifecycle'], row['enabled']) for row in all_items]
        target = toolbox.resolve_tool('extract_pdf_images.py')
        self.assertIn(target['id'], [row['id'] for row in before])
        extensions.set_disabled(target['id'], True)
        after = toolbox.filter_catalog(toolbox.catalog(), category_filter='全部',
                                       status_filter='可用', query='pdf')
        self.assertNotIn(target['id'], [row['id'] for row in after])
        self.assertEqual([(row['id'], row['lifecycle'], row['enabled']) for row in all_items],
                         original, 'Filtering must not mutate a previously obtained catalog')
        self.assertIn(target['id'], [row['id'] for row in toolbox.filter_catalog(
            toolbox.catalog(), category_filter='全部', status_filter='已禁用', query='pdf')])

    def test_display_command_is_full_and_shell_quotable_while_disabled(self):
        script = self.home / 'example tool.sh'
        script.write_text('#!/bin/bash\necho hello\n')
        script.chmod(0o700)
        tool = extensions.add_extension(str(script), name='Example')
        extensions.set_disabled(tool['id'], True)
        actual = toolbox.resolve_tool(tool['id'])
        with self.assertRaisesRegex(ValueError, '已禁用'):
            toolbox.command_for(actual, ['--name', 'two words'])
        preview = toolbox.command_text(toolbox.invocation_for(actual, ['--name', 'two words']))
        self.assertEqual(shlex.split(preview), ['/bin/bash', str(script), '--name', 'two words'])

    def test_cli_info_discloses_command_even_if_disabled(self):
        script = self.home / 'example tool.sh'
        script.write_text('#!/bin/bash\necho test-run\n')
        script.chmod(0o700)
        row = extensions.add_extension(str(script), name='Example')
        extensions.set_disabled(row['id'], True)
        process = subprocess.run([sys.executable, str(ROOT / 'toolbox.py'), '--info', row['id']],
                                 capture_output=True, text=True, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn('原程序命令：', process.stdout)
        self.assertIn(shlex.quote(str(script)), process.stdout)
        self.assertIn('mint-toolbox --run', process.stdout)
        blocked = subprocess.run([sys.executable, str(ROOT / 'toolbox.py'), '--run', row['id']],
                                 capture_output=True, text=True, timeout=10)
        self.assertNotEqual(blocked.returncode, 0)

    def test_cli_run_discloses_exact_args_but_preserves_argv(self):
        script = self.home / 'tool with spaces.sh'
        script.write_text('#!/bin/bash\nprintf "arg: %s\\n" "$@"\n')
        script.chmod(0o700)
        row = extensions.add_extension(str(script), name='Example')
        process = subprocess.run([sys.executable, str(ROOT / 'toolbox.py'), '--run',
                                  row['id'], '--keyword', 'two words'],
                                 capture_output=True, text=True, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn('执行命令：', process.stderr)
        self.assertIn(shlex.quote(str(script)), process.stderr)
        self.assertIn("'two words'", process.stderr)
        self.assertIn('arg: two words', process.stdout)

    def test_terminal_launcher_shows_quoted_command(self):
        with patch.object(toolbox.shutil, 'which', side_effect=lambda n: '/bin/xterm' if n == 'xterm' else None), \
             patch.object(toolbox.subprocess, 'Popen') as popen:
            toolbox.run_terminal(['/tmp/tool', '--name', 'two words'])
        argv = popen.call_args.args[0]
        self.assertEqual(argv[:3], ['/bin/xterm', '-e', 'bash'])
        self.assertIn('执行命令：', argv[-1])
        self.assertIn("'two words'", argv[-1])
        self.assertEqual(popen.call_args.kwargs['start_new_session'], True)

    def test_high_risk_cli_displays_full_command_before_confirmation(self):
        tool = toolbox.resolve_tool('categorize-posts-by-keyword')
        action = next(a for a in toolbox.actions_for(tool['id']) if a.key == 'apply')
        output = io.StringIO()
        with patch('builtins.input', side_effect=['my words', 'School', '取消']), \
             patch.object(toolbox.subprocess, 'run') as run, contextlib.redirect_stdout(output):
            result = toolbox.cli_action(tool, action)
        self.assertEqual(result, 0)
        self.assertFalse(run.called)
        self.assertIn('实际命令：', output.getvalue())
        self.assertIn("'my words'", output.getvalue())


class GuiFilterTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'),
                         'requires a graphical environment (run with xvfb-run)')
    def test_gui_does_not_change_filters_on_disable_remove_restore(self):
        import tkinter as tk
        from tkinter import ttk

        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        p = patch.dict(os.environ, {'XDG_CONFIG_HOME': str(Path(temp.name) / 'config'),
                                    'XDG_CACHE_HOME': str(Path(temp.name) / 'cache')})
        p.start()
        self.addCleanup(p.stop)

        real_tk = tk.Tk
        errors = []
        observations = []
        def make_root(*args, **kwargs):
            root = real_tk(*args, **kwargs)
            def descend(parent):
                for child in parent.winfo_children():
                    yield child
                    yield from descend(child)
            def find_button(label):
                return next(w for w in descend(root) if isinstance(w, ttk.Button)
                            and w.cget('text') == label)
            def check_ui():
                try:
                    search = next(w for w in descend(root) if isinstance(w, ttk.Entry))
                    combos = [w for w in descend(root) if isinstance(w, ttk.Combobox)]
                    self.assertEqual(len(combos), 2)
                    category, status = combos
                    listbox = next(w for w in descend(root) if isinstance(w, tk.Listbox))
                    search.delete(0, 'end')
                    search.insert(0, 'PDF')
                    category.set('全部')
                    status.set('可用')
                    root.update()
                    index = next(i for i in range(listbox.size()) if '提取' in listbox.get(i))
                    listbox.selection_set(index)
                    listbox.event_generate('<<ListboxSelect>>')
                    root.update()
                    initial = (search.get(), category.get(), status.get())
                    self.assertEqual(initial, ('PDF', '全部', '可用'))
                    self.assertIsNotNone(find_button('禁用工具'))
                    find_button('禁用工具').invoke()
                    root.update()
                    self.assertEqual((search.get(), category.get(), status.get()), initial)
                    self.assertTrue(find_button('启用工具'))
                    self.assertTrue(any('已禁用' in w.cget('text') for w in descend(root)
                                        if isinstance(w, ttk.Label)))
                    find_button('启用工具').invoke()
                    root.update()
                    self.assertEqual((search.get(), category.get(), status.get()), initial)
                    with patch('tkinter.messagebox.askyesno', return_value=True):
                        find_button('标记已移除').invoke()
                    root.update()
                    self.assertEqual((search.get(), category.get(), status.get()), initial)
                    self.assertTrue(find_button('恢复'))
                    find_button('恢复').invoke()
                    root.update()
                    self.assertEqual((search.get(), category.get(), status.get()), initial)
                    # GUI must display the *fully populated* command, not just a
                    # button label or an incomplete base invocation.
                    source_pdf = Path(temp.name) / 'example file.pdf'
                    source_pdf.write_bytes(b'%PDF mock source only')
                    with patch.object(toolbox, '_input_dialog', return_value={
                             'source': str(source_pdf), 'output': str(Path(temp.name)),
                             'duplicates': True}), patch.object(toolbox, 'run_terminal') as run:
                        find_button('提取图片').invoke()
                    run.assert_called_once()
                    shown = [w.get('1.0', 'end').strip() for w in descend(root)
                             if isinstance(w, tk.Text)]
                    self.assertTrue(any(shlex.quote(str(source_pdf)) in t and
                                        '--include-duplicates' in t for t in shown), shown)
                    self.assertEqual((search.get(), category.get(), status.get()), initial)
                    # Select same tool again to see the base invocation.
                    selected = listbox.curselection()
                    self.assertTrue(selected)
                    listbox.event_generate('<<ListboxSelect>>')
                    root.update()
                    # Exact executable is visible, selectable and copyable.
                    texts = [w.get('1.0', 'end').strip() for w in descend(root)
                             if isinstance(w, tk.Text)]
                    self.assertTrue(any('extract_pdf_images.py' in t and sys.executable in t
                                        for t in texts), texts)
                    observations.append(True)
                except Exception as exc:
                    errors.append(exc)
                finally:
                    root.destroy()
            root.after(100, check_ui)
            return root

        with patch.object(tk, 'Tk', side_effect=make_root):
            toolbox.launch_gui()
        if errors:
            raise errors[0]
        self.assertEqual(observations, [True])


if __name__ == '__main__':
    unittest.main()
