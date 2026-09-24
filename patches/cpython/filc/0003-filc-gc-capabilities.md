Upstream source: locked CPython 3.14.6, `Include/internal/pycore_interp_structs.h`,
`Include/internal/pycore_gc.h`, `Python/gc.c`, and `Objects/object.c`.
Origin: project-authored forward port of the capability-preserving GC and
trashcan semantics in Fil-C's historical CPython 3.12.5 port, commit
`4d81217a0e270ee87396680624a5218a1bc4afe8` (Fil Pizlo).
License: Python Software Foundation License Version 2 for the CPython edits;
Fil-C's `stdfil.h` helpers are used through the pinned toolchain headers.

Explanation: GC next/previous links and the trashcan delete chain contain
real pointers, sometimes with low-bit flags. Fil-C loses capability bounds
when these pointers are stored as integers. Preserve pointer metadata in
the fields, use `zandptr` and `zorptr` for flag changes, and use `zretagptr`
when replacing a GC predecessor while keeping its flags. GC reference
counts still occupy the same temporary slot during a collection, but are
explicitly interpreted as integers while that slot is in count state.

Scope: `x86_64-filc-linux-musl` only. The ordinary targets continue to use
the upstream integer representation.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` against the
verified CPython 3.14.6 source after shared and earlier Fil-C patches.

Regression test: run cyclic GC, weakref callbacks and finalizers, then a
deep recursive container destruction path that exercises trashcan chaining.
