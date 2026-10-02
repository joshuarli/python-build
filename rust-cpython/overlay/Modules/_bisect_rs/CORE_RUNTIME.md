# Core-only bisect source candidate

This module candidate starts at accepted source `220bd52`, independently of
the later selected memory cohort and older rejected image experiments.
The target library uses `core` for interior mutability, C character types,
and pointer operations. Its existing typed `cpython-sys` dependency remains
unchanged. The exact core-only bindings foundation at `19330c94` is a shared
integration prerequisite; this branch does not edit or import its files.

All search allocation remains Python-owned. The comparison callback, truth
conversion, reference decrements, signed index conversion, unsigned midpoint
arithmetic, method table, initializer, and module slots are unchanged.
The standalone panic handler calls the existing generated
`cpython_sys::Py_FatalError` binding with a static message. Its declared
return type is never; CPython's fatal-error provider terminates through
`abort()` without returning across the Rust boundary.

The `static-module` feature suppresses this local panic handler while retaining
unconditional `no_std`. A carrier must enable that feature and provide exactly
one panic implementation. Carrier and shared bindings source belong to their
coordinator; this candidate adds no handwritten C declarations or dependencies.

This is a source checkpoint, not a compiled or measured result. Future
qualification requires standalone and carrier builds with the core-only
bindings, complete `test_bisect`, `test_datetime`, `test_free_threading`, and
`test_statistics`, and the five-case native fixture in `tests/test_core_search.py`.
The fixture checks signed-limit midpoints, callback/truth error identity,
temporary result release between probes, argument failures, and public keyed
search/insertion dispatch. No panic path is intentionally triggered.
