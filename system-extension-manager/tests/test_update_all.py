"""One-time Update All regression tests: no live package installation."""
from pathlib import Path
import os
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import lifecycle
import manager


class UpdateAllTests(unittest.TestCase):
    def setUp(self):
        self.one = dict(id='zip-trash', kind='deb', package='zip-ext', version='2.0', name='ZIP')
        self.two = dict(id='homebackup', kind='deb', package='backup-ext', version='3.0', name='Backups', deb='packages/backup.deb')
        self.disabled = dict(id='link-provider', kind='deb', package='link-ext', version='1.0', name='Links')
        self.portable = dict(id='security-updates', kind='portable', name='Security Updates',
                             script='sources/security-updates/security_updates.py')

    def test_plan_only_upgrades_existing_old_packages(self):
        results = [('install ok installed', '1.0'),
                   ('install ok installed', '3.0'),
                   ('absent', None)]
        with patch.object(lifecycle, 'plugins', return_value=[self.one, self.two, self.disabled, self.portable]), \
             patch.object(lifecycle, 'package_status', side_effect=results) as status, \
             patch.object(lifecycle, 'bundled_deb') as verified, \
             patch.object(lifecycle.subprocess, 'run', side_effect=[subprocess.CompletedProcess([], 0, '', ''), subprocess.CompletedProcess([], 1, '', '')]) as compare:
            plan = lifecycle.update_all_plan()
        self.assertEqual(plan, [(self.one, '1.0')])
        self.assertEqual(status.call_count, 3)
        verified.assert_called_once_with(self.one, None)
        compare.assert_any_call(['/usr/bin/dpkg', '--compare-versions', '1.0', 'lt', '2.0'],
                                capture_output=True, text=True, timeout=15)

    def test_incomplete_state_aborts_without_installing_anything(self):
        with patch.object(lifecycle, 'plugins', return_value=[self.one]), \
             patch.object(lifecycle, 'package_status', return_value=('half-configured', '1.0')), \
             patch.object(lifecycle, 'change') as change:
            with self.assertRaisesRegex(RuntimeError, 'Incomplete installation'):
                lifecycle.update_all_plan()
            change.assert_not_called()

    def test_bad_candidate_hash_stops_plan_before_updates(self):
        with patch.object(lifecycle, 'plugins', return_value=[self.one]), \
             patch.object(lifecycle, 'package_status', return_value=('install ok installed', '1.0')), \
             patch.object(lifecycle.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')), \
             patch.object(lifecycle, 'bundled_deb', side_effect=ValueError('checksum mismatch')), \
             patch.object(lifecycle, 'change') as change:
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                lifecycle.update_all_plan()
            change.assert_not_called()

    def test_bad_dpkg_version_comparison_stops(self):
        with patch.object(lifecycle, 'plugins', return_value=[self.one]), \
             patch.object(lifecycle, 'package_status', return_value=('install ok installed', '1.0')), \
             patch.object(lifecycle.subprocess, 'run', return_value=subprocess.CompletedProcess([], 2, '', 'bad')):
            with self.assertRaisesRegex(RuntimeError, 'Cannot compare versions'):
                lifecycle.update_all_plan()

    def test_update_all_upgrades_only_plan_then_opens_security_review(self):
        log = Mock()
        with patch.object(lifecycle.os, 'geteuid', return_value=1000), \
             patch.object(lifecycle, 'update_all_plan', return_value=[(self.one, '1.0'), (self.two, '2.0')]), \
             patch.object(lifecycle, 'portable_script', return_value=Path('/tmp/safe-updater')), \
             patch.object(lifecycle, 'terminal_command', return_value=['terminal']), \
             patch.object(lifecycle, 'change', side_effect=['2.0', '3.0']) as change, \
             patch.object(lifecycle, 'open_extension') as security:
            result = lifecycle.update_all(log, include_security=True)
        self.assertEqual(result['updated'], ['zip-trash', 'homebackup'])
        self.assertTrue(result['security_review_started'])
        self.assertEqual([x.args[0] for x in change.call_args_list], ['zip-trash', 'homebackup'])
        self.assertTrue(all(x.kwargs.get('update') for x in change.call_args_list))
        security.assert_called_once_with('security-updates', log)

    def test_active_homebackup_timer_defers_only_homebackup(self):
        log, admin = Mock(), Mock()
        admin.run.return_value = subprocess.CompletedProcess([], 0)
        log.run.side_effect = [
            subprocess.CompletedProcess([], 0, '', ''),
            subprocess.CompletedProcess([], 0, 'active\n', ''),
            subprocess.CompletedProcess([], 0, '', ''),
        ]
        links = dict(self.disabled, deb='packages/link.deb', sha256='expected', version='2.0')
        with patch.object(lifecycle.os, 'geteuid', return_value=1000), \
             patch.object(lifecycle, 'update_all_plan', return_value=[(self.two, '2.0'), (links, '1.0')]), \
             patch.object(lifecycle, 'plugin', side_effect=[self.two, links]), \
             patch.object(lifecycle, 'package_status', side_effect=[
                 ('install ok installed', '2.0'), ('install ok installed', '1.0'),
                 ('install ok installed', '2.0')]), \
             patch.object(lifecycle, 'command', return_value=['verified-install']), \
             patch.object(lifecycle.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)), \
             patch.object(Path, 'read_bytes', return_value=b'bundled'), \
             patch.object(lifecycle.hashlib, 'sha256') as checksum:
            checksum.return_value.hexdigest.return_value = 'expected'
            result = lifecycle.update_all(log, include_security=False, admin=admin)
        self.assertEqual(result['updated'], ['link-provider'])
        self.assertIn('timer is active', result['deferred']['homebackup'])
        admin.run.assert_called_once_with('link-provider', True, ROOT / links['deb'], log)
        self.assertEqual([call.args[0][1] for call in log.run.call_args_list],
                         ['--simulate', 'show', '--simulate'])

    def test_failed_extension_stops_rest_without_opening_updater(self):
        log = Mock()
        with patch.object(lifecycle.os, 'geteuid', return_value=1000), \
             patch.object(lifecycle, 'update_all_plan', return_value=[(self.one, '1.0'), (self.two, '2.0')]), \
             patch.object(lifecycle, 'portable_script', return_value=Path('/tmp/safe-updater')), \
             patch.object(lifecycle, 'terminal_command', return_value=['terminal']), \
             patch.object(lifecycle, 'change', side_effect=RuntimeError('blocked by running service')) as change, \
             patch.object(lifecycle, 'open_extension') as security:
            with self.assertRaisesRegex(RuntimeError, 'stopped at ZIP'):
                lifecycle.update_all(log, include_security=True)
            self.assertEqual(change.call_count, 1)
            security.assert_not_called()
            self.assertTrue(any('UPDATE ALL STOPPED' in x.args[0] for x in log.stage.call_args_list))

    def test_terminal_unavailable_stops_before_any_extension_update(self):
        log = Mock()
        with patch.object(lifecycle.os, 'geteuid', return_value=1000), \
             patch.object(lifecycle, 'update_all_plan', return_value=[(self.one, '1.0')]), \
             patch.object(lifecycle, 'portable_script', return_value=Path('/tmp/safe-updater')), \
             patch.object(lifecycle, 'terminal_command', side_effect=ValueError('No terminal')), \
             patch.object(lifecycle, 'change') as change:
            with self.assertRaisesRegex(ValueError, 'No terminal'):
                lifecycle.update_all(log)
            change.assert_not_called()

    def test_no_update_still_offers_manual_security_review(self):
        log = Mock()
        with patch.object(lifecycle.os, 'geteuid', return_value=1000), \
             patch.object(lifecycle, 'update_all_plan', return_value=[]), \
             patch.object(lifecycle, 'portable_script', return_value=Path('/tmp/safe-updater')), \
             patch.object(lifecycle, 'terminal_command', return_value=['terminal']), \
             patch.object(lifecycle, 'change') as change, \
             patch.object(lifecycle, 'open_extension') as security:
            result = lifecycle.update_all(log)
            change.assert_not_called()
            security.assert_called_once()
            self.assertEqual(result['updated'], [])

    def test_explicit_cli_approval_required(self):
        with patch.object(manager.lifecycle, 'update_all_plan', return_value=[]), \
             patch.object(manager.sys.stdin, 'isatty', return_value=True), \
             patch('builtins.input', return_value='no'), \
             patch.object(manager.lifecycle, 'update_all') as update:
            self.assertEqual(manager.main(['--update-all']), 0)
            update.assert_not_called()
        with patch.object(manager.lifecycle, 'update_all_plan', return_value=[]), \
             patch.object(manager.sys.stdin, 'isatty', return_value=True), \
             patch('builtins.input', return_value='UPDATE ALL'), \
             patch.object(manager.lifecycle, 'update_all') as update:
            self.assertEqual(manager.main(['--update-all']), 0)
            update.assert_called_once_with(include_security=True)

    def test_noninteractive_cli_aborts_without_updates(self):
        with patch.object(manager.lifecycle, 'update_all_plan', return_value=[]), \
             patch.object(manager.sys.stdin, 'isatty', return_value=False), \
             patch.object(manager.lifecycle, 'update_all') as update:
            self.assertEqual(manager.main(['--update-all']), 1)
            update.assert_not_called()

    def test_batch_cannot_run_as_root(self):
        with patch.object(lifecycle.os, 'geteuid', return_value=0), \
             patch.object(lifecycle, 'update_all_plan') as plan:
            with self.assertRaisesRegex(ValueError, 'normal desktop user'):
                lifecycle.update_all(Mock())
            plan.assert_not_called()


if __name__ == '__main__':
    unittest.main()
