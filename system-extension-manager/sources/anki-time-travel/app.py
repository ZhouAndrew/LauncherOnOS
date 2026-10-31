#!/usr/bin/python3
"""Installed CLI and desktop entry point for historical Anki PDF imports."""
import argparse
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import tempfile

from execution import LogPanel, OperationLog

ROOT = Path(__file__).resolve().parent
DEFAULT_WP = '/var/www/html/wordpress'
IMPORT_SCRIPT = ROOT / 'anki-time-travel.sh'


def config_path():
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'anki-time-travel/settings.json'


def wordpress_path(explicit=None):
    if explicit:
        return Path(explicit).expanduser().absolute()
    if os.environ.get('WP_PATH'):
        return Path(os.environ['WP_PATH']).expanduser().absolute()
    try:
        saved = json.loads(config_path().read_text())
        return Path(saved['wordpress_path']).expanduser().absolute()
    except FileNotFoundError:
        return Path(DEFAULT_WP)


def save_settings(path):
    target = config_path()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary_name = tempfile.mkstemp(prefix='.settings-', dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump({'wordpress_path': str(path)}, stream)
            stream.write('\n')
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def check_environment(site):
    if not shutil.which('wp'):
        raise ValueError('WP-CLI (wp) was not found in PATH. Install WP-CLI before importing.')
    if not (site / 'wp-config.php').is_file():
        raise ValueError('Select the WordPress root containing wp-config.php: ' + str(site))
    if not IMPORT_SCRIPT.is_file():
        raise ValueError('The installed import script is missing. Reinstall the package.')


def run_import(files, site, log):
    files = [str(Path(file).expanduser().absolute()) for file in files]
    if not files:
        raise ValueError('Select at least one PDF file')
    check_environment(site)
    log.stage('Importing historical PDFs into WordPress')
    # Bash preflights all inputs and handles WordPress timestamps and readback.
    log.run(['/bin/bash', str(IMPORT_SCRIPT), *files], env={'WP_PATH': str(site)})
    log.stage('Import and verification completed')


def choose_files():
    import tkinter as tk
    import native_dialogs as filedialog
    window = tk.Tk()
    window.withdraw()
    try:
        return list(filedialog.askopenfilenames(parent=window, title='Select historical Anki PDFs',
                    filetypes=[('PDF files', '*.pdf'), ('All files', '*')]))
    finally:
        window.destroy()


def show_gui(files=(), site=None, parent=None):
    import tkinter as tk
    from tkinter import ttk, messagebox
    import native_dialogs as filedialog
    window = tk.Toplevel(parent) if parent is not None else tk.Tk()
    window.title('Anki Time Travel - PDF to WordPress')
    window.geometry('980x720')
    window.minsize(760, 560)
    holder = ttk.Frame(window, padding=12)
    holder.pack(fill='both', expand=True)
    ttk.Label(holder, text='Historical Anki PDFs to WordPress', font=('Sans', 17, 'bold')).pack(anchor='w')
    ttk.Label(holder, text='Uses the filename timestamp; publishes posts and attachments, then verifies the result.').pack(anchor='w', pady=(4, 12))
    wp_row = ttk.Frame(holder)
    wp_row.pack(fill='x')
    ttk.Label(wp_row, text='WordPress root').pack(side='left')
    wp_value = tk.StringVar(value=str(site or wordpress_path()))
    wp_entry = ttk.Entry(wp_row, textvariable=wp_value)
    wp_entry.pack(side='left', fill='x', expand=True, padx=8)
    def browse_site():
        path = filedialog.askdirectory(parent=window, title='Select WordPress root')
        if path:
            wp_value.set(path)
    browse = ttk.Button(wp_row, text='Browse...', command=browse_site)
    browse.pack(side='left')
    listed = ttk.Frame(holder)
    listed.pack(fill='x', pady=10)
    listing = tk.Listbox(listed, height=6, selectmode='extended', exportselection=False)
    scroll = ttk.Scrollbar(listed, command=listing.yview)
    listing.configure(yscrollcommand=scroll.set)
    scroll.pack(side='right', fill='y')
    listing.pack(fill='x', expand=True)
    selected = []
    def add(paths):
        for path in paths:
            absolute = str(Path(path).expanduser().absolute())
            if absolute not in selected:
                selected.append(absolute)
                listing.insert('end', absolute)
    add(files)
    actions = ttk.Frame(holder)
    actions.pack(fill='x', pady=(0, 10))
    def select_pdf():
        add(filedialog.askopenfilenames(parent=window, title='Select historical Anki PDFs',
            filetypes=[('PDF files', '*.pdf'), ('All files', '*')]))
    def remove_pdf():
        for index in reversed(listing.curselection()):
            selected.pop(index)
            listing.delete(index)
    add_button = ttk.Button(actions, text='Add PDFs...', command=select_pdf)
    add_button.pack(side='left')
    remove_button = ttk.Button(actions, text='Remove selected', command=remove_pdf)
    remove_button.pack(side='left', padx=8)
    panel = LogPanel(holder)
    panel.frame.pack(fill='both', expand=True)
    state = tk.StringVar(value='Ready')
    ttk.Label(holder, textvariable=state, wraplength=900).pack(anchor='w', pady=8)
    events = queue.Queue()
    busy = [False]
    result = [0]
    def start():
        paths = list(selected)
        try:
            site = wordpress_path(wp_value.get())
            check_environment(site)
            if not paths:
                raise ValueError('Select at least one PDF file')
        except Exception as exc:
            messagebox.showerror('Cannot start import', str(exc), parent=window)
            return
        if not messagebox.askyesno('Confirm WordPress import',
            f'Import {len(paths)} PDF file(s) into {site}?\n\nThis creates or updates WordPress posts and attachments.', parent=window):
            return
        busy[0] = True
        state.set('Running... Full commands and output are shown below.')
        for widget in controls:
            widget.configure(state='disabled')
        def worker():
            log = None
            error = None
            try:
                save_settings(site)
                log = OperationLog('Anki PDF to WordPress', lambda line: events.put(('line', line)))
                run_import(paths, site, log)
            except Exception as exc:
                error = str(exc)
                if log:
                    log.stage('FAILED: ' + error)
            finally:
                if log:
                    log.close()
                events.put(('done', error))
        threading.Thread(target=worker, daemon=False).start()
    run_button = ttk.Button(actions, text='Import to WordPress', command=start)
    run_button.pack(side='right')
    controls = [add_button, remove_button, run_button, browse, wp_entry]
    def poll():
        try:
            for _ in range(200):
                kind, value = events.get_nowait()
                if kind == 'line':
                    panel.append(value)
                else:
                    busy[0] = False
                    result[0] = 1 if value else 0
                    state.set('Failed: ' + value if value else 'Import completed and verified.')
                    for widget in controls:
                        widget.configure(state='normal')
        except queue.Empty:
            pass
        window.after(75, poll)
    def close():
        if busy[0]:
            messagebox.showinfo('Import running', 'Wait for the import to finish. The log is saved automatically.', parent=window)
        else:
            window.destroy()
    window.protocol('WM_DELETE_WINDOW', close)
    window.after(75, poll)
    if parent is None:
        window.mainloop()
        return result[0]
    return window


def main(argv=None):
    parser = argparse.ArgumentParser(description='Import historical Anki statistics PDFs into WordPress')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--gui', action='store_true', help='open the desktop import window')
    modes.add_argument('--choose', action='store_true', help='choose PDFs on the desktop, then run in this terminal')
    parser.add_argument('--wp-path', metavar='DIR', help='WordPress root (also accepts WP_PATH)')
    parser.add_argument('--check', action='store_true', help='check local requirements without changing WordPress')
    parser.add_argument('pdfs', nargs='*', metavar='PDF')
    args = parser.parse_args(argv)
    try:
        site = wordpress_path(args.wp_path)
        if args.check:
            check_environment(site)
            print('Local requirements found. WordPress root:', site)
            print('No WordPress data was changed.')
            return 0
        if args.gui or (not args.pdfs and not args.choose and (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))):
            return show_gui(args.pdfs, site)
        files = list(args.pdfs)
        if args.choose:
            files.extend(choose_files())
            if not files:
                print('No files selected; nothing changed.')
                return 0
        if not files:
            parser.error('provide PDF paths, use --choose, or open --gui')
        log = OperationLog('Anki PDF to WordPress')
        try:
            run_import(files, site, log)
            return 0
        except Exception as exc:
            log.stage('FAILED: ' + str(exc))
            return 1
        finally:
            log.close()
    except Exception as exc:
        print('Error:', exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
