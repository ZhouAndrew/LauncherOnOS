"""Real HTTPS/HTTP requests to the installed-command entry point in isolated state."""
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request

SCRIPT = Path(__file__).resolve().parents[1] / 'sources/link-provider/link-provider'
PASSWORD = 'fixture-only-password-123'


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class LANAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.env = dict(os.environ, XDG_CONFIG_HOME=str(self.folder / 'config'),
                        XDG_DATA_HOME=str(self.folder / 'data'))
        self.port, self.http_port = free_port(), free_port()
        self.origin = f'https://127.0.0.1:{self.port}'
        self.marker = self.folder / 'ran'
        self.run_cli('add-app', 'fixture', '/usr/bin/touch', str(self.marker))
        self.run_cli('allow-lan', 'fixture')
        self.run_cli('configure-lan', '--host', '127.0.0.1', '--bind', '127.0.0.1',
                     '--port', str(self.port), '--http-port', str(self.http_port))
        self.run_cli('set-lan-password', '--stdin',
                     input_text=json.dumps({'password': PASSWORD, 'repeat': PASSWORD}))
        self.log = (self.folder / 'server.log').open('w')
        self.addCleanup(self.log.close)
        self.server = subprocess.Popen([sys.executable, str(SCRIPT), 'start-lan'],
                                       env=self.env, stdout=self.log, stderr=self.log)
        self.addCleanup(self.stop)
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=str(self.folder / 'config/link-provider/lan-cert.pem'))))
        for _ in range(100):
            try:
                self.request()
                break
            except (OSError, urllib.error.URLError):
                if self.server.poll() is not None:
                    self.fail((self.folder / 'server.log').read_text())
                time.sleep(.05)
        else:
            self.fail('LAN listener did not start.')

    def stop(self):
        self.server.terminate()
        self.server.wait(timeout=10)

    def run_cli(self, *arguments, input_text=None):
        result = subprocess.run([sys.executable, str(SCRIPT), *arguments], env=self.env,
                                input=input_text, capture_output=True, text=True, timeout=40)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def request(self, fields=None, origin=None):
        data = urllib.parse.urlencode(fields).encode() if fields is not None else None
        headers = {'Origin': origin or self.origin} if data is not None else {}
        req = urllib.request.Request(self.origin + '/run/fixture', data=data, headers=headers)
        try:
            response = self.opener.open(req, timeout=6)
        except urllib.error.HTTPError as response:
            return response.code, response.read().decode()
        with response:
            return response.status, response.read().decode()

    def test_password_page_requires_remote_password_and_executes_only_saved_preset(self):
        self.assertFalse(self.marker.exists())
        self.assertIn('type="password"', self.request()[1])
        self.assertEqual(self.request({'password': PASSWORD}, origin='https://foreign.invalid')[0], 403)
        self.assertEqual(self.request({'password': PASSWORD, 'command': 'id'})[0], 400)
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.request({'password': 'incorrect-password'})[0], 403)
        self.assertEqual(self.request({'password': PASSWORD})[0], 429)
        time.sleep(2.05)
        self.assertEqual(self.request({'password': PASSWORD})[0], 200)
        self.assertTrue(self.marker.is_file())
        self.marker.unlink()
        self.run_cli('deny-lan', 'fixture')
        self.assertEqual(self.request({'password': PASSWORD})[0], 404)
        self.assertFalse(self.marker.exists())

    def test_http_link_opens_https_page_without_running_command(self):
        with self.opener.open(f'http://127.0.0.1:{self.http_port}/run/fixture', timeout=6) as response:
            self.assertEqual(response.url, self.origin + '/run/fixture')
            self.assertIn(b'type="password"', response.read())
        self.assertFalse(self.marker.exists())

    def test_custom_scheme_maps_exact_id_and_rejects_remote_arguments(self):
        self.run_cli('add-scheme', 'study')
        self.assertEqual(self.run_cli('link', 'fixture', '--scheme', 'study').strip(), 'study://fixture')
        self.run_cli('open', 'study://fixture')
        self.assertTrue(self.marker.is_file())
        self.marker.unlink()
        bad = subprocess.run([sys.executable, str(SCRIPT), 'desktop', 'study://fixture?cmd=id'],
                             env=self.env, capture_output=True, text=True)
        self.assertNotEqual(bad.returncode, 0)
        self.assertFalse(self.marker.exists())
