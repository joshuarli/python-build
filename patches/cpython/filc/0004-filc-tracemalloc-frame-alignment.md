Upstream source: locked CPython 3.14.6,
`Include/internal/pycore_tracemalloc.h`.
Origin: project-authored forward port of the same change in Fil-C's
historical CPython 3.12.5 port at commit
`4d81217a0e270ee87396680624a5218a1bc4afe8` (Fil Pizlo).
License: Python Software Foundation License Version 2.

Explanation: the packed internal `tracemalloc_frame` can place a pointer at
an address four bytes off its required eight-byte alignment. Fil-C correctly
traps during `_PyTraceMalloc_Init` when the frozen-module helper starts.
Keep the upstream layout on ordinary targets and allow natural alignment in
the Fil-C build. All uses of the frame are internal and use `sizeof`.

Scope: `x86_64-filc-linux-musl` only.

Applicability check: apply with `patch -p1 --fuzz=0 --dry-run` against the
verified CPython 3.14.6 source after earlier patches.

Regression test: build and run `_freeze_module`, import `tracemalloc`, and
exercise `tracemalloc.start()` in the packaged interpreter.
