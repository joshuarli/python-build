# Marshal route-local CPython bindings

The standalone `_marshal_rs` target uses `core` and the local declarations
in `src/ffi.rs` instead of importing the target-side `cpython-sys` crate.
`cpython-build-helper` remains a host-side build dependency. The common
bindings, interpreter Rust carrier and other routes remain unchanged.
The empty `static-module` feature suppresses this route's aborting panic
handler when a carrier supplies the handler; this change does not add
marshal to any carrier.

The local layouts describe the pinned 64-bit little-endian, GIL-enabled
CPython release ABI with 30-bit integer digits. Objects accessed by field
have precise layouts, including the full reference-count union, tuple
cached hash, compact integer value, long export and native-digit layout.
Type objects, method tables and long writers are opaque pointer-only types.
Rust size, alignment and field-offset assertions cover the precise layouts.
`tests/abi_fixture.c` independently checks the corresponding native headers,
all 48 used function signatures, static immortal head and module slot values.
The native observer reads live object fields, validates the module definition,
and invokes both functions through the actual `_marshal_rs._api` capsule.

`tests/check_live_abi.py` prepares ten observable cases: native module slots,
literal wire records independent of public dispatch,
container fields, long boundaries, strings and numeric records, shared/cyclic
references, code-object construction and allow-code errors, unsupported/malformed
record rejection and MEM-domain allocation failures. The failure observer arms
only around a synchronous capsule call and restores the original allocator
before result construction. It proves the capsule's existing NULL-without-error
rejection and recovery contract, without changing the public fallback.
The selected writer and reader failure cases necessarily grow their reference
tables. This observer is for isolated, GIL-held native qualification; it does
not qualify concurrent allocator hooks or subinterpreter allocation failures.

The serializer, decoder, Python ownership, size/depth limits, bytes growth,
C glue, capsule ABI, allow-code rules, rejection/error clearing and module
slots retain their accepted behavior. No layout padding or linker placement
is retuned. The source contract can be reviewed before compilation, but a
fresh clean build, full marshal-affected suites, compiled header observer and
artifact closure proof are required to qualify the manual bindings. A source
`no_std` attribute alone is not proof of the linked runtime closure or a memory
improvement. ROOT schedules all runtime and memory qualification.
