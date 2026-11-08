"""Security regression cases; no host services or real business data are touched."""
import ast
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'sources/zip-trash'))
import lifecycle
import zip_trash


def load_script(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def builder_string(name):
    tree = ast.parse((ROOT / 'sources/homebackup/build.py').read_text())
    return next(node.value.value for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == name for target in node.targets))


class SecurityTests(unittest.TestCase):
    @unittest.skipUnless((REPO / 'mint-toolbox/originals/web2menu').exists(), 'legacy source not in portable manager')
    def test_multiline_url_cannot_create_an_exec_key(self):
        web = load_script('security_web2menu', REPO / 'mint-toolbox/originals/web2menu')
        for char in ('\n', '\r', '\t', '\x00', '\x7f'):
            with self.subTest(char=repr(char)):
                with self.assertRaises(ValueError):
                    web.normalize_url('https://example.invalid/' + char + 'Exec=/bin/true')
                with self.assertRaises(ValueError):
                    web.exec_quote('https://example.invalid/' + char + 'Exec=/bin/true')
        self.assertEqual(web.normalize_url('https://example.invalid/a?x=1&y=2'),
                         'https://example.invalid/a?x=1&y=2')

    def test_zip_default_never_invokes_trash_even_after_late_write(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source'
            source.write_text('original')
            calls = []
            def run(args, **kwargs):
                calls.append(args)
                if args[0] == '/usr/bin/gio':
                    self.fail('Default archive path must not invoke Trash')
                return subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
            def report(message):
                if message.startswith('Archive verified.'):
                    source.write_text('new data after verification')
            archive = zip_trash.archive_and_trash([source], run, report)
            self.assertTrue(archive.is_file())
            self.assertEqual(source.read_text(), 'new data after verification')

    def test_explicit_trash_warns_of_residual_concurrent_write_risk(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source'
            source.write_text('original')
            messages = []
            def run(args, **kwargs):
                if args[0] == '/usr/bin/gio':
                    Path(args[-1]).rename(Path(temp) / 'mock-trash')
                    return subprocess.CompletedProcess(args, 0)
                return subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
            zip_trash.archive_and_trash([source], run, messages.append, trash_originals=True)
            self.assertTrue(any('WARNING' in text and 'new data' in text for text in messages))

    @unittest.skipUnless((REPO / 'mint-toolbox/originals/archive-folder-to-trash').exists(), 'legacy source not in portable manager')
    def test_legacy_archive_refuses_directory_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'target'
            target.mkdir()
            link = Path(temp) / 'link'
            link.symlink_to(target, target_is_directory=True)
            result = subprocess.run(['bash', str(REPO / 'mint-toolbox/originals/archive-folder-to-trash'), str(link)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(target.is_dir())
            self.assertTrue(link.is_symlink())

    def test_disable_dispatches_before_disk_or_password_checks(self):
        admin = builder_string('admin').replace('exec /usr/lib/mint-homebackup-extension/stop-scheduler',
                                               "echo STOP_DISPATCHED; exit 0")
        with tempfile.TemporaryDirectory() as temp:
            script = Path(temp) / 'admin'
            script.write_text(admin)
            shell = "id(){ echo 0; }; findmnt(){ echo DISK_CHECK_BUG >&2; return 1; }; export -f id findmnt; bash \"$1\" disable"
            result = subprocess.run(['bash', '-c', shell, 'test', str(script)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('STOP_DISPATCHED', result.stdout)
            self.assertNotIn('DISK_CHECK_BUG', result.stderr)

    def run_stop_helper(self, state='inactive', fail_stop=False):
        with tempfile.TemporaryDirectory() as temp:
            script = Path(temp) / 'stop'
            calls = Path(temp) / 'calls'
            script.write_text(builder_string('stop_scheduler'))
            shell = '''id(){ echo 0; }
systemctl(){
  echo "$*" >> "$CALLS"
  if [[ "$1" == stop && "$FAIL_STOP" == 1 ]]; then return 1; fi
  if [[ "$1" == show && "$2" == --property=ActiveState ]]; then echo "$TEST_STATE"; fi
  if [[ "$1" == show && "$2" == --property=MainPID ]]; then
    [[ "${@: -1}" == *.service ]] || return 9
    echo 0
  fi
  if [[ "$1" == is-enabled ]]; then echo disabled; return 1; fi
  return 0
}
export -f id systemctl
bash "$1"
'''
            result = subprocess.run(['bash', '-c', shell, 'test', str(script)], capture_output=True, text=True,
                                    env={**os.environ, 'CALLS': str(calls), 'TEST_STATE': state,
                                         'FAIL_STOP': str(int(fail_stop))})
            return result, calls.read_text()

    def test_shutdown_stops_timer_and_service_and_reads_back(self):
        result, calls = self.run_stop_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('stop mint-homebackup-extension.timer', calls)
        self.assertIn('stop mint-homebackup-extension.service', calls)
        self.assertIn('is-enabled mint-homebackup-extension.timer', calls)

    def test_shutdown_failure_is_not_silently_accepted(self):
        for kwargs in ({'state': 'active'}, {'fail_stop': True}):
            with self.subTest(kwargs=kwargs):
                result, calls = self.run_stop_helper(**kwargs)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('disable mint-homebackup-extension.timer', calls)

    def test_prerm_propagates_shutdown_failure(self):
        script = builder_string('prerm').replace('/usr/lib/mint-homebackup-extension/stop-scheduler', '/bin/false')
        result = subprocess.run(['sh', '-c', script, 'prerm', 'remove'])
        self.assertNotEqual(result.returncode, 0)

    def test_anki_warning_precedes_intentional_publication(self):
        source = (ROOT / 'sources/anki-time-travel/anki-time-travel.sh').read_text()
        self.assertIn('--post_status=publish', source)
        self.assertLess(source.index('This import PUBLISHES'), source.index('ensure_term category'))
        self.assertIn('can overwrite', source)

    @unittest.skipUnless((REPO / 'mint-toolbox/originals/complete_anki_tasks_today.py').exists(), 'legacy source not in portable manager')
    def test_caldav_http_refused_before_dependency_install_or_password(self):
        result = subprocess.run([sys.executable, str(REPO / 'mint-toolbox/originals/complete_anki_tasks_today.py'),
                                 '--url', 'http://example.invalid/calendar/'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('HTTP can expose credentials', result.stderr)

    def test_direct_backup_uses_runner_transaction_lock(self):
        source = (ROOT / 'sources/homebackup/backup.sh').read_text()
        start = source.index('# The runner passes inherited fd 8;')
        snippet = source[start:source.index('mkdir -p "$TARGET"', start)]
        with tempfile.TemporaryDirectory() as temp:
            lock = str(Path(temp) / 'transaction.lock')
            script = Path(temp) / 'lock-test'
            script.write_text('set -e\nerr(){ echo "$*" >&2; exit 1; }\n' +
                              snippet.replace('/run/lock/homebackup-monthly.lock', lock))
            inherited = subprocess.run(['bash', '-c', 'exec 8>"$1"; flock -n 8; bash "$2"',
                                        'test', lock, str(script)], capture_output=True, text=True)
            self.assertEqual(inherited.returncode, 0, inherited.stderr)
            with subprocess.Popen(['bash', '-c', 'exec 8>"$1"; flock -n 8; echo LOCKED; read -r _',
                                   'test', lock], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as holder:
                self.assertEqual(holder.stdout.readline().strip(), 'LOCKED')
                separate = subprocess.run(['bash', str(script)], capture_output=True, text=True)
                self.assertNotEqual(separate.returncode, 0)
                holder.communicate('\n', timeout=5)

    def test_apt_rejects_unrelated_removals_and_kernel_changes(self):
        for plan in ('Remv unrelated-package [1.0]\n', 'Inst linux-image-6.8-generic (1.0 Ubuntu)\n',
                     'Inst nvidia-driver-580 (1.0 Ubuntu)\n'):
            log = Mock()
            log.run.return_value = subprocess.CompletedProcess([], 0, plan, '')
            with patch.object(lifecycle, 'package_status', return_value=('absent', None)), \
                    patch.object(lifecycle, 'command', return_value=['/usr/bin/apt-get', 'install', 'test']):
                with self.assertRaises(ValueError):
                    lifecycle.change('zip-trash', True, log)
            self.assertEqual(log.run.call_count, 1)

    def test_old_homebackup_cannot_upgrade_while_service_is_active(self):
        log = Mock()
        log.run.side_effect = [subprocess.CompletedProcess([], 0, '', ''),
                               subprocess.CompletedProcess([], 0, 'inactive\n', ''),
                               subprocess.CompletedProcess([], 0, 'active\n', '')]
        with patch.object(lifecycle, 'package_status', return_value=('install ok installed', '0.1.3')), \
                patch.object(lifecycle, 'command', return_value=['/usr/bin/apt-get', 'install', 'test']):
            with self.assertRaisesRegex(ValueError, 'before updating'):
                lifecycle.change('homebackup', True, log, update=True)
        # The only APT call is simulation, never the real installation.
        self.assertEqual(log.run.call_args_list[0].args[0][1], '--simulate')
        self.assertEqual(log.run.call_count, 3)


if __name__ == '__main__':
    unittest.main()
