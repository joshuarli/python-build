Upstream source: locked CPython 3.14.6 `Include/internal/pycore_code.h` and
`Objects/codeobject.c`.
Origin: project-authored adaptation of the capability-preserving inline-cache
pointer table in Fil-C's historical CPython 3.12 port; no patch bytes copied.
License: Python Software Foundation License Version 2.

Explanation: CPython's specialized inline caches store pointers in 16-bit code
units through `memcpy`. Fil-C does not preserve a pointer capability through
that integer code-unit representation, so reading a cached method descriptor
returns a pointer with null bounds and `_Py_IsImmortal` traps. Encode cached
pointers as integer handles in a Fil-C `zptrtable` and decode them on read.
The table is initialized before interpreter startup because inline-cache
helpers may run before Python runtime initialization is complete.

Scope: `x86_64-filc-linux-musl` only; cache size and opcode layout stay fixed.
Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` to verified
CPython 3.14.6 after earlier Fil-C patches.
Regression test: build and run `_bootstrap_python`, then exercise repeated
method specialization and the CPython specialization regression tests.
