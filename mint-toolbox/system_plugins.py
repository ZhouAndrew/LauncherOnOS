"""Debian extension lifecycle, verified source builds, and a multi-tool manager."""
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading

from execution import OperationLog, LogPanel

ROOT = Path(__file__).resolve().parent


def plugins():
    rows = json.loads((ROOT / 'system-plugins.json').read_text('utf-8'))
    ids, packages = set(), set()
    for item in rows:
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', item['id']) or item['id'] in ids:
            raise ValueError('Invalid or duplicate extension ID')
        if not re.fullmatch(r'[a-z0-9][a-z0-9+.-]+', item['package']) or item['package'] in packages:
            raise ValueError('Invalid or duplicate package name')
        ids.add(item['id'])
        packages.add(item['package'])
    return rows


def plugin(key):
    for item in plugins():
        if item['id'] == key:
            return item
    raise ValueError('Unknown extension: ' + key)


def package_status(package, log=None):
    if log is not None:
        result = log.run(['/usr/bin/dpkg-query', '-W', '-f=${Status}\n${Version}', package], check=False)
    else:
        result = subprocess.run(['/usr/bin/dpkg-query', '-W', '-f=${Status}\n${Version}', package],
                            capture_output=True, text=True, timeout=15)
    if result.returncode == 1:
        return ('absent', None)
    if result.returncode:
        raise RuntimeError('Cannot read package status: ' + result.stderr)
    lines = result.stdout.splitlines()
    if len(lines) != 2:
        raise RuntimeError('Unexpected package status format')
    return tuple(lines)


def installed_version(package):
    status, version = package_status(package)
    return version if status == 'install ok installed' else None


def state_text(package):
    status, version = package_status(package)
    if status == 'install ok installed':
        return 'Enabled: ' + version
    if status == 'absent' or status.endswith(' ok config-files'):
        return 'Disabled'
    return 'Incomplete installation: ' + status


def verify_deb(item, deb, expected_hash=None, log=None):
    if not deb.is_file() or deb.is_symlink():
        raise ValueError('Debian package is missing or is a symbolic link')
    if expected_hash and hashlib.sha256(deb.read_bytes()).hexdigest() != expected_hash:
        raise ValueError('Debian package checksum verification failed')
    metadata = ['/usr/bin/dpkg-deb', '-f', str(deb), 'Package', 'Version', 'Architecture']
    architecture = ['/usr/bin/dpkg', '--print-architecture']
    if log is None:
        info = subprocess.run(metadata, check=True, capture_output=True, text=True, timeout=15).stdout
        arch = subprocess.check_output(architecture, text=True, timeout=15).strip()
    else:
        info = log.run(metadata).stdout
        arch = log.run(architecture).stdout.strip()
    fields = dict(line.split(': ', 1) for line in info.splitlines())
    if fields.get('Package') != item['package'] or fields.get('Version') != item['version']:
        raise ValueError('Package name or version does not match the extension catalog')
    if fields.get('Architecture') not in ('all', arch):
        raise ValueError('Incompatible package architecture. Use Build from source if available.')
    return fields


def bundled_deb(item, log=None):
    path = ROOT / item['deb']
    if not path.resolve().is_relative_to(ROOT):
        raise ValueError('Package path escapes the application directory')
    verify_deb(item, path, item['sha256'], log)
    return path


def command(key, enable, deb=None, log=None):
    item = plugin(key)
    if enable:
        if deb is None:
            deb = bundled_deb(item, log)
        else:
            deb = Path(deb)
            verify_deb(item, deb, log=log)
        args = ['/usr/bin/apt-get', '-o', 'Dpkg::Use-Pty=0', '-o', 'APT::Color=0',
                'install', '--no-install-recommends', '--no-remove', '-y', str(deb)]
    else:
        args = ['/usr/bin/apt-get', '-o', 'Dpkg::Use-Pty=0', '-o', 'APT::Color=0',
                'remove', '-y', item['package']]
    return args if os.geteuid() == 0 else ['/usr/bin/pkexec', *args]


