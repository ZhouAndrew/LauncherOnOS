"""Exercise real Bash input handling before any WordPress writes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'originals/anki-time-travel.sh'


class AnkiPdfPathsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.desktop = self.root / 'Desktop with spaces'
        self.desktop.mkdir()
        self.wp = self.root / 'wordpress'
        self.wp.mkdir()
        (self.wp / 'wp-config.php').touch()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.log = self.root / 'calls.jsonl'
        stub = self.bin / 'wp'
        stub.write_text('#!' + sys.executable + '\n' + '''import json, os, sys
with open(os.environ['STUB_LOG'], 'a') as log:
    log.write(json.dumps({'args': sys.argv[1:], 'cwd': os.getcwd()}) + '\\n')
args = sys.argv[1:]
if args == ['core', 'is-installed']:
    sys.exit(0)
if args == ['db', 'prefix']:
    print('wp_')
    sys.exit(0)
if args[:2] == ['term', 'get']:
    sys.exit(0)
if args[:1] == ['eval']:
    # Stop before the post/attachment write path. No real WordPress is used.
    sys.exit(19)
raise SystemExit('Unexpected WordPress command: ' + repr(args))
''')
        stub.chmod(0o755)

    def run_script(self, *args):
        return subprocess.run(['/bin/bash', str(SCRIPT), *map(str, args)], cwd=self.desktop,
            env={**os.environ, 'PATH': str(self.bin) + os.pathsep + os.environ['PATH'],
                 'WP_PATH': str(self.wp), 'STUB_LOG': str(self.log)},
            text=True, capture_output=True, timeout=10)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def assert_reaches_gmt_lookup(self, result):
        self.assertEqual(result.returncode, 19, result.stdout + result.stderr)
        self.assertNotIn('PDF not found', result.stderr)
        self.assertNotIn('Invalid filename', result.stderr)
        calls = self.calls()
        self.assertEqual(calls[-1]['args'][0], 'eval')
        self.assertTrue(all(call['cwd'] == str(self.wp) for call in calls))
        self.assertNotIn('create', [part for call in calls for part in call['args']])

    def test_relative_pdf_survives_wordpress_directory_change(self):
        filename = 'anki-stats-2026-10-27@22-58-46.pdf'
        (self.desktop / filename).write_bytes(b'%PDF fixture')
        self.assert_reaches_gmt_lookup(self.run_script(filename))

    def test_numeric_download_suffix_is_accepted(self):
        filename = 'anki-stats-2026-10-27@22-58-46-1.pdf'
        (self.desktop / filename).write_bytes(b'%PDF fixture')
        self.assert_reaches_gmt_lookup(self.run_script(filename))
        self.assertIn('2026-10-27 22:58:46', self.calls()[-1]['args'])

    def test_absolute_pdf_path_is_accepted(self):
        path = self.desktop / 'anki-stats-2026-10-27@22-58-46-12.pdf'
        path.write_bytes(b'%PDF fixture')
        self.assert_reaches_gmt_lookup(self.run_script(path))

    def test_missing_later_pdf_prevents_all_wordpress_calls(self):
        first = 'anki-stats-2026-10-27@22-58-46.pdf'
        (self.desktop / first).touch()
        result = self.run_script(first, 'missing.pdf')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('PDF not found', result.stderr)
        self.assertEqual(self.calls(), [])

    def test_unrecognized_suffix_is_rejected_before_wordpress(self):
        filename = 'anki-stats-2026-10-27@22-58-46-bad.pdf'
        (self.desktop / filename).touch()
        result = self.run_script(filename)
        self.assertIn('Invalid filename format', result.stderr)
        self.assertEqual(self.calls(), [])


if __name__ == '__main__':
    unittest.main()
