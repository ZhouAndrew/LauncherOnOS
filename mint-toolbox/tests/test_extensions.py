"""Unit tests for lifecycle classification and isolated, declarative user extensions."""
import json
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
import extensions


class UserExtensionsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        patcher = patch.dict(os.environ, {'XDG_CONFIG_HOME':str(self.home/'config'),
                                          'XDG_CACHE_HOME':str(self.home/'cache')})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.script = self.home/'my tool.sh'
        self.script.write_text('#!/usr/bin/env bash\nprintf "test-run\\n"\n')
        self.script.chmod(0o700)

    def test_builtin_lifecycle_groups(self):
        builtin = [x for x in toolbox.catalog() if x['origin']=='builtin']
        self.assertEqual(len(builtin), 24)
        self.assertEqual(len(toolbox.entries()), 16)
        states = {x['id']:x['lifecycle'] for x in builtin}
        self.assertEqual(states['anki-flow-patched'], 'removed')
        self.assertEqual(states['categorize-posts-by-keyword.bak'], 'archived')
        self.assertEqual(states['vdirsyncer'], 'external')
        self.assertEqual(states['extract_pdf_images.py'], 'available')

    def test_register_and_unregister_preserve_original_file(self):
        initial = self.script.read_bytes()
        item = extensions.add_extension(str(self.script),name='我的工具',category='开发辅助',
                                       description='Print test-run')
        self.assertTrue(item['id'].startswith('user-'))
        self.assertEqual(len(toolbox.entries()), 17)
        resolved = toolbox.resolve_tool(item['id'])
        self.assertEqual(resolved['name'], '我的工具')
        self.assertEqual(resolved['category'], '开发辅助')
        self.assertIn(str(self.script), toolbox.command_for(resolved, []))
        self.assertEqual(self.script.read_bytes(), initial)
        extensions.remove_extension(item['id'])
        self.assertEqual(len(toolbox.entries()),16)
        self.assertTrue(self.script.exists())

    def test_removed_tool_hidden_and_not_launchable(self):
        item = extensions.add_extension(str(self.script))
        extensions.mark_removed(item['id'],True)
        self.assertNotIn(item['id'], [x['id'] for x in toolbox.entries()])
        removed = toolbox.resolve_tool(item['id'])
        self.assertEqual(removed['lifecycle'], 'removed')
        with self.assertRaisesRegex(ValueError,'已标记为移除'):
            toolbox.command_for(removed,[])
        extensions.mark_removed(item['id'],False)
        self.assertEqual(toolbox.resolve_tool(item['id'])['lifecycle'],'available')

    def test_restore_previously_removed_builtin(self):
        self.assertEqual(toolbox.resolve_tool('anki-flow-patched')['lifecycle'],'removed')
        extensions.mark_removed('anki-flow-patched',False)
        self.assertEqual(toolbox.resolve_tool('anki-flow-patched')['lifecycle'],'available')

    def test_disabled_and_removed_are_independent_and_persistent(self):
        item = extensions.add_extension(str(self.script), name='试验工具')
        key = item['id']
        extensions.set_disabled(key, True)
        disabled = toolbox.resolve_tool(key)
        self.assertFalse(disabled['enabled'])
        self.assertEqual(disabled['lifecycle'], 'available')
        self.assertEqual(toolbox.display_status(disabled), '已禁用')
        self.assertNotIn(key, [entry['id'] for entry in toolbox.entries()])
        self.assertEqual(toolbox.manual_path(disabled, gui=True).suffix, '.html')
        with self.assertRaisesRegex(ValueError, '已禁用'):
            toolbox.command_for(disabled, [])

        extensions.mark_removed(key, True)
        both = toolbox.resolve_tool(key)
        self.assertEqual(both['lifecycle'], 'removed')
        self.assertFalse(both['enabled'])
        self.assertEqual(toolbox.display_status(both), '已移除')
        self.assertEqual(toolbox.detailed_status(both), '已移除 · 已禁用')
        with self.assertRaisesRegex(ValueError, '已标记为移除'):
            toolbox.command_for(both, [])

        extensions.mark_removed(key, False)
        restored = toolbox.resolve_tool(key)
        self.assertEqual(restored['lifecycle'], 'available')
        self.assertFalse(restored['enabled'], '恢复已移除状态不能偷偷重新启用')
        with self.assertRaisesRegex(ValueError, '已禁用'):
            toolbox.command_for(restored, [])
        extensions.set_disabled(key, False)
        ready = toolbox.resolve_tool(key)
        self.assertTrue(ready['enabled'])
        self.assertEqual(ready['lifecycle'], 'available')
        self.assertIn(str(self.script), toolbox.command_for(ready, []))
        self.assertTrue(self.script.exists())

    def test_enabling_does_not_restore_removed(self):
        item = extensions.add_extension(str(self.script))
        key = item['id']
        extensions.mark_removed(key, True)
        extensions.set_disabled(key, True)
        extensions.set_disabled(key, False)
        same = toolbox.resolve_tool(key)
        self.assertTrue(same['enabled'])
        self.assertEqual(same['lifecycle'], 'removed')
        with self.assertRaisesRegex(ValueError, '已标记为移除'):
            toolbox.command_for(same, [])

    def test_cli_respects_both_states_and_preserves_files(self):
        item = extensions.add_extension(str(self.script))
        key = item['id']
        env = {**os.environ, 'DISPLAY':'', 'WAYLAND_DISPLAY':''}
        def cli(*args):
            return subprocess.run([sys.executable, str(ROOT/'toolbox.py'), *args],
                                  env=env, text=True, capture_output=True, timeout=10)
        self.assertEqual(cli('--disable', key).returncode, 0)
        self.assertNotEqual(cli('--run', key).returncode, 0)
        self.assertIn('已禁用', cli('--info', key).stdout)
        self.assertEqual(cli('--mark-removed', key).returncode, 0)
        self.assertIn('已移除 · 已禁用', cli('--info', key).stdout)
        self.assertNotEqual(cli('--run', key).returncode, 0)
        self.assertEqual(cli('--restore', key).returncode, 0)
        self.assertNotEqual(cli('--run', key).returncode, 0)
        self.assertEqual(cli('--enable', key).returncode, 0)
        self.assertEqual(cli('--run', key).returncode, 0)
        self.assertTrue(self.script.exists())

    def test_missing_extension_entrypoint_becomes_unavailable(self):
        item = extensions.add_extension(str(self.script))
        self.script.unlink()
        self.assertEqual(toolbox.resolve_tool(item['id'])['lifecycle'],'unavailable')
        self.assertNotIn(item['id'], [x['id'] for x in toolbox.entries()])
        with self.assertRaises(FileNotFoundError):
            toolbox.command_for(toolbox.resolve_tool(item['id']), [])

    def test_manifest_rejects_path_traversal_and_implicit_code(self):
        sample = {'schema_version':1,'id':'user-example','name':'Example',
                  'description':'Test','category':'Test','executable':'/tmp/example',
                  'actions':[{'key':'run','label':'Start','argv':['{unsafe}']}]}
        with self.assertRaisesRegex(ValueError,'普通字面量'):
            extensions.validate_manifest(sample)
        sample['actions'][0]['argv']=[{'field':'missing','flag':'--output'}]
        with self.assertRaisesRegex(ValueError,'必须引用'):
            extensions.validate_manifest(sample)
        sample['executable']='../relative-path'
        with self.assertRaisesRegex(ValueError,'绝对路径'):
            extensions.validate_manifest(sample)

    def test_declarative_action_builds_safe_argv(self):
        item = extensions.add_extension(str(self.script))
        file = extensions.extension_dir() / (item['id']+'.json')
        obj = json.loads(file.read_text())
        obj['actions']=[{'key':'convert','label':'转换',
                         'fields':[{'key':'source','label':'源文件','kind':'file'},
                                   {'key':'folder','label':'输出目录','kind':'folder','required':False},
                                   {'key':'verbose','label':'详细模式','kind':'boolean','required':False}],
                         'argv':['convert', {'field':'source','flag':'--input'},
                                 {'field':'folder','flag':'--out'},
                                 {'field':'verbose','flag':'--verbose'}],
                         'severity':'medium'}]
        file.write_text(json.dumps(obj))
        tool=toolbox.resolve_tool(item['id'])
        action=toolbox.actions_for(item['id'])[0]
        result=toolbox.build_command(tool,action,
                {'source':str(self.script),'folder':str(self.home),'verbose':True})
        self.assertEqual(result,['convert','--input',str(self.script),
                                 '--out',str(self.home),'--verbose'])
        self.assertEqual(toolbox.build_command(tool,action,
                {'source':str(self.script),'folder':'','verbose':False}),
                ['convert','--input',str(self.script)])

    def test_invalid_manifest_is_isolated(self):
        folder=extensions.extension_dir()
        folder.mkdir(parents=True)
        (folder/'user-bad.json').write_text('THIS IS NOT JSON')
        self.assertEqual(len(toolbox.entries()),16)
        _,errors=extensions.load_extensions()
        self.assertEqual(len(errors),1)
        self.assertIn('user-bad.json',errors[0])

    def test_generated_html_escapes_untrusted_values(self):
        item=extensions.add_extension(str(self.script),name='<img src=x onerror=alert(1)>')
        webpage=toolbox.manual_path(toolbox.resolve_tool(item['id']),gui=True)
        body=webpage.read_text()
        self.assertIn('&lt;img',body)
        self.assertNotIn('<img',body)
        self.assertIn('<h1>',body)

    def test_cli_registration_lifecycle_and_unregistration(self):
        env={**os.environ,'DISPLAY':'','WAYLAND_DISPLAY':''}
        def cli(*args):
            return subprocess.run([sys.executable,str(ROOT/'toolbox.py'),*args],
                                  env=env,text=True,capture_output=True,timeout=10)
        add=cli('--extension-add',str(self.script),'--name','我的脚本','--category','示例')
        self.assertEqual(add.returncode,0,add.stderr)
        key=add.stdout.strip().split('：',1)[1].strip()
        self.assertIn(key,cli('--list').stdout)
        self.assertEqual(cli('--mark-removed',key).returncode,0)
        self.assertNotIn(key,cli('--list').stdout)
        self.assertIn(key,cli('--list','--all').stdout)
        self.assertNotEqual(cli('--run',key).returncode,0)
        self.assertEqual(cli('--restore',key).returncode,0)
        self.assertIn(key,cli('--list').stdout)
        self.assertEqual(cli('--extension-remove',key).returncode,0)
        self.assertTrue(self.script.exists())

    def test_native_picker_prefers_zenity(self):
        with patch.object(toolbox.shutil,'which',side_effect=lambda name:'/bin/zenity' if name=='zenity' else None), \
             patch.object(toolbox.subprocess,'run') as run:
            run.return_value.returncode=0
            run.return_value.stdout='/tmp/example file\n'
            self.assertEqual(toolbox.choose_path_gui('file',None),'/tmp/example file')
            self.assertIn('--file-selection',run.call_args.args[0])
            self.assertNotIn('--directory',run.call_args.args[0])


if __name__=='__main__':
    unittest.main()
