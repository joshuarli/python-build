Upstream source: locked CPython 3.14.6, SHA-256 in `sources.lock.json`.
Origin: local Fil-C 3.14.6 qualification in `Modules/_ctypes/cfield.c`.
License: CPython PSF License Version 2.

Explanation: ctypes pointer constructors intentionally mask arbitrary Python
integers to the machine pointer width. The initial Fil-C capability fix
decoded through `PyLong_AsVoidPtr` directly, which raised OverflowError on
integers wider than 64 bits. Mask first, then decode the pointer-table
address. A genuine pointer integer retains its capability; an invented
numeric address stays invalid for dereference while preserving its numeric
`.value` representation.

Scope: `x86_64-filc-linux-musl` only.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` after the
prior Fil-C CPython patches to verified 3.14.6 source.

Regression test: `test_ctypes.test_pointers:test_c_void_p` and the focused
ctypes address, callback, and native library checks.
