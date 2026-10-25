# Rust-for-CPython campaign

Status: coverage complete (71/71 targets qualified, macOS arm64 + Linux x86-64);
upstream-parity stage executed (U0–U6 done; D2 accepted 2026-10-25 with
two loud pre-existing deviations, rebase + backport queued as separate
items); Phase 3 is active on the macOS memory-first climb.

Goal: keep every named public stdlib behavior on maintained Rust on the
pinned experimental CPython 3.16 fork, prove it against CPython suites,
reconcile the pinned fork with upstream 3.16.0a1+ semantics, and only then
climb memory and CPU performance.

Deliverables:
- D1: 71/71 stdlib coverage targets qualified on macOS arm64 and Linux
  x86-64 (accepted; see Phase 1 and the parity register).
- D2: upstream-parity stage against 3.16.0a1-or-newer: exact-byte marshal
  differential, ICU/Unicode 18 evaluation, compression-backend evaluation,
  UUID re-baseline, and a compat sweep (re, datetime, pickle, csv,
  io/zipfile/shutil, ssl) — each with pristine-baseline comparison and full
  suite gates (done; accepted with two loud deviations per OD5; U7/U8 queued).
- D3: memory-first then CPU performance for all 71 routes (in progress;
  Phase 3 holds the full normative contract, unchanged in force).
- D4: this single campaign doc (done by this preflight; supersedes the
  former two-doc layout).

Last accepted checkpoint: `8d61d20` (integrated parity on main:
U1 C-writer two-pass + U5 datetime/zipfile reconciliations; U6
50,158 run / 4F+6E+14E, all pre-existing and loud, zero new).

Provisional work: none on the integration branch. The `lane-integrate`
worktree's stage build verified the D2 prerequisite shim; its overlay file
is now committed on main.

Current steering decision (2026-10-25): coverage stays accepted and closed
to rework; D2 accepted with the two loud pre-existing deviations below.
U8 done and merged. U7 parked as a multi-lane wave (blockers B1–B5
recorded on the item; retry needs P1–P3 + a Linux host). U2 done and
merged (proof above; integrated --all attributed clean). Current work is
Phase 3 memory-first on macOS. Linux re-qualification of U8+U2 and the U7
rebase remain downstream prerequisites for closeout; Linux work requires a
native host.

Next substantive milestone: clear every macOS module memory goal and eligible
workload RSS regression, then begin CPU performance work. U7 remains parked
until its recorded P1–P3 prerequisites and a native Linux host are available.

## Charter

- Decide, log the call, and keep going. Within the execution grant, decide
  and proceed without waiting. Park an item that needs authority outside
  the grant with evidence, the missing prerequisite, and a retry condition.
  Run until every deliverable is met or every remaining item is parked
  behind a hard stop.
- Hard stops are few: an irreversible or outside-the-repo action, a boundary
  below that forbids it, or a loop that cannot check anything. Pushing is
  always forbidden. Lane commits require the owner's instruction; without
  it use disjoint patch handoffs and do not claim a committed handoff.
- Fix on the way what is egregious, in its own commit, to thresholds stated
  in numbers: a loop command over 10 minutes gets one bounded repair tied
  to the next substantive delivery; a regression of more than 2x against
  the baseline is parked as a blocker, not worked around; a test red on the
  baseline that blocks an item is recorded in Baseline, not fixed
  opportunistically. Record anything else seen and leave it.
- Parity before optimization. No optimization or size work until D1 and D2
  acceptance pass. Memory and CPU numbers are logged during D2 but never
  gate it.
- Keep bookkeeping minimal: reuse existing results and logs. Record the
  revision and relevant inputs needed to qualify evidence. No provenance
  ledger, no second progress register, no per-attempt report files.
- Size lanes and validation waves by ownership, measured resources, and
  acceptance capacity. For this lane the coordinator skill below supersedes
  `orchestrate`. Memory budget: measure the lane host before expanding
  past 4 concurrent builders; reduce width when review or validation
  queues grow.
- The parent reviews direction, not just worker completion. After a method
  change, update current rulings here and notify affected lanes. Do not
  silently replace owner requirements or waive a failed acceptance check.
- Worktrees and all working state live under `.work/` in the repo, never
  `/tmp` or `$TMPDIR`. Lane worktrees live at `.work/wt/<lane>`.
- Follow the coordinator skill's worktree lifecycle (branch + worktree per
  lane, private build/stage/logs per worktree, shared `.cache/objects`
  linked, remove completed worktrees after integration). During winddown,
  retain a worktree only when it is clean, named in the handoff, and
  explicitly allowed by the closeout guard.
- Every commit is a Conventional Commit with the area as scope; the item ID
  belongs in the body, never the subject. Code comments never cite this doc.
- Parent steering checkpoint applies after each validation wave, on resume
  or context recovery, and before dispatch after a recurring rejection or
  bottleneck; after five attempted items with no completed wave. Record the
  ruling and next delivery here, not in a second artifact.

## Decisions

Owner-decided (2026-10-25, from the owner's direction; overrule by saying so):
- OD1: one campaign doc. `rust-for-cpython-perf.md` is merged here and
  removed (recoverable from git history). The normative perf contract
  survives verbatim in force as Phase 3.
- OD2: coverage and parity first; all performance goals deferred until D1
  and D2 are accepted. CPU, timing, and quiet-host results cannot qualify,
  reject, or delay D2 changes.
- OD3: add the D2 upstream-parity stage scoped to marshal, unicodedata,
  compression, uuid, and the compat sweep, in the brief's sequence
  (pristine baseline, then semantics, then full suites, then backend
  evaluations). No redesign of the 71-route architecture around the
  proposed upstream Rust API.
- OD4: coverage items stay accepted as qualified; upstream changes do not
  reopen them except through a D2 item with a reproducer.
- OD5 (2026-10-25, after `lane/integrated-parity` merged to main at
  `8d61d20`): D2 accepted with two loud pre-existing deviations
  (`test_ssl` 4F+6E RTLS policy gaps, `test_support` 14E hashlib-shim
  gaps, all on clean main, none integration-caused). U7 source rebase and
  U8 `re` locale-ignorecase backport run as separate sequenced items.
  Phase 3 launches memory-first, macOS-only per the perf skill.

Prescribed (settled from code and evidence; reversal needs counter-evidence):
- P1: marshal goes first. `rust-cpython/overlay/Modules/_marshal_rs/src/lib.rs:349`
  reads `ob_refcnt_full == 1` to set `FLAG_REF`, while upstream 3.16 tags by
  multi-occurrence. Both sides can be valid marshal yet differ byte-for-byte;
  the campaign's own checklist already admits the divergence (Phase 1,
  `marshal` line). Reversal: a byte-differential proving identity.
- P2: keep every Rust route until paired memory evidence says otherwise.
  The 3.16 native C uuid fast paths and zlib-rs/bzip2-rs backends are
  evaluation candidates, not replacements, until equivalence plus
  memory-neutral-or-better proof. Reversal: accepted U3/U4 verdicts.
- P3: ICU 2.2.0 stays until U2 qualifies 2.4/Unicode 18 on semantics and
  load footprint (`rust-cpython/overlay/Modules/_unicodedata_rs/Cargo.toml:9-10`
  pins `=2.2.0`). A data upgrade that moves `load_footprint` OVER is
  rejected pending a smaller mechanism. Reversal: U2 acceptance.
