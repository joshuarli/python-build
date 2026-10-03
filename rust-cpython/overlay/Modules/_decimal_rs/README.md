# Decimal immutable loader metadata

`PyModExport__decimal_rs` returns an immutable, process-lifetime `PySlot`
array. The pinned CPython 3.16 loader copies module metadata into each
interpreter's module and retains the method table marked `PySlot_STATIC`.
The helper no longer exposes `PyInit__decimal_rs` or owns a writable
`PyModuleDef` that `PyModuleDef_Init` modifies during its first import.

Both `METH_FASTCALL` functions, their names and docstrings, and all arithmetic,
Unicode conversion and error handling remain unchanged. `std`, BigUint,
Cargo dependencies, common bindings, build placement, and the native C
Decimal/context implementation remain unchanged. The C glue still dynamically
looks up `add_exact_integers` and `multiply_exact_integers` on `_decimal_rs`,
so monkeypatching and actual Rust activation are preserved. No execution,
traverse, clear, or free callbacks are added. State size defaults to zero;
multiple-interpreter support remains value 2 and GIL use remains required.

The ABI descriptor records the locked `3.16.0a0` GIL ABI. The loader checks
the non-stable major/minor version and GIL compatibility, but does not enforce
the recorded build version or complete release-level bits. The source lock
continues to pin the exact interpreter revision.

Private C introspection intentionally changes: `PyModule_GetDef` returns
NULL, and `PyModule_GetToken` returns the process-lifetime slot-table address.
Public `_decimal` keeps its original definition, native types and context ABI.
An observer that assumes the helper has an original `PyModuleDef` must be
adapted explicitly rather than treating its old result as qualification.

This removes a concrete import-time writer to helper image storage. It does
not establish that this definition uniquely dirtied a physical page: Rust
runtime, TLS, allocator and relocation storage can still occupy writable
image pages. Actual layout, dirty-page ownership and physical savings remain
unproved. The earlier arithmetic, Python-allocator, C/Rust image and core-only
experiments all retained the legacy module definition and initializer.

`tests/slot_export_abi_oracle.c` was frozen before production edits. Against
the accepted initializer, its new-export/old-export assertion is expected to
fail; this baseline failure has not been executed. The oracle requires the
helper image to be already loaded, checks native header layout, every slot,
ABI values, both method definitions and docstrings, legacy-export absence,
NULL definition and token identity. It never writes to the returned table.
Compile and invoke it only through a separately reviewed existing native
fixture runner with fresh source, header, artifact and ownership bindings.

The candidate has not been compiled or executed. Qualification still requires
a clean release build, complete `test_decimal`, `test_fractions`,
`test_numeric_tower` and `test_statistics` suites, the default-resource full
suite, public monkeypatch dispatch/context/error coverage and isolated
own-GIL lifetime checks. Physical protection and memory observations require
separate admission and the unchanged replicated memory gate. Historical
correctness and memory results do not qualify this source.
