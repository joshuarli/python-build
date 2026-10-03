# Collections immutable loader slots

The private counting helper exports `PyModExport__collections_rs`, returning
an immutable process-lifetime seven-entry `PySlot` array. The pinned loader
copies its metadata into each interpreter's module. This removes the helper's
writable global `PyModuleDef` and its `PyModuleDef_Init` write; it retains the
original Rust standard library and counting algorithm.

The entries are ABI descriptor, name, documentation, method table, execution
callback, multiple-interpreter support and zero sentinel. The methods pointer
uses `PySlot_INTPTR | PySlot_STATIC`: callable objects retain pointers into
the immutable method definitions. The execution callback still returns zero.
Omitted state size remains zero, and omitted traverse/clear/free callbacks
remain null. Omitted GIL slot still requires the GIL. The support value remains
2, admitting isolated interpreters with their own GIL. There are no global
Python references; every iterator, key, count and result is call-owned.

All `subtract_iterable` instructions, exception propagation, reference
ownership, callback order and `METH_FASTCALL` method metadata remain unchanged.
Public `Counter.subtract` still dispatches iterable counting into Rust, accepts
dynamic helper monkeypatches and retains its missing-helper fallback. Native
deque, defaultdict and OrderedDict types are unaffected. This helper has no
public C capsule; no native public collections type or C glue changes.

The intentional private C boundary changes: `PyInit__collections_rs` is absent,
`PyModExport__collections_rs` is present, `PyModule_GetDef` returns null, and
`PyModule_GetToken` returns the static table address. That token and borrowed
method definitions remain valid for the process. The non-stable ABI descriptor
records 3.16.0a0 and GIL use. The loader validates major/minor with mask
0xffff0000 and free-threaded/GIL compatibility; it does not validate
`build_version` or full release bits. The source lock supplies the exact
revision. The supported 64-bit typed layouts are asserted in Rust and checked
against actual native headers by the separately compiled C oracle.

The complete slot iterator validates module IDs, nulls, duplicate policy and
static method ownership. This table supplies only unique known IDs, non-null
metadata/callbacks, scalar support2 and a zero sentinel. ABI presence is
mandatory but not required to be first; this table puts it first. Reserved
fields are zero and checked by the oracle even though the iterator does not
validate them. No create/custom token/nested/optional/legacy slot is used.

`tests/test_slot_export.py` specifies four observable cases: C counting parity
and arity/metadata, public real-Rust delegation/monkeypatch/fallback/native
type identity, iterator/get/subtract/set error identity and temporary-release
with reentry, and reload/thread transfer with retained callable ownership.
`tests/slot_export_abi_oracle.c` specifies one read-only native header/export
unit including method flags/docs, zero state, private definition and token.
`tests/test_slot_export_own_gil.py` specifies one isolated-interpreter
lifetime unit. Interpreter creation requires a separately admitted native
startup and inner import audit boundary; the ordinary generic fixture runner
must not directly execute this raw fixture. These sources have not run.

This mechanism is distinct from discarded OrderedDict fallback construction,
namedtuple closure grouping, core-only runtime and image placement experiments.
No object-size, source-size or physical saving is inferred. The original
standard library/runtime may still dirty the same image data page. Qualification
requires independent complete loader/ABI SOURCE review, fresh compiler/link
and clean58, all seven collections suites and complete CPython suites,
ordinary4/native header1/isolated own-GIL1 reviewed actual evidence, then the
coordinator's replicated memory gate with retained Rust coverage. Physical
DATA-page ownership and collections load savings remain unproved.
