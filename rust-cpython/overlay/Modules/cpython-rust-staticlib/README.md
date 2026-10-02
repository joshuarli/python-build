# Core-only static Rust carrier

The existing archive keeps its 12 registered builtin initializer providers and I/O
exports. It declares `#![no_std]`, uses core pointer/slice operations and enables
`static-module` on every helper dependency. That feature excludes each helper's
standalone panic handler without restoring `std`; the final archive provides
one fatal handler through the existing generated `cpython_sys::Py_FatalError`
declaration. These builtin helper packages produce only `rlib`, so dependency
compilation cannot also link an unused helper `cdylib` without its panic owner.
The existing abort panic profiles remain unchanged. Rust tests use
their test harness's runtime instead of the target archive's handler.

The first compiler build reached the final C link, where the pinned prebuilt
`core` archive still referenced `rust_eh_personality`. The carrier supplies that
symbol only for the abort-panic target, using the full Itanium callback ABI of
the supported Darwin arm64 and Linux x86-64/arm64 targets: two C integers, one
64-bit exception class, two opaque pointers and a C-integer result. It neither
inspects nor dereferences unwinder state. An invocation terminates through the
same typed fatal API: foreign exceptions cannot unwind through these Rust
helpers, and no catch, cleanup or unwind runtime is promised. The Rust test
harness retains its own personality provider.

The ABI was checked against the pinned Rust compiler source commit
`574ff7d98bd6d037e5236a8453029173b32631fd`, in
[`library/std/src/sys/personality/gcc.rs`](https://github.com/rust-lang/rust/blob/574ff7d98bd6d037e5236a8453029173b32631fd/library/std/src/sys/personality/gcc.rs),
[`library/unwind/src/libunwind.rs`](https://github.com/rust-lang/rust/blob/574ff7d98bd6d037e5236a8453029173b32631fd/library/unwind/src/libunwind.rs),
and `library/unwind/src/types.rs`. This narrow symbol definition adds no
unwinder dependency and does not restore `std`.

`cpython-sys` is the original CPython-owned package with core-only generated
bindings. Its new direct carrier edge supplies the existing typed fatal-error
API; no copied ABI declarations, panic export, external library or registry
dependency is introduced. The lock adds that local dependency edge and removes
the unused carrier edge to `_base64`.
Initializer names, `Modules/Setup.local`, the wrapper header, source pin,
registry versions/checksums, and interpreter registration are unchanged.

All 12 core-only helper source ports are integrated. Compiler qualification is
still pending; source integration is not a completed target-dependency proof. Every helper
must declare `#![no_std]` independently of `static-module`, and retain a
standalone panic handler only under `cfg(not(feature = "static-module"))`.

| Existing provider | Required source closure |
| --- | --- |
| `_asyncio_rs` | Core types; Python-owned state and buffers; no target `std` or Rust `alloc` edge. |
| `_bisect_rs` | Core types; Python-owned list and comparison state. |
| `_codecs_rs` | Core UTF-8 validation and slices; Python-owned output bytes/text. |
| `_concurrent_futures_rs` | Core types; Python-owned callback and interpreter state. |
| `_contextlib_rs` | Core types; Python-owned callbacks and lists. |
| `_heapq_rs` | Core types; Python-owned list mutations and comparison error propagation. |
| `_html_parser_rs` | Core types; Python-owned Unicode and token output. |
| `_itertools_rs` | Core types; Python-owned callback and result state. |
| `_posixpath_rs` | Core types; fallible `PyMem` buffers with original cleanup. |
| `_random_rs` | Existing core algorithm; `static-module` no longer restores the standard runtime and retains its standalone-only panic handler. |
| `_ssl_rs` | Core types; unchanged CPython/OpenSSL boundary and Python-owned results. |
| `_tempfile_rs` | Core types; unchanged Python-owned audit, filesystem-call and result state. |

The generated bindings' host build dependencies may use `std`; host tools are
not target archive dependencies. Full source closure review must bind exact
consumer commits and inspect their target features. A clean compiler build must then prove no target `std` or
`alloc` edge and exactly one panic owner, with all registered providers and
retained ABI exports intact. Complete affected Python suites and the integrated full suite
remain required. No compiler, tests, native probe or memory check has qualified
this shared source checkpoint, and it establishes no physical saving.

## Shared-extension artifact boundary

The original archive also re-exported `PyInit__base64`, but the configured
interpreter does not register that initializer as a builtin. The existing
`_base64` package is a shared extension selected by `Modules/Setup.stdlib.in`;
its installed extension remains required. The carrier therefore drops only its
unused `_base64` dependency and private in-core `PyInit__base64` export. This is
an explicit private archive/export change, not removal of the shared module.
The `_base64` source, shared-module recipe, module API and `_binascii_rs`'s 15
base-encoding aliases remain the original source. Those shared packages may
still use their standard runtimes, independently of the core-only carrier.

The completed `perf-re60` build provides the finite prior-artifact evidence:
`Modules/config.c` registers all 12 helpers above and no `_base64` builtin;
the generated Makefile lists `_base64` in `MODSHARED_NAMES` and has its separate
shared Cargo recipe. Its verified release report includes the installed
`_base64.cpython-316-darwin.so` among 58 Rust shared extensions and none of the
12 builtin helpers. Finite source searches in Modules, Include, Python and
Programs find `PyInit__base64` only in the legacy helper definition and the old
carrier re-export. The actual base-encoding callers are the unchanged shared
`_binascii_rs` aliases, which retain their own legacy dependency.

The 12 helper packages no longer promise separately linked, uninstalled Cargo
`cdylib` artifacts. Their initialized builtin modules, initializer symbols,
method pointers, configured C layouts, I/O exports and public Python behavior
remain required. A clean build must still retain all 58 installed Rust shared
extension judges and prove the 12 registered providers remain in libpython.
