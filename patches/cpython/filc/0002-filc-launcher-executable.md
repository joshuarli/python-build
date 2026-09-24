Upstream source: locked CPython 3.14.6, `Modules/getpath.c`.
Origin: project-authored launcher integration; no third-party code copied.
License: Python Software Foundation License Version 2.

Explanation: The relocatable launcher invokes its bundled Fil-C loader with
the real interpreter as an argument, and sets CPython's existing
`PYTHONEXECUTABLE` override to the launcher path.
`getpath.py` already uses that override for `sys.executable` while resolving
the install prefix from the real executable. The override must be cleared
during initialization so unrelated child programs do not inherit it. CPython
already clears `__PYVENV_LAUNCHER__` by the same `env_to_dict` mechanism.

Scope: `x86_64-filc-linux-musl` only. The ordinary Linux and macOS patch sets
do not include this file.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` against the
verified CPython 3.14.6 source after the shared patch set.

Regression test: packaged Fil-C validation checks `sys.executable`, runs a
Python child through `subprocess` and multiprocessing spawn, and checks that
`PYTHONEXECUTABLE` is absent from `os.environ` after startup.
