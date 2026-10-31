"""Bundled Debian extensions. The dpkg database is the enabled-state authority."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import queue
import shlex

ROOT = Path(__file__).resolve().parent


def plugins():
    return json.loads((ROOT / 'system-plugins.json').read_text('utf-8'))


def package_status(package):
    result = subprocess.run(['/usr/bin/dpkg-query', '-W', '-f=${Status}\n${Version}', package],
                            capture_output=True, text=True, timeout=15)
    if result.returncode == 1:
        return ('absent', None)
    if result.returncode:
        raise RuntimeError('无法读取系统包状态：' + result.stderr)
    lines = result.stdout.splitlines()
    if len(lines) != 2:
        raise RuntimeError('系统包状态格式异常')
    return tuple(lines)


def installed_version(package):
    status, version = package_status(package)
    return version if status == 'install ok installed' else None


def state_text(package):
    status, version = package_status(package)
    if status == 'install ok installed':
        return '已启用 · ' + version
    if status == 'absent' or status.endswith(' ok config-files'):
        return '已禁用（扩展包未安装）'
    return '安装状态异常，请重试启用或禁用：' + status


def plugin(key):
    return next(p for p in plugins() if p['id'] == key)


def command(key, enable):
    item = plugin(key)
    if enable:
        deb = (ROOT / item['deb']).resolve()
        if not deb.is_relative_to(ROOT) or not deb.is_file():
            raise ValueError('随附 deb 缺失，请使用完整发行包')
        if hashlib.sha256(deb.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('随附 deb 校验失败')
        info = subprocess.run(['/usr/bin/dpkg-deb', '-f', str(deb), 'Package', 'Version', 'Architecture'],
                              check=True, capture_output=True, text=True, timeout=15).stdout
        expected = f"Package: {item['package']}\nVersion: {item['version']}\nArchitecture: all\n"
        if info != expected:
            raise ValueError('deb 包名、版本或架构与扩展清单不符')
        args = ['/usr/bin/apt-get', 'install', '--no-install-recommends', '--no-remove', '-y', str(deb)]
    else:
        args = ['/usr/bin/apt-get', 'remove', '-y', item['package']]
    return args if os.geteuid() == 0 else ['/usr/bin/pkexec', *args]


def change(key, enable):
    item = plugin(key)
    args = command(key, enable)
    result = subprocess.run(args, capture_output=True, text=True)
    status, version = package_status(item['package'])
    correct = (status == 'install ok installed' and version == item['version']) if enable else (status == 'absent' or status.endswith(' ok config-files'))
    if result.returncode or not correct:
        raise RuntimeError('扩展操作未完成或状态回读不符。\n' + result.stdout[-3000:] + result.stderr[-3000:])
    return version


def show_gui(parent=None):
    import tkinter as tk
    from tkinter import ttk, messagebox
    window = tk.Toplevel(parent) if parent else tk.Tk()
    window.title('Mint Toolbox · 系统扩展')
    window.geometry('760x460')
    ttk.Label(window, text='启用 = 安装随附 deb；禁用 = 卸载扩展包。系统会请求管理员授权。',
              wraplength=720).pack(padx=16, pady=14, anchor='w')
    rows = plugins()
    selected = tk.StringVar(value=rows[0]['id'])
    for item in rows:
        ttk.Radiobutton(window, text=item['name'], variable=selected, value=item['id']).pack(anchor='w', padx=16)
    status = tk.StringVar()
    ttk.Label(window, textvariable=status, wraplength=720).pack(anchor='w', padx=16, pady=12)
    text = tk.Text(window, height=8, wrap='word')
    text.pack(fill='both', expand=True, padx=16)
    def refresh(*_):
        item = plugin(selected.get())
        try:
            status.set(state_text(item['package']))
        except Exception as exc:
            status.set(str(exc))
        text.delete('1.0', 'end')
        text.insert('end', item['description'])
    selected.trace_add('write', refresh)
    buttons = ttk.Frame(window)
    buttons.pack(fill='x', padx=16, pady=12)
    results = queue.Queue()
    busy = [False]
    def operate(enable):
        key = selected.get()
        try:
            args = command(key, enable)
        except Exception as exc:
            messagebox.showerror('无法操作', str(exc), parent=window)
            return
        if not messagebox.askyesno('确认系统扩展操作',
                ('启用' if enable else '禁用') + '：' + plugin(key)['name'] + '\n\n' + shlex.join(args), parent=window):
            return
        busy[0] = True
        for button in controls:
            button.configure(state='disabled')
        status.set('正在安装或卸载，请完成系统授权…')
        def worker():
            try:
                change(key, enable)
                results.put(None)
            except Exception as exc:
                results.put(str(exc))
        threading.Thread(target=worker, daemon=True).start()
        window.after(100, poll)
    def poll():
        try:
            error = results.get_nowait()
        except queue.Empty:
            window.after(100, poll)
            return
        busy[0] = False
        for button in controls:
            button.configure(state='normal')
        refresh()
        if error:
            messagebox.showerror('操作失败', error, parent=window)
    controls = [ttk.Button(buttons, text='启用 / 安装', command=lambda: operate(True)),
                ttk.Button(buttons, text='禁用 / 卸载', command=lambda: operate(False)),
                ttk.Button(buttons, text='刷新状态', command=refresh)]
    for button in controls:
        button.pack(side='left', padx=(0, 10))
    window.protocol('WM_DELETE_WINDOW', lambda: None if busy[0] else window.destroy())
    refresh()
    if parent is None:
        window.mainloop()
