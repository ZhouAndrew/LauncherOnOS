"""Saved log history and export regressions. No package operations."""
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import execution
import lifecycle


class LogHistoryTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        environment = patch.dict(os.environ, {'XDG_STATE_HOME': workspace.name})
        environment.start()
        self.addCleanup(environment.stop)
        self.workspace = Path(workspace.name)
        self.folder = execution.log_directory()

    def test_history_reads_existing_operations_and_terminal_transcripts(self):
        self.assertEqual(execution.saved_logs(self.folder), [])
        operation = execution.OperationLog('ZIP and Trash', lambda _: None)
        operation.close()
        transcript = lifecycle.new_terminal_transcript()
        transcript.write_text('stderr output\nExit code: 27\n', encoding='utf-8')
        (self.folder / 'link.log').symlink_to(operation.path)
        os.mkfifo(self.folder / 'pipe.log')
        os.utime(operation.path, (10, 10))
        os.utime(transcript, (20, 20))
        self.assertEqual(
            [(path, label) for path, _, label in execution.saved_logs(self.folder)],
            [(transcript, 'Security Updates terminal'), (operation.path, 'ZIP and Trash')],
        )
        self.assertIn('Exit code: 27', execution.log_preview(transcript))

    def test_export_preserves_raw_output_beyond_preview_and_keeps_history(self):
        self.folder.mkdir(parents=True)
        source = self.folder / 'existing.log'
        original = b'first line\n' + b'x' * (512 * 1024) + b'\n\xff\nExit code: 27\n'
        source.write_bytes(original)
        destination = self.workspace / 'exported.log'
        self.assertNotIn('first line', execution.log_preview(source))
        execution.export_log(source, destination)
        self.assertEqual(destination.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
        with self.assertRaises(ValueError):
            execution.export_log(source, source)
        self.assertEqual(source.read_bytes(), original)

    @unittest.skipUnless(os.environ.get('DISPLAY'), 'requires a graphical environment')
    def test_manager_reopens_history_refreshes_and_exports_selected_log(self):
        import tkinter as tk
        from tkinter import ttk

        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)

        parent = tk.Tk()
        self.addCleanup(parent.destroy)
        parent.withdraw()
        manager = lifecycle.show_gui(parent)
        history_button = next(w for w in descendants(manager)
                              if isinstance(w, ttk.Button) and w.cget('text') == 'Log History...')
        history_button.invoke()
        history = manager.children['log_history']
        self.assertEqual(history.title(), 'Log History')
        widgets = list(descendants(history))
        buttons = {w.cget('text'): w for w in widgets if isinstance(w, ttk.Button)}
        tree = next(w for w in widgets if isinstance(w, ttk.Treeview))
        preview = next(w for w in widgets if isinstance(w, tk.Text))
        self.assertIn('No saved logs yet', preview.get('1.0', 'end'))

        transcript = lifecycle.new_terminal_transcript()
        transcript.write_text('Updater stderr\n', encoding='utf-8')
        buttons['Refresh logs'].invoke()
        self.assertEqual(tree.selection(), (transcript.name,))
        self.assertIn('Updater stderr', preview.get('1.0', 'end'))
        with transcript.open('a', encoding='utf-8') as output:
            output.write('Exit code: 27\n')
        buttons['Refresh logs'].invoke()
        self.assertIn('Exit code: 27', preview.get('1.0', 'end'))
        destination = self.workspace / 'saved terminal log.log'
        with patch('native_dialogs.asksaveasfilename', return_value=str(destination)) as chooser:
            buttons['Save log...'].invoke()
        self.assertEqual(chooser.call_args.kwargs['initialfile'], transcript.name)
        self.assertEqual(destination.read_bytes(), transcript.read_bytes())
        buttons['Close'].invoke()
        manager.destroy()

        reopened = lifecycle.show_gui(parent)
        next(w for w in descendants(reopened)
             if isinstance(w, ttk.Button) and w.cget('text') == 'Log History...').invoke()
        tree = next(w for w in descendants(reopened.children['log_history']) if isinstance(w, ttk.Treeview))
        self.assertEqual(tree.selection(), (transcript.name,))
