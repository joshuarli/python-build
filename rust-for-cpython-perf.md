# Rust-for-CPython performance phase

**Resumed for memory-only completion; CPU phase not started. Read the current memory-only contract below, then the [latest handoff](#latest-handoff-2026-09-30).** All 71 targets in [rust-for-cpython.md](rust-for-cpython.md)
are complete under its strict Python-suite coverage rule, and those rules
still bind every performance change. The old experiment archive was
removed from the active tree; its detailed reports and raw data remain
recoverable from Git history at commit `f0f8690`.

## Current memory-only resumption (2026-09-30)

The user resumed the handoff and requested achieving all memory goals first,
without checking or gating on CPU or timing performance requirements. This
contract supersedes the historical CPU guards, quiet-host requirements,
module-debt completion exceptions, and stopped-session status below.

- Acceptance targets and guards are module `load_footprint` / `working_peak`
  and application memory, including `peak_rss`. CPU and wall results cannot
  qualify, reject, or delay a memory change. The workload memory-only
  path skips timing rounds and CPU usage prerequisites entirely. Module
  iteration sizing remains unchanged to preserve the measured workload.
- Use the explicit `--memory-only` harness policy for goals, calibration and
  acceptance. Preserve the existing memory samples, floors, independent-run
  replication, output checks, verified clean builds and complete suites.
  Host quietness is not a prerequisite for this memory work.
- Completion requires all 71 modules' two memory goals to read MET or BEYOND
  and every eligible workload's absolute peak RSS to be neutral or improved
  against pristine control. A debt entry records an unresolved goal; it does
  not satisfy that goal. CPU lanes remain out of scope.
- The previous two empty attribution waves and 113 briefs remain historical
  evidence. The renewed run starts a fresh lane budget and progress count;
  revisit rejected candidates only with a distinct mechanism or an identified
  CPU-only rejection now excluded by this contract.

Doctor/status passed on resumption. The verified incumbent remains `7cf55a6`
(clean58, full50,158/2,748) and its overlay matches documentation HEAD
`b43b5d4`; the pristine control remains `7351620`. Fresh full module memory goals read 10 OVER / 16 UNCLEAR / 45 MET or BEYOND.
Memory-only self-calibration `20260930T233108Z` passed: all seven workload
RSS rows neutral in both runs. The fresh absolute workload comparison `20260930T233748Z` reads 16 RSS
regressions, 3 neutral and 4 improved. The explicit decision policy was committed at `e32c713`; the workload runner
now also skips timing and CPU prerequisites at `10a89fe` / `1f3245c`. Its
102 focused tests pass (two platform skips), including a real RSS collection
with CPU records absent and invalid measurement-mode rejection. Corrected
self-calibration `20261001T013533Z` reads all seven RSS rows neutral in both
runs, with host quietness unexamined. No new memory improvement is claimed yet.

### Controlled runtime-prefix memory context (2026-10-01)

A bounded diagnostic used the same verified incumbent binary and the normal
uninstrumented `collections` sampler six times, with explicit `PYTHONHOME`
paths of 55 or 105 ASCII characters. The order was original/short/long,
long/short/original, at 56 iterations. Short paths measured 48–96 KiB load;
the two long paths measured about 128 KiB. Digests matched throughout and
stage fingerprints were unchanged. This establishes sensitivity to the
runtime prefix in this diagnostic; it does not establish the cause of any
historical rejection or a correction amount. The raw report is
`regex-memory/results/prefix-context-attribution/FINDINGS.txt`.

`perf.py bench`, `calibrate`, and `goals` now offer opt-in
`--memory-only --matched-prefix`. Both sides receive distinct temporary
equal-length ASCII home aliases to their verified installations. Module and
application sampling, setup probes, and dependency bytecode preparation use
the selected homes. Self-calibration uses two aliases to the same stage.
The aliases are removed after measurement; verdicts retain the home paths,
and application provenance and compact exports retain requested and observed
prefixes. Harness source hashes are checked across lease acquisition and
sampling and recorded with each verdict. Container runs reject host aliases.
The shared benchmark launcher also strips an ambient `PYTHONHOME` so an
unrelated installation cannot replace the requested interpreter's stdlib.

This is a new measurement context requiring fresh self-calibration and
control/incumbent ground truth. It changes no kernel, iteration-sizing rule,
sample count, floor, memory threshold, or correctness requirement. It does
not control embedded build paths or dynamic-library install names. Natural
prefix runs and their historical REJECT/NEUTRAL decisions remain intact.
No source optimization is accepted by introducing this option.

Harness commit `4cff383` passed 156 benchmark tests (16 platform skips) and
68 Rust harness tests (13 skips), including alias cleanup, same-stage
two-home calibration, environment isolation, identity checks, compact export,
and source-change detection. The broader controller run had 189 tests with
two stale workload-registry expectation failures and one copied-uv-interpreter
relocation fixture error (exit 134). Parent-only registry tests reproduced
the two failures; relocation code and test are unchanged, and the copied
executable's sibling-library dependency is absent from the fixture.
Those controller limitations remain recorded; no formatter, linter, or
commit hook ran.

Fresh matched-prefix memory-only control self-calibration
`20261001T052920Z` passed: all 23 workload RSS rows and `collections` load
and working peak were neutral in both independent runs. Actual observed
prefixes matched both requested 39-character ASCII home aliases; outputs
matched, stage fingerprints held, and the harness source was clean.
Full 71-module control/incumbent ground truth `20261001T053304Z` reads
13 OVER / 10 UNCLEAR / 47 MET / 1 BEYOND. `_strptime` is MET already;
its prepared calendar candidate is held rather than measured. The remaining
OVER routes are datetime, re, threading, decimal, typing, uuid, base64,
tokenize, ipaddress, marshal, inspect and zlib load, and zstd working peak.
The 10 UNCLEAR routes receive the prescribed once-only rigorous classification
pass. Full absolute workload snapshot `20261001T054230Z` reads 15 RSS
regressions / 4 neutral / 4 improved. The regressions include Django,
compileall, startup, multiprocessing, serialization, catalog request/search,
large base64, wheel reading and cold zip import. These are unresolved goals,
not waived by the context change. No CPU, wall, or quiet-host requirement
was checked.

The once-only rigorous follow-up `20261001T054547Z` resolved logging and
binascii as MET, and ElementTree working peak plus pickle, SQLite and socket
load as OVER. SSL, struct, html.parser and warnings remain UNCLEAR.
Combining the latest applicable rows leaves 17 OVER / 4 UNCLEAR /
49 MET / 1 BEYOND; all 21 unresolved routes remain required goals.
New isolated source lanes are `builtin-aggregate-memory` (22 existing
helpers linked through the existing static builtin archive, SQLite excluded,
no linker-flag change) and `regex-corrected-memory` (direct PikeVM plus the
ASCII whitespace correctness repair, with original eligibility limits).
Both must retain every actual module/workload memory guard and full
correctness qualification. The zstd working-peak scout found no distinct
justified edit; bounded allocation attribution is pending. No resumed
source optimization has been integrated.

Corrected PikeVM source `59c2aa8` passed clean58, seven complete suites
(585/129) and 20 native checks, including original parser-depth and cached
pattern lifetime boundaries. Its once-only new-context all-71/all-23
exploration `20261001T060133Z` REJECTed: re load improved to
0.768x [0.732, 0.785], but compileall RSS, email working peak, and fractions,
importlib.resources, statistics and urllib.parse load regressed in both
runs. Warnings load was neutral overall (worse/neutral by independent run).
There were no output mismatches or unstable metrics. Restoration `4d66e8e`
returns the entire owned overlay to the incumbent; the rejected source,
fixtures, patch and artifact remain preserved. No retry or primary
qualification follows.

Builtin registration source `8e40885` has a clean committed build with
36 dynamic Rust extensions and all Rust packages compiled. Its native
proofs match incumbent method inventories, public native-call counts,
digests and own-GIL outcomes for the 22 added helpers plus codecs/itertools.
Fresh-process SQLite image comparison and final initializer/core symbol
proofs pass; all 78 affected suites passed (26,502/1,829). Its once-only
all-71/all-23 exploration `20261001T062024Z` REJECTed: 19 memory rows
improved, including datetime load 0.528x, typing load 0.921x and Django
import RSS 0.987x, but logging working peak 1.696x and startup RSS 1.020x
regressed in both runs. Restoration `8aba152` returns the overlay to the
incumbent. Source, proof scripts, patch and measured artifacts are preserved;
there is no retry or primary qualification.

The bounded same-binary executable-path diagnostic completed six normal
samples with a fixed 39-character home and three later metadata checks.
Launch aliases changed observed `sys.executable` and `_base_executable`;
load samples did not establish a repeatable causal amount. Stage bytes,
inode, outputs, prefixes and stdlib origins matched. The matched-prefix
context controls homes only: actual executable paths remain different.
This diagnostic changes no protocol or historical verdict.

Zstd diagnostic-only source `3ebbd5a` passed clean58, six complete suites
(2,274/178), six diagnostic checks, 1,796 native calls, four recorder
regressions and an isolated staged allocator-reentry fixture. The original
readout deadlock was reproduced before repair; Python allocation and resizing
now occur outside the recorder guard. Exactly one instrumented 61-iteration
trace after two warmups recorded 3,987 events with no drops and matching
digest. Unknown-size decompression grew and shrank output at the same pointer
in all 63 calls, so an output-copy hypothesis is unsupported. All 128 encoder
and 252 decoder creations had matching drops. The observer materially changed
the physical peak; it cannot qualify a memory improvement. The uninstrumented
80–96 KiB zstd excess remains unexplained, and its earlier compileall RSS
rejection remains binding. No resumed source optimization is integrated.

Distinct archive-only source `430e8b9` registers eight helpers: pathlib,
tokenize, pickle, shutil, email, http.client, datetime and typing. Six had
544 KiB resident / 192 KiB dirty mappings in the historical Django scout;
the last two had load improvements in rejected22. This motivates a smaller
group, not a claim that either rejected guard is repaired. Regex and logging
remain separate, and the core keeps its default System allocator. Independent
source review passes; clean50-dynamic release build passed. Installed native
proofs and all 45 complete affected suites passed (15,845/1,214). Its sole
all-71/all-23 exploration `20261001T070008Z` REJECTed with nine replicated
load regressions (collections, configparser, dataclasses, json, logging,
tarfile, urllib.parse, warnings and zipfile) and six RSS regressions
(catalog URL, both difflib workloads, startup, cold zip import and zlib
streaming). Startup was 1.017x and logging load 1.075x. Datetime and typing
load were neutral overall because their improvements did not replicate;
threading load alone improved. Logging working peak was neutral. Outputs
matched and there were no unstable metrics. Restoration `1e82b72` returns
the complete overlay to the incumbent; source, patch, tests, stage and all
94 entity results remain preserved. No retry or primary qualification follows.

Threading core-only and FFI-table grouping scouts closed before source edits
or measurements. Its artifact already contains no retained standard-runtime,
panic or allocator body, and grouping methods leaves three eager GOT bindings
on the separate dirty page. A broader core-only inventory found no other
untested allocation-free helper with an attributable runtime body to remove.
These are negative source/artifact findings, not failed measured candidates.
The legacy `_base64` deferral scout also closed: both actual stages already
ship it as a shared extension, and both base64 workloads explicitly call it.
Its archive dependency does not imply a registered builtin or a loaded core
image cost. Actual original builtin registrations number 12 despite 13
archive dependencies; the eight-helper candidate retains those 12 and adds
eight. No setup change was made to force `_base64` into the core.

Two distinct source lanes follow the bounded evidence. `zstd-flush-memory`
reduces only the flush buffer's initial capacity; the trace established
16 KiB allocations for three-byte results, while the C control starts at
`compressBound(0)` within its inline writer buffer. Earlier writer trials
retained the 16 KiB minimum. `base64-pair-memory` preserves both shared
modules by making the legacy filename a relative alias to the existing
`_binascii_rs` image, which already exports both original initializers.
The two workloads currently import both images; no exact pair-alias trial
was found in the prior history. Neither hypothesis establishes physical
savings yet. Both require unchanged coverage, exact native/API/own-GIL
behavior, clean builds, complete affected suites and all actual memory
guards in a single all-71/all-23 paired exploration. CPU, timing and host
quietness remain excluded from their decisions.

Flush source `6d71ff7` changes only initial capacity to `compress_bound(0)`;
incumbent contracts passed nine native dispatch checks and 24 accepted
allocation faults plus 24 successes across frame/block modes. Block-error
ownership checks drop the failed capsule and exercise a fresh one, without
inventing a reset contract. Pair source `160fe44` changes only Makefile
build/install aliases and scoped documentation. Its eight incumbent native,
API, error, GC, reload, import-order and own-GIL cases passed; the same-file
alias assertion failed before source as intended. Setup inventories already
describe both modules as shared and remain unchanged. Both clean builds are
complete. Pair source passed all eight neighboring suites (4,289/48), both
initializer exports, relative build/install alias identity, native dispatch,
original own-GIL outcomes and unchanged Cargo-byte verification. Its sole
all-71/all-23 exploration `20261001T072209Z` REJECTed: large base64 RSS
0.999x, small RSS 1.007x and both module memory targets were neutral. AST,
asyncio, urllib.parse and zipfile load, logging working peak, catalog URL
RSS and startup RSS regressed in both runs. Outputs matched. Restoration
`7b06a68` returns the overlay to the incumbent, with candidate, patch,
stage and raw results preserved; no retry
or primary qualification follows.

Final flush checkpoint `0da6ebd` retains the same one-line production change
and passed clean58, six complete suites (2,274/178), native/window/own-GIL
parity and both-mode failure ownership. The initial 24-offset fault corpus
was insufficient after extra buffer growth; isolated forwarding allocator
counts establish 25 requests per candidate mode versus 12 per incumbent mode
for the buffered fixture. Every candidate fault ordinal 0–24 and explicit
success at 25 pass; the retained 96-offset corpus covers all requests.
This is correctness evidence, not a memory draw. Its sole all-71/all-23
paired exploration `20261001T073426Z` REJECTed: zstd load 1.009x and
working peak 0.949x were neutral, and every workload RSS row was neutral.
CSV, fnmatch, fractions and urllib.parse load plus email working peak
regressed in both runs. Outputs matched. Restoration `432c82c` returns the
entire overlay to the incumbent; the rejected patch, stage, tests and raw
results remain preserved. No retry or primary qualification follows.

An isolated `typing-name-memory` lane investigates 7,600 temporary Unicode
attribute names per unchanged kernel call, confirmed in the pinned C API.
It caches only three interned names per interpreter, preserving dynamic
lookups, legacy getter dispatch and caller-supplied classinfo. The unpublished
draft review found nested-exec ownership leakage and borrowed traversal
pointers crossing allocating visitor callbacks. Both actual-function
regressions failed on the original draft and pass after repair: nested
initialization releases all six acquired references, and traversal reads
live fields before each visitor. Clear detaches all names before decrementing
references; callbacks retain strong local name references. An empty cache
uses the original lookup during initialization or clear/reinitialization;
invalid partial state raises an explicit error. A native fixture mistook the
valid legacy exec-slot spelling for a missing slot after clearing the cache;
the failing log is retained. Final checkpoint `0306a39` corrects the fixture,
passed clean58 and exact source/initializer verification, all 11 isolated
lifecycle contracts and eight complete suites (2,202/9). Its fixed kernel
confirmed 6,400 Rust calls. Its sole all-71/all-23 paired memory-only
matched-prefix exploration `20261001T080928Z` REJECTed: typing load improved
to 0.874x in both runs, but ten module loads, logging working peak and seven
workload RSS rows regressed in both runs. Outputs matched with no unstable
metrics. Restoration `5188180` returns the entire overlay to the incumbent;
source, fixtures, patch, stage and raw results remain preserved. No retry or
primary qualification follows, and no resumed source improvement is integrated.
Original drafts and failing evidence remain preserved. Its extra unchanged
setup-memory command was cancelled in the lease turnstile before any samples.
Only one changed paired memory comparison will follow final qualification.

Two source-only typing alternatives closed without builds or measurements.
The C `_typing` module is already builtin, so co-locating it with its Rust
helper removes no second shared image; the unchanged C object also requires
hidden core symbols. Deprecated identifier lookup holds an interpreter
identifier mutex across allocating operations, introducing a reentry risk.
Neither supplies a justified replacement for the isolated name-cache trial.

Further source-only scouts closed without candidates. Builtin registration
copying and visible builtin-name objects serve CPython lifecycle and inventory
contracts; no physical writable page is exclusively attributed to them.
Inspect's repeated temporary-name ownership mechanism was already exercised
by its earlier neutral trials, and no distinct physical retention saving is
established. These closures change neither goals nor measured verdicts.

The final natural-prefix calendar checkpoint `b4e4167` clean actual gate
`20261001T045734Z` REJECTed despite improved `_strptime` load (0.939x):
`catalog_request_path` RSS regressed in both runs (1.01124x). Its directed
absolute goals read `_strptime` MET (0.95x load) and `datetime` UNCLEAR
(1.63x load). The SQLite-isolated shared-image exploration
`20261001T044608Z` REJECTed with 27 load regressions and a logging working
peak regression, despite 10 improved and 13 neutral workload RSS rows.
Its six-file experiment was restored to `0acdd91`; the patch and evidence
remain preserved. Neither checkpoint replaces the incumbent.

### Resumed source experiment archive

No resumed source optimization has been integrated. The memory-only harness
and fresh control evidence above are committed; rejected and neutral source
checkpoints remain on isolated branches.

- Typing archive registration `393706e` improved load to 0.935x but raised
  logging working peak to 1.720x. Datetime registration `11ed0a1` was neutral
  on its target and regressed memory guards. Both were reverted; the restored
  shared-recovery branch is `57e379f`.
- Regex checkpoint `fd2bdac` reduced its helper image by 445,520 bytes and
  improved re load to 0.845x, but warnings load regressed to 1.065x.
  Direct PikeVM checkpoint `f83687a` reduced the image by 538,784 bytes;
  complete suites and 12 native regressions pass. Its actual two-run gate
  `20261001T010823Z` REJECTed: re load improved to 0.802x, warnings load
  regressed to 1.103x. Absolute re load remains 1.34x OVER. Both source
  checkpoints are preserved and unaccepted.
- Linker checkpoint `3ce73d3` hides private Rust names and strips unreachable
  code while retaining all unmangled ABI exports. Its image is 1,079,984 bytes
  smaller, but all 23 worktree workload memory rows were neutral. Primary
  source `455dfd7` clean-built all 58 helpers; the full suite passed
  50,158/2,748 after an asyncio-streams failure, a passing focused asyncio
  reproduction, and a full rerun. The first failed log remains preserved.
  All-71-module/all-23-workload primary gate `20261001T004401Z` REJECTed:
  CSV load 1.151x, logging load 1.071x and zipimport load 1.041x regressed
  in both runs. Two workload RSS rows improved, but no module load or
  working target improved. The source branch is preserved and unintegrated.
- Basename checkpoint `81f50cd` removes a discarded path head/tuple. Seven
  native regressions pass, including long-prefix allocations reduced from
  1–2.6 MiB to below 64 KiB, and complete suites pass 476/11. Formal logging
  and os.path memory comparisons were neutral, so no target win is claimed.
- ElementTree completed six distinct trials. One consumed-block trial
  REJECTed; five were neutral, including short attribute/text sharing that
  measurably reduced Python objects. The final actual rigorous two-run
  comparison `20261001T012554Z` read working peak 0.894x neutral because the
  improvement did not replicate. All source experiments were restored.
- Zstd double decoding and native PyBytesWriter were memory-neutral and
  discarded. Allocation-failure probes independently reproduced an existing
  decoder retry-state defect on the incumbent. Correctness-only checkpoint
  `c0c27a8` passes three retained regressions, six complete suites
  (2,274/178), and native/Rust parity. Its earlier lane gate reads all seven
  RSS guards neutral. Corrected-policy goals `20261001T014503Z` still read
  working peak 1.250x UNCLEAR; load is 0.807x BEYOND. Review independently found that reset vectorcall could fail its recursion
  guard before cleanup. The retained regression fails both the incumbent and
  first repair with a one-byte-short retry. Follow-up `5469d65` invokes the
  validated native fastcall directly; six isolated cases and independent
  review pass. Primary source `39f5dfe` clean-built all 58 helpers and passed
  the full 50,158/2,748 suite. Its corrected-path all-23-workload gate
  `20261001T021327Z` REJECTed compileall RSS 1.012x in both runs; zstd memory
  and the other 22 workloads were neutral. The repair remains unintegrated
  while that memory guard is attributed; no memory improvement is claimed.
- Lazy itertools initialization passed 8,293/203 complete-suite tests and
  lifecycle/reentrancy checks, but `20261001T011911Z` REJECTed a serialization
  RSS regression of 1.014x; target memory was neutral. It was reverted.
- Logging basename and emit allocation reductions passed native behavioral
  regressions but formal module memory remained neutral. The final emit
  trial `20261001T012055Z` was neutral and discarded; no target win is claimed.
- Eight Django helper deferrals removed 656 KiB resident / 240 KiB dirty
  mappings in diagnostics, but actual net RSS savings were only 208–336 KiB,
  below the workload floor. Gate `20261001T012610Z` REJECTed argparse,
  shutil and tokenize load regressions. Source `5aa4e4d` is preserved and
  unaccepted; physical mapping removal alone does not qualify it.
- A fresh primary-path unchanged build at `a2cfcaf` still REJECTed memory
  guards in `20261001T011140Z`: logging load and catalog URL, gzip, startup,
  and zlib-decode RSS. Its overlay exactly matches the incumbent. The
  measured drift is preserved without ratio corrections or weaker floors.
- Release codegen-unit consolidation `5e07096` passed clean58, full
  50,158/2,790 and exact current-incumbent skip parity. The all-71/all-23
  gate `20261001T022736Z` REJECTed twelve module-load and three workload-RSS
  regressions; no target improvement qualified. Five control goals still
  read re, datetime, typing and threading OVER, pickle UNCLEAR. The source
  was restored in `533e699`; the rejected checkpoint and raw evidence remain.
- Deferred private SSL error-name dictionaries `ce59916` passed clean58,
  5,712/455 complete-suite tests and 22 native lifecycle/OOM checks. Its
  first exploration was neutral despite pooled load 0.950x. Clean gate
  `20261001T024321Z` REJECTed five workload-RSS regressions; SSL load and
  working peak were neutral. The private dictionaries really disappear,
  but neither that diagnostic nor the pooled estimate qualifies a win.
- Exact first-request attribution finds 28 dynamic Rust helpers retain
  3,264 KiB resident memory. The net staged-image delta is 3,520 KiB in both
  held snapshots, accounting for most of the RSS gap; retained Python pools
  differ by only about 126 KiB with equal arena counts. A packaging-only
  23-helper shared-image trial preserves the five existing no_std helpers
  separately. Clean `bb15fd8` passes full 50,158/2,791 and all alias/state
  checks. Two unchanged setup comparisons REJECTed only load (fractions,
  then concurrent.futures), with working peaks, seven RSS guards and outputs
  neutral; exploration recovery preserves both verdicts and all final guards.
  Two physical attribution repeats find Django native residency lower by
  1,856 KiB and dirty pages by 656 KiB, but single-helper processes retain
  48–96 KiB more native memory. Actual all-71/all-23 gate
  `20261001T034526Z` REJECTed 33 module-load regressions in both runs.
  Working peaks were neutral throughout; all workload RSS rows were neutral
  or improved, including first-request RSS 0.963x and warm Django 0.978–0.980x.
  The broad image remains unaccepted. Eager data/fixup attribution is read-only;
  no smaller partition or initialization rewrite is yet qualified. The six
  eager fixup pages contain mostly compiler metadata; per-helper FFI tables
  own no exclusive page. Saved single-helper snapshots also show an eager
  SQLite dependency (80 KiB resident / 48 KiB dirty), absent from their
  standalone counterparts. The fixed 71-route co-import inventory matches
  every incumbent digest; only SQLite's warmup uses its helper. A fresh
  SQLite-only dependency-isolation variant starts from main with the other
  22 aliases preserved. It has no qualified memory result yet. Existing
  binascii/base64 linker options explain the shared image's missing read-only
  data segment; those options remain unchanged in this variant.
  A bounded collections diagnostic finds no aggregate loaded and equal
  native mapping growth on both sides. Longer embedded paths explain all
  libpython file growth, without establishing extra mapped-page demand.
  First-versus-second malloc page reuse remains unresolved; checkpoint
  instrumentation visibly perturbed its estimator. No guard is corrected.
- An isolated HMAC no_std trial `8ec73ba` starts from an actual 144 KiB
  resident / 32 KiB dirty helper cost. It passes clean58 and five complete
  suites (673/38) and eight native parity/lifetime/allocation checks; its
  smaller image is not a qualified target win. Matched first-call profiles
  show 48 KiB less resident code and unchanged dirty pages. Actual two-run
  comparison `20261001T032815Z` is NEUTRAL: load 0.993x [0.944, 1.034],
  working peak 1.000x and Django RSS 1.006x. No all-23 qualifying gate or
  retry follows; the source checkpoint and evidence remain preserved.
  The absolute candidate goal snapshot is MET, but does not replace incumbent
  goals or establish a source win. Restoration `6d5a593` retains `8ec73ba` in
  history; results/logs/native evidence are archived in the primary results tree.
  Separate regex correctness repair `5b955f1` addresses inherited ASCII
  information-separator whitespace misses, preserving the eligible grammar
  and fallback boundary. Clean58, four complete suites (470/58), thirteen
  native checks and 9,728 exhaustive ASCII comparisons pass; its memory
  lane gate `20261001T030129Z` was NEUTRAL. Primary source `3d6dbd1` passes
  clean58, full 50,158/2,748 and thirteen installed native checks. Primary
  all-71/all-23 gate `20261001T033357Z` REJECTed glob, statistics and zipfile
  load, logging working peak and gzip workload RSS in both runs. The repair
  remains unintegrated; no memory-improvement claim or retry follows.
- The bisect wrapper scout measures a 9,550-byte reachable Python graph,
  while importing its existing C accelerator adds 32 KiB dirty / 64 KiB
  resident memory. No replacement experiment is justified from that cost.
  Runtime probes also find wrapper validation, mutation and reflection
  differences from pristine C behavior. Direct own-GIL `_bisect_rs` import
  fails on the incumbent while public bisect falls back successfully; this
  inherited coverage issue is recorded separately from the memory goals.
- Bounded CSV and marshal scouts found no distinct retained-state mechanism;
  their UNCLEAR/OVER load goals remain unresolved. Multiprocessing framing
  does allocate a temporary native vector for 1,208 small frames across four
  threads; direct final-byte assembly is an isolated experiment with buffer,
  exception and wire-boundary regressions. It passes 1,630/165 complete-suite
  tests and eleven native contracts, and eliminates the confirmed temporary
  allocation. Actual comparison `20261001T040603Z` is NEUTRAL on load, working
  peak and both serialization/pool RSS guards. Its absolute candidate goals
  are MET under preserved floors; no distinct gain qualifies. Source restored,
  recoverable patch and evidence retained; no clean qualification or retry.
- The `_strptime` scout measures 224 KiB physical calendar-import growth on
  the incumbent after locale/re/datetime are loaded. An isolated experiment
  retains localized-name and Rust-parser behavior while deferring calendar's
  full module. Real calendar access, exports, locale overrides and import
  retry are tested. The private alias is stored only after publication;
  deletion before publication and never-observed cold assign/delete history
  follow that explicit lazy lifecycle. No candidate memory win is claimed.
  Incremental candidate passes eighteen isolated contracts and five complete
  suites (1,439/160). Exploration `20261001T040237Z` improves load to 0.939x
  in both runs but REJECTs four workload RSS guards. Short route probes show
  those workloads never load the sole changed module. Clean `684d8d6` passes
  full 50,158/2,791, but an isolated review regression finds that reload leaves
  fake, None or deleted calendar aliases stale. All three cases pass on the
  incumbent and fail on that candidate. Follow-up `b4e4167` binds calendar
  through normal import on explicit reload before rebuilding locale caches;
  cold first import stays lazy. New clean/full/native qualification precedes
  its once-only memory gate. The exploration rejection and uncertain cause
  remain preserved, and no guard is waived.
  Follow-up clean58, full 50,158/2,791 and all nineteen native contracts pass.
  Serial short-temp pathlib/shutil/socket suites match the current incumbent
  at 2,372/738, including all seven path-sensitive socket cases. One extra
  aggregate skip versus the refreshed full incumbent was unenumerated in the
  original log. An approved verbose coverage diagnostic passes 50,158/2,790
  and matches all 2,569 normalized skipped case IDs; reason differences are
  limited to existing path/PID strings. This establishes matching observed
  coverage without replacing the original logs or asserting the transient
  extra skip's cause. Once-only actual memory qualification is queued.
- The old direct-PikeVM warnings rejection remains unaccepted. Corrected
  diagnostics find zero native regex calls and no loaded `_re_rs` during the
  fixed warmup; loaded warning/tokenizer image costs match. A diagnostic
  excess of allocator fragmentation remains unattributed. The initial JSON-
  contaminated observations are labelled invalid. Inspect's prior dis-deferral
  also remains rejected on memory guards; no distinct replacement emerged.

Raw verdicts, failed-suite logs, import attribution and current command IDs
are retained in the ignored results trees and `coordinator-state.json`.
CPU, wall time and host quietness remain outside every memory decision.

## Latest handoff (2026-09-30)

This records the previous wind-down. The current memory-only resumption above
takes precedence over this historical state.
The user requested wind-down with no new work. All qualified changes are
integrated; the already-running final suite completed successfully. No further
lanes, builds or benchmarks are scheduled. Two consecutive memory attribution waves
also integrated no performance change, meeting the coordinator’s no-progress
stop condition. The memory completion condition has **not** passed.

### Integrated and verified

- `6a26a48` records memory batch 8: difflib’s uncolored theme avoids unused
  imports; the argparse definition guard now uses identity without invoking
  user equality. Primary source `d1900a2`, quiet two-run gate
  `20260930T214524Z` ACCEPT: difflib load 0.142x; diff workload RSS 0.947x/0.943x;
  all 23 guards pass. Clean 58 and full 50,158/2,748, zero failures; palette,
  native/interpreter checks and four installed argparse regressions pass.
- `7cf55a6` records the separate HASH lifetime correctness repair
  (`922a5af`, primary source `46d19a3`). All 18 failing Rust lifetime cases
  now pass; the real catalog type-reference delta changed from +4 to zero.
  Primary full 50,158/2,748 and installed native/interpreter probes pass.
  The quiet two-run guard `20260930T223511Z` is NEUTRAL on hashlib and every
  metric of all 23 workloads. It makes no memory-improvement claim.
- `@incumbent` / `perf-rust` is clean-built at `7cf55a6`, with all 58 release
  Rust helpers verified (265s). Final installed lifetime regression:
  three tests/18 cases PASS. Final default-resource full suite: 50,158 run/
  2,748 skipped, zero failures (8m02s; 464 test files OK).
- `@control` / `perf-upstream` remains the verified pristine empty-overlay
  build at `7351620`; its single upstream Rust extension is expected.
  Neither installed alias has a pending reader after the final suite.

The final handoff commit changes documentation only; its overlay matches the
verified `7cf55a6` stage. Keep the recorded build commit distinct from a later
documentation commit when reporting which bytes were tested.

### Evidence and remaining gates

The last full 71-route primary control goals are `20260930T215628Z`, source `d1900a2`,
quiet=yes: overall 41 OVER/8 UNCLEAR/21 MET/1 BEYOND; memory 13 OVER/12 UNCLEAR/
46 MET or BEYOND. Difflib load 0.146x BEYOND and working peak MET; argparse
load 0.812x BEYOND and working peak MET. This full snapshot predates only the
HASH lifetime repair; it is not a fresh goals table for the final build.

The last completed **absolute** all 23-workload control comparison is
`20260930T204927Z` at `a9a80e4`: 19 peak-RSS regressions, three neutral, one
improved. It predates batch 8 and HASH’s repair. The neutral repair guard and
accepted batch gate compare against previous incumbents; neither replaces
that absolute comparison. The planned final absolute comparison and focused
HASH control refresh were deferred at the user’s wind-down request. No new
baseline was recorded. Workload memory debt does not waive phase completion.

Calibration `20260930T174528Z` was CALIBRATION-OK; the next six-hour deadline
was `2026-09-30T23:45:28Z`. Recalibrate at the next session start as the skill
requires. Results/logs and `rust-cpython/results/coordinator-state.json` are
local ignored evidence; source changes, regression tests and the ledger are
committed. All lane worktrees have been removed, `perf-merge` is cleaned, and
rejected unmerged branches needed for findings are preserved. Last disk check:
568GiB free. The run used 113 lane briefs, below the 150 limit, with up to eight
memory lanes; all delegated agents used GPT-6.1 Sol at medium effort.

### Resume in this order

1. Read `.agents/skills/rust-cpython-perf/SKILL.md` and the climber skill.
   Only `gpt-6.1-sol` at `medium` is authorized. Keep the separate Claude
   skills intact. Use `uv run --no-project --offline --python 3.14 python`
   as the controller, and `perf.py` or `perf.host_lease` for every execution.
2. Run doctor/status and reconcile local state. Keep the locked Xcode 27.0
   (`27A266a`), SDK 27.0, LLVM 23.1.2 and Rust nightly 2026-09-15; the macOS
   deployment floor remains 26.0. Do not change product 3.14.6 or frozen Linux.
   Follow the skill’s rebuild/full-suite rules if stages or commit bindings
   need refreshing; current verified bytes are recorded above.
3. Calibrate against `@control`, then refresh full 71-route goals with `--min-idle 0`
   and the absolute all 23-workload `@control` versus `@incumbent` gate, including
   hashlib. Inspect actual outputs before dependent work. Do not record
   baselines or start CPU lanes while the memory completion gate is open.
4. Use the findings below and the module/workload tables to choose a distinct
   measured memory hypothesis. Avoid repeating discarded image flags,
   allocator reservations or regex clones without a new owned mechanism.
   Keep memory lanes filled up to eight (2 build jobs each), without waiting for a
   quiet host during exploration. Preserve CPU and workload regression guards.

The unresolved module debts and attribution findings are recorded below.
Some routes not on the debt list still have OVER or UNCLEAR memory rows; the
no-progress stop is not a claim that all module goals have been met. The
previously recorded zlib EOF-flush `unconsumed_tail` correctness finding also
remains open; no fix was attempted during this wind-down.

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

Fnmatch and tempfile have now integrated in the second Codex batch. Bisect's final memory gate was NEUTRAL despite its exploratory gain;
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
must continue reaching Rust. The current eight memory lanes target ast, threading, statistics, logging,
ipaddress, configparser, subprocess, and difflib. Regex eligibility and
strptime have qualified candidates awaiting primary-path judgment. Durable live lane state is in
`rust-cpython/results/coordinator-state.json` (ignored).

### Second accepted Codex memory batch

The primary batch integrates fnmatch, tempfile, argparse, and functools.
The corrected-boundary quiet two-run gate accepts load ratios **0.320x**,
**0.359x**, **0.966x**, and **0.846x**, respectively, with improvements in
both runs. Working peaks and all seven workload guards are neutral; no
output mismatch or regression occurs. The clean build verifies 69 Rust
extension images; the full suite passes **50,158/2,748**, zero failures.
Resources improves load to 0.849x as a cross-module guard and now reaches
memory MET against control (0.91x). Fnmatch and tempfile reach BEYOND on
load (0.39x/0.40x); argparse and functools remain OVER (1.16x/1.20x).
All five working peaks are MET. CPU remains a guard, not the phase target.

Evidence: `20260930T052640Z-perf-rust-vs-perf-merge/verdict.json` and
`20260930T053642Z-goals-perf-upstream-vs-perf-merge/verdict.json`, under
`rust-cpython/results/perf-bench/`. The build/gate source is `98c5362`;
subsequent commits before integration change documentation only. UUID's
memory improvement did not replicate under the corrected boundary; the
original decimal candidate also failed primary memory confirmation. Both
were reverted and their branches preserved. The separate decimal capsule
lane improved CPU, but neutral memory and a zlib CPU guard regression
prevented acceptance; decimal is now on memory debt after two failed lanes.

### Third accepted Codex memory batch

The primary source `868fb4f` passes the quiet two-run gate at
`20260930T102043Z-perf-rust-vs-perf-merge/verdict.json`. Load footprint
improves in both runs for `_strptime` **0.914x**, fractions **0.922x**,
logging **0.540x**, statistics **0.517x**, subprocess **0.873x**, and
warnings **0.953x**. Logging working peak also improves **0.554x**;
other working peaks are neutral. All seven workload guards are neutral,
with matching outputs and no replicated regression or unstable metric.
The clean build verifies 69 extensions; the full suite passes
**50,158/2,748**, zero failures, and fresh native and own-GIL probes pass.

The batch combines borrowed Unicode and bounded buffers in `_strptime`,
regex eligibility before native helper loading, and deferred logging,
statistics, and subprocess dependencies. The regex and date parser changes
qualify together; their standalone neutral trials remain preserved and do
not establish independent memory wins. An intermediate batch at `59f2f08`
was rejected for startup RSS **1.012x** in both runs. Its static threading
change was reverted before this accepted trial; attribution of that
regression remains unproven. Fresh absolute control goals at `bd886d2`
put statistics load at 0.640x BEYOND and subprocess at 0.951x MET.
Logging load is 0.632x BEYOND, but working peak remains 1.728x OVER;
asyncio working peak also remains OVER. The table below records the full
refresh, including the corrected tokenize kernel.

### Fourth accepted Codex memory batch

The final primary source `2fd93ca` passes the quiet two-run gate at
`20260930T134302Z-perf-rust-vs-perf-merge/verdict.json`, covering sixteen
module kernels and all 23 workloads. Load footprint improves for difflib
**0.909x**, pathlib **0.406x**, tarfile **0.739x**, asyncio **0.888x**,
bisect **0.571x**, contextlib **0.970x**, logging **0.937x**, tempfile
**0.875x**, and typing **0.961x**. Asyncio working peak improves
**0.333x**. No metric has a replicated regression, unstable verdict, or
output mismatch. The clean build verifies 58 shared Rust extensions; the
full suite passes **50,158/2,748**, zero failures. Fresh public Rust calls,
SSL capsule calls, and exact independent-GIL capability comparisons pass.

Difflib reuses the existing position dictionary and removes duplicate token
caches. Its Rust matching uses fallible CPython-owned buffers and a local
`no_std` boundary, preserving legacy conversion and mutation ordering.
Difflib, pathlib, and tarfile also defer unused import closures. Eleven
other unchanged helpers use the existing Rust archive. Logging and typing remain shared:
the first trial at `1750f34` was rejected for logging working peak **1.083x**;
the second at `acb5668` was rejected for typing CPU **1.033x**. Both rejected
gates and their source/build/test evidence are preserved. Restoring these
registrations precedes this accepted trial; that sequence does not establish
which layout caused each earlier regression. Absolute control refreshes for
this new source are pending; the full module table below describes the
previous `bd886d2` incumbent.

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
No overlay source or CPython test was changed by this correction. The current goal table below now uses a complete corrected-boundary refresh
at the accepted incumbent.

### Tokenize kernel reachability correction

The old tokenize kernel made one unsuccessful Rust scanner call and then
produced all 6,600 tokens through fallback. A staged regression failed on
zero successful native classifications. The corrected kernel retains that
function-definition workload and adds 64 simple assignment lines within the
native buffering limits. All six route/boundary checks pass; pristine control
and the accepted Rust candidate both return `(6600, "\n", 385, "2")`.
This is a separate measuring-stick correction, not a memory optimization.
The tokenize goal row below is historical until refreshed with this kernel.

### Memory lane findings after the full refresh

Contextlib and typing each completed a second unsuccessful memory lane:
combining their native images into the existing Rust static archive left
load and working peak neutral. Both are on the memory debt list, alongside
decimal and codecs; this does not waive the workload memory completion gate.
Inspect's six-attempt lane ended with neutral memory despite a CPU win;
ElementTree's six attempts likewise produced no replicated memory gain.
Their source branches and ignored evidence are retained, with no new acceptance.
UUID and socket also finished second unsuccessful memory lanes and join the
module debt list. Marshal remains OVER after an unchanged preparation lane:
no retained native tables were found; its image footprint needs separate
attribution before another patch. Zlib's large-allocation mapping experiment
improved load but introduced working peak OVER against control, so it was
discarded. A separate pre-existing zlib correctness finding remains open:
limited decoding followed by EOF flush clears `unconsumed_tail` in Rust,
where pristine C retains the trailing bytes. The mapping did not cause it.
The fresh full table exposes logging working peak at 1.82x OVER and
compression.zstd working peak at 1.25x OVER; the memory phase remains open.

### Corrected regex search kernel

Commit `70d1187` retains the original six compiled-pattern searches and adds
module-level searches over the same 1,031 input lines. Previously the kernel
compiled through Rust but searched through C `Pattern.search` only. The owned
regression failed first with zero Rust search calls; all seven route tests
now pass, including native matches, misses, and unsupported-pattern fallback.
Pristine control and incumbent produce identical two-list results. The `re`
row in the current full goal table now includes native searches: load1.76x
OVER and working peak MET. Four retained-expression/parser experiments
produced no qualified memory patch; pool attribution found only 2,880 bytes
of potential retained savings. Own-GIL public tests used the C fallback,
so they provide no Rust concurrency evidence.

### Current module memory goal table

Fresh full 71-route measurements at `20260930T231721Z` compare the verified
`7cf55a6` incumbent with pristine `7351620`. The command began before the
explicit harness policy was integrated; the table below reclassifies its
unchanged raw memory evidence with `goal_status(memory_only=True)`. CPU rows
are excluded. Memory counts are **10 OVER, 16 UNCLEAR, 44 MET, 1 BEYOND**.
Memory-only self-calibration `20260930T233108Z` passed with all seven workload
RSS rows neutral in both runs; no candidate acceptance is claimed.
Historical failed hypotheses remain findings, not completed goals.

| Route | Load footprint | Working peak | Memory status |
| --- | --- | --- | --- |
| `_strptime` | 1.019x UNCLEAR | 1.000x MET | UNCLEAR |
| `argparse` | 0.784x BEYOND | 1.000x MET | MET |
| `ast` | 0.718x BEYOND | 1.000x MET | MET |
| `asyncio` | 0.924x MET | 1.000x MET | MET |
| `base64` | 1.113x UNCLEAR | 1.000x MET | UNCLEAR |
| `binascii` | 1.000x MET | 1.000x MET | MET |
| `bisect` | 1.125x UNCLEAR | 1.000x MET | UNCLEAR |
| `bz2` | 0.995x MET | 1.000x MET | MET |
| `codecs` | 0.991x MET | 1.000x MET | MET |
| `collections` | 1.000x MET | 1.000x MET | MET |
| `compression.zstd` | 0.800x BEYOND | 1.250x OVER | OVER |
| `concurrent.futures` | 0.472x BEYOND | 1.000x MET | MET |
| `configparser` | 0.556x BEYOND | 0.721x BEYOND | BEYOND |
| `contextlib` | 1.009x MET | 1.000x MET | MET |
| `csv` | 1.019x UNCLEAR | 1.000x MET | UNCLEAR |
| `dataclasses` | 0.899x MET | 0.564x BEYOND | MET |
| `datetime` | 1.750x OVER | 1.000x MET | OVER |
| `decimal` | 1.220x UNCLEAR | 1.000x MET | UNCLEAR |
| `difflib` | 0.135x BEYOND | 1.000x MET | MET |
| `email` | 0.906x MET | 0.890x MET | MET |
| `fnmatch` | 0.378x BEYOND | 1.000x MET | MET |
| `fractions` | 0.980x MET | 1.000x MET | MET |
| `functools` | 1.000x MET | 1.000x MET | MET |
| `glob` | 0.325x BEYOND | 1.000x MET | MET |
| `gzip` | 0.762x BEYOND | 1.000x MET | MET |
| `hashlib` | 1.013x UNCLEAR | 1.000x MET | UNCLEAR |
| `heapq` | 1.000x MET | 1.000x MET | MET |
| `hmac` | 1.018x UNCLEAR | 1.000x MET | UNCLEAR |
| `html.parser` | 1.010x UNCLEAR | 1.000x MET | UNCLEAR |
| `http.client` | 0.994x MET | 1.000x MET | MET |
| `importlib.metadata` | 0.866x BEYOND | 1.000x MET | MET |
| `importlib.resources` | 0.842x BEYOND | 1.000x MET | MET |
| `inspect` | 1.017x UNCLEAR | 1.000x MET | UNCLEAR |
| `io` | 1.003x MET | 1.000x MET | MET |
| `ipaddress` | 1.025x UNCLEAR | 1.000x MET | UNCLEAR |
| `itertools` | 1.000x MET | 1.000x MET | MET |
| `json` | 0.909x MET | 1.000x MET | MET |
| `logging` | 0.588x BEYOND | 1.036x UNCLEAR | UNCLEAR |
| `lzma` | 0.110x BEYOND | 1.000x MET | MET |
| `marshal` | 1.039x OVER | 1.000x MET | OVER |
| `multiprocessing` | 0.915x MET | 1.063x UNCLEAR | UNCLEAR |
| `os.path` | 1.000x MET | 1.000x MET | MET |
| `pathlib` | 0.594x BEYOND | 1.000x MET | MET |
| `pickle` | 1.069x OVER | 1.000x MET | OVER |
| `plistlib` | 0.231x BEYOND | 0.943x MET | MET |
| `random` | 0.900x MET | 1.000x MET | MET |
| `re` | 1.691x OVER | 1.000x MET | OVER |
| `shlex` | 0.459x BEYOND | 1.000x MET | MET |
| `shutil` | 0.822x BEYOND | 1.000x MET | MET |
| `socket` | 1.036x OVER | 1.000x MET | OVER |
| `sqlite3` | 1.040x UNCLEAR | 1.000x MET | UNCLEAR |
| `ssl` | 1.029x UNCLEAR | 1.000x MET | UNCLEAR |
| `statistics` | 0.574x BEYOND | 1.000x MET | MET |
| `struct` | 1.005x MET | 1.000x MET | MET |
| `subprocess` | 0.902x MET | 1.000x MET | MET |
| `tarfile` | 0.825x BEYOND | 1.000x MET | MET |
| `tempfile` | 0.326x BEYOND | 1.000x MET | MET |
| `textwrap` | 0.092x BEYOND | 1.000x MET | MET |
| `threading` | 1.600x OVER | 1.000x MET | OVER |
| `tokenize` | 1.055x OVER | 1.000x MET | OVER |
| `tomllib` | 0.083x BEYOND | 1.000x MET | MET |
| `typing` | 1.179x OVER | 1.000x MET | OVER |
| `unicodedata` | 1.000x MET | 1.000x MET | MET |
| `urllib.parse` | 0.411x BEYOND | 1.000x MET | MET |
| `urllib.request` | 0.916x MET | 1.000x MET | MET |
| `uuid` | 1.133x UNCLEAR | 1.000x MET | UNCLEAR |
| `warnings` | 0.987x MET | 1.000x MET | MET |
| `xml.etree.ElementTree` | 0.985x MET | 1.219x UNCLEAR | UNCLEAR |
| `zipfile` | 0.304x BEYOND | 1.000x MET | MET |
| `zipimport` | 0.550x BEYOND | 1.000x MET | MET |
| `zlib` | 1.031x OVER | 1.000x MET | OVER |

### Focused goals after memory batch 5

Quiet two-run primary measurements at source `4b76f58`
(`20260930T162057Z-goals-perf-upstream-vs-perf-merge`):

| Route | CPU | Load footprint | Working peak |
| --- | --- | --- | --- |
| `ast` | 1.37x OVER | 0.73x BEYOND | 1.00x MET |
| `shlex` | 0.29x BEYOND | 0.44x BEYOND | 1.00x MET |
| `configparser` | 0.22x BEYOND | 0.57x BEYOND | 0.71x BEYOND |
| `logging` | 0.99x MET | 0.60x BEYOND | 1.50x UNCLEAR |

The single rigorous logging follow-up at `20260930T162859Z` remained
UNCLEAR at 1.29x; treat it as OVER under the greater-than-1.01x rule.
No further uncertainty reruns are authorized. The full 71-route table above
remains the explicitly dated earlier snapshot.
Configparser shares mortal section names and values, preserves custom
proxy lookup behavior, and explicitly supports independent GILs. Distinct
parse/discard diagnostics retained 207,552 bytes of intern-table capacity;
strings themselves were released and candidate physical memory stayed below
control throughout that diagnostic. This is retained table capacity, not a
claim that all interning storage disappears on parser destruction.

### Memory follow-ups after batch 6

The full table remains the single `0628c7b` snapshot. Directed follow-ups
resolve its UNCLEAR memory rows without repeated draws:

| Route | Metric | Follow-up ratio | Raw status | Treatment |
| --- | --- | --- | --- | --- |
| `pickle` | load | 1.065x | OVER | OVER |
| `marshal` | load | 1.025x | UNCLEAR | OVER under greater-than-1.01x rule |
| `functools` | load | 1.071x | OVER | OVER |
| `ssl` | load | 1.050x | OVER | OVER |
| `xml.etree.ElementTree` | working peak | 1.281x | UNCLEAR | OVER under greater-than-1.01x rule |
| `shutil` | working peak | 0.735x | MET | MET; lane closed |
| `plistlib` | working peak | 1.000x | MET | MET; lane closed |
| `collections` | load | 1.250x | UNCLEAR | OVER under greater-than-1.01x rule |
| `hashlib` | load | 1.008x | MET | MET; lane closed |
| `struct` | load | 1.0105x | UNCLEAR | OVER under greater-than-1.01x rule |
| `sqlite3` | load | 1.058x | OVER | OVER |
| `csv` | load | 1.037x | UNCLEAR | OVER under greater-than-1.01x rule |
| `binascii` | load | 1.019x | UNCLEAR | OVER under greater-than-1.01x rule |

Pickle, marshal, functools, ElementTree and shutil used the rigorous profile.
SSL's sole follow-up used the standard two-run profile and formally read
OVER; that profile deviation is preserved, with no additional unchanged draw.
Logging's previous rigorous follow-up remains OVER by the uncertainty rule;
its fresh attribution found equal live StringIO and message/record storage.
No allocation-only claim substitutes for an actual memory improvement.

Closed attribution found no new avoidable retained Rust allocation in
ipaddress, pickle or marshal. The proposed functools CacheInfo deferral was
closed because ordinary cached imports would change fresh/reloaded class
identity. A six-helper serialization consolidation reduced observed native
resident/dirty mappings by 336/144 KiB, but its single actual workload explore
read peak RSS0.987x neutral; the source experiment was discarded. Optional
local-symbol stripping likewise reduced native residency but remained startup
RSS neutral and is not adopted. Own-GIL regex public tests exercised the C
fallback, not Rust concurrency.

### Batch 7: argparse validation footprint

The primary clean `68cfb97` build passed all 50,158 tests (2,748 skipped,
zero failures), followed by native dispatch, own-GIL fallback, custom formatter,
and terminal-width help parity checks. Its quiet two-run primary gate
`20260930T202154Z` accepted argparse load **0.709x** versus `0628c7b`;
kernel CPU and working peak remained neutral. Fourteen of the 23 workloads
showed replicated RSS improvements, with every regression guard passing.
Built-in argument validation now uses an explicit width, avoiding the
terminal-size import closure; custom formatters and rendered help keep their
normal width behavior. Fresh primary control goals `20260930T203106Z` read
load **0.81x BEYOND**, working peak **1.00x MET**, and CPU **2.28x OVER**.
CPU remains outside the active memory phase.

The later inspect disassembly-deferral experiment reduced load to 0.871x,
but its all-workload gate regressed compileall wall time and two RSS rows;
it was rejected and reverted. ElementTree's bounded serializer reserve growth
regressed CPU and was discarded, completing its second unsuccessful memory
lane and adding it to module memory debt. SSL's lazy-base64 experiment was
neutral and discarded. The shared itertools attribution found no physical
import cost in its already built-in helper; validated native counters showed
its callbacks unused by the affected kernels. These findings change no
coverage routes or regression thresholds.

### Batch 8: difflib footprint and argparse definition repair

Difflib `73141db` passed a clean build, complete suites (1,696 run/16 skipped,
zero failures), and native/palette/interpreter-boundary checks. Its quiet
all-workload two-run lane gate `20260930T211406Z` accepted load0.150x and
both diff workloads' RSS0.941x/0.940x versus `a9a80e4`, with every remaining
guard neutral. Lane control goals read load0.159x BEYOND and working peak MET.
The primary clean build at `d1900a2` verified all 58 helpers; the full suite
passed 50,158 tests with 2,748 skips and zero failures. The quiet primary
two-run gate `20260930T214524Z` ACCEPTed difflib load0.142x and diff workload
RSS0.947x/0.943x. All 23 workload regression guards pass; argparse CPU, load
and working peak are neutral. Primary palette/native/interpreter checks and
four installed-stage argparse regression tests pass.

The accepted argparse definition guard could invoke a user-defined equality
method on a monkeypatched docstring and fail parser construction. The smallest
isolated regression fails before the repair and passes against pristine CPython.
The `9eb81f2` repair checks definition size, key presence and value identity;
four staged regression tests, all seven complete suites (2,672/145, zero
failures), and native/help/custom-formatter/interpreter checks pass. It makes
no additional performance claim and passed the combined primary gate.

Collections, struct and SQLite linker experiments each removed a real dirty
metadata page but remained neutral on actual module memory. CSV's smaller
writer buffer improved CPU alone and was discarded. Regex's initialized
metadata cannot fit one fewer page. All experiments were reverted; no page
count or CPU-only result substitutes for a replicated memory improvement.
The subsequent shared-image upper bound is 384 KiB across Django processes,
below its approximately 758 KiB RSS floor, and startup loads no dynamic helper.
Workload attribution continues with no change to the completion condition.

### HASH heap-type lifetime repair

The final catalog attribution lane found no accumulating native state or
physical pages, but four context destructions leaked four references to the
Rust heap type. The isolated regression reproduced this across all six
supported algorithms: ordinary and copied contexts each leaked one reference,
and 32 repeated contexts leaked 32. Pristine CPython passed all 18 cases.

The `922a5af` repair saves the heap type before freeing the native state and
object, then releases the reference owned by generic allocation. It preserves
the existing immutable, non-GC, non-subclassable type and allocator pairing.
The clean lane verified 58 helpers, passed 673 focused tests/38 skips, and
passed all 18 staged lifetime cases, public/native methods, copy, errors and
interpreter-capability parity. The actual catalog probe now has zero type
reference growth. The primary `46d19a3` clean build and full suite passed
50,158/2,748 with zero failures; the same installed-stage probes passed.
The quiet two-run primary guard `20260930T223511Z` is NEUTRAL: hashlib
CPU1.000x/load1.010x/working1.000x and every metric across all 23 workload
guards are neutral, with no mismatch or instability. This is a correctness
repair, with no memory-improvement claim.

### Final memory attribution waves

Two consecutive attribution batches integrated no memory optimization. The
first covered shared native pages, compileall/marshal, first-request/typing,
zipimport, serialization/pickle, multiprocessing and logging. Pickle's bounded
fallback reservation removed a measured 32 KiB temporary allocation, but its
actual workload memory remained neutral and the trial was discarded.

The second covered catalog/hashlib, catalog/URL parsing, pool/threading,
compileall/I/O, first-request/regex, startup/codecs and ORM/SQLite/decimal.
Owned buffers, caches, contexts and native routes were measured against the
actual application fixtures. No distinct removable owned physical cost was
established. Decimal's Rust helper, pool threading's Rust helper and the public
marshal helper were not reached by their assigned application workloads.
The earlier pool observer introduced its own Barrier helper; that diagnostic
artifact is corrected, while the actual native-frame lifetime evidence remains.
Regex retained only two engines; its clone mechanism repeated an already
closed attempt. Broader allocator and libpython mapping gaps remain unattributed.
The separately discovered HASH lifetime repair does not count as a memory win.

Module memory debts after two unsuccessful lanes include codecs, decimal,
contextlib, typing, socket, UUID, threading, warnings, base64, datetime,
ipaddress, marshal, ElementTree, regex, pickle, multiprocessing, logging,
SQLite and compression.zstd working peak. These findings do not waive workload
RSS requirements. Remaining module rows and the full workload comparison stay
visible below; CPU work has not started.

### Latest completed absolute workload memory comparison

Fresh replicated primary control comparison at `7cf55a6`, evidence
`20260930T233748Z`, uses the explicit memory-only policy: **16 RSS regressions,
3 neutral, 4 improved** across all 23 workloads. Host quietness is not checked;
CPU and wall results are excluded. The decision is REJECT for the outstanding
absolute memory debt, not for a newly proposed optimization. No output mismatch
or unstable memory metric was observed. This replaces the older `a9a80e4`
absolute memory picture; no baseline files were refreshed.

| Workload | Peak RSS | Memory verdict |
| --- | --- | --- |
| `catalog_json_export` | 0.989x | neutral |
| `catalog_request_path` | 1.034x | regressed |
| `catalog_search_form` | 1.020x | regressed |
| `catalog_url_normalize` | 1.010x | neutral |
| `compileall_source` | 1.072x | regressed |
| `difflib_unified_mostly_equal` | 0.949x | improved |
| `difflib_unified_reordered` | 0.951x | improved |
| `django_asgi_request` | 1.050x | regressed |
| `django_orm_10k` | 1.048x | regressed |
| `django_template_realistic` | 1.048x | regressed |
| `django_wsgi_first_request` | 1.083x | regressed |
| `django_wsgi_request` | 1.050x | regressed |
| `gzip_extract_1m` | 0.981x | improved |
| `import_django` | 1.051x | regressed |
| `multiprocess_pool` | 1.023x | regressed |
| `python_startup` | 1.019x | regressed |
| `rust_base64_large` | 1.016x | regressed |
| `rust_base64_small` | 1.000x | neutral |
| `serialization_roundtrip` | 1.033x | regressed |
| `zip_read_wheel` | 1.018x | regressed |
| `zipimport_cold` | 1.058x | regressed |
| `zlib_decode_1m` | 0.930x | improved |
| `zlib_stream_4k` | 1.016x | regressed |

Candidate acceptance must compare against the qualified incumbent, retain
replicated memory guards and output checks, and pass complete suites. The
memory phase remains open until all module memory goals and every workload's
absolute peak RSS pass; debt entries do not waive completion.

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
  shared `Modules/_base64` Rust extension and Cargo scaffolding, which
  public `base64` never reached during coverage; that residue is disclosed,
  not hidden. Both base64 application workloads explicitly call the private
  extension. Actual control and incumbent generated tables omit its builtin
  initializer, and both stages contain its shared library. A byte-exact
  CPython-upstream control at the fork base is a
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
| 2026-09-30 | `98c5362` (source) | Codex memory batch 2: fnmatch, tempfile, argparse, functools | Corrected-boundary primary quiet two-run gate ACCEPT; load **0.320x / 0.359x / 0.966x / 0.846x** improved both runs; working peaks and all seven workload guards neutral. Full suite **50,158/2,748**, zero failures; clean69 images. Resources guard load0.849x improved. | Control memory goals: fnmatch0.39x BEYOND, tempfile0.40x BEYOND, argparse1.16x OVER, functools1.20x OVER; resources0.91x MET, working peaks MET. UUID and decimal predecessors reverted after failed primary memory replication; no CPU-only candidate accepted. |
| 2026-09-30 | `868fb4f` (source) | Codex memory batch 3: logging, statistics, subprocess, date parser and regex eligibility | Quiet two-run primary ACCEPT: load0.540x/0.517x/0.873x/0.914x; fractions0.922x and warnings0.953x cross-module wins. Logging working0.554x; other peaks and all seven workload guards neutral. Full50,158/2,748, zero failures; clean69. | Absolute refresh at bd886d2: statistics load BEYOND, subprocess load MET, logging load BEYOND but working peak OVER. Intermediate startup RSS rejection retained; threading static change reverted. Date parser and regex changes qualify jointly. |
| 2026-09-30 | `2fd93ca` (source) | Codex memory batch 4: difflib, pathlib, tarfile and eleven shared-image registrations | Quiet primary two-run ACCEPT over sixteen modules/all23 workloads: load difflib0.909x, pathlib0.406x, tarfile0.739x, asyncio0.888x, bisect0.571x, contextlib0.970x, logging0.937x, tempfile0.875x, typing0.961x; asyncio working0.333x. No replicated regression/unstable/mismatch. Full50,158/2,748, zero failures; clean58; native/GIL probes pass. | Absolute refresh pending. Logging peak and typing CPU rejected trials retained; both helpers remain shared. |
| 2026-09-30 | `4b76f58` (source) | Codex memory batch 5: AST, shlex, configparser | Quiet primary two-run ACCEPT over twelve modules/all23 workloads: load AST0.701x, shlex0.402x, configparser0.519x; configparser working0.910x. Logging cross-route load0.945x; its working peak and typing CPU neutral. No replicated regression/unstable/mismatch. Full50,158/2,748, zero failures; clean58; fresh native/capsule/GIL and configparser ownership/override probes pass. | Control memory: AST0.73x BEYOND, shlex0.44x BEYOND, configparser0.57x/peak0.71x BEYOND. Five additional shared-image registrations dropped after rejected logging peak/typing CPU trial; no causal attribution. Absolute all23 picture remains dated AEC and memory phase stays open. |
| 2026-09-30 | `49e61fe` (source) | Codex memory batch 6: dataclasses, inspect | Quiet primary two-run ACCEPT (`20260930T181726Z`) over six modules/all23 workloads: dataclasses load0.872x and working0.561x; inspect load0.973x, both improved. CPU and every application guard neutral; no mismatch or unstable metric. Full50,158/2,748, zero failures; clean58. Fresh dataclasses exception/concurrency/recursion/slot/subinterpreter checks and inspect native binding/member calls pass; inspect own-GIL uses its existing Python fallback. | Fresh full71 control memory: dataclasses load0.95x MET/peak0.56x BEYOND; inspect load1.03x OVER/peakMET. New incumbent clean58/full50,158/2,748 passes. Worktree Django wall rejections are retained; primary gate establishes acceptance. Workload RSS is now eligible as a target, with existing floors, replication and regression guards unchanged (30 controller tests pass). Memory phase stays open. |
| 2026-09-30 | `68cfb97` (source) | Codex memory batch 7: argparse | Quiet primary two-run ACCEPT (`20260930T202154Z`): load0.709x improved; CPU0.999x and working1.000x neutral. Fourteen workload RSS rows improved; all23 regression guards pass, no mismatch or unstable metric. Clean58; full50,158/2,748, zero failures; native2500calls/custom formatters/help/own-GIL checks pass. | Fresh primary control memory: load0.81x BEYOND, working1.00x MET; CPU2.28x OVER. Explicit validation width avoids unused terminal-size imports while preserving customized formatter and rendered-help behavior. Memory phase remains open; baseline refresh deferred. |
| 2026-09-30 | `d1900a2` (source) | Codex memory batch 8: difflib; argparse correctness repair | Quiet primary two-run ACCEPT (`20260930T214524Z`): difflib load0.142x improved, CPU0.998x and working1.000x neutral; diff workloads RSS0.947x/0.943x improved. Argparse all metrics neutral; all23 guards pass. Clean58; full50,158/2,748, zero failures; palette/native/interpreter checks and four installed argparse regressions pass. | Fresh full71 quiet primary goals: difflib load0.146x BEYOND, peak1.00x MET; argparse load0.812x BEYOND, peak1.00x MET. Uncolored diff avoids unused color-theme imports; argparse definition matching uses value identity without invoking user equality. |
| 2026-09-30 | `46d19a3` (source) | HASH heap-type lifetime correctness repair | Quiet primary two-run NEUTRAL (`20260930T223511Z`): hashlib CPU1.000x/load1.010x/working1.000x and all23 workload metrics neutral. Clean58; full50,158/2,748, zero failures; 18 staged lifetime cases, native methods/copy/errors/interpreter parity/catalog delta0 pass. | No performance acceptance claim. Saves the heap type before freeing context state/object and releases its owned reference afterward. Memory stop counter remains two empty attribution batches. |

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