def build_source(item, log):
    if os.geteuid() == 0:
        raise ValueError('Source builds must run as a regular user. Start Mint Toolbox without sudo.')
    recipe = item.get('source')
    if not recipe:
        raise ValueError('No source build recipe is available for this extension')
    # Only reviewed local sources are supported; there is no arbitrary URL execution.
    dependencies = recipe.get('requires', [])
    missing = [name for name in dependencies if not shutil.which(name)]
    if missing:
        raise ValueError('Missing build tools: ' + ', '.join(missing) + '. Install them and retry.')
    base = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'mint-toolbox/builds'
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    stage = Path(tempfile.mkdtemp(prefix=item['id'] + '-', dir=base))
    source = stage / 'source'
    output = stage / 'output'
    source.mkdir()
    output.mkdir()
    log.stage('Verifying pinned source files')
    for relative, checksum in recipe['files'].items():
        path = ROOT / relative
        dest = source / relative
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT) or not dest.resolve().is_relative_to(source):
            raise ValueError('Invalid source file path: ' + relative)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != checksum:
            raise ValueError('Source checksum verification failed: ' + relative)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    log.stage('Building as the current regular user')
    args = [str(output) if arg == '{output}' else arg for arg in recipe['argv']]
    log.run(args, cwd=source)
    artifacts = list(output.glob('*.deb'))
    if len(artifacts) != 1:
        raise ValueError('Source recipe must produce exactly one Debian package')
    verify_deb(item, artifacts[0], log=log)
    log.write('Built package: ' + str(artifacts[0]) + '\n')
    return artifacts[0]


def change(key, enable, log=None, from_source=False):
    owned = log is None
    log = log or OperationLog(key)
    try:
        item = plugin(key)
        log.stage(('Enable' if enable else 'Disable') + ': ' + item['name'])
        if from_source and not enable:
            raise ValueError('Source builds are only valid for enabling an extension')
        deb = build_source(item, log) if from_source else None
        args = command(key, enable, deb, log) if from_source else command(key, enable, log=log)
        # Dependency resolution errors are displayed before the authorized install.
        if enable:
            log.stage('Checking dependency compatibility without changing the system')
            start = args.index('/usr/bin/apt-get')
            simulation = args[start:]
            simulation.insert(1, '--simulate')
            log.run(simulation)
        log.stage('Installing package' if enable else 'Removing package')
        result = log.run(args, check=False)
        log.stage('Reading package status back from dpkg')
        status, version = package_status(item['package'], log)
        log.write(f'Package state: {status}; version: {version or "none"}\n')
        correct = (status == 'install ok installed' and version == item['version']) if enable else (status == 'absent' or status.endswith(' ok config-files'))
        if result.returncode or not correct:
            raise RuntimeError('Operation failed or package status readback did not match')
        log.stage('Completed successfully')
        return version
    except Exception as exc:
        log.stage('FAILED: ' + str(exc))
        raise
    finally:
        if owned:
            log.close()


def filter_plugins(items, query='', status_filter='All'):
    query = query.casefold().strip()
    return [item for item in items
            if query in ' '.join(str(item.get(k, '')) for k in ('id', 'name', 'description', 'package')).casefold()
            and (status_filter == 'All' or item['state'].startswith(status_filter))]


