# URL quotation source patch feasibility, 2026-09-24

## Recommendation

**Proceed to a gated source patch only after a quiet, cache-valid paired lean
comparison clears the time and memory gates.** The smallest credible patch for
the pinned `b812b4a7b9efaca46b98544a8633b7d7e454166b` fork keeps
`urllib.parse`'s public functions and original guards, adds a private C
extension, and links that extension to a dedicated `no_std` Rust archive built
from the already pinned nightly compiler. This keeps the proven two-pass
kernel and avoids a Cargo package, dependency, or `Cargo.lock` change. It is
an implementation proposal, not a demonstrated whole-build result.

The isolated lean proof passed 2,177 differential public cases, 182 CPython
URL tests (7 skipped), and a complete catalog-output check. Its unstripped
extension was 50,712 bytes. Those facts establish feasibility of the C/Rust
boundary, not a source-build size, speed, or memory verdict. The initial RSS
increase was attributable to an invalid checked-hash `urllib.parse` cache in
the overlay candidate; four valid-cache diagnostic pairs had a median peak
RSS 65,536 bytes lower. The quiet paired speed and upstream memory gates
remain open (`url-quote-lean-proof-20260924.md`,
`url-quote-memory-attribution-20260924.md`).

## Verified source and build facts

- `Lib/urllib/parse.py:1096` normalizes `safe`, returns early for empty and
  already-safe input, then calls `_byte_quoter_factory`. The proof inserts its
  branch immediately before that call. Only exact `bytes` input, normalized
  exact `bytes` safe, and input shorter than 200,000 bytes enter Rust. Other
  inputs retain the original path, including bytearray and subclasses.
- The proof's `module.c` accepts two exact byte objects, holds their borrowed
  buffers across both Rust calls, checks the computed length, allocates
  `PyUnicode_New(length, 127)`, and fills its one-byte payload. `quote.rs`
  uses only `core`; it returns `-1` for invalid capacities and aborts on an
  impossible Rust panic rather than unwinding into C. The present proof C
  module is single-phase with `m_size = -1`.
- `Modules/cpython-rust-staticlib` is an existing Cargo static-library
  package, currently exporting `_base64::PyInit__base64`. It **can** export a
  plain `extern "C"` quote kernel without a new Cargo package or lock change
  by adding a source module to that package. But `configure.ac` sets
  `RUST_STATICLIB_DEP` only when `MODULE_BUILDTYPE=static`; the ordinary lane
  uses the shared build, so this archive is not automatically built or linked
  into a new C extension. `Modules/makesetup` links it automatically only for
  Rust modules selected as static. Explicit archive dependencies and link
  flags would still be required for a shared C wrapper. Its installed size
  and symbol retention in that arrangement are unmeasured; the existing
  `_base64` Rust runtime may erase the lean proof's size benefit.
- `Modules/makesetup` builds ordinary C extension objects and links their
  `MODULE_<NAME>_LDFLAGS`, with `MODULE_<NAME>_LDEPS` as a prerequisite.
  `Modules/Setup.stdlib.in` is configure-substituted; `configure.ac` uses
  `PY_STDLIB_MOD` to gate `_base64` on `HAVE_CARGO`. The generated `configure`
  is what `rust-cpython/build.py` runs, so any new configure declaration
  needs both source and generated script in the authored patch.
- `rust-cpython/build.py` extracts verified pinned source afresh, checks each
  patch digest and manifest schema, applies with `git apply --check` then
  `git apply`, and rejects `Cargo.lock` changes. The report records the patch
  inputs. `build_no_rust.py` extracts the pinned source separately and never
  invokes that patch application, retaining an unpatched same-fork control.

## Proposed patch targets

1. Copy the lean kernel semantics into a new, named fork source such as
   `Modules/_rust_url_quote/quote.rs`. Keep `#![no_std]`, the C ABI signature,
   capacity checks, and panic-abort policy. Compile it with the locked nightly
   `rustc --crate-type=staticlib -C panic=abort` into the build directory via
   a rule in `Makefile.pre.in`. Use the lane's `RUSTUP_TOOLCHAIN` environment;
   record the compiler command in the recipe. The rule must depend on the Rust
   source and produce a normal file target, not a source-tree artifact.
2. Adapt `url-quote-lean-proof/module.c` into
   `Modules/_rust_url_quote/module.c`. Keep `PyObject *` ownership, allocation,
   exact-type checks, and errors in C; Rust receives only borrowed byte
   spans and the bounded output pointer. Convert the module to a stateless
   multiphase definition with `m_size = 0` and a `Py_mod_exec` slot; explicitly
   declare multiple-interpreter support if the pinned API offers it. This
   avoids inheriting the proof's legacy `m_size=-1` subinterpreter limit. No
   process-global Python object or cache belongs in the wrapper.
