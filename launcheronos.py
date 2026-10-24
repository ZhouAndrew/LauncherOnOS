#!/usr/bin/env python3
"""LauncherOnOS: a safe, user-scoped manager for personal Linux utilities."""
from __future__ import annotations

import argparse
import fcntl
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
import tempfile
from datetime import datetime, timezone
from contextlib import contextmanager

APP_DIR = Path(os.environ.get('LAUNCHERONOS_HOME', Path.home() / '.local/share/launcheronos')).expanduser()
TOOLS_DIR = APP_DIR / 'tools'
DB_FILE = APP_DIR / 'registry.json'
DEFAULT_SCAN = Path.home() / 'bin'
VALID_ID = re.compile(r'^[a-z][a-z0-9_-]{0,63}$')


def slug(value: str) -> str:
    """Validate an existing ID *without* silently changing its meaning."""
    if not VALID_ID.fullmatch(value):
        raise ValueError('Invalid tool ID; use lowercase ASCII letters, digits, - or _')
    return value


def inferred_id(path: Path) -> str:
    """Make a safe default from a filename, including non-ASCII filenames."""
    name = re.sub(r'[^a-z0-9_-]+', '-', path.stem.lower()).strip('-_')[:58]
    if not name or not name[0].isalpha():
        name = 'tool-' + hashlib.sha256(path.name.encode()).hexdigest()[:12]
    return slug(name)


@contextmanager
def registry_lock():
    """Serialize registry mutations across independent CLI processes."""
    APP_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = APP_DIR / '.registry.lock'
    with lock_path.open('a+') as lock:
        lock_path.chmod(0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def database() -> dict:
    if not DB_FILE.exists():
        return {}
    data = json.loads(DB_FILE.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('Invalid registry')
    return data


def save(data: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=APP_DIR,
                                     prefix='.registry-', delete=False) as fh:
        temp = Path(fh.name)
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write('\n')
    try:
        temp.replace(DB_FILE)
    finally:
        temp.unlink(missing_ok=True)


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


def file_check(raw_path: str, external: bool = False) -> Path:
    path = Path(raw_path).expanduser().absolute()
    if (path.is_symlink() and not external) or not path.is_file():
        raise ValueError('Expected a regular file (symlinks are allowed only with register)')
    return path


def install(path: str, tool_id: str | None = None, description: str | None = None, external: bool = False) -> str:
    with registry_lock():
        return _install(path, tool_id, description, external)


def _install(path: str, tool_id: str | None = None, description: str | None = None, external: bool = False) -> str:
    src = file_check(path, external=external)
    if not external and src.stat().st_size > 10 * 1024 * 1024:
        raise ValueError('Standalone script exceeds 10 MiB; register as external tool instead')
    key = slug(tool_id) if tool_id is not None else inferred_id(src)
    data = database()
    if key in data:
        raise ValueError(f'Already registered: {key}. Uninstall it first.')
    suffix = src.suffix.lower() if re.fullmatch(r'\.[a-zA-Z0-9]{1,8}', src.suffix) else ''
    destination = TOOLS_DIR / (key + suffix)
    if not external:
        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f'Existing managed destination: {destination}')
        try:
            shutil.copy2(src, destination, follow_symlinks=False)
            destination.chmod(destination.stat().st_mode | 0o700)
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
    entry = {
        'id': key,
        'description': description or summary(src),
        'mode': 'external' if external else 'managed',
        'path': str(src if external else destination),
        'source': str(src),
        'sha256': sha256(src if external else destination),
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
    if entry['mode'] == 'managed' and sha256(path) != entry['sha256']:
        raise ValueError('Managed tool changed since installation; refusing to launch')
    # Respect an executable script's shebang, including virtualenv/pipx entrypoints.
    with path.open('rb') as stream:
        has_shebang = stream.read(2) == b'#!'
    if os.access(path, os.X_OK) and has_shebang:
        command = [str(path)]
    elif path.suffix == '.py':
        command = [sys.executable, str(path)]
    elif path.suffix == '.sh':
        command = ['/bin/bash', str(path)]
    elif os.access(path, os.X_OK):
        command = [str(path)]
    else:
        raise ValueError(f'Not executable: {path}')
    return subprocess.run(command + args, check=False).returncode


def uninstall(key: str) -> None:
    with registry_lock():
        _uninstall(key)


def _uninstall(key: str) -> None:
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
    """Publish an export only after the complete archive is successfully built."""
    entries = database()
    keys = sorted(entries) if item == 'all' else [slug(item)]
    if not all(k in entries for k in keys):
        raise KeyError(f'Unknown tool: {item}')
    destination = destination.expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f'Refusing to overwrite: {destination}')
    # Temp file is created on the same filesystem; hard-link publishes without
    # ever overwriting an existing destination (even under a concurrent race).
    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.launcheronos-',
                                     suffix='.tmp', delete=False) as tmp:
        staged = Path(tmp.name)
    try:
        manifest = []
        with tarfile.open(staged, 'w:gz') as tar:
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
        os.link(staged, destination)
    finally:
        staged.unlink(missing_ok=True)



