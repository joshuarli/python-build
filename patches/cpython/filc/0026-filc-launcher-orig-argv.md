Upstream source: locked CPython 3.14.6, SHA-256 in `sources.lock.json`.
Origin: local Fil-C 3.14.6 qualification in `Python/initconfig.c`.
License: CPython PSF License Version 2.

Explanation: The bundled Fil-C loader receives the private
`python3.14.real` ELF as argv[0]. The public launcher already provides its
path in `PYTHONEXECUTABLE`, which `getpath.py` uses for `sys.executable`.
Use the same path for `sys.orig_argv[0]` so child process introspection
reflects the command users invoked. Preserve all other arguments.

Scope: `x86_64-filc-linux-musl` only.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` to verified
CPython 3.14.6 source before configure.

Regression test: `test_sys:test_orig_argv` and installed launcher smoke.
