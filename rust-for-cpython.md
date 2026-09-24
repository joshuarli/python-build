You are working in `joshuarli/python-build`.

Implement this specification to completion. Do not merely write a plan. Inspect the current checkout and read the root `AGENTS.md` before modifying anything; the local checkout is authoritative if it has moved beyond the research snapshot below. Do not push.

## Goal

Add a cleanly isolated experimental build environment for **CPython 3.16 with Rust-for-CPython**, intended as the foundation for progressively moving high-value CPython stdlib/runtime implementation kernels to Rust without changing their Python APIs.

This is **not RustPython** and must never drift in that direction.

The architectural objective is:

```text
existing Python API
        |
        v
thin Python / CPython-facing shell
        |
        v
native Rust implementation kernel
        |
        v
ordinary CPython objects + C ABI where required
```

The defining compatibility requirements are:

* It remains CPython.
* Existing Python APIs remain unchanged.
* Existing Python semantics remain unchanged.
* Existing CPython C ABI/API contracts remain intact wherever they are part of the supported interface.
* Rust is an implementation language behind those boundaries.
* Existing pure-Python implementations are valuable as reference/oracle/fallback code and should not automatically be deleted when a Rust accelerator is introduced.
* We should prefer coarse native kernels rather than moving every tiny Python operation across a Python/Rust boundary.

For this task, **do not implement any new stdlib Rust migrations yet**. Establish the 3.16/Rust build lane, validate it rigorously, and leave behind a concrete ranked migration roadmap.

## Existing repository constraints

The current production build in this repository is CPython **3.14.6**.

At the research snapshot (`b30745ad78fcc7503849b30a79bda049def522f6`) the existing tree has:

```text
build.py
build/
buildsys/
sources.lock.json
bootstrap.lock.json
patches/
tests/
benchmarks/
Dockerfile
AGENTS.md
```

The root build system currently supports:

* `aarch64-apple-darwin`
* `x86_64-unknown-linux-musl`
* `aarch64-unknown-linux-musl`

and treats exact CPython 3.14.6 as part of its product contract.

The Linux targets are explicitly frozen/completed.

**Do not turn the current build system into a multi-version abstraction.**
**Do not change the existing 3.14.6 source pin.**
**Do not alter the frozen Linux build paths.**
**Do not add Rust-for-CPython conditionals throughout `buildsys/`.**
**Do not make the existing product build depend on Rust.**

This experiment must be visibly and mechanically separate.

The only acceptable coupling to the existing implementation is reuse of genuinely generic, already-good infrastructure such as:

* content-addressed input/cache machinery;
* safe archive extraction;
* command/log helpers;
* the locked macOS LLVM/Xcode toolchain description and loader;
* generic target detection where appropriate.

Do not reuse the existing 3.14-specific CPython configuration, pruning, packaging, reference-parity, or scope machinery merely to avoid writing a small amount of experimental glue.

## Initial platform scope

The first completed Rust-for-CPython environment should target:

```text
aarch64-apple-darwin
```

only.

This is intentional.

Do not touch the frozen Linux 3.14 targets and do not add a new Linux Rust target in this task. Keep the new implementation sufficiently clean that native Linux can be added later without redesigning it, but do not generalize pre-emptively.

This is initially a **development/research build lane**, not a new distributable product.

Do not add release publishing, uv mirror support, GitHub Actions, or production packaging yet.

## Rust-for-CPython source pin

Use the Rust-for-CPython CPython fork as the source, not upstream vanilla `python/cpython`.

Research snapshot:

```text
repository: Rust-for-CPython/cpython
branch:     3.x-rust-in-cpython
commit:     b812b4a7b9efaca46b98544a8633b7d7e454166b
version:    CPython 3.16.0a0
```

Pin the **commit**, not the moving branch.

Download an archive of that exact commit and record:

* canonical repository;
* informational branch name;
* exact commit SHA;
* archive URL;
* archive byte size;
* SHA-256;
* license;
* purpose.

Do not make a networked `git clone` part of the normal build.

It is fine to clone repositories temporarily while doing implementation research, but the finished build must consume a verified immutable source archive.

Create a Rust-for-CPython-specific source lock inside the new environment. Do not put this source in the production 3.14 `sources.lock.json`.

If upstream has advanced when you implement this, still use the commit above unless there is an objective reason that it cannot build with the requested Rust nightly. If you must change the source pin, document exactly why and choose another commit from the same 3.16 Rust-for-CPython line. Do not silently track branch HEAD.

## Rust toolchain

Pin exactly:

```text
nightly-2026-09-15
```

Use a `rust-toolchain.toml` in the new Rust-for-CPython environment with at least:

```toml
[toolchain]
channel = "nightly-2026-09-15"
profile = "minimal"
```

Do not silently fall back to:

* stable;
* whatever `rustc` is first in `PATH`;
* a newer nightly;
* the Rust-for-CPython repository's current MSRV.

The current Rust-for-CPython workspace declares an MSRV of Rust 1.95 and its own Cargo CI uses stable, but **this project intentionally pins nightly-2026-09-15**.

