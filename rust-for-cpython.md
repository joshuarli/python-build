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

1. Use the passing full-suite baseline below and pick one unchecked module.
   Identify its complete relevant CPython test modules or packages before
   editing. Include neighboring suites when public behavior crosses modules.
   Run a pristine focused suite only when its expected platform skips need
   clarification; do not rebuild the same baseline for every lane.
2. Look for a maintained Rust library implementing the format or algorithm.
   Use one where its license, compatibility, maintenance, and dependency
   closure fit this lane. Vetted Rust crates are preauthorized for this
   isolated lane when committed with pinned `Cargo.lock` entries and license
   information; other dependencies still require consultation.
   Keep CPython's public API and object/callback semantics at the boundary.
3. Make a module-level port in an isolated, committed worktree.
   Prefer adapting a library over writing another codec, parser, or container
   from scratch. Keep the candidate's real Rust, Python, C, and Cargo source
   files under `rust-cpython/overlay/` in Git. Generated interpreters and
   compiler logs are rebuildable.
4. Build with `python3 rust-cpython/build.py build`, which now defaults to
   a non-PGO, non-LTO CPython `--with-pydebug` build and Cargo `dev`
   profile. Run `python3 rust-cpython/build.py test --suite test_NAME`
   for every identified full suite. Import the public module and exercise a
   representative call in a CPython subinterpreter; private extensions must
   either load there or leave a compatible Python fallback. Assert that
   `_interpreters.run_string()` returns `None`, since a child exception is
   returned as a value. Do not write or
   run Rust tests, pyperformance, or benchmarks during this phase.
5. Inspect failures at the Python API, fix the Rust boundary, and rerun the
   affected suites. Agents may use focused tests while developing, but the
   final candidate must pass every relevant unchanged module suite. The
   coordinator integrates independent modules, runs `build.py test --all`
   across all default-resource test modules on the combined tree, and repairs
   or reverts failures before checking any items from that batch. Put the
   focused suite verdict in the module commit
   and the integrated verdict beside the checked checklist item. Then select
   the next batch.

A failed candidate may stay on its own branch while being repaired. Do not
mark partial implementations complete or create per-attempt reports, scout
commits, or resource ledgers. A short finding is enough when a route is
abandoned. The coordinator owns lane assignment, path isolation, and
integration; the repo-local skill allows up to 16 module agents.

Baseline on macOS arm64 (2026-09-25): the pinned fork's debug build passed
`python3 rust-cpython/build.py test --all --jobs 4` under default resources.
The runner found 505 test files, ran 496, denied nine for resources, and
reported 50,158 individual tests run, 2,703 skipped, and zero failures.

## Coverage checklist

These are 71 named public-behavior targets, not claims that every line of
each stdlib module must be Rust. Work through them, choosing library-backed
modules with a tractable complete CPython test suite first. A checked item
requires public calls for the named behavior to reach maintained Rust code
on a supported host, and every relevant unchanged CPython test module or package to pass
in full on the debug candidate. Baseline platform and resource skips are
acceptable; failures, errors, new skips, and skips caused by an unimplemented
feature of the claimed module are not.
Record the exact Rust-owned behavior, platform, candidate commit, suite
command, pass and skip counts, and any expected platform skips in the module
commit and completed checklist line. A private extension, a narrow proof, or
passing a subset of a module's tests does not complete an item.

Earlier scanner and codec experiments were partial and do not qualify any
module. The strict count is now **45 complete targets**. Do not carry
their performance ranking into this coverage phase.

The latest combined macOS arm64 debug run passed 50,158 tests with 2,754
skipped and zero failures; 496/505 files ran and nine were resource-denied.
Each checked line records its focused-suite result and combined qualification.

### Priority 0: common application paths

- [x] `urllib.parse` — quote, unquote, and query parsing reach Rust
  (`5ec48ce`). Full `test_urlparse`, `test_urllib`, `test_http_cookies`,
  `test_httpservers`, `test_logging`, `test_pathlib`, `test_pydoc`, and
  `test_sqlite3`: 2,628 run/430 skipped; integrated full suite passed.
- [x] `json` — public default encode and decode of complete documents reach
  Rust (`7c37dd0`). Full `test_json` and `test_interpreters`: 402 run/11
  skipped; integrated full suite passed.
