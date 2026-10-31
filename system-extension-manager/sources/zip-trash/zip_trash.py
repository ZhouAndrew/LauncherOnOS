#!/usr/bin/python3
"""Nemo ZIP action: system zip/unzip, verified contents, GIO trash only."""
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import zipfile

if Path(__file__).parent == Path("/usr/bin"):
    sys.path.insert(0, "/usr/lib/system-extensions/zip-trash")
from execution import OperationLog, run_operation_window


def digest(stream):
    h = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        h.update(chunk)
    return h.hexdigest()


def snapshot(paths):
    result = {}
    def visit(path, name):
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode):
            # Preserve the link text, including dangling targets; never traverse it.
            target = os.fsencode(os.readlink(path))
            after = path.lstat()
            fields = ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
            if any(getattr(before, field) != getattr(after, field) for field in fields):
                raise ValueError('Symbolic link changed while reading: ' + str(path))
            result[name] = ('symlink', target)
        elif stat.S_ISDIR(before.st_mode):
            result[name + '/'] = None
            for child in sorted(path.iterdir()):
                visit(child, name + '/' + child.name)
        elif stat.S_ISREG(before.st_mode):
            with path.open('rb') as stream:
                value = digest(stream)
            after = path.lstat()
            fields = ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
            if any(getattr(before, field) != getattr(after, field) for field in fields):
                raise ValueError('File changed while reading: ' + str(path))
            result[name] = value
        else:
            raise ValueError('Device, socket, or special file is unsupported: ' + str(path))
    for path in paths:
        visit(path, path.name)
    return result


def archive_and_trash(inputs, run=subprocess.run, report=lambda text: None):
    paths = [Path(os.path.abspath(p)) for p in inputs]
    if not paths or len(set(paths)) != len(paths):
        raise ValueError('Select nonduplicate files or folders')
    parent = paths[0].parent
    if any(p.parent != parent or p == parent for p in paths):
        raise ValueError('Select files or folders from the same directory')
    report("Reading original file contents")
    original = snapshot(paths)
    base = paths[0].name if len(paths) == 1 else 'Archive'
    # A private directory on the same filesystem allows no-clobber publication.
    with tempfile.TemporaryDirectory(prefix='.mint-toolbox-zip-', dir=parent) as temporary:
        staged = Path(temporary) / 'archive.zip'
        report('Compressing with system zip')
        run(['/usr/bin/zip', '-r', '-y', str(staged), '--',
             *['./' + p.name for p in paths]], cwd=parent, check=True)
        report('Testing ZIP integrity with system unzip')
        run(['/usr/bin/unzip', '-t', str(staged)], check=True)
        report('Comparing ZIP contents with original files')
        with zipfile.ZipFile(staged) as archive:
            actual = {}
            for entry in archive.infolist():
                name = entry.filename.removeprefix('./')
                if name in actual:
                    raise ValueError('ZIP contains duplicate entries. Originals retained.')
                with archive.open(entry) as stream:
                    if stat.S_ISLNK(entry.external_attr >> 16):
                        actual[name] = ('symlink', stream.read())
                    else:
                        actual[name] = None if entry.is_dir() else digest(stream)
        if actual != original or snapshot(paths) != original:
            raise ValueError('ZIP content differs or originals changed. Originals retained.')
        with staged.open('rb') as stream:
            os.fsync(stream.fileno())
        report('Publishing verified archive without overwriting existing files')
        number = 0
        while True:
            suffix = '' if number == 0 else f' ({number})'
            target = parent / (base + suffix + '.zip')
            try:
                os.link(staged, target)
                break
            except FileExistsError:
                number += 1
        fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        # Never fall back to rm. Failed/partial trash keeps the verified ZIP.
        try:
            if snapshot(paths) != original:
                raise ValueError('Originals changed after compression. Originals retained.')
            report('Moving originals to the system Trash')
            for path in paths:
                run(['/usr/bin/gio', 'trash', '--', str(path)], check=True)
        except Exception as exc:
            raise RuntimeError(f'ZIP saved to {target}; moving originals to Trash did not fully complete: {exc}') from exc
        return target


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Compress to ZIP and move originals to Trash')
    parser.add_argument('--gui', action='store_true')
    parser.add_argument('paths', nargs='+')
    args = parser.parse_args()
    if args.gui:
        import tkinter as tk
        from tkinter import messagebox
        confirm = tk.Tk()
        confirm.withdraw()
        accepted = messagebox.askyesno('Compress to ZIP and delete',
            'Compress and verify the selection, then move originals to Trash?\nSymbolic links are stored as links; their targets are not followed.\n\nA window will show commands and live output.', parent=confirm)
        confirm.destroy()
        if not accepted:
            return 0
        return run_operation_window('ZIP and Trash',
            lambda log: archive_and_trash(args.paths, log.run, log.stage))
    log = OperationLog('ZIP and Trash')
    try:
        target = archive_and_trash(args.paths, log.run, log.stage)
        log.stage('ZIP created; originals moved to Trash: ' + str(target))
        return 0
    except Exception as exc:
        log.stage('FAILED: ' + str(exc))
        return 1
    finally:
        log.close()


if __name__ == '__main__':
    sys.exit(main())
