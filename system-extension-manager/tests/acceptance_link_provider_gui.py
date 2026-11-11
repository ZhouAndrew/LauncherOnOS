#!/usr/bin/env python3
"""Use GTK controls, clipboard, saved settings and real HTTP(S) listeners."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sources/link-provider'))
from link_provider_gui import LinkManager

loader = importlib.machinery.SourceFileLoader('link_provider', str(ROOT / 'sources/link-provider/link-provider'))
spec = importlib.util.spec_from_loader(loader.name, loader)
backend = importlib.util.module_from_spec(spec)
loader.exec_module(backend)

def wait(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        if predicate():
            return
        time.sleep(.025)
    raise AssertionError('GTK operation timed out.')

def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]

def dialog():
    return next(w for w in Gtk.Window.list_toplevels() if isinstance(w, Gtk.Dialog))

def entries(widget):
    if isinstance(widget, Gtk.Entry):
        return [widget]
    if isinstance(widget, Gtk.Container):
        return [entry for child in widget.get_children() for entry in entries(child)]
    return []

with tempfile.TemporaryDirectory(prefix='link-provider-human-path-') as directory:
    os.environ['XDG_CONFIG_HOME'] = str(Path(directory) / 'config')
    os.environ['XDG_DATA_HOME'] = str(Path(directory) / 'data')
    marker = Path(directory) / 'ran'
    from argparse import Namespace
    backend.change_link(Namespace(action='add-app', id='fixture', program='/usr/bin/touch', arguments=[str(marker)]))
    window = LinkManager(ROOT / 'sources/link-provider/link-provider', backend.read_links,
                         backend.LinkError, backend.DESKTOP_ID, backend.lan_settings, backend.configured_schemes)
    window.show_all()
    try:
        wait(lambda: not window.busy)
        window.scheme_dialog(None)
        editor = dialog()
        entries(editor)[0].set_text('study')
        editor.response(Gtk.ResponseType.OK)
        wait(lambda: window.handler_current)
        assert backend.default_handler('x-scheme-handler/study') == backend.DESKTOP_ID
        subprocess.run(['gio', 'open', 'study://fixture'], check=True, timeout=10)
        wait(marker.is_file)
        marker.unlink()
        window.lan_button.clicked()
        wait(lambda: backend.read_links()['fixture'].get('allow_lan'))
        window.password_dialog(None)
        editor = dialog()
        for entry in entries(editor):
            entry.set_text('fixture-only-password-123')
        editor.response(Gtk.ResponseType.OK)
        wait(lambda: backend.registry_path().with_name('lan-password').is_file())
        wait(lambda: editor not in Gtk.Window.list_toplevels())
        window.lan_dialog(None)
        editor = dialog()
        https_port, http_port = free_port(), free_port()
        values = ['127.0.0.1', '127.0.0.1', str(https_port), str(http_port), '', '']
        for entry, value in zip(entries(editor), values):
            entry.set_text(value)
        editor.response(Gtk.ResponseType.OK)
        wait(lambda: bool(backend.lan_settings()))
        wait(lambda: editor not in Gtk.Window.list_toplevels())
        window.refresh('fixture')
        window.copy_lan_button.clicked()
        expected = f'https://127.0.0.1:{https_port}/run/fixture'
        assert Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).wait_for_text() == expected
        window.server_button.clicked()
        wait(lambda: window.server_button.get_label() == 'Stop LAN')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=backend.lan_settings()["cert"])))
        with opener.open(f'http://127.0.0.1:{http_port}/run/fixture', timeout=5) as response:
            assert response.url == expected
            assert b'type="password"' in response.read()
        assert not marker.exists()
        import urllib.parse
        request = urllib.request.Request(expected,
            data=urllib.parse.urlencode({'password':'fixture-only-password-123'}).encode(),
            headers={'Origin': f'https://127.0.0.1:{https_port}'})
        with opener.open(request, timeout=5) as response:
            assert response.status == 200
        assert marker.is_file()
        window.server_button.clicked()
        wait(lambda: window.server is None)
        print('PASS: GTK custom scheme and GIO dispatch, authorization, password entry, LAN configuration, clipboard, trusted HTTPS launch and Stop LAN.')
    finally:
        window.close_server()
        window.destroy()