3. Add `_rust_url_quote` to `configure.ac` with a `PY_STDLIB_MOD` gate on the
   pinned Rust compiler availability, regenerate and include `configure`,
   and add its gated C source line to `Modules/Setup.stdlib.in`. In
   `Makefile.pre.in`, set `MODULE__RUST_URL_QUOTE_LDEPS` to the Rust archive
   target and `MODULE__RUST_URL_QUOTE_LDFLAGS` to that archive. Confirm the
   generated module rule orders C objects before the archive and that the
   resulting extension is installed under `lib-dynload`. There is no need to
   turn all modules static or modify CPython's public C ABI.
4. Patch `Lib/urllib/parse.py` with the proof's guarded call after the
   existing early returns. Import the private extension at module import
   only on the Rust candidate. Because the candidate patch is never applied
   by `build_no_rust.py`, the control keeps its original parser and has no
   import dependency. If the patched source must later support a Cargo-free
   build, the import and branch need an explicit configure-generated guard;
   silently swallowing `ImportError` would conceal a broken candidate.

The archive rule is a design hypothesis. The pinned build has no equivalent
`rustc` rule for a C extension today. It must be checked for offline sandbox
execution, ThinLTO/PGO linkage, release optimization, macOS deployment
target, incremental rebuilds, and installation. A Cargo-staticlib variant
is a fallback if the direct archive is unsuitable: add the kernel to
`Modules/cpython-rust-staticlib/src/lib.rs`, make the archive explicitly for
the shared C module, and measure the resulting extension and link symbols.
Do not assume the proof's 50,712-byte size transfers to either full build.

## State, cache, and attribution gates

The kernel holds no Python references or global mutable state. On the
GIL-enabled fork, C owns all Python API calls while its caller holds the GIL;
Rust scans immutable exact-byte buffers without callbacks. A stateless
multiphase module permits separate interpreter instances in principle, but
actual subinterpreter import and concurrent calls require a runtime check.
The private module and its `quote_ascii` symbol must stay private; public
`urllib.parse` values, exceptions, and the CPython C ABI are the contract.

The overlay memory comparison was confounded because its changed parser
source and checked-hash `.pyc` disagreed while bytecode writes were disabled.
`rust-cpython/build.py` sets `PYTHONPYCACHEPREFIX` for its build environment.
The measured benchmark environment comes from
`benchmarks/harness/runner.py:workload_environment`: it sets
`PYTHONDONTWRITEBYTECODE=1` but does not set a cache prefix (and starts from
the inherited environment). A source build therefore does **not** by itself
guarantee a fresh parser cache in the benchmark. For every comparison,
precompile the patched and control parser into verified matching cache states
(or verify that both run from source), explicitly control any inherited
`PYTHONPYCACHEPREFIX`, then record source and `.pyc` hashes, invalidation
mode, `__cached__`, and environment. Keep cache generation outside timed and
memory passes. The source patch manifest must contain the patch file digest
and nonempty `author`, `origin`, `license`, `reason`, `compatibility`, and
`reproducer`, tied to the pinned source commit. The patch must include every
new source/build file and leave `Cargo.lock` byte-identical.

## Hard judges for an implementation lane

1. First verify the pre-promotion gate: quiet, counterbalanced complete
   catalog URL workload against the last accepted Rust fork, equal valid
   parser-cache states, control and candidate self-comparison, root and
   covered child CPU, separate memory pass, and no material per-workload
   regression. The existing memory attribution is diagnostic only.
2. For a draft patch, run manifest/schema/digest checks, `git apply --check`
   on a fresh pinned extraction, generated configure and Makefile inspection,
   an offline `--locked` build, and `Cargo.lock` hash comparison. Inspect the
   installed extension with `file`, `otool -L`, and `nm`; prove an actual
   public `urllib.parse.quote` call reaches Rust and that import fails loudly
   if the required module is absent.
3. Repeat the 2,177 differential cases, unchanged `test_urlparse` and
   `test_urllib`, complete catalog output digest, guard boundaries, and a
   subinterpreter import/call. Then run the broad unchanged CPython suite and
   a full candidate PGO build. Check stage installation, module size,
   startup/import cost, paired catalog timing/CPU, separate memory and
   allocation evidence when available, and matched upstream 3.16 comparison
   before claiming a general CPython improvement.

This report is a read-only source audit. It ran no build, test, benchmark,
fetch, formatter, or linter and did not mutate the pinned source or lock.