- P4: the lane coordinator skill supersedes `orchestrate` for D1/D2 lane
  mechanics; `orchestrate`'s campaign reference still governs waves,
  steering, and closeout. Reversal: owner says otherwise.

Delegated (executor decides inside the bound, logs the call):
- G1: lane width 1–16 and wave grouping, bounded by measured host memory,
  review capacity, and the provisional-work cap (at most 4 unintegrated
  branches). Default to fewer, wider lanes on shared files.
- G2: pristine-baseline scope for U0 (newer alpha vs current `b812b4a`),
  bounded by fetch cost; smallest newer upstream that builds sealed wins.
- G3: per-module port tactics inside D2 (adapt a library vs edit the
  boundary), bounded by the license/closure rule in the coverage loop.

## Baseline

Source pin (`rust-cpython/sources.lock.json:2-9`): Rust-for-CPython/cpython
`3.x-rust-in-cpython` at `b812b4a7`, version 3.16.0a0. Upstream 3.16.0a1
released 2026-10-13; next alpha 2026-11-10. The fork branch still points at
`b812b4a`; accumulating changes live in main python/cpython.

Accepted coverage numbers (macOS arm64, debug, default resources):
`test --all --jobs 4`, 505 files found, 496 run, 9 resource-denied,
50,158 run / 2,703 skipped / zero failures. Linux x86-64: 50,782 run /
2,828 skipped, same denials; only failure is the host-baseline VSOCK test
below.

Known baseline failures (never mistake for a regression):
- `test_socket.ThreadedVSOCKSocketStreamTest.testStream`: host kernel lacks
  `CONFIG_VSOCKETS_LOOPBACK` (`ENODEV`). Clears with `sudo modprobe
  vsock_loopback`. Applies to any interpreter on that host.
- Nine resource-denied files per platform (`test_zipfile64`,
  `test_socketserver`, `test_peg_generator`, etc.; see the register).

Loop timings (measured 2026-10-25/26, macOS arm64):
- narrow controller check (`python3 -m unittest tests.test_nix_build_image`):
  ~0.1s.
- `py_compile` of lane entry points: ~0.05s.
- full controller `discover -s tests`: exceeds 120s (earlier full run
  ~290s); run at milestones only, in the background.
- coverage `test --all --jobs 4`: 9m07s for 50,158 tests (measured
  2026-10-26 on the U2 integration tree; earlier "hours-scale" estimate
  retired). Runs at integration and close only — it is the manual gate,
  never part of the item loop. Focused `test --suite <name>` per item
  (~20-90s) is the item loop; a C-touching rebuild costs ~10-20 min, so
  chain build + all suites + footprint into one background round.
- Work-tree test-file swaps do not survive a rebuild (`build` re-extracts
  source): swap after the last build, verify by md5, restore after, and
  record the md5s. `-m test <out-of-tree path>` is rejected (run=0), so
  the swap is the only harness-compatible route; `Lib/test/` in the repo
  tree is never touched.

Reference numbers for D2: host python3 marshal probe — an object appearing
twice serializes with a back-reference (27 bytes) vs twice unshared
(42 bytes). Occurrence-based tagging is the behavior to match byte-for-byte.

## Sequence

Ordering: P0 ground → parity/completeness → hardening → optimization →
close. An item names its ID, size, prerequisites, owned files, and proof.
Prerequisites crossing workstreams are written on the item. A failing item
is time-boxed to 3 attempts, then parked with evidence, the named
prerequisite, and a retry condition.

### P0 — ground (no new behavior)

- GROUND-1: U0 recorded 2026-10-24: pristine v3.16.0a1
  (`7b243d1d…e68c4e6`, 44,088,359 bytes), macOS arm64 debug —
  551/560 files, 50,969 run / 2,892 skipped / zero failures, 9
  resource-denied (`test_curses`, `test_peg_generator`, `test_smtpnet`,
  `test_socketserver`, `test_urllib2net`, `test_urllibnet`,
  `test_winsound`, `test_xpickle`, `test_zipfile64`). Record:
  `.work/tmp/u0-pristine/baseline.json`; interpreter:
  `.work/tmp/u0-pristine/install/bin/python3.16d` (done).
- GROUND-2: loop repair only if the loop is the bottleneck (over
  10 minutes for a focused item loop). No open-ended infrastructure.

### Phase 1 — coverage (accepted; do not rework)

Parity register: 71 targets, each qualified by the full unchanged CPython
suites named on its line, on a debug candidate, with baseline skips only.
Public calls for the named behavior reach maintained Rust on macOS arm64;
Linux x86-64 qualification follows in Reference. Failed candidates were
repaired or reverted before batch acceptance; the combined-tree integrated
suite is the acceptance per batch.

Coverage loop (binds D2 ports as well): baseline → relevant-suite list →
maintained library with fitting license/closure (vetted crates
preauthorized when pinned in `Cargo.lock` with license record; other
dependencies need consultation) → isolated committed worktree with real
source under `rust-cpython/overlay/` (no patch manifests, no ignored dirs
as sole copy; new crates via `overlay/Modules/Setup.local`) → debug build
(`python3 rust-cpython/build.py build`) → every relevant full suite
(`test --suite ...` per line; subinterpreter probe: public call works,
`_interpreters.run_string()` returns `None`) → fix at the Rust boundary →
coordinator integrates, runs `test --all`, repairs or reverts.

Priority 0: common application paths

- [x] `urllib.parse` — quote, unquote, and query parsing reach Rust
  (`5ec48ce`). Full `test_urlparse`, `test_urllib`, `test_http_cookies`,
  `test_httpservers`, `test_logging`, `test_pathlib`, `test_pydoc`, and
  `test_sqlite3`: 2,628 run/430 skipped; integrated full suite passed.
- [x] `json` — public default encode and decode of complete documents reach
  Rust (`7c37dd0`). Full `test_json` and `test_interpreters`: 402 run/11
  skipped; integrated full suite passed.
- [x] `pickle` — public `dumps`/`loads` and `BytesIO` `dump`/`load` of
  supported graphs reach Rust (`771cf8f`, with source-inspection cleanup in
  `ced130b`). Full `test_pickle`, `test_picklebuffer`, `test_pickletools`,
  `test_shelve`, `test_email`, and `test_ctypes`: 4,079 run/121 skipped;
  `test_pyclbr` also passed after the cleanup. Integrated full suite passed.
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
- [x] `re` — public compilation and search of supported ASCII patterns reach
  Rust (`68ff4d1`). Full `test_re`: 169 run/3 skipped; integrated full suite
  passed.
- [x] `base64` — public encode and decode functions reach Rust (`5024bbf`).
  Full `test_base64`, `test_binascii`, and `test_email`: 2,123 run/19
  skipped; integrated full suite passed.
- [x] `binascii` — public hex conversion and checksums reach Rust
  (`481f5dd`). Full `test_binascii`, `test_base64`, `test_email`, and
  `test_zipfile`: 2,712 run/22 skipped; integrated full suite passed.
