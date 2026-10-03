# Regex immutable loader export

`PyModExport__re_rs` returns a process-lifetime immutable `PySlot` array.
The pinned CPython 3.16 loader copies module metadata into each interpreter
instead of calling `PyModuleDef_Init` on a writable helper-owned definition.
The existing `prepare` and `search` method array remains process-lifetime
storage and carries `PySlot_STATIC`, because CPython retains the method
definitions after copying the slots. Method names, docs, `METH_FASTCALL`
flags, arities, result tuples and method monkeypatch behavior are preserved.

State size remains zero. The execution callback does no work, and the
original no-op clear/free hooks remain. GIL use is explicit; multiple
interpreter support stays `Py_MOD_MULTIPLE_INTERPRETERS_NOT_SUPPORTED` (0).
In particular, isolated own-GIL import still fails and public `re` continues
through its existing Python/C fallback there. This differs from the datetime
helper's own-GIL support. The shared regex arena, parse memo, cache, FIFO
policy, regex engine features, admission rules and standard-library allocator
remain unchanged. Public matching and capture construction retain their
existing Rust/C boundaries.

The internal loader symbol changes from `PyInit__re_rs` to
`PyModExport__re_rs`; this helper is a standalone image, without a builtin
registration change. Private C introspection intentionally changes:
`PyModule_GetDef` returns null without an exception, and `PyModule_GetToken`
returns the immutable slot-array address. `PyModule_GetStateSize` still
returns zero. No helper consumer requires the old definition token.
The full ABI descriptor requires CPython 3.16 and the GIL ABI; its version
fields are `0x031000a0`. The loader checks major/minor ABI compatibility,
not all build/release-level version bits. The source lock remains
`b812b4a7b9efaca46b98544a8633b7d7e454166b`.

`tests/test_immutable_export.py` specifies four ordinary native/public
contracts: admission/spans/metadata, nonexceptional bad inputs, public method
monkeypatch dispatch with C capture objects, and reload/held-method lifetime.
`tests/test_immutable_export_own_gil.py` specifies one separately admitted
isolated-interpreter rejection/fallback/destruction contract; it must not be
executed by a runner that forbids interpreter creation.
`tests/immutable_export_abi_oracle.c` is a separate native header oracle for
the new export, old export absence, all eleven slots, flags, zero state,
private definition/token behavior and unchanged slot bytes. It requires an
already loaded, bound helper image and never writes the returned tables.
The oracle uses the locked common typed bindings as its production interface,
not a new manual FFI layer or a replacement common crate.

This mechanism is separate from the closed matcher, clone/cache, arena,
retained-storage, allocator/no-std and image-placement trials. It removes
loader writes to the static module definition, rather than changing engine
or allocation lifetime. Existing mutable regex storage and std runtime may
still occupy the same image pages. There is no inferred physical saving.
The fixtures were specified before the production edit and remain unrun.
Qualification needs independent source review, a clean release build, native
ABI/export and interpreter-boundary proofs, all affected complete suites,
full suites and the coordinator's scheduled replicated memory verdict.
