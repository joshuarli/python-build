Upstream source: locked CPython 3.14.6, SHA-256 in `sources.lock.json`.
Origin: local Fil-C 3.14.6 qualification in `_ctypes/cfield.c`.
License: CPython PSF License Version 2.

Explanation: `ctypes.addressof()` uses `PyLong_FromVoidPtr`, which the Fil-C
port backs with an exact capability-preserving pointer table. The ctypes
field setters for `c_void_p`, `c_char_p`, and `c_wchar_p` instead used raw
integer-to-pointer casts, discarding that capability. Use the matching
`PyLong_AsVoidPtr` decoder for Fil-C and propagate its conversion errors.
This restores ordinary address round trips such as
`ctypes.memset(ctypes.addressof(value), ...)` and shared ctypes allocation.

Scope: `x86_64-filc-linux-musl` only. Other targets retain their original
masking and cast behavior.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` to verified
CPython 3.14.6 source before configure.

Regression test: `buildsys/validate_filc.py` checks all three pointer field
types and an actual `ctypes.memset` write. The latter trapped on a numeric
pointer before this patch; rerun multiprocessing shared ctypes tests too.
