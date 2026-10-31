#!/usr/bin/env python3
"""Mint Toolbox: a simple GUI for existing personal utilities, with CLI fallback.

GUI: Tk widgets + system-native file chooser (Zenity if available).
Discovery never imports or executes scripts. Legacy runtime messages are translated to English.
"""
from __future__ import annotations

import argparse
import html
import re
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import webbrowser
from dataclasses import dataclass
from typing import Any

import extensions
import system_plugins

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / 'catalog.json'
ORIGINALS = ROOT / 'originals'
MANUALS_HTML = ROOT / 'manuals' / 'html'
MANUALS_MD = ROOT / 'manuals' / 'md'

@dataclass(frozen=True)
class Field:
    key: str
    label: str
    kind: str = 'text'  # text, file, folder, file_or_folder, boolean
    default: str = ''
    required: bool = True

@dataclass(frozen=True)
class Action:
    key: str
    label: str
    fields: tuple[Field, ...] = ()
    severity: str = 'low'
    note: str = ''
    argv: tuple[Any, ...] = ()  # Declarative argument template (user extensions only)

# Minimal, task-oriented interaction: everything here maps to a real script argument.
ACTION_MAP: dict[str, tuple[Action, ...]] = {
    'extract_pdf_images.py': (
        Action('extract', 'Extract images', (Field('source', 'PDF file or folder', 'file_or_folder'),
                                      Field('output', 'Output folder', 'folder', required=False),
                                      Field('duplicates', 'Keep duplicate images', 'boolean', required=False))),),
    'archive-folder-to-trash': (
        Action('archive', 'Archive and move to Trash', (Field('source', 'Folder to archive', 'folder'),
                                         Field('output', 'Archive output folder (optional)', 'folder', required=False)),
               'high', 'Create and verify the archive, then move the original folder to Trash.'),),
    'andrew-lan-speed-test.sh': (
        Action('link', 'Inspect network adapter and link', (), 'medium', 'The script may install missing packages and ask for a test IP address.'),
        Action('client', 'Test connection to another device', (Field('peer', 'Peer IP address or hostname'),), 'medium',
               'Run an iperf3 server on the peer. Dependencies may need installation.'),
        Action('server', 'Start a speed-test server', (), 'medium', 'Starts a local iperf3 listener. Close the terminal to stop it.'),
        Action('cable', 'Test network cable', (), 'high', 'Cable diagnostics may interrupt connectivity. Do not run over SSH.')),
    'anki-time-travel.sh': (
        Action('post', 'Import historical Anki PDF into WordPress',
               (Field('pdf', 'Historical statistics PDF', 'file'),), 'high', 'Creates or reuses WordPress posts and attachments. The filename must include a timestamp.'),),
    'categorize-posts-by-keyword': (
        Action('preview', 'Preview matching posts', (Field('keyword', 'Search keyword'),), 'low', 'Search only; categories are not changed.'),
        Action('apply', 'Set post categories in bulk',
               (Field('keyword', 'Search keyword'), Field('category', 'Category name')), 'high',
               'Changes categories on all matching posts. Preview the matches first.')),
    'create-subject-page.sh': (
        Action('create', 'Create or update subject pages',
               (Field('subjects', 'Subject names (comma-separated)'),), 'high',
               'Creates or updates WordPress tags and subject pages using the configured parent page.'),),
    'wordpress_diagnose_today.sh': (
        Action('diagnose', 'Generate a WordPress diagnostic report',
               (Field('output', 'Report output folder', 'folder', required=False),), 'low',
               'Runs the read-only diagnostic script and saves the report to the selected folder.'),),
    'unlock_wechat_export': (
        Action('unlock', 'Generate readable chat HTML',
               (Field('source', 'WeChat export root folder', 'folder'),), 'medium',
               'Generates messages-unlocked.html under conversations without overwriting existing files.'),),
    'import_wechat_export': (
        Action('preview', 'Preview import', (Field('source', 'WeChat export root folder', 'folder'),),
               'medium', 'The script may generate unlocked HTML before its dry-run checks. Preview can write files.'),
        Action('import', 'Import WeChat records into WordPress', (Field('source', 'WeChat export root folder', 'folder'),),
               'high', 'Copies exported assets and creates or updates WordPress posts containing private chats.')),
    'web2menu': (
        Action('add', 'Add a website to the application menu', (Field('url', 'Website URL'),
                                                     Field('name', 'Display name (optional)', required=False)),
               'medium', 'Creates a Linux Mint/Cinnamon desktop application entry.'),),
    'complete_anki_tasks_today.py': (
        Action('preview', 'Preview matching CalDAV tasks',
               (Field('keyword', 'Title keyword', default='Anki'), Field('date', 'Target date YYYY-MM-DD (optional)', required=False)),
               'low', 'Review the preview before applying changes.'),
        Action('complete', 'Complete matching tasks in bulk',
               (Field('keyword', 'Title keyword', default='Anki'), Field('date', 'Target date YYYY-MM-DD (optional)', required=False)),
               'high', 'Changes task completion status on the CalDAV server.')),
    'thunderbird-experiment': (
        Action('start', 'Back up and launch experimental build', (), 'medium', 'Uses the existing isolated Thunderbird experimental environment.'),),
    'thunderbird-experiment-restore-latest': (
        Action('restore', 'Restore the latest experimental backup', (), 'critical',
               'Replaces a Thunderbird profile. Close Thunderbird first. The script also requires YES confirmation.'),),
    'thunderbird-taskfix': (Action('start', 'Launch TaskFix', (), 'low'),),
    'thunderbird-taskfix-clean': (Action('start', 'Launch TaskFix Clean', (), 'low'),),
    'thunderbird-taskfix-recurring-safe': (Action('start', 'Launch Recurring Safe', (), 'low'),),
}


LIFECYCLE_NAMES = {
    'available': 'Available', 'external': 'External dependency', 'archived': 'Archived',
    'removed': 'Removed', 'unavailable': 'Missing file',
}