def show_gui(parent=None):
    import tkinter as tk
    from tkinter import ttk, messagebox
    window = tk.Toplevel(parent) if parent else tk.Tk()
    window.title('Mint Toolbox - System extensions')
    window.geometry('1100x760')
    window.minsize(820, 580)
    ttk.Label(window, text='Enable installs a package. Disable removes it. Installation affects all users.').pack(anchor='w', padx=12, pady=10)
    bar = ttk.Frame(window)
    bar.pack(fill='x', padx=12)
    ttk.Label(bar, text='Search').pack(side='left')
    query, status = tk.StringVar(), tk.StringVar(value='All')
    ttk.Entry(bar, textvariable=query).pack(side='left', fill='x', expand=True, padx=8)
    ttk.Combobox(bar, textvariable=status, values=['All', 'Enabled', 'Disabled', 'Incomplete'], state='readonly', width=16).pack(side='left')
    pane = ttk.Panedwindow(window, orient='vertical')
    pane.pack(fill='both', expand=True, padx=12, pady=10)
    upper = ttk.Frame(pane)
    pane.add(upper, weight=3)
    listing = ttk.Frame(upper)
    listing.pack(fill='both', expand=True)
    columns = ('name', 'version', 'state', 'source')
    tree = ttk.Treeview(listing, columns=columns, show='headings', selectmode='browse', height=7)
    for col, title, width in [('name', 'Tool', 280), ('version', 'Bundled version', 120), ('state', 'System status', 220), ('source', 'Source build', 110)]:
        tree.heading(col, text=title)
        tree.column(col, width=width, minwidth=90)
    scroll = ttk.Scrollbar(listing, command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    scroll.pack(side='right', fill='y')
    tree.pack(fill='both', expand=True)
    description = tk.StringVar(value='Select an extension to view its description.')
    ttk.Label(upper, textvariable=description, wraplength=980).pack(fill='x', pady=8)
    buttons = ttk.Frame(upper)
    buttons.pack(fill='x')
    panel = LogPanel(pane)
    pane.add(panel.frame, weight=3)
    events = queue.Queue()
    busy = [False]
    rows = []
    def selected():
        values = tree.selection()
        return next((r for r in rows if values and r['id'] == values[0]), None)
    def render(*_):
        old = tree.selection()
        tree.delete(*tree.get_children())
        for item in filter_plugins(rows, query.get(), status.get()):
            tree.insert('', 'end', iid=item['id'], values=(item['name'], item['version'], item['state'], 'Available' if item.get('source') else 'Unavailable'))
        if old and tree.exists(old[0]):
            tree.selection_set(old)
        update_selection()
    def refresh():
        nonlocal rows
        rows = plugins()
        for row in rows:
            try:
                row['state'] = state_text(row['package'])
            except Exception as exc:
                row['state'] = 'Incomplete: ' + str(exc)
        render()
    def update_selection(*_):
        item = selected()
        description.set(item['description'] if item else 'Select an extension to view its description.')
        for control in operation_buttons:
            control.configure(state='normal' if item and not busy[0] else 'disabled')
        if item and not item.get('source'):
            source_button.configure(state='disabled')
    def operate(enable, from_source=False):
        item = selected()
        if not item or busy[0]:
            return
        label = 'Build from source and install' if from_source else ('Enable / Install' if enable else 'Disable / Uninstall')
        if not messagebox.askyesno(label, label + ': ' + item['name'] + '\n\nCommands and output will appear below. Administrator authorization is requested only for package installation/removal.', parent=window):
            return
        busy[0] = True
        refresh_button.configure(state='disabled')
        update_selection()
        def worker():
            log = None
            error = None
            try:
                log = OperationLog(item['id'] + ': ' + label, lambda text: events.put(('line', text)))
                change(item['id'], enable, log, from_source)
            except Exception as exc:
                error = str(exc)
            finally:
                if log:
                    log.close()
                events.put(('done', error))
        threading.Thread(target=worker, daemon=False).start()
    def poll():
        try:
            for _ in range(200):
                kind, value = events.get_nowait()
                if kind == 'line':
                    panel.append(value)
                else:
                    busy[0] = False
                    refresh_button.configure(state='normal')
                    refresh()
                    if value:
                        panel.append('Operation failed: ' + value + '\n')
        except queue.Empty:
            pass
        window.after(75, poll)
    install_button = ttk.Button(buttons, text='Enable / Install', command=lambda: operate(True))
    remove_button = ttk.Button(buttons, text='Disable / Uninstall', command=lambda: operate(False))
    source_button = ttk.Button(buttons, text='Build from source...', command=lambda: operate(True, True))
    operation_buttons = [install_button, remove_button, source_button]
    for button in operation_buttons:
        button.pack(side='left', padx=(0, 8))
    refresh_button = ttk.Button(buttons, text='Refresh status', command=refresh)
    refresh_button.pack(side='left')
    tree.bind('<<TreeviewSelect>>', update_selection)
    query.trace_add('write', render)
    status.trace_add('write', render)
    def close():
        if busy[0]:
            messagebox.showinfo('Operation running', 'Wait for the current operation to finish. Its log is saved automatically.', parent=window)
        else:
            window.destroy()
    window.protocol('WM_DELETE_WINDOW', close)
    refresh()
    window.after(75, poll)
    if parent is None:
        window.mainloop()
    return window