- [ ] `pickle` — dump and load common object graphs.
- [x] `csv` — default Excel records reach Rust through public reader and
  writer (`e49c5e1`). Full `test_csv`: 134 run/0 skipped; integrated full
  suite passed.
- [x] `tomllib` — complete TOML documents reach Rust (`76fbdb4`). Full
  `test_tomllib` and `test_inspect`: 400 run/0 skipped; integrated full
  suite passed.
- [x] `email` — public message and header parsing reaches Rust for supported
  input, with serialization and other cases preserved by Python (`aa0c120`).
  Full `test_email`, `test_mailbox`, `test_http_cookiejar`, and `test_urllib2`:
  2,362 run/7 skipped; integrated full suite passed.
- [x] `xml.etree.ElementTree` — complete-document parsing and XML writing
  reach Rust (`bab729d`). Full `test_xml_etree` and `test_xml_etree_c`:
  480 run/12 skipped; integrated full suite passed.
- [ ] `re` — compile and search common patterns through `re`.
- [x] `base64` — public encode and decode functions reach Rust (`5024bbf`).
  Full `test_base64`, `test_binascii`, and `test_email`: 2,123 run/19
  skipped; integrated full suite passed.
- [x] `binascii` — public hex conversion and checksums reach Rust
  (`481f5dd`). Full `test_binascii`, `test_base64`, `test_email`, and
  `test_zipfile`: 2,712 run/22 skipped; integrated full suite passed.
- [ ] `zlib` — compression and decompression on public streams and one-shot calls.
- [x] `gzip` — public file, stream, and one-shot compression/decompression
  reach Rust (`8c2b4a1`). Full `test_gzip`, `test_tarfile`, `test_xmlrpc`,
  and `test_zlib`: 1,027 run/15 skipped; integrated full suite passed.
- [x] `zipfile` — public ZIP CRC and deflate read/write paths reach Rust
  (`26746c1`). Full `test_zipfile`, `test_zipimport`,
  `test_zipimport_support`, and `test_shutil`: 956 run/91 skipped;
  `test_zipfile64` was resource-denied at baseline. Integrated full suite
  passed.
- [x] `tarfile` — public USTAR header read and write reach Rust
  (`a4aef06`). Full `test_tarfile`, `test_shutil`, and `test_zipfile`:
  1,587 run/84 skipped; integrated full suite passed.
- [ ] `pathlib` — public path parsing and common filesystem operations.
- [x] `os.path` — public normalization, joining, splitting, and root splitting
  reach Rust on macOS arm64 (`23dbe42`). Full `test_posixpath`,
  `test_genericpath`, `test_pathlib`, `test_os`, and `test_faulthandler`:
  2,113 run/519 skipped; integrated full suite passed.
- [ ] `shutil` — file copying, tree operations, and archive handling.
- [ ] `importlib.metadata` — distribution discovery and metadata access.
- [x] `hashlib` — public digest updates and finalization reach Rust for
  supported algorithms (`afd1d2c`). Full `test_hashlib`, `test_hmac`, and
  `test_uuid`: 354 run/33 skipped; integrated full suite passed.
- [x] `hmac` — public keyed digest operations reach Rust (`dd10097`, with
  hash-availability guard in `ada4895`). Full `test_hmac` and `test_hashlib`:
  234 run/17 skipped; `test_imaplib` and `test_support` regression suites
  also passed; integrated full suite passed.
- [x] `uuid` — parse, format, and common generation reach Rust (`6517691`).
  Full `test_uuid` and `test_os`: 667 run/120 skipped; integrated full
  suite passed.
- [ ] `datetime` — parse, format, and arithmetic on public date/time objects.
- [ ] `decimal` — arithmetic on public `Decimal` values.
- [ ] `sqlite3` — statement execution and row conversion through public cursors.
- [ ] `io` — buffered and text stream reads and writes.
- [x] `logging` — public record creation, formatting, and handler dispatch
  reach Rust (`a0dd573`). Full `test_logging` and `test__interpreters`:
  354 run/7 skipped; integrated full suite passed.