def display_status(tool: dict[str, Any]) -> str:
    """Primary filter group; disabled never overwrites the removal category."""
    if tool['lifecycle'] == 'available' and not tool.get('enabled', True):
        return 'Disabled'
    return LIFECYCLE_NAMES.get(tool['lifecycle'], 'Unknown')


def detailed_status(tool: dict[str, Any]) -> str:
    """Show both independent properties when a removed/archived tool is disabled."""
    base = LIFECYCLE_NAMES.get(tool['lifecycle'], 'Unknown')
    if not tool.get('enabled', True):
        return 'Disabled' if tool['lifecycle'] == 'available' else base + ' · Disabled'
    return base


def catalog() -> list[dict[str, Any]]:
    """Unified read-only view of built-ins and user-registered extensions."""
    data = json.loads(CATALOG.read_text(encoding='utf-8'))
    builtin = data['items']
    custom, _errors = extensions.load_extensions()
    disabled_ids = extensions.disabled_tool_ids()
    result = []
    for row in [*builtin, *custom]:
        item = dict(row)
        item.setdefault('origin', 'builtin')
        item.setdefault('lifecycle', 'available')
        item['enabled'] = item['id'] not in disabled_ids
        if extensions.is_removed(item['id']):
            item['lifecycle'] = 'removed'
        elif extensions.is_restored(item['id']) and item['lifecycle'] == 'removed':
            item['lifecycle'] = 'available'
        elif item['origin'] == 'extension':
            item['lifecycle'] = ('available' if Path(item['executable']).is_file()
                                 else 'unavailable')
        elif item['lifecycle'] == 'available' and not (ORIGINALS / item['id']).is_file():
            item['lifecycle'] = 'unavailable'
        result.append(item)
    return result


def entries(*, include_hidden=False, lifecycle: str = 'available') -> list[dict[str, Any]]:
    data = catalog()
    if include_hidden or lifecycle == 'all':
        return data
    return [x for x in data if x['lifecycle'] == lifecycle and x.get('enabled', True)]


def script_path(tool: dict[str, Any]) -> Path:
    if tool.get('origin') == 'extension':
        path = Path(tool['executable']).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f'Extension executable is missing: {path}')
        return path
    name = tool['id']
    if '/' in name or '\\' in name or name in ('.', '..'):
        raise ValueError('Invalid tool name')
    path = ORIGINALS / name
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError(f'Script is not bundled: {name}')
    return path


def actions_for(tool_id: str) -> tuple[Action, ...]:
    if tool_id.startswith('user-'):
        tool = resolve_tool(tool_id)
        if tool.get('origin') == 'extension':
            return tuple(Action(a['key'], a['label'],
                                tuple(Field(f['key'], f['label'], f['kind'],
                                            f['default'], f['required'])
                                      for f in a['fields']),
                                a['severity'], a['note'], tuple(a['argv']))
                         for a in tool['actions'])
    return ACTION_MAP.get(tool_id, ())


def extension_arguments(action: Action, values: dict[str, Any]) -> list[str]:
    """Build argv from fixed tokens and named fields, with no shell expansion."""
    result = []
    for token in action.argv:
        if isinstance(token, str):
            result.append(token)
        else:
            key = token['field']
            field = next(f for f in action.fields if f.key == key)
            value = values.get(key, '')
            if field.kind == 'boolean':
                if bool(value) and token.get('flag'):
                    result.append(token['flag'])
            elif str(value).strip():
                if token.get('flag'):
                    result.append(token['flag'])
                result.append(str(value).strip())
    return result


def build_command(tool: dict[str, Any], action: Action, values: dict[str, Any]) -> list[str]:
    """Pure argument builder. Never invoke a shell or execute during UI selection."""
    required = [f for f in action.fields if f.required and not str(values.get(f.key, '')).strip()]
    if required:
        raise ValueError('Required: ' + ', '.join(f.label for f in required))
    for field in action.fields:
        if field.kind in ('file', 'folder', 'file_or_folder'):
            value = str(values.get(field.key, '')).strip()
            if value:
                path = Path(value).expanduser()
                if not path.exists():
                    raise ValueError(f'Path does not exist: {path}')
                if field.kind == 'file' and not path.is_file():
                    raise ValueError(f'Select a file: {path}')
                if field.kind == 'folder' and not path.is_dir():
                    raise ValueError(f'Select a folder: {path}')
                if field.key == 'output' and field.kind == 'folder' and not path.is_dir():
                    raise ValueError('The output directory must already exist')
    if tool.get('origin') == 'extension':
        return extension_arguments(action, values)
    id_, key = tool['id'], action.key
    v = lambda k: str(values.get(k, '')).strip()
    if id_ == 'extract_pdf_images.py':
        out = [v('source')]
        # Avoid writing into an arbitrary desktop-launch working directory.
        source = Path(v('source')).expanduser()
        output = v('output') or str((source if source.is_dir() else source.parent) / 'extracted_images')
        out += ['--output', output]
        if values.get('duplicates'): out += ['--include-duplicates']
        return out
    if id_ == 'archive-folder-to-trash':
        return [v('source')] + ([v('output')] if v('output') else [])
    if id_ == 'andrew-lan-speed-test.sh':
        return {'link': [], 'client': [v('peer')], 'server': ['--server'], 'cable': ['--cable-test']}[key]
    if id_ == 'anki-time-travel.sh': return [v('pdf')]
    if id_ == 'categorize-posts-by-keyword':
        return (['--dry-run', v('keyword')] if key == 'preview'
                else ['--yes', v('keyword'), v('category')])
    if id_ == 'create-subject-page.sh':
        parts = [x.strip() for x in v('subjects').split(',') if x.strip()]
        if not parts: raise ValueError('Enter at least one subject name')
        return parts
    if id_ == 'wordpress_diagnose_today.sh':
        return ['--output-dir', v('output')] if v('output') else []
    if id_ == 'unlock_wechat_export': return [v('source')]
    if id_ == 'import_wechat_export':
        return [v('source')] + (['--dry-run'] if key == 'preview' else [])
    if id_ == 'web2menu':
        return [v('url')] + (['--name', v('name')] if v('name') else [])
    if id_ == 'complete_anki_tasks_today.py':
        out = ['--keyword', v('keyword')]
        if v('date'): out += ['--date', v('date')]
        if key == 'preview': out.append('--dry-run')
        return out
    if id_.startswith('thunderbird-'): return []
    raise ValueError(f'No graphical actions are available for {id_}. Read the manual and use the original CLI.')


