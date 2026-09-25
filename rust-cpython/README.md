# Rust-for-CPython research lane

This directory builds the pinned Rust-for-CPython **CPython 3.16.0a0** fork as
a native Apple Silicon macOS development interpreter. It is an isolated
experiment: it does not change the production CPython 3.14.6 pin, frozen Linux
targets, production packaging, or release workflow. This is CPython with Rust
implementation kernels behind existing Python and CPython C-ABI boundaries;
it is not RustPython.

The verified source pin is `Rust-for-CPython/cpython` commit
`b812b4a7b9efaca46b98544a8633b7d7e454166b` from the informational
`3.x-rust-in-cpython` branch. Its archive digest, size, version, license, and
Cargo lock digest are in [sources.lock.json](sources.lock.json). The Rust
compiler is exactly `nightly-2026-09-15`, declared in
[rust-toolchain.toml](rust-toolchain.toml). The lane creates a private Cargo
home and wrapper; each Cargo invocation goes through `rustup run` for that
nightly. Do not run `cargo update` or alter the lockfile.

## Commands

```sh
python3 rust-cpython/build.py doctor  # read-only host, pins, and toolchain check
python3 rust-cpython/build.py fetch   # verified sources, LLVM, and locked Cargo deps
python3 rust-cpython/build.py build   # out-of-tree optimized build, network denied
python3 rust-cpython/build.py fetch --zlib-rs  # also cache pinned optional backend
python3 rust-cpython/build.py build --zlib-rs  # isolated optional zlib candidate
python3 rust-cpython/build.py fetch --zlib-hybrid # cache the same pinned backend
python3 rust-cpython/build.py build --zlib-hybrid # Rust inflate, platform deflate
python3 rust-cpython/build.py fetch --zlib-oneshot # cache the same pinned backend
python3 rust-cpython/build.py build --zlib-oneshot # Rust one-shot, platform streams
python3 rust-cpython/build.py build --url-unquote # optional guarded Rust percent decoder
python3 rust-cpython/build.py test    # Cargo, focused CPython, then broad regression
python3 rust-cpython/build_no_rust.py # matched same-source benchmark control
python3 rust-cpython/build.py clean   # remove generated outputs; retain private Cargo cache
```

Only native `aarch64-apple-darwin` is supported. The lane reuses the root
`bootstrap.lock.json` LLVM 23.1.2, Xcode SDK, deployment floor, and GNU Make
identity, but keeps CPython 3.16 configuration and outputs under this
directory. Source is safely re-extracted to `work/source/`; compilation is in
`work/build/`; installation is in `stage/`. The build runs with
`CARGO_NET_OFFLINE=true` under macOS `sandbox-exec` after `fetch` caches the
locked inputs. Machine-readable provenance and test results are written to
`results/build.json`; detailed command output stays in `logs/`.

On macOS, the fork's bindgen build script does not discover LLVM resource
directories on the host. The lane sets
`BINDGEN_EXTRA_CLANG_ARGS=-resource-dir=<locked LLVM resource dir>` so
`cpython-sys` uses the built-in headers paired with the locked clang; this
changes C header parsing only and does not add Rust code-generation flags.

To refresh the experimental CPython pin later, select and record one exact
commit from the Rust-for-CPython 3.16 line, then update the archive URL, size,
SHA-256, version, license, and Cargo lock digest together in
`sources.lock.json`. Reinstall or change the Rust nightly only as an explicit
toolchain decision in `rust-toolchain.toml`. Verify the new archive and lock
with `fetch`, then run `build` and `test`; never follow a moving branch or
regenerate Cargo.lock as part of the normal build.

The build uses a GIL-enabled optimized CPython, `-O3`, ThinLTO, and the
CPython `-m test --pgo` profile task with the locked `llvm-profdata`. CPython's
own Cargo integration chooses the Rust release profile and builds the Rust
workspace; this lane does not add Rust `RUSTFLAGS`, PyO3, a new package
manager, or a product archive. `ensurepip` is not installed.

## What this pin proves

