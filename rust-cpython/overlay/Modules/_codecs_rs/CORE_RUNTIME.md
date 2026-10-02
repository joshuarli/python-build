The UTF-8 helper uses core-only Rust runtime APIs and leaves all output and
temporary storage in CPython. `core::str::from_utf8` provides the same UTF-8
validator re-exported by `std::str::from_utf8`; conversion engines, unsupported
input boundaries, consumed-byte accounting and Python reference ownership do
not change. The existing typed `cpython-sys` functions, method tables, module
slots and exported initializer remain intact.

The source requires the reviewed core-only `cpython-sys` foundation at
`19330c94`. That shared binding overlay belongs to the foundation owner and
is intentionally absent from this module-only commit. Its bindgen output uses
`core` and preserves the existing typed CPython API. The standalone helper's
panic handler calls the existing generated `Py_FatalError` binding, whose
non-returning fatal path aborts the process. No manual FFI or allocator is added.

The `static-module` feature suppresses this helper's standalone panic handler.
A static carrier must enable it and provide its own single panic owner. The
carrier and shared binding sources require separate integration; this change
does not qualify a core-only carrier by itself.

This is an unbuilt source candidate based on the accepted main checkpoint
`220bd52`, independently of rejected aggregate-layout ancestry. The old route
continues to call Rust through the eagerly imported UTF-8 helper. No runtime
or physical memory saving has been established. Qualification requires a clean
build with the shared foundation, standalone and carrier panic ownership checks,
the prepared `tests/test_core_utf8.py`, complete `test_codecs`,
`test_multibytecodec`, `test_charmapcodec`, `test_capi`, and `test_io` suites,
subinterpreter conversion checks, integrated full suites and a memory gate.
