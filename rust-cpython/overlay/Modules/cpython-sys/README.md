# Core-only CPython C bindings

This overlay adapts CPython's existing `cpython-sys` target library to `core`.
It introduces no replacement ABI definitions or crate. The source files are
derived from `Modules/cpython-sys` at the locked Rust-for-CPython commit
`b812b4a7b9efaca46b98544a8633b7d7e454166b`, licensed PSF-2.0. The source pin,
package manifest, wrapper header, workspace entry and registry locks remain
unchanged. Only `build.rs` and `src/lib.rs` override those source files.

The target library declares `#![no_std]` and uses `core` for the original FFI
types, pointer operations, interior mutability and initialization. The existing
bindgen 0.72.1 generator receives `Builder::use_core()`; its documented output
uses `core::ffi` for this Rust version. The host generator and its existing
dependencies still use `std`. No Cargo feature can silently restore a target
`std` edge in this library.

Header allowlists and blocklists, generated layouts and layout tests, compiler
flags, include ordering, target selection, debug handling, `py_gil_disabled`,
pointer-width branches, static immortal-object initialization and pointer-global
import handling remain the original policy. In particular, free-threaded builds
still read their actual configuration and generate their actual object layout;
they are not treated as GIL-enabled layouts. The target wrappers are the original
typed definitions, rather than a second manually maintained C API inventory.

The nearest compiler judge must confirm the generated target source contains
no `std` paths, the library compiles without a target standard runtime and the
existing bindgen layout tests plus the added typed module-initializer signature,
generated-object wrapper layout, static-initializer and method-table sentinel
tests pass. This source checkpoint has not been built or tested.
Integrated qualification must still exercise all Rust routes and subinterpreter
lifetimes. Source inspection proves no image or physical memory saving.

## Remaining static-carrier source closure

Before the core-only consumer ports, `cpython-rust-staticlib` owned 13 helper
dependencies and its `io` module. This bindings overlay alone does not remove
the carrier's standard runtime. The following records the original source
obligations; integrated consumer ports require their own source and compiler
qualification:

| Consumer | Target source obligation |
| --- | --- |
| `_asyncio_rs` | Replace core-compatible `std` paths, declare `no_std`; preserve per-interpreter Python-owned state and reference ownership. |
| `_bisect_rs` | Replace core-compatible `std` paths and declare `no_std`; all allocation stays in Python. |
| `_codecs_rs` | Replace core-compatible `std` paths, including UTF-8 validation, and declare `no_std`; Python owns output storage. |
| `_concurrent_futures_rs` | Replace core-compatible `std` paths and declare `no_std`; preserve Python callback state and interpreter isolation. |
| `_contextlib_rs` | Replace core-compatible `std` paths and declare `no_std`; preserve Python callback/list ownership. |
| `_heapq_rs` | Replace core-compatible `std` paths and declare `no_std`; preserve Python list mutation, comparison errors and references. |
| `_html_parser_rs` | Replace core-compatible `std` paths and declare `no_std`; preserve Unicode scanning and Python token allocation. |
| `_itertools_rs` | Replace core-compatible `std` paths and declare `no_std`; preserve Python-owned result and callback state. |
| `_posixpath_rs` | Replace core-compatible `std` paths and declare `no_std`; preserve fallible `PyMem` storage and its cleanup. |
| `_ssl_rs` | Replace core-compatible `std` paths and declare `no_std`; preserve Python-owned results and CPython/OpenSSL boundaries. |
| `_tempfile_rs` | Replace core-compatible `std` paths and declare `no_std`; preserve Python objects, audit events and filesystem-call delegation. |
| `_random_rs` | The standalone route is already `no_std`; its `static-module` feature currently restores the ordinary standard prelude/runtime. The static route needs a deliberate single-owner panic policy before removing that edge. |
| `_base64` | Remove Rust `Vec` scratch/output ownership and its `base64` `std` / `data-encoding` `alloc` dependency closure, or provide an explicitly bounded fallible Python-owned allocation design preserving all encodings and error behavior. |
| `cpython-rust-staticlib::io` | Replace core-compatible pointer/slice/FFI paths. The carrier itself must declare `no_std` only once every target dependency is core-only, and must provide exactly one aborting panic owner. |

Build dependencies may retain `std`; they execute on the build host and are not
linked into the target carrier. Each separately linked `cdylib` still needs a
valid panic runtime, while an integrated core-only archive needs exactly one
panic implementation. Any eventual feature distinction must preserve those
link contracts rather than restoring a target `std` edge through unification.
