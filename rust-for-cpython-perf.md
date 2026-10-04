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

The current-harness full snapshot compares unchanged verified incumbent
`7cf55a6` with pristine control `7351620`: [all-71/all-23 evidence](rust-cpython/results/perf-bench/20261003T152630Z-perf-upstream-vs-perf-rust/verdict.json),
followed by the [once-only rigorous classification](rust-cpython/results/perf-bench/20261003T160906Z-goals-perf-upstream-vs-perf-rust/verdict.json) of its ten
UNCLEAR rows. The merged result is **15 OVER, 8 UNCLEAR, 47 MET, 1 BEYOND**,
leaving **23 unresolved module goals**. The eight remaining UNCLEAR rows
exceed 1.01x on a memory metric and remain targets under the uncertainty rule;
no further unchanged classification draw is scheduled.

Both snapshots use current harness fingerprint
`f741f1781d58cc62d9b585b7894b2e63cdab30e4807a3a556cb56376ac5795ab`,
two independent runs, ten module rounds, matched home aliases and executable
paths, and matching module outputs. [Memory-only self-calibration](rust-cpython/results/perf-bench/20261003T144625Z-calibrate-perf-upstream/verdict.json)
passed before these measurements. CPU, timing and quietness are excluded.
The full verdict SHA256 is `ad7b7b514c71022e5ef3c851ebdd6348c3d8a50990ae30e4fe4954fdd11d6e5f`;
the follow-up SHA256 is `275bc3cb74121bbfd075c9412dc5bb8c84d8d0a7c7baf0b93f9d6794a566f256`.

The historical `886f55c1` harness snapshot remains preserved as
15 OVER / 5 UNCLEAR / 50 MET / 1 BEYOND. The current caller context differs;
these fresh ratios do not establish a source improvement, an offset, or
context invariance. Compiled paths and mapping/host state remain uncontrolled.
No candidate was accepted and baseline files remain unchanged.

The ten focused rows use `160906Z`: `_strptime`, collections, hashlib,
html.parser, ipaddress, logging, socket, sqlite3, ssl and xml.etree.ElementTree.
All other rows use `152630Z`. Ratios are saved pooled medians; statuses are
saved memory-only classifications.

