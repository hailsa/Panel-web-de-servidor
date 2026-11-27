"""Manage a dedicated directory with the collector's unprivileged identity."""
from contextlib import contextmanager
import ctypes
import os
import stat

ROOT = '/srv/shc-files'
DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
LIBC = ctypes.CDLL(None, use_errno=True)
RENAME_NOREPLACE = 1


def components(path):
    if path == '':
        return []
    if not isinstance(path, str) or len(path) > 2048:
        raise ValueError('Ruta inválida')
    parts = path.split('/')
    if any(part in {'', '.', '..'} or any(ord(c) < 32 for c in part) for part in parts):
        raise ValueError('Ruta inválida')
    return parts


@contextmanager
def directory(parts):
    fd = os.open(ROOT, DIRECTORY)
    try:
        for part in parts:
            child = os.open(part, DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def operate(payload):
    action = payload.get('action')
    parts = components(payload.get('path', ''))
    if action == 'list':
        with directory(parts) as fd, os.scandir(fd) as entries:
            rows = []
            for entry in entries:
                if len(rows) >= 2000:
                    return {'entries': rows, 'truncated': True}
                try:
                    info = entry.stat(follow_symlinks=False)
                except FileNotFoundError:
                    continue
                kind = ('directory' if stat.S_ISDIR(info.st_mode) else
                        'file' if stat.S_ISREG(info.st_mode) else 'other')
                rows.append({'name': entry.name, 'kind': kind, 'size': info.st_size, 'mtime': info.st_mtime})
        return {'entries': rows}
    if action not in {'mkdir', 'create', 'delete', 'move'} or not parts:
        raise ValueError('Operación inválida')
    with directory(parts[:-1]) as fd:
        name = parts[-1]
        if action == 'mkdir':
            os.mkdir(name, 0o750, dir_fd=fd)
        elif action == 'create':
            os.close(os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640, dir_fd=fd))
        else:
            mode = os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValueError('Este tipo de entrada no se puede administrar')
            if action == 'delete':
                (os.rmdir if stat.S_ISDIR(mode) else os.unlink)(name, dir_fd=fd)
            else:
                destination = components(payload.get('destination'))
                if not destination:
                    raise ValueError('Indicá una ruta de destino con nombre')
                with directory(destination[:-1]) as target:
                    if LIBC.renameat2(fd, os.fsencode(name), target, os.fsencode(destination[-1]), RENAME_NOREPLACE):
                        error = ctypes.get_errno()
                        raise OSError(error, os.strerror(error))
    return {'accepted': True}
