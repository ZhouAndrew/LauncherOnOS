#!/usr/bin/python3
"""Opt-in security updates for Ubuntu Noble-based Linux Mint; no scheduler."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import queue


LOCK = '/run/lock/mint-security-updates.lock'
APT = '/usr/bin/apt-get'
PKEXEC = '/usr/bin/pkexec'
SELF = '/usr/bin/mint-security-updates'
APT_OPTIONS = [
    '-o', 'DPkg::Lock::Timeout=0',
    '-o', 'APT::Get::AllowUnauthenticated=false',
    '-o', 'Dpkg::Use-Pty=0',
    '--no-remove', '--only-upgrade', '--no-install-recommends',
]


class SafetyError(RuntimeError):
    pass


def command(argv, *, env=None):
    result = subprocess.run(argv, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, env=env, check=False)
    if result.returncode:
        raise SafetyError('Command failed (exit {}): {}\n{}'.format(
            result.returncode, ' '.join(argv), result.stdout))
    return result.stdout


def protected(name):
    name = name.lower().split(':', 1)[0]
    if 'nvidia' in name or 'cuda' in name:
        return True
    return name.startswith((
        'linux-', 'nvidia-', 'libnvidia-', 'xserver-xorg-video-nvidia',
        'cuda-', 'grub-', 'shim-', 'initramfs-', 'dracut-',
        'firmware-', 'fwupd', 'virtualbox-', 'zfs-', 'libkmod',
    )) or name in {
        'dkms', 'nvidia', 'grub', 'shim', 'mokutil', 'kmod',
        'intel-microcode', 'amd64-microcode', 'bcmwl-kernel-source',
    } or bool(re.search(r'(^|[-_])dkms($|[-_])', name))


def ensure_host():
    data = {}
    for line in Path('/etc/os-release').read_text().splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            data[key] = value.strip('"')
    if data.get('ID') != 'linuxmint' or data.get('UBUNTU_CODENAME') != 'noble':
        raise SafetyError('Supported OS: Ubuntu Noble-based Linux Mint 22.x only.')


def check_dpkg():
    result = command(['/usr/bin/dpkg', '--audit'])
    if result.strip():
        raise SafetyError('Incomplete dpkg transaction; repair separately:\n' + result)


def check_locks():
    locks = [p for p in (
        '/var/lib/dpkg/lock-frontend', '/var/lib/dpkg/lock',
        '/var/lib/apt/lists/lock', '/var/cache/apt/archives/lock',
    ) if Path(p).exists()]
    if not locks:
        return
    result = subprocess.run(['/usr/bin/fuser', *locks],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode == 0:
        raise SafetyError('An APT/dpkg process is already running; no locks were removed.')
    if result.returncode != 1:
        raise SafetyError('Cannot safely determine APT/dpkg lock ownership.')


def scan():
    ensure_host()
    import apt
    import apt_pkg
    apt_pkg.init()
    held = set(command(['/usr/bin/apt-mark', 'showhold']).splitlines())
    cache = apt.Cache()
    wanted, frozen = {}, {}
    for pkg in cache:
        if not pkg.is_installed:
            continue
        name, installed = pkg.name, pkg.installed.version
        if protected(name):
            frozen[name] = installed
            continue
        if name in held or name.split(':', 1)[0] in held:
            continue
        for version in pkg.versions:
            if apt_pkg.version_compare(version.version, installed) <= 0:
                continue
            origins = version.origins
            if not origins or not all(o.trusted and o.origin == 'Ubuntu' for o in origins):
                continue
            if not any(o.archive == 'noble-security' for o in origins):
                continue
            if name not in wanted or apt_pkg.version_compare(version.version, wanted[name]) > 0:
                wanted[name] = version.version
    return dict(sorted(wanted.items())), frozen


def digest(packages):
    encoded = json.dumps(packages, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def simulate(packages):
    specs = [name + '=' + version for name, version in sorted(packages.items())]
    output = command([APT, '--simulate', *APT_OPTIONS, 'install', *specs])
    installed = {}
    for line in output.splitlines():
        if line.startswith(('Remv ', 'Purg ')):
            raise SafetyError('APT proposed removal: ' + line)
        if line.startswith('Inst '):
            match = re.match(r'^Inst\s+(\S+)\s+\[([^\]]+)\]\s+\((\S+)(?:\s|\))', line)
            if not match:
                raise SafetyError('APT proposed a new or unknown installation: ' + line)
            name, _, version = match.groups()
            if name in installed or protected(name) or packages.get(name) != version:
                raise SafetyError('APT proposed an unapproved upgrade: ' + line)
            installed[name] = version
        if line.startswith('Conf '):
            name = line.split()[1]
            if name not in packages or protected(name):
                raise SafetyError('APT proposed an unapproved configuration: ' + line)
    if installed != packages:
        raise SafetyError('APT simulation did not match the approved security updates.')
    return specs


def apply(expected):
    if os.geteuid() != 0:
        raise SafetyError('Root authorization required for installation.')
    with open(LOCK, 'a+', encoding='utf-8') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SafetyError('Another manual security update is already running.') from None
        check_locks()
        check_dpkg()
        packages, frozen = scan()
        if digest(packages) != expected:
            raise SafetyError('Security update plan changed. Check again; no changes made.')
        if not packages:
            print('No eligible security updates; nothing changed.', flush=True)
            return
        specs = simulate(packages)
        check_locks()
        check_dpkg()
        print('Simulation passed: {} approved upgrades, no new packages or removals.'.format(len(specs)), flush=True)
        env = dict(os.environ, DEBIAN_FRONTEND='noninteractive',
                   NEEDRESTART_MODE='l', APT_LISTCHANGES_FRONTEND='none')
        print('Installing approved security updates...', flush=True)
        args = [APT, '-y', *APT_OPTIONS, '-o', 'Dpkg::Options::=--force-confold', 'install', *specs]
        result = subprocess.run(args, env=env, check=False)
        if result.returncode:
            raise SafetyError('APT exited with {}; installation may be partial.'.format(result.returncode))
        installed, frozen_after = scan_installed(packages, frozen)
        if installed or frozen_after:
            raise SafetyError('Post-install verification failed: ' + str(installed + frozen_after))
        check_dpkg()
        print('Verified {} security updates; protected package versions unchanged.'.format(len(packages)), flush=True)
        print('No timers, holds, autoremove or reboots were configured.', flush=True)


def scan_installed(packages, frozen):
    import apt
    cache = apt.Cache()
    mismatches, protected_changes = [], []
    for name, version in packages.items():
        actual = cache[name].installed.version if cache[name].is_installed else None
        if actual != version:
            mismatches.append('{}: expected {}, found {}'.format(name, version, actual))
    for name, version in frozen.items():
        actual = cache[name].installed.version if cache[name].is_installed else None
        if actual != version:
            protected_changes.append('PROTECTED {}: {} -> {}'.format(name, version, actual))
    return mismatches, protected_changes


def refresh():
    if os.geteuid() != 0:
        raise SafetyError('Root authorization required to refresh APT indexes.')
    ensure_host()
    with open(LOCK, 'a+', encoding='utf-8') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SafetyError('Another manual security update is already running.') from None
        check_locks()
        check_dpkg()
        print('Refreshing APT indexes; no packages will be installed...', flush=True)
        print(command([APT, '-o', 'DPkg::Lock::Timeout=0',
                       '-o', 'APT::Update::Error-Mode=any', 'update']), flush=True)
        print('APT index refresh completed.', flush=True)


def privilege(action, expected=None):
    argv = [PKEXEC, SELF, action]
    if expected is not None:
        argv += ['--expect', expected]
    return subprocess.call(argv)


def gui():
    import tkinter as tk
    from tkinter import ttk, messagebox, scrolledtext
    root = tk.Tk()
    root.title('Manual Security Updates')
    root.geometry('880x600')
    root.minsize(690, 450)
    ttk.Label(root, text='Ubuntu security updates only. Kernel, NVIDIA, DKMS and boot components are excluded.',
              wraplength=830).pack(anchor='w', padx=12, pady=(12, 4))
    ttk.Label(root, text='Manual operation only: no scheduler, automatic upgrade, package removal or reboot.',
              wraplength=830).pack(anchor='w', padx=12, pady=(0, 8))
    status = tk.StringVar(value='Checking the cached security-update list...')
    ttk.Label(root, textvariable=status).pack(anchor='w', padx=12)
    items = tk.Listbox(root, height=8)
    items.pack(fill='both', expand=True, padx=12, pady=8)
    ttk.Label(root, text='Execution log').pack(anchor='w', padx=12)
    log = scrolledtext.ScrolledText(root, height=12, state='disabled')
    log.pack(fill='both', expand=True, padx=12, pady=8)
    bar = ttk.Frame(root)
    bar.pack(fill='x', padx=12, pady=(0, 12))
    events = queue.Queue()
    state = {'busy': False, 'packages': {}, 'digest': None}

    def write(line):
        log.configure(state='normal')
        log.insert('end', line)
        log.see('end')
        log.configure(state='disabled')

    def redraw():
        for widget in (check_btn, refresh_btn):
            widget.configure(state='disabled' if state['busy'] else 'normal')
        apply_btn.configure(state='normal' if not state['busy'] and state['packages'] else 'disabled')

    def read_plan():
        proc = subprocess.run([SELF, '--check', '--json'], capture_output=True, text=True)
        if proc.returncode:
            raise SafetyError(proc.stderr or proc.stdout)
        return json.loads(proc.stdout)

    def launch(action):
        if state['busy']:
            return
        state['busy'] = True
        if action != 'check':
            state['packages'] = {}
        redraw()
        status.set('Running ' + action + '...')
        def worker():
            try:
                if action != 'check':
                    argv = [PKEXEC, SELF, '--refresh-root' if action == 'refresh' else '--apply-root']
                    if action == 'apply':
                        argv += ['--expect', state['digest']]
                    events.put(('log', '$ ' + ' '.join(argv) + '\n'))
                    with subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                          text=True, bufsize=1) as proc:
                        for line in proc.stdout:
                            events.put(('log', line))
                        code = proc.wait()
                    if code:
                        raise SafetyError('Operation exited with code {}'.format(code))
                result = read_plan()
                events.put(('complete', result))
            except Exception as exc:
                events.put(('error', str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def poll():
        try:
            for _ in range(200):
                kind, value = events.get_nowait()
                if kind == 'log':
                    write(value)
                elif kind == 'complete':
                    state['packages'] = value['packages']
                    state['digest'] = value['digest']
                    items.delete(0, 'end')
                    for name, version in value['packages'].items():
                        items.insert('end', '{}  ->  {}'.format(name, version))
                    status.set('{} eligible security updates. Protected packages remain unchanged.'.format(len(value['packages'])))
                    write('Check complete: {} eligible packages.\n'.format(len(value['packages'])))
                    state['busy'] = False
                else:
                    state['packages'] = {}
                    status.set('Failed: ' + value)
                    write('ERROR: ' + value + '\n')
                    state['busy'] = False
                redraw()
        except queue.Empty:
            pass
        root.after(80, poll)

    def confirm_apply():
        count = len(state['packages'])
        if count and messagebox.askyesno('Install security updates',
                'Install {} Ubuntu security updates?\n\n'
                'APT will first simulate the transaction and abort if it needs to add, remove, '
                'or change unapproved packages. Some services may restart. This is not reversible automatically.'.format(count),
                parent=root):
            launch('apply')

    check_btn = ttk.Button(bar, text='Check cached list', command=lambda: launch('check'))
    check_btn.pack(side='left')
    refresh_btn = ttk.Button(bar, text='Refresh package indexes (administrator)', command=lambda: launch('refresh'))
    refresh_btn.pack(side='left', padx=8)
    apply_btn = ttk.Button(bar, text='Install security updates...', command=confirm_apply)
    apply_btn.pack(side='left')
    redraw()
    root.after(80, poll)
    root.after(120, lambda: launch('check'))
    root.mainloop()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--gui', action='store_true')
    group.add_argument('--check', action='store_true', help='read-only scan of cached APT metadata')
    group.add_argument('--refresh', action='store_true', help='refresh APT package indexes with explicit authorization')
    group.add_argument('--apply', action='store_true', help='manually install only safe eligible security updates')
    group.add_argument('--refresh-root', action='store_true', help=argparse.SUPPRESS)
    group.add_argument('--apply-root', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--json', action='store_true', help='machine-readable --check output')
    parser.add_argument('--expect', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.refresh_root:
            refresh()
        elif args.apply_root:
            if not args.expect or not re.fullmatch('[0-9a-f]{64}', args.expect):
                raise SafetyError('Missing or invalid approved update fingerprint.')
            apply(args.expect)
        elif args.refresh:
            return privilege('--refresh-root')
        elif args.apply:
            wanted, _ = scan()
            if not wanted:
                print('No eligible security updates.')
                return 0
            print('Requested security updates:')
            for name, version in wanted.items():
                print('  {} -> {}'.format(name, version))
            return privilege('--apply-root', digest(wanted))
        elif args.check:
            wanted, frozen = scan()
            data = {'packages': wanted, 'digest': digest(wanted), 'protected_count': len(frozen)}
            if args.json:
                print(json.dumps(data, sort_keys=True))
            else:
                print('{} eligible Ubuntu security updates; {} protected packages.'.format(len(wanted), len(frozen)))
                for name, version in wanted.items():
                    print('  {} -> {}'.format(name, version))
        else:
            gui()
        return 0
    except (SafetyError, OSError, ImportError, subprocess.SubprocessError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