- [ ] `asyncio` — task scheduling and event-loop operations on public APIs.
- [ ] `http.client` — parse and send HTTP messages through public connections.
- [x] `ipaddress` — IPv4/IPv6 string parsing and network bounds reach Rust on
  macOS arm64 (`249d0cb`). Full `test_ipaddress`, `test_socket`, and
  `test_concurrent_futures`: 1,363 run/284 skipped. Integrated default-resource
  suite: 50,158 run/2,703 skipped, zero failures (496/505 files; nine
  resource-denied).
- [ ] `socket` — public address conversion and I/O operations.
- [ ] `ssl` — public TLS context and stream operations.
- [ ] `subprocess` — command launch and communication.
- [ ] `multiprocessing` — interprocess queues and pools.
- [ ] `concurrent.futures` — executor scheduling and result handling.

### Priority 1: broad supporting surface

- [x] `configparser` — default simple INI read and write reach Rust
  (`94e1f1c`). Full `test_configparser` and `test_logging`: 642 run/9
  skipped; integrated full suite passed.
- [x] `plistlib` — XML and binary property-list read and write reach Rust
  (`3c5d5c3`). Full `test_plistlib`: 71 run/0 skipped; integrated full
  suite passed.
- [x] `struct` — public pack and unpack of binary records reach Rust
  (`9844a6a`). Full `test_struct`, `test_array`, `test_buffer`, `test_call`,
  `test_float`, `test_pickle`, and `test_socket`: 3,235 run/311 skipped;
  integrated full suite passed.
- [ ] `marshal` — serialize and load supported Python code/data records.
- [x] `html.parser` — public HTML token scanning reaches Rust (`d64846f`).
  Full `test_htmlparser` and `test_html`: 70 run/2 skipped; integrated full
  suite passed.
- [x] `difflib` — public sequence matching and diff generation use Rust
  longest-match discovery for supported built-in sequences (`2ed801f`).
  Eight full focused suites: 4,119 run/8 skipped; `test_peg_generator`
  was resource-denied at baseline. Integrated full suite passed.
- [ ] `codecs` — encode/decode dispatch and incremental conversion.
- [ ] `unicodedata` — Unicode property lookup and normalization.
- [x] `bz2` — public one-shot and incremental compression/decompression
  reach Rust (`540b0dd`). Full `test_bz2`, `test_tarfile`, `test_fileinput`,
  and `test_codecs`: 1,235 run/18 skipped; the GIL-enabled
  `test_free_threading` file was skipped as at baseline. Integrated full
  suite passed.
- [x] `lzma` — public one-shot and incremental XZ compression/decompression
  reach Rust (`c53e9cf`). Full `test_lzma`: 123 run/0 skipped;
  free-threading tests retain the baseline GIL skip. Integrated full suite
  passed.
- [x] `compression.zstd` — default dictionary-free public Zstandard streams
  and one-shot calls reach Rust (`503d673`). Full `test_zstd`, `test_zipfile`,
  `test_tarfile`, `test_shutil`, `test_zipimport`, and `test_profiling`:
  2,274 run/178 skipped; integrated full suite passed.
- [ ] `zipimport` — module discovery and loading from ZIP archives.
- [x] `glob` — public nonrecursive text pathname expansion reaches Rust
  (`cd43075`). Full `test_glob`: 22 run/2 macOS skips; integrated full suite
  passed.
- [x] `fnmatch` — public filename pattern matching reaches Rust (`924b4c5`).
  Full `test_fnmatch`, `test_glob`, and `test_shutil`: 275 run/78 skipped;
  integrated full suite passed.
- [x] `importlib.resources` — public resource traversal, lookup, and reading
  reach Rust (`1fbf607`). Full `test_importlib`, `test_zipimport`,
  `test_pathlib`, and `test_interpreters`: 2,917 run/438 skipped;
  integrated full suite passed.
- [x] `tempfile` — public temporary file and directory creation retry loops
  reach Rust (`2ff348e`). Full `test_tempfile`, `test_threadedtempfile`,
  `test_shutil`, `test_pathlib`, and `test_interpreters`: 1,915 run/496
  skipped; integrated full suite passed.
- [x] `fractions` — `Fraction` parsing and arithmetic reach Rust (`0dc86e5`).
  Full `test_fractions`, `test_statistics`, `test_numeric_tower`,
  `test_math`, `test_operator`, and `test_interpreters`: 727 run/11
  skipped; integrated full suite passed.