Keep that distinction explicit.

During every build, also set:

```text
RUSTUP_TOOLCHAIN=nightly-2026-09-15
```

and record the complete output of:

```text
rustc -Vv
cargo -V
rustup show active-toolchain
```

in build provenance.

Fail closed if the requested nightly is unavailable.

Do not automatically mutate the user's default Rust toolchain.

A missing nightly should result in a concise actionable error such as the exact `rustup toolchain install nightly-2026-09-15 --profile minimal` command.

### Cargo isolation

Rust-for-CPython's generated Makefile expects Cargo at:

```text
$(CARGO_HOME)/bin/cargo
```

Do not let this force us into an uncontrolled global Cargo environment.

Prefer a small private Cargo home beneath the new experimental tree, for example:

```text
rust-cpython/.cargo-home/
```

with a generated `bin/cargo` wrapper that executes:

```text
rustup run nightly-2026-09-15 cargo "$@"
```

This gives us:

* a deterministic Cargo entry point;
* an isolated registry/cache;
* an exact Rust toolchain;
* compatibility with Rust-for-CPython's existing Makefile assumptions.

Keep `RUSTUP_HOME` alone unless there is a compelling reason not to; it is fine for rustup itself to manage the installed toolchain globally. We care that this build cannot accidentally consume a different toolchain and that Cargo package state/build output does not bleed into unrelated projects.

Never invoke `cargo update`.

Always respect upstream `Cargo.lock` and use `--locked`.

Where practical, make `fetch` populate the private Cargo cache with `cargo fetch --locked`, after which an offline build using `CARGO_NET_OFFLINE=true` should work.

Do not vendor the Cargo registry into this repository.

## Directory shape

Keep this small.

A good target shape is approximately:

```text
rust-cpython/
    build.py
    sources.lock.json
    rust-toolchain.toml
    README.md
```

plus ignored generated state:

```text
rust-cpython/.cache/       # only if truly experiment-specific
rust-cpython/.cargo-home/
rust-cpython/work/
rust-cpython/stage/
rust-cpython/logs/
rust-cpython/results/
```

Reuse the repository-wide content-addressed `.cache` for immutable source blobs if the existing generic cache abstraction makes that natural. Do not duplicate a correct content-addressed downloader merely for directory purity.

Conversely, Cargo state and build outputs should stay under `rust-cpython/`.

Do not create:

* a `docs/` hierarchy;
* `STATUS.md`;
* `plan.md`;
* progress ledgers;
* multiple overlapping design documents.

`rust-cpython/README.md` should be the one durable human-facing description of this lane, including the migration roadmap requested below.

Add only the minimum root `AGENTS.md` clarification necessary to make it unambiguous that `rust-cpython/` is an intentionally isolated CPython 3.16 experiment and is exempt from the root product's exact-3.14.6 source rule. Do not rewrite the rest of `AGENTS.md`.

## CLI

Keep the experimental CLI minimal.

Something equivalent to:

```text
python3 rust-cpython/build.py doctor
python3 rust-cpython/build.py fetch
python3 rust-cpython/build.py build
python3 rust-cpython/build.py test
python3 rust-cpython/build.py clean
```

is enough.

Avoid option sprawl.

### `doctor`

Must be side-effect free.

Report and validate at least:

* host OS and architecture;
* exact supported experimental target;
* source repository/commit/version pin;
* rustup path;
* whether `nightly-2026-09-15` is installed;
* `rustc -Vv` for that toolchain;
* Cargo version for that toolchain;
* private `CARGO_HOME`;
* C compiler/toolchain identity;
* Xcode SDK identity;
* deployment floor;
* GNU make identity;
* whether required cached source inputs are present.

On an unsupported host, explain that this experiment currently supports only native Apple Silicon macOS rather than pretending to cross-compile.

### `fetch`

Network is allowed.

It should:

1. fetch and SHA-256 verify the exact Rust-for-CPython archive;
2. populate the existing locked LLVM toolchain if it is not already cached;
3. safely extract or stage enough source to run `cargo fetch --locked`;
4. populate the experiment's private Cargo cache;
5. leave the environment capable of building with network disabled.

Do not compile CPython as part of `fetch`.

### `build`

The build must be out-of-tree.

Keep the verified source tree pristine.

Use roughly:

```text
rust-cpython/work/source/
rust-cpython/work/build/
rust-cpython/stage/
```

and make source reuse/re-extraction explicit and deterministic.

Use the repository's already locked macOS LLVM 23.1.2 / Xcode SDK machinery rather than inventing another C toolchain pin.

Important: reuse the **toolchain**, not the existing 3.14-specific `buildsys.cpython.configuration()` policy.

The Rust-for-CPython fork already has its own Rust-aware configure/Makefile machinery. Let it own Rust module compilation.

The current fork does the following:

* `configure` detects Cargo;
* derives a Rust target triple from CPython's platform machinery;
* chooses Cargo `dev` vs `release` profile based on the CPython optimization build;
* computes `CARGO_TARGET_<triple>_LINKER`;
* handles `.dylib` vs CPython `.so` naming on Apple platforms;
* places Cargo output in the C build directory;
* builds shared Rust stdlib modules as `cdylib`;
* can aggregate static Rust modules through `cpython-rust-staticlib`.

