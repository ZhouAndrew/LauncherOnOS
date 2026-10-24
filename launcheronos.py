#!/usr/bin/env python3
"""LauncherOnOS: a safe, user-scoped manager for personal Linux utilities."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone

APP_DIR = Path(os.environ.get('LAUNCHERONOS_HOME', Path.home() / '.local/share/launcheronos')).expanduser()
TOOLS_DIR = APP_DIR / 'tools'
DB_FILE = APP_DIR / 'registry.json'
DEFAULT_SCAN = Path.home() / 'bin'
VALID_ID = re.compile(r'^[a-z][a-z0-9_-]{0,63}$')


def slug(value: str) -> str:
    value = re.sub(r'[^a-z0-9_-]+', '-', value.lower()).strip('-_')
    if not VALID_ID.fullmatch(value):
        raise ValueError('Invalid tool name; use 1–64 ASCII letters, digits, hyphens or underscores')
    return value


def database() -> dict:
    if not DB_FILE.exists():
        return {}
    data = json.loads(DB_FILE.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('Invalid registry')
    return data


def save(data: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    temp = DB_FILE.with_name(DB_FILE.name + '.tmp')
    with temp.open('w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write('\n')
    temp.replace(DB_FILE)


def sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(128 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def summary(path: Path) -> str:
    try:
        with path.open('r', encoding='utf-8', errors='replace') as f:
            lines = [f.readline().strip() for _ in range(12)]
        for line in lines:
            if line.startswith('# ') and not line.startswith('# !'):
                return line[2:][:140]
    except (OSError, UnicodeError):
        pass
    return 'No description; inspect the file before running'


def file_check(raw_path: str) -> Path:
    path = Path(raw_path).expanduser().absolute()
    if path.is_symlink() or not path.is_file():
        raise ValueError('Expected a regular file, not a symlink or directory')
    return path


def install(path: str, tool_id: str | None = None, description: str | None = None, external: bool = False) -> str:
    src = file_check(path)
    if not external and src.stat().st_size > 10 * 1024 * 1024:
        raise ValueError('Standalone script exceeds 10 MiB; register as external tool instead')
    key = slug(tool_id or src.stem)
    data = database()
    if key in data:
        raise ValueError(f'Already registered: {key}. Uninstall it first.')
    suffix = src.suffix.lower() if re.fullmatch(r'\.[a-zA-Z0-9]{1,8}', src.suffix) else ''
    destination = TOOLS_DIR / (key + suffix)
    if not external:
        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f'Existing managed destination: {destination}')
        shutil.copy2(src, destination, follow_symlinks=False)
        destination.chmod(destination.stat().st_mode | 0o700)
    entry = {
        'id': key,
        'description': description or summary(src),
        'mode': 'external' if external else 'managed',
        'path': str(src if external else destination),
        'source': str(src),
        'sha256': sha256(src),
        'added': datetime.now(timezone.utc).isoformat(),
    }
    try:
        data[key] = entry
        save(data)
    except BaseException:
        if not external:
            destination.unlink(missing_ok=True)
        raise
    return key


def scan(directory: Path = DEFAULT_SCAN) -> list[Path]:
    folder = directory.expanduser()
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and not p.is_symlink()
                  and not p.name.startswith('.')
                  and not (p.name.endswith(('.bak', '.old', '~')) or '.before-' in p.name))


def search(term: str) -> list[str]:
    needle = term.casefold()
    out = []
    for key, row in sorted(database().items()):
        if needle in (key + ' ' + row.get('description', '')).casefold():
            out.append(f'[installed] {key:27} {row.get("description", "")}')
    for path in scan():
        if needle in (path.name + ' ' + summary(path)).casefold():
            out.append(f'[local]     {path.name:27} {summary(path)}')
    return out


def info(key: str) -> dict:
    return database()[slug(key)]


def execute(key: str, args: list[str]) -> int:
    entry = info(key)
    path = Path(entry['path'])
    if not path.is_file():
        raise FileNotFoundError(f'Missing tool: {path}')
    # Only explicit user invocation executes code. Scanning and installing never do.
    if path.suffix == '.py':
        command = [sys.executable, str(path)]
    elif path.suffix == '.sh':
        command = ['/bin/bash', str(path)]
    elif os.access(path, os.X_OK):
        command = [str(path)]
    else:
        raise ValueError(f'Not executable: {path}')
    return subprocess.run(command + args, check=False).returncode


def uninstall(key: str) -> None:
    key = slug(key)
    data = database()
    entry = data[key]
    if entry['mode'] == 'managed':
        path = Path(entry['path'])
        # The registry can never authorize deletion outside its designated tools folder.
        if path.parent != TOOLS_DIR or not path.name.startswith(key + '.') and path.name != key:
            raise ValueError('Unsafe managed path; refusing to delete')
        if path.is_symlink():
            raise ValueError('Managed file is unexpectedly a symlink; refusing to delete')
        if path.is_file() and sha256(path) != entry['sha256']:
            raise ValueError('Managed file has changed; refusing to delete automatically')
        path.unlink(missing_ok=True)
    del data[key]
    save(data)


def export_archive(item: str, destination: Path) -> None:
    entries = database()
    keys = sorted(entries) if item == 'all' else [slug(item)]
    if not all(k in entries for k in keys):
        raise KeyError(f'Unknown tool: {item}')
    destination = destination.expanduser().absolute()
    if destination.exists():
        raise FileExistsError(f'Refusing to overwrite: {destination}')
    manifest = []
    with tarfile.open(destination, 'x:gz') as tar:
        for key in keys:
            e = entries[key]
            item_record = {k: e[k] for k in ('id', 'description', 'mode', 'sha256', 'added')}
            if e['mode'] == 'managed':
                path = Path(e['path'])
                if path.is_symlink() or not path.is_file() or sha256(path) != e['sha256']:
                    raise ValueError(f'Export aborted: modified or missing tool {key}')
                archive_name = 'tools/' + path.name
                tar.add(path, arcname=archive_name, recursive=False)
                item_record['file'] = archive_name
            else:
                item_record['note'] = 'Externally managed entry: executable not bundled'
            manifest.append(item_record)
        payload = json.dumps({'schema': 1, 'tools': manifest}, indent=2).encode()
        meta = tarfile.TarInfo('manifest.json')
        meta.size = len(payload)
        meta.mode = 0o600
        tar.addfile(meta, io.BytesIO(payload))


def menu() -> None:
    while True:
        print('\n=== LauncherOnOS ===')
        print('1 List    2 Search    3 Info    4 Scan ~/bin    5 Install script')
        print('6 Register external tool    7 Launch    8 Export    9 Uninstall    0 Exit')
        choice = input('Choose: ').strip()
        if choice == '0':
            return
        try:
            if choice == '1':
                for k, e in sorted(database().items()):
                    print(f'{k:27} [{e["mode"]}] {e["description"]}')
            elif choice == '2':
                print('\n'.join(search(input('Search: '))) or 'No matches')
            elif choice == '3':
                print(json.dumps(info(input('Tool ID: ')), indent=2))
            elif choice == '4':
                for p in scan():
                    print(f'{p.name:30} {summary(p)}')
            elif choice in ('5', '6'):
                path = input('Script or executable path: ').strip()
                print('Registered:', install(path, external=(choice == '6')))
            elif choice == '7':
                key = input('Tool ID: ').strip()
                if input('Execute this tool? [y/N]: ').strip().lower() == 'y':
                    print('Exit status:', execute(key, []))
            elif choice == '8':
                key = input('Tool ID or all: ').strip()
                dest = Path(input('Export tar.gz path: ').strip())
                export_archive(key, dest)
                print('Exported:', dest)
            elif choice == '9':
                key = input('Tool ID: ').strip()
                if input(f'Unregister {key}? [y/N]: ').strip().lower() == 'y':
                    uninstall(key)
                    print('Unregistered:', key)
            else:
                print('Unknown choice')
        except (ValueError, KeyError, FileNotFoundError, PermissionError, OSError) as exc:
            print('Error:', exc, file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command')
    sub.add_parser('menu', help='interactive management menu')
    sub.add_parser('list', help='list registered tools')
    sp = sub.add_parser('scan', help='scan files without executing them')
    sp.add_argument('directory', nargs='?', default=str(DEFAULT_SCAN))
    sp = sub.add_parser('search', help='search registered and local tools')
    sp.add_argument('term')
    sp = sub.add_parser('info', help='show tool details')
    sp.add_argument('tool_id')
    for cmd in ('install', 'register'):
        sp = sub.add_parser(cmd, help='copy one script' if cmd == 'install' else 'track existing executable')
        sp.add_argument('path')
        sp.add_argument('--id')
        sp.add_argument('--description')
    sp = sub.add_parser('run', help='launch an explicitly selected tool')
    sp.add_argument('tool_id')
    sp.add_argument('args', nargs=argparse.REMAINDER)
    sp = sub.add_parser('export', help='export managed tools to tar.gz')
    sp.add_argument('tool_id', help='tool ID or all')
    sp.add_argument('path')
    sp = sub.add_parser('uninstall', help='unregister, deleting only owned copies')
    sp.add_argument('tool_id')
    args = p.parse_args(argv)
    try:
        if args.command in (None, 'menu'):
            menu()
        elif args.command == 'list':
            for k, v in sorted(database().items()):
                print(f'{k}\t[{v["mode"]}]\t{v["description"]}')
        elif args.command == 'scan':
            for path in scan(Path(args.directory)):
                print(path)
        elif args.command == 'search':
            print('\n'.join(search(args.term)) or 'No matches')
        elif args.command == 'info':
            print(json.dumps(info(args.tool_id), indent=2))
        elif args.command in ('install', 'register'):
            print(install(args.path, args.id, args.description, args.command == 'register'))
        elif args.command == 'run':
            return execute(args.tool_id, args.args)
        elif args.command == 'export':
            export_archive(args.tool_id, Path(args.path))
            print(args.path)
        elif args.command == 'uninstall':
            uninstall(args.tool_id)
        return 0
    except (ValueError, KeyError, FileNotFoundError, PermissionError, OSError) as exc:
        print('Error:', exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
