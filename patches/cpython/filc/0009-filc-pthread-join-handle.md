Upstream source: locked CPython 3.14.6 `Include/internal/pycore_pythread.h`.
Origin: project-authored port for CPython 3.14's joinable-thread handle API;
this API was absent from Fil-C's historical CPython 3.12 port.
License: Python Software Foundation License Version 2.

Explanation: Pizfix musl represents `pthread_t` as a pointer. CPython 3.14
stores a joinable thread's handle in `Py_uintptr_t`, losing its Fil-C bounds.
Passing it back to `pthread_join` traps when musl reads the thread structure.
Use a pointer-valued handle in the Fil-C interpreter while keeping the
integer thread identity for comparison and Python's `get_ident()` API.

Scope: `x86_64-filc-linux-musl` only; other targets' handle type is unchanged.
Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` to verified
CPython 3.14.6 after earlier Fil-C patches.
Regression test: join contending Python threads and run `test_threading`,
`test_thread`, and the installed runtime smoke.
