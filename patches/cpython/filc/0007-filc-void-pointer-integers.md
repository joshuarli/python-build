Upstream source: locked CPython 3.14.6 `Objects/longobject.c`, informed by
Fil-C's historical CPython 3.12 pointer-integer port and its `stdfil.h` API.
Origin: project-authored forward port; no historical patch bytes copied.
License: Python Software Foundation License Version 2.

Explanation: `PyLong_FromVoidPtr` exposes a pointer's integer address for
`id()`, symbol-table keys, and deferred annotation AST nodes. The ordinary
`PyLong_AsVoidPtr` casts that number back to an unbounded pointer, which loses
its Fil-C capability and traps when the compiler dereferences a deferred
annotation. A strong exact pointer table preserves the capability while the
Python integer remains the pointer's original numeric value. The table
releases entries when their objects are freed. Arbitrary integers decode to
invalid capabilities, preserving Fil-C's bounds checks.

Scope: `x86_64-filc-linux-musl` only; public integer values and CPython's
ordinary targets retain their prior behavior.
Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` to verified
CPython 3.14.6 after earlier Fil-C patches.
Regression test: run code with deferred annotations, compare `id()` values,
and run CPython's compile, annotation, and long integer suites.
