Upstream source: locked CPython 3.14.6, SHA-256 in `sources.lock.json`.
Origin: local Fil-C 3.14.6 qualification in `Modules/getpath.py`, applied
after the common executable-discovery patch.
License: CPython PSF License Version 2.

Explanation: the Fil-C launcher executes the bundled Pizfix loader, so
CPython sees that loader as its real kernel executable. The launcher already
sets `PYTHONEXECUTABLE` to itself for `sys.executable`, but CPython sets
`sys._base_executable` to the loader. Tests and applications that launch
`sys._base_executable` then pass Python options to the loader and fail. Use
the launcher's `PYTHONEXECUTABLE` path as the base executable on this target.
The launcher overwrites any inherited value before starting Python.

Scope: `x86_64-filc-linux-musl` only. Other targets retain their existing
getpath behavior.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` to verified
CPython 3.14.6 source after the common getpath patch.

Regression test: `tests/filc_runtime_smoke.py` asserts equality and
launches a child through `sys._base_executable`; installed `test_os.test_getppid`
previously launched the loader instead of Python.
