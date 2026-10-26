"""Private, no-follow synthetic-report storage primitives; no permissions issuer."""
import ctypes
import json
import os
import stat
from .common import canonical
from .engine import ToolRefusal

def _need(condition, code='INVALID_REPORT_ARTIFACT'):
    if not condition:
        raise ToolRefusal(code)

def _rename_exclusive(parent_fd, source, target):
    """Atomic, same-directory publication with OS-enforced no-replace semantics."""
    libc=ctypes.CDLL(None,use_errno=True)
    if hasattr(libc,"renameatx_np"):
        rename=libc.renameatx_np; flag=4  # Darwin RENAME_EXCL
    elif hasattr(libc,"renameat2"):
        rename=libc.renameat2; flag=1  # Linux RENAME_NOREPLACE
    else:
        _need(False,"REPORT_ATOMIC_PUBLICATION_UNSUPPORTED")
    rename.argtypes=(ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint)
    rename.restype=ctypes.c_int
    result=rename(parent_fd,os.fsencode(source),parent_fd,os.fsencode(target),flag)
    if result:
        _need(False,"REPORT_EXCLUSIVE_PUBLICATION_REFUSED")


def _open_directory(path):
    """Anchor every absolute component using no-follow directory descriptors."""
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW
    fd=os.open(path.anchor,flags)
    try:
        for part in path.parts[1:]:
            next_fd=os.open(part,flags,dir_fd=fd)
            os.close(fd); fd=next_fd
        return fd
    except BaseException:
        os.close(fd); raise

def _json(payload):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _need(key not in result)
            result[key] = value
        return result
    obj = json.loads(payload, object_pairs_hook=unique,
                     parse_constant=lambda _: _need(False))
    _need(payload == (canonical(obj) + "\n").encode())
    return obj


def _private(path, mode, directory=False):
    info = path.lstat()
    _need((stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
          and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == mode)


def _read_files(directory, names):
    """No-follow descriptor reads, bounded size, immutable owner-only files."""
    _private(directory, 0o500, True)
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        _need(set(os.listdir(fd)) == set(names))
        raw = {}
        for name in names:
            child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            with os.fdopen(child, "rb") as handle:
                info = os.fstat(handle.fileno())
                _need(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                      and stat.S_IMODE(info.st_mode) == 0o400 and info.st_size <= 16*1024*1024)
                raw[name] = handle.read(16*1024*1024 + 1)
                _need(len(raw[name]) == info.st_size)
        return raw
    finally:
        os.close(fd)