- [x] `zlib` — public one-shot and streaming compression and decompression
  reach Rust on macOS arm64 (`be46e24`). Full `test_zlib`, `test_codecs`,
  `test_gzip`, `test_tarfile`, `test_zipfile`, `test_zipimport`,
  `test_zipimport_support`, `test_zipapp`, `test_shutil`, `test_logging`,
  `test_sqlite3`, and `test_ensurepip`: 3,060 run/121 skipped;
  `test_zipfile64` was resource-denied at baseline. Integrated full suite
  passed.
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
- [x] `pathlib` — public path parsing and `exists`, `is_dir`, and `is_file`
  reach Rust (`d74abd7`). Full `test_pathlib`, `test_shutil`, and `test_glob`:
  1,644 run/485 skipped; integrated full suite passed.
- [x] `os.path` — public normalization, joining, splitting, and root splitting
  reach Rust on macOS arm64 (`23dbe42`). Full `test_posixpath`,
  `test_genericpath`, `test_pathlib`, `test_os`, and `test_faulthandler`:
  2,113 run/519 skipped; integrated full suite passed.
- [x] `shutil` — public `copyfileobj` and eligible default `copytree` reach
  Rust; ZIP archive handling uses the qualified Rust-backed `zipfile` route
  (`9062434`). Full `test_shutil`, `test_zipfile`, and `test_tarfile`:
  1,587 run/84 skipped; integrated full suite passed.
- [x] `importlib.metadata` — public metadata parsing and distribution
  discovery reach Rust (`4af83b5`). Full `test_importlib` and `test_zoneinfo`:
  1,486 run/39 skipped; integrated full suite passed.
- [x] `hashlib` — public digest updates and finalization reach Rust for
  supported algorithms (`afd1d2c`). Full `test_hashlib`, `test_hmac`, and
  `test_uuid`: 354 run/33 skipped; integrated full suite passed.
- [x] `hmac` — public keyed digest operations reach Rust (`dd10097`, with
  hash-availability guard in `ada4895`). Full `test_hmac` and `test_hashlib`:
  234 run/17 skipped; `test_imaplib` and `test_support` regression suites
  also passed; integrated full suite passed.
- [x] `uuid` — parse, format, and common generation reach Rust (`6517691`).
  Full `test_uuid` and `test_os`: 667 run/120 skipped; integrated full suite
  passed.
- [x] `datetime` — public ISO parsing and formatting plus date and datetime
  timedelta arithmetic reach Rust (`da6281d`). Full `test_datetime`,
  `test_strptime`, `test_time`, `test_calendar`, `test_locale`,
  `test_zoneinfo`, and `test_pickle`: 2,776 run/235 skipped; integrated full
  suite passed.
- [x] `decimal` — eligible public `Decimal` addition and multiplication of
  exact nonnegative integers reach Rust (`7d23831`). Full `test_decimal`,
  `test_fractions`, `test_statistics`, and `test_numeric_tower`: 1,194 run/14
  skipped; integrated full suite passed.
- [x] `sqlite3` — public cursor statement stepping and ordinary column
  conversion reach Rust (`3df4e0a`). Full `test_sqlite3`,
  `test_dbm_sqlite3`, `test_dbm`, and `test_shelve`: 954 run/14 skipped;
  integrated full suite passed.
- [x] `io` — public buffered byte transfers and line scans, plus text newline
  normalization and write-policy scans, reach Rust (`1e06fcf`). Full `test_io`:
  1,031 run/27 skipped; 14 neighboring suites: 5,052 run/792 skipped;
  integrated full suite passed.
- [x] `logging` — public record creation, formatting, and handler dispatch
  reach Rust (`a0dd573`). Full `test_logging` and `test__interpreters`:
  354 run/7 skipped; integrated full suite passed.
- [x] `asyncio` — public non-debug ready-handle dispatch and due-timer
  promotion reach Rust (`41892d3`). Full `test_asyncio` and seven
  neighboring suites: 4,497 run/122 skipped, with two Windows-only files;
  integrated full suite passed.
- [x] `http.client` — public response status parsing and request-line sending
  reach Rust (`d2aca96`). Full `test_httplib`, `test_httpservers`,
  `test_urllib`, `test_urllib2`, `test_urllib2_localnet`,
  `test_http_cookiejar`, and `test_urllib_response`: 538 run/13 skipped;
  integrated full suite passed.
- [x] `ipaddress` — IPv4/IPv6 string parsing and network bounds reach Rust on
  macOS arm64 (`249d0cb`). Full `test_ipaddress`, `test_socket`, and
  `test_concurrent_futures`: 1,363 run/284 skipped. Integrated default-resource
  suite: 50,158 run/2,703 skipped, zero failures (496/505 files; nine
  resource-denied).
- [x] `socket` — public IPv4/IPv6 `inet_pton`/`inet_ntop` and eligible blocking
  socket `send`/`recv` reach Rust (`609b503`). Full `test_socket` and six
  neighboring suites: 4,033 run/396 skipped; `test_socketserver` was
  resource-denied at baseline. Integrated full suite passed.
- [x] `ssl` — public TLS context setup and MemoryBIO handshake/read/write
  steps reach Rust (`8ab7252`). Full `test_ssl` and 18 neighboring suites:
  5,532 run/403 skipped, including two Windows-only asyncio files;
  integrated full suite passed.
- [x] `subprocess` — eligible POSIX launches and ready-pipe communication
  reach Rust (`0032df8`). Full `test_subprocess` and 12 neighboring suites:
  5,370 run/412 skipped, including baseline Windows and macOS fork skips;
  integrated full suite passed.
- [x] `multiprocessing` — public queue and pipe framing and Pool task
  batching reach Rust (`99fce8e`). Full fork, spawn, forkserver, main
  handling, futures, and logging suites: 1,630 run/163 skipped, including
  four baseline macOS fork files; integrated full suite passed.
- [x] `concurrent.futures` — public `Future` scheduling and publication
  transitions reach Rust (`5126933`). Full `test_concurrent_futures` and
  `test_interpreters`: 570 run/30 skipped; integrated full suite passed.

Priority 1: broad supporting surface

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
- [x] `marshal` — public version-6 serialization and loading of supported
  code/data records, including cycles, reach Rust (`112a4d2`). Cached
  bytecode imports stay extension-free (`1e399a2`); their valid marshal
  bytes match public Rust output but differ from pristine CPython's
  selective-reference output. Full `test_faulthandler`, `test_marshal`,
  `test_importlib`, `test_py_compile`, `test_compile`, and `test_audit`:
  1,602 run/29 skipped; integrated full suite passed.
- [x] `html.parser` — public HTML token scanning reaches Rust (`d64846f`).
  Full `test_htmlparser` and `test_html`: 70 run/2 skipped; integrated full
  suite passed.
- [x] `difflib` — public sequence matching and diff generation use Rust
  longest-match discovery for supported built-in sequences (`2ed801f`).
  Eight full focused suites: 4,119 run/8 skipped; `test_peg_generator`
  was resource-denied at baseline. Integrated full suite passed.
- [x] `codecs` — public standard UTF-8 one-shot and incremental conversion
  reach Rust (`54d5d7e`). Full `test_codecs`, `test_multibytecodec`,
  `test_charmapcodec`, `test_capi`, and `test_io`: 2,864 run/352 skipped,
  matching the clean-stage focused run; integrated full suite passed.