| Route | Load footprint | Working peak | Memory status |
| --- | --- | --- | --- |
| `_strptime` | 1.019x UNCLEAR | 1.000x MET | UNCLEAR |
| `argparse` | 0.779x BEYOND | 1.000x MET | MET |
| `ast` | 0.728x BEYOND | 1.000x MET | MET |
| `asyncio` | 0.928x MET | 0.333x BEYOND | MET |
| `base64` | 1.084x OVER | 1.000x MET | OVER |
| `binascii` | 1.009x MET | 1.000x MET | MET |
| `bisect` | 1.000x MET | 1.000x MET | MET |
| `bz2` | 0.995x MET | 1.000x MET | MET |
| `codecs` | 0.991x MET | 1.000x MET | MET |
| `collections` | 1.325x UNCLEAR | 1.000x MET | UNCLEAR |
| `compression.zstd` | 0.798x BEYOND | 1.250x OVER | OVER |
| `concurrent.futures` | 0.476x BEYOND | 1.000x MET | MET |
| `configparser` | 0.587x BEYOND | 0.724x BEYOND | BEYOND |
| `contextlib` | 1.006x MET | 1.000x MET | MET |
| `csv` | 0.937x MET | 1.000x MET | MET |
| `dataclasses` | 0.904x MET | 0.562x BEYOND | MET |
| `datetime` | 1.750x OVER | 1.000x MET | OVER |
| `decimal` | 1.857x OVER | 1.000x MET | OVER |
| `difflib` | 0.145x BEYOND | 1.000x MET | MET |
| `email` | 0.932x MET | 0.872x BEYOND | MET |
| `fnmatch` | 0.376x BEYOND | 1.000x MET | MET |
| `fractions` | 1.006x MET | 1.000x MET | MET |
| `functools` | 1.000x MET | 1.000x MET | MET |
| `glob` | 0.331x BEYOND | 1.000x MET | MET |
| `gzip` | 0.758x BEYOND | 1.000x MET | MET |
| `hashlib` | 1.010x MET | 1.000x MET | MET |
| `heapq` | 1.000x MET | 1.000x MET | MET |
| `hmac` | 1.008x MET | 1.000x MET | MET |
| `html.parser` | 1.010x UNCLEAR | 1.000x MET | UNCLEAR |
| `http.client` | 0.992x MET | 1.000x MET | MET |
| `importlib.metadata` | 0.864x BEYOND | 1.000x MET | MET |
| `importlib.resources` | 0.838x BEYOND | 1.000x MET | MET |
| `inspect` | 1.043x OVER | 1.000x MET | OVER |
| `io` | 1.003x MET | 1.000x MET | MET |
| `ipaddress` | 1.034x UNCLEAR | 1.000x MET | UNCLEAR |
| `itertools` | 1.000x MET | 1.000x MET | MET |
| `json` | 0.802x BEYOND | 1.000x MET | MET |
| `logging` | 0.604x BEYOND | 1.018x UNCLEAR | UNCLEAR |
| `lzma` | 0.111x BEYOND | 1.000x MET | MET |
| `marshal` | 1.039x OVER | 1.000x MET | OVER |
| `multiprocessing` | 0.907x MET | 1.000x MET | MET |
| `os.path` | 1.000x MET | 1.000x MET | MET |
| `pathlib` | 0.599x BEYOND | 1.000x MET | MET |
| `pickle` | 1.059x OVER | 1.000x MET | OVER |
| `plistlib` | 0.247x BEYOND | 0.895x MET | MET |
| `random` | 0.800x MET | 1.000x MET | MET |
| `re` | 1.699x OVER | 1.000x MET | OVER |
| `shlex` | 0.549x BEYOND | 1.000x MET | MET |
| `shutil` | 0.823x BEYOND | 1.000x MET | MET |
| `socket` | 1.074x OVER | 1.000x MET | OVER |
| `sqlite3` | 1.030x UNCLEAR | 1.000x MET | UNCLEAR |
| `ssl` | 1.034x UNCLEAR | 1.000x MET | UNCLEAR |
| `statistics` | 0.582x BEYOND | 1.000x MET | MET |
| `struct` | 1.021x OVER | 1.000x MET | OVER |
| `subprocess` | 0.898x MET | 1.000x MET | MET |
| `tarfile` | 0.802x BEYOND | 1.000x MET | MET |
| `tempfile` | 0.319x BEYOND | 1.000x MET | MET |
| `textwrap` | 0.087x BEYOND | 1.000x MET | MET |
| `threading` | 1.600x OVER | 1.000x MET | OVER |
| `tokenize` | 1.046x OVER | 1.000x MET | OVER |
| `tomllib` | 0.096x BEYOND | 1.000x MET | MET |
| `typing` | 1.208x OVER | 1.000x MET | OVER |
| `unicodedata` | 1.000x MET | 1.000x MET | MET |
| `urllib.parse` | 0.376x BEYOND | 1.000x MET | MET |
| `urllib.request` | 0.917x MET | 1.000x MET | MET |
| `uuid` | 1.170x OVER | 1.000x MET | OVER |
| `warnings` | 1.000x MET | 1.000x MET | MET |
| `xml.etree.ElementTree` | 1.015x UNCLEAR | 1.188x UNCLEAR | UNCLEAR |
| `zipfile` | 0.292x BEYOND | 1.000x MET | MET |
| `zipimport` | 0.594x BEYOND | 1.000x MET | MET |
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

The current [full snapshot](rust-cpython/results/perf-bench/20261003T152630Z-perf-upstream-vs-perf-rust/verdict.json) reads **16 RSS regressions,
3 neutral, 4 improved** across all 23 workloads. This is fresh evidence for
unchanged incumbent source under `f741f178`, superseding the older table while
preserving its historical result. The memory-only decision is REJECT for
outstanding absolute debt, with no output mismatch or unstable metric.
Baseline files remain unchanged.

| Workload | Peak RSS | Memory verdict |
| --- | --- | --- |
| `catalog_json_export` | 0.986x | improved |
| `catalog_request_path` | 1.033x | regressed |
| `catalog_search_form` | 1.019x | regressed |
| `catalog_url_normalize` | 1.010x | neutral |
| `compileall_source` | 1.076x | regressed |
| `difflib_unified_mostly_equal` | 0.950x | improved |
| `difflib_unified_reordered` | 0.950x | improved |
| `django_asgi_request` | 1.050x | regressed |
| `django_orm_10k` | 1.049x | regressed |
| `django_template_realistic` | 1.050x | regressed |
| `django_wsgi_first_request` | 1.079x | regressed |
| `django_wsgi_request` | 1.049x | regressed |
| `gzip_extract_1m` | 0.985x | neutral |
| `import_django` | 1.051x | regressed |
| `multiprocess_pool` | 1.021x | regressed |
| `python_startup` | 1.020x | regressed |
| `rust_base64_large` | 1.019x | regressed |
| `rust_base64_small` | 1.005x | neutral |
| `serialization_roundtrip` | 1.039x | regressed |
| `zip_read_wheel` | 1.020x | regressed |
| `zipimport_cold` | 1.068x | regressed |
| `zlib_decode_1m` | 0.932x | improved |
| `zlib_stream_4k` | 1.019x | regressed |

Candidate acceptance compares against the qualified incumbent, retains
replicated memory guards and output checks, and requires complete suites.
Completion requires all 71 module load/peak goals MET or BEYOND and all 23
absolute workload RSS rows neutral or improved. Debt does not waive any goal.

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