Do not duplicate or bypass that machinery.

Start with a normal GIL-enabled release CPython.

Use the existing python-build philosophy where it makes sense:

```text
-O3
ThinLTO
CPython PGO on macOS
no BOLT
no experimental JIT requirement
no free-threaded build initially
```

Prefer the same CPython PGO workload already used by the production macOS build:

```text
-m test --pgo
```

and the same locked `llvm-profdata` belonging to the locked LLVM toolchain.

However, do not force cross-language LTO or invent special Rust `RUSTFLAGS` merely because Rust is present. Initially use upstream Cargo release-profile behavior. We need a clean baseline before tuning Rust code generation.

Configure as an ordinary out-of-tree CPython build and install into the experimental stage tree.

Do not prune it into the 3.14 product scope.

This lane is for CPython/Rust development. Retain the regression tests and normal stdlib source needed for testing.

Avoid `ensurepip` installation if it would introduce irrelevant package-manager state; there is no need for pip to validate this environment.

### Offline build check

After `fetch` has populated:

* CPython source archive;
* locked LLVM;
* Cargo registry/git dependencies;
* exact Rust nightly installation;

the actual CPython `build` should be able to run with network access denied / Cargo offline.

At minimum set:

```text
CARGO_NET_OFFLINE=true
```

and ensure no build step downloads dependencies.

If a genuinely unavoidable upstream behavior prevents a fully offline build, identify it precisely rather than quietly permitting network access.

## Rust-for-CPython architecture you must preserve

The current Rust-for-CPython tree has a Cargo workspace containing:

```text
Modules/_base64
Modules/cpython-build-helper
Modules/cpython-rust-staticlib
Modules/cpython-sys
```

The integration model is significant.

`cpython-sys` generates low-level bindings to CPython's own C API.

Rust modules can export an ordinary CPython module initializer such as:

```rust
#[unsafe(no_mangle)]
pub extern "C" fn PyInit__base64() -> *mut PyObject
```

so CPython and third-party code continue to see the normal C ABI.

For shared builds, `Modules/makesetup` drives Cargo to build the module as a `cdylib`, then installs it under CPython's normal extension suffix.

For static builds, Rust modules are aggregated beneath:

```text
cpython-rust-staticlib
```

and linked into the interpreter.

This is precisely the model we want.

Do not replace it with PyO3.

### PyO3 policy

PyO3 is extremely useful **prior art** for:

* Python object lifetime modeling;
* `Python<'py>`-style interpreter tokens;
* ergonomic argument conversion;
* extension-module experiments.

It should not become the foundational dependency for in-tree CPython Rust code.

Rust-for-CPython is intentionally developing:

```text
raw cpython-sys layer
        +
small CPython-owned safe internal Rust API
```

rather than making CPython itself depend on PyO3.

Preserve that direction.

Third-party PyO3 projects mentioned later are implementation/performance references, not components to vendor wholesale.

## Current `_base64` caveat

The in-tree `_base64` module is primarily an integration proof.

At the current source pin it implements a Rust `standard_b64encode` and exports a normal `PyInit__base64`.

`Modules/Setup.stdlib.in` builds it as a Rust module.

However, `Lib/base64.py` currently still routes its normal Base64 APIs through `binascii`; it does **not** transparently use `_base64` as the public implementation.

Do not misrepresent the current fork as already shipping a fast Rust-backed `base64` stdlib.

The purpose of `_base64` for this task is to prove that our build actually compiles, links and imports an in-tree Rust extension through CPython's build machinery.

## Validation

The new build lane is not complete because `make` exits zero.

Automate checks covering at least:

### Toolchain identity

Verify and record that the build actually used:

```text
nightly-2026-09-15
```

and the expected locked C toolchain.

The presence of another `rustc` or Cargo installation on the host must not change the result.

### Interpreter identity

The built interpreter must report:

```text
sys.implementation.name == "cpython"
sys.version_info[:2] == (3, 16)
```

Record the full version string and build config.

### Rust module proof

From the freshly built interpreter:

```python
import _base64
```

must succeed.

Exercise the Rust function on representative inputs and compare it to the appropriate existing stdlib/binascii result where semantics overlap.

Verify the produced native module:

* is arm64 Mach-O;
* has the expected CPython extension suffix;
* exports the expected `PyInit__base64` symbol;
* has no unexpected Homebrew/Rust build-tool dylib dependencies;
* obeys the intended macOS deployment floor.

### Cargo

After CPython has been configured, run:

```text
cargo test --locked
```

against the in-tree Rust workspace using the exact nightly.

Do not run formatter/linter churn merely for ceremony.

### CPython tests

During iteration run targeted tests including the relevant Base64/binascii/import/build machinery tests.

Before declaring completion, run a broad CPython regression suite on the built interpreter.

Do not hide unexpected failures as skips.

Classify failures as:

* known platform skip;
* known upstream Rust-for-CPython failure at the exact pinned commit;
* regression introduced by this build environment.

