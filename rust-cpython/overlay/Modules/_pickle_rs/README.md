# Pickle immutable loader metadata

`_pickle_rs` remains a standalone shared extension. Its loader entry point is
`PyModExport__pickle_rs`, returning a process-lifetime immutable `PySlot` table
instead of initializing a writable global `PyModuleDef`. CPython copies the
metadata into each interpreter's module. The two existing `METH_FASTCALL`
methods retain their names, documentation, algorithms and mutable module
bindings. `PySlot_STATIC | PySlot_INTPTR` marks the retained method-table
pointer's process-lifetime ownership.

State size remains zero. There is no execution or traversal hook, and the
original clear/free callbacks remain unchanged. Multiple-interpreter support
remains value 2, including isolated own-GIL interpreters. The ABI descriptor
requires the non-stable CPython 3.16 GIL ABI and records version `3.16.0a0`.
The loader checks major/minor and GIL compatibility, rather than requiring
every release-level bit or validating the build-version field. The source
lock independently pins the exact interpreter revision. Both Rust layout
assertions and the native header oracle require the supported 64-bit ABI.

Private C introspection changes deliberately: `PyModule_GetDef(_pickle_rs)`
returns null, and `PyModule_GetToken` returns the static slot-table address.
The old `PyInit__pickle_rs` export is absent. Public `_pickle` C types, memo
behavior, protocol/buffer options, exceptions and fallback remain unchanged;
`pickle.dump`, `dumps`, `load` and `loads` still resolve the mutable helper
methods for their supported inputs. The Python facade, C glue, common bindings,
static carrier, dependency graph and Rust standard library are untouched.

This targets writes to mapped module metadata, distinct from prior helper
deferral, inline codec/image placement and transient parsing work. It does not
remove an allocator, cache or serializer allocation. Existing Rust runtime
data may still occupy the same writable image pages; physical memory savings
and acceptance have not been established.

`tests/test_slot_export.py` specifies four ordinary behavior units covering
private metadata, supported and unsupported graphs, consumed-byte boundaries,
all four public dispatch paths, mutable method replacement, C memo aliases,
missing-helper fallback, reload and bounded thread transfer.
`tests/slot_export_abi_oracle.c` is a separate read-only native oracle for the
loaded image's export, header-defined slots, ABI descriptor, zero state size,
token, original method definitions and legacy-export absence. It requires a
fresh coordinator-owned observer compile and admitted native execution.
`tests/test_slot_export_own_gil.py` specifies one isolated-interpreter lifetime
unit with inner module mutation and retained outer callables after destruction.
Its startup/import boundary needs separate admission; the ordinary runner's
ban on unadmitted interpreter creation must remain intact.

The fixtures were frozen before the production change. The old native oracle
is expected to fail its new-export assertion, but no baseline or candidate
execution has occurred. Qualification requires that actual fail-first proof,
clean build, native header/export checks, the complete affected suites
(`test_pickle`, `test_picklebuffer`, `test_pickletools`, `test_shelve`,
`test_email`, `test_ctypes`, `test_pyclbr`), full suites and ROOT's scheduled
replicated memory gate with unchanged Rust coverage and workload outputs.
