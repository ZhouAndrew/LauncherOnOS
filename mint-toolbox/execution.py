"""Real-time command output and persistent, private operation logs."""
from datetime import datetime
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import threading


class OperationLog:
    def __init__(self, label, emit=None):
        base = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state'))
        folder = base / 'mint-toolbox/logs'
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, name = tempfile.mkstemp(prefix=datetime.now().strftime('%Y%m%d-%H%M%S-'), suffix='.log', dir=folder)
        self.path = Path(name)
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
    def __init__(self, parent):
        import tkinter as tk
        from tkinter import ttk, filedialog
        self.frame = ttk.LabelFrame(parent, text='Execution log')
        self.text = tk.Text(self.frame, wrap='word', height=13, state='disabled')
        scroll = ttk.Scrollbar(self.frame, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.text.pack(fill='both', expand=True)
        controls = ttk.Frame(self.frame)
        controls.pack(fill='x')
        def copy():
            self.text.clipboard_clear()
            self.text.clipboard_append(self.text.get('1.0', 'end-1c'))
        def save():
            path = filedialog.asksaveasfilename(parent=parent, defaultextension='.log',
                                              filetypes=[('Log files', '*.log'), ('All files', '*')])
            if path:
                Path(path).write_text(self.text.get('1.0', 'end-1c'), encoding='utf-8')
        ttk.Button(controls, text='Copy log', command=copy).pack(side='left')
        ttk.Button(controls, text='Save log...', command=save).pack(side='left', padx=6)

    def append(self, text):
        self.text.configure(state='normal')
        self.text.insert('end', text)
        self.text.see('end')
        self.text.configure(state='disabled')


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