Anything in the third category must be fixed.

### Isolation regression

Run the existing repository unit suite as well.

The original 3.14.6 build controller and tests must remain green.

Add focused tests for the new Rust lane, but do not force existing target/configuration abstractions to know about 3.16.

## Provenance

Write one concise machine-readable build report under the experimental results directory containing at least:

```text
source repository
source commit
source archive SHA-256
CPython reported version
Cargo.lock SHA-256
Rust channel
rustc -Vv
cargo -V
C toolchain identity
SDK identity
configure arguments
PGO task
LTO mode
Cargo profile
CARGO_HOME
CARGO_TARGET_DIR
built Rust workspace members
test results
```

Do not create a separate bookkeeping ecosystem.

## Research context: why this architecture is credible

This task is founded on several concrete developments.

### Rust-for-CPython itself

The project has explicitly chosen Python 3.16 as its initial target.

Its reference implementation is not a new interpreter. It modifies CPython so Rust can implement extension modules while retaining normal CPython APIs and ABI.

The project initially discussed eventual Rust use throughout CPython but narrowed the first formal proposal to optional extension modules so portability, bootstrap and workflow issues can be learned with low risk.

That conservative upstream policy does **not** constrain this experimental fork from investigating broader stdlib acceleration later. It is nevertheless a good engineering pattern: prove the build/tooling/API layer first, migrate modules incrementally, maintain easy rollback.

Relevant upstream research threads in `Rust-for-CPython/cpython` include:

* issue 10: C API bindings design;
* issue 23: Unix Rust build-system integration;
* issue 30: choosing the first Rust module;
* issue 33: avoiding duplicated Rust `core`/`alloc` cost across many extension modules.

Read those before designing around the upstream build.

### The first-module discussion

Rust-for-CPython considered Base64, zlib and bz2.

The group ultimately chose **zlib** as the intended 3.16 module target because it combined manageable implementation scope with broad impact.

The separate `Rust-for-CPython/zlib-py` proof, using `zlib-rs`, reported on Darwin arm64 / CPython 3.16 approximately:

```text
decompress 1 MB:         ~5.1x
decompress 10 MB:        ~6.0x
stream compress 1 MB:    ~5.2x
stream compress 10 MB:   ~5.6x
stream decompress 1 MB:  ~3.7x
compress 10 MB level 9:  ~1.8x
adler32:                  ~9.7-9.9x
crc32:                    ~2.9x slower
```

Treat these as prior-art benchmark results, not promises.

The CRC32 regression is particularly instructive: **Rust is not automatically faster. Every migrated operation must earn its place through measurement.**

That proof also found compressed output could differ from zlib at intermediate compression levels even when decompression semantics remained valid. Compatibility tests therefore need to cover observable byte behavior, not merely round trips.

### CPython itself is already accepting Rust C-ABI backends

Current CPython 3.16 build configuration supports:

* `zlib-rs` as a backend for `zlib`;
* `libbzip2-rs` as a backend for `bz2`.

That is exactly the incremental compatibility model we want:

```text
Python API
   -> existing CPython-facing ABI
       -> Rust implementation
```

A module does not need to be completely rewritten on day one.

## Migration philosophy

Future stdlib migration should generally follow these rules.

### Preserve the Python shell when it buys compatibility

For dynamic modules, the ideal form is often:

```text
Lib/foo.py
    public classes
    subclassability
    callbacks
    monkey-patching semantics
    argument policy
        |
        v
_foo_rust / _foo
    coarse CPU-heavy kernels
```

rather than moving the entire public module into Rust.

Python code is often the cheapest place to preserve odd historical semantics.

### Treat CPython's tests as executable specification

For every migration:

1. identify the exact CPython test files covering the module;
2. run the unchanged tests against baseline CPython;
3. implement the Rust fast path;
4. run those same tests;
5. add differential/property/fuzz tests against the Python/C reference where useful;
6. benchmark only after semantic parity is established.

A Rust implementation that is fast but slightly different is **not** a stdlib replacement.

### Boundary crossings matter

Do not write Rust code that simply performs one Python object operation at a time through FFI.

The useful unit is something like:

```text
Python inputs
    -> convert/borrow once
        -> substantial Rust algorithm
            -> produce Python result
```

When possible, operate over raw UTF-8/bytes/buffer data in Rust.

Only release the GIL or parallelize once no arbitrary Python callback/object access is required.

### Algorithmic improvements are encouraged

A mechanical translation from Python to Rust is not the end goal.

`difflib` is a good example: large wins can come from changing the algorithm/data structures while reproducing exactly the same externally visible result.

SIMD, better automata, specialized parsers, cache-friendly data structures, batched work and safe internal parallelism are all fair game when semantics remain identical.

### Preserve fallbacks where useful

An accelerator may deliberately fall back to the Python path for:

* subclasses;
* user callbacks;
* custom hooks;
* rare exotic argument types;
* introspection-sensitive behavior.

This is preferable to making the fast path grotesquely complicated or subtly incompatible.

### C ABI compatibility

