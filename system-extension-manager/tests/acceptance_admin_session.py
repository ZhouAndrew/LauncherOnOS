#!/usr/bin/env python3
"""Use the manager window to install and remove via one real privileged helper."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from tkinter import messagebox, ttk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lifecycle

if os.environ.get('GITHUB_ACTIONS') != 'true':
    raise SystemExit('This real APT acceptance runs only on the disposable GitHub Actions VM.')

original = subprocess.Popen
authorizations = []
def launch(args, **kwargs):
    if args[:1] == ['/usr/bin/pkexec']:
        authorizations.append(1)
        # Use the runner's existing authorization. The broker and APT run as root.
        args = ['sudo', *args[1:]]
    return original(args, **kwargs)

def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)

def wait(root, condition):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        root.update()
        if condition():
            return
        time.sleep(.05)
    raise AssertionError('Manager window operation timed out.')

with tempfile.TemporaryDirectory(prefix='manager-window-acceptance-') as directory:
    os.environ['XDG_STATE_HOME'] = directory
    receipt = lifecycle.safety_notice_path()
    receipt.parent.mkdir(parents=True)
    receipt.write_text('acknowledged\n')
    root = tk.Tk()
    root.withdraw()
    with patch.object(subprocess, 'Popen', side_effect=launch), patch.object(messagebox, 'askyesno', return_value=True):
        window = lifecycle.show_gui(root)
        session = window.admin_session
        try:
            widgets = list(descendants(window))
            buttons = {w.cget('text'): w for w in widgets if isinstance(w, ttk.Button)}
            tree = next(w for w in widgets if isinstance(w, ttk.Treeview))
            tree.selection_set('link-provider')
            root.update()
            buttons['Unlock'].invoke()
            wait(root, lambda: buttons['Unlock'].cget('text') == 'Lock')
            process = session.process
            buttons['Enable / Install'].invoke()
            wait(root, lambda: tree.item('link-provider', 'values')[2] == 'Enabled: 0.3.0')
            assert lifecycle.installed_version('mint-link-provider-extension') == '0.3.0'

            process.stdin.write(json.dumps({'action': 'exec', 'id': 'link-provider',
                                            'command': ['/bin/true']}) + '\n')
            process.stdin.flush()
            while True:
                message = json.loads(process.stdout.readline())
                if 'code' in message:
                    assert message['code'] == 1
                    break

            buttons['Disable / Uninstall'].invoke()
            wait(root, lambda: tree.item('link-provider', 'values')[2] == 'Disabled')
            assert lifecycle.installed_version('mint-link-provider-extension') is None
            assert session.process is process
            assert len(authorizations) == 1, authorizations
            window.tk.call(window.protocol('WM_DELETE_WINDOW'))
            assert not window.winfo_exists()
            assert process.wait(timeout=10) == 0
            print('PASS: GUI Unlock, one authorization for real install/remove, arbitrary command rejected, helper exited on close.')
        finally:
            if window.winfo_exists():
                window.destroy()
            root.destroy()
