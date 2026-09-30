# Rust-for-CPython performance phase

**Active; memory phase in progress, CPU phase not started. See [Codex resumption](#codex-resumption-2026-09-29) first.** All 71 targets in [rust-for-cpython.md](rust-for-cpython.md)
are complete under its strict Python-suite coverage rule, and those rules
still bind every performance change. The old experiment archive was
removed from the active tree; its detailed reports and raw data remain
recoverable from Git history at commit `f0f8690`.

## Toolchain refresh (2026-09-29)

The macOS bootstrap now locks Xcode 27.0 (build `27A266a`) and SDK 27.0.
Apple ld reports `ld-27037.1`; it remains observed rather than pinned.
The bootstrap also records the installed pkgconf 3.0.7 and its Cellar path;
GNU make remains pinned at 4.4.1 and has been provisioned at its locked path.
The deployment floor remains macOS 26.0. The refreshed ThinLTO smoke gate
passed with LLVM 23.1.2: arm64, minos 26.0, SDK 27.0, verified bitcode and
a successful executable run. Doctor reports no missing prerequisites.
The private Cargo home now provides both Cargo and rustc launchers for the
pinned nightly; they work without Homebrew compiler proxies on PATH.
The isolated lane disables configure probes for `dup3` and `pipe2` below
macOS 27, using the existing POSIX paths at its 26.0 deployment floor even
with SDK 27. Both pristine and overlay builds use this same cache policy.
The macOS lane now exposes Homebrew mpdecimal pkg-config metadata, so
`_decimal` and the C-backed decimal tests are present. mpdecimal 4.0.1
is provisioned for this experimental lane; production dependency recipes
and frozen Linux inputs are unchanged.
Both performance interpreters have been rebuilt and qualified under this
toolchain; the resumption below records the fresh calibration, goals, and
baselines. The older handoff describes historical builds.

## Codex resumption (2026-09-29)

The separate Codex coordinator and climber skills live under `.agents/skills/`;
the Claude skills remain intact. Every Codex lane uses `gpt-6.1-sol` at
`medium` effort. The coordinator keeps eight memory climber slots filled as
lanes finish. New worktrees branch explicitly from verified `main`, including
while an integration branch is being judged; they never inherit unaccepted
changes. Memory exploration does not wait for host quietness. CPU remains a
guard; CPU-targeted lanes have not started.

Qualified source commit: `7351620`. Both clean interpreters are verified
release builds. The incumbent full suite passed **50,158 run / 2,748 skipped**,
with no failures. The pristine decimal/fractions/numeric/statistics suites
passed **1,194 run / 14 skipped**. All 30 Rust harness tests passed.
Quiet replicated calibration read **CALIBRATION-OK**: all seven workloads
neutral on every metric in both runs.

Fresh quiet replicated goals read **OVER 51 / UNCLEAR 6 / MET 13 / BEYOND 1**.
Those overall statuses include CPU debt; the memory phase uses the individual
load and working-peak rows below. No module output mismatch was observed.
The quiet all-workload gate against pristine control read REJECT because
**22 of 23 workloads regress peak RSS**; `zlib_decode_1m` improves.
This is outstanding absolute debt, not a verdict on a new optimization.
The committed baseline snapshots are refreshed from that run.

Historical batches `f7a0121`, `3ce7286`, and `e41f4fb` now have quiet,
replicated confirmation against their recorded previous incumbent `a97f52a`,
using exact overlay snapshots and the locked current toolchain. All target
memory improvements replicated; every application guard avoided regression.
This confirms their original measuring contract, not absolute memory completion.

The comparison evidence was preserved under the primary checkout's ignored
`rust-cpython/results/lane-handoffs/confirm-history/results/perf-bench/`
before removing the clean historical worktree: `20260930T031254Z` (zip/glob),
`20260930T033220Z` (futures), and `20260930T040005Z` (gzip/shlex/URL/textwrap).
Historical previous, zip, and final snapshots each passed 50,158/2,791.
The futures snapshot's full run had one asyncio stream-test failure; its
complete asyncio rerun passed 2,780/65. Both logs are retained. The 43 extra
historical skips are case/subtest skips, with unchanged test sources; path
length limits are a possible cause, not a proved attribution. Current
primary qualification remains 50,158/2,748, with no failures.

Fresh partial goals put zipfile, gzip, urllib.parse, textwrap, and futures
memory at MET or BEYOND. Zipimport load remains 1.10x OVER, shlex 1.08x OVER;
glob's rigorous rerun resolves load to 1.06x OVER. These are snapshots under
the original runner boundary; a discovered premeasurement JSON import
preloads Rust regex and requires refreshed goals after correction.

Local evidence (ignored result files): calibration `20260929T224548Z-calibrate-perf-upstream`,
workloads `20260929T224734Z-perf-upstream-vs-perf-rust`, and goals
`20260929T225352Z-goals-perf-upstream-vs-perf-rust` under
`rust-cpython/results/perf-bench/`.

### First accepted Codex memory batch

Batch `284fa00` integrates `fractions`, `tarfile`, and `random`. Its clean
primary-path build verified 69 Rust extension images and passed the complete
suite: **50,158 run / 2,748 skipped**, no failures. The quiet two-run gate
accepted load ratios **0.750x**, **0.875x**, and **0.762x**, respectively,
against the previous incumbent. Each improvement clears the floor in both
runs; working peak and all seven workload guards are neutral. The worktree
Django startup regressions did not recur on the primary path. Random's
worktree gate had only a CPU win; its memory acceptance comes from this
primary gate. Its wrapper intentionally retains the first successfully
imported private Rust module: patching attributes remains visible, replacing
`sys.modules['_random_rs']` no longer redirects the wrapper.

Primary candidate goals against control put random's memory rows at MET.
Fractions load remains OVER at 1.21x; tarfile load remains OVER at 1.12x.
Their working peaks are MET. The evidence is
`20260930T015030Z-perf-rust-vs-perf-merge/verdict.json` and
`20260930T020801Z-goals-perf-upstream-vs-perf-merge/verdict.json` under
`rust-cpython/results/perf-bench/`. Rigorous module sampling uses ten rounds;
workload guards retain complete standard evidence sampling.

Fnmatch and tempfile have qualified memory winners awaiting the next primary
batch. Bisect's final memory gate was NEUTRAL despite its exploratory gain;
socket, datetime, and the new codec startup experiment likewise did not
qualify memory gains. Those branches and ignored handoff evidence are
preserved for later work. Codecs startup saved about 0.5% RSS, below the floor;
this is its second failed memory lane, and it does not waive the outstanding
workload memory completion gate. Current skip discrepancies were checked
against the incumbent: tempfile 1,915/496, codecs 2,864/364, with no candidate
increase. Historical debug-era table counts remain separate evidence.

A shared `re` eligibility lane now tests whether unsupported flags can be
rejected before loading `_re_rs`. Warnings' 200 `re.I` filters resolve to
flags 34, while the Rust helper only accepts 0 or 32; the native profile
shows the image loading solely to decline those calls. Supported regex calls
must continue reaching Rust. Other active lanes include decimal, argparse,
functools, UUID, contextlib, and strptime. Durable live lane state is in
`rust-cpython/results/coordinator-state.json` (ignored).

### Corrected measurement boundary and native route coverage

Commit `1faf2e4` moves JSON result serialization after all memory and timing
snapshots. Previously JSON's encoder compiled supported regex patterns before
the load baseline, preloading `_re_rs` and hiding some routes' import cost.
The old comparisons remain evidence for their original boundary; future
goals and acceptance comparisons use the corrected runner. The shared regex
flag-eligibility experiment was rejected under the old boundary and its
tested patch is preserved for a later corrected comparison.

The same separate measuring-stick commit retains existing kernels and adds
successful native pickle dump/load round trips, functional resource reads,
and Pool task batching to multiprocessing. Three fresh staged regressions
failed before the route additions; all four route/boundary tests now pass.
Complete outputs for all three corrected kernels match pristine control.
No overlay source or CPython test was changed by this correction. Existing
tables below are snapshots; a full goal refresh follows the next accepted
integration before selecting further lanes.

### Current module goal table

Ratios compare the measured candidate with pristine control. Each cell records
the pooled ratio and replicated goal status; small memory values use harness
floors. Fractions, tarfile, and random are refreshed from the accepted primary
batch. Other rows retain the initial full snapshot at `7351620` and have not
yet been remeasured after this integration; cross-module drift is checked in
every third integration and at memory completion.

| Module | CPU | Load footprint | Working peak | Overall |
| --- | --- | --- | --- | --- |
| `_strptime` | 1.694x OVER | 1.169x OVER | 1.000x MET | OVER |
| `argparse` | 2.345x OVER | 1.287x OVER | 1.000x MET | OVER |
| `ast` | 1.371x OVER | 1.041x OVER | 1.000x MET | OVER |
| `asyncio` | 1.130x OVER | 1.069x OVER | 1.000x MET | OVER |
| `base64` | 2.932x OVER | 1.081x OVER | 1.000x MET | OVER |
| `binascii` | 1.645x OVER | 1.000x MET | 1.000x MET | OVER |
| `bisect` | 3.944x OVER | 2.000x OVER | 1.000x MET | OVER |
| `bz2` | 1.011x UNCLEAR | 1.013x UNCLEAR | 1.000x MET | UNCLEAR |
| `codecs` | 0.766x BEYOND | 0.900x MET | 1.000x MET | MET |
| `collections` | 1.053x OVER | 1.000x MET | 1.000x MET | OVER |
| `compression.zstd` | 0.897x MET | 0.760x BEYOND | 1.000x MET | MET |
| `concurrent.futures` | 0.740x BEYOND | 0.513x BEYOND | 0.258x BEYOND | BEYOND |
| `configparser` | 0.221x BEYOND | 0.838x MET | 0.896x BEYOND | MET |
| `contextlib` | 1.134x OVER | 1.081x OVER | 1.000x MET | OVER |
| `csv` | 3.011x OVER | 0.969x MET | 1.000x MET | OVER |
| `dataclasses` | 1.007x MET | 1.011x UNCLEAR | 0.993x MET | UNCLEAR |
| `datetime` | 3.017x OVER | 1.192x OVER | 1.000x MET | OVER |
| `decimal` | 5.710x OVER | 1.250x OVER | 1.000x MET | OVER |
| `difflib` | 1.151x OVER | 1.108x UNCLEAR | 1.000x MET | OVER |
| `email` | 1.039x OVER | 0.929x MET | 1.032x UNCLEAR | OVER |
| `fnmatch` | 1.443x OVER | 1.955x OVER | 1.000x MET | OVER |
| `fractions` | 3.299x OVER | 1.211x OVER | 1.000x MET | OVER |
| `functools` | 4.996x OVER | 1.348x OVER | 1.000x MET | OVER |
| `glob` | 0.614x BEYOND | 1.062x OVER | 1.000x MET | OVER |
| `gzip` | 0.613x BEYOND | 0.689x BEYOND | 1.000x MET | MET |
| `hashlib` | 1.036x OVER | 1.006x MET | 1.000x MET | OVER |
| `heapq` | 1.746x OVER | 1.000x MET | 1.000x MET | OVER |
| `hmac` | 1.449x OVER | 1.029x UNCLEAR | 1.000x MET | OVER |
| `html.parser` | 0.979x MET | 1.145x UNCLEAR | 1.000x MET | UNCLEAR |
| `http.client` | 1.047x OVER | 1.037x UNCLEAR | 1.000x MET | OVER |
| `importlib.metadata` | 0.738x BEYOND | 1.006x MET | 1.000x MET | MET |
| `importlib.resources` | 1.026x OVER | 1.043x OVER | 1.000x MET | OVER |
| `inspect` | 1.390x OVER | 1.072x OVER | 1.000x MET | OVER |
| `io` | 1.553x OVER | 1.000x MET | 1.000x MET | OVER |
| `ipaddress` | 0.485x BEYOND | 0.988x MET | 1.000x MET | MET |
| `itertools` | 2.826x OVER | 1.000x MET | 1.000x MET | OVER |
| `json` | 0.712x BEYOND | 0.476x BEYOND | 1.000x MET | MET |
| `logging` | 1.005x MET | 1.097x OVER | 1.037x UNCLEAR | OVER |
| `lzma` | 1.360x OVER | 0.116x BEYOND | 1.000x MET | OVER |
| `marshal` | 0.882x MET | 1.056x OVER | 1.000x MET | OVER |
| `multiprocessing` | 1.009x MET | 1.212x OVER | 1.000x MET | OVER |
| `os.path` | 1.727x OVER | 1.250x OVER | 1.000x MET | OVER |
| `pathlib` | 0.957x MET | 1.182x OVER | 1.000x MET | OVER |
| `pickle` | 1.002x MET | 1.045x UNCLEAR | 1.000x MET | UNCLEAR |
| `plistlib` | 0.078x BEYOND | 0.683x MET | 1.000x MET | MET |
| `random` | 1.274x OVER | 1.000x MET | 1.000x MET | OVER |
| `re` | 1.002x MET | 1.000x MET | 1.000x MET | MET |
| `shlex` | 0.285x BEYOND | 1.091x OVER | 1.000x MET | OVER |
| `shutil` | 1.006x MET | 0.718x BEYOND | 1.000x MET | MET |
| `socket` | 1.256x OVER | 1.318x OVER | 1.000x MET | OVER |
| `sqlite3` | 3.900x OVER | 1.088x OVER | 1.000x MET | OVER |
| `ssl` | 1.001x MET | 1.061x UNCLEAR | 1.000x MET | UNCLEAR |
| `statistics` | 0.077x BEYOND | 1.276x OVER | 1.000x MET | OVER |
| `struct` | 2.108x OVER | 1.004x MET | 1.000x MET | OVER |
| `subprocess` | 1.010x MET | 1.145x OVER | 1.000x MET | OVER |
| `tarfile` | 0.393x BEYOND | 1.120x OVER | 1.000x MET | OVER |
| `tempfile` | 1.022x UNCLEAR | 1.226x OVER | 1.000x MET | OVER |
| `textwrap` | 0.037x BEYOND | 0.915x MET | 1.000x MET | MET |
| `threading` | 1.950x OVER | 1.000x MET | 1.000x MET | OVER |
| `tokenize` | 1.114x OVER | 1.018x OVER | 1.000x MET | OVER |
| `tomllib` | 0.072x BEYOND | 1.100x UNCLEAR | 1.000x MET | UNCLEAR |
| `typing` | 1.524x OVER | 1.143x OVER | 1.000x MET | OVER |
| `unicodedata` | 2.468x OVER | 1.222x UNCLEAR | 1.000x MET | OVER |
| `urllib.parse` | 0.223x BEYOND | 0.514x BEYOND | 1.000x MET | MET |
| `urllib.request` | 1.130x OVER | 1.070x UNCLEAR | 1.000x MET | OVER |
| `uuid` | 1.395x OVER | 1.177x OVER | 1.000x MET | OVER |
| `warnings` | 1.097x OVER | 1.390x OVER | 1.000x MET | OVER |
| `xml.etree.ElementTree` | 0.927x MET | 1.194x OVER | 1.125x UNCLEAR | OVER |
| `zipfile` | 0.672x BEYOND | 0.678x BEYOND | 1.000x MET | MET |
| `zipimport` | 0.989x MET | 1.096x OVER | 1.000x MET | OVER |
| `zlib` | 0.624x BEYOND | 1.095x OVER | 1.000x MET | OVER |

### Current workload picture

| Workload | Wall | CPU | Peak RSS |
| --- | --- | --- | --- |
| `catalog_json_export` | 0.954x improved | 0.999x neutral | 1.058x regressed |
| `catalog_request_path` | 0.710x improved | 0.843x improved | 1.116x regressed |
| `catalog_search_form` | 0.413x improved | 0.463x improved | 1.100x regressed |
| `catalog_url_normalize` | 0.898x improved | 0.912x improved | 1.092x regressed |
| `compileall_source` | 1.004x neutral | 1.211x regressed | 1.106x regressed |
| `difflib_unified_mostly_equal` | 3.496x regressed | 3.226x regressed | 1.100x regressed |
| `difflib_unified_reordered` | 1.344x regressed | 1.335x regressed | 1.097x regressed |
| `django_asgi_request` | 1.021x regressed | 1.139x regressed | 1.061x regressed |
| `django_orm_10k` | 2.015x regressed | 1.205x regressed | 1.063x regressed |
| `django_template_realistic` | 1.079x regressed | 1.150x regressed | 1.060x regressed |
| `django_wsgi_first_request` | 1.240x regressed | 1.247x regressed | 1.105x regressed |
| `django_wsgi_request` | 1.029x regressed | 1.147x regressed | 1.067x regressed |
| `gzip_extract_1m` | 0.495x improved | 1.221x regressed | 1.041x regressed |
| `import_django` | 1.278x regressed | 1.292x regressed | 1.090x regressed |
| `multiprocess_pool` | 0.993x neutral | 1.001x neutral | 1.074x regressed |
| `python_startup` | 1.000x neutral | 1.099x regressed | 1.028x regressed |
| `rust_base64_large` | 0.611x improved | 1.134x regressed | 1.085x regressed |
| `rust_base64_small` | 0.894x improved | 1.205x regressed | 1.083x regressed |
| `serialization_roundtrip` | 1.009x neutral | 1.071x regressed | 1.089x regressed |
| `zip_read_wheel` | 0.987x neutral | 1.260x regressed | 1.065x regressed |
| `zipimport_cold` | 1.203x regressed | 1.250x regressed | 1.087x regressed |
| `zlib_decode_1m` | 0.567x improved | 1.193x regressed | 0.978x improved |
| `zlib_stream_4k` | 0.688x improved | 1.231x regressed | 1.074x regressed |

The next acceptance evidence must compare lane or integrated challenger
against the qualified incumbent, include complete suites, and retain the
application guards. The memory phase stays open until its absolute workload
condition and module/debt condition both pass.

## Handoff (2026-09-29)

Written when the session wound down. The memory phase (load footprint and
working peak first, CPU only after) is **not finished**; the CPU phase has not
started. Read this before touching anything.

### State

- `main` is at `e41f4fb`. `perf-rust` is built there (verified, clean);
  `perf-upstream` (pristine control) is at `d41b580`. No worktrees remain except
  the primary checkout. Check `python3 rust-cpython/perf.py status` and
  `git log --oneline -1` match before starting; rebuild `perf-rust` if not.
- 23 lane changes are integrated over 12 ledger rows (see the ledger): `etree`,
  `zstd` (Rust side, then the C glue), `lzma`, `re`, `bz2`, `asyncio`, `os.path`,
  `json`, `tomllib`, `plistlib`, `zlib`, `binascii`/`base64`, `statistics`,
  `marshal`, `configparser`, `zipfile`/`zipimport`, `glob`, `concurrent.futures`,
  `gzip`, `shlex`, `urllib.parse`, `textwrap`.
- Last full `perf.py goals` (host quiet at start, `e41f4fb`): **OVER 44,
  UNCLEAR 17, MET 10** of 71 (first baseline: 63 / 6 / 2). MET: `urllib.parse`,
  `json`, `re`, `zipfile`, `html.parser`, `zipimport`, `shutil`,
  `compression.zstd`, `configparser`, `concurrent.futures`. Working peak is MET
  or noise-bound on nearly every module; the remaining memory debt is mostly
  **load footprint** (about 50 modules, 16 KiB to 700 KiB over control), and
  most of it is other Rust routes' dylibs on each module's import path.
- **Provisional integrations.** The ledger rows `f7a0121`, `3ce7286` and `e41f4fb`
  (`zipfile`/`zipimport`/`glob`, `concurrent.futures`, and `gzip`/`shlex`/`urllib.parse`/`textwrap`)
  were integrated under the memory-phase unquiet-host rule (gate `INCONCLUSIVE` for `quiet=no` only, every
  target improved, no row regressed, full suite passed). They have **not** had a
  quiet-host confirmation. Baselines under `benchmarks/baselines/` were recorded
  at `3f5846f` (quiet); the workload picture (peak RSS regressed on 21 of 23
  workloads at that point) has **not** been re-measured since. The earlier
  ledger rows (`59ec0b8` through `a97f52a`) were gated at `quiet=yes` in the
  primary checkout, except `59ec0b8` and `3f5846f`, whose lane gates were
  `quiet=yes` on the same code.
- Skills, agents, and the harness are committed and current:
  `.claude/skills/rust-cpython-perf` (coordinator), `.../rust-cpython-perf-climber`,
  `.claude/agents/rust-perf-climber*.md`, `.claude/skills/rust-cpython-perf/wait_quiet.py`.
  The coordinator's working state file `rust-cpython/results/coordinator-state.json`
  is git-ignored and may be stale or absent; rebuild state from `git`, `perf.py
  status`, and this ledger.

### Do these first (in order)

1. `python3 .claude/skills/rust-cpython-perf/wait_quiet.py 180`, then
   `python3 rust-cpython/perf.py calibrate --ref @control --gate`; continue only on
   `CALIBRATION-OK` with `quiet=yes`.
2. Confirm the provisional batches and refresh the workload picture:
   `python3 rust-cpython/perf.py bench --baseline @control --candidate @incumbent
   --gate --all-workloads --record-baselines`. Any module or workload row that
   regressed against the previous incumbent becomes a repair lane; commit the
   refreshed baselines and add a ledger row. Watch `python_startup` (wall read
   1.237 with interval [1.000, 1.289] at `e41f4fb` on an unquiet host).
3. `python3 rust-cpython/perf.py goals`; for UNCLEAR rows use
   `goals --module M --profile rigorous` once (rule in the skill: pooled median
   above 1.01x counts as OVER, otherwise MET). Memory rows are noisy (below).
4. Then the memory phase ends only when every module's load footprint and
   working peak are MET or BEYOND (or debt-listed) **and** every workload's
   `peak_rss` is neutral or improved against `@control`. Only then start CPU
   lanes (largest ratios: `decimal` 5.7x, `functools` 5.0x, `sqlite3` 3.9x,
   `bisect` 3.9x, `fractions` 3.5x, `datetime` 3.3x, `csv` 3.0x, `base64` 2.9x,
   `itertools` 2.8x, `unicodedata` 2.5x, `argparse` 2.4x).

### What is left, and what to try

- **The per-dylib floor (biggest remaining lever).** Measured by the `dylib-mem`
  lane: every dlopen'd Rust extension dirties `__DATA_CONST` + `__DATA` (32 KiB)
  at import, 16 KiB with `-Wl,-no_data_const`, and costs 48 to 96 KiB resident
  and about 0.65 ms of dlopen; `asyncio` imports 14 of them and `import_django`
  35. `panic = "abort"`, `-Wl,-x`/strip and `opt-level=s` do not change
  footprint. Static linking all 67 modules through `cpython-rust-staticlib`
  builds first try and lowers import-heavy load rows 2% to 7% but adds about
  +150 KiB dirty `__DATA_CONST` to every process at startup (libpython 7.5 ->
  13.9 MB), so the plan is a **hybrid**: link the tiny `no_std` modules plus the
  hot mid-size ones statically, keep `_re_rs` and `_sqlite3_rs` shared, and judge
  it on `python_startup` private/PSS. Conflict to solve: every `no_std` route
  defines its own `#[panic_handler]`, which collides with the std-based
  staticlib; gate the handler behind a cargo feature enabled only by the shared
  build. Mechanism (Setup.local `*static*`, an entry in
  `overlay/Modules/cpython-rust-staticlib/Cargo.toml` and its `Cargo.lock`
  package, re-export `PyInit_*`) is on branch `dylib-mem-static-wip`
  (`118133a`, not integrable as is). A `no_data_const` line already lives in
  each `no_std` route's `build.rs`; the shared-helper version
  (`worktree-agent-abf87d8fae69689c8`, `410e46b`) read NEUTRAL and is redundant.
- **Lazy imports in overlay wrappers.** Several wins came from importing less
  (`re`, `ipaddress`, `threading`, `pathlib`, `shutil`, `contextlib`, `zlib`)
  in `overlay/Lib/*.py` wrappers, not from Rust changes. Look at every wrapper
  whose module still reads OVER on load with `-X importtime` against `@control`.
- **Startup.** `_codecs_rs` still loads at interpreter startup through
  `encodings.utf_8` (1.75 ms, the largest startup import; control has none). The
  `startup-mem` lane (branch `worktree-agent-a6c344f4467798c81`, `55bcd49619`)
  made it lazy and statically linked, read `NEUTRAL` (below the 1% floor), and
  is one failed lane on that route. It needs the static-link work above to pay.
  Linux `test_io.test_fileio` (an strace check) was not run on that branch.
- **Candidate lanes (memory, none tried yet):** `fnmatch` (+190 KiB), `fractions`,
  `functools`, `decimal`, `datetime`, `struct`, `socket`, `uuid`, `warnings`,
  `_strptime`, `tempfile`, `xml.etree.ElementTree` (peak 1.28x, load 1.19x),
  `tarfile` (load 1.49x), `logging`, `email`, `importlib.metadata`,
  `importlib.resources`, `multiprocessing`, `urllib.request`, `http.client`,
  `sqlite3`, `unicodedata`, `argparse`, `typing`, `random`, `tokenize`,
  `contextlib`, `difflib`, `inspect`, `pickle`. Use the `no_std` recipe below
  where the route is small.
- **`pickle` WIP.** Branch `worktree-agent-abe893d6765eee240` (`0ec6bed`):
  `_pickle_rs` rewritten `#![no_std]` (709 KB -> 38 KB) with no Rust allocation,
  built and smoke-tested, **no suite run**. The kernel graph (tuples) always
  declines to C `_pickle`, so the extra load is the image and the peak is the old
  encoder's transient allocations. Finish: run `test_pickle`, `test_picklebuffer`,
  `test_pickletools`, `test_copy`, `test_copyreg`, `test_shelve`, `test_dbm`,
  `test_zipfile`, then gate with `--module pickle --workload serialization_roundtrip`.
- **Remaining CPU debt** is untouched (memory phase first). `base64` (2.9x),
  `binascii` (1.6x; `crc_hqx` is bit by bit) and `lzma` (1.37x, `lzma-rust2`
  speed; a different crate is a valid experiment) were noted by their lanes.

### Review items owed (behavior or risk the lanes introduced)

- **`bz2`**: a codec-scoped allocator serves large "zeroed" block-sort tables
  without the libmalloc memset; safe only because `libbz2-rs-sys` never reads
  a table entry before writing it (MallocScribble runs matched control). Prefer a
  patched local copy if this ever changes.
- **`_re_rs`**: a global allocator with a 60 KiB static scratch arena confined to
  one thread and one parse scope; reviewed once by the coordinator (arena
  pointers are never freed, nothing escapes the scope, panic resets via `Drop`).
- **Workspace `panic = "abort"`** in `overlay/Cargo.toml` (needed by `no_std`
  routes; no overlay crate uses `catch_unwind`; gated across eight modules).
- **`marshal`**: glue in `overlay/Python/marshal.c` reaches Rust through a cached
  `_marshal_rs._api` capsule; public `marshal.dumps` bytes now match pristine
  CPython (`FLAG_REF` only on shared or interned objects); `force_refs` is always
  0 and can be removed.
- **`zstd`**: `_zstd/compressor.c` and `decompressor.c` no longer run libzstd
  first and Rust on a copy; the C path remains for dictionaries, options, and
  when `_zstd_rs` cannot load (subinterpreters).
- **`plistlib`**: equal XML dict keys share one `str`; `load()` reads a file object
  whole; module-level helper names `binascii`, `struct`, `re`, `itertools`,
  `ParserCreate` no longer exist on `plistlib` (private test helpers resolve
  through `__getattr__`); pure-Python code moved to `Lib/_plistlib_py.py`.
- **`zipfile`** imports `zipfile._path`, `shutil`, `bz2`, `lzma`,
  `compression.zstd`, `binascii` lazily (PEP 810 `lazy import`) and uses
  `_thread.RLock()`; `_codec_missing()` and `mock.patch('zipfile.bz2', None)`
  still work.
- **`concurrent.futures`**: `_FutureCondition` subclasses `threading.Condition`
  and depends on `_lock`, `_waiters`, and the RLock's `_is_owned`,
  `_release_save`, `_acquire_restore`; re-check it if `threading` changes.
- **`gzip`** keeps a process-global (atomic) ~300 KiB DEFLATE state block
  resident after the first compress; error text for a bad level now matches C.
- **`glob`** returns `readdir` order (sorted order was the crate's, `glob`
  documents order as undefined). **`textwrap`**: `\x0b` is whitespace in
  placeholders. **`urllib.parse`**: `re`, `ipaddress`, `math`, `warnings` import
  on first use; `urllib.parse.re` stays resolvable via `__getattr__`.
- **Skip counts** read a few higher than the checklist (release build vs the
  debug build the checklist ran: `test_bz2` refleak, `Py_DEBUG`-only tests);
  total skips across the full suite are identical to the incumbent
  (2,748), so nothing new was introduced.
- All lane commits keep their differential fuzz results in their handoffs
  (`glob` 2.1M pairs, `shlex` 800k, `textwrap` 30k, `configparser` 20k,
  `plistlib` 15k, `tomllib` 280k, `os.path` 42k); scripts were not committed.

### Playbook (what worked)

1. **Drop Rust `std` from small extensions.** `#![no_std]`, no `cpython-sys`, a
   `#[panic_handler]` that calls libc `abort`, hand-declared `extern "C"` entry
   points and `PyModuleDef`/`PyMethodDef` layouts; on macOS put
   `#[cfg_attr(target_vendor = "apple", link(name = "System"))]` on the extern
   block (rustc passes `-nodefaultlibs`); `PyMem_Malloc`/`PyMem_Free` instead of
   `Vec`. Images fell 408 KiB -> 35 to 70 KiB, and imports cost about 16 to 32
   KiB. Worked examples: `_statistics_rs`, `_glob_rs`, `_posixpath_rs`,
   `_marshal_rs`, `_shlex_rs`, `_textwrap_rs`, `_urllib_parse_rs`. For recursive
   routes that keep `std`, declaring only the recursive entry points `unsafe
   extern "C"` lets LLVM infer `nounwind` and drops landing pads.
2. **Write straight into the result object** (`bytes`/`str` sized exactly, resized
   in place), build Python objects directly from borrowed input, no intermediate
   `Vec`/tree/copy. Track shared objects in a `PyMem` table.
3. **Every first allocation of a new size class in a Rust first call dirties a
   fresh 16 KiB `MALLOC_SMALL` page** that stays resident; use one pre-sized
   buffer, a stack buffer with a `PyMem` fallback, or a scratch arena.
4. **libmalloc memsets large `alloc_zeroed` blocks**; avoid zeroed requests.
5. **Intern attribute names once** in per-module state and call with
   `PyObject_VectorcallMethod`; no temporary `str` per lookup.
6. **Swap `flate2`/`miniz_oxide` for `libz-rs-sys` (zlib-rs)** driving the zlib C
   API (`zlib`, `gzip`, `zipfile`, `zipimport`).
7. **Import less** in overlay wrappers (lazy `re`, `ipaddress`, `threading`, ...).
8. **Remove duplicate work in C glue** (`zstd` ran C then Rust; `configparser`
   parsed in Rust, re-serialized, parsed again in Python).
9. Attribute residue with the macOS `footprint` tool on a single probe process
   (probes only; benches and suites go through `perf.py`).

### Process lessons (pitfalls hit this session)

- **Worktree-path bias.** Lane builds sit at long paths; their gates read
  `import_django` / `python_startup` (and any startup-bound guard) 1% to 3% off
  against the primary-path `@incumbent`, producing false `REJECT`s
  (`zstd-glue`, `tomllib`, `plistlib`). Batches are built and gated in the
  **primary checkout** on a temporary `integrate-N` branch; that gate decides.
  Identical builds can read up to about 300 KiB apart in startup footprint by
  stage directory.
- **Spawn lanes only while the primary is on `main`** with `perf-rust` built from
  `main`'s overlay: worktrees branch from the primary's HEAD, and a lane spawned
  during an integration window starts from unaccepted commits and blocks.
- **`Cargo.lock`.** Lanes hand-edit it; two edits merge textually but can fail
  `cargo fetch --locked`. Fix: in `work/perf/perf-merge/source/cpython-*/` run
  `env CARGO_HOME=<primary>/rust-cpython/.cargo-home <cargo-home>/bin/cargo
  metadata --offline --format-version 1` (no `--locked`), copy that `Cargo.lock`
  to `overlay/Cargo.lock`, commit, rebuild. Check the build printed `OK` before
  chaining a gate or suite behind it.
- **Do not `pkill -f` a build command string**: it also matches chain shells
  that contain it. Kill by PID.
- **Memory rows are noisy and quantized.** Load moves in 16 KiB steps and is
  often bimodal; control working peak swings 16 KiB to 1.7 MiB run to run on some
  kernels (`shutil`, `zlib`, `lzma`); floors are 64 KiB (load) and 256 KiB (peak).
  Use replicated benches, `goals --profile rigorous`, and a 30-sample
  `perf_modules.py measure` spread before believing a single row. The kernel
  harness imports `json` before `measure()`, so probes that skip it look about
  400 KiB better than the harness reports; and the kernel setup imports `tempfile`
  for some kernels, so residual load rows include other routes' dylibs.
- Agents cannot be resumed once the user stops them; relaunch a new climber from
  the stopped branch (WIP commit first). `/tmp` is shared between lanes; use
  lane-unique probe file names.
- The host lease serializes measurements; builds and suites share it. With eight
  lanes, a lane's clean build plus suites plus gate took 40 to 90 minutes.

### Repository housekeeping

- Kept branches: `dylib-mem-static-wip`, `worktree-agent-a6c344f4467798c81`
  (startup), `worktree-agent-abe893d6765eee240` (pickle WIP),
  `worktree-agent-abf87d8fae69689c8` (dylib shared helper). Superseded and safe
  to delete: `worktree-agent-aae84e8e51f23d329` (old lzma), `worktree-agent-a88d705ab31f64e28`
  (old plistlib WIP).
- Decisions recorded in `AGENTS.md`: any Rust crate is allowed for the perf lane
  (pinned in `Cargo.lock`, license noted); the climb is memory-first with up to
  8 lanes; memory-phase lanes may integrate on an unquiet host when no row
  regresses (provisional until a quiet gate).
- Nothing was pushed. Do not push without the user.

## Objective after coverage

Make the covered stdlib faster and more resource efficient on representative
application workloads without sacrificing Python-level correctness. Compare
against matched upstream CPython 3.16 and the preceding accepted fork. Keep
wall latency, actual process-tree user/system CPU, peak and retained memory,
allocation activity, installed native size, and build complexity separate.
Use quiet, paired runs and self-comparison noise bounds. A microbenchmark
alone does not establish a practical gain. A coverage port may remain even
when a later performance result is negative; record that debt plainly.

## Goals

Every one of the 71 checklist routes, judged on its own, must use **no
more CPU and no more memory than the pristine control, and should reach
0.9x of it**: each ratio (Rust candidate over control) belongs in the band
0.9x to 1.0x.

- **Measured per module.** `rust-cpython/perf_modules.py` holds one kernel
  per checklist route that exercises the public behavior the checklist says
  reaches Rust, with deterministic inputs and an output digest both
  interpreters must match. Each sample is a fresh process. The three
  metrics are kernel CPU per iteration (`time.process_time()`), fixed load
  footprint (imports, lazily loaded extensions, and first-call caches,
  estimated as a first setup-and-call's footprint growth minus a
  second's), and working peak footprint over the kernel loop (the kernel's
  `ri_interval_max_phys_footprint`, reset at loop start). Memory values
  below 64 KiB (load) or 256 KiB (working peak) are raised to that floor
  before a ratio is taken, so negligible memory compares as equal.
- **Status per module** from `python3 rust-cpython/perf.py goals`: two
  independent runs of five alternating-order rounds each. A metric is
  **OVER** when both runs' 95% intervals sit above 1.01x, **BEYOND** when
  both sit below 0.9x, **MET** when the pooled median is at most 1.01x,
  and **UNCLEAR** otherwise. A module takes its worst metric's status and
  is BEYOND only when every metric is. Output mismatches read MISMATCH.
- **Sequencing.** The climb is memory-first. Only load footprint and working
  peak are targeted until every module reads MET or BEYOND on both (or is on
  the debt list); kernel CPU must not regress meanwhile. CPU lanes start
  after that. Up to 8 lanes run concurrently for memory, 4 for CPU.
- **Done for a module** means MET or BEYOND on all three metrics. OVER
  modules are the climb's targets, largest ratio first; UNCLEAR modules get
  more rounds before any lane. A MET module is climbed toward 0.9x only
  after no OVER module remains. Climbing stops on a metric once it is
  BEYOND.
- **Application workloads guard.** The seven baseline-set workloads run as
  guards on every gated step; a module win that regresses a guard is
  rejected. Kernel results are the goal; application results keep it
  honest.
- A route that cannot reach 1.0x after two failed lanes is recorded as
  debt in the ledger. Removing a Rust route to meet a goal needs the
  user's decision; coverage still holds.

## Fast-iteration harness (no PGO, no ThinLTO)

Coverage is complete under the strict suite rule in
[rust-for-cpython.md](rust-for-cpython.md), so this phase opens with a
fast-iteration harness. Both interpreters are built with the same locked
LLVM 23.1.2 compiler, the same `-O2` target flags, and the same macOS SDK;
GIL-enabled; no `--enable-optimizations` (no PGO profile task), no
`--with-lto`, no debug info, and test modules left enabled. `-O2` compiles
markedly faster than `-O3` while staying a fair matched comparison; the
checked-in standard stays there. Anything leaner (notably a Cargo `dev`
profile) is explicitly not comparable. The only deliberate difference
between the two interpreters is the source overlay. The builder is
`rust-cpython/perf.py`; it installs into
`rust-cpython/stage-perf-<name>/` with build trees under
`rust-cpython/work/perf/<name>/`, leaving the coverage `work/build` and
`stage` trees untouched. Timing baselines require an otherwise quiet host:
`perf.py` builds, suites, and profiles share a repository-wide host lease
that its measurements hold exclusively, across every worktree. The
coverage `build.py` does not take the lease; do not run it during the
climb.

- Control `perf-upstream`: the pinned fork source with an empty overlay
  (pristine fork, no Rust overlay crates). The fork source still carries its
  built-in `Modules/_base64` Rust extension and Cargo scaffolding, which
  public `base64` never reached during coverage; that residue is disclosed,
  not hidden. A byte-exact CPython-upstream control at the fork base is a
  later follow-up, not this baseline.
- Candidate `perf-rust`: the same source with the full committed overlay
  applied (all 71 coverage routes).
- Both use Cargo `release` for the compiled Rust members. A `dev` profile
  would punish the Rust routes artificially and is not a performance result.
  Configure selects `dev` whenever `--enable-optimizations` is absent, and
  each Rust extension rule moves its artifact out of the Cargo target
  directory, so a `make install` without the override rebuilds and installs
  `dev` artifacts. `perf.py` passes `CARGO_PROFILE=release
  CARGO_TARGET_DIR=release` to both `make` and `make install`, fails if
  either log shows `--profile dev` or a `debug` Cargo tree exists, and
  proves every installed Rust extension byte-identical to a release
  artifact. Its report records the stage-tree digest, and `bench` refuses a
  stage that changed after its build.

Run repository-owned application workloads first; targeted kernels explain
mechanisms only. The first baseline set on native macOS arm64
(`--local`, `--profile standard`) is `python_startup`,
`serialization_roundtrip`, `zlib_decode_1m`, `gzip_extract_1m`,
`django_wsgi_request`, `django_template_realistic`, and `import_django`:
stdlib-only workloads need no wheelhouse, and the Django workloads use the
committed `benchmarks/inputs.macos-cp316.lock.json` closure. Each run pairs
baseline and candidate invocations on the same host with the controller's
alternating order, keeps wall latency and kernel process-tree CPU from the
uninstrumented timing pass separate from the sampled RSS/physical-footprint
memory pass, and records per-workload noise from repeated rounds plus a
`self-compare` calibration of the control. Allocation tracing stays
unavailable on macOS (unknown, never zero); installed size comes from each
stage prefix. Baselines are checked in with explicit
`--record-baseline benchmarks/baselines/rust-cp316-perf-<workload>.json`
paths; raw run directories stay ignored. Broad pyperformance follows only
after these representative comparisons read clean.

Granularity runs both directions. For module focus, `perf.py test --name
perf-rust --suite test_zlib` runs one CPython suite on a perf build, and
`perf.py bench --baseline @control --candidate @incumbent --workload
zlib_decode_1m` measures one workload; substitute any workload or suite
name. For the whole picture, `perf.py test --name perf-rust --all` runs
every default-resource CPython suite, and `perf.py bench ... --gate
--all-workloads` runs every workload with locked 3.16 inputs. The 3.16
input closure covers Django plus package-free workloads only, so four
registered workloads (`pylint_source`, `pycparser_source`,
`import_app_stack`, `pip_install_wheelhouse`) are unavailable; the
23-workload eligible subset is the entire suite for this lane until those
closures exist. A focused win never overrides a full-suite regression:
judge each workload separately.

## Hill-climbing loop

Codex sessions use the separate
[Codex coordinator](.agents/skills/rust-cpython-perf/SKILL.md) and
[Codex climber](.agents/skills/rust-cpython-perf-climber/SKILL.md), with
`gpt-6.1-sol` at `medium` effort for every agent. The Codex quiet-host helper
is `.agents/skills/rust-cpython-perf/scripts/wait_quiet.py`. The handoff's
pending quiet confirmation and memory-first order apply to both workflows.
The Claude workflow below remains available with its own model policy.

A Sonnet 5.5 coordinator runs the climb with the repository skill
[`.claude/skills/rust-cpython-perf`](.claude/skills/rust-cpython-perf/SKILL.md);
climber subagents (`.claude/agents/rust-perf-climber*.md`, pinned to
`claude-sonnet-5-5` at `high` or `xhigh` effort, each in its own worktree)
follow [`.claude/skills/rust-cpython-perf-climber`](.claude/skills/rust-cpython-perf-climber/SKILL.md).
`perf.py goals` supplies the debt map (OVER modules first). One lane tests
one hypothesis about one module route: profile its kernel, edit,
incremental build, primary suite, and an exploratory bench against the
incumbent; then a clean build, every relevant suite, a gated verdict with
the application guards, and the route's goal row. The coordinator
integrates accepted lanes in batches, runs the full suite and a batch gate
against the incumbent, promotes the batch to `perf-rust`, and re-measures
goals and workloads against the control.

`perf.py bench` decides each attempt in code (`rust-cpython/perf_verdict.py`).
Per module kernel it classifies CPU, load footprint, and working peak, and
per workload wall time and kernel CPU per operation, from the bootstrap
95% interval of the paired candidate/baseline median; workload peak memory
uses the controller's repeatability bound. Each is held to a 1% practical
floor. Outputs that differ from the baseline reject the attempt
(`compileall_source` against the control is the documented marshal byte
difference and is reported instead). A metric is `improved` or `regressed` only when every
independent run agrees, and `unstable` when runs disagree. The decision is
REJECT on any replicated regression, INCONCLUSIVE on an unquiet host
(below 80% CPU idle around the runs, or on battery; `calibrate` proves the threshold on a given host), unstable metrics, or a
gate with one run, ACCEPT on a replicated target improvement, and NEUTRAL
otherwise. `--gate` also requires clean builds of committed overlays, a
challenger containing the incumbent commit, the memory pass, two runs, and
the seven baseline-set workloads as guards. `perf.py calibrate` applies the
same rules to one build against itself; every workload must read neutral
before a session climbs.

### Ledger

One row per integration, maintained by the coordinator. Ratios are
candidate over baseline for the batch targets.

| Date | Commit | Lanes | vs previous incumbent | Goal status vs control |
| --- | --- | --- | --- | --- |
| 2026-09-29 | `59ec0b8` | etree-mem, zstd-mem (memory phase) | Gate ACCEPT, quiet=yes, guards neutral. `xml.etree.ElementTree` cpu 0.313x, load 0.750x, peak 0.250x (all improved). `compression.zstd` cpu 0.934x improved, load 0.721x and peak 0.403x (neutral by interval, points below 1.0). | `xml.etree.ElementTree` OVER: cpu 0.92x MET, load 1.21x OVER (+176 KiB, from `_re_rs`/contextlib imports outside the lane; see `re-mem`), peak 1.34x UNCLEAR. `compression.zstd` OVER: cpu 1.94x OVER (CPU phase), load 1.45x UNCLEAR, peak 0.79x MET; open lead: `_zstd/*.c` runs C libzstd first and Rust on a copy. `goals --min-idle 0`, memory rows only. |
| 2026-09-29 | `3f5846f` | lzma-mem (memory phase) | Gate ACCEPT, quiet=yes, guards neutral. `lzma` load 0.049x (improved), cpu 0.973x and peak 1.000x (neutral). | `lzma` memory MET: load 0.12x BEYOND (4.9 MiB vs 39.8 MiB), peak 1.00x MET; cpu 1.36x OVER (CPU phase: lzma-rust2 match-finder speed). Known limit: decoding streams with an 8 MiB dictionary still touches 8 MiB (crate zero-fills the declared dictionary); the kernel does not exercise it. |
| 2026-09-29 | `b8d3c46` | re-mem, zstd-glue (memory phase) | Gate ACCEPT, quiet=yes, primary path, guards neutral. `re` load 0.035x improved (cpu, peak neutral). `compression.zstd` cpu 0.462x, load 0.501x improved, peak 0.204x neutral. | `re` MET (all three 1.00x). `compression.zstd` MET: cpu 0.90x, load 0.91x, peak 0.48x. `xml.etree.ElementTree` moved to UNCLEAR (load 1.27x, peak 1.19x): the `re` import cost went, a per-dylib floor remains. Lane gate of zstd-glue REJECTed on `import_django` 1.02-1.03x from a worktree build; the primary-path batch gate read neutral (worktree-path bias). |
| 2026-09-29 | `555de63` | bz2-mem, asyncio-mem, ospath-mem (memory phase) | Gate ACCEPT, quiet=yes, primary path, guards neutral. `bz2` load 0.673x. `asyncio` cpu 0.776x, peak 0.516x. `os.path` cpu 0.373x, load 0.269x. | `bz2` UNCLEAR at parity (cpu 1.02x, load 0.99x MET, peak 1.00x MET). `asyncio` OVER: load 1.07x (13 other `_*_rs` dylibs on its import path), peak MET. `os.path` OVER: load 1.70x (136/80 KiB, about one page above control), peak MET. Review item: the bz2 fix serves large zeroed tables without memset (relies on libbz2-rs-sys not reading before writing; MallocScribble runs matched control). |
| 2026-09-29 | `050f06e` | json-mem, tomllib-mem (memory phase) | Gate ACCEPT, quiet=yes, primary path, guards neutral (`gzip_extract_1m` cpu 0.994; the tomllib lane gate's +2.7% there was worktree-path bias). `json` cpu 0.153x, load 0.140x. `tomllib` cpu 0.121x, load 0.050x, peak 0.457x (neutral). | `json` MET: cpu 0.71x BEYOND, load 0.76x, peak 1.00x. `tomllib` UNCLEAR at the floor: cpu 0.07x BEYOND, load 1.24x (224/184 KiB), peak MET. Full `goals` at `050f06e`: OVER 56, UNCLEAR 10, MET 5 (was 63/6/2 at the first baseline). |
| 2026-09-29 | `d84fa9f` | plistlib-mem, zlib-mem (memory phase) | Gate ACCEPT, quiet=yes, primary path, guards neutral. `plistlib` cpu 0.038x, load 0.082x, peak 0.401x (all improved). `zlib` cpu 0.481x, load 0.825x improved, peak 0.327x neutral; `zlib_decode_1m` wall 0.267x and `zlib_stream_4k` wall 0.321x improved. | At `6c153ab`: `plistlib` UNCLEAR at the floor (cpu 0.08x BEYOND, load 0.76x MET, peak 1.09x on 296/256 KiB). `zlib` UNCLEAR at the floor (cpu 0.60x BEYOND, load 1.02x, peak 0.86x MET). The plistlib lane gate REJECTed on `import_django` cpu 1.028 (worktree-path bias); the primary-path batch gate read 1.008 neutral. Intentional plistlib changes: equal XML dict keys share one str; `load()` reads a file object whole; module-level helper names `binascii`/`struct`/`re`/`itertools`/`ParserCreate` no longer exist on `plistlib` (private test helpers resolve via `__getattr__`). `_gzip_rs`, `_zip_rs`, `_zipimport_rs` still use flate2. |
| 2026-09-29 | `6c153ab` | binascii-mem (memory phase) | Gate ACCEPT, quiet=yes, primary path, guards neutral. `binascii` cpu 0.894x, peak 0.414x improved, load 0.818x neutral. `base64` cpu 0.907x improved, load 0.684x and peak 0.309x neutral. | `base64` OVER on cpu only (2.90x; memory MET: load 0.94x, peak 1.00x). `binascii` OVER on cpu (1.67x); load 1.01x UNCLEAR, peak 0.95x MET. Full `goals` at `6c153ab`: OVER 54, UNCLEAR 12, MET 5. Row noise: control working peak swings 16 KiB to 1.7 MiB between runs on some kernels (`shutil`), so UNCLEAR rows get a rigorous rerun before a lane. |
| 2026-09-29 | `358d7cf` | statistics-mem (memory phase) | Gate ACCEPT, quiet=yes, primary path, guards neutral. `statistics` cpu 0.605x improved, load 0.557x and peak 0.668x neutral (points below 1.0). Also confirms the workspace-wide `panic = "abort"` profile (needed for `no_std`): eight modules that import many dylibs read neutral on every metric. | `statistics` UNCLEAR at the floor: cpu 0.08x BEYOND, load 1.03x (744/696 KiB), peak MET. Residual load is `import statistics` loading `_fractions_rs`, `_itertools_rs`, `_bisect_rs`, `_re_rs` (per-dylib cost). Image 408 KiB -> 70 KiB. |
| 2026-09-29 | `a97f52a` | marshal-mem, configparser-mem (memory phase) | Gate ACCEPT, quiet=yes, primary path, guards neutral. `marshal` cpu 0.345x improved, load 0.902x and peak 1.000x neutral. `configparser` cpu 0.175x, load 0.296x, peak 0.856x improved. Public `marshal.dumps` bytes now match pristine CPython (FLAG_REF only on shared/interned objects). | `marshal` UNCLEAR at the floor (cpu 0.88x BEYOND, load 1.05x, peak MET). `configparser` MET (cpu 0.22x BEYOND, load 0.88x, peak 0.87x BEYOND). Full `goals` at `a97f52a`: OVER 52, UNCLEAR 12, MET 7 (63/6/2 at the first baseline). Working peak is MET or near it on nearly every module; the remaining debt is mostly load footprint from other routes' dylibs on each import path. |
| 2026-09-29 | `f7a0121` | zip-mem, glob-mem (memory phase) | Gate INCONCLUSIVE for quiet=no only; every target improved, nothing regressed, guards neutral, full suite ok (originally provisional; quiet confirmed 2026-09-30: load glob0.710x, zipfile0.435x, zipimport0.825x; glob peak0.667x, no guard regressions). `zipfile` cpu 0.497x, load 0.248x; `zipimport` cpu 0.928x, load 0.824x; `glob` cpu 0.514x, load 0.733x, peak 0.697x; `zip_read_wheel` wall 0.574x. | Final `goals`: `zipfile` MET (cpu 0.65x, load 0.51x BEYOND), `zipimport` MET, `glob` UNCLEAR (cpu 0.64x BEYOND, load 1.09x, peak MET). `zipfile` gets its win from lazy imports in `Lib/zipfile` (PEP 810 `lazy import`, `_thread.RLock`); `glob` `_glob_rs` is `no_std` (433 -> 35 KiB) and returns readdir order. |
| 2026-09-29 | `3ce7286` | cf-mem (memory phase) | Gate INCONCLUSIVE for quiet=no only; all three metrics improved (originally provisional; quiet confirmed 2026-09-30: load0.613x, peak0.136x, CPU0.594x, no guard regressions). `concurrent.futures` cpu 0.576x, load 0.508x, peak 0.276x. | `concurrent.futures` MET (cpu 0.72x, load 0.53x BEYOND, peak 0.26x). Cost was per-`Future` bytes from `threading.Condition.__init__` (about 1.7 KB); `_FutureCondition` is lazy (about 520 B) and depends on `threading.Condition` internals. |
| 2026-09-29 | `e41f4fb` | gzip-mem, shlex-mem, urlparse-mem, textwrap-mem (memory phase, final) | Gate INCONCLUSIVE for quiet=no only; every target improved or points below 1.0, nothing regressed, guards neutral (`python_startup` wall 1.237 [1.000,1.289] flagged), full suite ok (originally provisional; quiet confirmed 2026-09-30: load gzip0.765x, shlex0.667x, textwrap0.508x, urllib.parse0.314x; peaks neutral, no guard regressions). `gzip` cpu 0.475x; `shlex` cpu 0.881x, load 0.759x; `textwrap` cpu 0.047x, load 0.488x; `urllib.parse` cpu 0.592x, load 0.333x; `gzip_extract_1m` wall 0.545x. | Full `goals` at `e41f4fb`: **OVER 44, UNCLEAR 17, MET 10** (63/6/2 at the first baseline). `urllib.parse` MET (load 0.51x BEYOND). `gzip`, `textwrap`, `shlex` still UNCLEAR/OVER on load (one to three pages above control: the extension's own dirtied `__DATA` page plus other routes' dylibs on the import path). flate2, adler2, miniz_oxide left the lock. |
| 2026-09-29 | `284fa00` | Codex memory batch 1: fractions, tarfile, random | Primary quiet two-run gate ACCEPT; load **0.750x / 0.875x / 0.762x** improved in both runs, working peaks and all seven workload guards neutral. CPU guard ratios 0.943x / 0.583x / 0.838x improved. Full suite **50,158/2,748**, no failures; clean69 Rust images. | Control goals: fractions load1.21x OVER, tarfile1.12x OVER, random1.00x MET; working peaks MET. Source gate eb026a7; primary path resolves lane startup bias and establishes Random memory win. Baseline refresh deferred to memory completion. |

### Workload picture at `3f5846f` (quiet gate, `@control` vs `@incumbent`, all 23 workloads)

Recorded 2026-09-29 with `--record-baselines`; the baselines under
`benchmarks/baselines/rust-cp316-perf-*.json` now cover every eligible
workload. Peak RSS reads regressed on 21 of 23 workloads (+3% `python_startup`,
+9% to +17% on Django, catalog, and difflib, +32% `zip_read_wheel`), which is
interpreter-wide memory overhead the per-module kernels do not isolate:
imports of Rust routes at startup and first use. CPU/wall regressions to
schedule in the CPU phase: `difflib_unified_mostly_equal` 3.3x cpu,
`zlib_decode_1m` 1.4x cpu / 1.9x wall, `zlib_stream_4k` 1.4x / 2.0x,
`zip_read_wheel` 1.4x / 1.6x, `django_orm_10k` 1.2x cpu / 2.0x wall, `import_django`
1.3x, `zipimport_cold` 1.3x. Improved: `catalog_search_form` 0.42x wall,
`rust_base64_large` 0.61x wall, `catalog_request_path` 0.81x wall,
`gzip_extract_1m` 0.81x wall (but 1.34x cpu). `compileall_source` differs by
design.

## Release-grade confirmation (later)

The fast-iteration harness is the climbing standard. Before claiming a
release-grade result, repeat the key comparisons on matched `-O3` PGO and
ThinLTO builds of both sides, and keep these rules throughout:

- Build matched optimized GIL-enabled interpreters with the same compiler,
  PGO task, ThinLTO, target flags, source revision, and Python dependencies.
  Restore the historical optimized recipe from Git history for that step;
  the coverage builder deliberately exposes only debug builds.
- Run repository-owned complete application workloads first: Django
  WSGI/ASGI/ORM, startup/import, tooling, packaging and archive operations,
  serialization, and multiprocessing. Use targeted kernels only to explain
  mechanisms. Run broad pyperformance only after the representative
  application comparisons.
- Measure wall latency and kernel-accounted process-tree CPU per logical
  unit in an uninstrumented timing pass. Measure peak/retained RSS and
  unique or proportional memory separately. Use a separate allocation pass
  where a suitable tool exists. Missing metrics are unknown, never zero.
- Calibrate control against itself. Pair equivalent control/candidate work
  on the same quiet host, counterbalance order, retain raw observations, and
  report noise intervals. Do not infer CPU use from wall time.
- Check installed Python source and bytecode-cache identity before measuring.
  `PYTHONDONTWRITEBYTECODE=1` blocks writes but still permits existing
  `.pyc` reads; stale caches can dominate startup memory.
- Judge each important workload separately. A global gain does not hide a
  clear regression. Compare native binary size and maintenance cost after
  correctness and resource results.

## Baseline (2026-09-29, macOS arm64, provisional)

**Correction.** The numbers first recorded here (`d41b580`) measured a
candidate whose installed Rust extensions were Cargo `dev` artifacts:
`make install` ran without the release override, rebuilt every Rust member
in `dev`, and installed those (the installed `_json_rs` was byte-identical
to the 1,158,912-byte `dev` artifact, not the 570,096-byte release one).
Its decompression headline (8.7x, "9x to 24x against system zlib") and its
338 MB size figure described unoptimized Rust. Those results and the
`benchmarks/baselines/rust-cp316-perf-*.json` files recorded with them are
superseded; refresh the baselines with the coordinator's gated
`--record-baselines` run.

Verified pair: `perf-upstream` (1 release Rust extension, `_base64`) and
`perf-rust` (70 release Rust extensions, each byte-identical to its release
artifact), both at `d41b580`, -O2, no PGO, no LTO. Installed size: 278.1 MB
to 306.7 MB (+10.3%).

Per-module goals (`perf.py goals`, two runs of five rounds, 833 s): **63
OVER, 6 UNCLEAR, 2 MET** of 71 routes. The host was in interactive use
(67% to 74% CPU idle), so the run is flagged not quiet; rerun on a quiet
host before recording statuses in the ledger.

- CPU: 16 routes are at or under 1.0x. Nine are already BEYOND (below 0.9x):
  `statistics` 0.13x, `shlex` 0.32x, `urllib.parse` 0.37x, `ipaddress`
  0.48x, `tomllib` 0.60x, `tarfile` 0.68x, `codecs` 0.77x, `textwrap`
  0.78x, `importlib.metadata` 0.85x. The largest CPU debts: `decimal`
  5.9x, `functools` 5.0x, `json` 4.7x, `os.path` 4.7x, `sqlite3` 3.9x,
  `bisect` 3.9x, `fractions` 3.3x, `datetime` 3.3x, `base64` 3.2x, `csv`
  3.1x.
- Load footprint: only 6 routes are at or under 1.0x. The largest absolute
  debts: `lzma` +59 MiB (100 MB against 40 MB), `compression.zstd` +12 MiB,
  `plistlib` +5.1 MiB, `bz2` +3.0 MiB, `tomllib` +2.8 MiB, `zlib` +2.4
  MiB, `re` +1.9 MiB, `gzip` +1.3 MiB, `configparser` +1.2 MiB, `json`
  +1.1 MiB; about 107 MiB across all routes.
- Working peak is OVER for `asyncio`, `glob`, `plistlib`, and
  `xml.etree.ElementTree`.

Application workloads: a single exploratory run puts `zlib_decode_1m` at
1.96x wall and 1.37x CPU against the control (not 8.7x). The seven-workload
self-calibration read neutral on every workload and metric. The full gated
workload comparison is pending a quiet host. `compileall_source` output
differs from the control by design (the checklist's marshal note), so it
is reported, not timed, against the control.


## Historical findings

The previous performance-first loop produced many narrow Rust kernels but
**zero fully qualified coverage modules**. The fork's private `_base64`
extension was not reached by public `base64`. Optional URL, TAR, IPv4,
timestamp, UUID, shlex, fraction, zlib, and Base64 routes were partial.
Several showed promising narrow timing results; others had regressions or
unresolved Python semantics. None establishes a practical interpreter-wide
gain. The prior benchmark system is retained under `benchmarks/` for the
production project and eventual performance phase, but it is not part of
the active Rust coverage loop.