If a migrated component exposes a CPython C symbol/API, Rust should export the compatible C ABI rather than inventing a Rust ABI.

Use:

```text
extern "C"
#[repr(C)]
```

where required.

Remember that CPython's object model permits mutation and aliasing patterns incompatible with ordinary Rust references. The eventual internal safe Rust layer should isolate that unsafety rather than pretending it does not exist.

The ideal long-term pattern is:

```text
small audited unsafe CPython boundary
        |
large safe Rust implementation
        |
small audited unsafe CPython boundary
```

not "zero unsafe at any cost."

## Prior art worth studying

Do not copy code blindly. Check licenses first. These projects are primarily architectural and benchmark references.

### `sweepai/difflib-rs`

Implements `difflib.unified_diff` through Rust/PyO3.

Its own benchmark data reports roughly 3–5x speedups on substantive diffs while targeting identical output.

Useful lessons:

* exact-output differential testing;
* coarse sequence processing;
* keep public behavior stable.

### `prostomarkeloff/difflib-fast`

Even more interesting algorithmically.

It implements exact `SequenceMatcher`-style Ratcliff–Obershelp behavior using substantially different algorithms/data structures, including suffix automata, and demonstrates that compatibility does not require cloning the old algorithm.

Study it for algorithmic ideas and correctness methodology, not as an API drop-in without verification.

### `juftin/pathlibrs`

Pure-Rust PyO3 reimplementation of `pathlib`.

It reports passing CPython 3.14.6's own `test_pathlib.py` suite:

```text
810 tests
0 failures
```

and reports lower memory use plus meaningful speedups, although its detailed numbers are more modest than a blanket headline:

* stat/I/O roughly 1.3–1.4x;
* stem/suffix roughly 1.5–1.8x;
* some operations several times faster;
* some construction/glob paths can be slower.

This is exactly the level of benchmark honesty we should emulate.

### `Indosaram/logxide`

Rust-backed logging implementation.

Historical sink-verified benchmarks report several-fold gains, around 5–11x for common file logging scenarios.

It also clearly demonstrates the compatibility cliff:

* custom Python handlers;
* custom Formatter subclasses;
* Logger/LogRecord subclassing;
* filters;
* callback paths

force fallback or differ.

This strongly supports a CPython-native design where the Python logging object model remains authoritative and only common formatting/emission kernels gain a Rust fast path.

### `ijl/orjson`

Proof that Rust can make Python JSON extremely fast.

Its project reports roughly:

* ~10x stdlib `json.dumps`;
* ~2x stdlib `json.loads`;

but it intentionally has different behavior/API in areas such as output type, `ensure_ascii`, integer policy, datetime/dataclass handling, etc.

Therefore:

**study its implementation techniques, not its semantics.**

A stdlib accelerator must remain `json`, not secretly turn `json` into `orjson`.

### `samuelcolvin/rtoml` and `lava-sh/toml-rs`

Strong evidence that TOML parsing maps well to Rust.

They demonstrate high-performance Rust parsing and good TOML spec coverage.

However error messages, extension behavior and Python type conversion need to match `tomllib` exactly before an in-tree accelerator can replace it.

### Generic Rust crates

Crates such as `url`, `regex`, generic INI parsers, mail parsers, etc. can be excellent algorithm references but are **not automatically compatible** with Python's historical semantics.

Examples:

* WHATWG URL parsing is not simply Python `urllib.parse`;
* Rust's mainstream regex semantics/features are not identical to Python `re`;
* generic INI parsers do not reproduce all `configparser` interpolation/default/case behavior.

Never sacrifice stdlib compatibility merely to reuse a popular crate.

## Ranked CPython 3.16 migration map

As part of this task, inspect the complete pinned:

```text
Lib/
Modules/
```

tree and put a refined ranked migration map into `rust-cpython/README.md`.

The research pass below is the seed ranking. Validate it against the actual pinned source. Adjust rankings only when you have a concrete source/benchmark/compatibility reason.

Use these dimensions:

```text
real-world frequency
current Python CPU share
coarseness of Python/Rust boundary
existing native implementation quality
semantic/compatibility tractability
quality of Rust prior art
ability to release the GIL / vectorize / batch
expected end-to-end impact
```

Do not rank something highly merely because its source file is large.

### 1. `zlib`

Current area:

```text
Modules/zlibmodule.c
```

Why #1:

* upstream Rust-for-CPython already selected it;
* `zlib-rs` has measured major wins;
* compression/decompression appears throughout wheels, zip files, HTTP, tooling;
* C ABI backend replacement is possible before rewriting the Python-facing extension.

Migration shape:

```text
existing zlib Python/C API
    -> zlib-rs backend first
    -> consider Rust module wrapper only later
```

Compatibility risk: compressed byte output differences at some levels; CRC32 performance regression observed on Darwin arm64.

### 2. `difflib`

```text
Lib/difflib.py             ~85 KB
```

Excellent target because it is CPU-heavy pure Python with large algorithmic kernels.

Prior art exists for exact-output Rust implementations and for radically faster exact matching algorithms.

Start with:

* SequenceMatcher matching-block core;
* ratio calculations;
* unified/context diff kernels.

