#!/usr/bin/python3
"""Open HomeBackUp locks without following links or truncating root files.

Re-exec the caller with the acquired lock inherited on fd 8/9. Does not create
backups, enable timers or remove any data.
"""
import fcntl
import os
from pathlib import Path
import stat
import sys

LOCKS = {
    8: '/run/lock/homebackup-monthly.lock',
    9: '/media/andrew/HomeBackUp/.mint-recovery.lock',
}


def locked_exec(argv):
    if os.geteuid() != 0:
        raise PermissionError('HomeBackUp locking requires root.')
    if len(argv) < 4:
        raise ValueError('Usage: safe_lock.py FD LOCK /usr/bin/bash SCRIPT [ARG ...]')
    fd_number = int(argv[0])
    location, program = argv[1:3]
    if fd_number not in LOCKS or location != LOCKS[fd_number]:
        raise ValueError('Unexpected HomeBackUp lock path.')
    if program != '/usr/bin/bash':
        raise ValueError('Only a bash script may inherit the HomeBackUp lock.')
    path = Path(location)
    parent_fd = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        parent_info = os.fstat(parent_fd)
        if (parent_info.st_uid != 0 or
                ((parent_info.st_mode & 0o022) and not (parent_info.st_mode & stat.S_ISVTX))):
            raise PermissionError('Lock directory is writable by untrusted users.')
        fd = os.open(path.name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=parent_fd)
    finally:
        os.close(parent_fd)
    try:
        meta = os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode) or meta.st_uid != 0 or meta.st_nlink != 1:
            raise PermissionError('Unsafe lock owner, type or link count; refusing to proceed.')
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if fd != fd_number:
            os.dup2(fd, fd_number, inheritable=True)
            os.close(fd)
        else:
            os.set_inheritable(fd, True)
        os.execv(program, argv[2:])
    finally:
        # execv() never returns on success.
        if fd != fd_number:
            try:
                os.close(fd_number)
            except OSError:
                pass


if __name__ == '__main__':
    try:
        locked_exec(sys.argv[1:])
    except (OSError, ValueError, PermissionError) as exc:
        print('SECURITY ERROR: HomeBackUp lock refused: ' + str(exc),
              file=sys.stderr, flush=True)
        sys.exit(1)
