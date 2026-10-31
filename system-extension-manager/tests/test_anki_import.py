"""Run the full Bash import against a strict, isolated WordPress stub."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'sources/anki-time-travel/anki-time-travel.sh'


class PermalinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.site = self.root / 'site'
        self.site.mkdir()
        (self.site / 'wp-config.php').touch()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.log = self.root / 'calls'
        self.pdf = self.root / 'anki-stats-2026-10-27@22-58-46-1.pdf'
        self.pdf.write_bytes(b'%PDF test')
        wp = self.bin / 'wp'
        wp.write_text('#!' + sys.executable + '\n' + '''import json, os, sys
args = sys.argv[1:]
with open(os.environ['CALL_LOG'], 'a') as log: log.write(json.dumps(args) + '\\n')
if args == ['core', 'is-installed']: pass
elif args == ['db', 'prefix']: print('wp_')
elif args[:2] == ['term', 'get']: pass
elif args[:1] == ['eval']:
    assert len(args) == 2, args
    if args[1] == "echo get_gmt_from_date('2026-10-27 22:58:46');": print('2026-10-27 14:58:46')
    elif args[1] == 'echo get_permalink(15128);':
        if os.environ.get('URL_MODE') == 'fail': sys.exit(8)
        if os.environ.get('URL_MODE') == 'multiple': print('https://wrong.example/first/')
        print('https://andrew.local/2026/10/27/anki-at-october-27-2026-tuesday/')
    else: raise AssertionError(args)
elif args[:2] == ['db', 'query']:
    query = args[2]
    if 'SELECT ID' in query: pass
    elif 'SELECT pm.post_id' in query: print('15110')
    elif 'UPDATE wp_posts' in query: pass
    else: raise AssertionError(args)
elif args[:2] == ['post', 'create']: print('15128')
elif args[:2] == ['post', 'update']: pass
elif args[:3] == ['post', 'meta', 'get']: print('2026/10/anki-stats-2026-10-27@22-58-46-1.pdf')
elif args[:2] == ['post', 'get']:
    field = args[3]
    print({'--field=guid': 'https://andrew.local/wp-content/uploads/2026/10/anki-stats-2026-10-27@22-58-46-1.pdf',
           '--field=post_status': 'publish', '--field=post_date': '2026-10-27 22:58:46',
           '--field=post_parent': '15128'}[field])
elif args[:3] == ['post', 'term', 'set']: pass
elif args[:3] == ['post', 'term', 'list']: print('anki')
elif args == ['cache', 'flush']: pass
else: raise AssertionError('Unexpected command: ' + repr(args))
''')
        wp.chmod(0o755)

    def run_import(self, mode='single'):
        return subprocess.run(['/bin/bash', str(SCRIPT), str(self.pdf)], cwd=self.root,
            env={**os.environ, 'PATH': str(self.bin) + ':' + os.environ['PATH'],
                 'WP_PATH': str(self.site), 'CALL_LOG': str(self.log), 'URL_MODE': mode},
            capture_output=True, text=True, timeout=15)

    def test_full_import_returns_only_exact_post_permalink(self):
        result = self.run_import()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        links = [line for line in result.stdout.splitlines() if line.startswith('Post URL:')]
        self.assertEqual(links, ['Post URL:    https://andrew.local/2026/10/27/anki-at-october-27-2026-tuesday/'])
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertIn(['eval', 'echo get_permalink(15128);'], calls)
        self.assertFalse(any(call[:2] == ['post', 'url'] for call in calls))
        self.assertTrue(self.pdf.exists())

    def test_multiple_permalink_lines_cannot_report_success(self):
        result = self.run_import('multiple')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Expected one HTTP(S) permalink', result.stderr)
        self.assertNotIn('Verification passed', result.stdout)

    def test_permalink_command_failure_cannot_report_success(self):
        result = self.run_import('fail')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Could not read the permalink', result.stderr)
        self.assertNotIn('Verification passed', result.stdout)


if __name__ == '__main__':
    unittest.main()