Keep public classes/generator semantics in Python if that simplifies compatibility.

### 3. `tomllib`

```text
Lib/tomllib/_parser.py     ~25 KB
```

Very attractive:

* coarse `str/bytes -> Python tree` boundary;
* used heavily by modern packaging/tooling;
* parser/state-machine workload;
* multiple mature Rust TOML implementations.

Exact `TOMLDecodeError` behavior and `parse_float` callback semantics are compatibility gates.

### 4. `pathlib` + `glob` + `fnmatch`

```text
Lib/pathlib/__init__.py    ~54 KB
Lib/pathlib/types.py       ~17 KB
Lib/glob.py                ~20 KB
Lib/fnmatch.py              ~7 KB
```

Treat these as one path-matching/traversal opportunity rather than unrelated rewrites.

`pathlibrs` is unusually relevant prior art.

Prefer preserving Python `Path` classes while moving:

* path decomposition;
* suffix/stem operations;
* matching;
* glob automata;
* directory traversal batching

into native kernels.

Do not expect large wins for individual filesystem syscalls.

### 5. `json` / `_json`

```text
Lib/json/*
Modules/_json.c            ~67 KB
```

Huge real-world importance.

Already has a C accelerator, so the question is not "Rust vs Python"; it is whether a better Rust engine can materially outperform `_json` while exactly preserving stdlib:

* hooks;
* `parse_float`;
* `parse_int`;
* `object_hook`;
* `object_pairs_hook`;
* subclass behavior;
* formatting;
* escaping;
* error locations/messages.

Use orjson as performance/implementation research only.

### 6. `zipfile` + `zipimport`

```text
Lib/zipfile/__init__.py   ~110 KB
Lib/zipimport.py           ~34 KB
```

Very high leverage for:

* package installation;
* wheels;
* archive-heavy tooling;
* imports from ZIPs.

Potential Rust kernels:

* central-directory parsing;
* name decoding;
* CRC;
* member lookup;
* decompression orchestration;
* bulk extraction.

This composes naturally with `zlib-rs`.

Keep file-like object and extension-hook behavior in Python initially.

### 7. `base64` + `binascii`

```text
Lib/base64.py              ~19 KB
Modules/binascii.c         ~96 KB
```

The current Rust `_base64` proof makes this easy to experiment with, but normal Base64 currently already goes through native `binascii`.

The more compelling work may be:

* SIMD Base64;
* Base32;
* Base85/Ascii85/Z85;
* eliminating Python loops in codecs not already handled by binascii.

Benchmark against current C, not against pure Python strawmen.

### 8. `logging`

```text
Lib/logging/__init__.py    ~86 KB
Lib/logging/handlers.py    ~64 KB
Lib/logging/config.py      ~42 KB
```

Large potential because logging can dominate real applications.

Do **not** replace the whole object model.

Keep Python:

* Logger hierarchy;
* subclassing;
* custom handlers;
* filters;
* formatter objects;
* callbacks.

Accelerate common fast paths:

* level checks;
* record field normalization;
* default formatting;
* timestamp formatting;
* file/stream emission;
* perhaps batching.

Fallback to Python immediately when dynamic customization is detected.

### 9. `ipaddress`

```text
Lib/ipaddress.py           ~83 KB
```

Excellent pure-Python parsing/formatting/math candidate.

Rust's integer/network primitives map naturally.

Maintain exact Python classes and exception behavior; move parse/normalize/network arithmetic beneath them.

### 10. `urllib.parse`

```text
Lib/urllib/parse.py        ~51 KB
```

Extremely common and still largely Python string processing.

Do not blindly use Rust's `url` crate because WHATWG URL semantics are not Python `urllib.parse` semantics.

A custom compatibility-first parser is likely required.

Candidate kernels:

* splitting;
* quoting/unquoting;
* percent decoding;
* query parsing;
* byte scanning.

### 11. `configparser`

```text
Lib/configparser.py        ~56 KB
```

Parser/state-machine workload with a naturally coarse boundary.

Generic Rust INI crates are references only; Python interpolation/default/case semantics are richer.

A scanner/tokenizer accelerator beneath the Python policy layer is probably the cleanest design.

### 12. `email` parsing + `importlib.metadata`

Large relevant pieces include:

```text
Lib/email/_header_value_parser.py   ~115 KB
Lib/email/feedparser.py              ~23 KB
Lib/email/message.py                 ~48 KB
Lib/importlib/metadata/__init__.py   ~38 KB
```

This is more important than it first appears because Python package metadata uses email/RFC-style metadata parsing.

A fast RFC 5322/header parser could improve:

* package discovery;
* build/install tools;
* mail workloads;
* metadata-heavy command-line startup.

Keep policy/hooks/message classes in Python; accelerate tokenization/header parsing/body boundary scanning.

### 13. `_strptime`

```text
Lib/_strptime.py           ~37 KB
```

Classic CPU-heavy pure-Python parsing.

Very suitable for a compiled format parser/cache.

Preserve:

* locale behavior;
* exact directives;
* error text;
* timezone quirks.

