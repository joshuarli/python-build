Upstream source: locked CPython 3.14.6 `Include/cpython/longintrepr.h` and
`Objects/longobject.c`.
Origin: project-authored port for the 3.14 `PyLong_Export` API, which did not
exist in Fil-C's historical CPython 3.12 port.
License: Python Software Foundation License Version 2.

Explanation: `PyLong_Export` retains a reference to a large integer in its
reserved field until `PyLong_FreeExport`. CPython declares that field as an
integer and casts the object pointer through it. Fil-C then loses the pointer
capability, so marshaling a large integer traps in `Py_DECREF`. Use a typed
`PyObject *` reserved field for the Fil-C ABI and keep the reference as a
pointer throughout the export/free lifetime. The field remains private to
the API implementation and has the same width on this x86_64 target.

Scope: `x86_64-filc-linux-musl` only. Ordinary target headers are unchanged.
Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` to verified
CPython 3.14.6 after earlier Fil-C patches.
Regression test: marshal a large integer, run `sysconfig --generate-posix-vars`
during the full build, and run CPython's long and marshal suites.
