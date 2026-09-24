# Independent public stdlib target: tomllib

## Recommendation

**Defer a Rust parser implementation; proceed with a bounded public-workload
measurement first.** The pinned CPython 3.16 parser is pure Python, and a
whole-document native boundary is plausible. The available local project
documents are only 133–798 bytes, however, and the short profile below shows
where those parses work, not a meaningful application bottleneck or a speedup.
No TOML parser crate is in the pinned Cargo lock. A new crate or lock change
requires a separate scope decision; writing an exact TOML parser in the
existing FFI workspace would be a substantial compatibility project.

This target is independent of zlib: `tomllib.load` reads binary file objects,
decodes UTF-8 and parses TOML; it does not call compression APIs. The product
CPython 3.14.6 build remains outside this experiment.

## Pinned source and public contract

The source is Rust-for-CPython commit
`b812b4a7b9efaca46b98544a8633b7d7e454166b` (3.16.0a0), locked in
`rust-cpython/sources.lock.json`. `Lib/tomllib/__init__.py` exports `load`,
`loads`, and `TOMLDecodeError`. `Lib/tomllib/_parser.py` implements binary-file
reading and decoding in `load`, CRLF normalization and statement parsing in
`loads`, plus table/array state in `Output`, `NestedDict`, and `Flags`.
`Lib/tomllib/_re.py` matches numbers, dates, and times and builds Python
`datetime` values. `Lib/tomllib/_types.py` supplies annotations only.

The public unit of work is one `tomllib.load(binary_file)` or
`tomllib.loads(str)` call returning ordinary nested Python `dict`, `list`,
`str`, `bool`, `int`, `float`, `date`, `time`, and `datetime` objects.
`load` owns the binary-file contract and UTF-8 decode error behavior.
`loads` accepts a string, normalizes CRLF even inside string literals, and
raises `TOMLDecodeError` with `msg`, `doc`, `pos`, `lineno`, `colno`, and exact
formatted text. The parser checks duplicate keys and namespace mutability
through `Flags`; arrays of tables and dotted keys require the same insertion
order and error positions. `parse_float` receives the original numeric text
in parse order, including signed `inf`/`nan`, and may return any object except
`dict` or `list`. Its callback exceptions propagate. A replacement must
preserve callbacks that run before a later parse error, not merely the final
tree. `MAX_KEY_PARTS` and the array/table recursion behavior are tested.

The source's direct stdlib caller search found public use principally in
`Lib/test/test_tomllib/`; `test_platform.py` also calls `tomllib.load` for
Emscripten configuration. Project metadata is the relevant external public
use: `pyproject.toml`, Cargo manifests, and platform config files exercise
the same `load` path. The unchanged suite is
`Lib/test/test_tomllib/{test_data,test_error,test_misc}.py`; its fixture tree
contains 14 valid and 50 invalid TOML files at this pin. `test_misc.py`
also checks that parsing a text-only document does not eagerly import
`tomllib._re`, callback conversion, binary-mode errors, and recursion limits.

## Short diagnostic (location evidence only)

On 2026-09-24, the existing `stage-no-rust/bin/python3.16` parsed four
files from the pinned source, 100 times each through public
`tomllib.load(io.BytesIO(data))` under `cProfile`:

| Input relative to pinned source | Bytes | SHA-256 |
| --- | ---: | --- |
| `Cargo.toml` | 298 | `bae2fc9c0b8a5a0e9380d6d690130e18e01bb3ce0d7af77e36362e9716f7739f` |
| `Tools/peg_generator/pyproject.toml` | 133 | `8ca51521e0b4e31b2df44250b79a5783c9d216bc01389c348f68ead7b10718b8` |
| `Platforms/emscripten/config.toml` | 798 | `4c63d06144531d4dabd5887ec1cd94c221cd2cf0086b9753141e528aa230b457` |
| `Lib/test/test_importlib/metadata/data/sources/example2/pyproject.toml` | 160 | `2dabaecb8e9b3d87a9e0c5ba7e7e360f016db570049d9ea677eb370ccb7b7f79` |