Do not substitute a generic Rust datetime parser unless it reproduces Python semantics.

### 14. `tarfile`

```text
Lib/tarfile.py            ~121 KB
```

Important for packaging, source distributions and tooling.

Rust can accelerate:

* header parsing;
* numeric field decoding;
* PAX parsing;
* member scanning;
* copy loops.

Security/filter semantics must remain controlled by Python's existing API.

### 15. `plistlib`

```text
Lib/plistlib.py            ~30 KB
```

Particularly attractive for this project's macOS environment.

Both XML and binary plist parsing contain substantial structured-data work suitable for Rust.

Keep Python API/types exactly identical.

### 16. `bz2`

```text
Modules/_bz2module.c       ~24 KB
```

CPython 3.16 already knows about `libbzip2-rs`.

Likely first step is simply using the Rust C-ABI backend and measuring it rather than rewriting the wrapper.

Prior discussion suggests a modest roughly 5–10% performance benefit plus memory-safety value.

### 17. `re` compile pipeline

```text
Lib/re/_parser.py          ~48 KB
Lib/re/_compiler.py        ~14 KB
Lib/re/_optimizer.py       ~18 KB
Modules/_sre/*             native engine
```

Do **not** begin by replacing `_sre`.

The lower-risk opportunity is compiling regex patterns faster:

```text
pattern text
 -> Rust tokenizer/parser/optimizer
 -> same CPython regex bytecode/program
 -> existing _sre matcher
```

Python regex syntax and semantics are sufficiently distinctive that replacing the engine with Rust's mainstream `regex` crate is not a drop-in strategy.

### 18. `pickle` / `_pickle`

```text
Lib/pickle.py              ~71 KB
Modules/_pickle.c         ~245 KB
```

High real-world and pyperformance relevance, but much of the important path is already native C and deeply tied to arbitrary Python objects.

Potential Rust work should focus on bounded internal kernels/opcode dispatch rather than assuming a wholesale rewrite wins.

Compatibility risk is substantial.

### 19. `csv` / `_csv`

```text
Lib/csv.py                 ~20 KB
Modules/_csv.c             ~53 KB
```

Already accelerated in C.

A Rust parser could still be competitive through optimized scanning/SIMD, but must preserve every dialect and error behavior.

Prototype and measure before committing.

### 20. `tokenize`

```text
Lib/tokenize.py            ~23 KB
```

Useful for formatters, linters, source tools and IDE tooling.

A scanner over large source buffers is a natural native kernel.

Exact token positions and encoding behavior are the compatibility oracle.

### 21. `html.parser`

```text
Lib/html/parser.py         ~23 KB
```

State-machine text parsing maps cleanly to Rust.

Do not substitute html5ever wholesale: `HTMLParser` has its own observable behavior and callback model.

A Rust tokenizer feeding the existing Python callback layer is more plausible.

### 22. `shlex`

```text
Lib/shlex.py               ~14 KB
```

Small but clean lexical scanner candidate used by many CLI/build tools.

A good low-risk project after the highest-impact parsers.

### 23. `statistics`

```text
Lib/statistics.py          ~62 KB
```

Some workloads can benefit greatly from native loops, but exact support for:

* Decimal;
* Fraction;
* arbitrary numeric subclasses

makes universal acceleration difficult.

Use typed fast paths with Python fallback.

### 24. `uuid`

```text
Lib/uuid.py                ~38 KB
Modules/_uuidmodule.c       ~4 KB
```

Parsing/formatting and common generation algorithms are straightforward native work.

Likely modest end-to-end impact, but low implementation risk.

### 25. `xml.etree.ElementTree` / `_elementtree`

```text
Lib/xml/etree/ElementTree.py  ~76 KB
Modules/_elementtree.c       ~130 KB
Modules/pyexpat.c             ~88 KB
```

Already substantially native and backed by Expat, so Rust must beat a strong baseline.

Possible long-term win from a modern streaming Rust parser, but compatibility with ElementTree behavior is extensive.

Benchmark before migration.

### 26. `lzma`

```text
Modules/_lzmamodule.c       ~51 KB
```

Archive workloads make this relevant, but current liblzma is already highly optimized.

A Rust backend should only be adopted if it demonstrably improves performance/safety/maintenance without behavioral regressions.

### 27. `textwrap`

```text
Lib/textwrap.py             ~19 KB
```

Pure string processing and therefore technically easy to accelerate, but lower application-level impact.

Useful only after measurement shows meaningful usage.

### 28. `argparse`

```text
Lib/argparse.py            ~113 KB
```

Large pure-Python module and ubiquitous in CLI applications.

Actual argument parsing usually handles very little data, so import/startup cost may dominate and a Rust kernel may not materially help.

Investigate startup profiles before rewriting anything.

### 29. `heapq` / `_heapq`

```text
Lib/heapq.py                ~23 KB
Modules/_heapqmodule.c      ~25 KB
```

Hot operations already have C acceleration.

Rust is interesting mainly if algorithmic/specialized fast paths beat the existing native implementation.

### 30. `bisect` / `_bisect`