The fork's Cargo workspace has `_base64`, `cpython-build-helper`,
`cpython-rust-staticlib`, and `cpython-sys`. CPython's normal module build
produces `_base64` as an extension with `PyInit__base64`; the lane verifies
that it imports, matches `binascii` for representative byte buffers, has the
expected extension suffix and export, and is arm64 Mach-O with the locked
deployment floor. It also runs the workspace Cargo tests and CPython tests.

At this commit, `_base64` is an integration proof, not a faster public
`base64` implementation: `Lib/base64.py` still routes its normal APIs through
`binascii`. The ordinary lane build still compiles `Modules/zlibmodule.c`
against the platform zlib library. `--zlib-rs` builds an optional candidate
from the pinned proof backend, retaining platform zlib for `binascii`; its
whole-build and public-workload evidence is in
[`experiments/zlib-full-candidate-20260924.md`](experiments/zlib-full-candidate-20260924.md).
`--zlib-hybrid` builds a separate candidate using prefixed Rust inflate
symbols while retaining platform zlib for compression, checksums, public
version identity, and `binascii`. Its digest-checked source patch is inert in
the ordinary and full-backend modes. The hybrid matched all 876 sampled
compressed byte outputs and passed focused CPython consumers. Seven paired
sustained public decode and gzip jobs then used about 36% less process CPU;
the real pinned source-tar read instead used 10.81% more process CPU. The
current all-stream hybrid cannot be promoted. See
[`experiments/zlib-hybrid-proof-20260924.md`](experiments/zlib-hybrid-proof-20260924.md)
and [`experiments/source-tar-hybrid-20260925.md`](experiments/source-tar-hybrid-20260925.md).
`--zlib-oneshot` is a separate built experiment that routes only public
`zlib.decompress` to prefixed Rust inflate, keeping persistent streaming
decompressors on platform zlib. Its installed symbol route passed inspection.
Five paired complete-process comparisons found 36.6% lower wall time and 38.4%
lower kernel CPU for sustained one-shot decode; gzip, source-tar, and streaming
tasks remained within control noise. A separate synthetic SQLite task with
many small, highly compressible BLOBs used 10.8% less complete-process wall
time and 10.9% less kernel CPU. A second SQLite task spanning repetitive to
nearly random BLOBs reversed that result: 8.4% more wall time and 9.0% more
CPU, beyond control noise. The unstripped installed extension is 1.59 MB
larger. This mixed-input regression blocks general promotion; memory parity
and semantic edges also remain open. A link-size reduction is scoped but
deferred until that regression is resolved. See
[`experiments/zlib-oneshot-comparison-20260925.md`](experiments/zlib-oneshot-comparison-20260925.md)
and [`experiments/zlib-oneshot-mixedblobs-20260925.md`](experiments/zlib-oneshot-mixedblobs-20260925.md);
the size audit is in
[`experiments/zlib-oneshot-size-feasibility-20260925.md`](experiments/zlib-oneshot-size-feasibility-20260925.md).
`--url-unquote` selects a digest-checked optional source patch after the
ordinary quote patches. Its exact-ASCII-string and default UTF-8 replacement
guard routes percent decoding through the existing private extension; other
inputs keep the Python path. The default build remains quote-only. A matched
installed-stage proof improved the complete catalog search-form task. The
optional source now builds and installs with the locked LLVM and PGO recipe;
fresh source and installed-byte checks found the intended selection, and the
two complete catalog URL output digests matched. Five serial installed-tree
pairs showed 42.9% lower complete search-form wall time and 44.0% lower kernel
CPU, beyond self-noise. The separate native builds have different PGO profiles;
the prior same-executable proof is cleaner for attribution. Broad public
semantic and upstream memory checks remain open. A separate three-way
resource pass found decoder root peak RSS within upstream self-noise on the
search task; unique/proportional and retained memory and allocations remain
unqualified. Against vanilla upstream, the complete search task used 49.6%
less wall time and 50.8% less kernel CPU across five pairs. Different source
ancestry and PGO profiles constrain attribution of that overall difference.
The
eligible native path also bypasses initialization and replacement of private
parser globals. Static source tracing finds the same built-in UTF-8 decoder
under the exact guard, while public differential behavior remains to check. See
[`experiments/url-unquote-source-patch-20260925.md`](experiments/url-unquote-source-patch-20260925.md)
[`experiments/url-unquote-build-20260925.md`](experiments/url-unquote-build-20260925.md),
[`experiments/url-unquote-installed-comparison-20260925.md`](experiments/url-unquote-installed-comparison-20260925.md),
[`experiments/url-unquote-upstream-memory-20260925.md`](experiments/url-unquote-upstream-memory-20260925.md),
[`experiments/url-unquote-upstream-speed-20260925.md`](experiments/url-unquote-upstream-speed-20260925.md),
and [`experiments/url-unquote-contract-audit-20260925.md`](experiments/url-unquote-contract-audit-20260925.md).
The post-change catalog profiles found no compelling next URL kernel: the
largest remaining individual parser self-time row was under 9% of either
instrumented complete task and included the existing native route. See
[`experiments/url-residual-profile-20260925.md`](experiments/url-residual-profile-20260925.md).
Separately,
[`zlib-proof/`](zlib-proof/README.md) links the pinned Rust zlib C ABI under
that unchanged CPython wrapper and runs CPython's zlib and compression-consumer
tests. This is an isolated backend proof, not a production build change.
`Modules/_bz2module.c` still uses its existing backend. Preserve the upstream
Rust-for-CPython model (`cpython-sys` plus CPython-owned internal Rust APIs);
PyO3 remains research prior art, not a dependency for in-tree modules.

