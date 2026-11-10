"""Real-time command output and persistent, private operation logs."""
from datetime import datetime
import os
from pathlib import Path
import shlex
import shutil
import stat
import subprocess
import tempfile
import threading


def log_directory():
    base = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state')
    return base / 'system-extension-manager/logs'


def new_log_file(prefix):
    folder = log_directory()
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=prefix, suffix='.log', dir=folder)
    return fd, Path(name)


def open_log(path):
    # Skip links and special files, even if an entry changed after listing.
    def opener(name, flags):
        return os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK)

    source = open(path, 'rb', opener=opener)
    if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
        source.close()
        raise ValueError('The log is no longer a regular file: ' + path.name)
    return source


def saved_logs(folder):
    entries = []
    try:
        paths = list(folder.iterdir())
    except FileNotFoundError:
        return entries
    for path in paths:
        if path.suffix != '.log':
            continue
        try:
            metadata = path.lstat()
            if not stat.S_ISREG(metadata.st_mode):
                continue
            with open_log(path) as source:
                header = source.readline(1024).decode('utf-8', errors='replace').strip()
        except (OSError, ValueError):
            continue
        label = 'Security Updates terminal' if path.name.startswith('security-updates-terminal-') else 'Operation log'
        if header.startswith('Operation: '):
            label = header.removeprefix('Operation: ')
        entries.append((path, metadata.st_mtime, label))
    return sorted(entries, key=lambda entry: (entry[1], entry[0].name), reverse=True)


def log_preview(path):
    limit = 512 * 1024
    with open_log(path) as source:
        size = source.seek(0, os.SEEK_END)
        source.seek(max(0, size - limit))
        output = source.read(limit).decode('utf-8', errors='replace')
    if size > limit:
        return 'Showing the last 512 KiB. Save log to export the complete file.\n\n' + output
    return output or 'This log has no output yet. Use Refresh logs to check again.'


def export_log(source, destination):
    if destination.parent.resolve() == source.parent.resolve():
        raise ValueError('Choose a location outside the log history folder.')
    # Use a private copy and replace the destination only after copying succeeds.
    with open_log(source) as log:
        size = os.fstat(log.fileno()).st_size
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as copy:
            temporary = Path(copy.name)
            try:
                while size:
                    chunk = log.read(min(size, shutil.COPY_BUFSIZE))
                    if not chunk:
                        break
                    copy.write(chunk)
                    size -= len(chunk)
                copy.close()
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)


class OperationLog:
    def __init__(self, label, emit=None):
        fd, self.path = new_log_file(datetime.now().strftime('%Y%m%d-%H%M%S-'))
        self.stream = os.fdopen(fd, 'w', encoding='utf-8')
        self.emit = emit or (lambda line: print(line, end='', flush=True))
        self.lock = threading.Lock()
        self.write(f'Operation: {label}\nLog: {self.path}\n')

    def write(self, text):
        with self.lock:
            self.stream.write(text)
            self.stream.flush()
            self.emit(text)

    def stage(self, text):
        self.write(f'\n[{datetime.now().isoformat(timespec="seconds")}] {text}\n')

    def run(self, args, *, cwd=None, check=True, **kwargs):
        args = [str(arg) for arg in args]
        self.write('\n$ ' + shlex.join(args) + '\n')
        if cwd:
            self.write('Working directory: ' + str(cwd) + '\n')
        environment = dict(os.environ, LC_ALL='C.UTF-8', LANG='C.UTF-8', PYTHONUNBUFFERED='1')
        environment.update(kwargs.pop('env', {}))
        chunks = []
        try:
            with subprocess.Popen(args, cwd=cwd, env=environment, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                    bufsize=1, **kwargs) as process:
                for line in process.stdout:
                    self.write(line)
                    chunks.append(line)
                    # Keep exception messages bounded; the complete output is in the log.
                    if len(chunks) > 1000:
                        del chunks[:500]
                code = process.wait()
        except OSError as exc:
            self.write(f'Command could not start: {exc}\n')
            raise
        self.write(f'Exit code: {code}\n')
        output = ''.join(chunks)
        if check and code:
            raise subprocess.CalledProcessError(code, args, output=output)
        return subprocess.CompletedProcess(args, code, output, '')

    def close(self):
        self.stream.close()


