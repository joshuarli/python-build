# Datetime immutable loader slots

The helper exposes `PyModExport__datetime_rs`, which returns a process-lifetime
immutable `PySlot` array. The pinned CPython loader prefers this export over a
legacy `PyInit` hook. CPython copies the slot metadata into each interpreter's
module and installs the existing seven `METH_FASTCALL` methods there. The
method-table pointer carries `PySlot_STATIC`: CPython
retains the immutable process-lifetime definitions after copying the slots.
There is no helper-owned writable `PyModuleDef` or cached Python reference. State size
remains zero; the no-op execution, clear, and free callbacks are preserved.
Multiple-interpreter support remains value 2, including isolated own-GIL
interpreters. GIL use is required; the ABI descriptor rejects a mismatched
non-stable interpreter major/minor version or free-threaded ABI. The descriptor
records `3.16.0a0`, but the loader does not validate its build version or require
the full release-level bits to match. The build source lock pins the exact
interpreter revision.

The internal loader export changes from `PyInit__datetime_rs` to
`PyModExport__datetime_rs`. Private C introspection also changes: the helper has
no original `PyModuleDef`, so `PyModule_GetDef` returns null; `PyModule_GetToken`
returns the process-lifetime slot-table address. Public datetime C types and
their C API capsule keep the original definition and contracts.
This helper is standalone, so no builtin registration
changes. The release artifact verifier checks installed/release byte parity;
its only explicit `PyInit` export test concerns `_base64`. Common bindings,
carrier, placement, controllers, C datetime types and public `datetime_CAPI`
remain unchanged. Unsupported parsing forms and missing-helper fallback still
run through the unchanged C glue. Every private method, its flags, errors,
metadata and algorithm body are preserved, including arbitrary private inputs.

This differs from the neutral borrowed-input/core-runtime, bounded formatting,
capsule/tuple-elimination and builtin-placement experiments. It avoids the
loader's writes to the image's global module definition. It does not remove
the Rust standard library, allocator, formatting runtime or existing common
bindings. Those components may still require the same writable image page.
Actual image layout, dirty-page ownership, physical saving and acceptance
remain unproved; there is no memory-win claim from source size or static types.

`tests/test_slot_export.py` has four observable contracts for all seven methods,
integer-conversion exception identity/reentry, public dynamic dispatch and C
capsule identity, reload, and bounded thread transfer. It contains no target
invocation or build step. `tests/slot_export_abi_oracle.c` is a separate native
header oracle: it requires the helper to be loaded, resolves the new export,
checks old-export absence, checks slot layout/ABI/methods against compiled C
headers, and never mutates the returned table. It must be compiled and invoked
only through the coordinator's separately reviewed native fixture procedure.

`tests/test_slot_export_own_gil.py` specifies one isolated-interpreter unit.
It needs a separately admitted runner: native interpreter startup and its
inner import boundary must be audited and bound before execution. The generic
fixture runner's ban on unadmitted interpreter creation must remain intact.
The unit exercises all seven methods and public C types in an own-GIL
interpreter, destroys it, and checks retained outer methods still work.
These fixtures have not run. Qualification requires actual native layout/export
proof, a clean release build, affected suites, full suites and the scheduled
replicated memory gate with unchanged workload outputs and Rust coverage.
