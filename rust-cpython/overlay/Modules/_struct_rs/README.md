# Struct helper module metadata

The helper exports `PyModExport__struct_rs`, which returns a process-static
immutable nine-slot table. CPython copies module metadata and creates methods
owned by each interpreter instead of initializing the mapped `PyModuleDef`
object in place. The method definitions and ABI record also remain immutable
for the process lifetime. This is a candidate for reducing dirty mapped data;
no physical memory saving follows from source or section placement alone.

The three existing `METH_FASTCALL` methods, documentation, clear/free hooks,
zero module state, format parser, allocations, buffer release and error/fallback
semantics are unchanged. Rust `std`, dependencies, compiler flags, COMMON
bindings, static carrier and C struct glue are unchanged. Public `struct.Struct`
and `struct.error` remain the native C types. Attribute monkeypatch dispatch and
native fallback still cross the existing helper boundary.

The slot ABI is the locked 64-bit CPython 3.16.0a0 GIL build. The loader checks
major/minor ABI and GIL compatibility; the recorded build version does not
replace the exact source lock. Slot identifiers omitted by generated macros
are checked against native headers. Shared-GIL subinterpreters remain admitted
and own-GIL direct helper imports remain rejected. Public struct operations can
still use their existing native C fallback in an isolated interpreter.

Private extension introspection intentionally changes: `PyModule_GetDef` is
NULL, and `PyModule_GetToken` returns the immutable slot table pointer. The old
`PyInit__struct_rs` export and mutable module definition disappear. Native tests
check the exact nine slots, method pointers/flags/documentation and module
state, stable token and byte-identical metadata before and after helper calls.
Ordinary tests cover public Rust dispatch, monkeypatch fallback, retained
callables, reload, thread transfer and buffer-export release. The own-GIL test
checks rejection plus public C fallback and outer callable survival. All are
prepared for later controlled qualification; source preparation is not a
compiler, runtime, native ABI or memory verdict.