# Manuals are imported locally; personal documents are never uploaded.
MANUALS_DIR = APP_DIR / 'manuals'


def list_manuals() -> list[str]:
    if not MANUALS_DIR.is_dir():
        return []
    return sorted(p.name[:-3] for p in MANUALS_DIR.glob('*.md')
                  if p.is_file() and not p.is_symlink())


def import_manuals(archive: Path) -> int:
    """Import ONLY scripts/*.md from a local manual ZIP, never scripts themselves."""
    import zipfile

    archive = archive.expanduser()
    if not archive.is_file():
        raise FileNotFoundError(archive)
    documents = {}
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.infolist():
            parts = entry.filename.replace('\\', '/').split('/')
            if (entry.is_dir() or len(parts) < 2 or parts[-2] != 'scripts'
                    or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,120}\.md',
                                        parts[-1])):
                continue
            if entry.file_size > 1024 * 1024 or len(documents) >= 300:
                raise ValueError('Manual archive exceeds safe import limits')
            name = parts[-1]
            if name in documents:
                raise ValueError(f'Duplicate manual name: {name}')
            documents[name] = bundle.read(entry)
    if not documents or sum(len(b) for b in documents.values()) > 16 * 1024 * 1024:
        raise ValueError('No script manuals found, or archive too large')
    for name, content in documents.items():
        existing = MANUALS_DIR / name
        if existing.is_symlink() or (existing.exists() and existing.read_bytes() != content):
            raise FileExistsError(f'Manual already exists with different contents: {name}')
    MANUALS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    count = 0
    for name, content in documents.items():
        destination = MANUALS_DIR / name
        if destination.exists():
            continue
        with tempfile.NamedTemporaryFile(dir=MANUALS_DIR, prefix='.manual-', delete=False) as file:
            temp = Path(file.name)
            try:
                file.write(content)
                file.flush()
                os.fchmod(file.fileno(), 0o600)
            except BaseException:
                temp.unlink(missing_ok=True)
                raise
        try:
            # Refuse unexpected collisions; importing never overwrites manuals.
            os.link(temp, destination)
            count += 1
        finally:
            temp.unlink(missing_ok=True)
    return count


def find_manual(target: str) -> Path:
    """Find a local Markdown manual without executing or importing any script."""
    direct = Path(target).expanduser()
    if direct.suffix.lower() == '.md' and direct.is_file():
        return direct
    names = [target]
    record = database().get(target)
    if record:
        source_name = Path(record.get('source', '')).name
        names.extend([source_name, Path(source_name).stem])
    for name in names:
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,120}', name):
            continue
        for candidate_name in (name + '.md', name + '.py.md', name + '.sh.md'):
            candidate = MANUALS_DIR / candidate_name
            if candidate.is_file() and not candidate.is_symlink():
                return candidate
    raise FileNotFoundError(f'No manual for {target}. Use: manual import FILE.zip')