To build and test that isolated proof after `build.py fetch`:

```sh
python3 rust-cpython/build_no_rust.py
python3 rust-cpython/zlib-proof/build.py fetch
python3 rust-cpython/zlib-proof/build.py build
python3 rust-cpython/zlib-proof/build.py test
```

The source pin, proof boundary, test results, and current limits are documented
in [`zlib-proof/README.md`](zlib-proof/README.md).

## Migration method

The ranking below is a source-informed starting order, not a claim that any
Rust port is already faster. The implementation should keep the existing
Python API, use a coarse kernel boundary, and retain Python/C code as an
oracle or fallback where that helps compatibility. Before a migration, run
the named unchanged CPython tests on baseline and migrated builds, add
differential/property tests for semantic edges, then benchmark realistic
end-to-end workloads against the current implementation (including existing
C accelerators). Report separate cold/warm, input-size, callback, and I/O
cases. Keep a Rust path only when it has exact behavior and a repeatable
measured benefit or a clearly scoped safety/maintenance case.

## Performance comparison

The pinned fork's Rust `_base64` module is not called by public `base64.py`,
so its presence alone does not imply an interpreter-wide speedup. For a fair
same-version comparison, `build_no_rust.py` builds the same locked source,
with the same LLVM, SDK, CPU flags, ThinLTO, and PGO workload, while hiding
Cargo from configure so `_base64` is absent. The enhanced benchmark's local
Apple Silicon path compares these interpreters on the smoke suite and invokes
the Rust encoder directly for its Base64 workloads. Native macOS runs now
record root kernel CPU plus a separate process-tree RSS and sampled physical
footprint pass. Unique/proportional memory and allocation measurements remain
unqualified for this 3.16 lane.

After `fetch`, `build_no_rust.py`, `build`, and `test`, run:

```sh
rust-cpython/stage/bin/python3.16 rust-cpython/bench_base64.py \
  --output rust-cpython/results/base64-pyperf.json \
  --processes 5 --values 8 --warmups 2 --min-time 0.1

python3.14 benchmarks/bench.py run \
  --baseline rust-cpython/stage-no-rust/bin/python3.16 \
  --candidate rust-cpython/stage/bin/python3.16 \
  --baseline-label "Rust-for-CPython 3.16 without _base64" \
  --candidate-label "Rust-for-CPython 3.16 with _base64" \
  --baseline-kind custom --candidate-kind custom \
  --suite smoke --profile standard --local
```

