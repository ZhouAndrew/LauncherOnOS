"""Window-scoped administrator helper with a fixed package allowlist and pipe IPC."""
import json
import subprocess
import threading

# This source is passed directly to isolated Python by pkexec. The authorized
# process captures its package allowlist before accepting requests on stdin.
BROKER = r"""
import json
import os
import subprocess
import sys

catalog = json.loads(sys.argv[1])
install_code = sys.argv[2]
environment = {
    'PATH': '/usr/sbin:/usr/bin:/sbin:/bin',
    'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
    'DEBIAN_FRONTEND': 'noninteractive',
}

def emit(value):
    print(json.dumps(value), flush=True)

if os.geteuid() != 0:
    raise SystemExit('Administrator authorization is required.')
emit({'ready': True})
while True:
    # EOF closes the authorization session when the window/process exits.
    line = sys.stdin.readline(65537)
    if not line:
        break
    try:
        if len(line) > 65536 or not line.endswith('\n'):
            raise ValueError('Invalid request size.')
        request = json.loads(line)
        if not isinstance(request, dict):
            raise ValueError('Invalid administrator request.')
        action = request.get('action')
        if action == 'close' and set(request) == {'action'}:
            break
        item = catalog[request['id']]
        if action == 'install' and set(request) == {'action', 'id', 'path'}:
            path = request['path']
            if not isinstance(path, str) or not os.path.isabs(path) or '\0' in path:
                raise ValueError('Invalid package path.')
            args = ['/usr/bin/python3', '-I', '-c', install_code,
                    item['sha256'], item['package'], item['version'], path]
        elif action == 'remove' and set(request) == {'action', 'id'}:
            args = ['/usr/bin/apt-get', '-o', 'Dpkg::Use-Pty=0', '-o', 'APT::Color=0',
                    'remove', '-y', item['package']]
            trial = subprocess.run([args[0], '--simulate', *args[1:]], env=environment,
                                   capture_output=True, text=True, timeout=120, check=True)
            emit({'line': trial.stdout})
            for row in trial.stdout.splitlines():
                fields = row.split()
                if fields and fields[0] in ('Inst', 'Remv', 'Purg'):
                    if fields[0] != 'Remv' or fields[1].split(':')[0] != item['package']:
                        raise ValueError('Removal would change another package.')
        else:
            raise ValueError('Unsupported administrator request.')
        with subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, errors='replace',
                              env=environment) as child:
            for output in child.stdout:
                emit({'line': output})
            emit({'code': child.wait()})
    except (KeyError, ValueError, TypeError, OSError, subprocess.SubprocessError) as exc:
        emit({'line': 'Administrator operation failed: ' + str(exc) + '\n'})
        emit({'code': 1})
"""


class AdminSession:
    def __init__(self, entries, install_code):
        self.catalog = {
            item['id']: {key: item[key] for key in ('sha256', 'package', 'version')}
            for item in entries if item.get('kind') != 'portable'
        }
        self.install_code = install_code
        self.process = None
        self.lock = threading.Lock()

    @property
    def active(self):
        return self.process is not None and self.process.poll() is None

    def authorize(self):
        with self.lock:
            if self.active:
                return
            self.process = subprocess.Popen(
                ['/usr/bin/pkexec', '/usr/bin/python3', '-I', '-u', '-c', BROKER,
                 json.dumps(self.catalog), self.install_code],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, bufsize=1,
            )
            line = self.process.stdout.readline()
            if not line or json.loads(line) != {'ready': True}:
                self.close()
                raise RuntimeError('Administrator authorization was cancelled or unavailable.')

    def run(self, key, enable, path, log):
        self.authorize()
        request = {'action': 'install' if enable else 'remove', 'id': key}
        if enable:
            request['path'] = str(path)
        with self.lock:
            if not self.active:
                raise RuntimeError('Administrator session ended. Unlock the window again.')
            self.process.stdin.write(json.dumps(request) + '\n')
            self.process.stdin.flush()
            output = []
            while True:
                line = self.process.stdout.readline()
                if not line:
                    raise RuntimeError('Administrator helper exited before returning a result. Refresh package status.')
                message = json.loads(line)
                if 'code' in message:
                    return subprocess.CompletedProcess(request, message['code'], ''.join(output), '')
                log.write(message['line'])
                output.append(message['line'])
                if len(output) > 1000:
                    del output[:500]

    def close(self):
        process, self.process = self.process, None
        if process:
            try:
                process.stdin.close()
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
            finally:
                process.stdout.close()
