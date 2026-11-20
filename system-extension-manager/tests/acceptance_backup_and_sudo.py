#!/usr/bin/python3
"""Exercise real Borg and password-backed sudo on the disposable Actions VM."""
import contextlib
import errno
import json
import os
from pathlib import Path
import pty
import secrets
import select
import signal
import subprocess
import tempfile
import time


def sudo_prompt():
    user = 'sem-console-test'
    policy = Path('/etc/sudoers.d/sem-console-test')
    assert not policy.exists()
    subprocess.run(['/usr/sbin/useradd', '--no-create-home', '--shell', '/bin/sh', user], check=True)
    try:
        secret = secrets.token_urlsafe(24)
        subprocess.run(['/usr/sbin/chpasswd'], input=f'{user}:{secret}\n', text=True, check=True)
        policy.write_text(f'{user} ALL=(root) PASSWD: /usr/bin/true\n')
        policy.chmod(0o440)
        subprocess.run(['/usr/sbin/visudo', '-cf', str(policy)], check=True)
        for answer, should_pass in ((b'\x04', False), (secret.encode() + b'\n', True)):
            pid, terminal = pty.fork()
            if pid == 0:
                os.execv('/usr/sbin/runuser', ['runuser', '-u', user, '--',
                         '/usr/bin/sudo', '-k', '-p', 'SEM password: ', '/usr/bin/true'])
            deadline = time.monotonic() + 15
            received = b''
            sent = False
            try:
                while time.monotonic() < deadline:
                    assert select.select([terminal], [], [], max(0, deadline - time.monotonic()))[0]
                    try:
                        part = os.read(terminal, 4096)
                    except OSError as exc:
                        if exc.errno != errno.EIO:
                            raise
                        break
                    if not part:
                        break
                    received += part
                    if not sent and b'SEM password: ' in received:
                        os.write(terminal, answer)
                        sent = True
            finally:
                os.close(terminal)
                if not sent or time.monotonic() >= deadline:
                    with contextlib.suppress(ProcessLookupError):
                        os.kill(pid, signal.SIGKILL)
                _, status = os.waitpid(pid, 0)
            assert sent and (os.waitstatus_to_exitcode(status) == 0) == should_pass
            assert secret.encode() not in received, 'Terminal echoed the test password'
        print('Real sudo: EOF cancelled; fresh password authorized without echo.')
    finally:
        policy.unlink(missing_ok=True)
        subprocess.run(['/usr/sbin/userdel', user], check=True)


def borg_roundtrip():
    package = Path(__file__).resolve().parents[1] / 'packages/mint-homebackup-extension_0.1.6_all.deb'
    with tempfile.TemporaryDirectory(prefix='sem-borg-acceptance-') as name:
        work = Path(name)
        repo = work / 'repo'
        subprocess.run(['dpkg-deb', '-x', str(package), str(work / 'package')], check=True)
        selector = work / 'package/usr/lib/mint-homebackup-extension/select.py'
        original = b'HomeBackUp acceptance file\n'
        (work / 'sample.txt').write_bytes(original)
        env = {**os.environ, 'BORG_BASE_DIR': name, 'BORG_PASSPHRASE': secrets.token_urlsafe(24),
               'TZ': 'UTC'}

        def borg(*args):
            return subprocess.check_output(['borg', *args], env=env, cwd=work, timeout=30)

        borg('init', '--encryption=repokey', str(repo))
        for day in range(1, 5):
            archive = f'mint-2026110{day}T090000Z'
            borg('create', '--timestamp', f'2026-11-0{day}T09:00:00',
                 f'{repo}::{archive}', 'sample.txt')
        borg('create', f'{repo}::manual-backup', 'sample.txt')
        new = f'{repo}::mint-20261104T090000Z'
        borg('check', '--archives-only', '--verify-data', new)
        assert borg('extract', '--stdout', new, 'sample.txt') == original
        before = borg('list', '--json', str(repo))
        metadata = work / 'archives.json'
        metadata.write_bytes(before)
        plan = subprocess.check_output(['/usr/bin/python3', str(selector), str(metadata)], text=True)
        assert sorted(plan.splitlines()) == [
            'DELETE mint-20261101T090000Z', 'KEEP mint-20261102T090000Z',
            'KEEP mint-20261103T090000Z', 'KEEP mint-20261104T090000Z',
        ]
        assert {entry['name'] for entry in json.loads(borg('list', '--json', str(repo)))['archives']} == {
            entry['name'] for entry in json.loads(before)['archives']
        }
        print('Borg: encrypted create, data check and byte-for-byte restore passed; preview changed no archives.')


if __name__ == '__main__':
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('Run only on the disposable Actions VM.')
    sudo_prompt()
    borg_roundtrip()
