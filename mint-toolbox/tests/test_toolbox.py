import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import toolbox


class ToolboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.pdf = self.dir / 'exam.pdf'
        self.pdf.write_text('dummy PDF')  # never processed by scripts
        self.source = self.dir / 'folder'
        self.source.mkdir()

    def spec(self, tool_id, action_id):
        tool = toolbox.resolve_tool(tool_id)
        action = next(x for x in toolbox.actions_for(tool_id) if x.key == action_id)
        return tool, action

    def test_complete_catalog_and_manuals(self):
        self.assertEqual(len(toolbox.catalog()), 24)
        self.assertEqual(len(toolbox.entries()), 16)
        for tool in toolbox.catalog():
            self.assertTrue(toolbox.script_path(tool).is_file())
            self.assertTrue(toolbox.manual_path(tool, gui=True).is_file())
            self.assertTrue(toolbox.manual_path(tool, gui=False).is_file())

    def test_unsupported_entrypoints_have_no_fake_gui(self):
        for entry in ('person-mosaic', 'podman-compose', 'vdirsyncer'):
            self.assertEqual(toolbox.actions_for(entry), ())
        self.assertNotIn('anki-flow-patched', [x['id'] for x in toolbox.entries()])
        self.assertNotIn('caldav-assistant-thunderbird-host-experimental',
                         [x['id'] for x in toolbox.entries()])

    def test_pdf_gui_args_match_original_cli(self):
        tool, action = self.spec('extract_pdf_images.py', 'extract')
        args = toolbox.build_command(tool, action, {
            'source': str(self.pdf), 'output': str(self.dir), 'duplicates': True})
        self.assertEqual(args, [str(self.pdf), '--output', str(self.dir), '--include-duplicates'])
        self.assertEqual(toolbox.command_for(tool, args)[:2], [sys.executable, str(ROOT/'originals/extract_pdf_images.py')])

    def test_pdf_output_defaults_next_to_selected_source(self):
        tool, action = self.spec('extract_pdf_images.py', 'extract')
        args = toolbox.build_command(tool, action, {'source':str(self.pdf)})
        self.assertEqual(args, [str(self.pdf), '--output', str(self.dir/'extracted_images')])

    def test_run_preserves_flags_for_original_cli(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        target = toolbox.resolve_tool('extract_pdf_images.py')
        with patch.object(toolbox, 'command_for', return_value=['mock-script','--output','folder']) as cmd, \
             patch.object(toolbox.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
            self.assertEqual(toolbox.main(['--run',target['id'],'--output','folder']), 0)
            cmd.assert_called_once_with(target, ['--output','folder'])
            run.assert_called_once_with(['mock-script','--output','folder'],check=False)

    def test_pdf_requires_actual_input(self):
        tool, action = self.spec('extract_pdf_images.py', 'extract')
        with self.assertRaises(ValueError):
            toolbox.build_command(tool, action, {'source':'/nonexistent/foo.pdf'})

    def test_archive_requires_folder(self):
        tool, action = self.spec('archive-folder-to-trash', 'archive')
        self.assertEqual(toolbox.build_command(tool, action, {'source':str(self.source), 'output':''}),[str(self.source)])
        with self.assertRaises(ValueError):
            toolbox.build_command(tool, action, {'source':str(self.pdf)})
        self.assertEqual(action.severity, 'high')

    def test_wordpress_bulk_edit_defaults_to_preview(self):
        preview = self.spec('categorize-posts-by-keyword', 'preview')
        apply = self.spec('categorize-posts-by-keyword', 'apply')
        self.assertEqual(toolbox.build_command(*preview, {'keyword':'my phrase'}),
                         ['--dry-run', 'my phrase'])
        self.assertEqual(toolbox.build_command(*apply, {'keyword':'my phrase', 'category':'School'}),
                         ['--yes', 'my phrase', 'School'])
        self.assertEqual(apply[1].severity, 'high')

    def test_wechat_preview_is_not_claimed_write_free(self):
        tool, act = self.spec('import_wechat_export', 'preview')
        self.assertEqual(toolbox.build_command(tool, act, {'source':str(self.source)}),
                         [str(self.source), '--dry-run'])
        self.assertIn('may generate', act.note)

    def test_caldav_action_must_be_confirmed(self):
        tool, action = self.spec('complete_anki_tasks_today.py', 'complete')
        self.assertEqual(action.severity, 'high')
        self.assertEqual(toolbox.build_command(tool, action, {'keyword':'Anki','date':''}),
                         ['--keyword','Anki'])

    def test_generated_html_contains_rendered_markdown(self):
        content=toolbox.manual_path(toolbox.resolve_tool('extract_pdf_images.py'),gui=True).read_text()
        self.assertIn('<html', content)
        self.assertIn('<h1', content)
        self.assertNotIn('<script', content)

    def test_list_cli_runs_without_gui_or_scripts(self):
        p=subprocess.run([sys.executable,str(ROOT/'toolbox.py'),'--list'], capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('extract_pdf_images.py',p.stdout)

    def test_unknown_tool_returns_error(self):
        p=subprocess.run([sys.executable,str(ROOT/'toolbox.py'),'--info','../../bad'],capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,1)


if __name__=='__main__':
    unittest.main()
