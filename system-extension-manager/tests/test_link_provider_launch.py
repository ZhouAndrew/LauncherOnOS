"""Check that Link Provider never reports process creation as backend readiness."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'sources/link-provider/link-provider'


class LaunchTests(unittest.TestCase):
    def run_link(self, *args, config):
        return subprocess.run([sys.executable, str(SCRIPT), *args],
                              capture_output=True, text=True, timeout=12,
                              env={**os.environ, 'XDG_CONFIG_HOME': str(config)})

    def test_fast_nonzero_exit_is_not_reported_as_started(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(self.run_link('add-app', 'fail', '/bin/sh', '-c', 'exit 17',
                                          config=temp).returncode, 0)
            result = self.run_link('open', 'fail', config=temp)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('exited immediately with code 17', result.stderr)
            self.assertNotIn('Started:', result.stdout)

    def test_zero_exit_does_not_promise_application_ready(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(self.run_link('add-app', 'quick', '/bin/true',
                                          config=temp).returncode, 0)
            result = self.run_link('open', 'quick', config=temp)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('readiness not verified', result.stdout)
            self.assertNotIn('Started:', result.stdout)


if __name__ == '__main__':
    unittest.main()
