# zlib helper module export

`_zlib_rs` remains a shared Rust extension behind the public native `zlib`
module and its Python codec facade. Its immutable `PyModExport__zlib_rs`
slot table replaces the writable legacy module definition initialized by
`PyModuleDef_Init`. The loader copies interpreter-owned metadata while the
slot and method tables remain process-lifetime static data. This is a load
memory hypothesis; source inspection establishes no physical saving.

The 13 FASTCALL methods, docstrings, exec callback, own-GIL support value 2,
zero module state, absent traverse callback, and no-op clear/free callbacks
are preserved. Stream state still belongs to capsules. Algorithms, public
stream types, native fallback, error translation, and monkeypatch dispatch
are unchanged. Rust std, dependencies, provider placement, and C glue remain
unchanged.

The private C introspection boundary changes: `PyModule_GetDef(_zlib_rs)`
returns null, and `PyModule_GetToken` returns the immutable export slot table
instead of the legacy definition. Code requiring the private legacy
`PyInit__zlib_rs` symbol or module-definition identity must use this new export
contract. Public zlib APIs are unaffected.

The export declares the full GIL-enabled CPython 3.16 ABI: info version 1.0,
flags 2, ABI/build versions `0x031000a0`. The loader checks ABI major/minor and
GIL compatibility; the source lock fixes the exact interpreter revision.
The supported 64-bit slot layout is asserted in Rust and in the native oracle.

`tests/test_slot_export.py` covers method metadata, retained callables, codec
buffer release, stream copies/tails, fallback, and public monkeypatch errors.
`tests/slot_export_abi_oracle.c` and `tests/test_slot_export_abi.py` check the
fresh loaded image against native headers, all method pointers, state size,
slot flags, token, and absence of the old initializer. The oracle must be
freshly compiled and admitted separately before use.
`tests/test_slot_export_own_gil.py` uses that admitted oracle in a fresh
isolated interpreter, leaves codec capsules alive during destruction, and
checks retained outer methods and capsules afterward. No fixture has yet run
for this source-only candidate; compiler, complete suites, fresh native ABI
qualification, own-GIL execution, and memory qualification remain required.
