import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import hashlib
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'sources/security-updates/security_updates.py'
spec = importlib.util.spec_from_file_location('security_updates', SOURCE)
security = importlib.util.module_from_spec(spec)
spec.loader.exec_module(security)


class SafetyTests(unittest.TestCase):
    def test_kernel_nvidia_and_dkms_protected(self):
        for name in ['linux-image-6.8.0-90-generic', 'linux-generic',
                     'linux-modules-nvidia-570-6.8.0', 'nvidia-driver-570',
                     'libnvidia-compute-570', 'xserver-xorg-video-nvidia-570',
                     'dkms', 'bcmwl-kernel-source', 'firmware-sof-signed',
                     'intel-microcode', 'grub-efi-amd64-signed', 'libegl-nvidia0',
                     'grub2-common', 'alsa-firmware-loaders', 'linux-firmware']:
            self.assertTrue(security.protected(name), name)
        for name in ['openssl', 'curl', 'libssl3t64', 'firefox']:
            self.assertFalse(security.protected(name), name)

    def test_simulation_rejects_unlisted_dependencies_and_removal(self):
        allowed = {'openssl': '3.0.13-0ubuntu3.8'}
        valid = 'Inst openssl [3.0.13-0ubuntu3.7] (3.0.13-0ubuntu3.8 Ubuntu:24.04/noble-security [amd64])\nConf openssl (3.0.13-0ubuntu3.8 Ubuntu:24.04/noble-security [amd64])\n'
        with patch.object(security, 'command', return_value=valid):
            self.assertEqual(security.simulate(allowed), ['openssl=3.0.13-0ubuntu3.8'])
        for bad in [
            valid + 'Inst libfoo (1.2 Ubuntu:24.04/noble [amd64])\n',
            valid + 'Remv nvidia-driver-570 [570.1]\n',
            valid + 'Inst linux-image-generic [1] (2 Ubuntu:24.04/noble-security [amd64])\n',
            valid.replace('0ubuntu3.8', '0ubuntu3.9'),
            '',
            valid + 'Conf libfoo (1.0)\n',
            valid.replace('Conf openssl (3.0.13-0ubuntu3.8', 'Conf openssl (3.0.13-0ubuntu3.9'),
        ]:
            with self.subTest(bad=bad):
                with patch.object(security, 'command', return_value=bad):
                    with self.assertRaises(security.SafetyError):
                        security.simulate(allowed)

    def test_interactive_requires_real_terminal(self):
        with patch.object(security.sys.stdin, 'isatty', return_value=False):
            with self.assertRaisesRegex(security.SafetyError, 'terminal'):
                security.interactive()

    def test_interactive_refresh_cancel_stops_before_install(self):
        with (
            patch.object(security.sys.stdin, 'isatty', return_value=True),
            patch.object(security.os, 'geteuid', return_value=1000),
            patch.object(security.subprocess, 'call', return_value=1) as sudo,
            patch.object(security, 'scan', side_effect=AssertionError('scan must not run')),
        ):
            with self.assertRaisesRegex(security.SafetyError, 'failed or was cancelled'):
                security.interactive()
            self.assertIn('--refresh-root', sudo.call_args.args[0])

    def test_interactive_decline_prevents_install(self):
        with (
            patch.object(security.sys.stdin, 'isatty', return_value=True),
            patch.object(security.os, 'geteuid', return_value=1000),
            patch.object(security.subprocess, 'call', return_value=0) as sudo,
            patch.object(security, 'scan', return_value=({'openssl': '1.0'}, {})),
            patch.object(security, 'simulate', return_value=['openssl=1.0']),
            patch('builtins.input', return_value='no'),
        ):
            security.interactive()
            self.assertEqual(sudo.call_count, 1)
            self.assertIn('--refresh-root', sudo.call_args.args[0])

    def test_apply_requires_root(self):
        with patch.object(security.os, 'geteuid', return_value=1000):
            with self.assertRaisesRegex(security.SafetyError, 'Root authorization'):
                security.apply('not-a-real-plan')

    def test_digest_ignores_dict_order_but_changes_on_new_version(self):
        self.assertEqual(security.digest({'b':'2','a':'1'}), security.digest({'a':'1','b':'2'}))
        self.assertNotEqual(security.digest({'a':'1'}), security.digest({'a':'2'}))

    def test_sudo_uses_isolated_root_verified_bootstrap(self):
        with patch.object(security.subprocess, 'call', return_value=0) as call:
            self.assertEqual(security.privileged_action('--refresh-root'), 0)
        args = call.call_args.args[0]
        self.assertEqual(args[:5], ['sudo', '/usr/bin/python3', '-I', '-c', security.ROOT_BOOTSTRAP])
        self.assertEqual(args[-1], '--refresh-root')
        self.assertIn('O_NOFOLLOW', security.ROOT_BOOTSTRAP)
        self.assertIn('mint-security-verified-', security.ROOT_BOOTSTRAP)

    def test_root_bootstrap_rejects_source_replacement(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'updater.py'
            source.write_bytes(b'altered contents')
            approved = hashlib.sha256(b'known approved bytes').hexdigest()
            with patch.object(sys, 'argv', ['-c', approved, str(source), '--refresh-root']), \
                 patch.object(sys, 'flags', SimpleNamespace(isolated=1)), \
                 patch.object(os, 'geteuid', return_value=0), \
                 patch.object(subprocess, 'run', side_effect=AssertionError('root must not run changed source')):
                with self.assertRaises(SystemExit) as exit_code:
                    exec(compile(security.ROOT_BOOTSTRAP, '<root-bootstrap>', 'exec'),
                         {'__name__': '__main__'})
                self.assertEqual(exit_code.exception.code, 1)

    def test_no_automatic_package_operations(self):
        text = SOURCE.read_text()
        self.assertNotIn('systemctl enable', text)
        self.assertNotIn('unattended-upgrades', text)
        self.assertNotIn('autoremove', '\n'.join(line for line in text.splitlines() if 'apt-get' in line))

    def test_root_lock_refuses_a_planted_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'keep'
            target.write_text('unchanged')
            link = Path(temp) / 'lock'
            link.symlink_to(target)
            with patch.object(security, 'LOCK', str(link)):
                with self.assertRaises(OSError):
                    security.open_update_lock()
            self.assertEqual(target.read_text(), 'unchanged')

    @unittest.skipIf(os.geteuid() == 0, 'requires an unprivileged file owner')
    def test_root_lock_refuses_unprivileged_precreated_file(self):
        with tempfile.TemporaryDirectory() as temp:
            lock = Path(temp) / 'lock'
            lock.touch()
            with patch.object(security, 'LOCK', str(lock)):
                with self.assertRaisesRegex(security.SafetyError, 'Unsafe update lock'):
                    security.open_update_lock()

    def test_simulation_command_forces_parser_locale(self):
        with patch.object(security.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')) as run:
            security.command(['/bin/true'], env={'LC_ALL': 'zh_CN.UTF-8'})
        self.assertEqual(run.call_args.kwargs['env']['LC_ALL'], 'C.UTF-8')


if __name__ == '__main__':
    unittest.main()
