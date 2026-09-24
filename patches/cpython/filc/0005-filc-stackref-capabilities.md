Upstream source: locked CPython 3.14.6 stack reference definitions and the
tier-2 case generator/output (`Include/internal/pycore_structs.h`,
`Include/internal/pycore_stackref.h`, `Tools/cases_generator/stack.py`,
`Python/executor_cases.c.h`).
Origin: project-authored port for a CPython 3.14 feature absent from the
historical Fil-C 3.12 port. No third-party patch was copied.
License: Python Software Foundation License Version 2.

Explanation: CPython 3.14 stores object pointers in the integer `bits` member
of `_PyStackRef`. Fil-C then sees a numeric address without capability bounds
when an object attribute is read during interpreter initialization. Add a
pointer member to the same eight-byte union and use it whenever a stack ref
contains an object or frame pointer. `zorptr` and `zandptr` preserve the
capability while managing reference tag bits. Integer-only tagged values
continue to use `bits`. The tier-2 generator now emits pointer-member access
for typed pointers; its checked-in output is updated to match.

Scope: `x86_64-filc-linux-musl` only. The GIL-enabled release ABI is the
product target; this patch does not claim a free-threading Fil-C build.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` against the
verified CPython 3.14.6 source after earlier Fil-C patches. Regenerating
`executor_cases.c.h` with the patched tier-2 generator yields the same file.

Regression test: boot `_freeze_module`, run a real Python program with
attribute access and calls, and run the CPython stackref/attribute suites.
