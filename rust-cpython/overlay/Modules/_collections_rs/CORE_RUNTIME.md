The iterable subtraction helper allocates all operation state through CPython.
Its Rust runtime now uses `core` for interior mutability, C primitive types and
pointer operations, with an unconditional `no_std` declaration. The counting
algorithm, callback order, Python exception propagation, temporary reference
ownership, method definitions, module slots and initializer are unchanged.
Existing handwritten CPython declarations retain their signatures; no new FFI
declaration, allocator or dependency is added.

This module-only source checkpoint starts from accepted `220bd52`. It requires
the separately owned typed core-only `cpython-sys` foundation at `19330c94`
and its subsequent shared integration. The common bindings and carrier are
intentionally absent from this commit. Their prerequisite is pending; the
module has not been compiled, imported or measured in this form.

The standalone panic handler uses the existing generated `Py_FatalError`
binding with a static message. Its non-returning provider aborts the process.
The `static-module` feature suppresses this handler while retaining `no_std`,
so a carrier can provide exactly one panic owner. Standalone and carrier builds
must separately establish linkage and panic ownership after shared integration.

The four prepared cases in `tests/test_core_subtraction.py` cover C tally
parity, public Rust reachability, exact callback error identity, release of
temporary callback/subtraction results, and nested reentry. They remain
unexecuted. Later qualification requires the fixture under the reviewed TEST
runner, complete `test_collections`, `test_defaultdict`, `test_deque`,
`test_ordered_dict`, `test_userdict`, `test_userlist`, and `test_userstring`,
subinterpreter operation checks, integrated full suites and ROOT's memory gate.
No target runtime or memory-improvement claim is made from source inspection.