def render_manual(path: Path) -> int:
    """Use an installed renderer. Never fall back to unformatted Markdown."""
    if shutil.which('glow'):
        return subprocess.run(['glow', '-p', str(path)], check=False).returncode
    if shutil.which('pandoc') and shutil.which('xdg-open'):
        cache = APP_DIR / 'rendered'
        cache.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Rendered HTML is cached because xdg-open may return before it is read.
        output = cache / (hashlib.sha256(str(path.resolve()).encode()).hexdigest() + '.html')
        with tempfile.NamedTemporaryFile(dir=cache, suffix='.html', delete=False) as f:
            staged = Path(f.name)
            os.fchmod(f.fileno(), 0o600)
        try:
            subprocess.run(['pandoc', '--standalone', '--from=markdown-raw_html',
                            '--to=html5', str(path), '-o', str(staged)], check=True)
            staged.replace(output)
        finally:
            staged.unlink(missing_ok=True)
        subprocess.Popen(['xdg-open', str(output)], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return 0
    raise ValueError('A Markdown renderer is required: install Glow (recommended), '
                     'or Pandoc with xdg-open. The raw Markdown will not be shown.')


def manual_command(target: str, path: str | None = None) -> int:
    if target == 'list' and path is None:
        manuals = list_manuals()
        print('\n'.join(manuals) if manuals else 'No imported manuals')
        return 0
    if target == 'import' and path:
        print(f'Imported {import_manuals(Path(path))} new script manuals')
        return 0
    if path is not None or target == 'import':
        raise ValueError('Usage: manual <name> | manual list | manual import FILE.zip')
    return render_manual(find_manual(target))


CONSOLE_HELP = """LauncherOnOS command console
  help [command]                 Show commands or help for one command
  list                           List registered tools
  scan [directory]               Discover scripts without running them
  search <term>                  Search local and registered tools
  info <id>                      Show tool information
  manual list                    List available formatted manuals
  manual <id>                    Read the manual in Glow (or browser)
  manual import <file.zip>       Import manuals only, not script files
  install <file> [--id ID]       Copy a standalone script
  register <file> [--id ID]      Register an existing executable
  run <id> [args...]             Execute the selected tool
  export <id|all> <file.tar.gz>  Export managed files and metadata
  uninstall <id>                 Unregister tool (asks for confirmation)
  exit                           Leave console
Quoted paths with spaces are supported. Use ? as an alias for help."""


def menu() -> None:
    """A command prompt, not a numerical menu; one-shot CLI remains available."""
    import shlex

    print('LauncherOnOS console — type help for commands, exit to quit')
    commands = {'list', 'scan', 'search', 'info', 'manual', 'install',
                'register', 'run', 'export', 'uninstall'}
    while True:
        try:
            line = input('launcheronos> ').strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line:
            continue
        try:
            tokens = shlex.split(line)
        except ValueError as exc:
            print(f'Invalid command: {exc}', file=sys.stderr)
            continue
        if not tokens:
            continue
        cmd = tokens[0].lower()
        if cmd in ('quit', 'exit', 'q'):
            return
        if cmd in ('help', '?'):
            if len(tokens) == 2 and tokens[1] in commands:
                try:
                    main([tokens[1], '--help'])
                except SystemExit:
                    pass
            else:
                print(CONSOLE_HELP)
            continue
        if cmd not in commands:
            print(f'Unknown command: {tokens[0]}. Type help.')
            continue
        if cmd == 'uninstall' and len(tokens) == 2:
            try:
                if input(f'Unregister {tokens[1]}? [y/N]: ').strip().lower() != 'y':
                    print('Cancelled')
                    continue
            except (EOFError, KeyboardInterrupt):
                print('\nCancelled')
                continue
        try:
            main(tokens)
        except SystemExit:
            # argparse --help or invalid arguments must not close the console.
            continue


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
    sp = sub.add_parser('manual', help='view a formatted local Markdown manual')
    sp.add_argument('target', nargs='?', default='list')
    sp.add_argument('path', nargs='?')
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
        elif args.command == 'manual':
            return manual_command(args.target, args.path)
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