class LogPanel:
    def __init__(self, parent, title='Execution log', save_log=None):
        import tkinter as tk
        from tkinter import ttk, messagebox
        import native_dialogs as filedialog
        self.frame = ttk.LabelFrame(parent, text=title)
        controls = ttk.Frame(self.frame)
        controls.pack(side='bottom', fill='x')
        self.text = tk.Text(self.frame, wrap='word', height=13, state='disabled')
        scroll = ttk.Scrollbar(self.frame, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.text.pack(fill='both', expand=True)
        def copy():
            self.text.clipboard_clear()
            self.text.clipboard_append(self.text.get('1.0', 'end-1c'))
        def save():
            path = filedialog.asksaveasfilename(parent=parent, defaultextension='.log',
                                              filetypes=[('Log files', '*.log'), ('All files', '*')])
            if path:
                try:
                    Path(path).write_text(self.text.get('1.0', 'end-1c'), encoding='utf-8')
                except OSError as exc:
                    messagebox.showerror('Could not save log', str(exc), parent=parent)
        self.copy_button = ttk.Button(controls, text='Copy log', command=copy)
        self.copy_button.pack(side='left')
        self.save_button = ttk.Button(controls, text='Save log...', command=save_log or save)
        self.save_button.pack(side='left', padx=6)
        self.controls = controls

    def replace(self, text):
        self.text.configure(state='normal')
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', text)
        self.text.configure(state='disabled')

    def append(self, text):
        self.text.configure(state='normal')
        self.text.insert('end', text)
        self.text.see('end')
        self.text.configure(state='disabled')


def scrollable_tree(frame, tree):
    from tkinter import ttk

    vertical = ttk.Scrollbar(frame, command=tree.yview)
    horizontal = ttk.Scrollbar(frame, orient='horizontal', command=tree.xview)
    tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(0, weight=1)
    tree.grid(row=0, column=0, sticky='nsew')
    vertical.grid(row=0, column=1, sticky='ns')
    horizontal.grid(row=1, column=0, sticky='ew')


def show_log_history(parent):
    import tkinter as tk
    from tkinter import ttk, messagebox
    import native_dialogs

    window = tk.Toplevel(parent, name='log_history')
    window.title('Log History')
    window.geometry('900x590')
    window.minsize(600, 360)
    window.columnconfigure(0, weight=1)
    window.rowconfigure(0, weight=1)
    window.rowconfigure(2, weight=2)
    folder = log_directory()
    columns = ('operation', 'updated', 'file')
    listing = ttk.Frame(window)
    listing.grid(row=0, sticky='nsew', padx=10, pady=(10, 0))
    tree = ttk.Treeview(listing, columns=columns, show='headings', selectmode='browse', height=3)
    for col, title, width in [('operation', 'Operation', 290), ('updated', 'Last written', 155), ('file', 'Log file', 325)]:
        tree.heading(col, text=title)
        tree.column(col, width=width, minwidth=width)
    scrollable_tree(listing, tree)
    status = tk.StringVar(value=str(folder))
    ttk.Entry(window, textvariable=status, state='readonly').grid(row=1, sticky='ew', padx=10, pady=5)

    def selected():
        selection = tree.selection()
        if selection:
            return folder / selection[0]
        return None

    def show_selected(_event=None):
        path = selected()
        status.set(str(path or folder))
        state = 'disabled'
        message = 'No saved logs yet.'
        if path:
            try:
                message = log_preview(path)
                state = 'normal'
            except (OSError, ValueError) as exc:
                message = 'Could not read log: ' + str(exc)
        panel.replace(message)
        panel.copy_button.configure(state=state)
        panel.save_button.configure(state=state)

    def refresh():
        previous = tree.selection()
        try:
            entries = saved_logs(folder)
        except OSError as exc:
            messagebox.showerror('Could not list logs', str(exc), parent=window)
            return
        tree.delete(*tree.get_children())
        for path, modified, label in entries:
            timestamp = datetime.fromtimestamp(modified).strftime('%Y-%m-%d %H:%M:%S')
            tree.insert('', 'end', iid=path.name, values=(label, timestamp, path.name))
        if entries:
            current = previous[0] if previous and tree.exists(previous[0]) else entries[0][0].name
            tree.selection_set(current)
            tree.see(current)
        show_selected()

    def save():
        path = selected()
        if path is None:
            return
        destination = native_dialogs.asksaveasfilename(parent=window, title='Save log',
            initialfile=path.name, defaultextension='.log', filetypes=[('Log files', '*.log'), ('All files', '*')])
        if destination:
            try:
                export_log(path, Path(destination))
            except (OSError, ValueError) as exc:
                messagebox.showerror('Could not save log', str(exc), parent=window)

    def open_folder():
        try:
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            result = subprocess.run(['/usr/bin/gio', 'open', str(folder)], capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or 'The desktop file manager could not open the folder.')
        except (OSError, RuntimeError) as exc:
            messagebox.showerror('Could not open log folder', str(exc), parent=window)

    panel = LogPanel(window, title='Saved log preview', save_log=save)
    panel.text.configure(width=1, height=3)
    panel.frame.grid(row=2, sticky='nsew', padx=10, pady=(0, 10))
    ttk.Button(panel.controls, text='Refresh logs', command=refresh).pack(side='left')
    ttk.Button(panel.controls, text='Open log folder', command=open_folder).pack(side='left', padx=6)
    ttk.Button(panel.controls, text='Close', command=window.destroy).pack(side='right')
    tree.bind('<<TreeviewSelect>>', show_selected)
    refresh()
    return window


def run_operation_window(title, operation):
    """Run a file-manager operation without hiding its output or final result."""
    import queue
    import tkinter as tk
    from tkinter import ttk
    root = tk.Tk()
    root.title(title)
    root.geometry('900x560')
    panel = LogPanel(root)
    panel.frame.pack(fill='both', expand=True, padx=10, pady=10)
    status = tk.StringVar(value='Running...')
    ttk.Label(root, textvariable=status).pack(anchor='w', padx=10)
    close = ttk.Button(root, text='Close', command=root.destroy, state='disabled')
    close.pack(anchor='e', padx=10, pady=10)
    events = queue.Queue()
    result = [1]
    active = [True]
    def worker():
        log = None
        try:
            log = OperationLog(title, lambda text: events.put(('line', text)))
            value = operation(log)
            log.stage('Completed: ' + str(value))
            events.put(('result', (0, 'Completed successfully. The log remains available below.')))
        except Exception as exc:
            if log:
                log.stage('FAILED: ' + str(exc))
            events.put(('result', (1, 'Failed: ' + str(exc))))
        finally:
            if log:
                log.close()
    def poll():
        try:
            for _ in range(200):
                kind, value = events.get_nowait()
                if kind == 'line':
                    panel.append(value)
                else:
                    result[0], message = value
                    active[0] = False
                    status.set(message)
                    close.configure(state='normal')
        except queue.Empty:
            pass
        root.after(75, poll)
    root.protocol('WM_DELETE_WINDOW', lambda: None if active[0] else root.destroy())
    root.after(75, poll)
    threading.Thread(target=worker, daemon=False).start()
    root.mainloop()
    return result[0]
