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
            raise ValueError('暂不支持符号链接：' + str(path))
        if stat.S_ISDIR(before.st_mode):
            result[name + '/'] = None
            for child in sorted(path.iterdir()):
                visit(child, name + '/' + child.name)
        elif stat.S_ISREG(before.st_mode):
            with path.open('rb') as stream:
                value = digest(stream)
            after = path.lstat()
            fields = ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
            if any(getattr(before, field) != getattr(after, field) for field in fields):
                raise ValueError('文件正在变化：' + str(path))
            result[name] = value
        else:
            raise ValueError('不支持设备、套接字或特殊文件：' + str(path))
    for path in paths:
        visit(path, path.name)
    return result


def archive_and_trash(inputs, run=subprocess.run):
    paths = [Path(os.path.abspath(p)) for p in inputs]
    if not paths or len(set(paths)) != len(paths):
        raise ValueError('请选择不重复的文件或文件夹')
    parent = paths[0].parent
    if any(p.parent != parent or p == parent for p in paths):
        raise ValueError('请选择同一目录下的文件或文件夹')
    original = snapshot(paths)
    base = paths[0].name if len(paths) == 1 else 'Archive'
    # A private directory on the same filesystem allows no-clobber publication.
    with tempfile.TemporaryDirectory(prefix='.mint-toolbox-zip-', dir=parent) as temporary:
        staged = Path(temporary) / 'archive.zip'
        run(['/usr/bin/zip', '-q', '-r', str(staged), '--',
             *['./' + p.name for p in paths]], cwd=parent, check=True)
        run(['/usr/bin/unzip', '-tqq', str(staged)], check=True)
        with zipfile.ZipFile(staged) as archive:
            actual = {}
            for entry in archive.infolist():
                name = entry.filename.removeprefix('./')
                if name in actual:
                    raise ValueError('ZIP 包含重复条目，保留原文件')
                with archive.open(entry) as stream:
                    actual[name] = None if entry.is_dir() else digest(stream)
        if actual != original or snapshot(paths) != original:
            raise ValueError('ZIP 内容或原文件发生变化，保留原文件')
        with staged.open('rb') as stream:
            os.fsync(stream.fileno())
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
                raise ValueError('原文件在压缩后变化，保留原文件')
            for path in paths:
                run(['/usr/bin/gio', 'trash', '--', str(path)], check=True)
        except Exception as exc:
            raise RuntimeError(f'ZIP 已保存到 {target}；移入回收站未全部完成：{exc}') from exc
        return target


def main():
    import argparse
    p = argparse.ArgumentParser(description='压缩为 ZIP 并将原文件移入回收站')
    p.add_argument('--gui', action='store_true')
    p.add_argument('paths', nargs='+')
    args = p.parse_args()
    try:
        if args.gui:
            answer = subprocess.run(['/usr/bin/zenity', '--question', '--title=压缩为 ZIP 并删除',
                '--no-markup', '--text=压缩并验证成功后，将所选原文件移入回收站。是否继续？'], check=False)
            if answer.returncode:
                return 0
        progress = None
        if args.gui:
            progress = subprocess.Popen(['/usr/bin/zenity', '--progress', '--pulsate',
                '--no-cancel', '--title=Mint Toolbox', '--text=正在压缩和验证，请稍候…'],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            target = archive_and_trash(args.paths)
        finally:
            if progress is not None:
                progress.terminate()
                progress.communicate()

        message = '已生成 ZIP，原文件已移入回收站：\n' + str(target)
        code = 0
    except Exception as exc:
        message, code = str(exc), 1
    if args.gui:
        subprocess.run(['/usr/bin/zenity', '--error' if code else '--info',
                        '--title=Mint Toolbox', '--no-markup', '--text=' + message], check=False)
    else:
        print(message, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == '__main__':
    sys.exit(main())
