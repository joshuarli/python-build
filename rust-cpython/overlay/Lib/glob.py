"""Filename globbing utility."""

import os
import sys

try:
    import _glob_rs
except ImportError:
    _glob_rs = None


__all__ = ["glob", "iglob", "escape", "translate"]

def glob(pathname, *, root_dir=None, dir_fd=None, recursive=False,
        include_hidden=False):
    """Return a list of paths matching a `pathname` pattern.

    The pattern may contain simple shell-style wildcards a la
    fnmatch. Unlike fnmatch, filenames starting with a
    dot are special cases that are not matched by '*' and '?'
    patterns by default.

    The order of the returned list is undefined. Sort it if you need a
    particular order.

    If `root_dir` is not None, it should be a path-like object specifying
    the root directory for searching.  It has the same effect as changing
    the current directory before calling it (without actually changing it).
    If pathname is relative, the result will contain paths relative to
    `root_dir`.

    If `dir_fd` is not None, it should be a file descriptor referring to a
    directory, and paths will then be relative to that directory.

    If `include_hidden` is true, wildcards can match path segments beginning
    with a dot ('.').

    If `recursive` is true, the pattern '**' will match any files and
    zero or more directories and subdirectories.
    """
    sys.audit("glob.glob", pathname, recursive)
    sys.audit("glob.glob/2", pathname, recursive, root_dir, dir_fd)
    if root_dir is not None:
        root_dir = os.fspath(root_dir)
    if _rust_eligible(pathname, root_dir, dir_fd, recursive):
        matches = _glob_rs.expand(pathname, include_hidden, root_dir or "")
        if matches is not None:
            return matches
    return list(_python()._iglob_python(pathname, root_dir, dir_fd, recursive,
                                        include_hidden))

def iglob(pathname, *, root_dir=None, dir_fd=None, recursive=False,
          include_hidden=False):
    """Return an iterator which yields the paths matching a `pathname` pattern.

    The pattern may contain simple shell-style wildcards a la
    fnmatch. However, unlike fnmatch, filenames starting with a
    dot are special cases that are not matched by '*' and '?'
    patterns.

    The order of the returned paths is undefined. Sort them if you need a
    particular order.

    If `root_dir` is not None, it should be a path-like object specifying
    the root directory for searching.  It has the same effect as changing
    the current directory before calling it (without actually changing it).
    If pathname is relative, the result will contain paths relative to
    `root_dir`.

    If `dir_fd` is not None, it should be a file descriptor referring to a
    directory, and paths will then be relative to that directory.

    If `include_hidden` is true, wildcards can match path segments beginning
    with a dot ('.').

    If `recursive` is true, the pattern '**' will match any files and
    zero or more directories and subdirectories.
    """
    sys.audit("glob.glob", pathname, recursive)
    sys.audit("glob.glob/2", pathname, recursive, root_dir, dir_fd)
    if root_dir is not None:
        root_dir = os.fspath(root_dir)
    if _rust_eligible(pathname, root_dir, dir_fd, recursive):
        return _rust_iglob(pathname, root_dir, include_hidden)
    return _python()._iglob_python(pathname, root_dir, dir_fd, recursive,
                                   include_hidden)

def _rust_eligible(pathname, root_dir, dir_fd, recursive):
    # Rust expands nonrecursive text patterns; everything else is Python's.
    return (
        _glob_rs is not None
        and dir_fd is None
        and not recursive
        and type(pathname) is str
        and (root_dir is None or type(root_dir) is str)
    )

def _rust_iglob(pathname, root_dir, include_hidden):
    matches = _glob_rs.expand(pathname, include_hidden, root_dir or "")
    if matches is None:
        yield from _python()._iglob_python(pathname, root_dir, None, False,
                                           include_hidden)
    else:
        yield from matches

def _python():
    """Import the pure Python implementation on first use."""
    import _glob_py
    return _glob_py

def escape(pathname):
    """Escape all special characters.
    """
    # Escaping is done by wrapping any of "*?[" between square brackets.
    # Metacharacters do not work in the drive part and shouldn't be escaped.
    drive, pathname = os.path.splitdrive(pathname)
    if isinstance(pathname, bytes):
        pathname = (pathname.replace(b"[", b"[[]").replace(b"*", b"[*]")
                    .replace(b"?", b"[?]"))
    else:
        pathname = pathname.replace("[", "[[]").replace("*", "[*]").replace("?", "[?]")
    return drive + pathname

def __getattr__(name):
    # `translate` and the private helpers (pathlib's globbers, the scandir
    # walkers) live in _glob_py so `import glob` does not import `re` and
    # its dependencies.
    if name.startswith("__"):
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    try:
        value = getattr(_python(), name)
    except AttributeError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    return value