The first report compares the Rust implementation directly with `binascii`
and public `base64`; the second tests the added module alongside startup,
serialization, and multiprocessing workloads. Neither is an Astral PBS or
upstream CPython comparison. A broader interpreter comparison needs a
same-version vanilla CPython build and a host/platform-matched benchmark.
The measured results, repeated runs, and limits are recorded in
[`PERFORMANCE.md`](PERFORMANCE.md).

### Tier A — candidate map and measured outcomes

| Rank | Area: current implementation and CPython tests | Leverage and proposed Rust boundary | Hazards, prior art, and measurement gate |
| ---: | --- | --- | --- |
| 1 | **zlib** — `Modules/zlibmodule.c`; `test_zlib.py`, `test_gzip.py`, `test_binascii.py` | Compression and decompression sit under ZIP, gzip, wheels, and HTTP. Keep the CPython C/Python API and swap only the backend. | The whole-backend candidate changed 210 of 876 sampled compressed encodings. The inflate-only hybrid preserved those bytes and lowered CPU about 36% in sustained direct decode/gzip tasks, but raised CPU 10.81% in a checked public read of the locked CPython source `.tar.gz`. A one-shot split removed that tar regression and improved sustained decode CPU by 38.4%, but mixed-compressibility small BLOBs regressed 9.0% in CPU. The extension adds 1.59 MB unstripped. Neither route meets the breadth and resource gates; see [`experiments/zlib-oneshot-mixedblobs-20260925.md`](experiments/zlib-oneshot-mixedblobs-20260925.md). |
| 2 | **difflib (rejected routes)** — `Lib/difflib.py`; `test_difflib.py` | A substantial pure-Python matching and diff kernel was the initial hypothesis. | Stop the transparent public matcher and one-shot `unified_diff` routes: exposed mutable state, callbacks, and trace-mediated mutation change behavior under snapshot dispatch. The measured snapshot alone also added CPU. See [`experiments/difflib-one-shot-contract-20260924.md`](experiments/difflib-one-shot-contract-20260924.md). |
| 3 | **tomllib (deferred)** — `Lib/tomllib/{_parser,_re,_types}.py`; `test_tomllib/{test_data,test_error,test_misc}.py` | A parser can take one document and return an ordinary Python tree, leaving `parse_float` callback policy at the Python boundary. | A pinned CPython build-tool command parses a real 72,592-byte manifest three times, and parser Python frames were 53.4% of its instrumented task time. Its direct process used only 0.07 CPU seconds, and approved inputs lack a substantial application metadata task. Pin and profile that task before a broad parser; preserve duplicate keys, datetime/error details, and callbacks. See [`experiments/tomllib-workload-scout-20260925.md`](experiments/tomllib-workload-scout-20260925.md). |
| 4 | **ipaddress** — `Lib/ipaddress.py`; `test_ipaddress.py` | Parse/normalize once and move integer subnet arithmetic and formatting kernels beneath existing Python address/network classes. | Preserve legacy forms, strict masks, exceptions, subclass behavior, and ordering. Rust `std::net`/`ipnet` offer primitives, not Python semantics. Differential/property-test IPv4/IPv6 and benchmark routing-table and parsing workloads. |
| 5 | **urllib.parse** — `Lib/urllib/parse.py`; `test_urlparse.py`, `test_urllib.py` | A guarded Rust `quote_from_bytes` byte scan reaches public `quote` callers. An optional source patch adds exact ASCII/default-decoder `unquote`. | The installed quote candidate improved three complete catalog URL tasks beyond local noise, while Django cold/warm requests showed no established benefit. A matched-compiler unquote proof cut complete search-form wall/CPU by 43.6%/44.7%; the fresh opt-in native build repeated a 42.9%/44.0% gain beyond self-noise. Broad public semantic qualification and upstream memory/allocation parity remain open. See [`experiments/url-unquote-proof-20260925.md`](experiments/url-unquote-proof-20260925.md) and [`experiments/url-unquote-installed-comparison-20260925.md`](experiments/url-unquote-installed-comparison-20260925.md). |
| 6 | **json / `_json` (deferred)** — `Lib/json/`, `Modules/_json.c`; `test_json/`, `test_free_threading/test_json.py` | A full-document native engine would need to beat the existing C encoder and scanner while preserving Python's dynamic hooks. | Two complete catalog-export profiles found that the fixture application encodes and immediately decodes each of 512 records before final encoding. That round trip, with the C accelerator already active, is the measured bottleneck; no C-only headroom or Rust advantage has been established. See [`experiments/json-headroom-20260925.md`](experiments/json-headroom-20260925.md). |
| 7 | **zipfile / zipimport** — `Lib/zipfile/`, `Lib/zipimport.py`; `test_zipfile/`, `test_zipfile64.py`, `test_zipimport.py` | Accelerate central-directory parsing, indexing, name decoding, CRC and bulk member processing while retaining Python file-like APIs. | A warmed complete-wheel profile put `ZipFile._RealGetContents` at 10% of instrumented work, with a broad file-like and replaceable-object contract. Defer a native directory parser pending stronger headroom; cold ZIP import uses a separate reader. See [`experiments/zipfile-profile-20260925.md`](experiments/zipfile-profile-20260925.md). |
| 8 | **pathlib / glob / fnmatch** — `Lib/pathlib/`, `Lib/glob.py`, `Lib/fnmatch.py`; `test_pathlib/`, `test_glob.py`, `test_fnmatch.py` | Keep `Path` objects and flavor policy in Python; consider batched lexical matching and directory traversal kernels. | PathLike, Windows/POSIX flavors, case rules, symlinks, races, and callbacks constrain batching. `juftin/pathlibrs` is directly relevant. Separate lexical-only benchmarks from filesystem traversal and test symlink/race behavior. |
| 9 | **tokenize** — `Lib/tokenize.py`; `test_tokenize.py`, `test_free_threading/test_tokenize.py` | Scan a complete encoded source buffer into token records, then preserve the existing iterator and token objects in Python. | BOMs, encodings, byte/character columns, partial input, f-strings and errors must match. Rust lexer/parser projects are design references only. Differential-test the CPython source corpus and malformed/chunked input; measure formatter/linter workloads. |
| 10 | **logging fast path** — `Lib/logging/`; `test_logging.py` | Keep logger hierarchy, records, handlers and customization in Python; accelerate the default record/format path or batch writes only when no customization is active. | Subclassing, filters, formatters, locks, exception formatting and stream behavior are contracts. `logxide` is prior art, not a compatible replacement. Benchmark with a verified sink, disabled/enabled levels, custom hooks, and realistic formatting. |

