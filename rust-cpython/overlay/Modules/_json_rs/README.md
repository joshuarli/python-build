# JSON call-local native storage

The codec uses a private, narrow CPython declaration module so its standalone
image does not depend on the shared binding crate's Rust runtime. The public
encoder and decoder, parser, byte-key memo, references, module tables and
capability policy are unchanged. The two-pass encoder writes into Python's
final Unicode allocation. Decoder workspaces and key memo use fallible
`PyMem_Realloc` owners with exactly one free on every exit.

Only workspace/key-memo allocation failures propagate `MemoryError`, after
preserving the raised exception across cleanup. Existing syntax, unsupported
input and conversion decline paths still return the original fallback marker.
The table remains half full; high-cardinality documents can require more
workspace than the former map. This is not a measured memory improvement.

`src/ffi.rs` contains only the API actually used by `src/lib.rs`. The concrete
layouts are the GIL-enabled, little-endian 64-bit object prefix, method table,
module base/definition and module slot. Type and long objects remain opaque.
Unicode data/kind access calls the already exported C functions; it does not
read Unicode bit fields or reconstruct their layouts. `build.rs` checks the
configured pointer size/GIL header, and target compile checks reject other
width/endian layouts. The native source pin is unchanged.

`tests/workspace_allocator_fixture.c` keeps the original controlled-process
allocator observer and adds header-typed signature/layout assertions and
live FASTCALL/definition ownership checks. Its allocator hooks must run in a
fresh process without concurrent interpreters. `tests/check_private_ffi.py`
compares live native method results with the explicit C decoder/encoder for
ASCII, Latin-1, BMP and astral values and checks original arity/decline behavior.
The original workspace ownership and allocation-failure fixtures remain.

No compiler, target fixture, suite or memory result is established by this
source transport. Fresh native-header/exports/provider checks, allocation
fixtures, capability/concurrency/teardown checks and full default-resource
suites are still required. The prior workspace regression belongs to its
original build; it is not a private-API qualification result for this image.