```text
Lib/bisect.py                ~3 KB
Modules/_bisectmodule.c     ~13 KB
```

Same caveat as heapq: already tiny/native and dominated by Python comparisons in many real uses.

Low priority unless profiles prove otherwise.

### 31. `functools` / `_functools`

```text
Lib/functools.py            ~44 KB
Modules/_functoolsmodule.c  ~63 KB
```

Very widely used, but hot pieces are already native and interact heavily with arbitrary Python callables.

Only targeted kernels make sense.

### 32. `collections` / `_collections`

```text
Lib/collections/__init__.py ~55 KB
Modules/_collectionsmodule.c ~84 KB
```

`deque` and other critical paths are already C.

Potential Rust migration is primarily a safety/maintenance project unless benchmarks identify a new algorithmic win.

## Explicitly deprioritize

Do not assume "replace all C with Rust" is the performance strategy.

Areas such as these already have very strong native implementations or are dominated by syscalls/external libraries:

```text
_ssl / OpenSSL
_hashlib / OpenSSL
sqlite3 / SQLite
_io filesystem operations
socket
subprocess
curses
decimal / mpdecimal
compression.zstd / libzstd
most POSIX wrappers
```

They can eventually be Rust for safety/maintainability, but they are not the first place to look for practical CPython speed.

Likewise, highly dynamic modules such as:

```text
inspect
typing
dataclasses
threading
asyncio orchestration
```

may contain isolated acceleratable kernels, but a wholesale Rust rewrite is unlikely to be the cleanest route.

## Roadmap tiers

After validating the actual pinned tree, divide the ranked map into approximately:

```text
Tier A — implement/prototype early
Tier B — strong candidate after measurement
Tier C — targeted kernel only / conditional
```

A reasonable initial Tier A should contain roughly:

```text
zlib
difflib
tomllib
pathlib/glob/fnmatch
json
zipfile/zipimport
base64/binascii
logging fast path
ipaddress
urllib.parse
```

but adjust based on concrete evidence.

For each roadmap row include:

```text
rank
module/area
current Python/C implementation
expected leverage
recommended Rust boundary
compatibility hazards
relevant CPython tests
known Rust prior art
measurement needed before migration
```

Do not invent numerical speedup estimates where none have been measured.

## Future architectural issue: many Rust stdlib modules

The current Rust-for-CPython model builds each shared Rust extension as its own `cdylib`.

As the number of Rust modules grows, duplicated Rust `core`/`alloc` and code size become relevant.

Rust-for-CPython issue 33 already calls this out and discusses a shared dylib containing Rust runtime pieces.

Do not solve that in this task.

Just record it in the README as a scaling issue to revisit after there are multiple real Rust modules. Prematurely inventing a common Rust runtime now would make the initial foundation more fragile.

For statically linked CPython, continue to respect the current single `cpython-rust-staticlib` aggregation strategy, which exists partly to avoid conflicting Rust symbols/UB.

## Acceptance criteria

This task is complete only when all of the following are true:

1. The existing CPython 3.14.6 build path has unchanged behavior.
2. Frozen Linux code has not been redesigned.
3. `rust-cpython/` is clearly isolated and understandable on its own.
4. Rust-for-CPython source is pinned by exact commit and SHA-256.
5. Rust is pinned to exactly `nightly-2026-09-15`.
6. The build cannot silently use another Rust toolchain.
7. Cargo dependencies are locked.
8. Build source is immutable and compilation is out-of-tree.
9. The native Apple Silicon 3.16 interpreter builds successfully.
10. The interpreter identifies itself as CPython 3.16.
11. The in-tree Rust `_base64` extension builds and imports.
12. Its exported CPython initializer and Mach-O properties are verified.
13. Upstream Cargo tests pass with the pinned nightly.
14. Relevant CPython stdlib tests pass.
15. A broad CPython regression run has been completed and unexpected failures resolved.
16. Existing repository unit tests remain green.
17. The build provenance records both Rust and C toolchains.
18. `rust-cpython/README.md` explains the environment concisely.
19. That README contains the refined ~30-entry ranked migration map.
20. No actual new stdlib migration beyond what exists in the pinned Rust-for-CPython source has been attempted in this task.

## Implementation style

Keep the implementation compact.

Prefer:

* stdlib-only Python;
* small typed functions;
* immutable source pins;
* fail-closed validation;
* deterministic paths;
* explicit subprocess environments;
* existing generic python-build helpers when they genuinely fit.

Avoid:

* framework-building;
* dependency injection abstractions;
* configuration DSLs;
* a generic "multiple Python versions" architecture;
* duplicated source cache logic;
* YAML;
* new third-party Python dependencies;
* speculative portability abstractions;
* gratuitous shell scripts;
* documentation ceremony.

This should feel like a small, high-quality experimental sibling to the existing build rather than a second build framework fighting the first one.

Before finishing, inspect the final diff as a whole and remove duplication, dead abstractions, temporary debugging code and redundant documentation.

Then run the relevant tests/builds yourself and leave the repository in a state where I can continue with the next instruction:

> implement the first migration from the ranked Rust stdlib roadmap