def command_for(tool: dict[str, Any], arguments: list[str]) -> list[str]:
    if tool.get('lifecycle') == 'removed' or extensions.is_removed(tool['id']):
        raise ValueError('Marked as removed: restore this tool before running')
    if not tool.get('enabled', True) or extensions.is_disabled(tool['id']):
        raise ValueError('Disabled tool: enable it before running')
    return invocation_for(tool, arguments)


def invocation_for(tool: dict[str, Any], arguments: list[str]) -> list[str]:
    """Describe the script invocation without changing its enabled/removed state.

    Display-only callers may use this for disabled/removed tools. Execution
    must continue to use command_for(), which enforces both state checks.
    """
    path = script_path(tool)
    if path.suffix == '.py': return [sys.executable, str(path), *arguments]
    if path.suffix == '.sh' or path.read_bytes()[:30].startswith(b'#!/bin/bash'):
        return ['/bin/bash', str(path), *arguments]
    if os.access(path, os.X_OK): return [str(path), *arguments]
    # Some archive extractors drop executable bits. Respect only known shebangs;
    # never invent an interpreter for pipx/venv wrappers with missing runtimes.
    with path.open('rb') as stream:
        head = stream.readline(256).decode('utf-8', 'replace').strip()
    if head in ('#!/usr/bin/env bash', '#!/bin/bash', '#!/bin/sh'):
        return ['/bin/bash' if 'bash' in head else '/bin/sh', str(path), *arguments]
    if head in ('#!/usr/bin/env python3', '#!/usr/bin/python3'):
        return [sys.executable, str(path), *arguments]
    raise ValueError('The script is not executable or its runtime is missing. See the manual.')


def command_text(argv: list[str]) -> str:
    """Quote arguments exactly as they would appear in a shell."""
    return shlex.join(argv)


def filter_catalog(items: list[dict[str, Any]], *, category_filter: str,
                   status_filter: str, query: str) -> list[dict[str, Any]]:
    """Return matches without mutating any filter or item state."""
    key = query.casefold().strip()
    return [x for x in items
            if (category_filter == 'All' or x['category'] == category_filter)
            and (status_filter == 'All' or display_status(x) == status_filter)
            and key in (x['name'] + ' ' + x['description'] + ' ' + x['id']
                        + ' ' + x['category']).casefold()]


def run_terminal(command: list[str]) -> None:
    """Run scripts in a real terminal, preserving interactive prompts and sudo."""
    # Quote every argument. Never concatenate unescaped user input into shell code.
    payload = 'printf \"%s\\n\" ' + shlex.quote('Command: ' + command_text(command)) + '; ' + command_text(command)
    payload += '; status=$?; printf "\\nExit code: %s\\n" "$status"; read -r -p "Press Enter to close..." _; exit "$status"'
    for candidate in ('x-terminal-emulator', 'mate-terminal', 'gnome-terminal', 'xfce4-terminal', 'konsole', 'xterm'):
        executable = shutil.which(candidate)
        if not executable:
            continue
        if candidate == 'gnome-terminal':
            argv = [executable, '--', 'bash', '-lc', payload]
        elif candidate == 'xfce4-terminal':
            argv = [executable, '--disable-server', '-e', 'bash -lc ' + shlex.quote(payload)]
        else:
            argv = [executable, '-e', 'bash', '-lc', payload]
        subprocess.Popen(argv, start_new_session=True)
        return
    raise RuntimeError('No terminal application was found. Use CLI mode.')


def manual_path(tool: dict[str, Any], *, gui: bool) -> Path:
    if tool.get('origin') == 'extension':
        custom = tool.get('manual')
        if custom:
            path = Path(custom).expanduser()
            if not path.is_file():
                raise FileNotFoundError(f'Extension manual is missing: {path}')
            if (gui and path.suffix.lower() in ('.html', '.htm')) or (not gui and path.suffix.lower() == '.md'):
                return path
            if gui and path.suffix.lower() == '.md' and shutil.which('pandoc'):
                out = _extension_summary_path(tool)
                out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                subprocess.run(['pandoc', '--standalone', '--from=markdown', '--to=html5',
                                str(path), '-o', str(out)], check=True)
                return out
        if gui:
            return _write_extension_summary(tool)
        return Path(custom) if custom and Path(custom).suffix.lower() == '.md' else Path('')
    name = tool['manual']
    doc = (MANUALS_HTML if gui else MANUALS_MD) / (name + ('.html' if gui else '.md'))
    if not doc.is_file(): raise FileNotFoundError(f'Manual not found: {name}')
    return doc


def _extension_summary_path(tool: dict[str, Any]) -> Path:
    base = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache')))
    return base / 'mint-toolbox' / 'manuals' / (tool['id'] + '.html')


def _write_extension_summary(tool: dict[str, Any]) -> Path:
    """Safe, readable offline HTML summary when user did not supply an HTML manual."""
    out = _extension_summary_path(tool)
    out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    escape = html.escape
    action_html = ''.join('<li>' + escape(a['label']) + '</li>' for a in tool.get('actions', []))
    full = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(tool['name'])}</title>
