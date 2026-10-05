# Rust-for-CPython performance phase

**Memory goals first, then performance goals; CPU phase not started. Read the [current objective](#current-memory-first-objective-2026-10-01).** All 71 targets in [rust-for-cpython.md](rust-for-cpython.md)
are complete under its strict Python-suite coverage rule, and those rules
still bind every performance change. The old experiment archive was
removed from the active tree; its detailed reports and raw data remain
recoverable from Git history at commit `f0f8690`.

## Current memory-first objective (2026-10-01)

The user requested all module and workload memory goals first, without CPU,
timing or quiet-host acceptance requirements. After memory completion, achieve
all performance goals without meaningful memory regressions. This contract
supersedes historical memory-phase CPU guards, quiet-host requirements,
module-debt completion exceptions and stopped-session status below.

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
  not satisfy that goal. CPU lanes remain out of scope until all memory goals
  pass; afterward they target every performance goal with memory as a guard.
- The previous two empty attribution waves and 113 briefs remain historical
  evidence. The renewed run starts a fresh lane budget and progress count;
  revisit rejected candidates only with a distinct mechanism or an identified
  CPU-only rejection now excluded by this contract.

The user authorizes up to 31 Codex subagents plus the root coordinator for
this resumed run, superseding the earlier eight-memory-lane cap. Shared-host
builds, correctness and RSS measurements use the perf host lease. A change
to the performance harness requires fresh memory-only calibration before
comparison.

### Reuse accepted artifacts without a canonical rebuild (2026-10-04)

After a primary candidate passes complete correctness and the broad memory
gate, retain its original named stage, build report, source commit and stage
digest as the accepted runtime. Do not rebuild and repeat the same suites
solely to rename it `perf-rust`. Source workers prepare isolated changes and
may drive dedicated exploration builds and focused correctness checks after
the coordinator reserves a builder slot. Use at most two native builders on
this ten-core host, with jobs divided between them, and keep operations on the
same stage sequential. Independent preparation can overlap under the shared
perf lease; queue RSS draws after that preparation finishes. Final memory
comparisons and qualification run from the primary checkout with explicit
accepted and candidate build names. Existing stage verification and host
leases remain mandatory.

Named baselines bypass the harness's `@incumbent` ancestry check. Before each
comparison, explicitly verify that the candidate's recorded build commit
descends from the accepted runtime's recorded build commit. Preserve original
reports and paths; never rewrite provenance or move installation prefixes.
Use explicit names for calibration and absolute goals too. The `@incumbent`
alias and default goal commands still refer to `perf-rust`, which becomes a
legacy snapshot when a different named runtime is accepted. Baseline recording
still requires the canonical alias pair and is deferred to final confirmation.
This replaces the duplicate canonical rebuild/test step in the older workflow.

### Verification workflow correction (2026-10-03)

The coordinator found that execution was underusing both agent lanes and the
host. At inspection, only two of 31 subagents were active; the ten-core,
64 GiB host was about 72% CPU idle, had no swap activity and had over 400 GiB
of free disk. Repeated bespoke input scans, review packets and wrapper
approvals had serialized ordinary setup and focused host tests. These were
coordinator-added procedures, not requirements of the memory acceptance
contract. Wrapper failures also obscured a genuine test-fixture receipt-path
error.

Use ordinary `perf.py` setup, builds and target suites with the existing host
lease and verified stages. Run pure controller unit tests directly in their
isolated worktree with the installed controller interpreter and an owned
temporary directory. Keep focused checks during iteration; use exploratory
memory results to discard losers before full qualification. Complete suites,
clean committed builds, fresh calibration when required, replicated memory
verdicts, output checks and Rust coverage still precede acceptance. Existing
failed receipts remain preserved. No CPU, timing or quiet-host gate applies.

The corrected ordinary host checks passed 20/20 and 31/31; the 31-case test
process took 0.037 seconds. Normal shared-runtime build `shared-normal156`
subsequently completed and its memory comparison rejected the candidate, as
recorded below. No new module or workload memory goal was accepted.

The follow-up sprint audit measured 87–93% host CPU idle, zero swap use and
412 GiB free disk. Only four of the authorized 31 subagents were active at
its initial snapshot. Recent clean builds took roughly four to five minutes;
5,545 focused tests took 100 seconds, a full correctness suite took 497 seconds,
and two-run standard memory comparisons took 296–377 seconds. The full rigorous
71-module/all-23-workload comparison took 1,307 seconds, including lease waits
and verification. These costs do not explain the extended coordination delays.
Run at most two native builders on the ten-core host while independent source
work proceeds; keep RSS draws exclusive. Validate typed descriptors and every
declared compiler-unit expectation before another clean build. First screen all
affected modules and all 23 workloads with standard memory-only sampling;
reserve full rigorous comparisons and full/native qualification for survivors.

The latest live snapshot again found only one implementation subagent active,
with the host about 75% idle, no swap activity and 408 GiB free disk. The
coordinator remains a scheduling bottleneck. Independent follow-ups now cover
measurement orchestration cost, a mechanism-level implementation frontier and
saved physical-memory attribution, without blocking ordinary lane execution.
The primary zlib trailer correctness fix passed 50,158 tests with the accepted
2,748 skip count; its memory qualification remains pending. Standalone-only
shared-runtime trial `cold160` subsequently rejected eight replicated module
load regressions, with all 23 workload RSS guards neutral. It receives no
full-suite rerun or unchanged measurement retry, and provides no memory win.

The next sprint inspection again found one active subagent out of 31. The
host had ten cores, 64 GiB RAM, zero swap use, 402 GiB free disk and about
74% CPU idle. Coordination, excessive review work and failure to reassign
completed agents remain larger delays than host capacity. Seven independent
follow-ups were restarted for concrete source mechanisms, allocation
attribution and measurement orchestration cost; their work does not require
the native host lease. Keep source work parallel, at most two native builders,
and RSS comparisons exclusive. A pending measurement currently also blocks
new builds and target tests under the existing lease; this intentionally
leaves CPU headroom during draws. Read-only installation scans took about
0.20 seconds per stage (one first scan took 0.35 seconds). Removing 90 repeated
scans would save an estimated 18 seconds, about 1.5% of a long comparison or
7% of a short one; this is not an end-to-end measured speedup. The existing
benchmark controller has no summary-reuse interface, so this is a modest
follow-up rather than the critical path.
Additional agent occupancy alone is not progress: source hypotheses must
identify a distinct removable owner rather than repeat closed experiments.

The latest audit (2026-10-03 23:22 local) found one running subagent out of
31, 85% instantaneous CPU idle, zero swap and 395 GiB free disk. The host
remains underused outside exclusive draws. Three lanes now cover codecs-only
primary qualification, native regex integration, and its independent executor
fix. Thirty-one lanes are an available ceiling, not thirty-one simultaneously
running jobs; closed scouts require distinct mechanisms before being reopened.
The practical bottlenecks are coordinator latency, low useful agent occupancy,
shared startup/dylib/allocator costs across otherwise independent modules,
physical RSS gains failing to follow logical allocation reductions, and the
exclusive comparison queue. Source and pure correctness work can overlap draws;
native builds/tests currently cannot under the existing lease. Batch isolation
also costs a new clean build when a neighbor regresses. Use incremental builds
for correctness iteration, first screens before full qualification, and clean
committed survivor builds with complete suites before acceptance.

### Sprint bottleneck update (2026-10-04)

The later twenty-trial audit found zero adoptions: fourteen memory-guard
rejections and six target-neutral closures. Recorded terminal comparisons
totalled 61.3 minutes; eight recent clean builds totalled 29.7 minutes, with a
median 217.75 seconds. Six target-only screens had a median 9.45 seconds;
twelve focused/all23 requests had a median 232.4 seconds. These command
duration sums overlap, generally include unseparated lease waits, and are
not additive sprint wall time. The last accepted optimization remains
regex185's gate at 2026-10-04T07:43:16Z, integrated as `e702f23`.

At the latest reassignment snapshot all 31 children were idle. The host had
ten cores, 64 GiB RAM, no swap activity and 363 GiB free disk. Coordinator
latency, repeated closed hypotheses, fixture mistakes and low resident-page
yield remain avoidable costs. The shared host serializes RSS measurements
and queues native builds/tests behind them; source work can overlap.
Restarted work covers two accepted-baseline checks, source frontiers for
unresolved module/application goals and existing-artifact attribution of
cross-route guards. Filling every agent slot without a distinct hypothesis
does not shorten qualification. No memory guard or completion goal is waived.

Four-route candidate243 passed its complete focused suites
(459 tests, 52 skips, 0.286 seconds) and 27 additional native/ownership cases.
Refreshed calibration `20261004T193341Z` passed all23 workloads and six
modules in 226.3 seconds. Separate standard two-run target screens were all
NEUTRAL: CSV load1.036x, fractions1.012x, IPv6/ipaddress0.984x and
strptime1.019x; working peaks were1.000x. These four candidates are closed
without all23/all71 sampling, full qualification, unchanged isolation retries
or adoption. Their logical owner reductions did not establish resident-memory
improvements. The controller changes preserve accepted runtime overlay bytes.

The following three-route candidate247 clean-built in217 seconds with58
verified Rust extensions. Seven complete focused suites passed1844 tests
with65 skips in2.9 seconds. HTML239 passed13 differential cases and three
own-GIL create/run/destroy cycles; collections245 passed all seven cases,
including own-GIL lifecycle and observed Rust subtraction. Collections
target discovery `20261004T195017Z` was NEUTRAL: load0.900x [0.800,1.000],
working1.000x. HTML discovery `20261004T195112Z` was NEUTRAL despite pooled
load0.956x [0.940,0.980]: one independent run was neutral. Its sole rigorous
target qualification `20261004T195246Z` remained NEUTRAL at0.975x
[0.960,0.985]. Both mechanisms are closed without broad/full qualification,
unchanged retries or adoption. These are combined-candidate observations,
not isolated source attribution.

Pickle244's six semantic cases passed, but ordinary and own-GIL ownership
checks failed: unchanged CPython `_pickle.c` still imports
`functools.partial` into per-interpreter state. The Python-only change cannot
remove that owner; no pickle memory screen followed. The original failure
and tests are preserved. Distinct follow-up249 changes that native import
site while preserving existing facade bindings and captured partial
lifecycle. Source work proceeds independently of plistlib246, whose baseline
four cases, exact compiled24B/8B node-layout check and bounded source review
passed. Primary248 then clean-built58 verified Rust extensions in217 seconds;
all71 plistlib suite tests and four frozen native cases passed. Target
discovery `20261004T195852Z` was NEUTRAL: load0.827x [0.719,1.059],
working1.000x [0.881,1.051]. The writer-offset mechanism is closed without
broad/full qualification, unchanged retry or adoption. No new goal is claimed.

The native pickle follow-up249 passed six accepted-baseline cases, with
two expected ownership failures, and an initial bounded source review. A
further baseline check passed a Python module-map membership-hook case. The
Python facade needs a narrower optimization boundary to preserve that
behavior. A separate proposed C virtual-provider case was a wrong oracle:
rebinding Python `sys.modules` did not replace the interpreter's native
import dictionary or reach a fresh C initializer. Its failed receipt is
preserved; it establishes no C module-map regression. The live fixture is
corrected before the candidate build, with valid existing tests retained.

Corrected native-import candidate251 clean-built58 verified Rust extensions
in216 seconds. All17 focused cases passed: Python and direct C bootstrap
ownership, native keyword reconstruction, custom bindings/provider errors,
module-map behavior, observed Rust codec dispatch and own-GIL lifecycles.
Complete pickle/pickletools suites passed1274 tests with61 skips in2.8s.
Target discovery `20261004T201104Z` improved pickle load0.795x
[0.760,0.855] in both runs, with working peak neutral. The all23 request
`20261004T201139Z` stopped early on replicated compileall_source RSS
regression1.020x [1.019,1.021]. Remaining entities were not completely sampled.
The candidate is closed without all71/full qualification, unchanged retry
or adoption. The target gain establishes no accepted module or workload goal.

Struct253 moves the public dispatch adapters into the existing C module,
retaining the unchanged lazy Rust helper and original native fallbacks.
Public functions become builtins; private Python loader globals disappear.
The clean primary build verified58 release Rust extensions in215 seconds;
all47 struct suite tests and12 additional dispatch/lifecycle cases passed.
Target-only discovery `20261004T204522Z` was NEUTRAL: load1.000x
[0.990,1.010], working1.000x. The coordinator subsequently found that this
command omitted matched executable/prefix flags. Preserve this natural-path
receipt; the candidate requires a corrected matched-path target screen before
closing or qualifying it. No adoption or goal improvement is established.
Corrected matched-path discovery `20261004T212619Z` completed in10.9s:
load1.005x [0.990,1.010] and working1.000x were NEUTRAL. The candidate is
now closed on this valid target result without broad/full qualification or
adoption. The earlier natural-path receipt remains preserved.

An isolated compileall diagnostic compared accepted and rejected251 stages
at six import/workload checkpoints. Both compiled the same23 sources, and
all target/observer processes were reaped with stage/source guards intact.
Before compilation, candidate physical footprint was800KiB greater, matching
extra default malloc-zone residency despite identical live allocation counts
and nearly identical live bytes. Normalized image residency matched except
candidate libpython clean TEXT was16KiB smaller. Compilation narrowed the
starting difference. This single traced/checkpointed draw identifies allocator
free-capacity residency as the observed excess; it neither proves its cause
nor replaces the replicated acceptance verdict. No allocator trial is reopened.

Decimal254 links unchanged Rust arithmetic into the C decimal image and
avoids constructing the private helper when its module key is absent;
present entries preserve import/dynamic lookup and explicit private import
retains its standalone API. The absent-key path deliberately omits private
helper import events. Its clean build verified58 release Rust extensions
in214 seconds; the complete decimal suite passed735 tests with9 skips.
All six additional cases, two callback image-ownership checks, actual Cargo
archive/compile/link provenance and standalone API checks passed. Target-only
discovery `20261004T205708Z` completed in7.6s with NEUTRAL verdict:
load1.168x [1.072,1.307], neutral in one run and worse in the other;
working1.000x in both. This command also omitted matched executable/prefix
flags. Preserve it as a natural-path observation; perform the corrected target
screen before closing or qualifying the candidate. No adoption is established.
Corrected matched-path discovery `20261004T212751Z` completed in8.3s:
load1.077x [1.000,1.168] and working1.000x were NEUTRAL. The candidate is
now closed without broad/full qualification or adoption.

The same command error affected datetime255's standard and rigorous target
discoveries and its all23 discovery. Its rigorous natural-path load0.667x
improvement and neutral workload rows do not qualify acceptance. Corrected
commands explicitly include `--matched-prefix --matched-executable`; the
unchanged harness's existing matched-path calibration remains current.

Datetime255 keeps its seven unchanged Rust callbacks in the existing builtin
carrier and avoids helper-module construction on absent-key public calls.
A minimal present-None/custom-import regression passed accepted and failed
the initial candidate; the kept test verifies the corrected explicit absence
flag independently of the imported module pointer. Incremental exploration
passed all six focused cases, seven core callback ownership checks and the
complete datetime/time/strptime suites (1285 tests,83 skips). Clean stage
`perf-datetime255-qualified`, source700ec02, then verified58 release Rust
extensions in215s and passed those native/complete module checks again.
Its corrected matched-path rigorous target `20261004T212941Z` improved load
0.571x [0.571,0.667] in both runs, working neutral. Broad matched-path
all71/all23 memory-only gate `20261004T213147Z` completed in685.1s and
REJECTed replicated logging working-peak regression1.852x [1.786,1.870].
Datetime load remained improved0.571x [0.500,0.667], and every application
RSS guard was neutral. This mechanism is closed without full correctness
qualification, adoption or unchanged retry. Its local gain establishes no
accepted absolute goal. Natural-path receipts remain excluded.

Warnings256's original Python module-map admission bypassed a provider still
present in the interpreter's internal import dictionary. The kept minimal
regression passed accepted and genuinely failed a model of the candidate
facade using the same accepted native callbacks. This is modeled dispatch
evidence, not compiled candidate qualification. Corrected source2f573d4
checks internal helper presence in C before argument conversion; every
present entry declines into the unchanged Python import/cache path. Resolved
module and None cache owners remain sticky. Primary sourcee2d5ece clean-built
58 verified Rust extensions in224s. All five required suites passed1803 tests
with23 skips in27s. All12 native cases, four core callback ownership checks,
standalone private API and genuine Cargo carrier/helper provenance passed;
the replay preserved archive/core/stage bytes and actual `fresh:false` flags.
Matched standard target `20261004T215507Z` completed in9s and was NEUTRAL:
load0.988x [0.958,1.052], working1.000x. Normal interpreter startup initializes
default filters in C; no normal-startup Rust helper owner was established by
the bounded source trace. The candidate is closed without additional startup,
all23/full qualification, unchanged retry or adoption. No goal gain is claimed.

Threading257 retains its original Python from-import path for every present
helper entry, while absent-key calls execute the unchanged Rust transition
through the existing native thread carrier. Private absent-helper import
events are deliberately omitted; standalone helper API remains available.
Accepted verification passed two provider/reentry cases and failed the
separate absent-helper ownership case as expected. Primary source3b073ed
clean-built58 verified Rust extensions in214s. Complete affected/checklist
suites passed4630 tests with240 skips. All six native cases and callback
image-ownership checks passed; genuine Cargo carrier/helper JSON replay
preserved archive/core/stage bytes and actual `fresh:false` flags. Standard
matched target `20261004T215333Z` read load0.625x [0.625,0.833] but was
NEUTRAL because only one run resolved an improvement. Its sole rigorous
qualification `20261004T215618Z` improved load0.625x [0.625,0.729] in both
runs, working neutral. Matched all23 exploration `20261004T215733Z` stopped
after139.6s on replicated compileall_source RSS regression1.017x
[1.014,1.020]. Six workload results completed; the other18 entities, including
threading, were incompletely sampled. The candidate is closed without all71,
full correctness qualification, unchanged retry or adoption. The target gain
establishes no accepted absolute goal.

Distinct UUID258 source work targets helper-module construction by retaining
unchanged Rust callbacks in the existing shared C UUID image. Its explicit
experimental private-owner boundary captures the C provider when the helper
was initially absent. Initial present-provider import/cache and later namespace
overrides must retain their behavior; later module-map replacement is ignored.
A separately imported standalone helper remains available, but patching it no
longer modifies the already captured public provider. Keep an unchanged
accepted-behavior comparison fixture and test the new ownership separately.
No UUID source implementation, compilation or memory improvement is yet proved.

The subsequent bounded audit of26 closed candidates found zero adoptions,
nine target-neutral closures and17 memory-guard rejections. A standard full
71-module/23-workload two-run comparison launches approximately1883 root
children, plus probes and fixture preparation. Workload timing rounds and
quiet-host waits are already disabled. Build and benchmark timers start
before lease acquisition, so saved durations include unmeasured queue wait.
Source work overlaps draws; native builds/tests retain the exclusive RSS
isolation boundary. Seven independent follow-ups were restarted after another
one-active-child snapshot; this does not establish sustained full utilization.

The latest host check found ten cores, 64 GiB RAM, no swap use and 392 GiB
free disk; the host was mostly idle. Only one subagent was running at the
initial snapshot, completing the zstd screen. Agent capacity is underused;
the 31-agent allowance has not translated into 31 independent implementations.
Most saved scouts are closed without a distinct removable owner. Scheduling,
repeated historical rediscovery and excessive coordinator procedures have
added avoidable delay. Source work and pure tests can run alongside draws;
native builds/tests currently wait behind the exclusive measurement lease.

Primary borrowed-SRE trial184 passed its clean build, 13 focused suites
(3,756 tests / 75 skips), and 11 native fixtures. Its first standard two-run
screen rejected logging load **1.035x**, despite regex load **0.704x** improving;
all 23 workload RSS guards were neutral. The verdict is
`20261004T070306Z-perf-rust-vs-perf-regex-primary184`, SHA256
`9bd6ed82b985c84ff07aa5a6461aafebdb6de11787e937a32c71c46653285225`.
No full suite, broad gate or unchanged retry follows this rejection.

Zstd provider182 passed 11 focused suites (2,715 / 192) and seven native
fixtures, then finished its first screen in **236.4 seconds**. All target,
neighbor and workload memory rows were neutral; working memory remained
327,680 bytes on both sides. The exploratory draw matched PYTHONHOME but
not executable paths and establishes no acceptance. Verdict
`20261004T071332Z-perf-rust-vs-perf-zstd-provider182` has SHA256
`69e53673776fa2f98b879e9f03d7b2117def99894f152897c9fec4f4359eca3e`.
Candidate `1c3635e` and receipts are preserved; no full qualification or
unchanged retry follows. Sharing the provider removed bundled code, without
a demonstrated resident-memory gain.

Clean builds recently cost about four minutes, focused suites roughly
12 seconds in the latest codecs/zstd runs, full correctness about eight
minutes, and the codecs broad standard comparison about fifteen minutes.
A second zstd clean build after a fixture-only correction repeated about
four minutes of compilation. Use incremental correctness iteration, avoid
rebuilding unchanged production code solely for fixture corrections, and
run full correctness once per qualified source rather than in both worker
and primary paths. Keep committed clean builds, stage verification, complete
suites and replicated memory guards before acceptance. Full suites may use
four workers when the host is otherwise available; focused suites use two.

Distinct regex trial185 moves the typed borrowed-pattern accessor from core
libpython into helper-owned C glue, preserving the executor and native
contracts while leaving the core SRE source unchanged. This tests a new source
placement hypothesis; the trial184 regression has no established causal
attribution. No new module or absolute workload goal has been accepted.

Logging attribution186 completed once under the ordinary test lease, with
all three children and twelve `vmmap` captures exiting zero, cleanup complete,
and stages unchanged. Incumbent, worker176 and primary184 had identical
displayed live allocation counts (2,449 before import, 2,962 after the second
setup/call) and rounded allocated bytes (2,214 KiB to 3,118 KiB). Mapped DATA
totals matched, while dirty default-malloc-zone totals differed. This locates
variation in allocator commitment/fragmentation in this capture, without
identifying a caller or establishing the earlier gate's causal mechanism.
Worker176 logging already had a pooled 1.039x increase; primary184's 1.035x
result was classified worse by its confidence bounds. The classification
change is not evidence that primary placement introduced that cost.
Raw evidence remains at
`/Users/josh/d/python-build-perf-worktrees/memory-wave-20261002/inspect-text-signature/rust-cpython/results/logging-region-attribution186/`.

Trial185 will receive one primary clean build and qualification, avoiding
worker and primary rebuilds of identical source. First-screen rejection still
stops full qualification; survivors retain full correctness and broad memory
guards. Reported build and comparison timers start before lease acquisition;
the codecs broad comparison's 915.9 seconds included approximately 210 seconds
of waiting/preflight, so its post-acquisition/preflight span was about 706
seconds. These timings are not compiler-only or pure sampling measurements.

Primary185 source `f792e33` passed its single clean build in 216.8 seconds
(58 verified Rust extensions), all 13 focused suites (3,756 / 75), and twelve
native fixtures with stage guards and temporary-directory cleanup passing.
Its built `Modules/_sre/sre.c` SHA256 matches the incumbent exactly:
`7eede3058b7de42e657ac99130ce8dfb8d351a0f65cc54e1443853b8a4292aae`.
The first exploratory two-run screen
`20261004T073412Z-perf-rust-vs-perf-regex-primary185` finished in 233.6 seconds
and read ACCEPT: regex load 0.699x improved, `import_django` RSS 0.987x
improved, and all other checked memory rows neutral. Verdict SHA256 is
`e4abdd5c1b6a28006a51274d11d5da7c5e77b777b41c3a4cc22a6444537b1dc0`.
Logging remains a concern: its pooled load was 1.035x, with one run neutral
and one worse. This is exploratory evidence, not acceptance or resolution.

Full correctness subsequently passed with four workers in 252 seconds:
50,158 tests / 2,748 skips, zero failures, 464 test files OK. The same artifact's
all-71-module/all-23-workload standard two-run memory-only gate is running
under owner63's handle93403, controller91727, with matched home and executable
paths. No source or incumbent advance precedes its actual terminal verdict.

Distinct follow-up187 source `c6118fd` keeps the borrowed-program validator's
word-role and pending-offset storage inline for small programs, with fallible
heap growth for larger ones. This targets two new transient heap vectors;
search continuation storage, allocator ownership and legacy caches are
unchanged. The existing locked `smallvec` 1.16.1 version/checksum is retained
and its license is recorded. Source work overlapped185 qualification; pure
tests are queued behind the measurement lease and remain unrun. No physical
saving or goal completion is claimed.

The live coordinator state was reduced from accumulated 334 KiB history to
current operational fields; the original ignored JSON is preserved separately
as `coordinator-state-history-20261004T073600Z.json`. Historical evidence remains
available without presenting stale running entries as current work.

Primary185's broad gate subsequently **ACCEPTED**, actual exit zero and all
owner handles drained. The 687-second standard two-run memory-only comparison
`20261004T074316Z-perf-rust-vs-perf-regex-primary185` covers all 71 modules and
all 23 workloads under clean harness `f741f178`, with matched home/executable
paths. Regex load **0.670x [0.653, 0.702]** improved in both runs; working peak
was neutral. Every other module memory row was neutral, and workload RSS was
neutral except `django_wsgi_first_request` **0.985x** improved. Mismatches,
unstable rows and replicated regressions were empty. Verdict SHA256 is
`dcf6b119e74de20bf9220ac4c4aadcc7ecdc67625873174b5cbd4711fecc0475`.
Source `f792e33` is qualified for integration. This is an incumbent-relative
memory improvement; absolute module/workload goals against control remain
unproven until refreshed. CPU work remains out of scope.

Follow-up187's seventeen pure Rust tests passed under the normal test lease
(fourteen existing cases plus three inline/spill/error invariants). Its first
launcher failed before compilation because it guessed a missing Cargo path;
that receipt is preserved. The corrected launcher used the installed locked
nightly toolchain, offline/locked dependencies and two jobs. No native-helper
or physical-memory result is claimed for187 yet.

The accepted185 source was integrated onto main at `e702f23`. The canonical
incumbent then passed a clean build (217.9 seconds), twelve native fixtures,
all thirteen affected suites, and full correctness with four workers
(50,158 / 2,748, zero failures, 250 seconds). Fresh memory-only self-calibration
`20261004T081619Z-calibrate-perf-rust` passed. Absolute regex goals
`20261004T082016Z-goals-perf-upstream-vs-perf-rust` still read load OVER:
1.216x [1.197, 1.232], 1,200 versus 992 KiB; working peak is MET. The older
whole-project absolute snapshot is not a fresh completion audit.

Primary187 passed its single clean build (216.3 seconds), thirteen affected
suites (3,756 / 75), and thirteen native fixtures. Its first standard two-run
memory-only screen **REJECTED** after 233.8 seconds: catalog URL normalization
RSS 1.014x, compileall RSS 1.021x, and multiprocessing pool RSS 1.012x all
regressed in both runs. Every module memory row was neutral; nothing improved.
Verdict `20261004T082302Z-perf-rust-vs-perf-regex-primary187` SHA256 is
`62d779c2ddbe036b71132d5a2b91f2f6f6ae4e3576b8c4618e976f90a140e51e`.
No full suite, retry or integration follows; main remains accepted185.

The latest roster check found all 31 workers idle before reassignment. The
host has ten cores, 64 GiB RAM, no swap activity and 390 GiB free disk.
Coordinator latency and insufficient distinct implementation work remain
avoidable bottlenecks. Current successful qualification costs about 3.6
minutes for a clean build, 15 seconds for affected suites, four minutes for a
first screen, 4.2 minutes for full correctness, and 11.5 minutes for a broad
memory gate, plus a similar canonical incumbent rebuild/test cycle. Larger
agent occupancy cannot parallelize the exclusive RSS queue.

Distinct lane188 now implements a source-supported but unproved split:
retain native wrappers and the borrowed compiled-pattern executor in
`_re_rs`, moving the legacy regex engine intact into a private Rust extension
loaded only by legacy prepare/search. This changes internal installed-image
inventory and must preserve direct helper and hook behavior. No existing
measurement attributes the residual 208 KiB to that engine. Independent
contract/fixture work overlaps implementation; physical savings require a
new first screen. No custom ABI, allocator redesign or mimalloc revival is
part of the lane.

Primary188 source `35a27b6` passed its single clean build in 216.6 seconds
(59 verified Rust images), all thirteen affected suites (3,756 / 75), and
all 31 native fixture cases. Its first standard two-run memory-only screen
**REJECTED** in 234.3 seconds: gzip RSS 1.016x, wheel reading RSS 1.014x,
and zlib streaming RSS 1.016x regressed in both runs. All seven module memory
rows were neutral; regex load was 0.961x [0.911, 1.000], with no demonstrated
improvement. Verdict `20261004T085627Z-perf-rust-vs-perf-regex-primary188`
SHA256 is `dafb8bb9b65374412424646a0aa6fff0b7e1a4c8ba7047d2c9b6bf55feeae410`.
Outputs matched, the current harness was clean, and no metric was unstable.
No full suite, retry or integration follows; accepted runtime remains185.

An independent source inventory check found that the pinned generator includes
every internal Rust extension in `sys.stdlib_module_names`. Trial188 omitted
its new backend there. Preserved worker commit `91e14bf` adds the name and a
source regression that failed before the fix and passed afterward. The native
assertion remains unrun; this correctness fix does not justify rerolling the
rejected memory candidate. Future new-image briefs must include this inventory.

Attribution189 now compares pristine control directly with the accepted
incumbent for regex and datetime, using one bounded physical-region capture.
The older logging186 capture compared candidate builds rather than control;
its identical allocation counts therefore do not explain the absolute excess.
Observer evidence will guide source work, not qualify memory acceptance.

Attribution189 completed once, with four target children and sixteen region
captures exiting zero and reaped, matching outputs and unchanged stage/harness
guards. Accepted regex adds 16 KiB dirty DATA plus 48 KiB DATA_CONST in
`_re_rs`; datetime adds 16 KiB in each segment in `_datetime_rs`. Startup
already differs in libpython dirty segments by 16/32 KiB. Malloc-zone live
allocation counts and bytes also differ, but accepted absolute physical
counters were lower in this capture. It parks before import and after one
retained setup/call, without the kernel's second setup subtraction. These
are ownership observations, not acceptance ratios, caller attribution or a
reproduction of the gate excess. Read-only symbol/relocation attribution190
now checks which mutable definitions and Rust runtime tables occupy those
helper pages, before proposing another source change.

Attribution190 bound the saved region addresses to the exact installed images.
Datetime's constant page has 381 loader fixups, only fifteen in the 304-byte
method/slot tables; regex's three constant pages have 863, 741 and 699 fixups,
only fifteen in its 192-byte method table. Mutable 104-byte module definitions
share DATA pages with lazy imports, TLS and Rust globals. Regex's first DATA
page also contains part of its scratch storage. Removing just module tables
therefore has no established exclusive page to reclaim; no new export or
shared-image candidate follows these observations. The bounded findings remain
in the ignored `dirty-helper-page-attribution190` results directory.

Distinct lane191 targets execution storage rather than module layout. The
borrowed executor currently creates an immutable repeat snapshot and pending
alternative per matched character even for canonical single-character
REPEAT_ONE/MIN_REPEAT_ONE programs. A five-second ordinary accepted-incumbent
sample (`20261004T091901Z-perf-rust-module-re-sample`) reaches repeat_step,
continuation pushes and RawVec growth. This confirms the route is exercised,
without proving an RSS cause or using timing as acceptance. The candidate
uses compact repeat continuations with bounded storage for that admitted
subset, preserving general repeat behavior, priority, fallible growth and
interruption polling. Validator storage, legacy engine and allocator stay
unchanged. Source `541381f` passed eighteen Rust tests, including 9,583 canonical span
comparisons and bounded-storage/interruption checks. Primary candidate
`5efe2a8` built all 58 images, passed 3,756 focused tests (75 skipped), and
passed all 23 native contract tests. Its first standard two-run memory-only
screen **REJECTED**: regex load 0.924x remained neutral, logging working peak
1.679x and search-form RSS 1.012x regressed in both runs. Other workload RSS
rows were neutral. The continuation enum also increases ordinary branch-state
size, so logical storage bounds alone never established a physical win.
Verdict `20261004T093243Z-perf-rust-vs-perf-regex-primary191` SHA256 is
`530075f3701ebdb3f349a356978c08bfc44b2280997c3d952fcd6cbb7173c6de`.
All owned handles drained; no full suite, reroll or integration followed.
The accepted production source remains `e702f23`.

Diagnostic work192 completed paired captures for datetime, decimal, typing
and the actual serialization workload. Typing import allocations differed by
only 1,260 traced bytes; serialization retained essentially identical decoded
graphs and wire buffers. Date formatting and decimal arithmetic traces instead
identified fresh method-name strings consistent with retention by CPython's
pointer-keyed type cache. These are traced Python allocation observations, not
Rust malloc ownership or acceptance RSS. The datetime probe used a randomized
hash under isolated startup, so its original matching-digest claim was
retracted; subsequent native tests check explicit values.

Sources193/194/195 respectively reject necessarily unsupported pickle lists
before reserving their child workspace, and reuse interpreter-owned names in
datetime and decimal while resolving mutable helper callables every time.
Native legacy getters retain their original precedence when both attribute
slots exist. Original batch197 compiled successfully but was withheld from
tests and measurement until that precedence correction; its compiler evidence
is preserved separately. Corrected batch198 (`d8b4f83`, fixture-only descendant
`111333c`) built all 58 images and passed seventeen complete focused suites
(6,985 / 323) and twenty-one native tests, including four dual-slot contracts.

The first standard comparison198 was NEUTRAL with no replicated regressions:
datetime load pooled 0.571x and decimal 0.809x, but each improved in only one
run. One predefined higher-sample comparison on the same artifact resolved
that uncertainty without changing floors or replication. It ACCEPTED datetime
load 0.598x and decimal 0.815x in both runs; all other checked module metrics
and all 23 workload RSS guards were neutral. Pickle load worsened in one run
only, which remains preserved rather than represented as an improvement.
Verdict `20261004T101328Z-perf-rust-vs-perf-memory-primary198` SHA256 is
`1a510d1c45c55fc7c48ea32a22b2be062bd2685801147b172119daebedbecc9a`.
This is exploratory evidence, not integration or absolute goal completion.

The first full198 suite ran 50,158 tests / 2,748 skips and failed one process
pool remote-traceback assertion. The relevant process and test sources match
the accepted build byte-for-byte. The exact method subsequently passed for
Fork, Forkserver and Spawn on both installations. An exit-status polling race
is plausible but unproved; no speculative fix or test weakening followed.
The one complete recheck on the same artifact passed: 50,158 tests / 2,748
skips, 464 test files OK, zero failures, in 249 seconds with four workers.
The original failure remains preserved. The same artifact's all-71-module /
all-23-workload standard two-run memory-only gate subsequently REJECTED in
685.7 seconds: tarfile load 1.066x [1.047, 1.078] regressed in both runs.
Datetime load 0.661x and decimal 0.800x improved in both runs; pickle and all
23 workload RSS rows were neutral. No mismatch or unstable row occurred.
Verdict `20261004T103037Z-perf-rust-vs-perf-memory-primary198` SHA256 is
`a5e95fb96f7dedeadecf102a3e42e986866752794b1f939a15a3f86674d81ceb`.
The rejected source and artifact remain preserved, with no unchanged retry
or adoption. Batch199 isolates the datetime/decimal name changes from the
memory-neutral pickle budget change; no cause for the tarfile regression is
established. Its single clean build passed in 216 seconds (58 Rust images),
ten complete focused suites passed (2,900 / 202), and all fourteen native
cases passed. One legacy-fixture launcher failed because an extra `-v`
argument prevented its artifact loader from running; the receipt is retained,
and the corrected invocation passed without source changes or a rebuild.
Its first standard two-run memory screen over eleven modules, including
tarfile, and all 23 workloads REJECTED in 261.9 seconds. Logging working peak
1.222x [1.185, 1.259] and five workload RSS rows regressed in both runs:
catalog request path 1.014x, gzip extraction 1.015x, startup 1.014x, large
base64 1.011x and zlib streaming 1.017x. Datetime and decimal load rows were
coded neutral, despite pooled ratios 0.667x and 0.832x; tarfile was neutral
overall with one worse run. No mismatch or unstable row occurred.
Verdict `20261004T104927Z-perf-rust-vs-perf-memory-primary199` SHA256 is
`c5f87eadc1b6c4e42dbb31904b05a83d83b6bd2d79eade97e9fd94b1b53f6701`.
No full qualification, retry or adoption follows. This isolation does not
establish the cause of either batch's regressions.
Contextlib source196 independently applies canonical attribute names while
preserving legacy getters. Its three-case baseline reproducer failed the
expected canonical-name identity assertion; the other two semantic/lifecycle
cases passed, with stage guards and cleanup passing. Candidate native and
Primary203 isolated that change from datetime, decimal and pickle changes.
Its clean build passed in 216 seconds (58 images), eleven complete focused
suites passed (6,315 / 153), and five native cases passed. Its first standard
two-run eleven-module/all-23-workload screen REJECTED in 266.3 seconds:
catalog request path 1.016x, catalog search form 1.013x, reordered difflib
1.015x, gzip extraction 1.017x, multiprocessing pool 1.012x and small base64
1.014x RSS all regressed in both runs. Contextlib load 1.008x and working
peak 1.000x were neutral. No mismatch or unstable row occurred.
Verdict `20261004T110249Z-perf-rust-vs-perf-contextlib-primary203` SHA256 is
`3fa6d7d86f6a5e53200f76dec2c5ab21b0bad4a663b83937623c55908f336939`.
The source and artifact are preserved without full qualification, retry
or adoption.

A narrow C-bridge audit found two distinct additional name-lookup prospects:
the fixed SQLite kernel performs 12,000 `column` and at least 3,001 `step`
lookups per run; socket performs 200 `send` and 200 `recv` lookups. Zstd has
six kernel-reached operation names and sixteen lookups per loop. These counts
describe fresh-name lookup paths, not retained names or physical savings.
Sources200/201/202 are ready and passed independent source review. Accepted
baseline runs reproduced SQLite's step/column identity failures, socket's
ordinary and own-GIL identity failures, and all seven zstd operation-name
identity failures. Socket's other three ordinary contracts passed; its later
own-GIL lifecycle assertions were not reached. A wrong SQLite step-error test
was corrected to the observed existing behavior (query returns None), and the
selected semantic case passed; canonical assertions remain intact. These are
behavioral reproductions, not resident-memory evidence.
Primary204 combines these three independent C-bridge changes for one clean
build and qualification, excluding the rejected prior candidates. No image,
provider, allocator or callable-cache experiment is revived.
Its single clean build passed in 218 seconds (58 verified Rust images),
all 21 complete focused suites passed (7,651 / 602), and seventeen native
cases passed, including shared dual-slot tests and interpreter lifecycle
checks. The first standard two-run thirteen-module/all-23-workload screen
REJECTED in 273.3 seconds: gzip extraction RSS 1.015x, startup 1.013x and
zlib streaming 1.012x regressed in both runs. SQLite load 1.014x, socket
0.980x and zstd 1.000x were all coded neutral, as were their working peaks.
The other twenty workload RSS rows were neutral; no mismatch or unstable
row occurred. Verdict `20261004T111726Z-perf-rust-vs-perf-cnames-primary204`
SHA256 is `a3aae3a480e1886b6366fa3a80d8b4c6316e97f445b6043621031e2961e8b32a`.
No full qualification, retry or adoption follows; source and artifacts remain
preserved. Repeated small guard increases are under saved-evidence review,
without causal attribution or a changed acceptance threshold.

Distinct inspect prospect205 targets the three parameter metadata names
(`name`, `kind`, `default`), reached 84,000 times per fixed kernel run.
Its source-only lane preserves original lookup for legacy and custom modern
getters, canonicalizing names only for the generic getter. This is a source
prospect. The accepted-stage retention regression reproduced nineteen blocks
and 876 bytes released after clearing the type cache and collecting; its
twelve-block bound failed, while its 1,024-byte bound passed. This proves a
modest logical retention difference, not a page-sized resident-memory owner.
Primary210 compiled this source cleanly in 216 seconds. All five Python
contracts and its compiled dual-slot case passed, including the retention
bound; six complete focused suites passed (1,696 / 1). The first standard
two-run six-module/all-23-workload memory screen REJECTED in 229.6 seconds:
inspect load 1.011x [0.995, 1.028] and working peak were neutral, while logging
working peak 1.563x, reordered-diff RSS 1.016x and zlib-stream RSS 1.015x
regressed in both runs. Verdict
`20261004T123505Z-perf-rust-vs-perf-inspect210` SHA256 is
`3d27cb03403624a0ad9a3a87bae978180914ea1a2d934400b47663afd832b6a3`.
No full suite, broad comparison, unchanged retry or adoption follows.

The same-source rebuild diagnostic206 completed four startup children and
twelve observers under the ordinary test lease, with successful stage guards
and cleanup. The original qualified regex185 artifact and canonical accepted
artifact have identical production overlays, normalized interpreter paths,
loaded module names and code filenames. The former showed 352/576 KiB more
process RSS; stage-owned dirty pages were identical, while malloc-zone
residency and fragmentation were higher. Allocation counts were identical
and printed allocated bytes differed by only 1 KiB. This descriptive probe
does not establish causality or acceptance. A separate source/artifact audit
found absolute Cargo output paths in macOS dylib install names, with different
load-command lengths and text offsets. A stable install-name experiment will
control that known layout input; it is not yet an explanation for RSS.

The latest sprint inspection found ten CPU cores, 64 GiB RAM, no swap
activity, 381 GiB free disk and load averages around 1.3. All 31 agents had
completed at that snapshot, and no native qualification was running.
Coordinator latency and low useful reassignment remain avoidable delays.
Recent clean builds took 216–218 seconds, initial memory comparisons
262–273 seconds, full correctness about 249 seconds, and broad all-module
memory qualification about 686 seconds. Shared-host measurements serialize;
independent source implementation and analysis need not. Repeated source
scouts and sub-page logical savings should not displace physical-memory
attribution and distinct implementation hypotheses.

For a candidate that survives the focused/native checks and initial memory
screen, run the one broad all-71/all-23 memory gate before the full correctness
suite. Its result remains provisional: adoption requires both that gate and
the complete suite to pass on the same unchanged clean artifact. This changes
coordinator ordering, not acceptance criteria or sampling. Candidate198 spent
500 seconds on two full-suite attempts before its broad memory rejection;
the reversed order would have avoided that work. Initial-screen losers still
receive neither a broad comparison nor the full suite.

Stable-install-name candidate207 built cleanly in 217 seconds. Three build-helper
tests and six complete focused suites passed (1,891 / 38), but the artifact
contract failed for binascii: its requested own install name was followed by
the base64 dependency's install-name arguments, leaving the linked image
with base64's identity. The other 57 identities and unchanged threading/struct
header-shift checks passed. Cargo's dependency-argument propagation is under
source investigation; no memory measurement or adoption
follows this failed artifact contract.

Distinct candidate208 releases binary plist flattening's deduplication maps
and traversal scratch before output and offset allocation. Frozen mapping
snapshot owners remain alive through serialization. The fixed graph has at
least 17,404 bytes of logical map/scratch payload before spare capacity and
bucket overhead. This is an allocation-overlap hypothesis, not a proven
working-peak improvement; clean compilation and ownership/output fixtures
precede its memory screen.
Its clean build passed in 217 seconds; four native fixtures passed on both
the accepted and candidate interpreters, and five complete focused suites
passed (1,679 / 62). The first standard two-run seven-module/all-23-workload
memory screen REJECTED in 232.7 seconds. Plistlib load improved to
0.629x [0.547, 0.778] in both runs; working peak was neutral at
0.957x [0.830, 1.087]. Catalog request, gzip extraction, small base64, wheel
reading and zlib decoding RSS regressed in both runs. Verdict
`20261004T120549Z-perf-rust-vs-perf-plistlib208` SHA256 is
`a2aa02ce1c629b91af867419dc3f97a57e86923a5a78cb8c93ee68b62ca2ab23`.
No full suite, broad comparison, unchanged retry or adoption follows.

Corrected install-name candidate209 uses package-local Cargo linker arguments
for the new identity pair. Cargo's cdylib-specific arguments propagate to
dependent cdylib links; package-local arguments avoid that overwrite. Existing
general helper directives remain unchanged. A fresh clean build must establish
all actual image identities before memory measurement; source reasoning alone
does not qualify this change.
The corrected clean build passed in 216 seconds. All three artifact checks
passed, including all 58 exact install names, binascii's distinct identity,
and unchanged small-helper header geometry. Three Rust helper tests and six
complete focused suites passed (1,891 / 38), with unchanged stage guards.
Its first standard two-run twelve-module/all-23-workload memory screen
REJECTED in 265 seconds. Logging working peak regressed in both runs to
1.667x [1.667, 1.704], with raw medians 442,368 versus 737,280 bytes. All
23 workload RSS rows and the other module memory classifications were neutral;
there were no mismatches or unstable rows. Verdict
`20261004T121603Z-perf-rust-vs-perf-installid209` SHA256 is
`55cfaec799700c96957a3486be6921991295ef6cb1d7f71b2f8079f39fd708cd`.
No full suite, broad comparison, retry or adoption follows. The controlled
install-name input is verified, but its memory result does not explain the
earlier rebuild variation or establish a generally beneficial layout change.


### Current throughput audit (2026-10-04)

Exploratory memory comparisons now stop after an entity has all requested
independent runs and the existing verdict proves a replicated memory
regression. Survivors, gates, calibration, goals, timing comparisons and
baseline recording still collect the full selection. Partial reports retain
all raw observations and output mismatches, publish verdicts and goals only
for fully sampled entities, and identify incomplete sampling with
`sampling_complete`, `incomplete_entities` and `stopped_after`. No partial
comparison can establish acceptance. Source220 passed62 controller tests;
independent review passed the same tests. Existing logs show76–95 seconds
of continuation after the first replicated failure in four earlier screens;
this is an upper bound on possible savings, not a measured end-to-end gain.
The harness change requires fresh memory-only calibration before comparisons.

The live audit found one running child out of 31 before three bounded audit
tasks were assigned. The host has ten cores, 64 GiB RAM, zero swap use and
377 GiB free disk. The latest ten measured candidates (187, 188, 191, 198,
199, 203, 204, 208, 209 and 210) produced eight target-neutral rejections,
two target-improved rejections and no adoptions. Their comparisons alone
consumed 48.6 minutes. Low candidate yield, coordinator delay, repeated
mechanism discovery and the exclusive measurement queue are the current
bottlenecks; agent slots and host memory are not exhausted.

Ordinary source edits may use a dedicated incremental exploration stage for
focused correctness and the first standard two-run memory screen. The harness
requires a clean build for gate evidence, not for rejecting exploration
candidates. Structural changes that its incremental planner refuses still
require clean builds. An exploration survivor must qualify again on one clean
committed artifact: focused/native checks, the broad all-71/all-23 memory gate
and the full correctness suite all remain required before adoption. No saved
incremental duration establishes a numerical speedup yet. Reuse qualified
artifacts and avoid fixture-only rebuilds; preserve sampling, output checks,
memory floors and regression guards.

Logging diagnostic211 completed four children and 36 observers with unchanged
stage and harness guards. Both images retained identical stream-associated
allocations. Tracing and snapshot work removed the original untraced
18-page differential, so the probe cannot attribute its cause or overturn209's
rejection. Findings are saved under
`bisect-core-source/rust-cpython/results/logging-loop-owner-attribution211/`
in the memory-wave worktrees; report SHA256 is
`b851b43b421af8d51a81299612b09f43afb2a947ec8cedad5005df0255cef1ad`.

Plistlib output-growth experiment212 changes the result buffer's geometric
growth from doubling to 3/2 with checked signed sizes. Source `7579075` starts
from accepted production and does not retain208's early-map-drop change. The
original208 stage/report/logs are preserved at
`rust-cpython/results/plistlib208-original/`; its configured build name was
reused for mutable exploration. Incremental compilation took 35.3 seconds,
versus the preceding 216.7-second clean build. Six native checks and five
focused suites passed (1,679 / 62). Its first standard two-run seven-module/
all-23-workload memory screen REJECTED: plistlib load0.934x and working0.957x
were neutral, and seven workload RSS rows regressed in both runs. Verdict is
`20261004T130338Z-perf-rust-vs-perf-plistlib208`. Reserved capacity fell in the
source model, without demonstrated physical benefit. No clean qualification,
full suite, broad gate, unchanged retry or adoption follows this rejection.

ElementTree captured-text experiment213 stores owned references to eligible
long exact ASCII strings instead of copying their payload into the complete
prevalidated output buffer. Coalesced literal spans retain callback order;
subclasses, escaped and non-ASCII text keep the copied path. Writer callbacks
still receive fresh strings, while captured owners gain one temporary
reference through emission. Source `bf2b96b` starts from accepted production,
without212's growth change. Six native ownership/callback/error tests passed.
Five actual focused suites passed across two executions (869 / 13); the first
selection's two nonexistent optional suite names remain preserved as a driver
error, and the three successful suites were not rerun. Incremental compilation
took 35.2 seconds. The first standard two-run seven-module/all-23-workload
screen REJECTED: ElementTree load1.039x and working1.073x were neutral, while
compileall, small-base64 and zlib-decode RSS regressed in both runs. Verdict is
`20261004T131655Z-perf-rust-vs-perf-plistlib208`; this reused exploration build
name is distinct from the original208 and212 artifacts/results. No clean
qualification, full suite, broad gate, unchanged retry or adoption follows.
The two incremental builds were about six minutes shorter in total than two
recent clean builds; this comparison does not establish identical-work speedup.
Neither candidate produced an accepted
memory improvement. The accepted runtime and absolute goals are unchanged.

Decimal bounded-integer experiment214 isolates historical `e1b1476`'s checked
u128 arithmetic and 39-byte stack formatting on current accepted production.
Cargo settings, std, allocator, C dispatch and module ABI remain unchanged.
The earlier primary `4ea59fa` combined this mechanism with no_std/PyMem and
read decimal memory-neutral, so it did not establish this isolated variant's
result. Current source `8b95feb` passed all five supplemental tests on both
baseline and candidate. Four actual focused suites passed (1,194 / 14) across
three suites plus the correctly named numeric-tower suite; a nonexistent
`test_numbers` selection error is preserved, without repeating passing suites.
Its 35-second incremental build verified all58 helpers. The first standard
two-run seven-module/all-23-workload memory screen REJECTED: decimal load0.962x
and working1.000x were neutral in both runs. Six workload RSS rows regressed
in both runs. Verdict is `20261004T134303Z-perf-rust-vs-perf-plistlib208`.
This now closes the standalone std/default-allocator arithmetic variant as
well as preserving the older combined result. No clean qualification, full
suite, broad gate, unchanged retry or adoption follows.

The renewed sprint audit found 24 unresolved load-only goals and three
working-only goals (zstd, plistlib and ElementTree), with none unresolved on
both metrics. At the live snapshot all31 children were complete and the host
had no native work, no swap use and376 GiB free disk. Agent slots are being
underused; physical RSS comparisons remain exclusive. Recent tiny-allocation
and temporary-buffer work has low yield against predominantly retained-import
goals. Prioritize distinct retained owners and source attribution, without
reopening closed mechanisms or treating logical allocation reductions as RSS
wins. Raise focused-suite workers to four when the host is otherwise free;
initial exploration may run the complete direct-route suites and native
contracts, deferring distant neighbor suites until survival. All affected
suites remain required before final adoption. Keep two-run sampling, memory
floors and all final guards unchanged. Ordinary source review of borrowed
binary plist tables215 found no change-relative bug; incremental compilation
verified58 extensions in35 seconds. Native and memory qualification remain
pending, and its modeled11,032-byte payload removal is not a physical-memory
claim.

Borrowed binary plist table experiment215 retains immutable wire slices
instead of allocating decoded offset and recursive-reference vectors. Source
`0d8a321` preserves object sharing, cycles, checked bounds and value-before-key
callback order. Its35-second incremental build verified58 extensions; six
native methods passed on accepted and candidate interpreters, and complete
`test_plistlib` passed71 tests with no skips at four workers. The first standard
two-run seven-module/all23-workload screen REJECTED: plistlib load0.840x
[0.560,1.104] and working0.868x [0.727,1.000] were neutral in both runs;
compileall RSS regressed in both. There were no mismatches or unstable metrics.
Verdict `20261004T135810Z-perf-rust-vs-perf-plistlib208` SHA256 is
`aa0d6be4a5e4af60dd353b1c40de71451750da2944ec1bf581f89469c1c75a22`.
No unchanged retry, higher-resolution comparison, clean qualification, broad
gate, full suite or adoption follows. The modeled11,032-byte removal did not
prove a physical-memory win; accepted goals remain unchanged.

Functools retained-class experiment216 defers construction of the comparator
wrapper class until cmp_to_key or private attribute lookup. Private _KeyWrapper
is absent from the module dictionary before materialization but remains
available through lookup and dir; Rust still performs all six comparisons.
Source review identified concurrent first-use publication returning different
classes. A controlled two-thread test passed on accepted production and failed
on the initial candidate; atomic dictionary setdefault publication fixes it.
Native execution then exposed a read-only slot-descriptor metadata assignment;
normalizing only actual Python functions fixes that separate defect. Both
failed receipts remain preserved. Corrected source `3b1af79` compiled all58
extensions in33 seconds. Standalone factory checks on both interpreters,
seven candidate contracts and the own-GIL fixture passed with clean reaping,
temporary cleanup and unchanged stages. Complete test_functools passed335
with no skips. The renewed standard memory-only calibration passed in226.1 seconds with
all selected module and workload rows neutral. Its verdict is
`20261004T141639Z-calibrate-perf-rust`, SHA256
`a7253086be588567ba049b5525045bb81c3f29dec2cfa781882d49c0a8ea1a73`.
The first standard two-run eleven-module/all23-workload comparison REJECTED
in263.3 seconds: every module memory classification was neutral, and catalog
request, compileall, reordered diff and zlib streaming RSS regressed in both
runs. There were no output mismatches or unstable metrics. Verdict is
`20261004T142109Z-perf-rust-vs-perf-plistlib208`, SHA256
`5c2ba5f3fd6ee69cf5c7dc21e4a0578a702e23161af6c99cf44bded0a4a52f91`.
No higher-resolution comparison, unchanged retry, clean qualification, broad
gate, full suite or adoption follows. This closes the standalone functools
class-deferral experiment; distinct CSV and zlib class owners remain separate
source prospects. Accepted goals are unchanged.

CSV writer-class experiment217 defers only the private _RustWriter type;
reader-only CSV imports, including the catalog JSON export module, do not
construct its class, methods or property. Attribute lookup and dir preserve
private discovery; deprecated-version lookup and missing-name errors remain
unchanged. Source `8e1d414` built all58 helpers incrementally in34 seconds.
Accepted public writer behavior passed, the accepted ownership test failed at
the expected eager-class assertion, and four candidate cases passed. Complete
test_csv passed134 tests with four skips. The first standard two-run seven-
module/all23-workload memory screen REJECTED: CSV load0.953x and working1.000x
were neutral; catalog JSON export RSS0.999x was neutral. Catalog request,
mostly-equal diff and wheel-read RSS regressed in both runs. Verdict is
`20261004T143509Z-perf-rust-vs-perf-plistlib208`; there were no mismatches or
unstable metrics. No unchanged retry, higher-resolution comparison, clean
qualification, broad gate, full suite or adoption follows. Accepted goals are
unchanged. Source review of the separate zlib stream-type experiment218
identified late default evaluation; installer-time bindings and staged-source
fixture selection were corrected before native execution.

Zlib stream-type experiment218 passed twelve native cases and complete
test_zlib (85 tests, two skips). Its incremental build took33 seconds. The
first standard two-run seven-module/all23-workload memory screen REJECTED in
236.9 seconds: zlib load1.001x and working1.000x were neutral; zipfile load
and catalog request, catalog URL, compileall and reordered-diff RSS regressed
in both runs. No mismatches or unstable metrics occurred. Verdict
`20261004T144944Z-perf-rust-vs-perf-plistlib208` SHA256 is
`b0735a24978f83194bf7a2bde5c0180fad6caaccc53ea86b2959589840877e31`.
The stage is preserved in results/zlib218-original with digest
`460b211b7553e3bcdb14de4311a008002b6db7819fee1624e943f9b8a47008d4`.
No unchanged retry, clean qualification, broad gate, full suite or adoption
follows. Candidates212–218 produced no replicated target improvements or
adoptions; their first screens consumed1,665 seconds altogether.

The original fresh-decompressor copy failure is a real accepted-runtime bug,
not an invalid test. An ordinary three-stage observation established that
pristine C passes copy(), copy.copy() and copy.deepcopy() before input, while
both accepted Rust and218 fail all three with inconsistent-stream-state
errors. Compressor copies pass on all three stages. The pinned zlib-rs
inflate-copy implementation rejects a null output pointer even when output
capacity is zero. Separate failing regression641e569 is preserved;219 is a
distinct correctness fix from accepted source, without218's rejected class
deferral. No memory saving is claimed for this bug or its pending fix.

Correctness219 source `cc98605` compiled incrementally in34 seconds, verifying
all58 helpers. Independent source review established that the copied native
state retains no stack-stream backpointer. Four runtime regressions passed
on pristine C and219; accepted Rust passed active-copy behavior and failed
the three pristine-copy operations as expected. Complete test_zlib passed
85 tests with two skips. Native receipt SHA256 is
`00857d7d304ea544df6e6183db8efca63f0ffb2d46c4b98207493a3fc5918080`.
Memory qualification and complete integrated correctness remain pending;
the candidate is not adopted and accepted goals remain unchanged.

After220's harness change, fresh six-module/all23-workload memory-only
calibration passed in225.6 seconds with full sampling. Verdict
`20261004T151101Z-calibrate-perf-rust` SHA256 is
`a9c6019677f333843901e8aeed0d246ca1addf0a9775441978facce28f0a2b22`;
harness SHA256 is
`968693ccc6db5cb935f219a8db6f9b15cd62c0996c87335a3b70fecfd732c90c`.
Correctness219's first memory screen then REJECTED in169.3 seconds after
zlib decoding RSS regressed1.012x in both runs. It stopped after that
workload's second observation, preserving the first run's remaining raw
data and publishing no replicated module-memory claims. Verdict
`20261004T151537Z-perf-rust-vs-perf-plistlib208` SHA256 is
`5dd00cb662089fcac950bb5cc6d3bc5dc0bac9e5b11e7e17afbcb5bb6b5b176e`.
No unchanged retry or qualification follows; the corrected source remains
preserved but unadopted. This establishes real early rejection, not a
controlled speed comparison with earlier candidates.

The separate post-logging region diagnostic completed four fresh processes
and twelve external observers with matching outputs and successful cleanup.
Original185 and canonical accepted source had identical printed allocated
bytes/counts (3509KiB/3036), but original185 retained384/416KiB more malloc-
zone residency. Dirty stage-image bytes matched; canonical image residency
was16KiB higher. This locates the retained differential in malloc-zone
fragmentation rather than extra dirty images, without proving its cause.
The maps describe post-output parked processes; measured counters were
captured before parking, without tracing or heap inspection. It is diagnostic
evidence only and cannot overturn a rejection. The report in
results/logging-post-driver-attribution212 has SHA256
`0824e0492cf90ccc3f8ccd2c137968c6759fe17c048a46669da886999bfb9d56`.

### Mimalloc experiment closed by the user (2026-10-03)

The broad Rust-heap mimalloc candidate is **rejected and closed**. Source
`5a6129def99f135082bf575bc38a891c5c08d849` routed Rust heap fallbacks through
one versioned, typed API to CPython's existing bundled mimalloc 2.1.2,
preserving Python's allocator defaults and the existing Rust scratch arenas.
It introduced no new native dependency or production change.

The clean 58-extension build passed. Eleven complete focused suites ran
2,417 tests with 371 skips; the full suite ran 50,158 tests with 2,791 skips
and zero failures. The **43 additional individual skips remain unexplained**;
this is not full correctness qualification. Provider lifecycle, cross-image
ownership and allocator fixtures were prepared but not executed.

After exact current-harness alignment, self-calibration
`20261003T185634Z-calibrate-perf-mi150` passed for four modules and all 23
workloads. Its first and only two-run exploratory comparison,
`20261003T190116Z-perf-rust-vs-perf-mi150`, **REJECTED** four replicated memory
regressions:

| Memory guard | Candidate / incumbent |
| --- | --- |
| `bz2` load footprint | 1.082478x |
| `difflib_unified_reordered` peak RSS | 1.015319x |
| `gzip_extract_1m` peak RSS | 1.012620x |
| `zlib_decode_1m` peak RSS | 1.012046x |

No metric improved, outputs matched, and no metric was unstable. Both runs
used the current `f741f178` harness, standard sampling, memory-only verdicts
and matched prefixes/executable paths. CPU, timing and quietness were not
requirements. Verdict SHA256 is
`ff55e58e190e7882d2e0018bac5930afd549b2c703a635df472e3fbf43cb28b0`;
independent saved-output audit SHA256 is
`a9c0faa1f4a87d83b9e5f344667efc07631b23bd8b5086f785fb86012788057c`.
These observations establish the rejection, without attributing the
regressions to a particular allocator mechanism.

Two supporting host-only preparations needed corrections: an initially
incomplete input-pin closure was fixed before execution; the first executed
capture failed because the configured Makefile has no `SYSCONFIGDATA_NAME`
variable. The corrected capture derived the installed filename from the
actual install rule and passed its source/resource/stage equality checks.
This qualifies that capture only, not the provider's native behavior.

The separate zstd-only callback candidate `7ca960bfb3f5dc2e94dfa03ee397f72cc9a71e87`
passed source review and setup/doctor checks. Its clean build was interrupted
at the user's cancellation and exited 130; no correctness suites or memory
comparison ran. It has no measured rejection or memory benefit.

The user ended all mimalloc work. Paired skip diagnostics, provider native
qualification, zstd callbacks, page-extension tuning and further experiments
are canceled. Sources, reviews and actual receipts remain preserved; no
mimalloc change was accepted or integrated, and memory goals remain open.

### Other closed memory experiments (2026-10-03)

The zlib EOF-trailer repair is qualified as a correctness change, with no
memory-saving claim. Primary source `fc5611c` passes a clean 58-extension
build, both public and direct Rust capsule-copy regressions, and the complete
default suite: 50,158 run, 2,748 skipped, zero failures. Flush now preserves
the existing unconsumed-tail state after moving its input buffer, matching
the native C behavior without cloning the input. Fresh memory-only calibration
`20261004T040812Z-calibrate-perf-rust` is CALIBRATION-OK. The two-run standard
primary gate `20261004T041157Z-perf-rust-vs-perf-correct158` is NEUTRAL for
zlib load/working peak and all 23 workload RSS guards, with no mismatches or
unstable metrics. The original module/workload memory goals remain unresolved;
this qualification does not change their accepted counts. The incumbent build
was refreshed at main `f2ba588`: clean 58-extension build, both installed
regressions passed, and all 50,158 default-resource tests passed with 2,748
skips. Its six-route/all-workload memory-only self-calibration passed.

Source `cd43345` compiles the existing typed CPython bindings against Rust
`core`, then removes Rust `std` from the typing, threading, UUID, collections,
SQLite and ipaddress helpers. Host-side binding generation still uses `std`;
target declarations retain their original types and layout through core
aliases. UUID retains its OS entropy path and uses borrowed parsing and
fixed-size formatting buffers. The combined clean build verified all 58
extensions in 229 seconds. Thirty-one focused suites passed 10,348 tests with
582 skips, and all six native fixture groups passed. Two initial fixture
expectations were corrected after identical failures on the accepted build:
UUID retains its existing subinterpreter restriction, and public SQLite
decode errors remain OperationalError. The first two-run standard memory-only
screen `20261004T044903Z-perf-rust-vs-perf-core-batch168` REJECTED replicated
compileall RSS (1.017x) and catalog request-path RSS (1.013x) regressions.
UUID load improved to 0.870x; the other five targets and all fourteen working
peaks were neutral. The batch is closed without redraw or full qualification.
No saving or goal completion is accepted. The UUID-only source branch passed
a clean build, 4,096 focused tests with 158 skips, and five native fixtures.
Its first replicated screen left UUID load neutral (pooled 0.887x), with all
23 workload RSS guards neutral. The sole replicated improvement was typing
load (0.961x); typing's helper source is unchanged but its shared binding
dependency changed, so the improvement is unattributed. The clean primary
build at `c131bf7` verified all 58 extensions; eight focused suites passed
4,096 tests with 158 skips and five native fixtures passed with an unchanged
stage. Its first primary screen `20261004T052400Z-perf-rust-vs-perf-uuid-primary164`
improved UUID load in both runs (0.885x pooled), with all 23 workload RSS
guards neutral and no mismatch or unstable metric. Complete default-resource
correctness then passed 50,158 tests with 2,748 skips in 512 seconds. Broad
memory acceptance remains pending, so this is not yet an accepted saving or
goal completion. The separate algorithm-only UUID variant, retaining the
original runtime, was rejected by replicated logging load regression
(1.049x); UUID load and all 23 workload RSS guards were neutral. Neither
variant establishes accepted goal completion. Fresh incumbent self-calibration
`20261004T043812Z-calibrate-perf-rust` passed for all six targets and all 23
workloads before the screen.
The initial typing/threading link failures were corrected by explicit system
library linkage. UUID's feature change also required Cargo to remove twelve
unreachable packages from its lock; retained versions/checksums are unchanged,
and locked offline fetching passes. Individual source branches remain available
for isolation if the combined memory screen rejects the batch.

Three distinct allocation candidates have clean builds, focused correctness
evidence and completed first replicated memory screens:

- HTML source `689d18e` defers the 144-line Python parsing fallback until it
  is called, preserving live parser globals, callbacks and the Rust scanner.
  Seventy focused tests and four native/fallback fixtures passed. The private
  fallback implementation's code location and traceback gain a wrapper frame.
  Its first screen was NEUTRAL for HTMLParser, regex and all 23 RSS guards;
  the candidate is closed without integration or another draw.
- Codecs source `06cf0f4` encodes Unicode scalars directly into exact-sized
  Python bytes without caching UTF-8 on the input. The accepted helper first
  failed the retained-size fixture by growing a Latin-1 string by 6,001 bytes;
  the candidate passes all six fixtures and 2,864 focused tests with 364 skips.
  Its first screen improved codecs load in both runs (0.807x), with io and
  all 23 workload RSS guards neutral. Final qualification remains pending.
- Marshal source `a97723c` obtains uncached deoptimized bytecode through a new
  private C getter, `_PyCode_GetCodeForMarshal`, retaining existing cache
  identity when one already exists. Wire reference flags and owner cleanup
  are preserved. The accepted helper retained 39,424 bytes in the regression;
  the candidate passes that invariant and all six other wire, alias, ownership,
  specialization and monitoring cases. Nine suites passed 3,275 tests with
  75 skips. No public marshal API or capsule layout changes.
  Its first screen REJECTED replicated pickle load regression (1.053x);
  marshal load and all 23 RSS guards were neutral. The source is excluded.

Each clean build verified all 58 Rust extensions. Correctness and logical
allocation reductions alone establish no physical memory saving or completed
goal. To avoid separate full qualification cycles, primary batch source
`4d8bc80` combines only the surviving UUID and codecs changes. Its clean build
verified 58 extensions in 224 seconds; thirteen selected suites expanded to
21 files and passed 6,960 tests with 522 skips. All eleven native fixtures
passed with an unchanged stage. Its first sixteen-module/all-workload screen
`20261004T061215Z-perf-rust-vs-perf-memory-batch180` REJECTED replicated
logging load regression (1.059x); codecs load improved (0.807x), UUID load
and all 23 workload RSS guards were neutral. No full qualification or unchanged
redraw follows this rejection. A distinct primary source `37fd67e` now isolates
only the three codecs files against accepted main `f2ba588`, preserving the
original UUID, binding, runtime and lock sources. The isolated clean build
verified all 58 extensions in 241 seconds. Five selected suites expanded to
13 files and passed 2,864 tests with 364 skips; all six native fixtures passed
with unchanged stage guards. Its first standard two-run screen
`20261004T062812Z-perf-rust-vs-perf-codecs-primary181` improved codecs load
(0.801x), with io, logging and all 23 workload RSS guards neutral, no mismatch
and no unstable metric. Complete default correctness then passed all 50,158 tests with 2,748 skips
in eight minutes three seconds. The all-71/all-23 standard two-run memory-only gate
`20261004T064444Z-perf-rust-vs-perf-codecs-primary181` REJECTED replicated
argparse load regression (1.030x) and startup RSS regression (1.011x). Codecs
load improved (0.809x), while working peak, logging and the other 22 workload
RSS guards were neutral. The isolated candidate is closed without another
draw or incumbent change. Correctness and target improvement do not establish
accepted saving or goal completion.

The next regex hypothesis borrows the canonical compiled pattern's SRE
instructions rather than retaining a second Rust engine on the public route.
Four independent source components cover the C/Rust bridge, execution frames,
allocation-free atoms and constants, and native differential fixtures. Pure
execution passed 13 tests and 9,583 comparisons against controller-generated
canonical programs. Those checks do not establish native 3.16 qualification.
The accepted build also reproduced a whitespace correctness bug: native
compiled search matches U+001C with `\\s`, while the current public Rust path
returns no match. The new native fixture retains that regression. The integrated
candidate's clean build verified all 58 extensions in 239 seconds. All ten
native contract fixtures passed, including the whitespace regression. Twelve
of thirteen focused suites passed; test_re exposed four errors on empty
complement classes. Their canonical programs contain FAILURE followed by an
unreachable SUCCESS, which the initial validator rejected. The executor
repair validates those unreachable instruction tails without changing FAILURE
semantics or narrowing supported coverage.
The corrected final source `c5bd2ba` then passed a clean 58-extension build,
all thirteen focused suites (3,756 tests, 75 skips), and eleven native fixtures,
including 35 Rust-dispatched empty-complement searches. Its first standard
memory-only screen is running; no full qualification precedes a survivor.
The first two-run standard screen
`20261004T064050Z-perf-rust-vs-perf-sre176` improved re load to 0.696x
[0.676, 0.722], with working peak and all six dependent-module guards neutral.
All 23 workload RSS guards were neutral or improved; three Django rows
improved (0.988x–0.989x). No mismatch, regression or unstable metric occurred.
Primary source `34c1263` is prepared with all nine overlay files byte-identical
to the clean-qualified donor. After the codecs gate rejected its separate candidate, the primary regex
clean build started against unchanged accepted baseline `f2ba588`. No new memory goal is marked
complete; exploratory savings are not accepted goals.

Zstd provider sharing is a distinct source mechanism in an isolated worktree
based on accepted main `f2ba588`. It retains both module images while binding
Rust to the exact existing C zstd 1.5.7 dylib, eliminating the bundled second
engine. Ordinary pkg-config selection alone still links the available archive,
so explicit dynamic-provider build glue is required. Valid legacy-frame
acceptance may expand to match pristine CPython and must be tested and
documented. There is no new native library or allocator change. Source `6b47d2` is committed with provider and codec fixtures. Existing Rust
package versions and checksums remain unchanged; no physical saving or goal
completion is claimed. Setup and the original-C legacy-frame oracle passed:
the original and incumbent C decoders return abc at EOF, while accepted Rust
raises Unknown frame descriptor. Four accepted baseline behavior fixtures
also passed. Its clean build is now running alongside regex, with three jobs
per builder. No memory comparison precedes clean correctness verification.

The proposed datetime fixed-field transfer was closed before production edits
or a build: archived source `29a8ba8` already eliminated the same Unicode
substring, Rust Vec and Python tuple/integer carriers while retaining all seven
Python methods. Its historical screens were memory-neutral. The prepared new
baseline fixtures remain unrun. A saved mechanism index is being assembled to
prevent repeated source briefs from reaching the build queue.

Regex no-inlining source `d043b476` removed only the forced-inlining feature
while retaining the existing cache, DFA, one-pass, backtracking and literal
features. Its actual staged target feature graph matched that selection; the
clean build verified 58 extensions, eighteen complete suites passed 6,839 tests
with 491 skips, and seven existing native routing/eligibility fixtures passed.
The first and only current-`f741f178`, two-run standard memory-only screen
`20261004T034156Z-perf-rust-vs-perf-ri161` **REJECTED**: compileall RSS regressed
to 1.013x and email working peak to 1.034x. Regex load (1.010x) and working
peak (1.000x) were neutral. Improvements in unchanged datetime and shlex routes
remain unattributed. No full qualification, integration or unchanged retry
follows. The smaller feature selection established no physical regex saving.

The fourteen-root variant, source `aeaeb3`, added UUID and decimal to that
closed shared-runtime selection. Its clean build verified 58 extensions and
all sixty expected compiler-unit occurrences; thirty-one complete focused
suites passed 12,334 tests with 665 skips and zero failures. Its first and
only current-`f741f178`, two-run standard memory-only comparison
`20261004T033424Z-perf-rust-vs-perf-shared-expanded159` **REJECTED** replicated
RSS regressions in `compileall_source` (1.011x) and `gzip_extract_1m` (1.012x).
All twenty-seven measured modules' memory rows were neutral; UUID's 0.925x
and decimal's 0.928x pooled load estimates did not establish replicated
improvements. The other twenty-one workload RSS guards were neutral. No
full/native qualification, integration or unchanged retry follows.

Expanded shared-runtime source `49232b3` completed a clean build with 58
verified extensions and fresh proofs for all twelve selected standalone roots.
Twenty-five complete focused suites passed 10,473 tests with 533 skips and zero
failures. After aligning the diagnostic controller to current `f741f178`, its
two-run standard memory-only comparison
`20261004T032802Z-perf-rust-vs-perf-shared-expanded155` **REJECTED**: asyncio
load footprint regressed to 1.021x and `catalog_json_export` RSS to 1.011x in
both runs. SSL load improved to 0.949x; every selected standalone load target
and all working peaks were neutral. The comparison took 420 seconds, matched
runtime prefixes and executable paths, and had no output mismatch. No full
suite, native qualification, integration or unchanged retry follows. These
current-harness regressions also remain guards for the distinct experiment
that keeps the core carrier on its original compiler/runtime policy.

Shared-runtime source `2da6e40` completed an ordinary clean build with 58
verified Rust extensions and 14 complete focused suites (5,545 tests, 160
skips, zero failures). Its ownership proof binds the original thirteen
carrier dependencies, twelve builtin registrations, four I/O exports and
the shared provider. Build-driver regressions for verbose Cargo receipt
output and repeated producer/move calls were reproduced and fixed.

The two-run, standard-profile memory-only exploration
`20261004T023704Z-perf-rust-vs-perf-shared-normal156` **REJECTED** a replicated
`tempfile` load-footprint regression: 1.061x [1.048, 1.084]. All other twelve
measured module memory rows and all 23 workload RSS guards were neutral;
no memory metric improved. No full-suite, normal-stage embedding/relocation
qualification or integration follows this result. The expanded standalone
experiment remains separate and must guard this known tempfile regression.

Collections keyword source `79db5aa` deferred the private `keyword.iskeyword`
binding until first namedtuple validation. Its clean build verified 58 Rust
extensions; three complete focused suites passed 256 tests with one skip,
and three owned regression cases passed. The single-run quick memory-only
exploration `20261004T021235Z-perf-rust-vs-perf-ck157` found no collections
load or working-peak improvement (both 1.000x). Four workload RSS rows were
worse in that run, giving an exploratory REJECT; these are not replicated
regressions or acceptance evidence. The candidate is closed without full
qualification, integration or an unchanged retry. Deferring the import
changed private capture timing without demonstrating physical savings.

Regex source `c81b21257d2e449d9c4e70a2d60f42860bca199f` reduced the
acceptance-hint memo table from 512 to 64 slots while preserving its 60 KiB
scratch arena, engine configuration, FIFO cache and allocation domains.
The clean 58-extension build, four complete affected suites (582 tests,
60 skips) and three native Python cases passed. Fresh self-calibration passed.
Its sole two-run, matched-prefix/executable memory-only exploration,
`20261003T201827Z-perf-rust-vs-perf-rm154`, was **NEUTRAL**: all four modules'
load and working metrics and all 23 final workload RSS classifications were
neutral. Three workloads were worse in one run only; no replicated regression
or improvement occurred. The smaller logical table did not demonstrate
physical savings. Verdict SHA256 is
`040ff03d9b6e074f4e1db8bdd74374ad5e82564cc7b257721a9333024f6b3397`;
independent saved-output audit SHA256 is
`fd850497e40c4b0acf0fb16fe5c40e3fcf7bb49494b26fbfbdb9e7e7cd4c5e6a`.
Private Rust unit tests and full qualification remain unrun; no unchanged
retry or integration follows the neutral result.

Collections source `a488f1e7b7fb03403288d0ddd63a5f1fe6c0e9e3` isolated the
immutable loader-export change previously tested in an eleven-route batch.
It passed a clean 58-extension build and seven complete suites (666 tests,
three skips). Fresh self-calibration passed. Its first and only two-run
memory-only exploration, `20261003T205555Z-perf-rust-vs-perf-collections-singleton`,
**REJECTED** eleven replicated workload RSS regressions: catalog request/search,
compileall, both difflib workloads, gzip, process pool, both base64 workloads
and both zlib workloads (1.010–1.017x). Collections load and working peak were
neutral; no metric improved. Four additional workload rows were worse in one
run only and remained neutral. Verdict SHA256 is
`9d9dcaeb4b5b2ca01acbca74b3ab4e5a9b4b7b6acd565e1affd6af766be0d698`;
independent saved-output audit SHA256 is
`b6645a826ed82ec641483f33dcf4b9c06c14ec65e5aa7127e3ce227094b0cf2d`.
The singleton resolves the earlier lack of a separate measurement. Native
custom fixtures and full qualification remain unrun; there is no unchanged
retry or integration.

Pickle source `5e7735d57252629c23096bee170d54779003a80e` restored the previously
unmeasured single-parse candidate. It validates and consumes one typed tree,
avoiding an earlier generic validation parse whose tree was already dropped
before the second parse. This targets allocation high-water and retention.
Private admission can become narrower;
the existing C fallback preserves public behavior. A clean 58-extension build,
seven complete suites (4,085 tests, 121 skips) and four fresh native fixtures
passed. Fresh self-calibration passed. The sole two-run memory-only exploration,
`20261003T211427Z-perf-rust-vs-perf-pickle-singleparse137`, was **NEUTRAL**:
pickle load was 0.984x with interval [0.943, 1.053], working peak was 1.000x,
and all 23 workload RSS classifications were neutral. No physical benefit
was demonstrated. Verdict SHA256 is
`90655887e45583c2e7bd1bb10820a34beb2c763b33c903705e80f6da8fea1e78`.
Independent noise-aware saved-output audit SHA256 is
`61c5eeb74d7639181a82bd93eaa1c346ba1690a6171ee11ec93f2cd65611b661`;
it verified 40 module samples, 92 workload summaries and 600 saved memory/output
payloads. Warmup outputs were not separately retained. Full qualification
remains unrun. There is no unchanged retry, absolute-goal resampling or integration.

Inspect source `dbf4f19e4cc929aef29e9b34118ee899a7edbeba` deferred
`importlib.machinery` with a lazy import. Its clean build, nine affected
complete suites (4,325 tests, 26 skips) and five targeted fixtures passed.
Fresh self-calibration passed. The first two-run memory-only exploration,
`20261003T183154Z-perf-rust-vs-perf-im151`, rejected seven replicated workload
RSS regressions: compileall, both difflib workloads, gzip extraction, small
base64, zlib decoding and zlib streaming. Inspect load (0.989x) and working
peak (1.000x) were neutral; no metric improved. Verdict SHA256 is
`73305de145a5d6043d3e2939489a4eb7a513a95d326a97d2829393fa4849f9f4`.
The source and receipts are preserved, with no unchanged retry, full-suite
qualification or integration.

The unchanged regex scratch-arena experiment with a shared abort-strategy
Rust standard library also closed. Both matched driver cases passed all
1,023 lifetime/local checks and exited cleanly. The static control's
non-inline `std::env::current_dir` allocation stayed in its scratch arena;
the shared case's allocation was outside that arena, with the caller address
in the canonical shared library. This fails the preserved allocation-domain
requirement for that tested caller. Symbol/load observers and the final
runtime receipts passed independent audit
`15251852f72146a9141cfa0bae64d43fb254649f9da0b8318f9bc85969306b85`.
No memory measurement ran, and this result does not establish every caller's
allocator behavior. No retry or allocator redirection follows this candidate.
The independent static-carrier experiment remains open.

The first all-71/all-23 memory-only gates for source75 (`perf-co75`),
source76 (`perf-al76`) and source79 (`perf-se79`) rejected their candidates
after clean release builds and complete correctness suites. Source79's
replicated regressions were warnings load (1.052x), reordered-difflib RSS
(1.011x) and startup RSS (1.013x). Its verdict is
`20261002T194029Z-perf-rust-vs-perf-se79`, SHA256
`3c3940fbd33ffded20b6e4d79a9cf4500a9849312db1ab8b573f08d27d091726`.
CPU, timing and quietness were not checked. Sources, stages and first
verdicts remain preserved; main and incumbent `7cf55a6` remain unchanged.

Source78's first and only primary memory comparison also **REJECTED**:
`20261002T204422Z-perf-rust-vs-perf-pb78`, verdict SHA256
`4360d85bb3be1adced6ce03ccef60268c01ee69173c0738127213e85952505d7`.
Its two-run all-71/all-23 memory-only comparison used matched prefixes and
executables. Struct load improved to 0.975x, but 16 module-load guards and
two workload RSS guards regressed (compileall 1.012x and reordered difflib
1.011x). Observed textwrap, threading and UUID wins are not attributed to
the source change. The clean 57-extension build, complete correctness suite
(50,158 run, 2,748 skipped), both native import orders and four semantic
contracts passed. The source and evidence remain preserved; no improvement
was accepted and no unchanged retry is authorized.

Optimize algorithms and memory layout; do not write assembly or SIMD
optimizations. Any Rust crate may be adopted in the isolated lane, retaining
pinned versions/checksums and recorded licenses. Preserve Rust coverage and
correctness throughout both phases.

Source93b's first and only primary memory comparison **REJECTED**:
`20261002T222929Z-perf-rust-vs-perf-cc93b`, verdict SHA256
`a988a3f28f09fb23c2469b1fc933682182eabfbfc74a6df54f43e7f12958c241`.
The two-run rigorous all-71/all-23 comparison used matched prefixes and
executables. Threading load improved to 0.750x; 17 module-load guards
regressed. All 23 workload RSS rows were neutral, with no output mismatch or
unstable metric. The observed datetime, decimal, textwrap and typing load
improvements are not attributed to changes in those helpers' source.
The clean 58-extension build, full suite (50,158 run, 2,748 skipped, zero
failures), artifact proof and 63 behavioral units passed. The first Darwin
link failure and the corrected metadata-audit parser failure remain
preserved alongside successful qualification. CPU, timing and quietness
were not checked. No improvement was accepted; main and incumbent remain
unchanged. Sources, stages and the first verdict remain preserved, with no
unchanged retry authorized.

Source95's first and only primary memory comparison **REJECTED**:
`20261003T001010Z-perf-rust-vs-perf-cp95`, verdict SHA256
`0a7bfcdd1a88347610c7c8e7e81dd506d04cd4c6e7de26435b81f37c9a93a02d`.
The two-run rigorous all-71/all-23 memory-only comparison used matched
prefixes and executables. Eighteen module-load guards regressed; every
working peak and all 23 workload RSS rows were neutral. Decimal load
improved to 0.793x, but the batch remains unaccepted. The observed textwrap,
threading and typing improvements are not attributed to the three new helper
implementations. Outputs matched and no metric was unstable. The clean
58-extension build, full suite (50,158 run, 2,748 skipped, zero failures),
88 supplemental behavioral units and 35 artifact checks passed. Preserved
controller preparation failures did not launch duplicate target tests.
CPU, timing and quietness were not checked. Main and incumbent remain
unchanged; the source, stage and first verdict remain preserved without
an unchanged retry.

The next candidate isolates those three helper implementations from the
rejected common-binding and carrier changes. Source101 passed independent
source and lock review at `bc82da1`: only binascii, decimal, hashlib and
their three local lock dependency lists differ from the accepted overlay.
Source101 then completed fresh primary qualification at `0335db3`: clean58,
the full 50,158/2,748 suite, 25 native units and 13 artifact observations
passed independent audits. Its first and only rigorous all-71/all-23
memory-only comparison **REJECTED**:
`20261003T012923Z-perf-rust-vs-perf-sa101`, verdict SHA256
`2bde57d9ce5039616b7e7df4390703b97dd09999f4c0c8155ae166223c801cfe`.
Seventeen module-load guards, logging working peak (1.643x), compileall RSS
(1.015x) and serialization RSS (1.014x) regressed in both runs. The three
changed helpers' load and working metrics were neutral. Threading load
improved to 0.750x, but its source was unchanged and that observation is not
attributed to this candidate. No outputs differed and no metric was unstable.
Removing Rust std from these three DLLs established no accepted memory win.
Main and incumbent remain unchanged; source, stage, preparation failures and
first verdict are preserved without an unchanged retry. CPU, wall time and
quietness were not checked.

The algorithm and retained-object candidate across 14 routes completed fresh
primary qualification at `58e6f3e`: clean58, full 50,158/2,748, 47 fresh
supplemental cases and 11 artifact observations passed independent audits.
Its first and only rigorous all-71/all-23 memory-only comparison **REJECTED**:
`20261003T023244Z-perf-rust-vs-perf-ag106`, verdict SHA256
`87ec7b31dfcd9bc698c5fbab72734f5459366095d110a3a0dfce6be13da52932`.
Fourteen module-load guards, startup RSS (1.015x) and multiprocessing RSS
(1.013x) regressed in both runs. Typing load improved to 0.969x; its source
changed, but the rejected batch establishes no accepted improvement.
Textwrap, threading, urllib.parse and UUID load also improved with unchanged
sources and remain unattributed. Every working-peak metric was neutral;
zstd's peak remained 327,680 bytes on both sides. Decimal's pooled load
ratio was 0.862x but did not replicate an improvement in both runs.
Outputs matched and no metric was unstable. Main and incumbent remain
unchanged; the source, stage and first verdict are preserved without an
unchanged retry. CPU, timing and quietness were not checked.

The separate narrow UUID/HMAC, struct, marshal and JSON candidates were
composed at `c2c2d93` with accepted common bindings and carrier preserved.
Fresh primary qualification at `0157242` passed clean58, the full
50,158/2,748 suite, all five native qualification lanes and 17 scoped
artifact captures. Its first and only rigorous all-71/all-23 memory gate
**REJECTED**: `20261003T035457Z-perf-rust-vs-perf-sp114`, verdict SHA256
`cdee9b513434ddde700c9933c6fbe14017363c455b62c5ff3bfe9ce94efd992c`.
Replicated regressions were `_strptime` load (1.037x), warnings load
(1.072x), logging working peak (1.571x) and URL-normalization RSS (1.012x).
UUID load improved to 0.843x in both runs; the rejected composition does
not establish an accepted UUID improvement. HMAC, struct and JSON memory
were neutral; marshal load worsened in only one run. Threading's observed
load improvement has unchanged source and remains unattributed. Outputs
matched and no metric was unstable. Main and incumbent remain unchanged;
sources, stages and the first verdict are preserved without an unchanged
composition retry. CPU, timing and quietness were not checked.

The UUID-only projection at `b7cf5af` restored every other overlay route to
the accepted source. Fresh clean58, full 50,158/2,748, three semantic cases,
one live ABI case and scoped artifact verification passed. Its first and
only rigorous all-71/all-23 memory-only gate **REJECTED**:
`20261003T050216Z-perf-rust-vs-perf-u117`, verdict SHA256
`6cc28ba1dfe75626e26401422d604d505b8688400aa4de7cdb371519aee487d5`.
Twenty-two module-load guards, plistlib working peak (1.125x) and startup
RSS (1.011x) regressed in both runs. UUID's pooled load was 0.923x, but its
runs were improved/neutral, so no improvement qualified. Outputs matched
and no metric was unstable. Main and incumbent remain unchanged; the
first verdict and qualification evidence are preserved without an unchanged
retry. CPU, timing and quietness were not checked.

The datetime-only immutable-export projection at `c2c77ed` completed fresh
primary clean58, full 50,158/2,748, six native checks and scoped artifact
verification. Its first and only rigorous all-71/all-23 memory-only gate
**REJECTED**: `20261003T060151Z-perf-rust-vs-perf-d120`, verdict SHA256
`c0764ff16ab81677a65e7202e39236098b7974e24e7b61c3c20ece65f362ee7c`.
Thirteen module-load guards and ten workload RSS guards regressed in both
runs. Datetime load and working peak were neutral in both runs. Textwrap and
threading load improved with unchanged sources and remain unattributed.
Outputs matched and no metric was unstable. Main and incumbent remain
unchanged; source, stage and first verdict are preserved without an unchanged
retry. CPU, timing and quietness were not checked.

The corrected threading projection at `388a4be` completed fresh primary
clean58, full 50,158/2,748 and six regression cases with unchanged source
and process cleanup. Its first and only rigorous all-71/all-23 memory-only
gate **REJECTED**: `20261003T065737Z-perf-rust-vs-perf-t121`, verdict SHA256
`fca51d4de43c03d48889f8ffdf7b0684af9d8e0e58fdd5ad8a14d63e3248bc35`.
Threading load improved to 0.750x in both runs and working peak was neutral.
Thirteen module-load guards, logging working peak (1.776x) and seven
workload RSS guards regressed in both runs. Textwrap load improved with
unchanged source and remains unattributed. Outputs matched and no metric
was unstable. Main and incumbent remain unchanged; source, stage and first
verdict are preserved without an unchanged retry. CPU, timing and quietness
were not checked.

Ipaddress local-binding, typing cache-metadata, tokenize deferred-grammar
and Decimal immutable-export candidates have completed isolated correctness
qualification. Seven separate shared-helper immutable-export candidates
passed a combined clean58 and full 50,158/2,791 suite; fresh native
qualification continues. SSL's builtin registration requires a legacy
initializer and closed that scoped source hypothesis. The exact 54-file
union of these eleven routes passed independent source review; fresh primary
correctness and memory comparisons remain necessary. These checks establish
no accepted memory improvement.

The eleven-route union at `17a82b0` completed fresh primary qualification:
clean58, full 50,158/2,748 with zero failures, and all eleven native route
audits passed. Its first and only rigorous all-71/all-23 memory-only gate
**REJECTED**: `20261003T083056Z-perf-rust-vs-perf-m136`, verdict SHA256
`7680b8c86ea263e2f0757d81265c7055aa5773b70c6a856f1272dd1375b70bed`.
Eighteen module-load guards and five workload RSS guards regressed in both
runs. All eleven changed routes' aggregate load and working metrics were
neutral; socket load worsened in one run and ipaddress load in the other.
Threading and textwrap load improved with unchanged sources and remain
unattributed. Outputs matched and no metric was unstable. Main and incumbent
remain unchanged; source, stage and first verdict are preserved without an
unchanged retry. CPU, timing and quietness were not checked.

After the terminal gate, `07cb87b` corrected two supplemental test assumptions:
a poisoned socket helper entry is distinct from module absence, and zero-size
module state may have an allocated marker. Those exact corrected fixtures
already passed against the fresh candidate; production code is unchanged.
The measured build remains pinned to `17a82b0`. At `394f6e1`, the harness
began retaining all five raw footprint snapshots after the measured window.
Existing arithmetic, workloads and guards are unchanged. This starts a new
harness epoch requiring fresh memory-only calibration; historical ratios are
not corrected or reinterpreted as acceptance.

Fresh raw-counter-epoch calibration passed at
`20261003T085725Z-calibrate-perf-upstream`, SHA256
`0a1f6e5e269944035b3c1a6eadad6735d57f66ed76e79fbcc1cc4129feeb77d5`:
all 23 workload RSS rows and four module kernels were neutral in both runs.
Bounded two-module diagnostics then self-compared incumbent and candidate
successfully, and compared warnings/threading across the two interpreters.
These exploratory observations establish no acceptance. The candidate's
physical footprint was already roughly 320 KiB higher before the target
module imported. Threading's first growth was 128 KiB versus 96 KiB, with
zero repeated growth; warnings showed larger first growth and variable
repeated growth. Same startup module names and same-length bytecode filename
rewrites do not identify the owner of this difference. The original candidate
rejection remains terminal; no historical ratio is corrected.

External parked-child snapshots subsequently located an extra 192–208 KiB
at startup before ctypes, with identical module sets; the changed Rust struct
helper was absent from every recorded module set. A separate startup-only
region diagnostic passed all process, source and stage checks. In that pair,
candidate footprint was 128 KiB higher, matching extra dirty `Malloc Small`
memory and default-zone fragmentation. Both maps displayed 2,087 default-zone
allocations and 1,778 KiB allocated, with fragmentation 206 KiB versus
334 KiB; these allocated-byte values are rounded. Other displayed region
category totals matched. The saved report is
`rust-cpython/results/startup-region-first-diagnostic/report.json`, SHA256
`632b0ba1cf402a4f29314da958e985329c5702e59b85fb259a32477235208834`.
This bounds a shared allocator hypothesis; it does not establish a general
offset, identify individual allocation owners, or qualify any candidate.

The separate last-empty-pymalloc-arena candidate at `4c4257f` completed
clean58 and focused correctness checks (1,964 run, 348 skipped, zero failures;
four multiprocessing-fork submodules skipped on macOS). A supplemental
allocator-hook regression failed on the incumbent with the expected retained
arena assertion and passed on the candidate in normal and debug modes, with
three allocation/free waves each. The initial fixture incorrectly assumed
`unittest` had not imported threading; its preserved failure was corrected
to assert one active thread, without changing the production patch.
Its first memory-only exploratory probe **REJECTED**:
`20261003T095850Z-perf-rust-vs-perf-a137`, verdict SHA256
`627c84de315e8207ec974d2d52f3e92d584bf7e2f833a6213f9e2f04f93ae0d7`.
JSON load (1.041x) and startup RSS (1.012x) regressed in both runs.
Zstd load improved (0.892x), while working peak remained neutral. The
unchanged candidate will not proceed to full qualification or acceptance.
Main and incumbent remain unchanged. CPU, timing and quietness were not
checked; no memory goal was completed by this experiment.

The supported 4 KiB pool-layout candidate at `97e7c6e` completed clean58,
focused 1,964/348 and native geometry, boundary, realloc, interpreter,
fork and debug checks. Its first full suite had one asyncio stream callback
error; both complete asyncio packages then passed unchanged (2,780/65 each),
and a fresh full suite passed 50,158/2,748 with zero failures. The first
failure is preserved and its cause remains unestablished.
Its first rigorous all-71/all-23 memory-only acceptance gate **REJECTED**:
`20261003T110616Z-perf-rust-vs-perf-p139`, verdict SHA256
`94d6b389bac805abb55e8f42182dd8e34ead401a769ccb81f7eae360efa77999`.
Four module loads regressed
(asyncio, contextlib, csv and tomllib), as did configparser, dataclasses
and logging working peaks. All 23 workload RSS rows were neutral.
Many loads improved in both runs, including base64, datetime and JSON,
but the candidate remains unaccepted. No unchanged retry follows this
gate; main and incumbent remain unchanged. CPU, timing and quietness
were not checked.

The static intern-table pre-sizing candidate at `45e7cf7` completed a clean
58-extension build and focused correctness checks (3,929 run, 390 skipped,
zero failures). The initial focused invocation used the obsolete
`test_unicode` suite name; its import failure is preserved, and the corrected
complete string and neighboring suites passed without source or test changes.
Its first memory-only exploratory comparison **REJECTED**:
`20261003T114444Z-perf-rust-vs-perf-i138`, verdict SHA256
`8af3fcb1e543bc84af0d684801fd8a25114b094f08ed2df36a8bb53da5c4c4dc`.
Warnings load (1.059x) and compileall RSS (1.014x) regressed in both runs;
no metric improved in both runs. The candidate will not receive an unchanged
retry or further qualification. Supplemental native fixtures passed source
review but never executed; actual table counts and replacement traces remain
unproven. Main, incumbent and the accepted memory snapshot remain unchanged.
CPU, timing and quietness were not checked.

The scoped 1024-byte pymalloc-cutoff candidate at `3b99e53` retained
the accepted 16 KiB pools and 1 MiB arenas. Its clean build verified 58 Rust
extensions and complete focused suites passed (2,033 run, 351 skipped,
zero failures). Its first memory-only exploratory comparison **REJECTED**:
`20261003T115749Z-perf-rust-vs-perf-t140`, verdict SHA256
`fd9371f6966ca908431aedff9bc5b7b79406a39c89ac7150b0f422d08e7f4bb6`.
Twelve module loads, two working peaks and eight workload RSS guards
regressed in both runs. Threading load improved (0.625x), but the candidate
remains unaccepted. Native execution bindings passed source review; compiler
and native probes never ran. No full suite, acceptance gate or unchanged
retry follows this rejection. Main, incumbent and accepted memory goals
remain unchanged; CPU, timing and quietness were not checked.

The scoped 256 KiB arena candidate at `4445d8c` retained 16 KiB pools,
the 512-byte cutoff and existing retention rules. Clean58 and focused
2,033/351 correctness checks passed. Its first memory-only exploratory
comparison **REJECTED**:
`20261003T121037Z-perf-rust-vs-perf-a141`, verdict SHA256
`2fd798c0589d2a4cb44ada3225ad2a2d9cd7aa0dd8c2f02be2491f73e903689e`.
Datetime and decimal loads improved (0.646x and 0.857x), as did zstd and
configparser working peaks (0.800x and 0.955x). Asyncio and logging working
peaks regressed (3.062x and 1.701x); all 23 workload RSS rows were neutral.
The unchanged candidate is closed without native execution, full-suite
qualification, or acceptance. Its unexecuted native binding also omitted
a required git input; that source-review gap is preserved. Main, incumbent
and accepted memory goals remain unchanged. CPU, timing and quietness
were not checked.

A separate public malloc-counter embedder diagnostic completed two stage-
specific compiles and two healthy initialization/finalization traces against
the accepted interpreter and preserved candidate136. Its exact live-block
counts and reserved-byte totals matched at all three checkpoints; candidate136
reported 32 more in-use bytes before configuration, after initialization and
after finalization. Initialization added equal reported in-use bytes in
this instrumented context. These counters do not measure physical residency
or establish the earlier vmmap difference's cause. The completed evidence
SHA256 is `108d71c5fb37c68e885f8bb116571c717288315c107c0a83e7dbde4cdb199921`;
no gate, goal, or historical ratio was changed.

The shared Rust regex-key candidate at `6ac55c2` passed clean58 and seven
complete focused suites (737 run, 18 skipped, zero failures). Its first
memory-only exploration **REJECTED**:
`20261003T124015Z-perf-rust-vs-perf-k142`, verdict SHA256
`9b2ee2386156b13cd175f39a5a90adc33d66d89b584f25e14e6d446726309415`.
Both regex memory metrics were neutral; warnings load and six workload RSS
guards regressed in both runs. Supplemental private Rust and Python fixtures
remained unexecuted, and no full qualification or unchanged retry follows.
No accepted memory goal changed. CPU, timing and quietness were not checked.

The scoped 512 KiB arena candidate at `027a84d` passed clean58 and
complete focused suites (2,033 run, 351 skipped, zero failures). Its first
memory-only exploration **REJECTED**:
`20261003T130133Z-perf-rust-vs-perf-a144`, verdict SHA256
`57780fd588a9e62fddc612fbbfad63853a3a0c1258b81f7c62e3c77be6450fb9`.
Asyncio and zstd load improved (0.978x and 0.900x), while logging working
peak (1.793x) and zlib decoding RSS (1.012x) regressed in both runs.
Native execution and full qualification remained unrun; no unchanged
retry or accepted memory change follows. CPU, timing and quietness were
not checked.

The standalone StringIO zero-truncation candidate at `1cdf701` passed
clean58 and complete I/O, logging, pickle and codecs suites (2,693 run,
93 skipped, zero failures). Its first memory-only exploration **REJECTED**:
`20261003T132012Z-perf-rust-vs-perf-i143`, verdict SHA256
`4068c6171e8013103b80b87713f0ca92e6ad95f4a6ea32d8f9df0ea0135d033a`.
Logging working peak improved to 0.571x in both runs, but six workload RSS
guards regressed in both runs. The allocation regression fixtures and full
qualification remained unrun. Source and inert runner evidence are preserved;
no unchanged retry or accepted memory change follows. CPU, timing and
quietness were not checked.

The contextlib lazy-helper activation candidate at `ebc7e9e` passed
clean58 and complete contextlib, import, importlib and asyncio suites
(4,227 run, 80 skipped, zero failures). Its first memory-only exploration
was **NEUTRAL**: `20261003T134055Z-perf-rust-vs-perf-c145`, verdict SHA256
`d08f1313a9551b206a43fec273a2ec49c36b0db2e66d419fc10671f4aaac4547`.
All six module memory pairs and all 23 workload RSS rows were neutral.
No target improved beyond the interval and floor. Native regression execution
and full qualification remained unrun; the unchanged candidate is closed
without acceptance or retry. CPU, timing and quietness were not checked.

The same-meta-engine regex source-owner candidate at `3f977b2` passed
clean58 and nine complete focused suites (810 run, 21 skipped, zero failures).
The staged tree shrank by 21,213 bytes versus the accepted build; this is
file size, not a residency result. Its first memory-only exploration
**REJECTED**: `20261003T135537Z-perf-rust-vs-perf-r146`, verdict SHA256
`1636a388ed9f6150d6071353b67e8cd1324193097f8c20c83a3da7ace095efe6`.
Warnings load regressed (1.051x) in both runs; regex load and working peak
and all 23 workload RSS rows were neutral. Supplemental Rust/Python fixtures
and full qualification remained unrun. No unchanged retry or accepted memory
change follows. CPU, timing and quietness were not checked.

The dense-rank FIFO regex candidate at `726606a` replaces duplicate queue
keys with bounded insertion ranks while retaining the accepted engine,
allocator, mutex and FFI. Clean58, nine focused suites (810 run, 21 skipped),
the full default-resource suite (50,158 run, 2,748 skipped, zero failures),
and three Python plus four Rust regressions passed independent review.
Its first rigorous all-71/all-23 memory-only gate **REJECTED**:
`20261003T154857Z-perf-rust-vs-perf-f147`, verdict SHA256
`05e1aae5129075641d459d83be0fae37b59022ea807778d1a0ec7c8cf3b0b621`.
Concurrent-futures load (1.016x), compileall RSS (1.013x) and gzip RSS (1.012x)
regressed in both runs. Typing and textwrap load improvements are unattributed;
regex memory stayed neutral. Source, correctness and the first verdict remain
preserved, with no unchanged retry or accepted memory change. CPU, timing
and quietness were not checked.

A separate pinned-source shared abort-runtime review verified the official
nightly source archive and 31 vendored package identities with 1,231 file
checksums. Exact compiler sources support abort-mode std linkage, but the
System-only provider repeats rejected cohort75. Custom allocator roots,
staticlib-carrier linkage and canonical runtime installation remain unresolved.
No new producer diagnostic, runtime or source candidate was executed.

The original C UUID and Rust UUID helper image completed primary qualification
at `41b85a6`: clean58, all 50,158 default-resource tests / 2,748 skips,
typed ABI and native provider checks, all semantic fixtures, and two
installer-only replays preserving all 58 Cargo artifacts. Fresh memory-only
self-calibration `20261002T025911Z` passed all 23 workload RSS rows in both
runs. Its first and only all-71/all-23 memory gate,
`20261002T030858Z-perf-rust-vs-perf-uu46`, rejected the candidate despite
replicated UUID load improvement (pooled 0.874812x; working peak neutral).
Replicated regressions were fractions, glob, statistics and warnings load,
plus catalog URL normalization, both difflib workloads and startup RSS.
Outputs matched, no metrics were unstable, and CPU, wall time and host
quietness were not acceptance requirements. Verdict SHA256 is
`895e4a2118549d31b78cbc621b01337495ce5e4805dd74b9ccb17f2e171b8ab7`.
Postflight confirmed unchanged frozen sources, resources, stage bytes and
proof inputs. Main's overlay was restored to incumbent `7cf55a6`; branch
`integrate-uuid-c-rust-image-46`, candidate stage and raw evidence remain
preserved. No retry or accepted memory improvement follows this candidate.
Binascii's original C/Rust image completed primary qualification at `a655f24`:
clean58, the full 50,158/2,748 suite, native provider and semantic checks,
and two installer-only replays preserving all 58 artifacts. Its first and
only all-71/all-23 matched memory-only gate,
`20261002T043832Z-perf-rust-vs-perf-bi45`, rejected it. Base64 and binascii
load and working memory were neutral in both runs; logging working peak
regressed in both runs (pooled 1.357143x). All 23 workload RSS rows were
neutral; outputs matched and no metric was unstable. Verdict SHA256 is
`3a19cbd711bc419a0eb40ac505d813baae146d5b2ddffd4894d998352e64a79b`.
Frozen source, stage and correctness evidence matched after measurement.
Main's overlay is restored to incumbent `7cf55a6`; candidate branch
`integrate-binascii-c-rust-image-45`, stage and raw results remain preserved.
No retry or accepted memory improvement follows this candidate.

Decimal completed primary qualification at `8c7962e`: clean58, the full
50,158/2,748 suite, two fresh observer compilations, 16 native rows and
two installer replays with eight scratch provider/kernel checks. Its first
and only all-71/all-23 memory-only gate,
`20261002T061236Z-perf-rust-vs-perf-de48`, rejected it. Decimal load and
working peak were neutral in both runs (pooled load 0.886957x did not meet
the per-run rule). Replicated load regressions were argparse, configparser,
difflib, glob, importlib.resources, tempfile and warnings. All 23 workload
RSS verdicts were neutral; catalog URL normalization, mostly-equal difflib,
startup and serialization each worsened in one run only. Outputs matched,
no metrics were unstable, and CPU/wall/quiet criteria were excluded. Verdict
SHA256 is `3760cbedd19c07a727f1b1a81f9acd60fbeae5ef381eee5e2807d5b4bd4b288a`.
Post-measurement integrity passed; main's overlay is restored to incumbent
`7cf55a6`. Branch `integrate-decimal-c-rust-image-48`, stage and raw evidence
remain preserved. No retry or accepted memory improvement follows it.

Pickle and socket have passed clean worktree builds, complete affected
suites, native ABI/provider/semantic checks and installer replays. Pickle's
unbound primary templates passed source review with future build fields
unset. Socket's repaired native proof passed 14 baseline semantic checks,
two baseline provider checks and all 16 candidate rows. Two installer
replays plus a copy of their generated shared-extension directory passed
48 native checks and all 50 child-process completion records. These prove
correctness; neither candidate has a primary memory measurement yet.

An earlier private, pinned-source Rust standard library emitted canonical
Cargo-owned abort-strategy `dylib` and `rlib` artifacts. The shared library
SHA256 is `2e04de6fbe46ffd0285bd8362ec6e623f1d5ab548e3247510e4229ee2ae5b7a6`;
its closure is 19 target libraries / 39 files plus four host scripts.
A first default-System consumer compiled with eight actual shared-library
import bindings. Three bounded runtime children passed buffer ownership,
concurrent thread calls and cross-thread handoff, with loaded-image and
resolved-pointer ownership checks and captured successful completion.
Builtin coexistence, relocation/signing and memory savings were unqualified
by those early checks. The later unchanged-arena experiment is closed with
the allocation-domain failure recorded above.

Doctor/status passed on the2026-09-30 resumption. The verified incumbent remains `7cf55a6`
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

An additional opt-in `--matched-executable` requires both `--memory-only`
and `--matched-prefix`. It launches through each fixed home's `bin/python3.16`,
matching executable-path lengths as well as home lengths. The two aliases
remain distinct strings and never change targets while any setup or sample
process runs. Verified stage/executable identities and hashes remain the
original paths; requested and observed launch paths are retained separately.
Module identity fields are emitted after memory snapshots, without changing
kernels, imports, iteration sizing, samples, floors or verdicts. Workload
identity, dependency preparation, bytecode compilation, warmups and sampling
use the selected launch path. Old contexts remain available and unchanged.

The launch-context change passed 157 benchmark tests (16 skips) and 71 Rust
harness tests (13 skips), plus an installed-control identity probe under the
host test lease. Both aliases appeared exactly in `sys.executable`,
`_base_executable` and both prefixes, with unchanged executable hash and
stage fingerprints. Independent read-only review found no blocking issue.
Fresh self-calibration `20261001T083131Z` passed: all 23 workload RSS rows
and collections load/working peak were neutral in both runs. Full
all-71/all-23 control/incumbent snapshot `20261001T083549Z` reads
10 OVER / 15 UNCLEAR / 45 MET / 1 BEYOND, with 16 workload RSS regressions,
three neutral and four improved. Outputs and integrity checks passed; all
observed module launch paths and prefixes matched their requested aliases.
Once-only rigorous classification `20261001T084855Z` resolves five as OVER,
five as MET and leaves five UNCLEAR. Combining applicable rows gives
15 OVER / 5 UNCLEAR / 50 MET / 1 BEYOND. The unresolved routes are base64,
zstd, datetime, decimal, inspect, ipaddress, marshal, pickle, re, socket,
threading, tokenize, typing, uuid and zlib, plus collections, hashlib,
SQLite, SSL and struct UNCLEAR. All 20 module goals and 16 workload RSS
regressions remain required. This snapshot reflects unchanged source and does not
qualify a source improvement. Compiled paths, loader names, bytecode filenames,
mapping layout and host state remain uncontrolled; no physical saving,
historical correction or rejected-source retry is authorized by this change.

Source-only smaller-engine scouting closed the simple `regex-lite`
substitution: parser and compiled-size accounting do not preserve the current
native-support boundaries without further compatibility work. A distinct
`regex-deterministic-memory` lane instead investigates a bounded generic
matcher for deterministic ASCII expressions, retaining the existing Rust
backend for every other pattern. Archived engine construction made hundreds
of System allocations per expression and retained about 52 KiB across five
engine/cache pairs; that is an allocation basis, not physical-page savings.
The lane must first derive a conservative acceptance bound from the pinned
compiler before source edits. Original grammar/nesting, keys, fallback
coverage, Python whitespace semantics and memory guards remain binding.
No benchmark-expression recognition or rejected-engine retry is authorized.

The bounded matcher candidate `2869dc2` passed independent source review,
clean58 verification, four tests of its actual private Rust plan, 24 staged
Python tests and all 13 affected complete suites (4,923 tests / 186 skips).
Its conservative admission proof limits surviving capture indexes as well as
node counts, and rejects zero-minimum variable repetitions before word
boundaries. Plans leave the parser arena by value, then allocate their exact
immutable storage after arena reset; unsupported expressions retain the
existing Rust engine and cache behavior. Original grammar and nesting checks
precede the ASCII whitespace correction. Source/build hashes and stage
identity match. Two standalone Rust test-driver startup failures are preserved;
the corrected driver passed without changing source or staged bytes. The
helper image grows by 17,744 bytes, so no image-size saving is claimed.
Exactly one all-71/all-23 two-run matched-home-and-executable memory-only
exploration `20261001T092145Z` REJECTed the candidate. Regex load improved
0.650x [0.625, 0.714], with neutral working peak, but catalog JSON RSS
1.01054x, email working peak 1.02703x, HTTP client load 1.01413x and URL
parsing load 1.04878x regressed in both runs. Outputs matched and no metric
was unstable; stage and launch identities held. Restoration `82c8a1b`
returns the entire overlay to incumbent `7cf55a6`, retaining the candidate
stage, patch, source and proofs. No retry or primary qualification follows.
The bounded semantic traces matched all four archived outputs and stage
fingerprints. Every phase had zero helper search calls, so neither plans
nor fallback engines were constructed and duplicate search-time parsing was
unreachable. URL parsing did not load the helper. Email had 19 preparation
calls, HTTP client 14 and catalog JSON six, all during imports or first
warmup. Catalog covered its exact 100-operation core and corpus, excluding
the CLI frontend. Pattern classification describes hypothetical admission,
not actual engine construction. The guard causes remain unattributed.

Read-only binary analysis found one extra 16 KiB text page, unchanged
data/TLS/scratch capacities, unchanged exports and binding counts, and
parser functions shifted across page boundaries. Search-only plan code
shares the initializer/preparation page. The longer builder install name
adds 64 load-command bytes. These static facts do not establish resident,
dirty or physical cost. No source improvement is accepted.

An unchanged-source setup diagnostic now uses `/Users/josh/d/py-mem-lane1`,
whose 26-character root matches the primary root, and the same `perf-rust`
build name. It retains the exact incumbent overlay, pins and compiler flags;
no prefix remapping or harness change is introduced. Clean58 verification,
source/installed-artifact comparisons and full suites precede authorization
for one unchanged-source all-71/all-23 memory comparison. This checks build
path lengths left uncontrolled by runtime aliases. It cannot qualify a
source improvement, correct historical verdicts or replay rejected source.
The unchanged build verified all 58 release artifacts. Their code/data
sections, sizes and symbol topology match the primary incumbent; differences
are equal-length root strings, install names and UUIDs. Core code/data also
match, with source/object-path debug records differing. Initial full suites
passed 50,158/2,791. Paired named-skip enumeration then passed 50,158/2,790
on both builds, matching both XML IDs and all verbose skip multiplicities;
three AF_UNIX reasons differ only in equal-length over-limit root spellings.
The old primary 2,748 and initial 2,791 counts remain preserved, with their
historical discrepancy unattributed. There is no current differential
coverage gap. Single unchanged-source comparison `20261001T102746Z` completed
with REJECT: 154 memory metrics neutral, 11 regressed in both runs and none
improved across all 71 modules and 23 workloads. The repeated regressions are
argparse, fractions, json, subprocess and warnings load; logging working peak
(1.719x); and catalog URL, compileall, reordered difflib, startup and streaming
zlib RSS. Outputs and postflight source/artifact fingerprints matched.
Equal build-path lengths and identical code sections did not establish a
neutral context or a physical cause. No retry, correction or source acceptance
is authorized. Read-only audits now inspect iteration sizing and installed
stdlib/setup differences in the retained evidence.

Those audits completed without a causal explanation. All 71 routes used
equal counts on both sides in both runs, including 28 logging iterations.
Installed inventories match: 2,048 Python sources and 6,108 valid checked-hash
bytecode files per side. Generated configuration and bytecode differences
are equal-length root spellings; no missing source, invalid cache or logging
source drift was found. All 138 installed Mach-O files have matching sizes
and layouts, with remaining root, signature and loader metadata differences.
Logging retains names derived from object addresses in its unchanged kernel;
actual address/name populations were not captured. These remaining context
boundaries establish neither a cause nor a correction for the eleven rows.

Further semantic traces of the 20 unresolved modules matched every archived
output. Nineteen never loaded the regex helper; only re used it, with searches
as well as preparation. Thus a prepare-only grammar shortcut has no reached
target in that map and closed without a candidate.

A distinct source-only typing proposal reuses existing core immortal
`__origin__` and `__args__` names through two narrow private C getters;
metadata retains its original string lookup. This could avoid 7,200 of the
archived 7,600 normal name constructions, without a name cache, interning,
module state or identifier mutex. It requires explicit default-visible core
exports for the shared Rust helper, owned-result/error tests, legacy slot
priority and deliberate canonical name-identity alignment. Static lifetime
and semantic design passed independent review. Physical benefit is unknown;
the previous cache REJECT remains binding. Following the nonneutral unchanged
comparison, implementation and correctness qualification are authorized as a
distinct source lane, independently of the setup investigation. Measurement
remains paused pending explicit coordinator review of the context evidence;
no source benefit or guard waiver is inferred from the setup result.

For this distinct source lane, the coordinator authorizes qualification
directly in a temporary primary-checkout integration branch after exact
source review, fail-first regression evidence, clean58 and complete suites.
This deliberately skips the usual worktree explore/gate prerequisite; it
does not use the skill's load-only recovery exception, because the unchanged
setup also regressed working peak and workload RSS. The first and only
changed-source comparison must be a two-run memory-only primary gate over
all 71 modules and all 23 workloads, with verified unchanged incumbent,
matching harness and strict existing floors/output/integrity requirements.
Generic ACCEPT is insufficient: typing itself must improve in both runs,
and every other memory guard must be neutral or improved. Any other decision
ends the candidate without retry; preserve evidence and restore primary main
without replacing the incumbent. This is qualification permission, not
source acceptance or a reinterpretation of either prior REJECT.

Source lane 33 checkpoint `29d39cb` implements that distinct typing boundary.
Its retained-name regression passes pristine control and fails the incumbent;
nine original compatibility contracts pass on the incumbent. Exact source
review and independent review both pass: the original C body is byte-identical
outside three includes and two private getters, and metadata lookup remains
unchanged. Twelve durable contracts include facade ownership/error context,
legacy slot priority and concurrent independent interpreters. Clean build and
assigned complete suites passed in `py-mem-lane2`: clean58, all twelve
contracts and 2,202/9 across eight suites. Primary temporary branch
`integrate-typing-core-identifiers-33` at `5e36b6b` independently passed
clean58, native ABI/6,400-call proofs, twelve contracts and full50,158/2,748.
Fresh primary stage `perf-ty33` preserves earlier stages and matches the
incumbent build-name length. Its first and only changed-source gate
`20261001T111040Z` REJECTed: typing load improved in both runs to 0.905x
[0.879, 0.920], but seven module memory and six workload RSS guards regressed.
Those are _strptime, glob, ipaddress, shutil, urllib.parse and warnings load,
logging working peak (1.597x), both difflib workloads, gzip extraction,
wheel reading, cold zip import and streaming zlib RSS. No output mismatch or
unstable metric occurred. Postflight incumbent, candidate and control
fingerprints passed. Primary main is restored to the exact incumbent overlay;
branches, stages, source patch and raw results remain preserved. No retry,
acceptance or resumed source improvement follows this candidate.

A source-only marshal scout found no retained map or RandomState mechanism:
the incumbent already uses a fixed-hash full-pointer identity table and writes
directly into final Python bytes. A distinct storage proposal removes four
padding bytes per writer slot with one aligned allocation containing full
pointer keys and 32-bit indices. At 4,096 slots the requested size would fall
from 65,536 to 49,152 bytes; physical effect remains unknown. The sampler's
64 KiB load floor clamps each side, not minimum savings. Current marshal load
is about 3 MiB, so an actual 16 KiB saving alone would not clear the 1% judge.
Source-only ownership, growth and failure-atomicity review precedes any lane
authorization. No new source candidate or measurement is authorized yet.

That source-only proof now supports distinct lane 34, `marshal-reference-storage`,
in root-created `py-mem-lane3` from main `abb3420`. One checked, aligned
`PyMem_Calloc` block stores full pointer keys followed by 32-bit values;
probing, index/PENDING bits and owned references remain unchanged. New
allocation and rehash complete before publishing; failure retains old state.
At capacity 4,096, final requested bytes fall by 16,384, cumulative growth
requests by 32,512 and final rehash overlap by 24,576. The kernel establishes
capacity at least 4,096, not an exact final count. All are logical request
reductions, not physical-memory claims. Independent design review passed.
Implementation and correctness qualification are authorized, with exact
source review before a clean build. The coordinator extends the explicit
once-only primary qualification procedure to this distinct lane: no worktree
memory draw, fresh primary `perf-ma34`, clean58 and full suites before a
two-run all-71/all-23 memory-only gate. Marshal itself must improve in both
runs and all memory guards bind. A non-ACCEPT ends the candidate without
retry, while retaining branch/stage/evidence and restoring main. No changed
memory comparison is authorized until source and correctness review finish.

Lane 34 checkpoint `b1ac334` passed private storage/fault probes, four public
contracts on pristine/incumbent/candidate, byte-identical fresh-input encodings,
native capsule routing and own-GIL checks. Its clean worktree build verified
58 release helpers; twelve complete suites passed 3,359/96. Primary temporary
branch `integrate-marshal-reference-storage-34` at `b5546e9`, fresh stage
`perf-ma34`, independently passed clean58, native proofs and full50,158/2,748.
Its first and only changed-source memory gate `20261001T120934Z` REJECTed:
marshal load was 1.029x [1.006, 1.048], worse/neutral across runs, and working
peak stayed neutral. Glob and tomllib load plus compileall and multiprocessing
RSS regressed in both runs. The two unrelated improvements do not satisfy the
marshal requirement. All 94 entities/165 metrics were assessed, with no output
mismatch or unstable metric. Independent verdict review and three-stage
postflight fingerprints passed. Main is restored to the incumbent overlay;
branch, stage, patch and raw evidence are preserved. No retry or acceptance.

Distinct lane 35, `base64-deferred-binascii`, starts in root-created
`py-mem-lane4` from main `a51aa3e`. Valid default conversions use Rust but
currently import the separate C binascii image eagerly. Historical attribution
found 96 KiB resident in that image, including 32 KiB dirty; this is evidence
of a possible owner, not a current physical-saving claim. Checkpoint `4e2e01b`
uses the existing PEP810 lazy-import mechanism and makes native hex errors
import the real fallback module before resolving its current Error class.
Owned module/exception references are released with the selected error protected
against cleanup reentry. No cache, ABI, dependency or algorithm change is added.
Exact coordinator and independent source review passed. Two isolated incumbent
regressions reproduce eager loading and missing Error on a cold direct native
call; helper-independent public output/error contracts pass pristine and
incumbent. Thirteen durable isolated contracts, a clean release build and
complete assigned suites are authorized; worktree memory draws are not.
After qualification, the same explicit once-only primary procedure requires
fresh `perf-ba35`, clean58, native proofs and full suites before an all-71/
all-23 two-run memory-only gate. Base64 itself must improve in both runs and
all memory guards bind. Any non-ACCEPT ends the candidate without retry while
preserving evidence and restoring main. No changed memory draw is authorized
before correctness qualification finishes. Inspect, tokenize, ipaddress,
threading and UUID source-only scouts closed without a distinct new mechanism.

Lane 35 passed clean58, all thirteen contracts and native kernel proofs in
its worktree, with 4,231/45 across seven complete suites. Primary temporary
branch `integrate-base64-deferred-binascii-35` at `e294fe1`, fresh stage
`perf-ba35`, independently passed clean58, the contracts and native proofs,
and full50,158/2,748. Fresh control memory-only calibration `20261001T123716Z`
passed all 23 workload RSS rows plus collections load/working peak in both
runs. Its first and only changed-source memory gate `20261001T124141Z`
REJECTed. Base64 load was better/neutral, pooled 0.933x [0.910, 1.176], so its
required improvement did not replicate; working peak was neutral/worse and
pooled neutral. Startup RSS regressed in both runs to 1.013x [1.012, 1.014].
All 94 entities/165 metrics were assessed: 162 neutral, one regression and
two unrelated improvements, with no output mismatch or unstable metric.
Independent verdict review and three-stage postflight fingerprints passed.
Main is restored to the incumbent overlay; the branch, stage, patch and raw
evidence are preserved. No retry or acceptance. Module/workload goals remain
unchanged. Additional pickle, hashlib and decimal source-only scouts closed
without a distinct retained owner. A socket/SSL source-only design is checking
whether a per-interpreter live-object guard can defer the socket helper while
preserving preexisting C sockets, subtypes and the no-import-during-I/O rule;
no implementation or measurement is authorized for that proposal.

The socket/SSL design now supports source lane 36,
`socket-interpreter-activation`, in root-created `py-mem-lane5` from main
`c218071`. Tests-first implementation-candidate work is authorized; exact
review precedes any native execution or build, and no memory draw is authorized.
The intended boundary defers `_socket_rs` for SSL MemoryBIO-only use while
preserving preexisting/direct C socket objects, old `_socket` module generations,
subtypes and unchanged C send/recv lookup with no imports during I/O. Counts
belong to the object's owning interpreter, including finalization under a
different current thread state. Actual destruction decrements; resurrection,
reinitialization and close do not. Synchronization preserves `_socket`'s
existing no-GIL claim without locks across callbacks/imports/ref release.

Review rejected scalar activation rollback because it could discard a prior
import's completed outcome. The revised proposal uses owned C activation
records, one designated outcome owner per record, retained stale outcomes and
ABORTED rollback ancestors; it holds no Python-object or socket references.
Ordinary import success includes legitimate partial/custom importer results,
and the frontend's unresolved helper uses an explicit lazy-resolution contract.
Normal lifecycle review passed for a candidate. Three isolated source-only
fixtures are prepared but have not executed; the overlay is untouched. Fork
cleanup remains under review: inherited import ownership from vanished threads
must retire without corrupting a surviving import's records or counters. A
private C operation-owner registry is a proposed solution, not a completed
implementation. New private C allocation costs and physical benefit are unknown.
Correctness qualification must close that lifecycle boundary before compilation
or measurement. The same once-only primary policy, if qualification passes,
requires fresh `perf-so36`, clean58, native socket/SSL proofs and full suites
before an all-71/all-23 two-run memory-only gate. SSL itself must improve in
both runs, all memory guards bind, and any non-ACCEPT ends without retry.

Further pinned-source review found two distinct child-process boundaries.
The global recursive import lock is already held by the forking thread;
its child reset only rewrites the owner identity. Moving that rewrite before
dead-thread destructors preserves the held mutex and recursion level, so no
new import fence or C fallback is justified. The proposed private operation
registry can retire vanished C owners before those destructors while keeping
surviving import frames and old socket generations valid.

That does not repair Python's separate per-module import locks. A retained
`_socket_rs` lock owned by a vanished worker, blocked before helper publication,
would make a newly importing child constructor hang where the incumbent C
constructor completes. The bounded incumbent semantic probe confirmed that
distinction: an audit callback blocked after module-lock acquisition, the
child C constructor completed with the helper absent, and explicit helper
import timed out with exit124. The parent reaped the child and joined the
worker. This is incumbent evidence, not an executed candidate failure.
Independent review confirmed that the proposed constructor would introduce
the same orphan-lock wait. Lane36 is closed before implementation: avoiding
it requires changing the import or coverage contract. No candidate source,
build or memory draw ran, and no source improvement is claimed. The prepared
fixtures and fork evidence remain preserved.

Separate zlib, collections and pickle-deferral source-only scouts closed
without a distinct credible memory candidate. Zlib's output/context ownership
is required; a 49KiB engine-zeroing observation does not establish physical
savings. Collections has no retained Rust heap state, and its image/itertools
mechanisms were already tested. Pickle helper deferral was already rejected
and still loads Rust before the unchanged kernel's load snapshot. A source-only
shared Rust runtime scout is checking a different image-ownership boundary;
it authorizes no implementation, build or memory draw.

The stock-runtime linkage question is now closed by a bounded compiler
diagnostic under the build lease. Exact pinned nightly2026-09-15 rejected a
tiny std-using cdylib with `-Cpanic=abort -Cprefer-dynamic`: its selected
`panic_unwind` runtime does not match the required abort strategy. No library
was emitted or executed, and no replacement runtime or panic policy was
introduced. This is a compatibility result, not a memory verdict.

A distinct regex source scout found the existing
`RegexBuilder::dfa_size_limit(0)` setting can disable optional hybrid caches
without changing parser/NFA limits or matching semantics. The default2MiB is
a capacity limit, not a retained allocation: searched Regex clones own temporary
caches, while the global cache shares the immutable strategy. Reverse NFA and
one-pass representation remain. A private pinned-engine allocation diagnostic
in root-created `py-mem-lane6` is authorized to compare actual logical requests
and result/admission parity. It is not a source candidate or physical saving;
no production edit, full build or memory draw is authorized yet.

The private diagnostic passed compilation and default/zero/parity runs using
the exact pinned engine. Five eligible fixed-kernel patterns over1032 lines
produced identical counts/checksums. All searched clones released their cache
allocations; warm net live was zero. Zero capacity reduced logical cumulative
warm requests by46.9MB in its private two-native-pass diagnostic, the largest
cold-search live allocation by7,750B and
retained compiled storage by2,880B. Default2MiB was never a retained-cache claim.
The public kernel uses Rust for one pass and compiled C methods for the other;
the private churn total is not the public kernel's allocation total.
Twenty-one generic patterns checked admission, spans, captures/empty iteration,
invalid/oversize patterns and nesting251 rejection. The System allocator ledger
omits production scratch/Python/cache-map context and proves no physical saving.

Root and independent review authorize source lane37,
`regex-hybrid-cache-capacity`, in `py-mem-lane6`: only the existing zero-capacity
builder setting and native correctness fixtures. Exact committed source/tests
must pass review before native execution or a full build. No worktree memory
draw is authorized. After correctness qualification, a fresh primary
`perf-re37` must pass clean58, native proofs and full suites before its first
and only all-71/all-23 two-run memory-only gate. Regex itself must improve in
both runs, all memory guards bind, and any non-ACCEPT ends the candidate while
preserving its branch/stage/evidence and restoring main. The earlier bounded
matcher, engine-removal and clone trials remain closed.

Checkpoint `36ada80` passed exact root and independent source/test review.
Baseline fixtures passed public6 on control and all9 on incumbent. Its clean
release build verified58 helpers; the candidate passed9 new contracts and7
existing flag tests. Isolated native kernel proofs match incumbent output and
the actual5160 eligible Rust searches plus1032 unsupported validations retaining
C fallback. Two ignored proof assumptions failed on incumbent first (bound
method type spelling and a hand-entered truncated-corpus count); both are
preserved, and the corrected proof uses the C oracle and deterministic SHA256.
Complete13 affected suites are running; no changed-source memory draw has run.

Lane37 completed those suites with4,923/186 and unchanged fingerprints. Fresh
primary `perf-re37` at `780be59` passed clean58, isolated9+7 contracts/native
proofs and full50,158/2,748. Its first and only two-run memory-only gate
`20261001T144719Z` REJECTed all94 entities/165 metrics:162 neutral, three
regressions, no improvement, mismatch or unstable metric. Regex load was
neutral in both runs despite pooled0.940x [0.905,0.977]; neither individual
interval met the required improvement threshold. Regex working peak was neutral.
Dataclasses load1.074x [1.047,1.093], logging peak1.667x [1.638,1.736] and
socket load1.049x [1.028,1.063] regressed in both runs. All23 application RSS
rows were neutral against incumbent. Postflight source, harness and all three
stage fingerprints passed. Main is restored to7cf55a6; the candidate branch,
stage, source and evidence remain preserved. No acceptance or retry follows.
Absolute module/workload goals remain unchanged and required.

A subsequent source-only capture-representation scout found that subgroup
NFA storage is unused by the native whole-span API; C still constructs public
capture objects. Implicit captures were part of an earlier rejected direct-
PikeVM bundle, so that history remains binding. Removing subgroup states at
the same numeric NFA limit changes admission. A conservative small-byte-HIR
proof with an original-All preflight for every uncertain case may preserve
that boundary; charged intermediate states and group metadata are distinct.
This is source-design evidence only, with no implementation, diagnostic build
or memory draw authorized, and no physical-saving claim.

The follow-up now authorizes a private pinned-engine diagnostic in root-created
`py-mem-lane7` from main`30ae24d`. It compares original byte-regex All captures
with equivalent meta-engine Implicit group0 storage, retaining the full engine
feature closure and incumbent's default2MiB hybrid capacity. Rejected lane37's
zero-capacity setting is not stacked. The initial diagnostic uses the original
All builder as admission preflight for every pattern; the conservative HIR
shortcut remains a separate source proof. Only logical allocation lifetimes and
whole-match/admission parity may run under build/test leases. No production
edit, full build or physical memory draw is authorized; renewed source count
remains37 until an implementation candidate is approved.

That private diagnostic is now closed before implementation. Across the five
fixed native patterns, Implicit captures reduced logical retained engine
storage by only 384 bytes and the largest independent lifetime high-water by
154 bytes. Whole-span, admission, nesting and size-limit parity passed across
28 patterns. These totals exclude the original-All admission preflight's
cost and provide no physical-page or replicated memory-improvement evidence.
No production edits, full build or memory draw followed; source count remains
37 and the rejected engine trials remain closed.

Two further source-only ownership checks also closed without experiments.
Marshal already owns writer references directly in its occupied hash-table
keys, so there is no duplicate reference vector to remove. The fixed typing
kernel does not load the regex helper, so a regex/typing shared image would
introduce a new owner rather than eliminate a coimported image.

A bounded source and archived-import-graph scout is checking smaller shared
images. SSL actually loads both standalone `_socket_rs` and `_binascii_rs`.
Binascii links the `_base64` crate, but the incumbent installs a separate
legacy `_base64` extension; its prior alias-only trial remains rejected.
Their allocator,
module-initialization and alias contracts need review before an implementation
candidate. Socket-only and base64-only memory remain guards. No image saving,
production change, build or measurement is authorized by this graph finding.

Root and independent source reviews now authorize source lane 38,
`socket-binascii-image`, in root-created `py-mem-lane8` from main `4d14882`.
One internal cdylib may link the existing socket and binascii Rust libraries
and provide two generated relative aliases, preserving their separate original
initializers, definitions, interpreter flags and public routes. The installed
legacy `_base64` image stays separate. No dependency, engine, allocator or
builtin placement change is included. The aggregate explicitly reuses
binascii's existing macOS `-no_data_const` linker setting: a cdylib-only flag
does not transfer from a linked Rust library automatically. This deliberately
extends binascii's single-data-segment policy to socket in the pair image;
socket's standalone image currently separates constant and writable data.
No flag variants are included, and neither one dirty page nor a physical
saving is promised.
Exact committed source and behavioral fixtures require root and independent
review before native execution or full builds. Subsequent clean58, complete
affected suites and alias/native lifetime proofs precede a fresh primary
`perf-ss38` full-suite qualification. Its first and only all-71/all-23 two-run
matched-context memory-only gate must improve SSL in both runs and preserve
every memory guard. Any non-ACCEPT closes the candidate without retry,
preserving its branch, stage and evidence and restoring main. CPU/wall and
host quietness remain outside the decision.

Source38 completed fresh primary qualification on temporary branch
`integrate-socket-binascii-image-38` at `c412995`: clean58, all three native
contracts against the original reference, and full50,158/2,748 passed. Fresh
control calibration `20261001T165331Z` was independently verified: all 23
workload RSS rows plus collections load/working peak were neutral in both runs,
with observed matched homes and executable aliases. Its first and only
all-94 memory gate `20261001T165746Z-perf-rust-vs-perf-ss38` REJECTed.
SSL load was neutral/neutral, pooled 0.964310x [0.943984, 0.994681], and
working peak was neutral. The 165 metrics read 156 neutral, eight regressions
and one unrelated textwrap load improvement. Regressions were argparse,
functools, statistics and warnings load, plus compileall, gzip extraction,
startup and zlib decode RSS. There were no mismatches or unstable metrics.
Verdict SHA256 is
`5766ce34578cec8fe3eabf9eaaeba8757198a16f2945e15c1a03164521853791`.
Postflight source, unchanged harness, all three stages and candidate release58
passed. Main is restored to the incumbent overlay; branch, stage and raw
evidence are preserved without retry. No renewed source improvement is accepted.

Source lane 40 now examines singleton marshal builtin placement in root-created
`py-mem-lane10` from main `4cd1640`, separately from both image-pair candidates.
The archived 16 KiB helper-load dirty-data delta is a possible physical owner,
not a promised saving. The historical five-helper placement had neutral marshal
load and remains preserved; broad22/eight excluded marshal. Only the original
marshal Rust library and initializer are added to the existing core archive;
algorithms, capsule API, lazy initialization, C glue, slots and allocator stay
unchanged. Private builtin loader/origin, absent `__file__` and builtin inventory
changes are explicit contract changes. Source review caught a fixture lifetime
bug at `b82bf96`: local forwarding owners could die while C cached their table.
Corrected `0b634f2` roots owners globally through controlled child execution;
it makes no arbitrary late-finalization claim. Root and independent review
passed. Four isolated incumbent baseline probes passed, including exact native
five-dumps/three-loads counters, fallback, capsule lifetime and own-GIL cycles,
with unchanged stage fingerprints. Verified private cache preparation, doctor,
clean release57 plus core-artifact proofs, native reference parity and complete
affected suites are authorized after the measurement lease. No memory draw is
authorized before correctness qualification. Fresh primary `perf-ms40`, full
suites and its first-only all-94 memory gate must improve marshal in both runs
and preserve every memory guard; a non-ACCEPT closes it without retry. CPU/wall
and host quietness do not qualify or block it.

Source40 completed clean57 and all four native probes against the original
reference in its worktree, then all13 affected suites (4,311/436). Its proof
controller initially stopped before native execution because Apple `nm` could
not read LLVM23 Rust IR attributes. The exact error remains preserved; the
already verified LLVM23.1.2 `llvm-nm` proved the original initializer in the
actual core archive and built/installed libpython. The core link consumes that
archive, built/installed libpython bytes match, and runtime attribution places
the capsule table and both functions in libpython. Source, stage and release
hashes remained unchanged. Fresh primary `perf-ms40` on temporary branch
`integrate-marshal-single-builtin-40` at `538eccc` passed clean57, the original
native reference, all50,158/2,748 default-resource tests and final integrity.
Its first-only memory gate `20261001T172943Z-perf-rust-vs-perf-ms40` REJECTed:
marshal load was neutral/better, pooled0.978617x [0.967810, 0.991848], so its
improvement did not replicate; working peak was neutral. Of165 metrics,
161 were neutral, three regressed and one unrelated textwrap load improved.
Difflib, glob and warnings load regressed in both runs; all23 workload RSS
rows were neutral. No mismatch or instability. Verdict SHA256 is
`98a93066827afd161c58cfa771bb11e7b8fd1eb9ae437ac44deb9edf186003e2`.
Independent audit and three-stage/source/harness/release57 postflight passed.
Main is restored to the incumbent overlay; branch, stage and raw evidence are
preserved without retry. No resumed source improvement is accepted.

Source41 is now source/fixture-only in root-created `py-mem-lane11` from main
`3307830`: remove the global Rust compiled-expression cache while preserving
its original guarded bytes RegexBuilder, default All admission, hybrid capacity,
NFA/nesting/size limits, grammar, allocator, FFI and module slots. This is distinct
from rejected hybrid-capacity37, implicit-capture and fast-matcher32 mechanisms.
The fixed regex kernel leaves five immutable expressions retained globally,
separately from Python's compiled patterns. Archived logical allocation evidence
counts56,453 bytes before extra map/FIFO keys; physical attribution is unknown
and no saving is promised. Source history and scoped archives show no earlier
explicit global-cache bypass trial. Checkpoint `a0aaf7d` removes the global map,
FIFO and synchronization and gives each search its own original engine lifetime.
Production review passed; a fixture review found the generated lifetime probe
omitted original cache definitions, so binding the incumbent would fail to
compile. That probe must include the original cache closure and reach the
intended ownership assertion before any fail-first claim or execution.
Corrected `c2dc378` binds an explicit production source and includes the original
cache closure. Root and independent source review passed. Verified private cache
preparation and baseline/regression execution are now authorized under the host
leases: the exact old source must compile and fail the shared-owner assertion,
and the candidate-source logical probe must release every per-call allocation
against the same pinned engine dependencies. Incumbent public/native and pristine
public contracts must pass with unchanged stages. The diagnostic counts logical
allocations and does not claim physical savings. A candidate CPython build or
memory draw is not yet authorized. Subsequent
reviewed regression/native/full affected qualification must precede fresh primary
`perf-rc41`, full default suites and its first-only all94 memory gate: regex itself
must improve in both runs and every memory guard binds. A non-ACCEPT closes it
without retry; CPU recompilation cost and quietness do not qualify or block it.

The authorized source41 proofs completed at clean `c2dc378`. Both standalone
actual-source probes compiled against the incumbent's exact regex1.13.1 std/perf
artifacts and unchanged regex-automata0.4.18/regex-syntax0.8.11 pins. The old path
failed the intended identical-pattern-pointer ownership assertion; the candidate
passed independent live owners, continued use after peer drop and per-call logical
release/admission checks. Pristine public2 and incumbent public/native5 contracts
passed with no native skips; stage and harness fingerprints stayed unchanged.
A summary controller initially looked for the inherited cpython-sys manifest in
the overlay instead of the verified extracted source. That report-only error is
preserved and corrected, without hiding or rerunning any runtime failure.
Independent audit verified actual source/generated/artifact hashes and raw exits.
A clean58 worktree CPython build, actual native kernel counters/output parity,
five native/public contracts and the complete19 affected-suite union are now
authorized. No worktree memory draw is authorized or performed. The probe's
logical System ledger does not model physical pages or Python/scratch bookkeeping.

Source41 completed correctness qualification at `c2dc378`: clean58, native5
plus flag/interpreter7, exact fixed-kernel output and 5,160 eligible / 1,032
unsupported native calls, then25 complete affected suites (9,598/272). Fresh
primary `perf-rc41` on `integrate-regex-no-retained-cache-41` at `da2d971`
passed clean58, the same native proofs and full50,158/2,748. Final source,
unchanged harness, all three stages and actual release58 checks passed. Its
first-only memory gate `20261001T181234Z-perf-rust-vs-perf-rc41` REJECTed.
Removing logical retention increased regex load footprint in both runs:
1.429131x [1.348210, 1.495894], with pooled baseline/candidate load medians
1,794,096 / 2,506,764 bytes. Working peak remained neutral. All165 metrics
read161 neutral/four regressed/zero improved. Glob, regex, socket and tempfile
load regressed; all23 workload RSS guards were neutral, with no output mismatch
or instability. Verdict SHA256 is
`8fcee5c230353bd624d7d5ae373b86b455aa653407304c8931ce1d67f0fb6ec6`.
Postflight passed. Main is restored to the incumbent overlay; branch, stage and
raw evidence are preserved without retry. The logical lifetime proof is not a
physical memory win, and no source improvement is accepted. Physical attribution
must precede any distinct follow-up; this source candidate is closed.

A once-only observational probe of the preserved incumbent and source41 stages
completed six independent terminal-phase children under the test lease. Each
executed the unchanged regex kernel prefix and stopped only at its final
boundary; first/second calls remained uninterrupted in the final-phase child.
Output, matched launch identities, both58-artifact maps, source pins, harness
and stage fingerprints passed, and external counters did not drift during
mapping inspection. Raw observations live in lane11's ignored
`results/regex-no-retained-cache/phase-stop-observations`. The final-phase
children recorded first/second physical growth of1,572,864/212,992 bytes for
the incumbent and2,359,296/147,456 for source41. These diagnostic observations
do not replace the replicated gate or qualify a retry. Region attribution is
being assessed; no new regex source is authorized.

That probe narrows the regex excess to malloc residency. After the second
call, source41 has736KiB more dirty malloc pages, while the helper's dirty
pages are identical and its text residency is48KiB lower. The malloc-zone
summary reports fewer live allocated bytes and more fragmentation. These
cross-process observations support allocator retention as a category, not an
exact compiler-allocation-site attribution. Any whole-call scratch allocation
would require engine/pool destruction before reset and exclusion or proof of
all lazy global/TLS pointer escapes. Only a source-level lifetime audit is
authorized; the original gate remains REJECT with no retry.

The allocator-owner scout closed without an untried conversion. Decimal's
historical no_std/PyMem worktree win failed primary memory replication:
`20260930T034305Z` reads load neutral/neutral1.071429, not a CPU-only rejection.
Ipaddress has no Rust heap owner to convert, and regex requires physical-page
ownership evidence beyond logical cache bytes. A historical CPU-only rejection
audit found six other memory winners already incorporated in the incumbent.
The remaining typing builtin placement is under separate narrow source review;
broad builtin rejections stay closed. A distinct zstd fresh single-END stable
buffer configuration has a native reservation basis but no established physical
saving; only an API feasibility script is being prepared for review. No source42
implementation, new source qualification or memory draw follows these scouts.

The singleton typing placement review found no source-level blocker. Root now
authorizes source42, `typing-single-builtin`, from main's unchanged incumbent
overlay. Its entire production scope is four registrar files: move only
`_typing_rs` into the existing static library, retaining its original Rust
initializer and method/module definitions. The historical80KiB bundled result
is not a predicted singleton saving; eager core residency can offset the removed
image. Broad22/eight builtin candidates remain rejected and closed. This is a
separate singleton placement trial, not a reinterpretation of those verdicts.
Private BuiltinImporter/origin/no-file/inventory identity is an explicit change;
public algorithms, ownership, callbacks/errors and own-GIL support remain intact.
First prepare regression and semantic fixtures for root review, with no runtime
or build yet. Qualification requires independent source review, original/builtin
identity and held-method lifetime proofs, native3200/3200 dispatch, actual static
archive/core linkage, clean57, complete affected suites and full primary suites.
Its sole primary all71/all23 memory gate must improve typing in both runs with
all memory guards intact; CPU/wall/quiet remain excluded. Any non-acceptance is
terminal, with source/stage/raw preservation and no retry.

Source42's preparation at `d3ea736` passed root and independent review.
Production remains four registrar changes with the original6/7-argument ABI.
The isolated baseline fails exactly its first builtin-loader assertion against
the incumbent's real ExtensionFileLoader. Seven shared-helper modes, actual
3200/3200 kernel dispatch, held-method GC/reimport, three own-GIL teardowns,
controlled initial ImportError fallback and pristine public oracle all pass.
Source, harness, incumbent58/control1 artifacts and stage fingerprints are
unchanged. Verified private APFS cache clones and doctor passed; a clean
worktree build, actual archive/core/native proofs and11 complete affected suites
are now authorized. No worktree memory draw is allowed.

Source42 completed that work: clean57, all native contracts and11 full affected
suites (3,337/24, no failures), with final source/harness/stage/artifact checks.
The controller's expected build-directory core owner was wrong: the build
executable's load command names the installed core. The identical built and
installed core hashes, actual link line and single initializer proofs passed.
The failure is archived; a controller-only correction resumed just the failed
ownership and pending context/oracle checks, all passing without rebuilding or
repeating passed native cases. Root now authorizes fresh primary `perf-ts42`,
the same proofs, full default suites and its sole all71/all23 memory gate.

Source42's fresh primary clean57/native proofs and full50,158/2,748 passed.
Its sole memory gate `20261001T194317Z-perf-rust-vs-perf-ts42` REJECTed:
typing load was neutral/better, pooled0.944580 [0.907692,0.968513], so its
lower point estimate did not replicate as an improvement. Working peak was
neutral. URL parsing load regressed in both runs at1.050 [1.037177,1.075].
All23 workload RSS guards were neutral; all165 metrics were164 neutral and
one regressed, with no mismatch or unstable metric. Source/harness/three-stage
and57-artifact postflight passed. Main's overlay is restored to7cf55a6;
branch `integrate-typing-single-builtin-42`, stage `perf-ts42`, lane12 and raw
proofs remain preserved. The candidate is terminal without retry; CPU/wall
and host quietness played no role in its rejection.

The once-only zstd API feasibility invocation passed six inputs, including
empty,1MiB kernel data, incompressible data and multiple blocks. Fresh single-END
stable input/output modes produced identical bytes to the default native mode
and the actual public Rust route; decoding matched the inputs. Native1.5.7
accepted both experimental settings. Its reported1MiB context allocation
decreased by1,311,233 bytes, a logical reservation result only. Original stage,
all58 artifacts, full harness and native-library identities passed pre/post
checks. A bounded external-native physical diagnostic is being prepared for
review; it cannot establish private Rust-route savings or acceptance. No zstd
production candidate is authorized.

The once-only external zstd physical pair completed with valid identical
outputs and unchanged artifacts/harness. Both modes recorded zero interval
footprint growth after identical warmups; each mode's four phase counters stayed
constant. A32KiB cross-process starting difference is not operation savings.
The1,311,233-byte reservation reduction therefore remains logical-only in this
topology. The lead is closed without production code, a private Rust diagnostic
build or qualification; no retry. Unwritten reservation and warmed allocator
reuse remain possible explanations, not separated causal findings. Zstd's
working-peak goal remains unresolved.

Root now authorizes source43 preparation, `regex-full-call-arena`, from the
unchanged incumbent overlay, for source and isolated logical-proof fixtures only.
The distinct mechanism routes temporary whole-engine construction/search/drop
through existing bounded scratch storage, addressing the observed malloc
retention category. Source41's System-only no-cache candidate remains rejected
and cannot be retried or reclassified. No net physical saving is predicted.
The scratch size/alignment, owner/nesting rules, System overflow fallback,
parser memo, engine configuration, admission/resource limits and public ABI
must remain intact. Only copied status/span scalars may cross scope reset.
The concrete default pool-capacity Lazy allocation must initialize under
System before any full-engine scratch activation, using its original public
configuration getter. A direct edge to already-pinned automata0.4.18 is allowed
only with identical unified features and package/version/checksum inventory.
Cold global/TLS allocation escape, engine/pool complete destruction, errors,
overflow/alignment and concurrent/nested scopes require isolated proofs with
actual source and dependencies; warming an unrelated engine oracle first
would hide the known escape and is forbidden. No runtime, build or memory draw
is authorized until root reviews those sources and fixtures. Complete affected
and primary suites plus a sole all71/all23 memory-only qualification remain
required for any eventual candidate; non-acceptance is terminal without retry.

Source43 preparation at `f6f8d09` passed bounded root and independent source
review. The original default-capacity Lazy is initialized under System before
scratch ownership; only scalar search outcomes escape and all engine/error/pool
owners drop before reset. The cold naive negative control must expose its exact
8-byte escaped global before the candidate proof runs. Fixed observer bookkeeping
serializes raw System realloc with ledger updates, checks each worker call and
preserves aligned bytes. Failed-realloc injection remains untested; its unchanged
null branch is source-audited only. Historical audit provenance is now separated
from current candidate state. Root authorizes only verified private APFS LLVM/
Cargo cache clones and doctor at this step. Probe execution awaits final explicit
locked-linker and dependency/hash binding review. No memory draw follows review.

Verified cache clones and doctor passed. Root's final controller review binds
the locked LLVM23.1.2 linker/target and scrubbed environment, exact reviewed
source/generator/generated hashes, all five incumbent Cargo dependency artifact
pairs/features, pinned crate/std sources, original stages and clean58 map.
One isolated logical invocation is now authorized under the host test lease:
fresh naive cold escape counterexample first, then fresh candidate cleanup.
Every subprocess is bounded and exact pre/post checks run in finally. No
production build or memory draw is authorized by this logical-only step.

That invocation stopped during preflight: the controller incorrectly assumed
one normal-target memchr artifact, but the incumbent has three feature variants.
No probe was compiled or executed. Its finally check encountered the same
binding fault, so no complete pre/post proof is claimed. The raw failure is
preserved; an independent test-lease integrity check passed incumbent58/control1,
source/harness and both stage fingerprints. Only a controller correction that
follows exact regex/automata/Aho-Corasick extern edges and matching compile
invocations is authorized; production and fixtures remain unchanged. Relaunch
awaits separate review, with no memory draw or candidate acceptance.

The corrected controller passed root's actual read-only graph/preflight judge
and independent source review. It starts at the real `_re_rs` extern edge,
keys nodes by exact rmeta path, recursively preserves variants and matches each
compile invocation/output/features. The engine's graph selects one exact memchr
instance shared by automata and Aho-Corasick; only the three used direct crates
and five selected dependency directories reach the probe linker. Original
failure/archive, source/fixtures and stages remain intact. Root authorizes the
resumed single cold logical proof; no native probe has run previously, and no
production build or memory measurement follows without separate qualification.

The resumed proof passed preflight but stopped compiling the naive driver before
any native execution: the command supplied metadata-only externs for artifacts
whose metadata is stored outside their archives. Complete finally pre/post checks
passed. The compile failure and inputs are archived. The incumbent Cargo command
and established private driver both supply each direct crate's verified rlib and
rmeta pair; root's controller-only correction now does the same for the exact
selected instances. Independent review passed without changing source, features,
artifacts or toolchain. Root authorizes resuming the still-unexecuted cold proof
with this established archive-pair convention; no memory draw is authorized.

The resumed cold proof passed: naive full-call scratch exposes exactly one
8-byte global surviving reset and fails the intended assertion; the candidate
keeps the original default-capacity global under System, survives scratch poison
and releases all tracked arena/scope-System owners before reset. Original All
limits, compile errors, overflow/alignment, successful realloc preservation,
actual nested ownership and concurrent/new-thread calls passed. Exact source,
harness, dependencies/features, toolchain and both stages matched pre/post.
This is logical ownership evidence only, with failed-realloc injection still
untested. Root now authorizes a clean worktree release58, staged native/public
fixtures, original own-GIL/flag/kernel proofs and all25 complete affected suites.
No worktree memory draw is permitted; primary qualification remains separate.

Source43's clean worktree build verified58 release extensions. All25 complete
affected suites passed (9,598/272), and all eight staged proof cases passed:
pristine public output, original/candidate public/native parity, seven unchanged
flag/own-GIL tests and fixed-kernel5160/1032 Rust dispatch with the original digest.
Actual Cargo dependencies/features, copied source, all58/1/58 release maps and
three stages matched pre/post. Independent read-only qualification review passed.
Root now authorizes fresh primary `perf-ra43`, the same staged/native proofs,
full default-resource suites and its sole all71/all23 matched-context memory-only
gate. Regex itself must improve in both runs with every memory guard intact;
any non-acceptance is terminal, preserving source/stage/raw with no retry.

Source43's fresh primary build verified58 release artifacts; all eight native
proof cases and the full50,158/2,748 default-resource suite passed. Fresh memory
self-calibration `20261001T204049Z` read all25 metrics neutral in both runs,
with verified matched home/executable identities and no quiet/timing prerequisite.
The final source/harness/ancestry/three-stage/release58 preflight passed.
Its sole gate `20261001T204444Z-perf-rust-vs-perf-ra43` REJECTed: regex load
regressed in both runs at1.171271 [1.149416,1.335505], raw pooled1,794,060 to
2,129,944 bytes. Working peak remained neutral under the original floor; its raw
medians were49,152 to212,992 bytes. Startup RSS1.011635 and zlib-decode RSS
1.010192 also regressed in both runs; the other21 workload RSS rows were neutral.
All165 metrics were162 neutral, three regressed and zero improved, without
mismatches or unstable metrics. Postflight passed source/harness/ancestry,
three-stage and58-artifact identity. Main's overlay is restored to7cf55a6;
`integrate-regex-full-call-arena-43` at `3caa0ee`, `perf-ra43`, lane13 and raw
proofs remain preserved. Logical ownership correctness did not establish a
physical saving. Source43 is terminal without retry; all memory goals remain
required and CPU/wall/quiet played no role in rejection.

The separate typing no_std scout closed without a candidate. An exact typing
trial appears absent, but shared `cpython-sys` forces std and actual archived
symbols/pages show required module/method/loader ownership rather than removable
std runtime pages. No local FFI substitution or shared binding change follows.

A second bounded zstd ownership review found no distinct removable output overlap.
The C proxies bypass their codec/output paths when Rust capsules exist. Rust writes
directly into one Python bytes buffer and transfers references without copying
payloads; complete kernel frames leave no pending input Vec. The simultaneous
1MiB decoded results are imposed by the unchanged kernel on control too. No new
source candidate, runtime or diagnostic follows; zstd working peak remains open.

A bounded hashlib inline-state scout closed without a candidate. Archived
repeated construction released the224-byte Box with no retained physical growth;
first-call resident growth belonged to the helper image. Embedding the same state
in a larger Python object has no demonstrated physical saving and introduces
initialization, alignment, zeroization, heap-type and reflected-size contracts.
No source edit or runtime followed.

A source-only tiny-helper layout review closed without a candidate. The typing,
threading, UUID, datetime and struct images have fixups on separate16KiB
DATA_CONST and DATA pages. Consolidation through `no_data_const` would remove
the relocated tables' read-only protection; moving method tables alone leaves
the eager GOT page. The shared-helper flag and struct page-removal mechanisms
were already tried without a memory win. Static payload arithmetic establishes
no physical saving. No compiler, runtime, source change or memory draw followed;
the preserved report is lane9's `results/tiny-helper-layout-scout/report.md`.

Further source-only retained-owner reviews closed pickle, base64, decimal,
inspect, tokenize, ipaddress and startup without a candidate. Pickle's duplicate
decode tree and inspect's two unused frontend containers are temporary, with
no exclusive physical-page evidence. Base64's measured paths already write
directly into Python bytes; decimal's conversion and allocator variants were
tested. Successful inspect/ipaddress native results return directly, and
tokenize's replay buffer preserves later fallback. Startup's codec metadata is
required; archived conversion counts are zero and itertools is absent. These
reviews authorize no source change, runtime or memory draw. All goals remain.

The smaller-engine source review now identifies a concrete boundary mismatch:
the current portable filter admits class subtraction such as `[a-z--m]`, which
regex-lite's parser rejects. Matching numeric nesting and compiled-size limits
does not match their accounting. Original literal strategies can also bypass
NFA construction, so unconditional original-NFA preflight changes admission.
The old standalone lite report was not recovered; these findings come from
current pinned source and upstream source review. No replacement is authorized.

Root authorizes source44, `regex-retained-storage`, for code and fixtures only,
in a fresh isolated lane from the restored incumbent overlay. Preserve the
original512 FIFO cache, Regex clones, parser, grammar, All captures,250 nesting,
10MiB NFA and2MiB hybrid defaults. Change only parser/build allocation placement:
the existing permanent60KiB range may hold individually reclaimed blocks.
No reservation, capacity, feature, dependency or search-pool policy changes.
Keep the range zero-initialized; metadata and alignment overhead consume its
existing bytes. Scope exit releases admission ownership and never resets live
storage; actual final deallocation, including on another thread, frees blocks.

A nonallocating lock and single-atomic canonical block headers must keep the
physical chain valid at every split/free/coalesce commit. Realloc failure keeps
the original block and bytes; System spill, overalignment and nonowner behavior
remain explicit. Child-only pthread fork refresh plus process-tagged lock
recovery avoids inherited-lock/PID-reuse deadlock. Registration is nonwaiting,
outside allocation admission: pending or failed registration uses System only.
The handler changes neither block metadata nor existing owner/cache state.
Normal CPython-imported image lifetime and libc fork handling bound this proof;
no arbitrary external unload or raw-syscall fork promise is added.

Actual-source fail-first lifetime, clone/eviction, fragmentation/coalescing,
cross-thread free, realloc failure, registration and fork-boundary fixtures must
pass review before any execution. Existing logical ownership grounds a testable
placement hypothesis, not a saving: newly touched static pages can cost16–32KiB
and offsetting malloc residency is unknown. Clean builds, complete affected and
primary full suites precede the first and only all71/all23 matched-path
memory-only gate. Regex must improve in both runs and every memory guard binds.
Any non-acceptance preserves source/stage/raw and restores the incumbent without
retry. CPU, timing and host quietness play no role. No runtime or build is yet
authorized.

Source44 preparation `5b7b1c8` is frozen and clean. Independent review passed
the production allocator and final fixtures, including same-byte extraction
bindings and positive searches through all five cold retained engines before
any oracle. The old reset allocator has a prepared failing lifetime control;
candidate fixtures cover exact ownership, cache eviction, allocation failure,
threads and canonical-header/lock fork simulations. These are prepared proofs,
not executed results or physical savings. Root authorizes only verified private
LLVM/Cargo cache clones and `perf.py doctor` next. Logical compilation and
execution await separately reviewed controller bindings; no build or memory
draw is authorized.

Source44's frozen private controller and all67 input bindings,20 support
bindings and five incumbent dependency variants passed independent review.
Root's read-only preflight and verified cache/doctor checks passed. Root now
authorizes only the isolated logical proof under the test lease: compile and
run the original failing lifetime control first, then the candidate. Preserve
every command, generated probe, binary and output, and check source, tools,
dependency artifacts and incumbent/control stages before and after, including
failure cleanup. Fork fixtures remain simulations. This authorizes neither
product compilation nor a memory draw; those await the proof result.

Source44 logical proof completed successfully: the original reset control
aborted on retained storage overwritten by a later scope; the candidate
reported one8-byte persistent global, zero ledger/header errors,79226 canonical
commits,14081 arena requests and54697 System requests. These are logical counts,
not resident bytes. Frozen inputs, generated/binary outputs and incumbent/control
stages matched after execution. Root now authorizes a clean isolated interpreter
build, complete25 affected suites and reviewed native correctness cases. Native
fork checks must distinguish actual child execution from the earlier simulations.
No memory draw is authorized until build, full suites and native checks pass.

Source44 isolated clean build verified58 installed release Rust extensions.
All25 affected suites passed9598 tests with272 skips. Independent review passed
the frozen native controller and120 input bindings. Root authorizes its12
isolated cases: the original public/native/flags/own-GIL/kernel checks plus
incumbent and candidate cold/warm actual libc forks, each with two bounded
children, child cache pressure and parent continuation. This public proof does
not force a held pool lock or pending registration. Source, artifacts and all
three stages are checked before and finally after. Separate private actual-fork
fixtures remain source-only; no memory draw is authorized.

Source44 native controller completed12 cases successfully, including eight
actual child processes across incumbent/candidate cold and warm imports.
Unchanged kernel outputs, native call counts and all source/tool/artifact/stage
pre/post checks passed. Root authorizes primary-checkout preparation on a
temporary integration branch, a clean `perf-rs44` build, reviewed primary native
checks and the complete default-resource suite. The private held-lock and
installed-before-Ready fork fixtures still require review and proof before
memory qualification. No source is accepted and no memory draw is authorized.

Source44 completed primary clean58 qualification, the full default-resource
suite (50158 tests,2748 skips,464 modules OK), and12 native cases. Separate
single-threaded actual libc-fork proofs passed inherited held-lock recovery,
retained block reclamation/parent ownership, and installed-before-Ready child
registration. Private controller interruption-cleanup regressions and a typed
cache preflight correction were tested and preserved before native execution.
The initial preflight-only failure ran no compiler or native program. Cargo's
post-build cache difference was confined to SQLite usage timestamps;142 locked
archives and5333 source files matched. All source/tool/cache/stage postflights
passed; fork proofs carry no general multithreaded async-signal-safety claim.

The first and only primary matched-prefix/executable all71/all23 memory-only
gate, `20261001T230025Z-perf-rust-vs-perf-rs44`, is terminal **REJECT**. Regex
load improved in both runs:0.827138x,95% interval[0.786296,0.872729], raw
1785892 to1458188 bytes (-327704 bytes). Regex working growth rose49152 to98304
bytes, both below the256KiB floor, and remained neutral. Of165 memory rows,
157 were neutral,3 improved and5 regressed. Replicated regressions were
argparse load1.03509x, fractions load1.02548x, glob load1.06383x,
catalog JSON export RSS1.01806x and zlib4KiB-stream RSS1.01027x. There were no
output mismatches or unstable verdicts; CPU, timing and quietness were absent.

Postflight passed before restoring `main`: its overlay remains exact7cf55a6
and incumbent/control stages are unchanged. Preserve source5b7b1c8, temporary
primary branch3a09f51, both stages, all native proofs and raw gate evidence.
No retry or sizing/layout retune of this candidate is authorized. Its regex
saving does not waive the guard regressions. No source optimization was accepted;
all20 unresolved absolute module memory goals and16 workload RSS goals remain
open. The renewed SSL image scout closed again because its helper is already
builtin, with no separate image to remove; no experiment followed.

A source-only history map now binds actual C/Rust placement and prior trials
for all20 unresolved routes. Exact singleton datetime11ed0a1 already rejected
memory guards; C `_datetime` is itself builtin, so no existing C shared image
can be paired with its helper. The zstd C/Rust image proposal closed: C binds
39 ZSTD/ZDICT APIs to Homebrew while Rust bundles a reduced-feature engine;
same-image unprefixed symbols could silently change C provider/features. No
new experiment followed either closure.

Root authorizes source45, `binascii-c-rust-image`, for code and fixtures only
in a fresh isolated worktree. C `binascii` and `_binascii_rs` are actual
standalone coimports; historical attribution identifies a16KiB dirty helper
page. This is distinct from rejected legacy Rust Base64/helper and socket/helper
pairs. Conditional independent design review passed; savings remain unknown.

Compile the unchanged original C source with its exact configured C flags,
headers and dependencies plus only an initializer symbol rename. Link that
object during Cargo's real release helper link, with a thin exported forwarder
for original `PyInit_binascii`. Preserve both module definitions, states,
methods, lifecycle/GIL slots, errors, buffers and current-interpreter lookup.
Install the canonical Cargo bytes once and a relative C-module alias, preserving
both inventory names and all58 release Rust artifact proofs. No post-Cargo C
relink, validator relaxation, legacy `_base64` redirect or new dependency.

The merged recipe drops the helper's `-no_data_const` flag so C's protected
DATA_CONST tables retain read-only protection; other member recipes stay exact.
The deliberate C bundle-to-Cargo dylib packaging contract requires explicit
loader/export/import-order/install-replay fixtures. Physical page fit is not
assumed. Independent source/fixture review precedes any execution or build;
clean builds, complete affected and primary full suites/native proofs precede
the first and only primary matched-path all71/all23 memory-only gate. Base64
or binascii memory must improve in both runs and every memory guard binds.
Any non-acceptance preserves source/stages/raw and restores the incumbent with
no retry. CPU, timing and quietness play no role. No runtime is yet authorized.

Source45 froze at7ca5306 with six owned files and static generation checks
for active, earlier-disabled-C/helper, static-C and non-Darwin configurations.
Independent production review passed. Its fixture incorrectly compared the
process-local ABI slot109 pointer; preserve that checkpoint and its outputs.
Fixture-only e073116 decodes the five original ABI fields using pinned headers;
supplemental review passed, with all production hashes unchanged. No runtime
has run. Root authorizes only the frozen nine-case incumbent semantic baseline
and separate intended same-image packaging failure under the test lease,
after exact controller/binding review. Every pre/post source, stage, release
artifact, harness and tool identity must hold. Baseline assumption failures
stop dependent construction and remain preserved; no candidate build or
measurement is authorized by this step.

Root baseline32566 exited1 on its first semantic child: fixture `error_of`
did not accept `strict_mode` and failed before calling the native target.
All other cases and the expected packaging failure were unrun. Independent
audit confirms byte-identical pre/post snapshots, all123 bindings and exact
incumbent58/control1 stages, with no finalization error. Preserve the complete
first attempt and earlier review failures. The smallest isolated regression
extracts the actual fixture helper and checks keyword forwarding and target
exception capture: old helper failed, fixture-only fe2a73e passed under the
test lease. It adds the retained regression and changes no production hash.
A separate reviewed second baseline may bind the repaired fixture; this is
fixture repair before construction, with no candidate or memory retry.

Root second baseline64451 exited0: nine original cases passed and the separate
merged-packaging assertion failed exactly at the missing C symlink. The saved
semantic reference is e2bea43d33514f2726d04e680d747602ef1556fb1d7193cfb7cff5f379051676.
C-first imports both modules; helper-first leaves C absent. Both support the
three tested own-GIL lifetimes, while legacy `_base64` rejects them as before.
Held owners/Error, buffers/errors, native call counters, threads, normal fork
and controlled import-failure recovery passed. Postflight reports all frozen
identities unchanged. Root authorizes isolated verified private LLVM/Cargo
caches and locked doctor, then one clean worktree58 build and complete affected
suites after independent baseline audit passes. Preserve original object-cache
policy and all build provenance. Native mapping/protection/provider/kernel and
install-replay proofs remain required before primary qualification; no memory
draw or primary build is authorized by this worktree step.

Source45 clean worktree build49112 passed all58 release artifact checks.
Suite87802 passed the16 real affected modules (5,989 tests/147 skips), but
exited1 because root also selected nonexistent `test_bytearray`; bytearray
coverage belongs to `test_bytes`. Preserve the report and log before a
corrected selection. The actual final Cargo link still includes inherited
`-no_data_const`; static inspection of the canonical installed image confirms
no DATA_CONST segment and writable C relocation tables. This violates the
frozen protection contract despite source omission of the local flag. Hold
native execution, primary qualification and memory measurement. Source-only
diagnosis may propose the smallest build-glue correction; preserve original
build provenance and unchanged algorithms before any reviewed correction.

Source-only UUID C/helper image scouting runs independently in the existing
datetime worktree. It must distinguish this pairing from closed Rust-builtin
placement trials and identify provider, lifecycle and protection constraints
before proposing source. This authorizes reports only, with no source change,
compiler, runtime or measurement. Binascii controller preparation likewise
remains source-only until the lane freezes and independent review passes.

The UUID scout and independent review conditionally passed. Root authorizes
source46, `uuid-c-rust-image`, for code and isolated baseline-relative fixtures
only in fresh `py-mem-lane16`, branching from unchanged incumbent source.
Use the existing `_uuid_rs` release Cargo image as canonical and one relative
C `_uuid` alias. Compile unchanged `_uuidmodule.c` with its original limited
API, flags, headers and libSystem provider, adding only a private initializer
rename and Rust export forwarder. Preserve independent definitions and the
different own-GIL outcomes, imports, errors, methods and read-only protection.
No new Cargo package, features, dependency or validator exception. The new
source owns only its helper build/initializer glue, narrowly specialized
`makesetup` and install-alias rules, fixtures and explanations in its worktree;
it does not inherit source45. No compiler, runtime, build or memory execution
is authorized before frozen-source review. Any later qualification requires
clean58, complete affected/native proofs and primary full suites, then one
primary all71/all23 matched memory-only gate. UUID memory must improve in both
runs and every memory guard binds; any non-acceptance preserves all evidence
and restores the incumbent without retry. Physical savings remain unknown.

Source46 froze at3b7da3b. Independent production review passed conditionally;
its fork fixture lacked a bounded wait/child cleanup. Preserve that checkpoint.
Refreeze4255d0a bounds and reaps the owned child and delegates C native linker
flags to the existing pinned helper parser, removing a redundant parser.
All12 static variants and full module inventories/non-UUID recipes remain
equal to their originals. Supplemental source review precedes any execution;
baseline, builds, native proof and memory gate remain unrun.

Source46 reviewed incumbent baseline21094 exited1 after eight passing rows
and11 actual native children. Its own-GIL child failed to parse because a
nested script defeated outer indentation removal; no own-GIL assertion ran.
Remaining rows and the expected alias failure were unrun. Pre/post identities
and all286 bindings held, with no finalization error. Preserve the complete
first attempt and source4255d0a. The smallest retained emitted-script
regression failed on the original fixture and passed after fixture-only
f35737b: the exact inner assertions and three teardown cycles are unchanged,
and every production hash is unchanged. Independent repair review passed.
Root authorizes preparation and independent review of a separate repaired
baseline controller, then only its incumbent semantic rows and intended alias
failure under the test lease. Candidate build and memory remain unauthorized.

Root repaired baseline60803 exited0: all11 semantic rows passed through14
actual native children, including three own-GIL teardown cycles, reentrant
concurrent imports and normal fork. C succeeds and the original Rust helper
rejects own-GIL interpreters; public fallback remains intact. The separate
alias regression failed exactly at its original missing-symlink assertion.
Independent audit confirms all294 inputs and93 output hashes, byte-identical
pre/post snapshots and no finalization errors. Typed ABI/lifecycle remains
unrun. Root now authorizes isolated verified private caches and locked doctor,
then one clean worktree58 build and the complete actual affected suite union.
Native ABI/provider/protection/kernel and installer-replay proofs remain
required before primary qualification; no primary build or memory draw is
authorized by this step.

Source45's original final link inherited `-no_data_const` from a Cargo
dependency. A narrowly scoped, independently reviewed linker wrapper removes
only that exact argument for the identified merged binascii output/object;
other links pass through, and unsupported response arguments fail closed.
The retained wrapper regressions fail on the original and pass on0faa96b.
Protected clean build17465 passed all58 release artifacts; corrected affected
suite selection82121 passed5,989 tests/147 skips across16 complete suites.
The first native baseline96389 passed its ten children but failed aggregate
kernel digest comparison: `-I` ignored `PYTHONHASHSEED`. Preserve that complete
375-payload archive. Fixture-only a6b4c8c retains the launch regression; the
separate corrected controller uses the unchanged kernel with a checked seed1
launch. Root compile31145, baseline52840 and candidate36580 all passed.
Independent audit confirms all766 inputs and identical stage snapshots;
original two definitions/lifecycles, separate legacy helper, native counts,
semantic reference and all ten complete readonly tables (1,826 bytes) hold.
Root installer56290 passed two disposable destinations, all58 actual Cargo
bytes, the relative C alias, separate legacy image and twenty fresh native
checks. Independent audit confirms133 supplemental inputs,79 outputs and six
unchanged snapshots. This establishes worktree correctness, not memory savings.

Source46 clean build40771 passed all58 artifacts; complete affected suites35945
passed5,627 tests/578 skips across17 suites. Its first native baseline96313
stopped because the observer assumed only full-API slot IDs; unchanged C UUID
uses its pinned limited-API compatibility IDs2/3/4. Preserve all889 archived
payloads. Fixture-only9c76b5b decodes those original IDs alongside85/86/87,
without changing raw evidence or productionf35737b. The retained native
regression failed before repair and passed afterward. Root corrected observer
compile53900, baseline98276 and candidate18538 all passed: typed ABI, six
native rows and14 fixture cases/17 children. Independent audit confirms1,643
inputs, unchanged stages, distinct original definitions and own-GIL outcomes,
loaded readonly protection and actual libsystem_c `uuid_generate_time` binding.
Root installer17637 passed two distinct disposable destinations, all58 actual
Cargo bytes and relative alias, typed ABI and twelve fresh native rows.
Independent audit confirms194 supplemental inputs and unchanged snapshots.
Both installer proofs explicitly omit space-bearing DESTDIRs because the
unchanged recipe does not quote that input; original ambient build variables
were unsaved, so replay binds known configured requirements and records that
limitation. Primary full suites/native/install qualification and the sole
all71/all23 matched memory-only gate remain required for each candidate.

Root authorizes distinct source47 pickle, source48 decimal and source49 socket
C/Rust image candidates in isolated worktrees, for code and fixtures before
reviewed incumbent baselines. Each compiles the unchanged original C object
with original flags/headers/providers and only a private initializer rename,
links during the existing helper's real Cargo release link, and installs one
canonical image plus a relative C alias. Original definitions, states, heap
owners, lifecycle/GIL, APIs, algorithms, fallbacks and all58 artifact proofs
remain binding. No new dependency, feature or helper activation is authorized.
Decimal retains its existing dynamic mpdecimal provider and C-only provider
initialization; direct helper import maps that existing provider earlier.
Socket retains `_socket.CAPI` ownership and original SSL consumers; direct
C/SSL import may map Rust earlier but must never import or initialize the
optional helper. Static page fit establishes no physical saving. Each later
candidate requires complete affected and primary full suites, native/provider/
protection/installer proofs, then exactly one primary all71/all23 matched
memory-only gate with replicated target improvement and every memory guard.
Any non-acceptance preserves source/stages/raw evidence and restores the
incumbent without retry. CPU, wall time and host quietness are excluded.

Source47 froze productiondb3e5b3. Its first incumbent baseline63705 stopped
before children because the controller required `all-passed` for the pristine
control whose saved report is `suite-passed`; preserve the complete26-file
attempt. An exact per-reference status repair retained the failing/passing
mock and rejected swapped, failed or incremental records. Second baseline91403
passed three rows/four children before a fixture fake returned the wrong
private helper result shape. The original decoder returns
`(supported, value, consumed)`; two further held/own-GIL assertions also read
the boolean as the value. Preserve the complete67-file attempt. Fixture-only
86286b9 repairs those clients without changing production; three retained
controller regressions pass. A separately reviewed436-input controller records
independent semantic failures while aborting on observer, error/skip, cleanup
or snapshot inconsistency; all nine passes remain mandatory. Root baseline95078
passed nine cases/eleven children and the precise original missing-alias
negative. Typed ABI/provider cases remain explicitly unrun pending compilation.

Source48 froze production0768d1a. Fixture-only c6a40b6 adds a pinned-header
typed module observer and three own-GIL lifetimes, corrects the accepted custom
flag scenario, and makes bounded fork reaping continue after signaling faults
while preserving the original exception. Independent nine-source/591-header
review passed; old cleanup faults reproduce and the corrected five mock
regressions pass. Correctly configured static generation checks pass; root's
earlier omitted fixture environment failure is preserved. Root baseline6606
passed six semantic tests, two unchanged-kernel executions with identical
control output and3,000 additions/six multiplications, two cold import orders
and the precise alias negative. Independent audit confirms all1,753 inputs,
identical snapshots and no cleanup error. Compiled ABI/own-GIL/provider cases
remain explicit pending work. Verified private caches and locked doctor85069
passed; original absent-cache evidence is archived before that authorized path
change. Only Cargo's usage bookkeeping differs from the older donor ledger;
all other5,822 files,142 locked archives and5,333 sources remain verified.

Root now authorizes UUID primary qualification on a temporary integration
branch: copy only its reviewed production and durable fixtures, clean-build
all58 actual release artifacts, run the complete default-resource suites, then
bind and independently review actual primary native and installer controllers
before their execution. Binascii follows independently after UUID concludes.
Fresh memory-only control calibration and the first and only all71/all23
matched-prefix/executable memory gate follow complete correctness qualification.
Neither build nor correctness results establish acceptance; every memory guard
and replicated UUID target improvement remain binding. Decimal may separately
run its reviewed clean worktree58 build and complete affected suites.


The separate bounded zlib/ZIP source review found matching pinned codec
dependencies and no allocator or module-lifetime incompatibility. Root now
authorizes source lane 39, `zlib-zip-image`, in root-created `py-mem-lane9`
from main `070301a`, for source and behavioral fixtures only. One internal
cdylib may link just the existing two Rust libraries and install two relative
aliases. Original capsule families, APIs, destructors, zlib's own-GIL support
and ZIP's existing own-GIL rejection remain unchanged. No helper algorithm,
dependency feature/version, allocator or linker flag changes are included.
The absolute ZIP wheel RSS goal is still regressed at 1.017x; cold ZIP import
RSS is 1.065x. The zlib-only kernel does not load ZIP today and remains a
binding memory guard. Exact source/fixture reviews precede any execution or
build. Clean58, complete affected suites and native ownership proofs must
precede a fresh primary `perf-zz39` full-suite build and its first and only
all-71/all-23 memory-only gate. ZIP wheel RSS must improve in both runs;
every memory guard binds. Source38 is not inherited or stacked. If the
incumbent advances, this lane must merge it and qualify cleanly again.
No physical saving is claimed by static dependency deduplication.

Exact source checkpoints `f618f29` (socket/binascii) and `d51dde5`
(zlib/ZIP) passed root and independent review. Both retain the original
helper sources and link environment; the private canonical artifacts need
explicit Cargo-byte and export proofs in addition to the unmodified alias
verifier. Baseline contract execution is now authorized under the host test
lease after small fixture refinements: child processes must disable bytecode
writes, and each import-order probe must observe the second helper absent
before importing it. Existing interpreter stages must retain their fingerprints.
Only passing incumbent contracts authorize each lane's clean release build,
then its candidate native proofs and complete affected-suite union. Any
baseline assumption failure is preserved and reviewed before building; no
worktree memory draw is authorized. No source improvement is accepted yet.

Socket/binascii checkpoint `0ca3cd5` passed incumbent contracts, clean58,
three candidate contracts matching the incumbent reference, exact canonical
Cargo bytes and all three initializer exports, followed by all 48 affected
suites (15,615 tests / 1,022 skips, zero failures). Its installed stage stayed
unchanged through two disposable installation replays. However, that replay
controller supplied an incomplete compilation environment and rebuilt one
unrelated Cargo artifact (`_zstd_rs`) with a hash differing from the installed
stage. The original clean build, suites, fingerprints and mismatch report
remain preserved. The authorized repair is complete: a fresh clean build verified all 58
release extensions, the three native contracts passed against the original
incumbent reference, and all 48 affected suites repeated with 15,615 tests /
1,022 skips. Two installer-only `make -o all sharedinstall` replays passed
without compilation; all 58 actual Cargo hashes and stage fingerprints stayed
unchanged. Its subsequent primary qualification and terminal rejection are
recorded above.

Zlib/ZIP's first baseline snapshot incorrectly expected every zero-argument
native call to raise; ZIP's decompressor legitimately constructs a capsule.
The failure is preserved. Fixture-only checkpoint `a67482a` records stable
successful return types and exception outcomes separately, retaining every
native method and semantic test. Corrected incumbent runs passed all 16
contracts in both import orders with identical snapshots and unchanged stage
fingerprints. Clean58 and candidate contracts likewise passed in both orders,
with exact baseline snapshots, canonical Cargo bytes, two initializer exports
and evaluated shared-module inventory. All 18 affected suites passed
6,007 tests / 562 skips with zero failures and the existing large-ZIP resource
denial. Two disposable installer-only replays and final release58/stage
checks passed. Fresh primary `perf-zz39` verified clean58, both native import
orders and all 50,158 default-resource tests / 2,748 skips. Its first and only
all-94 memory gate, `20261001T162322Z-perf-rust-vs-perf-zz39`, REJECTed:
156 neutral, eight regressed and one unrelated textwrap load improvement.
ZIP wheel RSS had no replicated target improvement (neutral/worse; pooled
1.008718x). Regressions were `_strptime`, configparser, difflib, statistics,
warnings, ElementTree and zipfile load, plus catalog URL RSS. There were no
output mismatches or unstable rows. Verdict SHA256 is
`f35715619cd5a592eef29b2140175eca051932e37c4befdfa77159bc91955c95`.
Postflight verified all three stages and the unchanged harness. Main was
restored to the incumbent overlay; candidate branch
`integrate-zlib-zip-image-39`, stage and raw evidence remain preserved. No retry
or source improvement is accepted. Source38 subsequently completed its own
terminal memory rejection, recorded above.

Two bounded source scouts also closed without implementation or runtime work.
Socket without the Rust standard library repeats the actual `e69ac90` /
`e41a364` trials, whose archived memory rows were neutral; their historical
acceptance was CPU-only. Regex scratch alignment has no demonstrated resident
page saving: only 32 KiB of zero-fill was resident, the live memo/hot arena
prefix exceeds one 16 KiB page, and moving it away from already dirty data
can add a page. A datetime input-borrow/core-runtime scout likewise closed:
the exact `6a9f3e8` mechanism already had neutral archived memory results,
with no retained input-buffer owner. A singleton marshal builtin-placement scout remains distinct
from the historical five-helper trial, but its physical saving is uncertain
and was subsequently authorized as the bounded source40 candidate above.

The socket/SSL pair-image scout also closed: `_ssl_rs` is already builtin in
libpython, leaving no second standalone helper image to eliminate. Moving
socket into libpython repeats rejected builtin placement rather than establishing
a distinct removable page. No implementation or runtime experiment followed.

A separate source-only struct scout found a real 8-byte format copy and six
temporary 32-byte Rust operations per call, alongside the retained C Struct
format. The Rust plan drops on return and accepted calls bypass the C cache;
no second retained cache or exclusive physical-page cost was established.
The scout closed without a build or runtime experiment. Its temporary
allocation count does not explain the unresolved load goal.

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
baselines. Earlier results below describe historical builds.

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
must continue reaching Rust. At that historical checkpoint, eight memory
lanes targeted ast, threading, statistics, logging, ipaddress, configparser,
subprocess and difflib. Regex eligibility and strptime awaited primary-path
judgment. The checkpoint state was recorded in
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

The latest [all-71/all-23 absolute snapshot](rust-cpython/results/perf-bench/20261004T083451Z-perf-upstream-vs-perf-rust/verdict.json)
compares accepted incumbent `e702f23` with pristine control `7351620`.
It reads **12 OVER, 15 UNCLEAR, 43 MET, 1 BEYOND**, leaving **27 unresolved
module goals**. This replaces the older merged classification table; UNCLEAR
rows do not satisfy completion. The historical `7cf55a6` snapshot and focused
follow-up remain preserved at `20261003T152630Z` and `20261003T160906Z`
(15 OVER, 8 UNCLEAR, 47 MET, 1 BEYOND). Differences between separate absolute
snapshots do not alone establish source causality or newly completed goals.

The new run finished in 753 seconds with standard sampling, two independent
runs, five module rounds, matched home and executable aliases, matching
outputs and no unstable metric. Harness `f741f178` was clean; fresh incumbent
self-calibration `20261004T081619Z` passed. CPU, timing and quietness are
excluded. Verdict SHA256 is
`4b737934b59343e0c8a5537a138dc5c5110cac3cdf87bb7ea6c996c646d5f0e3`.
Ratios below are saved pooled medians and statuses are coded memory-only goals.

| Route | Load footprint | Working peak | Memory status |
| --- | --- | --- | --- |
| `_strptime` | 1.024x UNCLEAR | 1.000x MET | UNCLEAR |
| `argparse` | 0.786x BEYOND | 1.000x MET | MET |
| `ast` | 0.722x BEYOND | 1.000x MET | MET |
| `asyncio` | 0.931x MET | 0.340x BEYOND | MET |
| `base64` | 1.073x OVER | 1.000x MET | OVER |
| `binascii` | 1.019x UNCLEAR | 1.000x MET | UNCLEAR |
| `bisect` | 1.000x MET | 1.000x MET | MET |
| `bz2` | 0.992x MET | 1.000x MET | MET |
| `codecs` | 0.996x MET | 1.000x MET | MET |
| `collections` | 1.225x UNCLEAR | 1.000x MET | UNCLEAR |
| `compression.zstd` | 0.802x BEYOND | 1.312x OVER | OVER |
| `concurrent.futures` | 0.483x BEYOND | 1.000x MET | MET |
| `configparser` | 0.592x BEYOND | 0.712x BEYOND | BEYOND |
| `contextlib` | 1.013x UNCLEAR | 1.000x MET | UNCLEAR |
| `csv` | 1.019x UNCLEAR | 1.000x MET | UNCLEAR |
| `dataclasses` | 0.899x MET | 0.562x BEYOND | MET |
| `datetime` | 1.750x OVER | 1.000x MET | OVER |
| `decimal` | 1.571x OVER | 1.000x MET | OVER |
| `difflib` | 0.151x BEYOND | 1.000x MET | MET |
| `email` | 0.929x MET | 0.878x BEYOND | MET |
| `fnmatch` | 0.372x BEYOND | 1.000x MET | MET |
| `fractions` | 1.032x UNCLEAR | 1.000x MET | UNCLEAR |
| `functools` | 1.000x MET | 1.000x MET | MET |
| `glob` | 0.333x BEYOND | 1.000x MET | MET |
| `gzip` | 0.740x MET | 1.000x MET | MET |
| `hashlib` | 1.003x MET | 1.000x MET | MET |
| `heapq` | 1.000x MET | 1.000x MET | MET |
| `hmac` | 1.008x MET | 1.000x MET | MET |
| `html.parser` | 1.030x UNCLEAR | 1.000x MET | UNCLEAR |
| `http.client` | 0.986x MET | 1.000x MET | MET |
| `importlib.metadata` | 0.858x BEYOND | 1.000x MET | MET |
| `importlib.resources` | 0.838x BEYOND | 1.000x MET | MET |
| `inspect` | 1.037x OVER | 1.000x MET | OVER |
| `io` | 1.000x MET | 1.000x MET | MET |
| `ipaddress` | 1.025x UNCLEAR | 1.000x MET | UNCLEAR |
| `itertools` | 1.000x MET | 1.000x MET | MET |
| `json` | 0.817x BEYOND | 1.000x MET | MET |
| `logging` | 0.628x BEYOND | 1.000x MET | MET |
| `lzma` | 0.110x BEYOND | 1.000x MET | MET |
| `marshal` | 1.008x MET | 1.000x MET | MET |
| `multiprocessing` | 0.907x MET | 1.000x MET | MET |
| `os.path` | 1.000x MET | 1.000x MET | MET |
| `pathlib` | 0.615x BEYOND | 1.000x MET | MET |
| `pickle` | 1.010x UNCLEAR | 1.000x MET | UNCLEAR |
| `plistlib` | 0.228x BEYOND | 1.079x UNCLEAR | UNCLEAR |
| `random` | 0.733x MET | 1.000x MET | MET |
| `re` | 1.211x OVER | 1.000x MET | OVER |
| `shlex` | 0.549x BEYOND | 1.000x MET | MET |
| `shutil` | 0.824x BEYOND | 1.000x MET | MET |
| `socket` | 1.059x OVER | 1.000x MET | OVER |
| `sqlite3` | 1.045x UNCLEAR | 1.000x MET | UNCLEAR |
| `ssl` | 1.010x UNCLEAR | 1.000x MET | UNCLEAR |
| `statistics` | 0.574x BEYOND | 1.000x MET | MET |
| `struct` | 1.021x OVER | 1.000x MET | OVER |
| `subprocess` | 0.870x MET | 1.000x MET | MET |
| `tarfile` | 0.754x BEYOND | 1.000x MET | MET |
| `tempfile` | 0.312x BEYOND | 1.000x MET | MET |
| `textwrap` | 0.089x BEYOND | 1.000x MET | MET |
| `threading` | 1.600x OVER | 1.000x MET | OVER |
| `tokenize` | 1.065x OVER | 1.000x MET | OVER |
| `tomllib` | 0.069x BEYOND | 1.000x MET | MET |
| `typing` | 1.185x OVER | 1.000x MET | OVER |
| `unicodedata` | 1.000x MET | 1.000x MET | MET |
| `urllib.parse` | 0.383x BEYOND | 1.000x MET | MET |
| `urllib.request` | 0.915x MET | 1.000x MET | MET |
| `uuid` | 1.136x UNCLEAR | 1.000x MET | UNCLEAR |
| `warnings` | 1.026x UNCLEAR | 1.000x MET | UNCLEAR |
| `xml.etree.ElementTree` | 0.988x MET | 1.312x UNCLEAR | UNCLEAR |
| `zipfile` | 0.275x BEYOND | 1.000x MET | MET |
| `zipimport` | 0.587x BEYOND | 1.000x MET | MET |
| `zlib` | 1.022x OVER | 1.000x MET | OVER |

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
No further uncertainty reruns are authorized for those historical rows.
These measurements precede the current absolute memory table.
Configparser shares mortal section names and values, preserves custom
proxy lookup behavior, and explicitly supports independent GILs. Distinct
parse/discard diagnostics retained 207,552 bytes of intern-table capacity;
strings themselves were released and candidate physical memory stayed below
control throughout that diagnostic. This is retained table capacity, not a
claim that all interning storage disappears on parser destruction.

### Memory follow-ups after batch 6

These historical follow-ups resolve the earlier `0628c7b` snapshot
without repeated draws; they precede the current absolute memory table:

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

The latest [full snapshot](rust-cpython/results/perf-bench/20261004T083451Z-perf-upstream-vs-perf-rust/verdict.json)
reads **12 RSS regressions, 6 neutral, 5 improved** across all 23 workloads
at accepted source `e702f23`. It uses the same fresh memory-only, matched-path,
replicated comparison as the module table. The decision is REJECT for
outstanding absolute debt, with no output mismatch or unstable metric.
The historical `20261003T152630Z` snapshot remains preserved (16 regressed,
3 neutral, 4 improved); cross-snapshot changes are not a causal attribution.
Baseline files remain unchanged.

| Workload | Peak RSS | Memory verdict |
| --- | --- | --- |
| `catalog_json_export` | 0.985x | improved |
| `catalog_request_path` | 1.030x | regressed |
| `catalog_search_form` | 1.009x | neutral |
| `catalog_url_normalize` | 1.005x | neutral |
| `compileall_source` | 1.062x | regressed |
| `difflib_unified_mostly_equal` | 0.943x | improved |
| `difflib_unified_reordered` | 0.941x | improved |
| `django_asgi_request` | 1.036x | regressed |
| `django_orm_10k` | 1.040x | regressed |
| `django_template_realistic` | 1.039x | regressed |
| `django_wsgi_first_request` | 1.062x | regressed |
| `django_wsgi_request` | 1.038x | regressed |
| `gzip_extract_1m` | 0.985x | improved |
| `import_django` | 1.035x | regressed |
| `multiprocess_pool` | 1.017x | regressed |
| `python_startup` | 1.027x | regressed |
| `rust_base64_large` | 1.010x | neutral |
| `rust_base64_small` | 0.994x | neutral |
| `serialization_roundtrip` | 1.029x | regressed |
| `zip_read_wheel` | 1.011x | neutral |
| `zipimport_cold` | 1.062x | regressed |
| `zlib_decode_1m` | 0.922x | improved |
| `zlib_stream_4k` | 1.004x | neutral |

Candidate acceptance compares against the qualified incumbent, retains
replicated memory guards and output checks, and requires complete suites.
Completion requires all 71 module load/peak goals MET or BEYOND and all 23
absolute workload RSS rows neutral or improved. Debt does not waive any goal.

## Sprint friction audit (2026-10-04)

The 23:29 UTC recheck found all31 child agents idle, with10 host cores,
64 GiB RAM, zero swap use and350 GiB free disk. This is a snapshot, not a
measured utilization average. The current frontier assessment supports one
distinct source-ready implementation, collections261; a JSON fallback
singleton assessment is a new bounded source investigation. The agent
ceiling is31, but filling slots with closed hypotheses does not create
31 useful implementations. The stitched accepted memory picture still has
26 unresolved module goals and12 absolute workload RSS regressions; it is
not a fresh full completion verdict.

Move the rejection-only target screen before expensive native ownership,
ABI and own-GIL qualification: build, run the smallest meaningful regression
and nearest focused suite, then take matched-prefix/matched-executable
standard two-run target memory samples. Only promising survivors receive
complete native proof and every affected complete suite, followed by all23
workloads and final clean broad71/all23/default-resource qualification.
This order changes no acceptance invariant. Compatible source exploration
uses incremental builds; carrier/Cargo/registrar topology still requires a
clean build. Source investigation continues during exclusive RSS draws;
native builds and tests share the host only outside those draws, with at
most two builders and a combined worker budget appropriate to ten cores.

Recorded examples put target screens near9s, eligible incremental builds
near33–35s, clean builds near216s and one full broad comparison near684s.
Build/benchmark durations include unseparated lease waits; native proof
cost and coordinator idle duration are unmeasured. Roughly18s of repeated
installation-size summaries is only2.6% of that broad example. The larger
frictions are coordinator latency, low physical-memory experiment yield,
repeat mechanism investigation, fixture/wrapper mistakes and serialized
measurement. Logical allocation and binary-size savings do not by themselves
prove fewer resident pages. Do not replace final replication or Rust-route
proof with modeled savings, and do not reopen the canceled mimalloc work.

The initial live-agent snapshot had zero running children among 31 available
child slots. This was coordinator underuse. The host has 10 cores, 64 GiB
RAM, zero swap usage/traffic, and 374 GiB free disk; it was lightly loaded.
Agent capacity is remote reasoning capacity, not 32 local compiler cores.
Source implementations, fixture preparation and independent review overlap;
RSS measurements remain exclusive to avoid competing allocations changing
resident-page behavior. Native exploration uses incremental builds (recently
34–35 seconds rather than 216–218 seconds clean), at most two builders,
and no clean/full qualification for rejected discoveries.

The latest 15 measured source candidates produced zero adoptions. Median
first-screen duration was 233.3 seconds; workload RSS guards rejected 14,
and logging working peak rejected the other. Most intended target metrics
were neutral. Allocation reductions are not resident-page reductions:
saved same-source observations had nearly equal live allocations but
hundreds of KiB of different malloc-zone residency. The causes remain
unproven. Twenty-four unresolved module goals are load-only and three are
working-only; module-local temporary-buffer optimizations mostly address
already-passing working metrics.

Exploratory all23 sampling on every candidate was an avoidable coordinator
policy. Discovery now selects only the target module and directly affected
workloads, retaining standard two-run replication, output checks, floors,
matched paths and stage guards. A target discovery survivor must pass broad
all71/all23 memory checks before clean/full qualification and adoption.
This changes verification order, not acceptance or completion requirements.
CPU, timing and host quietness do not gate any memory step. Calibration is
reused for six hours unless stage, harness, toolchain or host conditions
invalidate it; no per-candidate refresh.

The bounded follow-up audit found44.7 minutes of recorded comparisons in
the latest15 closed verdicts: four target-only terminal comparisons took
60.3s total, ten focused-module/all23 requests took2233.3s, and one broad
request early-rejected after386.4s. Five documented clean builds totaled
1099s; seven incremental builds totaled242.5s. These durations are not
additive sprint wall time: source work and builds overlap, and recorded
timers can include lease waits. No full qualification suite ran after those
rejections. Exact coordinator idle time is unavailable from the receipts;
the zero-active-child snapshot proves underuse at that instant only.
New candidates use unique runtime tags and suite names from the pinned test
inventory to avoid stage identity bookkeeping and incorrect suite requests.
Source work continues during exclusive memory draws. Native builds and tests
wait for that lease;31 reasoning lanes cannot create31 local compiler cores.

StringIO222 passed six behavior and three allocator checks and complete
I/O/logging suites (1,316 run, 33 skipped), then early-rejected in 169.4s:
`20261004T155539Z-perf-rust-vs-perf-plistlib208`, replicated zlib streaming
RSS regression. The candidate and raw partial observations are archived;
there is no published replicated module result or adoption. Region223
retained XML's working excess, but zstd's excess was inconsistent and
plistlib reversed direction; endpoint maps do not establish a causal owner.

Compact XML tokens224 replace copied long plain ASCII text with inline
owner-index tokens plus strong references. Source accounting models 60 KiB
less reserved capacity, not a measured RSS gain. Its independent source
review found no concrete hole; callbacks temporarily observe one extra
reference to captured exact strings, restored after return. The incremental
build verified 58 release extensions in 34s and the complete two direct
XML suites passed (480 run, 12 skipped). Seven native behavior cases passed on accepted and candidate stages; three
actual-production decoder tests also passed. Target-only standard two-run
discovery finished in 8.8s: `20261004T162031Z-perf-rust-vs-perf-plistlib208`
reads NEUTRAL, load 1.027x and working 0.920x, both neutral in both runs.
The candidate is closed without all23 screening, clean/full qualification,
unchanged retry or adoption. Accepted goal status remains unchanged.

### Threading metadata and single-engine regex candidates

Threading226 source `518c34a` moves the helper's method, slot and module
definitions into the existing C thread translation unit, and statically
links its unchanged Rust transition callback through the existing carrier.
The private helper now has builtin provenance and no `__file__`. Its clean
build verified 57 installed shared Rust extensions in 217s; the helper is
builtin instead. Six native lifecycle/dispatch cases passed, and its actual
builtin callable address equals the exported Rust callback. Complete
`test_thread` and `test_threading` passed 281 tests with five skips. Static
symbols place helper and existing thread tables on the same 16 KiB page
at `0x530000`; this establishes binary cohabitation, not an RSS saving.

The first standard two-run target screen finished in 8.8s:
`20261004T164205Z-perf-rust-vs-perf-threading226`. Load is neutral because
one run is neutral and one better, despite pooled 0.583x [0.500, 0.667];
working peak is neutral. A single rigorous absolute target check on the
same artifact, ten rounds per run, then read load 0.800x [0.800, 0.800]
improved in both runs, with working peak neutral at the floor:
`20261004T164556Z-perf-upstream-vs-perf-threading226`. This is exploratory
evidence of the actual goal, not adoption. All71/all23 screening against the incumbent early-rejected on replicated
compileall RSS 1.019x [1.018, 1.019]:
`20261004T164732Z-perf-rust-vs-perf-threading226`. The complete request
stopped at that run2 workload; no replicated module result is published
from this partial broad screen. The candidate is closed without full
correctness qualification, adoption or unchanged retry. The focused
absolute target result remains exploratory and changes no accepted goal.

Regex225 aims to replace its duplicate legacy execution backend with the
existing borrowed SRE engine, retaining pinned regex-syntax parsing. The
old legacy helper's compiler-size admission is an implementation resource
policy, distinct from syntax and public results. The replacement explicitly
may execute valid patterns previously declined only by the old compiler's
allocation limit. Nullable-repeat scratch admission uses a documented 10 MiB
budget and may decline additional private-helper cases; public `re` uses
its existing fallback on decline. Canonical compiled-pattern routing stays
unchanged. Old helper results are retained as baseline evidence, with
separate candidate admission tests. The clean build verified 58 release
extensions in 234s; complete `test_re` passed 169 tests with four skips.
All 22 native contract tests and 49,324 old/new span comparisons passed,
including interrupt identity and recovery. The helper binary shrank from
1,273,600 to 611,840 bytes, but target-only memory discovery was NEUTRAL:
`20261004T171905Z-perf-rust-vs-perf-regex225`, load
0.987x [0.949, 1.014] and working peak 1.000x, neutral in both runs.
The candidate is closed without broad screening, full qualification,
unchanged retry or adoption. Binary size does not establish resident-memory
savings. The original baseline's claim that `a**` was invalid was
wrong: the locked Rust parser accepts it. The corrected baseline passed
all three cases, and the original failed receipt remains preserved.

The warnings227/collections228 metadata batch229 encountered two integration
failures before measurement. Its first install failed because warnings had
both shared and static registrations; `bbc3f6a` removed the shared duplicate.
The second build compiled and installed, but final artifact verification
rejected the missing explicit builtin declaration for collections. Both
failures are retained; neither build is qualified. These were missed source
contract checks, not host resource limits. Declaration and carrier review
now precede the next build.
Adding the declaration exposed the absent Cargo JSON artifact receipt;
incremental attempt6009 also failed final verification. The existing carrier
recipe now captures genuine Cargo JSON without a pipe or hidden exit status
in `6573c4c`. Both declaration and receipt source regressions failed before
their fixes and passed afterward. The required clean rebuild is pending;
the verifier and memory acceptance rules remain unchanged.
The corrected clean build passed in216s with56 shared release extensions
and the explicit collections builtin artifact proof. Complete collections,
deque and warnings suites passed392 tests with8 skips. Six collections and
seven warnings native contracts passed, with actual Rust callback-address
equality, clean child reaps and unchanged stage guards. Warnings' genuine
Cargo archive/rlib/final-core proof passed separately through existing
parsers. An initial host assertion incorrectly expected the export-only
parser to expose a local C initializer; that failure is retained separately.
The standard target screen took15.0s and was NEUTRAL:
`20261004T173223Z-perf-rust-vs-perf-c-metadata229`, collections load0.800x
[0.733,1.000] and warnings1.031x [0.988,1.090], both working peaks neutral.
One rigorous control comparison took27.6s:
`20261004T173400Z-goals-perf-upstream-vs-perf-c-metadata229`, collections
MET at the64KiB floor, warnings OVER at1.05x. These remain exploratory;
Rigorous paired target qualification then remained NEUTRAL:
`20261004T174030Z-perf-rust-vs-perf-c-metadata229`, collections pooled
load0.757x [0.667,0.917] and warnings1.031x [1.013,1.050], but neither
established an improvement in both independent runs. Working peaks were
neutral. The batch is closed without all23/all71 screening, full
qualification, unchanged retry or adoption. Local goal evidence does not
replace replicated paired acceptance.

The accepted interpreter's fifteen previously UNCLEAR goals received one
rigorous two-run, ten-round clarification:
`20261004T173621Z-goals-perf-upstream-vs-perf-rust`. Binascii is now MET;
UUID and warnings are OVER; twelve remain UNCLEAR and unresolved. Combining
that partial clarification with the unchanged full accepted snapshot leaves
14OVER,12UNCLEAR,44MET and1BEYOND. This is an evidence update, not a new
integration or a full completion run. The original all23 workload evidence
is unchanged. Collections remains UNCLEAR at1.25x in this accepted run,
which motivates one rigorous paired qualification of its candidate gain.

Collections-only230 removes the nonwinning warnings change from229. Its
clean build verified57 shared release extensions and the collections
builtin proof in216s; six native contracts and callback-address equality
passed, as did392 tests with8 skips across collections/deque/warnings.
Standard target discovery took8.8s and remained NEUTRAL:
`20261004T175244Z-perf-rust-vs-perf-collections230`, pooled load0.733x
[0.619,0.917], but neutral in both independent runs. One rigorous target
qualification likewise remained NEUTRAL:
`20261004T175455Z-perf-rust-vs-perf-collections230`, pooled0.800x
[0.733,1.000], working peak neutral. The isolated composition is closed
without broad screening, full qualification, unchanged retry or adoption.

Candidate filtering had incorrectly required savings at least as large as
the64KiB load or256KiB working floor in some source assessments. Those
floors normalize measured values; they are not minimum saving sizes. Above
the normalized floor, smaller repeatable resident-page reductions can
qualify under the unchanged1% practical threshold. New source assessments
use the actual gap and normalized ratios.

Datetime231 placed C-owned metadata beside the accepted builtin datetime
tables, preserving existing Rust bridge code. Its clean build verified57
shared extensions in216s; six native cases, seven callback addresses and
actual Cargo archive/rlib/core symbol proofs passed. Complete datetime,
strptime and time suites passed1285 tests with83 skips. Target discovery
`20261004T181219Z-perf-rust-vs-perf-datetime231` improved load0.714x
[0.625,0.833] in both runs, with working peak neutral. The all23 RSS screen
`20261004T181314Z-perf-rust-vs-perf-datetime231` stopped after141.4s on
replicated python_startup RSS regression1.013x [1.012,1.015]. This candidate
is closed without adoption, all71 sampling, remaining suites or unchanged
retry. Old unchanged-table carrier packing also stays closed.

Typing233 similarly removes Rust-owned module metadata while retaining
both Rust callback algorithms and separate C builtin typing state. The
private helper becomes builtin and has no file attribute; public typing
behavior is unchanged. Its clean build verified57 shared extensions in216s.
Eight native cases, both callback addresses and actual Cargo
archive/rlib/core symbol proofs passed; complete typing and annotationlib
suites passed856 tests. Target discovery
`20261004T183153Z-perf-rust-vs-perf-typing233` improved load0.953x
[0.938,0.984] in both runs, with working peak neutral. The all23 workload
RSS screen `20261004T183312Z-perf-rust-vs-perf-typing233` stopped after152.4s
on replicated gzip_extract_1m RSS regression1.014x [1.013,1.015]. Typing233
is closed without adoption, all71 sampling, remaining suites or unchanged
retry. The partial broad screen does not publish a replicated typing result.

Inspect235 consolidates the original sorting epilogue across Rust and Python
collection paths, removing one retained nested key code object. Its clean
build verified58 shared extensions in219s; seven fresh native cases and
own-GIL fallback passed, as did381 complete test_inspect tests. An incorrect
baseline fixture expected one dynamic-class descriptor and included a
compiler-generated integer attribute; the accepted implementation returns
the descriptor twice. The fixture was corrected to preserve that behavior,
and the original failure remains recorded. Target discovery
`20261004T184543Z-perf-rust-vs-perf-inspect235` reads NEUTRAL: load1.011x
[1.006,1.017], working1.000x. The candidate is closed without all23/all71
sampling, remaining suites, unchanged retry or adoption.

Tokenizer234 consolidates C fallback replay into the existing generator,
removing the private `_c_tokenizer_tokens` function. Its clean build
verified58 shared extensions in232s; eight baseline and candidate cases
passed, as did137 complete test_tokenize tests. A fixture had wrongly
expected C fallback for ASCII bytes with an explicit encoding; the accepted
Rust scanner handles them. That expectation was corrected and its original
failure preserved. Target discovery
`20261004T185530Z-perf-rust-vs-perf-tokenize234` took9.0s and reads NEUTRAL:
load1.006x [0.997,1.022], working1.000x. This candidate is closed without
broad sampling, remaining suites, unchanged retry or adoption.

Socket237 obtains the same native `_functools.partial` directly when the
Python functools facade is absent. Existing facade bindings, including
patches, and ImportError fallback behavior remain tested. The intentional
boundary is the absent facade's import side effect and import-hook event.
Five accepted-stage semantic cases passed; fresh facade absence failed as
expected. Candidate six cases and full own-GIL lifecycle passed, as did750
socket suite tests with262 skips. The clean build verified58 shared
extensions in230s. Target discovery
`20261004T185358Z-perf-rust-vs-perf-socket237` improved load0.392x
[0.375,0.408] in both runs, with working peak neutral. The all23 RSS screen
`20261004T185630Z-perf-rust-vs-perf-socket237` completed in196.8s: every
workload RSS row neutral, socket load0.392x [0.381,0.396] improved in both
runs. Absolute target goals
`20261004T190223Z-goals-perf-upstream-vs-perf-socket237` read load0.41x
(440/1072KiB) BEYOND and working peak MET. Gated all71/all23 screening
`20261004T190325Z-perf-rust-vs-perf-socket237` completed in683.9s and
REJECTED: replicated gzip, http.client, marshal, tarfile, zipfile and zlib
load regressions, plus logging working peak1.852x. Socket stayed improved
and all23 workload RSS rows stayed neutral. Socket237 is closed without
adoption, full correctness qualification or unchanged retry.

Configured-source comparison found socket.py to be the sole common-file
production difference; C/Rust/Cargo sources and compiler policies matched.
All58 recorded Rust extension hashes nevertheless differ between the two
builds. The unrelated module regressions therefore have unresolved build
attribution; neither source identity nor a local win waives the measured
guards. No physical cause has been established.

Controller-only preflight236 is integrated: source declarations, carrier
dependencies, abort policy and genuine Cargo receipt capture are checked
before external build commands, with post-build artifact proofs retained.
The integration also carries the previously tested exploratory early-stop
and scratch-cleanup changes onto main, so new branches retain them. A first
controller check found that the preflight tests depended on ExitStack from
those earlier changes; carrying the complete tested controller restored all
71 passing tests. The runtime overlay still matches accepted e702f23
byte-for-byte. Memory calibration must be refreshed for this controller
identity before further qualification.

Exploratory batch243 combines four independently prepared Python changes:
CSV reader predicate inlining, release of Fraction's completed operator
factory, cold alternate-digit data, and cold IPv6 validation. Six production
files match their frozen donors exactly; the header adds exactly the two
new private module names. Its clean build verified58 extensions in394s,
including measurement-lease waiting. Individual candidate fixtures and
target-only screens remain pending; no component is adopted.

## Memory sprint continuation (2026-10-04, UUID258)

The subsequent accepted-only co-import inventory264 completed71 successful
fresh-kernel observations at the unchanged e702 stage. Each observation records
helper origins after baseline, declared imports, first setup/call and second
setup/call. First and second results match, stage/source guards pass and every
owned process group is reaped. The initial multiprocessing diagnostic lacked
the spawn entry-point guard; that forced-9 failure is preserved and only that
route was rerun with a versioned guarded launcher, making72 attempts overall.
After excluding builtin/nonshared, no_std and always-baseline helpers, no pair
has identical presence vectors at every phase across all71 kernels. This
closes the proposed equivalence-derived shared-image partition without an
implementation; import equivalence alone would not prove resident savings.
The completed summary SHA256 is
`f5947fdeb4b51f64e25aaf56fbdf98cf0b4f2e821a89203f439ae9b5966b9d6c`.

Post-inventory inspection found the six unchanged regex kernel programs have
42,69,36,70,45 and40 words. An independent source bound limits their validator
pending list to20 entries: ordinary instructions add no net pending entry,
at most17 disjoint four-word repeat headers add one each, and the sole
two-arm branch adds at most two. Both buffers therefore fit the closed187
256-word/32-entry inline-storage experiment. Allocation-free validator
algorithm263 has no uncovered fixed-kernel allocation owner and closes before
implementation. This conclusion does not cover uncaptured workload programs.

Regex265 instead targets the cold helper module/image through the existing
core SRE owner, using the unchanged borrowed-program executor in a small local
kernel crate. The standalone helper and its allocator remain separate. This
experiment intentionally suppresses the initial private helper import on the
cold path, including unsupported programs that return False/status0 and use
the native Pattern fallback. Context refusals return NotImplemented before
conversion and retain the original getter/cache/preloaded-provider path;
existing getter overrides, module-map entries and interpreter behavior remain
contracts. Its original accepted borrowed-program fixture passes all12 cases,
including legacy hooks and own-GIL fallback.

Regex 265 is now closed without adoption. Donor commits 602e95e/1866c4a and narrow
free-threaded refusal aedcdbd were integrated on isolated primary branch
integrate-regex265 as 4461325. The local borrowed-only rlib preserves the
standalone helper, its allocator and legacy backend. Independent source review
caught the missing free-threaded context refusal; the corrected route declines
before conversions and Rust entry. The flag fixture intentionally changes the
initial helper-import expectation while preserving native flags and matches.

The clean build passed in 217s with 58 verified release extensions; the compatible
four-line correction rebuilt incrementally in 33s. All 27 candidate contract
cases passed (cold 8, unchanged borrowed 12, flags 7), including provider mutation,
import hooks, native fallback and own-GIL behavior. The complete test_re suite
passed 169 tests with 4 skips; eight neighboring suites passed 1,881 tests with 102 skips in 28.3s. Candidate stage
identity is bb2ebb719af91f743d671fb0c1aaf0aa148acd1b400af2e7baefb95de80dba87.

Matched standard two-run target sampling at 20261005T002358Z was NEUTRAL,
load 0.961 [0.942,0.981], independently better/neutral. The sole predefined
higher-sample target screen at 002419Z improved in both runs: load 0.946
[0.924,0.967], working 1.000 neutral. Their verdict SHA256s are
40abcca942fa9b132928ce0da51e2796e0c8da415c38f8653a26918d41b0f750 and
5ee28582b0e1e71fcb31f70a991d7c7339a214296624811711f3c2c7a8e5cf0d.

The re/all23 exploratory comparison at 002549Z took 198s; all 23 workload RSS
guards were neutral, while re standard load was neutral again (pooled 0.942).
The subsequent all 71 request at 002918Z early-rejected after 294.8s: tarfile load
regressed in both runs to 1.067 [1.043,1.097]. Fourteen routes completed paired
sampling; the other 57 are incomplete, not passes. Broad verdict SHA256 is
91ed1362e813cc58b3358b52de346b01d5d4cbfcf6dbc542aef9724695e4cee8.
The physical cause of the neighboring regression is unproven. No unchanged
retry, final clean/full qualification, final gate or adoption follows. The
accepted overlay and 26 unresolved module goals and 12 absolute workload memory goals
remain unchanged.


Two small shared-image trials followed as 266 and 267. The perfect co-import
condition used by inventory264 was a source-selection assumption, not a memory
acceptance requirement. These trials instead selected observed co-use in module
kernels while retaining single-helper kernels as guards. Both preserve original
helper bodies, facades, independent initializers, lifecycle definitions, allocator
and linker policy. Original extension names become relative aliases to one
canonical binary; resolved file identity deliberately changes.

Tokenize/warnings266 donor b917c2e/8784134 was primary-built at bc8b7b6 in 217s
with 58 verified release extensions. The original four behavior/lifecycle cases
passed on the accepted stage. Complete warnings/tokenize suites passed 328 tests
with 6 skips. The first three-case candidate run failed a fixture assertion that
compared the canonical installation parent with the temporary prefix's lexical
parent; receipt 88300/d182cb is preserved. Fixture-only ea1ac46 (primary7b11e3d)
canonicalizes both parents, retaining every relative-alias, definition and export
assertion. The same three cases then passed as 29761/e37c4a; production and the
built stage stayed unchanged. Stage identity is
41e152a04410ab40a426c299f8d47e3d21f91b9a68ec2d716d0e5e5ea6a02eff.

Its matched standard two-run warnings screen at 20261005T011012Z was NEUTRAL:
load 1.024 [1.000,1.051], independently worse/neutral; working 1.000 neutral.
The recorded 186.9s includes waiting behind the second trial's build lease;
it is not the target sampling time. Verdict SHA256 is
c5e8ebbcc65db30ad021dc23ccc1fba28f0f7903a24210abb8d0c96ac51338bb.
No target retry, deferred lifecycle/native ownership tests, broad workload/module
sampling, final qualification or adoption follows.

Dataclasses/logging267 retained its null-slot single-phase dataclasses admission
and logging's own-GIL slots. Fixture-first e5e10ef, production3934acf and license
follow-up ffb1d2f clean-built in its isolated worktree in 224s with 58 verified
release extensions. Five original baseline cases and four early candidate cases
passed, including original admission, mutable hooks, independent module ownership
and the new alias identity. Complete dataclasses/logging suites passed 570 tests
with 6 skips. Its candidate stage is
a3b7d5941c60c3040ec17296ab51953c9a3612b36bf12a4e5afcc909207b4b30.

The matched standard two-run contextlib/asyncio screen at 20261005T011421Z took
19s and was NEUTRAL on all memory rows: contextlib load 1.002 [1.000,1.004],
asyncio load 1.006 [1.002,1.009], both independently neutral; working 1.000.
Verdict SHA256 is
c93bad8bac357b6ae6629b6ace80553e539696a73ff95dcb6b5353091f769faf.
The target load is about 8.5 MiB, making its 1% practical threshold about 85 KiB:
the proposed 32 KiB fixup-page saving was too small by itself to qualify. Future
source selection must compare the saving with the actual target scale before
implementation. No unchanged retry, deferred candidate tests, broad sampling,
primary rebuild, final qualification or adoption follows.

Read-only accounting verifies both built pairs actually collapsed two separate
CONST/DATA fixup pages into one each. Total mapped extents fell 48 KiB for266 and
64 KiB for267, and both alias pairs resolve to one regular file/inode. This proves
artifact layout, not resident or physical-footprint saving. Accounting SHA256 is
dbb11031c6c4cf86bf6d0b794ed250e9eaf327b03c1a92218c3913be5882f033.
Both trials are closed. Accepted e702 and all unresolved memory goals remain.

Collections261 subsequently tested the cold helper-module ownership boundary
through a raw Rust callback in the existing C core. The unchanged standalone
helper remains installed; existing module-map entries retain the original
import and override path. Fixture-first source reproduced and fixed a
replaceable builtin-type anchor, and independent review corrected one
wrong-Counter fixture assertion. Those failures remain preserved.
Primary source4077b21 clean-built in217.1s with58 verified release extensions;
the nearest complete collections suite passed120 tests with1 skip.

Its matched-home/executable standard two-run target screen at233540Z was
NEUTRAL: pooled load0.691 [0.646,0.817], independently neutral/better;
working1.000 neutral. The sole predefined rigorous screen at233609Z also
read NEUTRAL: load0.800 [0.667,0.800], independently neutral/better, with
first-run upper bound1.000; working1.000 neutral. The verdict SHA256s are
`be44c964d3abfcb931a78d8f9d2b03e4d5d6f34104667ff2a696ddc779947287`
and`399364b324d9430f67172f85473ae9b4f839384c1872be12f2d9620e62e0d1fa`.
Collections261 is closed without native ownership qualification, all23/all71
sampling, full-suite qualification, unchanged retry or adoption. Its candidate
stage remains a070cb204ff50283669d1e5392fd04dbf754eb1d9c4a94b828e3b6159c8c5072;
the accepted overlay and26 unresolved module/12 workload RSS picture remain
unchanged. Early target screening avoided unnecessary broad qualification.

Bounded follow-ups found no distinct zstd context/workspace duplication or
ElementTree intermediate document graph. JSON already builds Python objects
directly; its eager fallback decoder owns less than roughly1KiB and remains
reachable through identity, override and construction-time behavior, so no
clear contract-preserving removal followed. Pickle262 instead targets its
per-call heap-allocated object-identity set: the existing100-node visit budget
bounds insertion attempts and permits stack storage. Fixture-first source
3dbcea3 and primary2c4791d replace only that set with100 pointer-sized stack
slots. Independent source review confirms the bound, identity semantics,
recursive ownership and error/protocol precedence. All seven unchanged
identity/boundary fixtures pass on the accepted runtime. The candidate clean
build passed in216.6s with58 release extensions verified, and the nearest
complete pickle suite passed1070 tests with47 skips.

Its matched-home/executable standard two-run target screen at234712Z was
NEUTRAL: pickle load0.997 [0.981,1.040], working1.000 and serialization RSS
1.000 [0.997,1.003], with no output mismatch or replicated regression.
Pickle262 is closed without candidate native/ABI qualification, all23/all71
sampling, full-suite qualification, unchanged retry or adoption. Its stage
is6f647fea7b58fb739151f98b8ff5a4ecff05ff6eda8153dfbb8b0594e15d6d56.
Eliminating the real per-call hash-set heap allocation did not establish an
RSS saving. Prior list-reservation, repeated-parser and initializer-ownership
trials remain closed; the accepted memory goals remain unchanged.

UUID258 hosts the eight unchanged Rust callbacks in the existing shared C
`_uuid` image while keeping the separately importable helper API. Cold helper
absence captures the C provider; subsequent standalone-helper patches have a
different owner. That private ownership and import-hook timing boundary is
explicit, and the unchanged accepted ownership oracle remains recorded as an
expected candidate failure rather than being weakened.

The first build failed because the replacement `makesetup` had mode0644.
Donor `bf0c351` restores0755 without changing its bytes; its two generator
cases now invoke the script directly and pass. Primary `37a199c` built clean
in215s with58 verified Rust extensions. Twelve native cases, eight callback
address/image checks, eight standalone API checks, actual Cargo archive/link
proof and own-GIL lifecycle pass. Complete UUID/OS suites pass667 tests with
118 skips. The replay leaves archive, shared images and installed stage
unchanged; all owned children and temporary directories are drained.

Matched two-run target discovery `20261004T223850Z` reads NEUTRAL: pooled
load0.922x [0.873,0.942], with one neutral and one improved run; working peak
is neutral. Its sole rigorous follow-up `20261004T223933Z` also reads NEUTRAL:
load0.941x [0.905,0.962], again neutral/improved. The first independent interval
is [0.887,1.000061], so replication does not establish an improvement.
UUID258 closes without all23/all71 sampling, full-suite qualification,
adoption or unchanged retry. All memory goals remain binding.

Base64259 donor `48af6e55`, primary `47fe324`, removes helper-module
construction by hosting the unchanged method table in shared C binascii.
Its clean build passes in214s with58 verified Rust extensions. Six accepted
baseline cases and eleven candidate cases pass, as do the getter/table image
checks, all21 callback pointer/flag checks and21 standalone API comparisons.
Actual Cargo archive/link proof leaves stage and artifacts unchanged. Complete
base64/binascii/email/zipfile suites pass2,712 tests with22 skips. Two host
generator cases exercise six direct executable invocations and preserve the
disabled/static/partial/custom/first-wins configurations.

Its first matched two-run target screen `20261004T224754Z` reads NEUTRAL:
base64 load1.011x [0.978,1.034], binascii load1.019x [1.000,1.038], both
working peaks neutral. Base64259 closes without all23/all71 sampling,
full-suite qualification, adoption or unchanged retry. The cold-helper
import/late-helper ownership boundary remains documented as experimental.
Socket260 donor `e820f84`, production `8ec7295`, primary compiled `6aadc34`,
hosts the unchanged callbacks in the original shared C socket image. The
initially absent helper is skipped; after native activation, helper absence
uses Rust directly. Initial helper providers and present-helper dynamic I/O
lookups retain their original path and callable lifetime across retries.
Cold-helper import-hook and deletion behavior are explicit private boundaries.
Its clean build passes in214s with58 verified Rust extensions. Eight corrected
accepted-baseline cases pass. All11 corrected candidate cases and the fresh
before-facade script pass; the unchanged old-hook contract separately fails
at the expected first ownership assertion, with no errors or skips. Two
initial fixture failures remain preserved: an incorrect hook/loader setup,
then a membership trap that intercepted legitimate importlib work. Fixture
fixes leave production and the installed stage unchanged; current fixture
commit `5d10e41` is recorded separately from compiled source.

Actual Cargo archive/link proof, table/getter ownership, all four C aliases,
both direct I/O exports, standalone helper and C initializers, and four private
API/socketpair comparisons pass. All processes and temporary directories are
drained and stage/source/harness checks match. All seven socket suites pass
4,033 tests with396 skips, including the resource-denied socketserver module,
in57.6s. Its sole matched two-run target screen `20261004T230857Z` reads
NEUTRAL: load1.000x [0.959,1.028], working peak1.000x. Socket260 closes without
all23/all71 sampling, full-suite qualification, adoption or unchanged retry.

The decimal direct-output source scout closes without a patch: `8f0f124`
already used stack-only output, with no output Unicode, Python argument or
per-call capsule allocation. Raw limb output would remove formatting and
reparsing work, but no distinct heap saving was established. Its exact
historical memory-verdict pin remains unknown; this is a source closure,
not a new measured result. A startup codec scout likewise finds borrowed
buffers and required results rather than a new removable heap owner.

Two actual incumbent import-time profiles of Django ASGI and ORM each record
the same39 Rust helpers once. This establishes shared loading, not duplicate
retained objects or physical savings. A bounded build-attribution comparison
also finds matching Cargo metadata and compiler flags for an unchanged
collections route despite different absolute build paths; artifact section
comparison finds collections and CSV sections/layout identical; their byte
differences are install ID, UUID and signature metadata. Zlib's longer install
ID shifts its text offset by64 bytes and changes real code/data bytes despite
equal segment sizes. This is not an RSS explanation, and the previously
rejected before-link stable-install-ID experiment209 remains closed.

## Cold capability helpers272–275: closed target discovery (2026-10-05)

An accepted/control six-checkpoint `compileall_source` diagnostic found
`TemporaryDirectory` first use loading shutil and its compression capability
providers. The accepted-only `_shutil_rs`, `_zlib_rs` and `_lzma_rs` images
retained288KiB resident/96KiB dirty in the saved trace. The entire736KiB
preparation increment was not removable helper cost; control loaded the
common providers earlier. The diagnostic is attribution, not acceptance.
Report: owner259 `results/accepted-control-attribution268/actual-output/report.json`,
SHA `bb72021bee2455f1f90dfed5b03685d329c96bdb9f4e47d663c4953f82c45803`.

Shutil274 matched already measured deferral `5aa4e4d` and was closed before
editing. Distinct LZMA272/zlib273 cold-helper candidates were combined with
two private `_imp` cache/importer queries275. The original clean build at
`baf84bd` passed214s/58 verified Rust extensions; corrected source `7f944b1`
rebuilt incrementally in33s. Complete lzma/zlib/shutil/tempfile suites passed
557 tests/83 skips in731ms. Accepted behavior fixtures passed19 cases;
candidate codec fixtures passed30 and native query fixtures passed9, including
own-GIL checks. All owned children were reaped, temporary directories removed,
and frozen-fixture/stage guards passed.

Retained regression-first fixtures also established real candidate defects:
Python-visible module-map membership traps passed accepted code and failed
the initial candidate; those fixes are included in `7f944b1`. Independent
review then found a plain rebound dictionary concealing the bootstrap object
and reentrant zlib import overwriting a provider owning an existing stream.
Actual selected execution confirmed accepted LZMA PASS/candidate assertion
failure and zlib candidate `RuntimeError` for a foreign provider's stream
state. The latter runner expected an assertion failure and exited1 when the
child reported an error; the original error receipt remains preserved.
Source fixes `eac81947`/`53dc21c1` and a combined private sys query
`10e132dc` are preserved unexecuted in isolated branches; none was adopted.

The rejection-only matched standard two-run memory screen on built
`7f944b1` took13.1s and was **NEUTRAL**: shutil load1.001x
[1.000,1.005], working1.000x; compileall RSS1.006x [0.999,1.013]. No output
mismatch or replicated target improvement. Verdict
`20261005T022024Z-perf-rust-vs-perf-cold272/verdict.json`, SHA
`cde0f2c569541993d7781cb2094aa2cb48b2574f77d6a6cd3f0e151bf5269014`.
Further rebuilds, broad draws and full qualification were canceled. The
known edge-case defects do not affect accepted code. All71/all23 goals and
accepted overlay `e702f23` remain unchanged; no CPU/quiet gate was applied.

The contemporaneous host has10 cores,64GiB RAM, zero swap use and344GiB
free disk. Source implementation, fixture preparation, independent review
and bounded owner scouts overlapped with root-native execution. The new
target screen cost13.1s versus33s incremental/214s clean compilation;
the expensive full loop did not run after neutral discovery. The bottleneck
remains finding physical resident savings that survive actual workload
measurement, together with coordinator latency and repeated closed leads.
Candidate admission must use the actual target's meaningful memory scale;
there is no universal64KiB minimum that excludes smaller module-page wins.

## Plistlib writer277–279: local peak win, workload rejection (2026-10-05)

The blanket64KiB source-admission filter was removed. A guarded paired
four-operation diagnostic of the exact plistlib kernel identified binary
dumping as the accepted run's observed page-growth phase:64KiB then16KiB
and16KiB, with the other operations flat. Instrumentation perturbs allocation
state; this is attribution only. Owner259's
`results/plistlib-phase279/actual-output/report.json` SHA is
`a94e434ae48c13410f610745b72daf7ac06c0fa94c70ff230df6d506984e5e89`.

Two independently reviewed writer owners were combined at primary `b27ba41`:
277 `0317364` partitions integer deduplication into signed i64 and high
unsigned u64 keys;278 `119be5a` stores node tags separately from full-width
typed payloads. Nominal fixed-input capacities shrink about8KiB and7KiB,
respectively. No pointer tagging, smaller length limits, output changes,
coverage removal, dependencies or CPU/quiet gates. Fixture-first tests use
the independent Python writer for exact bytes and cover all node variants,
integer boundaries, aliases/cycles, callback reentry/GC, snapshots and declines.
All10 cases pass on accepted and candidate interpreters; complete plistlib
passes71/0. Clean build23157 passes214s/58 verified Rust extensions. All
native children are reaped, temporary directories gone, and guards pass.

The8.3s matched standard two-run target screen shows working peak0.785x
[0.696,0.863], improved in both runs; load0.833x is neutral in both.
Verdict `20261005T024108Z-perf-rust-vs-perf-pl277a/verdict.json`, SHA
`abb74d56b03ba4deb8333844b06eed1cb8a2dd6d40c4614b9477c9bd2712ccea`.
The all23-workload request then rejects after158.6s on replicated difflib
mostly-equal RSS1.012x [1.012075,1.012094]. Sixteen entities complete; seven
workloads and the plistlib entity are incomplete. No all23 pass or accepted
module-goal improvement is claimed. Verdict
`20261005T024215Z-perf-rust-vs-perf-pl277a/verdict.json`, SHA
`5d1d1f5f44cd0636f56aa8a5cb987c5f9c0eb2d52a4b05384356aa0228a84f98`.
The cross-route cause is unknown. Broad71/full qualification and the prepared
three Rust representation-unit tests are canceled; no adoption or unchanged
retry. Accepted overlay e702 and absolute module/workload goals remain binding.

A difflib source follow-up disproves the proposed large string-span-vector
owner: accepted matching already indexes borrowed tuples and existing position
lists. Fixed workload sizes are512/511 and396/396 lines. Preserving dynamic
backend overrides retains the historical b snapshot, leaving only about4KiB
or3KiB transient tuple storage removable by a new callback-safe list view.
No source-supported100KiB owner was found and no edit followed. The separate
compat-pickle source scout also found required shared tuple/dictionary owners;
generator-to-comprehension cleanup removes no persistent load owner.

## Socket receive281: duplicate payload removed, memory neutral (2026-10-05)

Donor `f3d1ae0`, primary `a2b46ad`, replaces the Rust receive Vec with the
existing opaque CPython bytes writer. Rust still performs the syscall and
releases/restores the GIL; success consumes the writer, and errors/signals
discard it once. No dependency, ABI, provider or coverage change. The fixed
input requests8KiB and receives4KiB; removing their old payload overlap is
a logical allocation improvement, not proof of reduced resident pages.

Independent source review passes. All8 fixture cases pass on accepted and
candidate interpreters, including exact/short/EOF/error output, captured
retry providers, returning/raising signal handlers and two own-GIL lifecycles.
Candidate complete socket passes750 run/262 skips in57.5s. Children are
reaped, temporary directories removed and stage/fixture guards pass.
Reusing277's tree incrementally refuses four removed plistlib test files;
the separate clean socket build then passes214.3s with58 verified extensions.

The8.7s matched standard two-run target screen is NEUTRAL: load1.006944x
[0.986111,1.041687] and working1.000x, neutral in both runs. No output mismatch.
Verdict `20261005T033106Z-perf-rust-vs-perf-sock281/verdict.json`, SHA
`300b82e003c097aca6ff60dbae2dbb124057b11c327a5302448f54f5a2b7b5e0`.
No all23, broad71, full qualification, adoption or unchanged reroll follows.

Parallel source/artifact follow-ups close operator packing in tokenize: its
installed/Cargo image `c4514b10` already contains61 spelling bytes with no
rebases targeting that range, so no560-byte pointer table was established.
The proposed delimited blob would add34 literal bytes. Threading's distinct
lazy fallback-class design stops before production because its hidden cache
would prolong class lifetime after both aliases are deleted. Zstd's separate
static and dynamic engines are confirmed, but sharing that existing engine
repeats provider182's measured neutral trial. These closures do not impose
a minimum savings size or establish global exhaustion.

## Inspect positional-only range282: allocation removed, memory neutral

Fixture-first donor `9a0c2ba` plus corrected fixture `6fa5b09`, primary
`35f2cbd`, removes an unnecessary parameter-count pointer reservation.
Collected keyword names are a contiguous range into existing strongly owned
parsed parameters; getter, dictionary callback and error ordering are retained.
The fixed seven-parameter input avoids56 requested bytes per bind, not56
bytes of persistent memory. Independent source review passes.

All7 fixtures pass on accepted and candidate interpreters, including native
dispatch, independent Python diagnostics, partial binding, keyword collection,
dynamic getters, reentry and exception identity. Complete inspect passes381
tests in911ms. Native children are reaped and temporary/stage/source guards
pass. A source-plan search identifies compatible configured tree185: exactly
two changed files, no removals or build-system changes. Its incremental build
passes34.2s with58 verified extensions, avoiding another clean build.

The9.3s matched two-run target screen is NEUTRAL: load0.994471x
[0.991705,1.002789], working1.000x, both neutral in both runs. Raw working
medians32KiB versus16KiB are below the256KiB normalization floor; they do
not qualify an improvement. Verdict
`20261005T033713Z-perf-rust-vs-perf-regex-primary185/verdict.json`, SHA
`047ce644136d853f6ae021e119c71031b716460d8a1ee25e43359e3717f920af`.
No all23/broad/full qualification, adoption or unchanged reroll follows.
A distinct parsed-parameter representation owner is being investigated;
the existing neutral result remains binding for this exact source.

## Inspect compact parameter283: distinct layout, memory neutral

Donor `177ffe04`, primary `62d405b`, adds a private repr-u8 kind enum to the
unaccepted range282 variant. Full signed-long conversion and exception/getter
ordering stay unchanged; only values0/2/3/4 have special binding semantics,
and every other value retains ordinary behavior. A compile-time assertion
requires16-byte parameters instead of24; seven parsed slots save another56
requested bytes. No exported ABI or API changes. Independent review passes.

All12 fixture cases pass on accepted and candidate stages, including signed
bounds, high-bit aliases, conversion callbacks/errors and prior range cases.
Complete inspect passes381. Compatible two-file incremental build passes
with58 verified extensions. The matched two-run target screen is NEUTRAL:
load1.000x and working1.000x, neutral in both runs. No mismatch, all23/broad/full
qualification, adoption or unchanged retry follows. The exact new verdict is
`20261005T034802Z-perf-rust-vs-perf-regex-primary185/verdict.json`.

## Pickle direct output284: wire copy removed, memory neutral

Fixture-first donor `1c77372`, primary `9f4c0a8`, replaces the compact
serializer's intermediate Vec with a counting/bounded-output writer over
the same already-owned value tree. Both passes use the same locked serializer
and writer type; no Python conversion or callbacks repeat. Output allocates
exact unpublished PyBytes storage, checks every write, releases it on error
and retains the protocol patch and decline behavior. Independent review passes.
The fixed compact wire is61 bytes, with an old128-byte Vec reservation; the
large serialization workload declines before this output path. No physical
savings or improvement to that workload is inferred.

All7 fixtures pass on accepted and candidate interpreters, including wire
goldens, capacity/Unicode boundaries, eligible graphs, alias/cycle declines
and provider/error identity. Complete pickle/re suites pass1,239/51 in2.6s.
The compatible configured tree158 has the accepted Cargo.lock and unchanged
module/configuration rules; it restores accepted regex sources alongside the
pickle change and passes a36.4s incremental build with58 verified extensions.
Children are reaped and temporary/stage/source guards pass.

The8.6s matched two-run target screen is NEUTRAL: pickle load1.009842x
[0.999895,1.039225], working1.000x, both neutral in both runs. Verdict
`20261005T035623Z-perf-rust-vs-perf-correct158/verdict.json`, SHA
`f0da852724ae9624304f38f818e0d43bd04a12ca26f3dba555b758524939132c`.
No all23/broad/full qualification, adoption or unchanged reroll follows.
The two representation-unit tests remain UNRUN after this early closure.

## Rigorous absolute clarification285 (2026-10-05)

With accepted overlay e702 restored, compare the same verified control and
incumbent over the12 previously UNCLEAR modules, two independent runs of ten
rounds, memory-only and matched visible prefixes/executables. The185.6s
request completes all12 entities with no output mismatch. Verdict
`20261005T035823Z-goals-perf-upstream-vs-perf-rust/verdict.json`, SHA
`27fdf425825ec24971f1bc45312b1ccb2df8a3c0179f09d0bd0b352de88e7da5`.

| Route | Load | Working | Memory status |
| --- | --- | --- | --- |
| plistlib | 0.203x BEYOND | 0.946x MET | MET |
| _strptime | 1.009493x MET | 1.000x MET | MET |
| html.parser | 1.010000x MET | 1.000x MET | MET |
| ipaddress | 1.042372x OVER | 1.000x MET | OVER |
| collections | 1.250x UNCLEAR | 1.000x MET | UNCLEAR |
| xml.etree.ElementTree | 0.990x MET | 1.190x UNCLEAR | UNCLEAR |
| sqlite3 | 1.05x UNCLEAR | 1.000x MET | UNCLEAR |
| csv | 1.04x UNCLEAR | 1.000x MET | UNCLEAR |
| fractions | 1.03x UNCLEAR | 1.000x MET | UNCLEAR |
| pickle | 1.02x UNCLEAR | 1.000x MET | UNCLEAR |
| ssl | 1.02x UNCLEAR | 1.000x MET | UNCLEAR |
| contextlib | 1.01x UNCLEAR | 1.000x MET | UNCLEAR |

These are the harness's goal classifications; MET does not imply every
confidence bound is below the ceiling. Three prior uncertainty rows resolve
to MET and ipaddress becomes OVER. Stitching this with unchanged accepted
evidence gives15 OVER/8 UNCLEAR/47 MET/1 BEYOND, or23 unresolved and48 passing.
That stitched picture is not a fresh full71 completion proof. The23 absolute
workload RSS goals are not remeasured here; their12 recorded regressions
remain unresolved. No overlay adoption, CPU work or goal-completion claim.

### Live sprint bottlenecks and ipaddress closure (2026-10-05)

The04:13 UTC snapshot finds all31 children completed, no active native
command,10 host CPUs,64GiB RAM, zero swap use and342GiB free disk. Load
averages are1.37/1.27/1.29. This establishes idle capacity at inspection;
it does not measure average utilization or total coordinator delay.

The latest four implementations281–284 pass their focused correctness
checks but all target comparisons are NEUTRAL. Three compatible incremental
builds take roughly33–36s, versus214s for socket281's clean build; target
comparisons take8.6–9.3s. The implementation frontier is empty after these
closures. Agent occupancy alone will not supply additional distinct owners.

The newly confirmed ipaddress load excess is not explained by duplicate
functools descriptors: both versions have four cached properties, four LRU
decorators and two ordering decorators, with matching implementations and
cache layouts. The fixed kernel reaches only the final network's broadcast
property; Rust avoids the control's additional cached hostmask. Native
output bytes are temporary, and no Rust heap cache or capsule owner was
found. The48KiB excess remains unattributed. This bounded source inquiry
made no edits and launched no native work; it is not a global exhaustion
claim or a measured rejection of a new candidate.

Remaining friction includes coordinator scheduling, investigation of
already closed mechanisms, temporary-allocation edits aimed at load-only
debts, bespoke fixture-runner mistakes, and a large historical plan with
superseded instructions. Preserve historical evidence, but use the current
memory-first contract and corrected survivor-only verification order.
No CPU, timing or host-quietness requirement delays memory work.

### Four new implementation screens286–291 (2026-10-05)

Source work runs in parallel on gpt-6.1-sol at medium effort. Four distinct
implementations reach native execution; all are closed without adoption.
The primary overlay is restored to accepted e702. No CPU, timing or host
quietness gate applies, and no all23/full qualification follows these closures.

| Source | Mechanism | Native correctness | Target memory result |
| --- | --- | --- | --- |
| 286 `816036a` | Direct fixed-array ASCII address parser replaces std::net parsing; existing APIs unchanged | Six frozen cases pass on accepted/candidate; complete ipaddress215/0 passes; clean223.3s,58 artifacts verified | 8.8s; load1.000x and working1.000x, neutral in both runs |
| 287 `71acaf5` | Borrowed FASTCALL classification fields replace typing's per-call classinfo tuples | Six frozen cases pass accepted/candidate; two candidate-only cases pass; typing plus restored ipaddress954/0; incremental33.7s,58 verified | 8.5s; load0.968266x [0.953126,0.992312], both runs neutral; working1.000x |
| 288 `2e9c4e2` | Count a complete unknown-size immutable frame into16KiB scratch, then exact-size replay in the same DCtx | Frozen frame/state/error cases pass accepted/candidate; complete zstd119/0; clean223.2s,58 verified | Standard10.1s working0.927381x; one rigorous16.2s check working0.952381x; both checks neutral/better across independent runs |
| 291 `104c241` | Metadata upper bound caps the existing one-pass output growth; no count, replay or context reset | Expanded boundary/state/error cases pass accepted/candidate, plus288's frozen cases; complete zstd119/0; incremental34.8s,58 verified | 9.4s; load1.001985x neutral; working0.976190x [0.928571,1.026316], neutral in both runs |

Typing287 extends only the private helper forms from6/7 arguments to also
accept9/11; original forms remain supported. Public output ownership,
global lookup/callback order, nested classinfo and recursion behavior are
checked. The3600 eliminated classifier tuples are sequential allocation
traffic, not a retained-memory claim. No private extension is adopted.

The actual fixed Zstandard input is29885 compressed bytes decoding to262144
bytes. Its original seed119540 doubles to modeled capacity478160. This
logical capacity delta does not establish a resident reduction. Counting288
shows a pooled working benefit but fails independent-run replication even
with ten rounds; metadata291 remains neutral. The latter's exact C ABI
matches the pinned header, and the built image contains ZSTD_decompressBound.
The metadata bounds allocations, never decoded length or the public limit.

Saved target verdicts and SHA256:

- 286 `20261005T042919Z-perf-rust-vs-perf-ip286`: `fbf20f6dc1e7ed121dd26b989c249e33fe1e46a436914f6cf5b62308f2b746c2`.
- 287 `20261005T043155Z-perf-rust-vs-perf-ip286`: `a7b96bf0ba09d284e0d72d4cfcbf2c2ec60921766d29dfa3689cb0c8f4717728`.
- 288 standard `20261005T043859Z-perf-rust-vs-perf-zstd288`: `623100edd08d73aebada6aabd6c31230fdaab2fb03bb20e6b79a7328465ee9b2`.
- 288 rigorous `20261005T044014Z-perf-rust-vs-perf-zstd288`: `f3601e99569483272f6fe4f893deec93720072ddfc70f93bcdeea6c5cb5795a3`.
- 291 `20261005T045031Z-perf-rust-vs-perf-zstd288`: `5333eb92f7ad56d3ed64d46e2f8033a2ddf2e7d17c71c07ec4bae660c7e58a96`.

The exploration names are reused after preserving original reports/logs in
results/ip286-original and results/zstd288-original. Each verdict retains
its source/stage identity; the old source branches remain unmerged. Accepted
perf-rust and control stages are unchanged. Ordinary fixture children are
reaped, owned temporary directories removed, and pre/post stage and fixture
hash guards pass. An initial over-scrubbed build environment fails doctor
before compiling; the normal environment verifies the locked prerequisites
and succeeds. No toolchain substitution occurs.

Two parallel source inquiries stop before implementation. Threading289's
fixture confirms accepted fallback-alias lookup succeeds under a class-build
hook installed after import; a deferred constructor can recursively enter
that hook before its class exists. A boolean-only publication cannot preserve
that behavior. Core-bindings290 finds an exact previous typed bridge
fe69c04 plus collections d786dcc, including its C-abort handler and fixtures;
combined cd43345/core-batch168 already measured collections neutral and
compileall/catalog RSS regressions. This is prior combined-trial evidence,
not a newly measured isolated collections verdict.

The recorded memory picture remains48 passing/23 unresolved modules and12
absolute workload RSS regressions. No fresh full71 proof, debt waiver,
accepted runtime change or memory-completion claim follows this wave.

### Retained cache screens292–293 (2026-10-05)

Two new retained-owner implementations pass native correctness but close
without adoption. The accepted e702 overlay and48 passing/23 unresolved
module picture, with12 absolute workload RSS regressions, remain unchanged.
No CPU, timing or quiet-host requirement participates.

- Struct293 `59866e9` delays the C format-cache dictionary until native
  conversion; Rust-only calls retain no empty dictionary. Five existing
  lifecycle/error/reentry/thread/subinterpreter contracts pass accepted;
  the cold-owner assertion fails as expected. All seven candidate contracts
  pass, followed by complete test_struct47/0 in349ms. The compatible
  configured-tree build verifies58 Rust artifacts in34s. Its first natural
  path screen is neutral; a once-only correction adds the required matched
  home/executable flags and remains neutral in both runs, load1.000x and
  working1.000x. Corrected verdict `20261005T052854Z-perf-rust-vs-perf-zstd288`,
  SHA256 `13fcbbca118a6516d83480a27ef69a840dd4dfd15de9156575563126516c1003`. Earlier natural evidence is preserved, not
  treated as a matched comparison. GC introspection and allocation-failure
  timing change only in this unadopted source. Optional allocation-fault
  fixture b5766c3 remains unrun after target closure.
- Importlib292 `6d8ab11` avoids newly cached bytecode exclusively in the
  internal C pyc writer; the public Rust marshal getter stays unchanged.
  It preserves warm-cache identity, deoptimization and wire reference flags
  with temporary ownership. The immutable corrected fixture passes four
  accepted cases and fails six expected retention assertions; the candidate
  passes all ten. Clean build217s verifies58 artifacts; complete compileall,
  marshal and code suites pass264/14 in6.9s. The matched two-run compileall
  RSS target screen REJECTS1.017241x [1.016129,1.018354],6.4s. Verdict
  `20261005T053059Z-perf-rust-vs-perf-importlib292`, SHA256
  `4229ace80529b311718eff0234bf09834c75c4dde045b3f299e0dec115979199`.
  No all23, full correctness, adoption or unchanged retry follows.

The original marshal fixture used a ctypes argument owner that changed
selective wire flags; its failure is preserved. A subsequent shared-file
mutation failed the post-run fixture hash guard. Final source e81b261 is
snapshotted immutably before accepted/candidate execution, SHA256
`352d088deee54f2ccdef150e0f704069b8dd8b068cabefaf2d4e326659517f22`;
those final executions pass stage/fixture guards and reap their children.

Bounded source inquiries294/295 find no new large retained owner in the
actual application branches or SSL/SQLite/CSV/fractions tables. SSL's
ce59916 private error-name dictionary trial was missing from the central
index and is now indexed; its original memory rejection remains binding.
These inquiries do not establish impossibility or waive any goal. Fractions
297's independent seven-case fixture passes on accepted; its distinct Rust
text-grammar implementation remains unqualified in its isolated source lane.

### Fractions dependency screens297–302 (2026-10-05)

Native rational-text parser297 passed eighteen differential, Unicode,
digit-limit, hook-order and lifetime contracts plus complete fractions50.
Its compatible incremental build took36.5seconds with58 verified release
extensions. Three review defects were fixed: a hidden strong backend owner,
used matcher deletion, and invalid-input errors after backend-hook deletion.
The matched two-run memory screen was NEUTRAL: load1.000
CI[0.981259,1.012345], working1.000. Verdict
`20261005T054740Z-perf-rust-vs-perf-se79`, SHA256
`299e32e9532052d7be205a238614680a18a5c34ebdcb7682033660f2f68177f1`,
closes that one-pattern mechanism without an unchanged retry or adoption.

Distinct298 also defers both formatting-pattern owners and the otherwise
unused regex import graph during ordinary integer/slash construction. It
resets all matcher aliases on reload, correcting297's retained replacement
behavior. The private aliases are initially absent from the module dictionary;
explicit access or formatting publishes the required live alias. Regex import,
audit and allocation move to formatting, uncertain input or private lookup.
Published deletion and replacement lifetime remain covered. These boundaries
are explicit proposed changes, not an accepted runtime contract yet.

Four format/reload cases passed accepted; candidate298 passed all24 frozen
contracts and complete fractions50. Its first matched target screen improved
load to0.415 CI[0.400,0.427] in both runs, with working peak neutral. Adding
inspect299's AST import deferral and pickle301's Python-fallback struct deferral
formed source302 (`2f3c55c`). Seven pickle contracts passed candidate; accepted
passed six and failed only the expected retained struct-owner assertion. Six
complete suites passed1885/49 in2.8seconds, and six shared/own-GIL interpreter
cycles passed. Matched target screen `20261005T060059Z` retained fractions
load0.413 improvement, but inspect1.000 and pickle0.978 were neutral in both
runs. Those two target mechanisms are closed from the combined source screen,
without claiming individual isolation or adopting their deferral boundaries.
Source inspection explains inspect299's missing exclusive owner: annotationlib
imports AST before inspect reaches its own AST import.

The fractions-only survivor56db7b0 clean-built as
`perf-fractions298-qualified` in214seconds with58 verified release extensions.
All24 contracts, six interpreter cycles and complete fractions50 passed again.
Its broader eight-module/all23-workload matched memory screen REJECTED in
196.1seconds: catalog request RSS1.011361, CI[1.011047,1.011675], regressed
in both runs. Verdict `20261005T061144Z`, SHA256
`c9573c7bc32c86117e7c8c85b1129283f856b048c1aa41b41dd423dd4ebc40ac`,
stopped after the replicated workload rejection. The remaining second-run
workloads and module draws are incomplete; no replicated module verdict is
inferred from that partial screen. No full-suite/all71 qualification, adoption
or unchanged retry follows. The local fractions load win remains exploratory.
Accepted runtimee702f23 and the48 passing/23 unresolved stitched module picture
remain unchanged. CPU, timing and host quietness are excluded throughout.

### Annotation and arithmetic screens303–313 (2026-10-05)

Annotationlib303 addresses the transitive AST owner missed by inspect299.
It keeps the stringifier eager, uses builtin AST operators when Python AST
is cold, and delegates the private name-fixer visitor through a per-instance
captured base. Its proposed private MRO, class membership, capture timing
and non-visitor inheritance changes are explicit and remain unadopted.
Review caught metaclass hooks during descriptor lookup and accidental
AttributeError when `sys.modules['ast']` is None; regression-first corrections
use raw type structures and preserve delayed ModuleNotFoundError.

Source462678d passes eight frozen behavior cases, three activation checks,
four complete suites1457/2 and six shared/own-GIL interpreter cycles. Its
34.6-second incremental build verifies58 extensions; the matched target
screen improves inspect load0.963993 in both runs, working1.000. Verdict
`20261005T064127Z`, SHA256
`916cd3ebaf48e9917fb3579b13d3c929cae73f9c561e0ed42a47312aeac6c7b3`.
The clean equal-length `perf-a303` build takes214seconds and passes again.
Its six-module/all23 screen REJECTS after156.6seconds on compileall RSS
1.013597 in both runs. Verdict `20261005T064748Z`, SHA256
`68c6cc17695079c5d3af4a8725b2b8622dffd712bd73de2a03d1f25526f32a5d`.
Sampling stops early; no other replicated module result is inferred.

Read-only diagnostic304 found that fractions298's longer build tag added
one16KiB libpython LINKEDIT page through path strings and symbol metadata.
Future clean comparisons use equal-length build tags. This does not establish
RSS causality or reopen298. The equal-length303 comparison has identical
138-image segment extents and section bytes after tag substitution; all58
Rust helper files match after excluding UUIDs/signatures. Compileall compiles
23 fixed repository files rather than candidate stdlib sources, and its
bytecode digests match. No causal fix or unchanged retry follows303.

Independent source inquiries305–309 find no new removable owner in
ElementTree, SQLite, contextlib or warnings. CSV306's replay-class replacement
would add iterator callbacks and lose StopIteration identity/value, so it
closes before implementation without relaxing that protocol.

Decimal310 replaces general BigUint arithmetic with unbounded decimal limbs.
Five frozen cases pass both accepted and candidate runtimes; complete decimal
passes. The original fixture wrongly expected Inexact for999+1 at precision2;
the preserved failure is corrected to999+2, retaining both flag assertions.
Linked BigUint/radix symbols disappear, TEXT shrinks48KiB and LINKEDIT16KiB.
The34-second incremental target screen is NEUTRAL: load1.240295 with
worse/neutral per-run classes, working1.000. Verdict `20261005T065637Z`,
SHA256 `9506a1a602cc78029d757eaa3534bece9f356146b9473b22b3d870b1bb5e2edb`.

Distinct decimal313 removes the remaining Rust heap buffers from public
eligible arithmetic using inline limbs and stack ASCII output, preserving
unbounded heap fallback and the private API. Eight cases and complete decimal
pass; compatible incremental build takes33seconds with58 verified extensions.
Its matched target screen is NEUTRAL, load0.964223 CI[0.898,1.042] and
working1.000. Verdict `20261005T070927Z`, SHA256
`d5b1500a91e0da74e34830ac18a53836d1abae933c10e258b42219653e7d597c`.

Fractions312 replaces BigRational with normalized BigInt pairs and direct
cross-cancelled arithmetic, removing the num-rational package. Clean source
b30cbf1 builds `perf-f312` in213seconds, verifies58 extensions, passes five
differential cases on both sides and complete fractions50. Linked generic
ratio symbols disappear. The matched target screen is NEUTRAL: load1.012579,
working1.000. Verdict `20261005T070554Z`, SHA256
`5207886d7ccb46878aedd54e55ae3a19777844e20d7aa1410381aea477adddf6`.
None of these arithmetic screens proceeds to broad/full qualification,
adoption or unchanged retry. Accepted runtimee702 and all memory goals remain.

Harness311 adds an additive `phase_seconds` receipt field: lock acquisition,
stage verification, controller preparation, module iteration calibration,
module sampling and combined workload preparation/sampling. Existing totals,
pairing, samples, lease modes and verdicts remain unchanged. All74 controller
tests pass. The changed harness requires fresh memory-only calibration before
further comparisons; CPU, timing and host quietness remain excluded.

## Objective after coverage

### CSV engine and native holder screens314–318 (2026-10-05)

CSV314 replaces the high-level writer engine with `csv-core`, preserving the
Python callback and fallback boundaries. Primary `d9bcfb0` clean build
`perf-c314` takes211.3seconds and verifies58 Rust extensions. The 3,931-case
oracle, seven behavior contracts and complete CSV suite134/4 pass. The
two-run target comparison is NEUTRAL: load0.981160x and working1.000x.
Verdict `20261005T073054Z-perf-rust-vs-perf-c314` SHA256 is
`6f2711e9ac9f6c469d953f372a0a275b3b4abdfd00c3ab8b137235d0c4a7e9d2`.
Smaller native sections do not establish physical memory savings.

CSV317 removes the three Python proxy classes and routes Rust through native
CSV holders and a replay iterator. Native type, private-alias and instance
introspection changes were explicit experimental boundaries. Primary
`b1c7a9a` clean build `perf-c317` takes221.9seconds and verifies58 extensions;
17 candidate contracts and complete CSV suite134/4 pass. The7.4second
two-run comparison is NEUTRAL: load0.972223x, pooled interval
[0.894714,1.056631], and working1.000x. Verdict
`20261005T083552Z-perf-rust-vs-perf-c317` SHA256 is
`611c12323ab1a2351c289281a1846054d84a1d75c778dd6b1614a5820e2ab445`.

The separate corrected retained-owner diagnostic318 confirms the three
accepted CSV proxy classes survive native-reader fallback, with13,120 logical
bytes in their intrinsic type/function/code/property graph. Packet SHA256 is
`eb92c79f984638c8cf1cabc8148e26886db3cd145b6d327ea85e5719f841c6e3`.
This explains the source hypothesis, but is not RSS acceptance evidence.
Both314 and317 close without adoption, broad/full qualification or unchanged
retry. Accepted runtime and memory goal counts remain unchanged.

### CSV borrowing319 and pickle fallback deferral320: rejected guards

CSV319 preserves callback-sensitive rows and borrows exact surrogate-free
string inputs. Its eleven regression tests and complete CSV suite pass.
Worktree exploration improves load footprint, but primary combined
confirmation is neutral; no isolated primary CSV improvement is claimed.

Pickle320 defers the unused pure Python class graph into one real source
file, preserving original globals, reentry, reload, source/ZIP/bytecode
loading and caller overrides. Thirteen contracts and the complete pickle,
picklebuffer and pickletools suites pass (1,283 run,61 skipped). Primary
rigorous exploration improves load0.947864x in both runs; working is neutral.
The combined319/320 screen321 rejects small-base64 RSS1.014270x; pickle-only
isolation322 rejects compileall RSS1.019728x. Both requested all23 workloads
but stopped early on replicated regressions. Their verdict SHA256 values are
`ffd3ecd6cf473b414b9837418b89866b6ebb5a5ef505cba5673dffba56835f79`
and `c8a44d840c231fc2b0597fff49ffc387cd56c8372e28dab0ffbef5bbda8fee59`.
Neither change is adopted; no full suite, all71 confirmation or unchanged
retry follows these rejections. Memory goal counts remain48 passing/23
unresolved, with12 workload RSS regressions against pristine control.

### Incremental memory screens and native allocation attribution (2026-10-05)

No runtime change is adopted from these screens. Single-file pickle deferral
keeps the original definitions in a59,079-byte literal and supports source,
ZIP and bytecode-only loading; a fixture-first fix preserves the file's
optimization level during deferred compilation. Checked128-bit rational
pairs avoid temporary BigInt owners for bounded inputs while retaining the
original arbitrary-precision path. Their measured results remain neutral.

| Source | Verification | Target memory against accepted e702 |
| --- | --- | --- |
| Pickle325 `459dc68` | Incremental35s,58 verified Rust extensions;16 activation/optimization and9 wire/callback contracts pass; complete pickle/picklebuffer/pickletools1,283run/61skip | Standard load0.970683 neutral both; one rigorous confirmation load0.984 neutral both; working1.000 neutral both |
| Fractions326 `3a28d1c` | Incremental34s,58 verified;6 independent integer-oracle contracts pass accepted/candidate; complete fractions/numeric-tower/math148run/3skip | Load1.019059 [1.000000,1.037993] neutral both; working1.000 neutral both |

The rigorous325 verdict SHA is
`cc69165f2e2bfd9738ac96e11b9ffd53adfde57d943f7da10be96b6881c4d9b1`;
326's target verdict SHA is
`0d9fbdad342f74930f4f9b6ff68b6d130496ad38e9877af47cda022cd573db54`.
Neither proceeds to a clean build, broader qualification or an unchanged retry.
Both tuple writers in326 also correct stolen-reference failure cleanup;
that correction is preserved on the unadopted branch.

Native allocation diagnostic324 completed14 guarded children with matching
outputs and cleanup. Fixed live malloc differences, accepted minus control,
were pickle+9,360B,CSV+10,384B,threading+288B,typing+4,256B,
inspect−2,272B,ElementTree+7,472B andzstd+272B. These single-sample,
observer-perturbed endpoint totals do not identify a dominant owner or prove
physical-memory savings. Zstd's nonlinear4MiB reservation steps cannot be
interpreted as payload savings. Packet SHA:
`d6ea389cc7d4a3306f3f340b8ead3d102305c6d3627a6a8cc3e82f70ba19b6a7`.
The accepted source and stitched48passing/23unresolved module counts and
12workload RSS regressions remain unchanged.

### Packed pickle source and VM ownership evidence (2026-10-05)

Packed-source candidate328 reconstructs the exact original 59,079-byte
fallback from a 47,862-byte immutable string. Regression-first source
`0cd52f6` exposes a new callback through a caller's `pickle.str` override;
`c0d74ce` fixes it with an activation-local builtin lookup. ROOT reproduces
the pre-fix error and fixed behavior on the accepted interpreter, then
verifies all 18 installed candidate contracts and nine wire contracts.
The incremental primary build takes 34 seconds with 58 verified helpers;
complete pickle, picklebuffer and pickletools suites pass 1,283 tests with
61 skips. The two-run target screen takes 8.6 seconds and reads NEUTRAL:
load 0.986933x, interval [0.962,1.028], and working 1.000x, interval
[1.000,1.062]. Verdict `20261005T110748Z` SHA256 is
`d4396a3d94e08275aec04e28adc0d61ea9ed27eb22138be5fba6e778163b1c4b`.
The logical 11,217-byte saving establishes no physical memory win. No
rigorous retry, broader qualification or adoption follows.

Diagnostic329 completes one pinned native observer build and four verified
children, preserving kernel lifetimes, outputs, inputs and stage bytes.
VM query brackets change neither sampled physical footprint nor resident
size. Pickle's fixed physical footprint is 32,792 bytes above control;
Zstandard's is 1,523,688 bytes below control, associated with 98 fewer
best-effort resident pages in private `MALLOC_SMALL` objects. These counters
identify a page category, not an allocation or function owner. Object-wide
counters and observer-region growth prevent exclusive physical accounting;
this diagnostic cannot qualify a runtime change. Summary SHA256 is
`5a1083817ddea054d74e34d3ab69cd1324ef6cf6a6f50f588cc319e5af92aefe`.

The installed-toolchain sharing probe327 fails on the existing unwind/abort
panic-runtime mismatch; installed `rust-src` is absent. Source inquiry330
finds no duplicate C/Rust Zstandard context: the remaining ended-frame and
EOF contexts repeat previously closed lifetime candidates. Accepted runtime
and the 48 passing/23 unresolved module picture, with 12 workload RSS
regressions, remain unchanged. No CPU, timing or quiet-host gate applies.

### Bounded block source and shared-runtime probes (2026-10-05)

Candidate331 holds a 17,719-byte fallback payload and a small decoder; the
host model totals 20,668 retained bytes. Exact source reconstruction, eight
definition ASTs, optimization levels, callback isolation and malformed-block
bounds pass independent source review. The primary incremental build takes
33 seconds with 58 verified helpers; 20 contracts, nine wire contracts and
the complete pickle suites pass (1,283 run, 61 skipped). The standard target
screen is NEUTRAL. One higher-sample confirmation takes 14.3 seconds and has
pooled load 0.960775x, interval [0.948557,0.979783], but its independent runs
read better/neutral: the second interval reaches 0.993093x and does not clear
the existing 1% practical floor. Working peak remains neutral. Preserve the
actual NEUTRAL verdict `20261005T113323Z`; no broader qualification, adoption
or unchanged retry follows. Encoded source remains an unadopted private
representation change.

Probe332 compiles a Rust dylib carrier with static standard-library code and
the existing abort strategy, using only installed pinned artifacts. Both
ordinary consumer cdylib link modes fail dependency reconciliation and
panic-runtime compatibility. One separately bounded Rust-dylib consumer
also fails; no consumer artifact or memory saving exists. All probe groups
are reaped and accepted/control stage guards pass. This closes the tested
formats, not every hypothetical linkage strategy. Accepted runtime and
memory goal counts remain unchanged.

Candidate333 is the final bounded encoding variant: a 16,202-byte payload
with a 3,091-byte decoder graph in the host model. Independent source review,
20 fallback contracts, nine wire contracts and the complete pickle suites
pass; the incremental native build takes34 seconds with58 verified helpers.
Target verdict `20261005T115340Z`, SHA256
`1d4edb6ddd2880994bf235ef31f8315558f1357e9394be6116a594f50fcdd69e`,
is NEUTRAL: load0.974270x [0.945097,1.026124], working1.0x [1.0,1.03125],
neutral in both independent runs. Close this source-encoding family without
retry, adoption, broad screening or final qualification. The archived
exploration preserves its report and logs; accepted runtime and goal counts
remain unchanged.

### Sprint audit update (2026-10-05)

The live recheck found one running child among31 available child slots before
restarting independent verification, source-admission and route scouts. This
is coordinator underuse. The host snapshot has10 logical CPUs,64GiB RAM,
zero swap usage/traffic and343GiB free disk; it is lightly loaded. There are
226 registered worktrees, which add state-management cost but have not
exhausted disk space. No measured coordinator-idle total is available.

Actual recent costs: clean builds214–224s; compatible incremental builds
32.9–34.3s; target screens8.3–16s. Focused suites range from275ms to2.9s
in the cited recent examples. A saved complete suite took252s, followed by
a687s broad71/all23 gate; another complete suite took483s. Timers may
include lease waits. Build/test leases can overlap; measurements remain
exclusive. Thirty-one reasoning lanes do not supply31 local compiler cores.

The fastest qualifying order remains compatible incremental build, minimal
meaningful regression and nearest complete suite, replicated target plus
known affected memory guards, then all23 and broader qualification only for
survivors. Fixture-only edits do not require recompiling an unchanged stage.
Reuse valid calibration; do not perform CPU, timing or quietness gates during
memory work. Final clean builds, complete suites and replicated absolute
module/workload proof remain required. Preserve existing measured failures.

The64KiB load and256KiB working floors normalize denominators, not admission
sizes. Earlier size-only dismissals of compat-pickle and the cold ZIP
compressor were invalid; reopened compat-pickle analysis still finds no
removable persistent owner. Small concrete candidates remain eligible.
The principal technical uncertainty is physical attribution: fewer objects
or buffer bytes do not establish fewer resident pages, and a target win can
coexist with a replicated cross-route memory regression.

### Plistlib references280: larger local win, second workload rejection

Fixture-first donor280 `6aff775` adds a lossless narrow reference arena to
277/278: u16 entries promote to u32 before an out-of-range append. Previous
references, order and full u32 values are preserved. Modeled fixed-kernel
capacity drops about8KiB. Primary `adf7073` incremental build passes34.3s;
all14 independent byte/behavior cases pass on accepted and candidate stages,
including the actual65,536-index promotion boundary. Complete plistlib
passes71/0. Source review passes; five prepared Rust unit tests remain UNRUN.

The16s matched target screen reports working0.680x [0.556,0.814], improved
in both runs; load0.685x is better/neutral. The selected difflib RSS guard
is neutral in both runs. Verdict
`20261005T030058Z-perf-rust-vs-perf-pl277a/verdict.json`, SHA
`b557d6e76bad841581c624c1bac174fca23b95ed4b0ef1dcf74fb8749072434a`.
The all23 request REJECTS after150.2s: zlib streaming RSS1.016085x
[1.015826,1.016345], worse in both runs. Twelve entities complete; eleven
workloads and plistlib are incomplete. Verdict
`20261005T030236Z-perf-rust-vs-perf-pl277a/verdict.json`, SHA
`13f6e8a7f004093fb0a3449c2790444e9b9b8e4333df04d92dcb7a6246628251`.
Broad/full qualification and native Rust-unit execution are canceled.
No acceptance, absolute goal change or unchanged reroll follows.

The bounded current-artifact audit finds identical mapped segment extents
and fixup-page sets in accepted/candidate zlib, difflib, struct and core.
Zlib/difflib section bytes and offsets match exactly. Struct/core embedded
build paths shift some readonly sections64 bytes; normalized data/pointer
targets match and code differences are address immediates. This does not
establish RSS causality or an extra mapped-page owner. No allocator revival,
random build-name change or previously closed layout trial follows.

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
- **Sequencing.** The current memory-first objective above governs this run.
  Every module load/working goal and eligible absolute workload RSS goal must
  pass before CPU lanes start; debt entries remain unresolved. CPU, timing
  and quietness do not gate memory work. The user authorizes 31 subagents
  plus the root coordinator, with shared-host work scheduled through its leases.
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
is `.agents/skills/rust-cpython-perf/scripts/wait_quiet.py`. The current objective's
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
