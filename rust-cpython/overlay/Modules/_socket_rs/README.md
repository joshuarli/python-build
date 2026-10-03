# Socket immutable loader slots

The standalone helper exports `PyModExport__socket_rs`, returning an immutable
process-lifetime six-entry `PySlot` array. The locked CPython loader prefers
this export to a legacy `PyInit` entry point and copies the metadata into each
interpreter's module. The existing four `METH_FASTCALL` definitions carry
`PySlot_STATIC`, so installed method objects retain the process-lifetime
definitions without copying or changing them. No global Python object is
cached. Module state size remains zero; execution, traversal, clear and free
callbacks remain absent. Multiple-interpreter support remains value 2 and
GIL use remains required.

The ABI descriptor records the non-stable 64-bit GIL ABI `3.16.0a0`. The loader
checks interpreter major/minor and GIL compatibility, rather than requiring
the complete release-level bits or build version to match. The source lock
pins the exact interpreter revision. Rust and native-header assertions cover
the `PySlot` and `PyABIInfo` layouts and slot flags.

The private helper's loader export changes from `PyInit__socket_rs` to
`PyModExport__socket_rs`. Its original `PyModuleDef` disappears, so private
`PyModule_GetDef` returns null and `PyModule_GetToken` returns the static slot
table pointer. This is an intentional private introspection boundary. The
public native `_socket.socket` type, `CAPI` capsule, C socket methods, Python
facade, dynamic helper lookup, missing-helper fallback, monkeypatching,
coercion and errors remain unchanged. Every Rust callback body and method
definition is preserved, including borrowing buffers while the GIL is
released, signal checking, descriptor ownership and IPv6 spelling.

`_socket_rs` remains in `Setup.local`'s shared section and has no static carrier
dependency or builtin registration. Cargo, generated common bindings and
controller code remain unchanged. This mechanism avoids loader writes to the
global legacy module definition. It retains `std`, its allocator and all
address and I/O algorithms. It differs from local-FFI/core-runtime and bound
facade experiments. Source metadata does not establish image placement,
dirty-page ownership, physical memory saving or acceptance.

`tests/test_slot_export.py` specifies four ordinary units for method metadata,
address conversion, callback errors, borrowed-buffer release, public dispatch
and fallback, borrowed descriptor I/O, reimport/reload and thread transfer.
`tests/slot_export_abi_oracle.c` requires an already-loaded helper and checks
the new export, old-export absence, exact slots, state size zero, private
definition/token boundary and installed native method identity against actual
interpreter headers. It never mutates the slot table.
`tests/test_slot_export_own_gil.py` specifies one independent-GIL interpreter
unit and outer-method survival after interpreter destruction. Native observer
compilation/loading and interpreter creation require separately reviewed,
owned native fixture declarations; the generic ordinary audit remains intact.

Only SOURCE preparation and host AST checks have occurred. These fixtures have
not executed. Qualification requires a clean locked build, the complete socket
and neighboring suites, full suites, native ABI/export evidence and all six
fixture units, followed by the coordinator's scheduled replicated memory gate
with unchanged outputs and Rust coverage.
