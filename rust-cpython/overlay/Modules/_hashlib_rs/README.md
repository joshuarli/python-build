# Rust hashlib helper

`PyModExport__hashlib_rs` exports immutable, process-lifetime `PySlot`
metadata. CPython copies the module metadata into each interpreter's module
object and retains the static method table. The export replaces the writable
`PyModuleDef` and its initialization writes; its effect on load footprint is
unmeasured.

The ABI descriptor declares the full CPython 3.16.0a0 GIL ABI. The loader
checks major/minor version and GIL compatibility; the source lock supplies
the exact interpreter revision. This helper remains a shared extension.
Its zero-byte module state, `exec_module`, `clear_module`, `free_module`,
`new` method table, and shared-GIL multiple-interpreter capability are
preserved. Own-GIL interpreters remain unsupported. The HASH heap type is
created separately in each interpreter; hash instances retain and release
their heap-type references exactly as before.

For private native observers, `PyModule_GetDef()` now returns NULL and
`PyModule_GetToken()` identifies the static slot array instead of the old
definition. There is no `PyInit__hashlib_rs` export. Consumers must use the
slot loader and must not treat the token as a `PyModuleDef`.

Rust standard-library use, algorithm state ownership, crypto dependency
features, digest allocation, method and getset tables, and Python/OpenSSL
provider validation remain unchanged. Public `hashlib` routing, fallback,
error ordering, and helper monkeypatch behavior are unchanged.

`tests/slot_export_abi_oracle.c` checks typed slot layout, every metadata
entry, method flags and pointers, state size, loader symbols, and the private
definition/token boundary, then invokes the native factory. The Python
fixtures exercise all six algorithms, public dispatch, retained factories,
copy/reload/GC ownership, shared-GIL interpreter-local types, and own-GIL
import rejection. The interpreter fixture requires separately authorized
startup and destruction qualification. No compiler, fixture, suite, or
memory measurement has run for this source candidate.
