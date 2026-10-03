# Rust HMAC ownership

`src/lib.rs` is core-only and retains the typed `cpython-sys` interface. Integration requires the reviewed core-only `cpython-sys` foundation and its corrected default-System/no-builtin configuration; this isolated main-base patch does not change that shared dependency.

The arguments tuple keeps the immutable algorithm-name Unicode object alive while key and data buffers are acquired and released. Name conversion, buffer acquisition, and unsupported-algorithm errors retain their original order. Buffer owners remain alive until state construction or one-shot computation has completed.

Each state uses the same malloc/free allocation domain as the previous default System allocator on supported 64-bit macOS and Linux targets. Compile-time checks require a nonzero state size and alignment at most 16 bytes. State allocation remains infallible: exhaustion aborts, matching the previous `Box::new` contract. Capsule creation failure and capsule destruction run the same state destructor before freeing storage, preserving the pinned crypto zeroize features' destruction behavior. No Python allocation domain or capsule layout changes.

Finalization clones the existing state and copies its fixed output into a 64-byte stack buffer. Hex encoding uses a separate 128-byte stack buffer. Python bytes and Unicode constructors copy the used prefix before these buffers leave scope. Original state contents remain available for further updates and copies.

Crypto versions, zeroize features, backend selection, provider checks, methods, module definition, slots, and GIL contract remain unchanged. The source-only fixture covers native outputs against OpenSSL, block/key boundaries, retained copies, buffer callback lifetime, and error ordering. It has not run at source freeze. Build, complete affected suites, admitted interpreter qualification, and memory-only workload qualification remain required; image-runtime removal alone does not establish an RSS improvement.

The standalone route declares only its used CPython C APIs in `src/ffi.rs`,
without overriding the shared binding crate or changing core placement.
The object head initializer is scoped to the pinned 64-bit little-endian,
GIL-enabled ABI; runtime objects remain opaque. `tests/abi_fixture.c` checks
header sizes, offsets and static flags, then checks live module state, slots,
method flags, registered pointers and bound module identity.
`tests/check_live_abi.py` drives every registered pointer through its exact
C calling convention. These new declarations require a fresh clean build
and live observer qualification before any memory result is eligible.
