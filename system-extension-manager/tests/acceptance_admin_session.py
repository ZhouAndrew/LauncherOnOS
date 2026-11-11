#!/usr/bin/env python3
"""Exercise one authorized helper across real install/remove on an ephemeral CI VM."""
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lifecycle
from admin_session import AdminSession
from execution import OperationLog

if os.environ.get('GITHUB_ACTIONS') != 'true':
    raise SystemExit('This real APT acceptance runs only on the disposable GitHub Actions VM.')

original = subprocess.Popen
authorizations = []
def launch(args, **kwargs):
    if args[:1] == ['/usr/bin/pkexec']:
        authorizations.append(1)
        args = ['sudo', *args[1:]]
    return original(args, **kwargs)

session = AdminSession(lifecycle.plugins(), lifecycle.SECURE_INSTALL_CODE)
log = OperationLog('Real window-scoped administrator session')
try:
    with patch.object(subprocess, 'Popen', side_effect=launch):
        session.authorize()
        process = session.process
        lifecycle.change('link-provider', True, log, admin=session)
        assert lifecycle.installed_version('mint-link-provider-extension') == '0.3.0'
        # Reject attempts to send arbitrary commands to the privileged process.
        session.process.stdin.write(json.dumps({'action': 'exec', 'id': 'link-provider',
                                               'command': ['/bin/true']}) + '\n')
        session.process.stdin.flush()
        rejected = []
        while True:
            message = json.loads(session.process.stdout.readline())
            rejected.append(message)
            if 'code' in message:
                assert message['code'] == 1
                break
        lifecycle.change('link-provider', False, log, admin=session)
        assert lifecycle.installed_version('mint-link-provider-extension') is None
        assert session.process is process
        assert len(authorizations) == 1, authorizations
        session.close()
        assert process.wait(timeout=10) == 0
    print('PASS: one authorization, real verified install/remove, arbitrary command rejected, EOF closed session.')
finally:
    session.close()
    log.close()