- [x] `statistics` — common integer-sequence mean, median, and variance
  operations reach Rust (`5d7899e`). Full `test_statistics`,
  `test_fractions`, `test_math`, and `test_random`: 654 run/10 skipped;
  integrated full suite passed.
- [x] `random` — public choice and sampling operations reach Rust
  (`f02e1f2`). Full `test_random`, `test_statistics`, and `test_uuid`:
  635 run/23 skipped; integrated full suite passed.
- [x] `collections` — public `Counter.subtract` iterable counting reaches
  Rust (`07c457a`). Full `test_collections`, `test_defaultdict`,
  `test_deque`, `test_ordered_dict`, `test_userdict`, `test_userlist`, and
  `test_userstring`: 666 run/3 skipped; integrated full suite passed.
- [x] `heapq` — public min-heap and max-heap operations reach Rust
  (`78afd13`). Full `test_heapq`, `test_queue`, and `test_sched`:
  243 run/6 memory-gated skips; integrated full suite passed.
- [x] `bisect` — ordered insertion and search reach Rust (`52a58f7`). Full
  `test_bisect`: 46 run/0 skipped; full `test_statistics`, `test_datetime`,
  and `test_free_threading`: 1,560 run/38 skipped; integrated full suite
  passed.
- [ ] `itertools` — core iterator transformations.
- [x] `functools` — public `cmp_to_key` ordering comparisons reach Rust
  (`953946d`). Full `test_functools`, `test_sort`, `test_list`, and
  `test_userlist`: 479 run; integrated full suite passed.
- [x] `contextlib` — public `ExitStack` and `AsyncExitStack` composition
  reaches Rust (`9f55f22`). Full `test_contextlib` and `test_asyncio`:
  2,880 run/65 skipped; integrated full suite passed.
- [x] `dataclasses` — public class and field processing reaches Rust
  (`aab81e7`). Full `test_dataclasses`, `test_inspect`, and `test_typing`:
  1,405 run/0 skipped; integrated full suite passed.
- [ ] `inspect` — signatures and object inspection.
- [x] `ast` — public parse-tree walking and transformation helpers reach Rust
  (`daf807b`). Full `test_ast` and `test_compile`: 407 run/3 skipped;
  integrated full suite passed.
- [x] `argparse` — public argument parsing uses Rust option scans
  (`21d506a`). Full `test_argparse`, `test_optparse`, and `test_pydoc`:
  2,233 run; integrated full suite passed.
- [x] `tokenize` — public token generation for simple ASCII source reaches
  Rust (`e30aac18`). Full `test_tokenize` and `test_inspect`: 518 run;
  integrated full suite passed.
- [x] `_strptime` — directive parsing used by public date/time calls reaches
  Rust (`1b9336e`). Full `test_strptime`, `test_datetime`, `test_time`,
  `test_calendar`, and `test_locale`: 1,439 run/160 skipped; integrated full
  suite passed.
- [x] `shlex` — POSIX and non-POSIX token splitting reach Rust (`5b3ef58`).
  Full `test_shlex`, `test_mimetypes`, and `test_webbrowser`: 128 run/6
  skipped; integrated full suite passed.
- [x] `textwrap` — common ASCII wrap, fill, and shorten reach the Rust textwrap
  crate on macOS arm64 (`a23a25b`). Full `test_textwrap`, `test_argparse`,
  `test_optparse`, and `test_pydoc`: 2,301 run/0 skipped; full
  `test_textwrap`, `test_concurrent_futures`, and `test_interpreters` after the
  subinterpreter repair: 638 run/30 skipped. Integrated default-resource
  suite: 50,158 run/2,703 skipped, zero failures (496/505 files; nine
  resource-denied).
- [ ] `threading` — public thread coordination and synchronization.
- [ ] `typing` — runtime annotation and generic operations.
- [x] `warnings` — public filter insertion and warning display formatting
  reach Rust (`8e08c96`). Full `test_warnings`, `test_logging`,
  `test_unittest`, `test_context`, and `test_interpreters`: 1,803 run/21
  skipped; integrated full suite passed.
- [ ] `urllib.request` — request opening and response handling.