The 400 complete parses made 94,702 profiled calls in 0.026 s of
**instrumented** time. `loads` accounted for the full 0.026 s cumulative;
2,100 `key_value_rule` calls accounted for 0.017 s, 2,100
`parse_key_value_pair` calls for 0.012 s, 3,600 `parse_value` calls for
0.009 s, and 500 `parse_array` calls for 0.005 s. These cumulative values
overlap. There were 22,100 `skip_chars` calls. The operation pattern
supports testing a coarse whole-document boundary, not a per-token FFI call.

`/usr/bin/time -l` around the whole profiled command reported 0.05 s user
CPU, 0.01 s system CPU, 0.07 s wall, 23,117,824 bytes maximum resident set,
and zero swaps. These process totals include startup, imports, file reads,
and profiling; they are not per-parse performance or a baseline/candidate
comparison. The files are too small and homogeneous to represent a large
application configuration. No speed, CPU, memory, or allocation improvement
is claimed.

## Proposed boundary and feasibility

The first candidate should retain Python `load`, public exception class,
argument validation, binary decoding, and `loads` dispatch. For the exact
default `parse_float is float` path, one Rust extension call could scan a
complete normalized document, track offsets and namespace state, and build
the ordinary Python tree with CPython-owned `cpython-sys`/internal Rust APIs.
It must return exact error kind, message and source position so Python can
construct `TOMLDecodeError` with the original normalized document. Keep the
existing Python parser as oracle and as the custom `parse_float` path at
first. The custom path must be reported separately; routing it through Rust
would require ordered synchronous callback calls and the existing rejection
of `dict`/`list` results. A guarded default path must still honor text-only
lazy regex import and normal import/startup behavior.

The pinned `Cargo.lock` has `cpython-sys` and general parser helpers such as
`nom`, `regex`, and `memchr`, but no `toml`, `toml_edit`, or `toml_datetime`
parser package. General helpers do not provide TOML 1.0 or CPython's exact
error contract. There is no dependency-free ready backend to plug in.
Implementing one should wait for workload evidence that could repay the
semantic and maintenance cost, or a separately authorized dependency pin.

## Qualification plan and decision gate

Start with exact public tasks: a cold process importing `tomllib` and
loading one file; a warm process loading the four pinned files above as a
single logical metadata batch; and a larger batch of real `pyproject.toml`
files from already locked, version-matched application inputs if available.
Record the exact file list, SHA-256s, total bytes, number of tables and
values, and completed parses. Add a deterministic 4 KiB–1 MiB synthetic
size sweep only to explain scaling; keep it separate from real metadata.
Include `loads` on in-memory strings, `load` on a binary file, a float-heavy
document, and custom `parse_float` cases. Compare cold and warm paths
separately, with serial counterbalanced controls and self-comparison noise.

Before timing a candidate, run unchanged `test_tomllib` on the immediate
no-patch fork control and candidate. Differentially compare valid fixture
trees and all invalid fixture error class, attributes, and text; test
duplicate dotted keys, implicit/explicit table transitions, arrays of
tables, multiline strings, escapes, CRLF, Unicode scalar checks, datetime
and timezone values, malformed numeric tokens, recursion/key-part limits,
binary-vs-text `load`, `loads` input types, and callback values, order,
errors, and side effects. Verify that the public API reaches the Rust path
for its stated guard. Use matched upstream CPython 3.16 as the memory parity
baseline and the last accepted fork as the immediate change control.

Keep only if complete metadata workloads show a repeatable useful wall and
kernel-accounted user/system CPU gain beyond self-comparison noise, with no
material cold startup, peak/retained RSS, unique/proportional memory,
allocation, or installed-size regression, and exact behavior. Record the
candidate source patch, build recipe, input digests, raw paired observations,
and fallback frequency. Stop if real metadata spends too little time in
TOML parsing, the guarded path rarely applies, callback/error parity forces
per-token Python crossings, or a meaningful workload regresses. The current
macOS allocation and unique-memory gates are unavailable, so even a focused
timing win would remain provisional until those measurements exist.