### Tier B — strong candidates after the first prototypes

| Rank | Area: current implementation and CPython tests | Leverage and proposed Rust boundary | Hazards, prior art, and measurement gate |
| ---: | --- | --- | --- |
| 11 | **`_strptime`** — `Lib/_strptime.py`; `test_strptime.py`, `test_datetime.py`, `test_time.py` | Compile format directives once and scan input natively, retaining Python's locale and cache policy. | Locale changes, directive quirks, cache invalidation, platform behavior, and exact errors. Chrono is reference material only. Compare cached/uncached parsing across locales and date formats. |
| 12 | **tarfile** — `Lib/tarfile.py`; `test_tarfile.py` | Accelerate header/PAX scanning and copy loops under the existing extraction and security policy. | Streaming/file-like behavior, numeric variants, filters, malformed data, and traversal protection are critical. Rust `tar` crates are prior art. Measure scan vs decompression vs I/O and test malicious archives. |
| 13 | **bz2** — `Modules/_bz2module.c`, `Lib/bz2.py`; `test_bz2.py`, `test_free_threading/test_bz2.py` | First test a Rust C-ABI compression backend beneath the existing wrapper. | Preserve stream/memory behavior, format variants, output and errors. `libbzip2-rs` is discussed upstream but not integrated in this pinned tree. Compare bytes, memory, streaming, and archive workloads with libbz2. |
| 14 | **configparser** — `Lib/configparser.py`; `test_configparser.py` | Move only line scanning/tokenization into Rust and keep interpolation, defaults and mapping policy in Python. | Custom delimiters, interpolation, case handling, comments, callbacks and exact errors exceed generic INI semantics. Rust INI crates are references. Measure real startup/config workloads as well as large-file scans. |
| 15 | **email parsing / importlib.metadata** — `Lib/email/{_header_value_parser,feedparser,message}.py`, `Lib/importlib/metadata/__init__.py`; `test_email/`, `test_importlib/` | Start with RFC header tokenization or body-boundary scanning; preserve Python message/provider objects and policy. | Folding, defects, MIME, filesystem providers, hooks and custom policies. `mail-parser`/`mailparse` are references. Benchmark email parsing separately from package metadata discovery and import startup. |
| 16 | **`re` compile pipeline** — `Lib/re/{_parser,_compiler,_optimizer,_constants}.py`, `Modules/_sre/`; `test_re.py`, `test_free_threading/test_re.py` | Parse/optimize to the same CPython regex bytecode while retaining `_sre` as the matcher. | Syntax, flags, error spans/messages, cache behavior and backtracking semantics. Rust `regex` is not a drop-in engine; `regex-syntax` is parser prior art. Fuzz patterns and separate cold compilation from warm matching. |
| 17 | **plistlib** — `Lib/plistlib.py`; `test_plistlib.py` | Parse or serialize a whole XML/binary plist buffer to ordinary Python values. | UID, datetime, key ordering, binary details, and error behavior. Rust plist crates are prior art. Test large real macOS plists and compare bytes as well as decoded values. |
| 18 | **base64 / binascii** — `Lib/base64.py`, `Modules/binascii.c`, `Modules/_base64/`; `test_base64.py`, `test_binascii.py` | Consider raw buffer codec kernels, especially operations not already handled efficiently by `binascii`. | Standard Base64 already enters C; `_base64` is not wired into the public module. The first size sweep in [`PERFORMANCE.md`](PERFORMANCE.md) found Rust 39.5% faster at 64 bytes but 42–48% slower at 4 KiB and above. Preserve alphabets, newlines, validation and buffer formats; improve the bulk path before promoting. |
| 19 | **csv / `_csv`** — `Lib/csv.py`, `Modules/_csv.c`; `test_csv.py`, `test_free_threading/test_csv.py` | Only consider a row scanner or batched field parser if it beats the existing C accelerator. | Dialects, custom iterators, quoting, errors and callbacks are observable. `csv-core` is prior art. Compare realistic dialects and row sizes against `_csv`; separate scanning from Python object creation. |
| 20 | **pickle / `_pickle`** — `Lib/pickle.py`, `Modules/_pickle.c`; `test_pickle.py`, `test_picklebuffer.py`, `test_pickletools.py` | Restrict experiments to bounded opcode/buffer kernels; keep arbitrary object construction and callbacks at CPython's boundary. | Existing implementation is native and deeply coupled to object identity, reducers, protocols and callbacks. Serde is not a compatibility replacement. Profile real serialization before prototyping; compare every protocol and object graph. |

