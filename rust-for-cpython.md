# Rust-for-CPython stdlib coverage

## Objective

Port important public stdlib behavior to Rust on the pinned experimental
CPython 3.16 fork, as quickly as correctness permits. Coverage is the sole
goal of this phase. Performance, memory, allocation, and size optimization
are deferred to [rust-for-cpython-perf.md](rust-for-cpython-perf.md). **Do not
start that document until every checklist item here is complete.** A correct
Rust port can be kept regardless of its unmeasured performance.

The production CPython 3.14.6 build is outside this lane. Supported
experimental targets are native macOS arm64 and Linux x86-64; Linux arm64
remains in scope but its builder is not implemented yet. Windows, Intel
macOS, and every other platform are unsupported. Public APIs on supported
hosts must still preserve their behavior, including lexical Windows path
parsing where exposed.

## Coverage loop

1. Pick one unchecked module and identify its complete relevant CPython
   Python-level test modules or packages before editing. Include neighboring
   suites when the public behavior crosses modules. Run the unchanged suite
   on the pinned fork to learn existing failures.
2. Look for a maintained Rust library implementing the format or algorithm.
   Use one where its license, compatibility, maintenance, and dependency
   closure fit this lane. Consult the user before adding a dependency.
   Keep CPython's public API and object/callback semantics at the boundary.
3. Make a small module-level port in an isolated, committed worktree.
   Prefer adapting a library over writing another codec, parser, or container
   from scratch. Keep the candidate source and exact build input in Git;
   generated interpreters and compiler logs are rebuildable.
4. Build with `python3 rust-cpython/build.py build`, which now defaults to
   a non-PGO, non-LTO CPython `--with-pydebug` build and Cargo `dev`
   profile. Run `python3 rust-cpython/build.py test --suite test_NAME`
   for every identified full suite. Do not write or run Rust tests, run
   pyperformance, or run benchmarks during this phase.
5. Inspect failures at the Python API, fix the Rust boundary, and rerun the
   full affected suites. Mark a module complete only when the public route
   reaches Rust and all relevant Python suites pass. Commit the source
   and one concise suite result with the module checklist change. Then
   select the next module.

A failed candidate may stay on its own branch while being repaired. Do not
mark partial implementations complete or create per-attempt reports, scout
commits, or resource ledgers. A short finding is enough when a route is
abandoned. The coordinator owns lane assignment, path isolation, and
integration; the repo-local skill specifies the six-agent maximum.

## Coverage checklist


Work through the modules below, choosing library-backed modules with a
tractable complete CPython test suite first. A checked item requires public
calls for the named behavior to reach maintained Rust code on a supported
host, and every relevant unchanged CPython test module or package to pass
in full on the debug candidate. Normal platform skips are acceptable;
failures, errors, and skips caused by an unimplemented feature are not.
Record the exact Rust-owned behavior, platform, candidate commit, suite
command, pass and skip counts, and any expected platform skips in a short
checked-in note. A private extension, a narrow proof, or passing a subset
of a module's tests does not complete an item.

Earlier scanner and codec experiments were partial and do not qualify any
module. The strict count starts at **0 complete modules**. Do not carry
their performance ranking into this coverage phase.

### Priority 0: common application paths

- [ ] `urllib.parse` — quote, unquote, and query parsing on public calls.
- [ ] `json` — encode and decode complete documents.
- [ ] `pickle` — dump and load common object graphs.
- [ ] `csv` — parse and write records through the public reader and writer.
- [ ] `tomllib` — parse complete TOML documents.
- [ ] `email` — parse and serialize messages and headers.
- [ ] `xml.etree.ElementTree` — parse and serialize XML trees.
- [ ] `re` — compile and search common patterns through `re`.
- [ ] `base64` — public encode and decode functions.
- [ ] `binascii` — binary/text conversion and checksums used by public callers.
- [ ] `zlib` — compression and decompression on public streams and one-shot calls.
- [ ] `gzip` — complete file and stream compression/decompression.
- [ ] `zipfile` — read and write complete ZIP archives.
- [ ] `tarfile` — read and write complete TAR archives.
- [ ] `pathlib` — public path parsing and common filesystem operations.
- [ ] `os.path` — path normalization, joining, and splitting via the platform module.
- [ ] `shutil` — file copying, tree operations, and archive handling.
- [ ] `importlib.metadata` — distribution discovery and metadata access.
- [ ] `hashlib` — public digest updates and finalization.
- [ ] `hmac` — public keyed digest operations.
- [ ] `uuid` — parse, format, and generate UUIDs.
- [ ] `datetime` — parse, format, and arithmetic on public date/time objects.
- [ ] `decimal` — arithmetic on public `Decimal` values.
- [ ] `sqlite3` — statement execution and row conversion through public cursors.
- [ ] `io` — buffered and text stream reads and writes.
- [ ] `logging` — record creation, formatting, and handler dispatch.
- [ ] `asyncio` — task scheduling and event-loop operations on public APIs.
- [ ] `http.client` — parse and send HTTP messages through public connections.
- [ ] `ipaddress` — parse addresses and calculate network ranges.
- [ ] `socket` — public address conversion and I/O operations.
- [ ] `ssl` — public TLS context and stream operations.
- [ ] `subprocess` — command launch and communication.
- [ ] `multiprocessing` — interprocess queues and pools.
- [ ] `concurrent.futures` — executor scheduling and result handling.

### Priority 1: broad supporting surface

- [ ] `configparser` — read and write INI-style configuration.
- [ ] `plistlib` — parse and serialize property lists.
- [ ] `struct` — pack and unpack binary records.
- [ ] `marshal` — serialize and load supported Python code/data records.
- [ ] `html.parser` — tokenize complete HTML documents.
- [ ] `difflib` — public sequence matching and diff generation.
- [ ] `codecs` — encode/decode dispatch and incremental conversion.
- [ ] `unicodedata` — Unicode property lookup and normalization.
- [ ] `bz2` — public compression and decompression.
- [ ] `lzma` — public compression and decompression.
- [ ] `compression.zstd` — public Zstandard streams and one-shot calls.
- [ ] `zipimport` — module discovery and loading from ZIP archives.
- [ ] `glob` — public pathname expansion.
- [ ] `fnmatch` — public filename pattern matching.
- [ ] `importlib.resources` — resource lookup and reading.
- [ ] `tempfile` — temporary file and directory creation.
- [ ] `fractions` — `Fraction` parsing and arithmetic.
- [ ] `statistics` — common summary operations.
- [ ] `random` — public random number generation and sampling.
- [ ] `collections` — common containers and counting operations.
- [ ] `heapq` — heap operations.
- [ ] `bisect` — ordered insertion and search.
- [ ] `itertools` — core iterator transformations.
- [ ] `functools` — caching and ordering helpers.
- [ ] `contextlib` — public context-manager composition.
- [ ] `dataclasses` — class generation and field processing.
- [ ] `inspect` — signatures and object inspection.
- [ ] `ast` — parse-tree walking and transformation helpers.
- [ ] `argparse` — argument parsing and help generation.
- [ ] `tokenize` — token generation from Python source.
- [ ] `_strptime` — directive parsing used by public date/time calls.
- [ ] `shlex` — POSIX and non-POSIX token splitting.
- [ ] `textwrap` — paragraph wrapping and shortening.
- [ ] `threading` — public thread coordination and synchronization.
- [ ] `typing` — runtime annotation and generic operations.
- [ ] `warnings` — warning filtering and display.
- [ ] `urllib.request` — request opening and response handling.