- [x] `unicodedata` — public category, combining, normalization, and
  normalized-state queries reach ICU4X-backed Rust (`ecf5a04`). Full
  `test_unicodedata`, `test__locale`, `test_re`, `test_str`,
  `test_unicode_file`, and `test_unicode_file_functions`: 420 run/99 skipped;
  integrated full suite passed.
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
- [x] `zipimport` — public ZIP discovery, candidate matching, and stored or
  DEFLATE payload extraction reach Rust in the main interpreter (`1196638`);
  own-GIL children retain the Python route. Seven full suites including
  `test_zipimport` and `test_importlib`: 3,146 run/347 skipped; integrated
  full suite passed.
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
- [x] `itertools` — public `chain`, `compress`, `dropwhile`, `filterfalse`,
  `islice`, `starmap`, and `takewhile` steps reach Rust (`3fc5b6d`). Nine
  full relevant suites: 6,027 run/84 skipped, including two Windows-only
  files; integrated full suite passed.
- [x] `functools` — public `cmp_to_key` ordering comparisons reach Rust
  (`953946d`). Full `test_functools`, `test_sort`, `test_list`, and
  `test_userlist`: 479 run; integrated full suite passed.
- [x] `contextlib` — public `ExitStack` and `AsyncExitStack` composition
  reaches Rust (`9f55f22`). Full `test_contextlib` and `test_asyncio`:
  2,880 run/65 skipped; integrated full suite passed.
- [x] `dataclasses` — public class and field processing reaches Rust
  (`aab81e7`). Full `test_dataclasses`, `test_inspect`, and `test_typing`:
  1,405 run/0 skipped; integrated full suite passed.
- [x] `inspect` — public exact `Signature.bind`/`bind_partial` and member
  lookup reach Rust in the main interpreter (`d54262d`); own-GIL children
  retain a Python route. Full `test_inspect`, `test_enum`, `test_pydoc`, and
  `test_unittest`: 2,688 run/11 skipped; integrated full suite passed.
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
- [x] `threading` — public `Barrier` state transitions reach Rust
  (`5fe006a`). Full threading, interpreter, and futures suites: 906
  run/38 skipped; integrated full suite passed.
- [x] `typing` — public `get_origin` and `get_args` generic inspection reach
  Rust (`848ea2d`). Full `test_typing`, `test_annotationlib`,
  `test_dataclasses`, and `test_inspect`: 1,522 run/0 skipped; integrated full
  suite passed.
- [x] `warnings` — public filter insertion and warning display formatting
  reach Rust (`8e08c96`). Full `test_warnings`, `test_logging`,
  `test_unittest`, `test_context`, and `test_interpreters`: 1,803 run/21
  skipped; integrated full suite passed.
- [x] `urllib.request` — public `urlopen` request preprocessing, handler
  dispatch, and response processor dispatch reach Rust (`c8ef0e3`). Twelve
  full default-resource suites: 1,113 run/34 skipped; `test_urllib2net` and
  `test_urllibnet` were resource-denied. Integrated full suite passed.

### Phase 2 — upstream parity (defined, unstarted)

Prerequisite for every U-item: U0. Sequenced after: U1, then U2–U5 in any
order the parent chooses, then U6. Each item owns its route files plus the
differential test it adds; shared `Cargo.toml`/`Cargo.lock`/`Setup.local`
edits need coordinator review even when append-only.

- U0: disposable pristine 3.16.0a1-or-newer comparison build (no overlay).
  Owns: nothing in the overlay; a build record under `.work/tmp/`.
  Proof: `test --all` counts recorded here as the new expected baseline
  (run/skip/deny lists), before any U1–U5 edit.
- U1: marshal exact-byte differential. Replace the `ob_refcnt_full`
  heuristic with occurrence-based reference tagging; add a differential
  test that dumps shared objects, interned strings, code objects, and
  repeated serialization after altering unrelated references, and asserts
  byte identity with pristine. Owns:
  `rust-cpython/overlay/Modules/_marshal_rs/`. Proof: differential test
  plus full `test_marshal`, `test_py_compile`, `test_compile`,
  `test_importlib` green. (Done 2026-10-24 on `lane/u1-marshal`: two-pass
  port, importlib path routed through the same writer decision; 13/13
  corpus byte-identical, all six register suites green. Follow-up: the
  importlib path imported the capsule mid-write, breaking `test_audit` —
  fixed by porting two-pass into the overlay C writer (v6-gated, older
  versions byte-identical), so no import happens on `.pyc` writes.
  Known divergence, not gated: tuple cycles round-trip via the fork
  reader while pristine raises. Resolved by the source rebase, parked as
  an owner decision in Reference.)
