# UUID core runtime

`src/lib.rs` uses `core` and the typed `cpython-sys` boundary. The pinned
`uuid` crate keeps its v3/v4/v5 algorithms and `getrandom` provider; its
`std` feature is disabled. Parsing borrows UTF-8 while its buffer export
is alive. Formatting uses a 36-byte stack buffer, copied into Python bytes.
No Rust allocator is required. Native `_uuid`, Python initialization,
provider/path/getnode selection, method metadata and module layout remain
unchanged.

Standalone panic handling aborts through the platform C runtime. The
`static-module` feature leaves panic ownership to the interpreter carrier.
Qualification requires the reviewed common core-only `cpython-sys` and its
Darwin System link repair; those prerequisites are not part of this patch.

This source candidate has no build, runtime correctness or memory result.
`tests/test_core_contract.py` covers helper output, errors, RFC bits, name
vectors, exporter release and observable public UUID behavior. Clean builds,
full affected suites, native ABI/ownership checks and the memory gate remain
required before acceptance.

The standalone route declares only its used CPython C APIs in `src/ffi.rs`,
without overriding the shared binding crate or changing core placement.
The object head initializer is scoped to the pinned 64-bit little-endian,
GIL-enabled ABI; runtime objects remain opaque. `tests/abi_fixture.c` checks
header sizes, offsets and static flags, then checks live module state, slots,
method flags, registered pointers and bound module identity.
`tests/check_live_abi.py` drives every registered pointer through its exact
C calling convention. These new declarations require a fresh clean build
and live observer qualification before any memory result is eligible.
