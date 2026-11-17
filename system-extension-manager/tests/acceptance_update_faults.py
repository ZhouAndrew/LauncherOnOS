#!/usr/bin/python3
"""Exercise the packaged updater with real APT failures on a disposable CI VM."""
import argparse
import io
from pathlib import Path
import select
import subprocess
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, '/usr/share/system-extension-manager/sources/security-updates')
import security_updates as updater


def expect_review_failure(detail):
    # Refresh fails before reading from stdin or reaching installation.
    with patch.object(updater.sys, 'stdin', spec=io.TextIOBase) as stdin:
        stdin.isatty.return_value = True
        try:
            updater.interactive_root()
        except updater.SafetyError as exc:
            message = str(exc)
            assert 'Review stopped before package installation.' in message, message
            assert detail in message, message
            print(message)
            return message
        else:
            raise AssertionError('Expected the review to stop.')


def busy():
    lock = Path('/var/lib/dpkg/lock-frontend')
    if not lock.is_file():
        raise AssertionError(f'Expected an existing APT lock: {lock}')
    holder = subprocess.Popen(
        ['/usr/bin/python3', '-c',
         'import fcntl, sys, time; '
         'held = open(sys.argv[1], "r+"); fcntl.lockf(held, fcntl.LOCK_EX | fcntl.LOCK_NB); '
         'print("ready", flush=True); time.sleep(30)', str(lock)],
        stdout=subprocess.PIPE, text=True,
    )
    try:
        assert select.select([holder.stdout], [], [], 5)[0], 'APT lock holder timed out'
        assert holder.stdout.readline().strip() == 'ready', 'Could not take APT lock'
        with patch.object(updater, 'ensure_host'):
            expect_review_failure('Another package operation is running.')
    finally:
        holder.terminate()
        holder.wait(timeout=5)
        holder.stdout.close()
    updater.check_locks()
    print('Lock released; the next check passes.')


def offline():
    with tempfile.TemporaryDirectory(prefix='sem-offline-') as name:
        directory = Path(name)
        directory.chmod(0o755)
        lists = directory / 'lists'
        lists.mkdir()
        sources = directory / 'ubuntu.list'
        sources.write_text('deb http://127.0.0.1:9/ubuntu noble main\n')
        scope = updater.APT_SCOPE | {
            'Dir::Etc::sourcelist': str(sources),
            'Dir::State::lists': str(lists),
        }
        options = [argument for key, value in scope.items()
                   for argument in ('-o', f'{key}={value}')]
        # Use real apt-get with a local fixture repository in an isolated network.
        with patch.object(updater, 'ensure_host'), \
                patch.object(updater, 'prepare_apt_scope'), \
                patch.object(updater, 'APT_SCOPE_OPTIONS', options):
            message = expect_review_failure('Could not refresh the update list.')
            assert '127.0.0.1' in message and any(reason in message for reason in (
                'Network is unreachable', 'Connection refused', 'Unable to connect',
            )), message


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('fault', choices=('busy', 'offline'))
    args = parser.parse_args()
    {'busy': busy, 'offline': offline}[args.fault]()