- U2: unicodedata / ICU4X 2.4 evaluation. (DONE 2026-10-26 on
  `lane/u2-retry`, merged to main. Retry path: re-applied 2.4.0 pins
  (exact 5-crate lock delta, `build.py fetch --locked` stable, license
  record updated), shadowed a1's three generated UCD headers
  byte-identical (`unicodedata_db.h`, `unicodename_db.h`,
  `Objects/unicodetype_db.h`; struct/index/name-table shapes verified
  identical), and ported a1's 3-state GB9c `update_incb_state` verbatim.
  Root causes fixed, all in owned files: stale 3.2.0 frozen-bidi entries,
  the older 4-state grapheme machine, U17 name/case tables. Proof ran
  a1's own test file out-of-tree (no `Lib/test/` modification):
  lane 73 run / 0 failures / 7 skipped, SUCCESS — identical counts to
  pristine a1; `unidata_version` now 18.0.0 on both. Neighbors
  `test_locale`, `test_re`, `test_str` green on fork files (no U17→U18
  conflict). Footprint import+RSS: lane 20.6 MB vs pristine 16.9 MB
  (logged, not gating). Integrated `test --all --jobs 4` on the merged
  tree: 50,158 run / 9 failures / 2,731 skipped in 9m07s — 3 failed
  files, all attributed: `test_ssl` 4F+6E and `test_support` 14E (the
  OD5-dispensed sets, counts exact), `test_unicodedata` 5 failures all
  fork-file staleness (U17 checksums, old bidi expectation, one renamed
  unassigned char), each green under a1's file. `test_audit` flaked once
  in the full run (parallel `.pyc` churn) and passed alone plus on rerun;
  kept visible, not quarantined. Owns:
  `rust-cpython/overlay/Modules/_unicodedata_rs/` plus the three db
  shadows and the GB9c port in `rust-cpython/overlay/Modules/unicodedata.c`.
  Proof when unparked: full `test_unicodedata` (+ locale/re/str suites
  per the register) green on both hosts plus footprint comparison
  logged (not gating).
- U3: compression-backend evaluation. (DONE 2026-10-24, decision KEEP,
  no flag change: a1 needs pkg-config `libz_rs >= 0.6.0` + `libbz2_rs`
  built from source — sealed-lib production plus new pinned sources and a
  non-SPDX license sit outside the grant; the lane already ships the same
  implementations (`libz-rs-sys 0.6.7`, `libbz2-rs-sys`), so a switch only
  changes the integration layer. Equivalence: `test_zlib`, `test_bz2`,
  `test_gzip`, `test_zipfile`, `test_tarfile` 1,624 run / 9 skipped,
  SUCCESS.)
- U4: uuid re-baseline. (DONE 2026-10-24, keep Rust route: a1 has no
  native C uuid fast paths — uuid4/uuid7 still pure Python — so the item
  reduced to delta reconciliation. `test_uuid` behavior identical to
  pristine (11-test delta is all `test_os` environment drift: fork
  predates 8 upstream tests, lacks `os.pipe2`). Memory logged: lane
  23.2 MB vs pristine 21.3 MB import+RSS (not gating).)
- U5: compat sweep. (DONE 2026-10-24 with two parks, one blocker; commit
  `f63f61b` on `lane/u2-parity`: microsecond UTC normalization in
  `time_richcompare` and the `ZipFile.repack` open-handle guard, both
  probe-identical to pristine with register suites 2,188/170 SUCCESS.
  Lane-vs-pristine suite deltas fully attributed to upstream-added tests,
  zero lane-only failures. PARKED: (a) `re` locale-ignorecase negated
  bytes sets — fork `_sre/sre_lib.h` predates upstream's case-closure
  fix, `_sre` is not a route file, needs an owner backport decision;
  (b) `test_ssl` BLOCKER — 4 failures + 6 errors, all pre-existing RTLS
  policy gaps on clean main (no OpenSSL version/options/DH/reason-codes,
  option-default deltas, one cert-SAN IPv6 rendering divergence); all
  loud, none silent (bad-cert rejection and verify paths pass). Fixing is
  an RTLS policy redesign outside the grant — owner decision required
  before D2 acceptance.)
- U6: integrated re-qualification. (DONE 2026-10-25 on merged
  `lane/integrated-parity` (U1 + U5): full default-resource suite
  50,158 run / 4 failures / 2,731 skipped — run count exactly D1's;
  failures are only the two pre-existing owner-dispensed sets
  (`test_ssl` 4F+6E RTLS policy gaps, `test_support` 14E hashlib-shim
  gaps, all loud, none integration-caused, zero new). The U1 C-port
  fixed `test_audit` back to green. Parity probe: 13/13 byte-identical
  plus the known cycle NOTE. D2 ACCEPTED 2026-10-25 (OD5) with those two
  sets as known deviations; Linux x86-64 re-qual on merged main still
  owed. Proof: run/skip/deny lists equal D1 modulo the recorded
  VSOCK/resource entries; per-item probes still reach Rust in the main
  interpreter with `None` from own-GIL children.)
- U7: source rebase (PARKED 2026-10-25 as a multi-lane wave, not a
  single lane: attempt on `lane/u7-rebase` stopped clean per the ~20-file
  bound with zero tree changes. Triage: 595 overlay files, 88 true
  shadows, 47 differ fork-vs-a1; blockers B1 (missing `cpython-sys` /
  `cpython-build-helper` bindgen glue), B2 (`Makefile.pre.in` Parser
  object drift), B3 (`build.py` fetch-order + `cargo_lock_sha256`
  semantics — pristine upstream has no Cargo workspace), B4 (~47 manual
  merges incl. reworked `Python/marshal.c`), B5 (a1's C writer is already
  two-phase occurrence-based — U1's overlay port may be partially
  redundant, needs a design call). Named prerequisites: P1 lock/fetch
  semantics, P2 U1-writer design call, P3 vendoring + header port.
  Retry: re-scope as a wave when a native Linux host exists (proof needs
  both hosts) or test-file drift forces it. Re-pin target stays peeled
  a1 `22d79d9` (`sha256=7dcd8a1f…`, `size=44114970`); a1 still resolves
  U8 for free and keeps U4 closed; it does NOT resolve U2 (see U2 —
  no pin move was ever needed). HEAD remains a deferred separate step.
  `b812b4a` to peeled `v3.16.0a1` `22d79d9` (2026-10-13; smallest newer
  upstream that builds sealed per G2 — the only candidate with a proven
  sealed build, the U0 record; scouted 2026-10-25: fork branch still at
  `b812b4a`, no newer fork head exists). The a1 pin resolves U8 for free
  (a1 already carries the case-closure fix) and keeps U4 scope closed
  (a1 predates the Oct-21 C-uuid landing `cf690004e`); it does NOT resolve
  U2 (a1's `test_unicodedata` checksum is byte-identical to HEAD's —
  U2 needs a UCD/test update to Unicode 18, not a pin move). Rebasing to
  main HEAD (`2468c35`, +382 commits) is a deferred second step: it
  reopens U4 against native C `UUID`/`uuid4`/`uuid7` and needs its own
  sealed trial. Cost of either: full re-fetch, rebuild, and
  re-qualification on both hosts. Owns:
  `rust-cpython/sources.lock.json` + full overlay reconciliation.
  Proof: new U0 record, U1 differential green, full suites both hosts.
- U8: `re` locale-ignorecase backport (DONE 2026-10-25 on
  `lane/u8-sre-backport`, merged to main: upstream `6671d27327dd`
  GH-156445 rewrite of `SRE(charset_loc_ignore)` via overlay C-shadow;
  fork-plus-hunk byte-identical to pristine a1. NOTE: the U7 a1 re-pin
  subsumes this item; it finished first because the rebase timeline is
  parked behind Linux-host re-qual. Proof: 15-case probe lane-vs-pristine
  OK plus `test_re` 169/3, `test_locale` 69/69, `test_str` 139/6, all
  SUCCESS matching the register.)

### Phase 3 — performance (memory-first in progress; normative contract preserved)

Current macOS memory checkpoint: `perf-rust@373ac78` against `@control`
(`9de0511`) has 31 routes OVER, 39 MET, and 1 BEYOND across all 71 module
memory goals, with no output mismatches. The six remaining workload peak-RSS
regressions are `python_startup` (+4.60%), `django_wsgi_first_request`
(+2.55%), `django_asgi_request` (+1.59%), `django_orm_10k` (+1.76%),
`django_template_realistic` (+1.41%), and `django_wsgi_request` (+1.78%);
the other 18 workloads are neutral or improved. The largest module deficits
are SSL working peak (3.66x control), HMAC load footprint (2.60x), and
datetime load footprint (2.12x). The workload memory gate was repeated at
2026-10-25 21:57Z; the module goal rerun and rigorous UNCLEAR resolution
completed at 22:02Z and 22:12Z.

The shared unicodedata kernel now omits the eight sampled code points newly
assigned in Unicode 18, so both pinned Unicode versions receive identical
benchmark inputs and outputs. A fresh memory-only calibration passed, and
the refreshed 71-route goals had no mismatches. The rejected SSL certificate
key cache lane was NEUTRAL; its unmerged branch is retained. The next SSL
hypothesis targets repeated default crypto-provider construction in the
client and server config builders. The HMAC lane will test whether placing
its generic state behind `_hashlib_rs`, already loaded by `_hashlib`, reduces
resident code while preserving the Rust route. Both worktrees are prepared,
but no climber started: `perf-gate-ready -s` returned 75 at 22:22Z with swap
75% used. The next launch requires that check to pass. Prior startup/export-list
attempts showed no RSS movement and are closed to repetition without a
distinct mechanism.

No lane starts until D1 and D2 acceptance pass. Debt entries remain
unresolved goals; removing a Rust route to meet a goal needs the owner's
decision; coverage still holds.

- Goals: every one of the 71 routes, judged on its own, must use no more
  CPU and no more memory than the pristine control, and should reach 0.9x
  of it (ratio band 0.9x–1.0x). Per-module kernels in
  `rust-cpython/perf_modules.py` (deterministic inputs, output digest both
  interpreters must match, fresh process per sample): kernel CPU per
  iteration, fixed load footprint, working peak footprint; floors 64 KiB
  (load) / 256 KiB (peak) before ratios. Status from `python3
  rust-cpython/perf.py goals` (two runs of five alternating rounds):
  OVER / BEYOND / MET / UNCLEAR per the interval rules in `perf.py`;
  MISMATCH on output divergence. Done per module is MET or BEYOND on all
  three metrics; OVER largest-ratio first; BEYOND stops the climb.
  Seven baseline-set application workloads guard every gated step; a win
  that regresses a guard is rejected. Two failed lanes on a route record
  debt in the ledger.
- Sequencing inside the phase: the memory-first objective governs — every
  module load/working goal and eligible absolute workload RSS goal passes
  before CPU lanes start; debt entries stay unresolved; CPU, timing, and
  quietness do not gate memory work. Memory-only path uses the explicit
  `--memory-only` harness policy (no timing rounds, no CPU prerequisites);
  memory samples, floors, replication, output checks, verified clean
  builds, and complete suites still bind. Host quietness is not a
  prerequisite for memory work.
- Harness: matched fast-iteration builds (`rust-cpython/perf.py`,
  `stage-perf-<name>/`, no PGO/ThinLTO/debug-info, same compiler/flags/SDK
  both sides; only the overlay differs). Timing baselines need a quiet
  host via the repository host lease. Width: up to 31 Codex subagents plus
  the root coordinator (Codex: `gpt-6-luna` at `xhigh` for coordinator and
  every subagent; Claude workflow: Sonnet 5.5 at `high`, `xhigh` for named
  lanes); shared-host work through the perf host lease; harness changes
  need fresh memory-only calibration.
- Hill-climb loop: one lane tests one hypothesis about one module route
  (profile, edit, incremental build, primary suite, exploratory bench,
  then clean build, every relevant suite, gated verdict with application
  guards, goal row). `perf.py bench` decides in code
  (`rust-cpython/perf_verdict.py`): REJECT on any replicated regression,
  INCONCLUSIVE on unquiet host/unstable/single-run, ACCEPT on replicated
  target improvement, NEUTRAL otherwise; `--gate` needs committed
  overlays, incumbent-containing challenger, memory pass, two runs, seven
  guards. The coordinator integrates accepted lanes in batches, gates the
  batch, promotes to `perf-rust`, re-measures.
- Release-grade confirmation (later): repeat key comparisons on matched
  `-O3` PGO + ThinLTO builds; repository workloads first; wall + process
  CPU, RSS/unique memory, allocation passes separately; control
  self-calibration; paired quiet-host counterbalanced runs with raw data;
  stale-`.pyc` control; per-workload judgment.
- Ledger: one row per integration in the coordinator's log (history to
  date recoverable from git history of the former perf doc). Rejected
  candidates are revisited only with a distinct mechanism.

### Phase 4 — hardening

Contract changes written up, docs updated, edge cases from D2 folded into
register lines, exclusion/scope coherence re-checked.

Deferred by owner decision: investigate the intermittent `_marshal_rs`
capsule import failure in `test_audit`, also observed in the product
regression gate. Parallel `.pyc` churn is suspected, not established.
Reproduce under the gate's process environment before choosing a fix.

### Phase 5 — close

Delete what is dead and prove liveness (`dead-code-archaeology` lens),
run the final full suites on both hosts, fix findings to the thresholds
in the Charter, write the final report. No terminal re-audits to
rediscover known obligations.

## Acceptance

- D1: `python3 rust-cpython/build.py test --all --jobs 4` on macOS arm64
  and Linux x86-64 matches Baseline counts (modulo VSOCK/resource
  entries); all 71 probes reach Rust with `None` from own-GIL children.
  Already met; rerun at U6 and close.
- D2: U0 baseline recorded; U1 differential test exists and passes with
  byte identity; U2–U5 suite sets green on lane and pristine with matching
  counts; U6 integrated counts equal U0. Security-sensitive U5-ssl behavior
  verified, not assumed.
- D3: `perf.py goals` reads MET or BEYOND for all 71 modules' load/working
  goals and every eligible workload absolute RSS neutral-or-better; CPU
  goals per the band after. (Deferred; commands retained, not run.)
- D4: this doc is the only campaign plan; no `rust-for-cpython-perf.md`
  in the tree.
- Failure behavior is explicit: distinct user-visible suite failures fail
  the item; interruption/parks record evidence + prerequisite + retry
  condition; recovery after interruption resumes from the last accepted
  checkpoint, never by redefining acceptance.

## Execution boundary

Authorized: branches and worktrees under `.work/wt/`; isolated builds and
sealed-network Linux runs per `rust-cpython/build.py`; fetching pinned
sources; running CPython suites; editing `rust-cpython/overlay/`,
`rust-cpython/*.py` lane tooling, and this doc; local commits only when
the owner explicitly authorizes them for the lane.
Forbidden: pushing anywhere; changing production `buildsys/` artifacts or
the 3.15.1 product; adding platforms, production dependencies, or product
versions; removing a Rust route to meet a goal (needs OD-level decision);
substituting Nixpkgs LLVM/Rust/libc or store paths into payloads; network
access during sealed builds; warm-host timing claims as qualification.
Contract changes made (none this preflight): listed here for the owner.

## Non-goals

- No OpenSSL anywhere in any route, ever. TLS rides the rustls-based
  `_ssl_rs` engine and hashing rides `_hashlib_rs`/`_hmac_rs`; the C
  `_ssl`/`_hashopenssl` modules stay deleted and disabled. This is settled
  ground, not a migration: any lane reintroducing an OpenSSL dependency
  fails its acceptance.
- No redesign around the proposed upstream CPython Rust API (3.17+ plans
  are not merged guarantees).
- No CPU optimization before D2 acceptance; no workload-latency work in D2.
- No Linux arm64 lane builder (out of scope for the experimental lane).
- No second plan, dashboard, supervisor service, or provenance platform.
- No upstream rebase beyond the U0 comparison build without a new owner
  decision (fetch cost and sealed-build policy). Parked for the owner:
  rebasing the lane pin from `b812b4a` to a newer upstream resolves the
  U1 tuple-cycle divergence and lets U6 run upstream test files, at the
  cost of a full re-fetch, rebuild, and re-qualification.
  (b) `test_ssl` RTLS policy gaps (no OpenSSL version/options/DH/
  reason-codes, option defaults, one SAN rendering divergence) — all
  pre-existing on clean main and loud, never silent. `test_support`
  hashlib-disable expectations (14 errors, OpenSSL-fallback assumed
  absent) belong to the same dispensation: pre-existing on clean main,
  in hashing-lane files U1/U5 do not own. Accept deviations, redesign
  RTLS policy, or defer ssl+hashlib-fallback from D2.
  (c) `re` locale-ignorecase fix lives in `_sre`, not a route file —
  backport upstream's case-closure fix or accept the divergence.

## Reference

Code map (verified 2026-10-25 at `920fa8b` unless noted):
- pin: `rust-cpython/sources.lock.json:2-9` (b812b4a, 3.16.0a0).
- lane entry: `rust-cpython/build.py:624-663` (overlay copy),
  `rust-cpython/build.py:1417` (CLI), coordinator skill at
  `.agents/skills/rust-cpython-coordinator/SKILL.md`.
- marshal writer: `rust-cpython/overlay/Modules/_marshal_rs/src/lib.rs:31`
  (`FLAG_REF`), `:349` (`ob_refcnt_full == 1` decision),
  `:959-960` (reader tag handling).
- unicode data: `rust-cpython/overlay/Modules/_unicodedata_rs/Cargo.toml:9-10`
  (`icu_normalizer`/`icu_properties =2.2.0`).
- compression routes: `rust-cpython/overlay/Modules/_zlib_rs/`,
  `_bz2_rs/`, `_gzip_rs/`, `_zip_rs/`; no `--with-zlib`/`--with-bzip2`
  backend selection in `rust-cpython/build.py` (checked).
- hashing/TLS lanes (recent integration context):
  `rust-cpython/overlay/Lib/_hashlib.py` (clinic-exact shim, `920fa8b`),
  `rust-cpython/overlay/Lib/_ssl.py`, `rtls/` provider tree.
- perf tooling (deferred): `rust-cpython/perf.py`, `perf_modules.py`,
  `perf_verdict.py`; Codex skills at
  `.agents/skills/rust-cpython-perf/SKILL.md` and
  `.agents/skills/rust-cpython-perf-climber/SKILL.md`; Claude skills under
  `.claude/skills/`.

Linux x86-64 qualification (accepted, `4710c23` over macOS `1ffb365`;
rerun included at `9329e1c` with identical macOS counts): four
shared-overlay repairs, none changing claimed Rust-owned behavior —
`b0888dd` (mpdecimal static lib; uuid own-GIL fallback; `encodings.utf_8`
eager `_codecs_rs` import), `499308e` (socket send/recv from C methods),
`4710c23` (`stdlib_module_names.h` regeneration). Per-item main/own-GIL
probes: 71/71 reach Rust in main; 60 observed calls, 10 C-level module
loads, `io` via static lib. Suite sets per row as recorded below; pristine
comparisons matched on every row; `test_os` skips vary ±2 between runs
(rerun matched 667/84).

| Target | Suites | Run | Skipped | Notes |
| --- | --- | --- | ---: | --- |
| `urllib.parse` | 8 suites | 2,635 | 420 |  |
| `json` | `test_interpreters`, `test_json` | 402 | 11 |  |
| `pickle` | 7 suites | 4,169 | 119 |  |
| `csv` | `test_csv` | 134 | 0 |  |
| `tomllib` | `test_inspect`, `test_tomllib` | 400 | 0 |  |
| `email` | `test_email`, `test_http_cookiejar`, `test_mailbox`, `test_urllib2` | 2,362 | 5 |  |
| `xml.etree.ElementTree` | `test_xml_etree`, `test_xml_etree_c` | 480 | 12 |  |
| `re` | `test_re` | 169 | 3 |  |
| `base64` | `test_base64`, `test_binascii`, `test_email` | 2,123 | 19 |  |
| `binascii` | `test_base64`, `test_binascii`, `test_email`, `test_zipfile` | 2,712 | 22 |  |
| `zlib` | 13 suites | 3,067 | 94 | denied: `test_zipfile64` |
| `gzip` | `test_gzip`, `test_tarfile`, `test_xmlrpc`, `test_zlib` | 1,027 | 14 |  |
| `zipfile` | 5 suites | 956 | 64 | denied: `test_zipfile64` |
| `tarfile` | `test_shutil`, `test_tarfile`, `test_zipfile` | 1,587 | 59 |  |
| `pathlib` | `test_glob`, `test_pathlib`, `test_shutil` | 1,644 | 455 |  |
| `os.path` | 5 suites | 2,113 | 474 |  |
| `shutil` | `test_shutil`, `test_tarfile`, `test_zipfile` | 1,587 | 59 |  |
| `importlib.metadata` | `test_importlib`, `test_zoneinfo` | 1,486 | 47 |  |
| `hashlib` | `test_hashlib`, `test_hmac`, `test_uuid` | 354 | 36 |  |
| `hmac` | `test_hashlib`, `test_hmac`, `test_imaplib`, `test_support` | 553 | 22 |  |
| `uuid` | `test_os`, `test_uuid` | 667 | 84 |  |
| `datetime` | 7 suites | 2,753 | 313 |  |
| `decimal` | `test_decimal`, `test_fractions`, `test_numeric_tower`, `test_statistics` | 1,194 | 14 |  |
| `sqlite3` | `test_dbm`, `test_dbm_sqlite3`, `test_shelve`, `test_sqlite3` | 1,062 | 15 |  |
| `io` | 15 suites | 6,099 | 805 | VSOCK host failure only |
| `logging` | `test__interpreters`, `test_logging` | 354 | 10 |  |
| `asyncio` | 8 suites | 4,497 | 87 |  |
| `ipaddress` | `test_concurrent_futures`, `test_ipaddress`, `test_socket` | 1,363 | 298 | VSOCK host failure only |
| `socket` | 7 suites | 4,033 | 376 | denied: `test_socketserver`; VSOCK host failure only |
| `ssl` | 19 suites | 5,532 | 389 | VSOCK host failure only |
| `subprocess` | 13 suites | 5,814 | 383 |  |
| `multiprocessing` | 6 suites | 2,074 | 228 |  |
| `concurrent.futures` | `test_concurrent_futures`, `test_interpreters` | 570 | 30 |  |
| `configparser` | `test_configparser`, `test_logging` | 642 | 12 |  |
| `plistlib` | `test_plistlib` | 71 | 2 |  |
| `struct` | 7 suites | 3,235 | 336 | VSOCK host failure only |
| `marshal` | 6 suites | 1,602 | 39 |  |
| `html.parser` | `test_html`, `test_htmlparser` | 70 | 2 |  |
| `difflib` | 8 suites | 1,619 | 15 | denied: `test_peg_generator` |
| `codecs` | 5 suites | 2,881 | 354 |  |
| `unicodedata` | 6 suites | 420 | 191 |  |
| `bz2` | 5 suites | 1,235 | 18 |  |
| `lzma` | `test_lzma` | 123 | 0 |  |
| `compression.zstd` | 6 suites | 2,274 | 73 |  |
| `zipimport` | `test_importlib`, `test_zipimport` | 1,352 | 28 |  |
| `glob` | `test_glob` | 22 | 2 |  |
| `fnmatch` | `test_fnmatch`, `test_glob`, `test_shutil` | 275 | 54 |  |
| `importlib.resources` | `test_importlib`, `test_interpreters`, `test_pathlib`, `test_zipimport` | 2,917 | 437 |  |
| `tempfile` | 5 suites | 1,915 | 470 |  |
| `fractions` | 6 suites | 830 | 16 |  |
| `statistics` | `test_fractions`, `test_math`, `test_random`, `test_statistics` | 654 | 10 |  |
| `random` | `test_random`, `test_statistics`, `test_uuid` | 635 | 26 |  |
| `collections` | 7 suites | 666 | 3 |  |
| `heapq` | `test_heapq`, `test_queue`, `test_sched` | 243 | 6 |  |
| `bisect` | `test_bisect`, `test_datetime`, `test_free_threading`, `test_statistics` | 1,606 | 38 |  |
| `itertools` | 9 suites | 6,027 | 50 |  |
| `functools` | `test_functools`, `test_list`, `test_sort`, `test_userlist` | 479 | 0 |  |
| `contextlib` | `test_asyncio`, `test_contextlib` | 2,880 | 31 |  |
| `dataclasses` | `test_dataclasses`, `test_inspect`, `test_typing` | 1,405 | 0 |  |
| `inspect` | `test_enum`, `test_inspect`, `test_pydoc`, `test_unittest` | 2,688 | 11 |  |
| `ast` | `test_ast`, `test_compile` | 407 | 3 |  |
| `argparse` | `test_argparse`, `test_optparse`, `test_pydoc` | 2,233 | 48 |  |
| `tokenize` | `test_inspect`, `test_tokenize` | 518 | 0 |  |
| `_strptime` | 5 suites | 1,416 | 228 |  |
| `shlex` | `test_mimetypes`, `test_shlex`, `test_webbrowser` | 128 | 21 |  |
| `textwrap` | 6 suites | 2,871 | 78 |  |
| `threading` | 5 suites | 906 | 38 |  |
| `typing` | `test_annotationlib`, `test_dataclasses`, `test_inspect`, `test_typing` | 1,522 | 0 |  |
| `warnings` | 5 suites | 1,803 | 24 |  |

Upstream background (brief of 2026-10-25; plans, not merged guarantees):
3.16.0a1 (2026-10-13) adds `--with-zlib=zlib-rs` / `--with-bzip2=bzip2-rs`
backends, Unicode 18, native C uuid paths (~15x/30x/6.8x claimed), `%Nf`
and fast numeric datetime paths, weakref pickle support, `Sniffer`
rework, `BytesIO.peek`/`ZipFile.remove`/`repack`/`copy_dir_stat`, ECH
with OpenSSL 4+ and eMudhra rejection, and the Sep-30 language-summit
Rust roadmap (3.16 optional zlib + internal API; 3.17 possible
io/json/XML/memoryview/parser; 3.18+ earliest build requirement).
ICU4X 2.4.0 (2026-10-22) embeds Unicode 18 data. The fork branch has no
newer head; deltas accumulate in python/cpython main. Recon 2026-10-24
against the U0 tree: (a) `--with-zlib=zlib-rs` needs pkg-config
`libz_rs >= 0.6.0` (or `zlib.h` plus `-lz_rs`) — a system library the lane
must fetch and pin before any sealed U3 trial; same pattern for
`bzip2-rs`. (b) 3.16.0a1 has NO native C `UUID`/`uuid4`/`uuid7` fast paths
(`uuid4`/`uuid7` are still pure Python in `Lib/uuid.py`; `_uuidmodule.c`
only carries platform helpers) — U4 reconciles the 169-line overlay delta
and re-checks for C entry points at rebase time instead of chasing the
upstream speedups secondhand.

## Decision log and campaign log

- 2026-10-25 preflight: combined the two docs into this one; deferred all
  perf goals behind D2; added the D2 parity stage from the upstream brief.
  Superseded: the two-doc layout and any perf-first scheduling. Preserved:
  all 71 register lines, suite sets, counts, and the full perf normative
  contract above. Removed `rust-for-cpython-perf.md` (in git history).
- 2026-10-25: `8d61d20` integrated parity merged to main (= origin/main
  = `lane/integrated-parity`); D2 accepted with the two loud deviations
  per OD5; U7 rebase + U8 backport queued; Phase 3 memory-first launching.
- 2026-10-25 U7 scout (read-only, no tree changes): no newer fork head
  (`3.x-rust-in-cpython` still `b812b4a`); main HEAD `2468c35` is +382
  commits over peeled a1 `22d79d9`. a1-vs-HEAD: `_sre/sre_lib.h`
  identical (a1 already has the U8 fix), `Python/marshal.c` logic
  identical (wasi→wasm line only), unicodedata checksum identical (U2
  needs a test update, not a pin move), C-uuid landed post-a1 in
  `cf690004e` (HEAD rebase would reopen U4), zlib/bz2 selection
  unchanged (U3 KEEP stands). U7 target set to peeled a1 `22d79d9`;
  HEAD deferred as a separate owner call.
- 2026-10-26 U2 done on `lane/u2-retry` (5ca8af5, merged): 2.4.0 + three
  byte-identical a1 db shadows + GB9c port; a1-file proof 73/0/7 both
  interpreters; integrated --all 50,158/9/2,731 in 9m07s with only
  attributed failures (ssl/support dispensed, unicodedata fork-drift,
  audit flake kept visible). Verification rules learned: swap test files
  after the last build (md5 both ways), chain build+suites+footprint in
  one round, full --all stays a manual integration-only gate.
- 2026-10-26 linker/toolchain ticket (yea-authorized) CLOSED with pushback:
  the libpython export-list half was built and measured — 6702→2066
  exports, all imports green — but vmmap shows resident sections
  byte-identical (LINKEDIT 1248K, DATA_CONST 320K before and after):
  startup residency is dyld fixup chains walked at bind time, not the
  export trie. Reverted (dead mechanism; it had already cost two
  pre-integration breakages: Xcode nm vs Rust objects, ctypes dlsym of
  rtls natives). The panic-sysroot half is parked, not started: the
  same vmmap evidence bounds its win to a fraction of the gap (unwinder
  TEXT is clean/unresident; only its relocs are resident), not worth a
  sysroot rebuild + full requalification now. Workload debt (5 regs:
  python_startup +4.7%, django first-requests +1.1–2.3% peak RSS):
  two failed attempts recorded (startup-mem NEUTRAL with source-proof;
  toolchain ticket with no RSS movement). Mechanism: fixup-chain
  residency proportional to 8 MB Rust TEXT; moves only with LTO or a
  staticlib diet, both out of lane scope. Module lanes continue against
  per-module targets.
- 2026-10-25 U7 attempt stopped per bounds (zero changes): 47 differing
  shadows + B1–B5 infra/design blockers make it a wave, not a lane;
  parked with P1–P3 + Linux-host retry condition. Same day: fork-vs-a1
  test-file check resolved U2's value question — fork expects `00b13fa9…`
  (U17), a1 expects `04a01eac…` (U18, green in U0) — so U2 retries on the
  current pin with 2.4.0 + a1's own test value, no rebase, no invented
  checksum, no `Lib/test/` modification.
- Pre-preflight history (substantive only): 71/71 coverage integrated at
  `9329e1c`/`4710c23`; openssl-less hashing+TLS lanes merged (`ca4d541`);
  macOS promote bridge takes an explicit archive dir (`e8fdad6`).
  Infrastructure, attribution waves, and rejected candidates stay in git
  history, not here.

## For the owner afterwards

- Overrulable without rework: OD1–OD4 above; P1–P4 reversal conditions.
- To launch: the one-line prompt in the preflight report.
- Cherry-picks: U1 differential test (reusable for any future rebase); U3
  backend-equivalence harness; U0 build record as the new baseline anchor.