### Tier C — targeted kernel only, or wait for profile evidence

| Rank | Area: current implementation and CPython tests | Leverage and proposed Rust boundary | Hazards, prior art, and measurement gate |
| ---: | --- | --- | --- |
| 21 | **statistics** — `Lib/statistics.py`, `Modules/_statisticsmodule.c`; `test_statistics.py` | A typed batch kernel may help large built-in numeric inputs; keep generic numeric behavior in Python. | Decimal, Fraction and subclasses have distinct arithmetic semantics; current C support is narrow by design. Compare float-only large batches with the existing C path and confirm type fallbacks. |
| 22 | **uuid** — `Lib/uuid.py`, `Modules/_uuidmodule.c`; `test_uuid.py`, `test_free_threading/test_uuid.py` | Parse/format bytes and fields in a kernel; leave OS entropy, time and privacy/version choices to existing policy. | Preserve generation source selection, clock state, privacy and exact variants. Rust UUID crates are prior art. Measure parsing separately from OS-backed generation and verify randomness behavior. |
| 23 | **ElementTree / `_elementtree`** — `Lib/xml/etree/ElementTree.py`, `Modules/_elementtree.c`, `Modules/pyexpat.c`; `test_xml_etree.py`, `test_xml_etree_c.py`, `test_xml.py` | If needed, target streaming tokenization while preserving ElementTree classes and Expat-facing behavior. | Already largely native; namespaces, targets, comments, DTD and incremental callbacks are extensive contracts. `quick-xml` is not a drop-in. Benchmark against Expat and existing C before any migration. |
| 24 | **lzma** — `Lib/lzma.py`, `Modules/_lzmamodule.c`; `test_lzma.py`, `test_free_threading/test_lzma.py` | Swap only the codec backend beneath the existing wrapper if a Rust backend proves useful. | Filters, formats, memory limits, streaming and error behavior matter; liblzma is already optimized. Compare formats and memory/throughput against current liblzma. |
| 25 | **html.parser** — `Lib/html/parser.py`; `test_htmlparser.py`, `test_html.py` | A Rust incremental tokenizer could feed the existing Python callback API. | Chunk boundaries, malformed HTML, entity conversion, script/style handling and callbacks are observable. `html5ever` follows different parsing semantics. Differential-test malformed and incremental inputs; measure parse-only and callback-heavy use. |
| 26 | **shlex** — `Lib/shlex.py`; `test_shlex.py` | A whole-string split scanner could return tokens while preserving Python's public options. | `source`, punctuation, comments, quoting, escaping and POSIX/non-POSIX modes are important; shell crates differ. Benchmark real command strings and full build/config workloads. |
| 27 | **textwrap** — `Lib/textwrap.py`; `test_textwrap.py` | A coarse whole-string wrapping kernel is plausible for repeated large inputs. | Tabs, whitespace, hyphens, long-word policy, code points and subclass overrides. No exact Rust prior art identified. Measure large-document formatting; low-volume cases may not repay FFI. |
| 28 | **argparse** — `Lib/argparse.py`; `test_argparse.py` | Only consider isolated token scanning after profiling startup and parse-heavy workloads. | Custom actions/types, subclasses, callbacks, error/usage text and help formatting make a broad port risky. `clap` has different APIs. Separate import cost from parsing and benchmark real CLI argument sets. |
| 29 | **heapq / `_heapq`** — `Lib/heapq.py`, `Modules/_heapqmodule.c`; `test_heapq.py`, `test_free_threading/test_heapq.py` | Explore specialized kernels only if profiles identify a gap in existing C operations. | User comparisons and Python ordering are arbitrary; Rust `BinaryHeap` semantics differ. Compare exact outputs/callback counts with C for realistic heap sizes. |
| 30 | **bisect / `_bisect`** — `Lib/bisect.py`, `Modules/_bisectmodule.c`; `test_bisect.py`, `test_free_threading/test_bisect.py` | No broad rewrite; a batch operation is only interesting if it reduces repeated Python/C crossings. | `key`, rich comparisons, insertion mutation and callbacks dominate many cases; current operations are already native. Profile call patterns, then compare complete workloads with `_bisect`. |
| 31 | **functools / `_functools`** — `Lib/functools.py`, `Modules/_functoolsmodule.c`; `test_functools.py`, `test_free_threading/test_functools.py` | Limit work to measured helpers not already implemented in C. | Descriptors, arbitrary callables, caching and introspection are delicate; most hot paths are native already. Profile imports and operations before attempting a kernel; test exact call and cache behavior. |
| 32 | **collections / `_collections`** — `Lib/collections/`, `Modules/_collectionsmodule.c`; `test_collections.py`, `test_free_threading/test_collections.py` | Only consider a measured batch operation; retain existing native deque/container implementations otherwise. | Hashing, equality hooks, ordering, subclassing and reentrancy are central. Core structures are already C; benchmark real operations and treat safety/maintenance as a separate claim from speed. |

## Scaling question to revisit

Each shared Rust extension currently builds as its own `cdylib`. If several
stdlib modules move to Rust, duplicated `core`/`alloc` code and binary size
may become material. Rust-for-CPython issue 33 discusses sharing runtime
pieces in a dylib. Revisit only after multiple real modules exist and their
size is measured. For static CPython, keep using the upstream
`cpython-rust-staticlib` aggregation model; do not invent a shared runtime in
this initial lane.
