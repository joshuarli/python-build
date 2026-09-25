# `tomllib` public boundary and workload gate

## Decision

**Defer a parser prototype.** A single Rust call per complete document is a
credible fast path for exact `str` input with `parse_float is float`, but it
cannot replace every public `load`/`loads` call without preserving Python
object behavior and ordered callbacks. Profile a real application metadata
task through the public API before paying for an exact parser implementation.
The existing pinned project metadata is useful for correctness and a small
batch diagnostic, not evidence of application headroom.

## Evidence and semantic boundary

The pin is `b812b4a7b9efaca46b98544a8633b7d7e454166b` in
`rust-cpython/sources.lock.json`. The extracted
`Lib/tomllib/_parser.py` and both `stage/lib/python3.16/tomllib/_parser.py`
and `stage-no-rust/lib/python3.16/tomllib/_parser.py` have identical SHA-256
`1eca6101d6135d4ba30573eb2212becb4cea39cb3416f48225a1deeecdd94c4d`.
The public exports are `load`, `loads`, and `TOMLDecodeError` in
`Lib/tomllib/__init__.py`.

Keep `load`'s `fp.read()`, result `.decode()`, and binary-mode `TypeError` in
Python. They permit arbitrary file-like objects, including overridden `read`
or `decode`, and their exceptions and side effects occur before parsing.
Keep `loads`' `s.replace("\r\n", "\n")` and its exact input `TypeError` in
Python. A `str` subclass may override `replace`, so dispatch to Rust only
when `type(s) is str` and `parse_float is float`; retain the Python parser for
subclasses and every other callback. An ordinary binary file still reaches
the fast path after Python's read and decode. This guard makes the public
surface plausible without promising that all calls accelerate.

`parse_float` is called with the original token, in parse order, for decimal
floats and signed `inf`/`nan` (`_parser.py:parse_value`,
`_re.py:match_to_number`). Its return may be any object except a `dict` or
`list`, checked with `isinstance`; callback exceptions and side effects must
occur even when a later statement is invalid. A whole-document Rust parser
can preserve this only by synchronous, ordered calls into Python while it
parses, or by retaining the Python path for custom callbacks. A post-parse
conversion pass changes observable order and failure behavior. Identity
checking `parse_float is float` also preserves callable subclasses and
user-supplied float-like converters on the fallback path.

For the guarded path, the Rust parser must return ordinary Python containers
and scalar/date/time objects with the same insertion order. `_parser.py`
checks duplicate dotted keys, implicit versus explicit tables, frozen inline
tables, and arrays of tables after parsing values; therefore a duplicate-key
error can follow a `parse_float` call. It also uses `MAX_KEY_PARTS` and Python
recursion limits. Exact errors need the same message and **character** offset
in the CRLF-normalized Python string, including end-of-document positions.
`TOMLDecodeError` computes `doc`, `pos`, `lineno`, `colno`, and formatted text
from that offset. A Rust UTF-8 byte offset alone is insufficient after
non-ASCII text. Python should construct the public, subclassable exception
from the Rust message and character offset; keep its existing deprecated
constructor behavior. `test_tomllib/test_error.py` checks attributes/text,
and `test_data.py` covers valid and invalid fixture trees. `test_misc.py`
covers binary mode, callbacks, recursion, and text-only parsing without an
eager `tomllib._re` import. Those are qualification evidence, not proof that a
new parser already matches them.

## Workload boundary

The only direct pinned-source stdlib caller outside `test_tomllib` found here
is `Lib/test/test_platform.py:test_libc_ver`, which loads
`Platforms/emscripten/config.toml` only on Emscripten. The repo's
`rust-cpython/build.py:_zlib_source` and `rust-cpython/zlib-proof/build.py` read
a Cargo manifest with `tomllib.loads(manifest.read_text())`, but those run in
the **host controller**, not the staged CPython candidate. The existing
`benchmarks/harness/pyperformance.py` selection `tomli_loads` times Tomli,
so it cannot establish a `tomllib` candidate gain.

One reproducible metadata diagnostic is all ten `Cargo.toml`,
`pyproject.toml`, and platform `config.toml` files in the pinned CPython
source tree, sorted by relative path. They total 2,714 bytes, range from 122
to 798 bytes, and include the four files already profiled in
`tomllib-target.md`. Use one cold public `load` and one warm batch of all ten
as separate units; record each file hash and total completed parses at
measurement time. This corpus is a control and compatibility fixture, not a
real application workload. The prior four-file cProfile diagnostic reported
0.026 s instrumented cumulative `loads` time for 400 parses; it supplies no
uncontended speed or CPU comparison.

Before a prototype, identify a version-matched application that actually
loads meaningful project metadata under the staged interpreter, then profile
the complete cold and warm task to measure the share spent in public
`tomllib.load`/`loads`. If that share is material, measure the no-patch fork
against itself for noise, and qualify a guarded candidate against the
unchanged `test_tomllib` suite plus exact error and callback observations.
The source and test search and metadata size count here were read-only and
short; no build, test, benchmark, or resource-intensive command was run.