<style>body{{font:17px/1.7 system-ui,sans-serif;max-width:790px;margin:2.5rem auto;
padding:0 1.5rem;color:#20252c;background:#fafafa}}main{{background:white;padding:2rem;
border-radius:12px;border:1px solid #ddd}}h1{{line-height:1.3}}code{{overflow-wrap:anywhere}}
small{{color:#667}}li{{margin:.4em 0}}</style></head><body><main>
<h1>{escape(tool['name'])}</h1><p>{escape(tool['description'])}</p>
<p><small>Category: {escape(tool['category'])} · Status: {escape(LIFECYCLE_NAMES.get(tool['lifecycle'], 'Unknown'))}</small></p>
<h2>Available actions</h2><ul>{action_html or '<li>Read the original documentation for arguments</li>'}</ul>
<h2>Original executable</h2><p><code>{escape(tool['executable'])}</code></p>
<p>This summary is generated automatically. Set an HTML or Markdown manual in the user-tool manifest for a full manual.</p>
</main></body></html>"""
    out.write_text(full, encoding='utf-8')
    out.chmod(0o600)
    return out


def show_manual(tool: dict[str, Any], *, gui: bool) -> None:
    if gui:
        webbrowser.open(manual_path(tool, gui=True).as_uri())
    else:
        if tool.get('origin') == 'extension' and not tool.get('manual'):
            print(f"\n{tool['name']}\n{tool['description']}\nPath: {tool['executable']}")
            return
        doc = manual_path(tool, gui=False)
        if not doc.is_file() or doc.suffix.lower() not in ('.md', '.html', '.htm'):
            print(f"{tool['name']}: {tool['description']}")
        elif doc.suffix.lower() in ('.html', '.htm'):
            if shutil.which('xdg-open') and (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
                subprocess.Popen(['xdg-open', str(doc)])
            else:
                print(f'HTML manual: {doc} (open in a graphical session)')
        elif shutil.which('glow'):
            subprocess.run(['glow', '-p', str(doc)], check=False)
        elif shutil.which('less'):
            subprocess.run(['less', str(doc)], check=False)
        else:
            print(doc.read_text(encoding='utf-8'))


def resolve_tool(name: str) -> dict[str, Any]:
    for tool in catalog():
        if tool['id'] == name:
            return tool
    raise ValueError(f'Tool not found: {name}')


def choose_path_gui(kind: str, parent) -> str:
    if shutil.which('zenity'):
        args = ['zenity', '--file-selection', '--title=Select ' + ('folder' if kind == 'folder' else 'file')]
        if kind == 'folder': args += ['--directory']
        completed = subprocess.run(args, capture_output=True, text=True, check=False)
        return completed.stdout.strip() if completed.returncode == 0 else ''
    from tkinter import filedialog
    if kind == 'folder': return filedialog.askdirectory(parent=parent) or ''
    return filedialog.askopenfilename(parent=parent) or ''


def _input_dialog(parent, action: Action) -> dict[str, Any] | None:
    import tkinter as tk
    from tkinter import ttk
    if not action.fields: return {}
    win = tk.Toplevel(parent)
    win.title(action.label)
    win.transient(parent)
    win.grab_set()
    win.resizable(False, False)
    frame = ttk.Frame(win, padding=16)
    frame.grid(sticky='nsew')
    values: dict[str, Any] = {}
    widgets: dict[str, Any] = {}
    for index, field in enumerate(action.fields):
        ttk.Label(frame, text=field.label).grid(row=index, column=0, padx=(0, 8), pady=6, sticky='w')
        if field.kind == 'boolean':
            var = tk.BooleanVar(value=False)
            ttk.Checkbutton(frame, text='Yes', variable=var).grid(row=index, column=1, sticky='w')
        else:
            var = tk.StringVar(value=field.default)
            ttk.Entry(frame, textvariable=var, width=43).grid(row=index, column=1, pady=6, sticky='ew')
            if field.kind in ('file', 'folder', 'file_or_folder'):
                def browse(f=field, v=var):
                    if f.kind == 'file_or_folder':
                        from tkinter import messagebox
                        select_folder = messagebox.askyesno('Select input type', 'Select an entire folder?', parent=win)
                        chosen = choose_path_gui('folder' if select_folder else 'file', win)
                    else: chosen = choose_path_gui(f.kind, win)
                    if chosen: v.set(chosen)
                ttk.Button(frame, text='Browse...', command=browse).grid(row=index, column=2, padx=(8, 0))
        widgets[field.key] = var
    holder: list[dict[str, Any] | None] = [None]
    def accept():
        holder[0] = {field.key: widgets[field.key].get() for field in action.fields}
        win.destroy()
    buttons = ttk.Frame(frame)
    buttons.grid(row=len(action.fields), column=0, columnspan=3, sticky='e', pady=(16, 0))
    ttk.Button(buttons, text='Cancel', command=win.destroy).pack(side='right', padx=(8, 0))
    ttk.Button(buttons, text='Continue', command=accept).pack(side='right')
    win.bind('<Escape>', lambda _event: win.destroy())
    win.protocol('WM_DELETE_WINDOW', win.destroy)
    win.wait_window()
    return holder[0]


def _approved_gui(parent, tool, action: Action, argv: list[str]) -> bool:
    from tkinter import messagebox, simpledialog
    if action.severity == 'low': return True
    details = action.note or tool['description']
    description = f'{action.label}\n\n{details}\n\nOriginal script command: \n{shlex.join(argv)}'
    if action.severity in ('high', 'critical'):
        answer = simpledialog.askstring('Confirm data-changing action', description + '\n\nType RUN to confirm', parent=parent)
        return answer == 'RUN'
    return messagebox.askyesno('Confirm action', description + '\n\nContinue?', parent=parent)


def launch_gui() -> int:
    import tkinter as tk
    from tkinter import ttk, messagebox
    root = tk.Tk()
    root.title('Mint Toolbox v0.4.0')
    root.geometry('1100x740')
    root.minsize(900, 600)
    style = ttk.Style(root)
    if 'clam' in style.theme_names(): style.theme_use('clam')
    holder = ttk.Frame(root, padding=18)
    holder.pack(fill='both', expand=True)
    ttk.Label(holder, text='Toolbox', font=('Sans', 19, 'bold')).pack(anchor='w')
    ttk.Label(holder, text='Choose a task. Existing script capabilities and CLI arguments are preserved.').pack(anchor='w', pady=(0, 13))
    search_var = tk.StringVar()
    row = ttk.Frame(holder)
    row.pack(fill='x', pady=(0, 10))
    ttk.Label(row, text='Search').pack(side='left', padx=(0, 8))
    search = ttk.Entry(row, textvariable=search_var)
    search.pack(side='left', fill='x', expand=True)
    categories = ['All'] + sorted({x['category'] for x in catalog()})
    category = tk.StringVar(value='All')
    ttk.Label(row, text='Category').pack(side='left', padx=(12, 4))
    category_box = ttk.Combobox(row, state='readonly', values=categories,
                                textvariable=category, width=18)
    category_box.pack(side='left')
    status = tk.StringVar(value='Available')
    ttk.Label(row, text='Status').pack(side='left', padx=(12, 4))
    status_box = ttk.Combobox(row, state='readonly',
                              values=['Available', 'Disabled', 'External dependency', 'Archived', 'Removed', 'Missing file', 'All'],
                              textvariable=status, width=10)
    status_box.pack(side='left')
    toolbar = ttk.Frame(holder)
    toolbar.pack(fill='x', pady=(0, 9))
    count_label = ttk.Label(holder, text='')
    count_label.pack(anchor='w', pady=(0, 5))

    content = ttk.Panedwindow(holder, orient='horizontal')
    content.pack(fill='both', expand=True)
    left = ttk.Frame(content)
    right = ttk.Frame(content, padding=(18, 6, 4, 4))
    content.add(left, weight=2)
    content.add(right, weight=3)
    listbox = tk.Listbox(left, font=('Sans', 11), activestyle='none', exportselection=False)
    scroll = ttk.Scrollbar(left, orient='vertical', command=listbox.yview)
    listbox.configure(yscrollcommand=scroll.set)
    listbox.pack(side='left', fill='both', expand=True)
    scroll.pack(side='right', fill='y')
    name = ttk.Label(right, font=('Sans', 16, 'bold'), wraplength=400)
    name.pack(anchor='w', pady=(0, 8))
    desc = ttk.Label(right, wraplength=420, justify='left')
    desc.pack(anchor='w', pady=(0, 12))
    risk = ttk.Label(right, wraplength=420)
    risk.pack(anchor='w', pady=(0, 12))
    command_header = ttk.Frame(right)
    command_header.pack(fill='x', pady=(0, 4))
    ttk.Label(command_header, text='Full command (selectable and copyable)', font=('Sans', 10, 'bold')).pack(side='left')
    current_command = tk.StringVar(value='Select a tool')
    def copy_command():
        text = current_command.get()
        if text and not text.startswith('Cannot generate') and text != 'Select a tool':
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update_idletasks()
    ttk.Button(command_header, text='Copy command', command=copy_command).pack(side='right')
    command_box = tk.Text(right, height=3, wrap='char', font=('Monospace', 9),
                          relief='flat', padx=6, pady=5)
    command_box.pack(fill='x', pady=(0, 8))
    def display_command(command: str):
        current_command.set(command)
        command_box.configure(state='normal')
        command_box.delete('1.0', tk.END)
        command_box.insert('1.0', command)
        command_box.configure(state='disabled')
    display_command('Select a tool')
    ttk.Separator(right).pack(fill='x', pady=(4, 12))
    ttk.Label(right, text='Available actions', font=('Sans', 11, 'bold')).pack(anchor='w', pady=(0, 8))
    operations = ttk.Frame(right)
    operations.pack(fill='x')
    bottom = ttk.Frame(right)
    bottom.pack(side='bottom', fill='x', pady=(20, 0))
    displayed: list[dict[str, Any]] = []
    selected: list[dict[str, Any] | None] = [None]

    def choose_action(tool: dict[str, Any], action: Action):
        vals = _input_dialog(root, action)
        if vals is None: return
        try:
            cmd = command_for(tool, build_command(tool, action, vals))
        except (OSError, ValueError) as exc:
            messagebox.showerror('Cannot run command', str(exc), parent=root)
            return
        # Show the exact final command even for low-risk operations.
        display_command(command_text(cmd))
        if not _approved_gui(root, tool, action, cmd): return
        try:
            run_terminal(cmd)
        except (OSError, RuntimeError) as exc:
            messagebox.showerror('Cannot open terminal', str(exc), parent=root)

    def render_tool(tool: dict[str, Any], *, outside_filter: bool = False):
        for child in operations.winfo_children(): child.destroy()
        selected[0] = tool
        name.configure(text=tool['name'])
        desc.configure(text=tool['description'])
        current = detailed_status(tool)
        origin = 'User tools' if tool['origin'] == 'extension' else 'Built-in tool'
        risk.configure(text=f"Category: {tool['category']}     Status: {current}     Source: {origin}     Risk: {tool['risk']}")
        try:
            display_command(command_text(invocation_for(tool, [])))
        except (OSError, ValueError) as exc:
            display_command('Cannot generate the full command: ' + str(exc))
        if outside_filter:
            ttk.Label(operations, text='The tool status changed. Your filters were preserved. '
                      'This tool is outside the current results but can still be managed here.',
                      wraplength=420).pack(anchor='w', pady=(0, 7))
        acts = actions_for(tool['id']) if tool['lifecycle'] == 'available' and tool['enabled'] else ()
        if acts:
            for a in acts:
                ttk.Button(operations, text=a.label, command=lambda a=a, t=tool: choose_action(t, a)).pack(fill='x', pady=4)
        elif not tool['enabled'] and tool['lifecycle'] == 'available':
            ttk.Label(operations, text='This tool is disabled. Its manual remains available. Enable it to run it again.',
                      wraplength=420).pack(anchor='w')
        elif tool['lifecycle'] != 'available':
            ttk.Label(operations, text='This entry is available for reference only and cannot be launched here.',
                      wraplength=420).pack(anchor='w')
        else:
            ttk.Label(operations, text='This tool needs a dedicated environment or CLI arguments. Read the manual first.',
                      wraplength=420).pack(anchor='w')
        update_buttons()

    def show_tool(_event=None):
        if not listbox.curselection(): return
        index = listbox.curselection()[0]
        if index >= len(displayed): return
        render_tool(displayed[index])

    def update_buttons():
        tool = selected[0]
        mark_button.configure(state='normal' if tool and tool['lifecycle'] != 'removed' else 'disabled')
        restore_button.configure(state='normal' if tool and tool['lifecycle'] == 'removed' else 'disabled')
        delete_button.configure(state='normal' if tool and tool['origin'] == 'extension' else 'disabled')
        toggle_button.configure(text=('Disable tool' if tool and tool['enabled'] else 'Enable tool'),
                                state='normal' if tool else 'disabled')

    def redraw(*_args, keep_selected: bool = False):
        nonlocal displayed
        # Never write category/status/search here. User filters are independent
        # of lifecycle mutations and must stay exactly as the user selected.
        old_id = selected[0]['id'] if selected[0] else None
        all_tools = catalog()
        category_box.configure(values=['All'] + sorted({x['category'] for x in all_tools}))
        displayed = filter_catalog(all_tools, category_filter=category.get(),
                                   status_filter=status.get(), query=search_var.get())
        listbox.delete(0, tk.END)
        for x in displayed:
            listbox.insert(tk.END, x['name'] + ('  · Disabled' if not x['enabled'] else ''))
        count_label.configure(text=f'Matching tools: {len(displayed)}. Status changes preserve filters.')
        index = next((i for i, x in enumerate(displayed) if x['id'] == old_id), None)
        if index is not None:
            listbox.selection_set(index)
            listbox.see(index)
            render_tool(displayed[index])
            return
        if keep_selected and old_id:
            old_tool = next((x for x in all_tools if x['id'] == old_id), None)
            if old_tool:
                render_tool(old_tool, outside_filter=True)
                return
        # Never auto-select an unrelated tool after a status change or deletion.
        selected[0] = None
        name.configure(text='Select a tool' if displayed else 'No matching tools')
        desc.configure(text='Adjust the filters as needed. Status changes never reset them.')
        risk.configure(text='')
        display_command('Select a tool')
        for child in operations.winfo_children(): child.destroy()
        update_buttons()

    def add_custom():
        path = choose_path_gui('file', root)
        if not path: return
        default = Path(path).stem
        dialog = tk.Toplevel(root)
        dialog.title('Add user tool')
        dialog.transient(root)
        dialog.grab_set()
        dialog.resizable(False, False)
        panel = ttk.Frame(dialog, padding=18)
        panel.pack(fill='both', expand=True)
        name_var = tk.StringVar(value=default)
        category_var = tk.StringVar(value='User tools')
        desc_var = tk.StringVar(value=f'Run {default}')
        manual_var = tk.StringVar()
        fields = (('Name',name_var), ('Category',category_var), ('Description',desc_var))
        for i,(title,var) in enumerate(fields):
            ttk.Label(panel,text=title).grid(row=i,column=0,sticky='w',pady=6,padx=(0,10))
            if title == 'Category':
                ttk.Combobox(panel,textvariable=var,values=sorted({t['category'] for t in catalog()} | {'User tools'}),
                             width=42).grid(row=i,column=1,sticky='ew',pady=6)
            else:
                ttk.Entry(panel,textvariable=var,width=45).grid(row=i,column=1,sticky='ew',pady=6)
        ttk.Label(panel,text='Manual (optional)').grid(row=3,column=0,sticky='w',pady=6)
        ttk.Entry(panel,textvariable=manual_var).grid(row=3,column=1,sticky='ew',pady=6)
        def select_manual():
            chosen = choose_path_gui('file',dialog)
            if chosen: manual_var.set(chosen)
        ttk.Button(panel,text='Browse...',command=select_manual).grid(row=3,column=2,padx=(8,0))
        ttk.Label(panel,text='The original file is not copied, deleted, or modified. Unregister it at any time.',
                  foreground='#666').grid(row=4,column=0,columnspan=3,sticky='w',pady=(10,4))
        buttons = ttk.Frame(panel)
        buttons.grid(row=5,column=0,columnspan=3,sticky='e',pady=(12,0))
        holder = [None]
        def accept():
            holder[0] = (name_var.get().strip(),category_var.get().strip(),
                         desc_var.get().strip(),manual_var.get().strip())
            dialog.destroy()
        ttk.Button(buttons,text='Cancel',command=dialog.destroy).pack(side='right',padx=(8,0))
        ttk.Button(buttons,text='Add tool',command=accept).pack(side='right')
        dialog.bind('<Escape>',lambda _e:dialog.destroy())
        dialog.wait_window()
        if holder[0] is None: return
        name_text,category_text,desc_text,manual_file = holder[0]
        try:
            created = extensions.add_extension(path,name=name_text or default,
                         category=category_text or 'User tools',
                         description=desc_text or f'Run {default}',
                         manual=manual_file or None)
        except (OSError, ValueError) as exc:
            messagebox.showerror('Cannot add tool',str(exc),parent=root)
            return
        # Adding a tool must not reset or silently adjust the user's filters.
        redraw(keep_selected=True)
        messagebox.showinfo('Added', 'Tool registered. The original file was not modified.',parent=root)

    def toggle_disabled():
        tool = selected[0]
        if not tool: return
        disabled = tool['enabled']
        try:
            extensions.set_disabled(tool['id'], disabled)
        except (OSError, ValueError) as exc:
            messagebox.showerror('Cannot save enabled state', str(exc), parent=root)
            return
        redraw(keep_selected=True)

    def change_removed(removed: bool):
        tool = selected[0]
        if not tool: return
        if removed and not messagebox.askyesno('Mark as removed',
                f'Move {tool["name"]} to the removed category?\n\nScripts and manuals will not be deleted.', parent=root):
            return
        try:
            extensions.mark_removed(tool['id'], removed)
        except (OSError, ValueError) as exc:
            messagebox.showerror('Cannot save state', str(exc), parent=root)
            return
        redraw(keep_selected=True)

    def remove_custom():
        tool = selected[0]
        if not tool or tool['origin'] != 'extension': return
        if not messagebox.askyesno('Remove user tool', f'Unregister {tool["name"]}？\n\nThe original script and manual will not be deleted.', parent=root):
            return
        try:
            extensions.remove_extension(tool['id'])
            extensions.mark_removed(tool['id'], False)
        except (OSError, ValueError) as exc:
            messagebox.showerror('Removal failed', str(exc), parent=root)
            return
        redraw(keep_selected=True)

    ttk.Button(toolbar, text='System extensions...', command=lambda: system_plugins.show_gui(root)).grid(row=0, column=0, padx=4, pady=3, sticky='ew')
    ttk.Button(toolbar, text='+ Add user tool...', command=add_custom).grid(row=0, column=1, padx=4, pady=3, sticky='ew')
    toggle_button = ttk.Button(toolbar, text='Disable tool', command=toggle_disabled)
    toggle_button.grid(row=0, column=2, padx=4, pady=3, sticky='ew')
    delete_button = ttk.Button(toolbar, text='Unregister', command=remove_custom)
    delete_button.grid(row=1, column=0, padx=4, pady=3, sticky='ew')
    restore_button = ttk.Button(toolbar, text='Restore', command=lambda: change_removed(False))
    restore_button.grid(row=1, column=1, padx=4, pady=3, sticky='ew')
    mark_button = ttk.Button(toolbar, text='Mark as removed', command=lambda: change_removed(True))
    mark_button.grid(row=1, column=2, padx=4, pady=3, sticky='ew')

    for column in range(3):
        toolbar.columnconfigure(column, weight=1)

    def view_help():
        tool = selected[0]
        if tool:
            try: show_manual(tool, gui=True)
            except (OSError, subprocess.CalledProcessError) as exc: messagebox.showerror('Cannot open manual', str(exc), parent=root)

    ttk.Button(bottom, text='Read illustrated manual', command=view_help).pack(side='left')
    ttk.Button(bottom, text='Close', command=root.destroy).pack(side='right')
    listbox.bind('<<ListboxSelect>>', show_tool)
    search_var.trace_add('write', redraw)
    category.trace_add('write', redraw)
    status.trace_add('write', redraw)
    redraw()
    search.focus_set()
    root.mainloop()
    return 0


def cli_action(tool: dict[str, Any], action: Action) -> int:
    print(f'\n{tool["name"]} — {action.label}')
    if action.note: print('Note: ', action.note)
    values = {}
    for field in action.fields:
        default = f' [{field.default}]' if field.default else ''
        value = input(f'{field.label}{default}: ').strip()
        values[field.key] = (value or field.default) if field.kind != 'boolean' else value.lower() in ('y', 'yes', '1', 'Yes')
    try:
        argv = command_for(tool, build_command(tool, action, values))
    except (ValueError, OSError) as exc:
        print('Error: ', exc, file=sys.stderr)
        return 1
    print('Command: ', command_text(argv), flush=True)
    if action.severity in ('high', 'critical'):
        if input('This action modifies data. Type RUN to confirm: ').strip() != 'RUN':
            print('Cancelled')
            return 0
    elif action.severity == 'medium':
        if input('Continue? [y/N]: ').strip().lower() != 'y': return 0
    return subprocess.run(argv, check=False).returncode


def launch_tui() -> int:
    print('\nMint Toolbox (terminal mode)')
    active_only = True
    while True:
        visible = entries() if active_only else entries(include_hidden=True)
        for i, tool in enumerate(visible, 1):
            tag = '' if detailed_status(tool) == 'Available' else f" [{detailed_status(tool)}]"
            print(f'{i:2}. {tool["name"]}{tag}')
        choice = input('\nNumber: select; /text: search; a: add; s: toggle archived; q: quit: ').strip()
        if choice.lower() == 's':
            active_only = not active_only
            continue
        if choice.lower() == 'a':
            file = input('Full script or executable path (Enter to cancel): ').strip()
            if file:
                try:
                    extension = extensions.add_extension(file)
                    print('User tool registered: ', extension['name'])
                except (OSError, ValueError) as exc:
                    print('Could not add tool: ', exc)
            continue
        if choice in ('q', 'Q', '0'): return 0
        if choice.startswith('/'):
            term = choice[1:].casefold()
            visible = [x for x in visible if term in (x['name']+' '+x['description']).casefold()]
            for i, t in enumerate(visible, 1): print(f' {i}. {t["name"]}')
            if not visible: continue
            choice = input('Select a number or press Enter to return: ').strip()
        try:
            tool = visible[int(choice)-1]
        except (IndexError, ValueError):
            print('Invalid selection')
            continue
        print(f'\n{tool["name"]}\n{tool["description"]}\nRisk: {tool["risk"]}')
        try:
            print('Original command: ', command_text(invocation_for(tool, [])))
        except (OSError, ValueError) as exc:
            print('Command unavailable: ', exc)
        actions = actions_for(tool['id']) if tool['lifecycle'] == 'available' and tool['enabled'] else ()
        for i, action in enumerate(actions, 1): print(f'{i}. {action.label}')
        print('h. Read formatted manual')
        print('e. ' + ('Disable tool' if tool['enabled'] else 'Enable tool'))
        print('r. ' + ('Restore tool' if tool['lifecycle'] == 'removed' else 'Mark as removed'))
        act = input('Select an action (Enter to return): ').strip()
        if act.lower() == 'h': show_manual(tool, gui=False)
        elif act.lower() == 'e':
            extensions.set_disabled(tool['id'], tool['enabled'])
            print('Disabled' if tool['enabled'] else 'Enabled')
        elif act.lower() == 'r':
            removed = tool['lifecycle'] != 'removed'
            if not removed or input('Mark as removed (keep original files)? [y/N]: ').strip().lower() == 'y':
                extensions.mark_removed(tool['id'], removed)
                print('Marked as removed' if removed else 'Restored')
        elif act.isdigit() and 1 <= int(act) <= len(actions): cli_action(tool, actions[int(act)-1])


def main(argv: list[str] | None = None) -> int:
    raw = sys.argv[1:] if argv is None else list(argv)
    # Exact CLI compatibility: --run TOOL receives ALL trailing flags unchanged,
    # including --help and --output (argparse would otherwise consume them).
    if raw[:1] == ['--run']:
        if len(raw) < 2:
            print('Usage: mint-toolbox --run TOOL [original script arguments...]', file=sys.stderr)
            return 2
        try:
            tool = resolve_tool(raw[1])
            arguments = raw[2:]
            if arguments[:1] == ['--']:
                arguments = arguments[1:]
            cmd = command_for(tool, arguments)
            print('Command: ', command_text(cmd), file=sys.stderr, flush=True)
            result = subprocess.run(cmd, check=False)
            print('Exit code:', result.returncode, flush=True)
            return result.returncode
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as exc:
            print('Error: ', exc, file=sys.stderr)
            return 1
    p = argparse.ArgumentParser(description='Mint Toolbox — graphical integrated utility set')
    p.add_argument('--plugins', action='store_true', help='open system extension manager')
    p.add_argument('--plugin-list', action='store_true', help='show installed deb extension status')
    plugin_operation = p.add_mutually_exclusive_group()
    plugin_operation.add_argument('--plugin-build', metavar='ID', choices=[p['id'] for p in system_plugins.plugins()], help='build the pinned source as a regular user and install the generated deb')
    plugin_operation.add_argument('--plugin-enable', metavar='ID', choices=[p['id'] for p in system_plugins.plugins()])
    plugin_operation.add_argument('--plugin-disable', metavar='ID', choices=[p['id'] for p in system_plugins.plugins()])
    p.add_argument('--gui', action='store_true', help='use graphical tool window')
    p.add_argument('--tui', action='store_true', help='use terminal mode')
    p.add_argument('--list', action='store_true', help='list available tools')
    p.add_argument('--all', action='store_true', help='include removed, archived and unavailable tools with --list')
    p.add_argument('--categories', action='store_true', help='show tool categories')
    p.add_argument('--extensions', action='store_true', help='list user extensions and manifest errors')
    p.add_argument('--extension-add', metavar='FILE', help='register script using local user extension slot')
    p.add_argument('--extension-remove', metavar='ID', help='unregister extension; source file stays untouched')
    p.add_argument('--name', help='name for --extension-add')
    p.add_argument('--category', default='User tools', help='category for --extension-add')
    p.add_argument('--description', help='description for --extension-add')
    p.add_argument('--extension-manual', metavar='FILE', help='optional manual path for --extension-add')
    p.add_argument('--disable', metavar='ID', help='disable a tool without deleting it or its manual')
    p.add_argument('--enable', metavar='ID', help='re-enable a disabled tool')
    p.add_argument('--mark-removed', metavar='ID', help='hide a tool as removed (retain its files)')
    p.add_argument('--restore', metavar='ID', help='restore a marked-removed tool')
    p.add_argument('--info', metavar='ID', help='show tool details')
    p.add_argument('--manual', metavar='ID', help='open a tool manual')
    p.add_argument('--run', metavar='ID', help='execute original tool in CLI mode')
    args = p.parse_args(argv)
    try:
        if args.plugins:
            system_plugins.show_gui()
            return 0
        if args.plugin_list:
            for item in system_plugins.plugins():
                print(item['id'], item['name'], system_plugins.state_text(item['package']), sep='\t')
            return 0
        if args.plugin_build:
            system_plugins.change(args.plugin_build, True, from_source=True)
            return 0
        if args.plugin_enable or args.plugin_disable:
            key = args.plugin_enable or args.plugin_disable
            system_plugins.change(key, bool(args.plugin_enable))
            print('Enabled' if args.plugin_enable else 'Disabled', key)
            return 0
        if args.list:
            for x in entries(include_hidden=args.all):
                print(f"{x['id']}\t{x['name']}\t{x['category']}\t{detailed_status(x)}")
            return 0
        if args.categories:
            for cat in sorted({x['category'] for x in catalog()}):
                print(cat)
            return 0
        if args.extensions:
            rows, errors = extensions.load_extensions()
            for x in rows:
                print(f"{x['id']}\t{x['name']}\t{x['category']}\t{display_status(resolve_tool(x['id']))}")
            for error in errors:
                print('Invalid user tool: '+error, file=sys.stderr)
            return 0 if not errors else 1
        if args.extension_add:
            created = extensions.add_extension(args.extension_add, name=args.name,
                      category=args.category, description=args.description,
                      manual=args.extension_manual)
            print(f"Registered: {created['id']}")
            return 0
        if args.extension_remove:
            target = resolve_tool(args.extension_remove)
            if target['origin'] != 'extension':
                raise ValueError('Built-in tools cannot be unregistered; mark them as removed instead')
            extensions.remove_extension(target['id'])
            return 0
        if args.disable or args.enable:
            target = args.disable or args.enable
            resolve_tool(target)
            extensions.set_disabled(target, bool(args.disable))
            print('Disabled (tool, settings, and manual retained)' if args.disable else 'Enabled (removed/archived state preserved)')
            return 0
        if args.mark_removed:
            resolve_tool(args.mark_removed)
            extensions.mark_removed(args.mark_removed, True)
            print('Marked as removed (script and manual retained)')
            return 0
        if args.restore:
            resolve_tool(args.restore)
            extensions.mark_removed(args.restore, False)
            print('Entry restored')
            return 0
        if args.info:
            x = resolve_tool(args.info)
            print(f'{x["name"]}\n{x["description"]}\nCategory: {x["category"]}\nRisk: {x["risk"]}\nStatus: {detailed_status(x)}')
            try:
                print('Original command: ', command_text(invocation_for(x, [])))
            except (OSError, ValueError) as exc:
                print('Command unavailable: ', exc)
            print('Toolbox CLI: ', command_text(['mint-toolbox', '--run', x['id']]), '[original script arguments...]')
            return 0
        if args.manual:
            show_manual(resolve_tool(args.manual), gui=bool(os.environ.get('DISPLAY')))
            return 0
        if args.run:
            x = resolve_tool(args.run)
            # Execute exactly as the original CLI, no GUI translations.
            cmd = command_for(x, [])
            print('Command: ', command_text(cmd), file=sys.stderr, flush=True)
            result = subprocess.run(cmd, check=False)
            print('Exit code:', result.returncode, flush=True)
            return result.returncode
        if args.tui: return launch_tui()
        if args.gui or os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'):
            try: return launch_gui()
            except (ImportError, OSError) as exc:
                if args.gui: raise
                print('GUI unavailable; using terminal mode: ', exc, file=sys.stderr)
        return launch_tui()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as exc:
        print('Error: ', exc, file=sys.stderr)
        return 1

if __name__ == '__main__':
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        print('\nCancelled')
        sys.exit(130)
