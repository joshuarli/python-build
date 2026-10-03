# Standard record storage and private C interface

The helper keeps the existing standard-format eligibility and native `_struct`
fallback contract. The public wrapper, native `Struct` type, errors, and module
registration remain unchanged. The private module retains three `METH_FASTCALL`
methods, `m_size = 0`, null `m_slots`, and its existing clear/free callbacks.
Independent-GIL interpreters continue to reject the helper and use the public
native-C fallback.

`FormatText` retains the exact immutable Unicode object instead of copying its
UTF-8 bytes. `scan_format` validates every field and checked size before any
operation-storage allocation. A second scan initializes a precisely sized
`OperationStorage` allocation from `PyMem_Malloc`; its initialized prefix is the
only slice exposed, and its destructor returns the allocation with `PyMem_Free`.
Allocation size is checked against multiplication overflow and `isize::MAX`.

`pack_values` allocates the final Python bytes object, zeroes its private storage,
and fills fields before publishing it. Every unsupported-value path decrements
that private object and returns the existing `False` fallback sentinel. An
allocation failure returns NULL with the Python exception retained. Borrowed
source buffers are released on every scope exit. These algorithms and ownership
rules match the separately qualified owned-storage implementation.

`src/ffi.rs` declares only the C functions, opaque object/type addresses, buffer
layout, method table, and module definition this helper uses. The interface is
for the pinned 64-bit GIL-enabled CPython release ABI on LP64 platforms; the
build rejects free-threaded and reference-tracing configurations. Rust size and
offset assertions accompany the concrete layouts. The standalone crate no
longer depends on `cpython-sys`; the existing common bindings, static carrier,
registration and other modules are untouched. `byteorder` remains pinned with
its default features disabled. No Rust allocator or target `std` dependency is
introduced. The existing platform runtime is explicitly linked for the
standalone image, and the abort handler still calls `Py_FatalError`.

The optional `static-module` feature retains the existing exclusion of this
crate's standalone panic handler. The accepted static carrier does not consume
this helper; no carrier feature, placement, or own-GIL admission is changed.

`tests/test_owned_storage.py` retains six behavioral cases and warms the native
format cache before checking Rust-only format references. The earlier cold-cache
fixture failure belongs to the separately preserved qualification evidence, not
to this candidate's passed tests. `tests/check_allocation_ownership.py` and
`tests/check_own_gil.py` retain the three scoped allocation/provider cases and
one baseline own-GIL rejection/public-fallback case. `tests/allocation_fixture.c`
adds configured-header checks for every used function signature and type
address, buffer and module layouts, and all three live method pointers, flags
and self bindings. No new launcher or proof framework is required.

This candidate has source review evidence only. Compilation, complete suites,
newly bound native fixtures and physical memory qualification remain required;
the separate owned-storage results do not qualify this private interface.
