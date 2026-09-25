# Rust-for-CPython experiment lanes

## Optional URL unquote source patch (base `50737ef`)

The source integration lane uses
`/private/tmp/python-build-exp-url-unquote-source-patch-20260925a`, branch
`exp/url-unquote-source-patch-20260925a`. It owns only `rust-cpython/build.py`,
the patch manifest, a new `0004-rust-url-unquote.patch`, and
`experiments/url-unquote-source-patch-20260925.md`. It must encode the measured
proof behind an explicit opt-in build mode, retain the ordinary quote-only
source route, and verify actual file changes in a fresh pinned extraction.
No full build or performance run is concurrent. Budget: 90 kernel CPU
seconds and 1 GiB per-process RSS, including failed attempts. The
coordinator owns the later serial native build and installed comparison.

## URL unquote native proof (base `70b57b2`)

The reversible proof uses
`/private/tmp/python-build-exp-url-unquote-proof-20260925a`, branch
`exp/url-unquote-proof-20260925a`. It owns only a new
`experiments/url-unquote-proof/` source directory, its report, compact data,
and ignored work/logs. It copies the installed guarded quote source into
its own lane, builds a dependency-free Rust scan behind a CPython-owned C
wrapper, and overlays only an APFS-cloned candidate stage. The accepted
stage remains read-only. The search-form task is the speed target and
catalog normalization is a negative control. No other heavy lane runs
concurrently. Budget: 180 kernel-accounted command CPU seconds and 2 GiB
per-process RSS, including failed attempts; all benchmark outputs must
match complete digests and cache policy before any speed verdict.
The proof retained 129 uniquely logged attempts and a matched-compiler
quote-only control. Five search-form pairs gave a 0.564 median external-wall
ratio and 0.553 kernel-CPU ratio, with identical full digests and 1.3%
maximum control self-variation. The extension added 368 bytes against the
matched build. Total measured command CPU was 81.10 seconds, maximum
per-process RSS 102.04 MB, and swaps zero. It remains a prototype pending
reproducible source integration and semantic qualification; see
`url-unquote-proof-20260925.md`.

## URL unquote headroom (base `0b0ebc4`)

The diagnostic uses
`/private/tmp/python-build-exp-url-unquote-headroom-20260925a`, branch
`exp/url-unquote-headroom-20260925a`. It owns only
`experiments/url-unquote-headroom-20260925.md`, optional uniquely named
diagnostic code/data, and ignored raw logs. On the installed guarded quote
candidate, it profiles the complete catalog URL normalization and search
form tasks, counts eligible public `unquote` calls outside timing, and
checks all workload digests. No other heavy lane is active. Budget: 45
kernel-accounted CPU seconds, 512 MiB per-process RSS. The coordinator
will compare projected headroom with existing self-noise before authorizing
decoder source work.
The scout found 182 eligible escaped calls per 48-record search batch and
a 36.74% instrumented `unquote` ceiling, above its 1.78% timing self-noise.
Catalog normalization had only four eligible calls and a 1.59% ceiling below
its 1.83% noise. Six diagnostic commands used 2.65 kernel CPU seconds, at
most 32.51 MB RSS, and zero swaps. See
`url-unquote-headroom-20260925.md`.

## JSON headroom scout (base `8c9f92c`)

The next-target diagnostic uses
`/private/tmp/python-build-exp-json-headroom-20260925a`, branch
`exp/json-headroom-20260925a`. It owns only
`experiments/json-headroom-20260925.md`, compact data if needed, and ignored
raw logs. It profiles the existing complete 512-record catalog export on
the accepted fork stage, separating stdlib JSON calls from application
conversion and hashing. Its output is an Amdahl-style headroom decision,
not a speed verdict. It is the only active profiler or timing lane. Budget:
30 kernel-accounted CPU seconds and 512 MiB per-process RSS, with every
attempt and its output digest retained. The coordinator will integrate its
result before selecting any JSON implementation experiment.
The accepted-control profile repeated the prior pinned-stage diagnostic:
250 complete exports passed fixed digests, and sequential `dumps`/`loads`
calls occupied about 82% of instrumented export time. The C encoder and
scanner were active; an application encode/decode round trip caused many
calls. Three measured commands used 2.84 kernel CPU seconds, at most 31.67
MB RSS, and zero swaps. Defer a Rust JSON engine on this evidence; see
`json-headroom-20260925.md` and `catalog-json-profile-20260924.md`.
In parallel, the read-only URL unquote scout uses
`/private/tmp/python-build-exp-url-unquote-scout-20260925a`, branch
`exp/url-unquote-scout-20260925a` (base `a0e697e`), and owns only
`experiments/url-unquote-boundary-20260925.md`. It maps the pinned public
unquote behavior, existing catalog caller, and a guarded native boundary.
It runs no profiler, benchmark, or build while JSON timing is active. The
coordinator will reconcile both scouts before choosing a source-patch lane.
The URL scout found an exact-ASCII-string/default-decoder guard and warned
that the older `unquote` profile predates the installed quote patch. It ran
no build, benchmark, or substantial command; see
`url-unquote-boundary-20260925.md`.

## Mixed-input follow-up (base `0da49c3`)

The one-shot zlib mixed-BLOB comparison uses
`/private/tmp/python-build-exp-zlib-oneshot-mixedblobs-20260925a`, branch
`exp/zlib-oneshot-mixedblobs-20260925a`. It owns only a new workload,
report, compact raw data, and ignored scratch. Its question is whether the
small-BLOB gain survives a fixture spanning highly compressible, modestly
compressible, and nearly incompressible 1–4 KiB values. It is the only active
timing lane, with a 120-second kernel CPU and 1 GiB per-process RSS cap.
The coordinator will review its input distribution and self-noise before
deciding whether the one-shot route earns further size and memory work.
The mixed fixture had 64 rows in each of four compressibility categories.
Seven candidate pairs regressed complete-process wall/CPU by 8.41%/9.00%,
outside seven control/control pairs' −1.12% to +0.58% wall range. All 39
attempts matched output identity. The controller used 37.10 kernel CPU
seconds, at most 35.98 MB per-process RSS, and zero swaps. See
`zlib-oneshot-mixedblobs-20260925.md`. This blocks general one-shot
promotion regardless of a possible size reduction.
The static size scout in
`/private/tmp/python-build-exp-zlib-size-scout-20260925a`, branch
`exp/zlib-size-scout-20260925a` (base `9ca3c68`), owned only
`experiments/zlib-oneshot-size-feasibility-20260925.md`. It found 63
exported prefixed Rust entry points and 713,724 bytes of `__text` in the
one-shot extension. It ran no build or substantial command, and deferred a
private-export/dead-strip build while the mixed-input regression stands.

## Current cycle (bases `1b0507a` and `c2baee4`)

The one-shot zlib small-BLOB application comparison uses
`/private/tmp/python-build-exp-zlib-oneshot-smallblobs-20260925a`, branch
`exp/zlib-oneshot-smallblobs-20260925a` (base `1b0507a`). It owns only its
new workload, report, compact raw data, and ignored lane scratch. Its question
is whether the optional public `zlib.decompress` Rust route helps a complete
SQLite compressed-BLOB task with many 1–4 KiB values. It uses the already
built fork control and one-shot candidate, with seven self pairs and seven
counterbalanced cross pairs if host conditions permit. It is the only active
timing lane. Budget: 180 kernel-accounted controller CPU seconds and 1 GiB
maximum reported RSS; every attempt retains a unique resource record.

The static `tomllib` boundary scout uses
`/private/tmp/python-build-exp-tomllib-boundary-20260925a`, branch
`exp/tomllib-boundary-20260925a` (base `1b0507a`). It owns only
`experiments/tomllib-boundary-20260925.md`; it examines the pinned parser,
public callers, semantic limits, and a real metadata workload before any
prototype. It may not compile or benchmark while the zlib lane is timing.

The static macOS memory-method scout uses
`/private/tmp/python-build-exp-mac-memory-scout-20260925a`, branch
`exp/mac-memory-scout-20260925a` (base `c2baee4`). It owns only
`experiments/mac-memory-next-method-20260925.md`; it examines a bounded
route to unique or proportional child-process memory evidence after the
earlier region traversal failed. It may not compile or benchmark while the
zlib lane is timing. Both static scouts have no substantial-command budget;
the coordinator must authorize a separately measured probe before running
one. Integration order is the zlib result, then the nonoverlapping scouts,
followed by updates to the shared objective and ranked map.

The zlib lane completed seven self and seven candidate pairs. Its synthetic,
highly compressible 1–4 KiB SQLite BLOB task improved complete-process
wall/CPU by 10.83%/10.89%, beyond self-noise; memory remained inconclusive.
All 39 successful child attempts had matching output digests. The two
controllers, including a retained failed calibration guard, used 35.10
kernel CPU seconds, at most 35.1 MB per-process RSS, and zero swaps. See
`zlib-oneshot-smallblobs-20260925.md`.

The `tomllib` scout found a plausible single-call boundary for exact `str`
and default `float`, but the available metadata corpus is too small to
justify a parser. It ran no substantial commands; see
`tomllib-boundary-20260925.md`. The memory scout rejected Mach per-page
object reference counts as USS/PSS evidence and specified a diagnostic-only
submap probe. It also ran no substantial commands; see
`mac-memory-next-method-20260925.md`.

## Fifteenth cycle (base `53364e2`)

The full URL source-patch qualification uses
`/private/tmp/python-build-exp-url-full-build-20260924o`, branch
`exp/rust-cpython-url-full-build-20260924o`. It owns only new
`experiments/url-quote-full-build-20260924.md` and uniquely named compact
evidence. It gives the candidate its own verified input cache, source/build,
Cargo, stage, logs, and results under this worktree. It must execute the
authored patch in a fresh pinned Rust fork extraction, configure and complete
the usual macOS PGO/ThinLTO build with nine PGO workers, inspect the installed
module and patch identity, then run focused unchanged URL tests, differential
public cases, a complete catalog digest, and a subinterpreter import/call.
No other lane may compile or benchmark concurrently. Budget: 3,000 actual
command CPU seconds, 16 GiB maximum reported RSS. The coordinator will
review before any timed full-build comparison or promotion.

## Fourteenth cycle (base `ddb5cf7`)

The URL source-patch implementation uses
`/private/tmp/python-build-exp-url-source-patch-20260924n`, branch
`exp/rust-cpython-url-source-patch-20260924n`. It owns only a new authored
patch under `rust-cpython/patches/`, that lane's manifest entry, and a new
`experiments/url-quote-source-patch-20260924.md`. Its question is whether the
cache-matched lean overlay can be rebuilt from the pinned Rust fork source
without a new dependency or `Cargo.lock` change. It will prepare the patch,
verify digest/schema/context against fresh pinned source, inspect generated
configure/build rules, and run focused checks. No PGO/full interpreter build
or paired benchmark while the host has unrelated heavy work; the coordinator
will review before scheduling that serial qualification. Budget: 120 actual
command CPU seconds, 2 GiB maximum reported RSS, generated trees inside its
own worktree. The no-Rust control and production 3.14.6 build stay intact.

## Thirteenth cycle (base `6d8a8c0`)

The URL memory-attribution diagnostic uses
`/private/tmp/python-build-exp-url-memory-attribution-20260924l`, branch
`exp/rust-cpython-url-memory-attribution-20260924l`, and owns only a new
`experiments/url-quote-memory-attribution-20260924.md`, a diagnostic script,
and uniquely named compact data. It compares cloned no-Rust interpreters
with original parse/no extension, original parse plus imported lean extension,
and the guarded lean parse plus extension. The question is whether the
roughly 2.9 MB paired RSS rise starts at extension import or during quotation.
It may run serial paired external memory passes and fixed-digest checks,
but no compilation or authoritative timing. Budget: 50 command CPU seconds,
1 GiB maximum reported RSS. All generated clones and raw samples stay in its
own worktree; the coordinator owns the next implementation decision.
Five 24-process passes isolated the old RSS signal to parser cache state.
The candidate inherited an invalid checked-hash `parse.py` cache in both
earlier overlays, while control caches were valid and benchmark bytecode
writes were disabled. Stale-cache catalog RSS deltas were +2.78 and +3.03
MB; with all parser caches removed they were +65,536 and +114,688 bytes;
with valid caches on all copies the delta was −65,536 bytes. Extension import
alone stayed near control. All 120 processes passed exact digest and import
checks. Five measured controllers used 45.06 user-plus-system CPU seconds,
31,424,512 bytes maximum reported RSS, and zero swaps. The earlier memory
rejections are withdrawn pending a cache-matched standard comparison; see
`url-quote-memory-attribution-20260924.md`.

The fair lean URL comparison uses
`/private/tmp/python-build-exp-url-fair-compare-20260924m`, branch
`exp/rust-cpython-url-fair-compare-20260924m` (base `30efa06`). It owns a
new `experiments/url-quote-fair-comparison-20260924.md` and uniquely named
compact data only. It clones the last accepted Rust fork stage into control
and candidate, installs the hash-verified lean overlay only in the
candidate, and explicitly regenerates and verifies valid checked-hash parser
bytecode in both clones outside measurement. Then it runs serial control and
candidate self-calibration and a complete standard paired catalog comparison
if timing noise permits. No concurrent build or benchmark lane. Budget:
120 actual command CPU seconds and 1 GiB maximum reported RSS.
With both parser pycs regenerated and verified as checked-hash caches, the
quiet control and candidate self-calibrations had 2.05% and 1.90% timing
noise. Five complete-task pairs gave a 0.81324 median external wall ratio
(−18.7%) and 18.6% lower root CPU. Three separately sampled memory pairs
gave +131,072 bytes median peak RSS, within the 327,927-byte control and
169,160-byte candidate self-noise allowances. All digests matched. The
discarded first control run overlapped unrelated `rustc` and had 28.5% noise.
Seven measured controller commands used 52.88 user-plus-system CPU seconds,
28,082,176 bytes maximum command RSS, and zero swaps. Keep the lean overlay
as a source-patch candidate only; upstream USS/PSS and allocation gates are
still open. See `url-quote-fair-comparison-20260924.md`.

While unrelated host compilation holds timing, the source-patch feasibility
audit uses `/private/tmp/python-build-exp-url-patch-design-20260924m`, branch
`exp/rust-cpython-url-patch-design-20260924m` (base `578c4db`). It owns only
`experiments/url-quote-patch-design-20260924.md`. It identifies an exact
no-new-dependency integration path for the lean kernel in the pinned Rust
fork, including Cargo/staticlib, CPython-owned module registration, parser
patch, cache preparation, and build checks. It runs no compilation or
benchmark and makes no source changes. Budget: 20 command CPU seconds,
512 MiB maximum RSS; the coordinator owns any later implementation.
The audit found that the existing `cpython-rust-staticlib` can hold a kernel
without changing `Cargo.lock`, but the shared C extension will not link that
archive automatically. It recommends a dedicated no-std archive rule, a
CPython-owned stateless C wrapper, gated setup/configure entries, and an
authored source patch after the fair comparison clears both gates. It also
separates the build-only pycache prefix from the benchmark environment. No
build, test, or benchmark ran; see `url-quote-patch-design-20260924.md`.

## Twelfth cycle (base `5c393f5`)

The macOS 3.16 application-input audit uses
`/private/tmp/python-build-exp-mac-input-audit-20260924j`, branch
`exp/rust-cpython-mac-input-audit-20260924j` (base `3ff3b10`), and owns only
`experiments/mac-input-audit-20260924.md`. It traces existing benchmark
fixtures, wheel locks, and the cold Django request gap, then proposes exact
code/manifest changes needed for compatible byte-pinned inputs. It does not
fetch packages, add dependencies, edit benchmarks, or run substantial
compilation/timing while the lean URL proof is active. Budget: 20 command CPU
seconds, 512 MiB maximum RSS. The coordinator owns any decision or edits.
The audit found that the single wheel lock is Linux x86_64 CPython 3.14,
including native musllinux wheels, while native macOS realworld runs still
select it. The current Django request interval starts after setup, handler
construction, and a warm-up request. Its report proposes a separate
target-validated lock, per-workload input groups, and a fresh-process first
request using an identical preseeded fixture. No packages were fetched,
tests run, or dependency changes made; see `mac-input-audit-20260924.md`.

The lean URL quotation proof uses
`/private/tmp/python-build-exp-url-lean-20260924j`, branch
`exp/rust-cpython-url-lean-20260924j`, and owns only a new
`experiments/url-quote-lean-proof/` plus its report. It tests a no-std Rust
kernel and direct CPython Unicode allocation/fill to remove the former
temporary bytes output and reduce resident extension cost. The pinned stage,
build configuration, and existing rejected proof stay intact. It may run
focused differential and CPython URL tests, but no paired performance
benchmark; the coordinator will schedule that separately on a quiet host.
Budget: 300 command CPU seconds and 2 GiB maximum reported RSS. Generated
outputs remain inside this worktree. The result must report size, dynamic
dependencies, actual command CPU/RSS/swap, semantic evidence, and a
keep/reject/inconclusive recommendation.
The proof passed 2,177 differential public cases, 182 unchanged CPython URL
tests (7 skipped), and one complete catalog digest check. Its corrected
no-std two-pass kernel writes directly into an exactly sized CPython Unicode
object. The unstripped extension is 50,712 bytes, down from 1,473,544 bytes,
and links only to libSystem. Final build and semantic-check commands used
1.27 actual user-plus-system CPU seconds in total, at most 101,482,496 bytes
reported RSS, and zero swaps. This is inconclusive pending a paired
full-workload memory and speed comparison; see
`url-quote-lean-proof-20260924.md`.

The lean URL comparison uses
`/private/tmp/python-build-exp-url-lean-compare-20260924k`, branch
`exp/rust-cpython-url-lean-compare-20260924k` (base `5cda922`). It owns only
`experiments/url-quote-lean-comparison-20260924.md` and uniquely named
compact raw data. It clones the same no-Rust stage into control and candidate
inside its worktree, installs only the hash-verified lean overlay into the
candidate, calibrates quiet control/control and candidate/candidate noise,
and runs serial complete catalog pairs if calibration permits. No other lane
will compile or benchmark concurrently. Budget: 120 command CPU seconds and
1 GiB maximum reported RSS. The coordinator decides the verdict.
Control self-noise was 1.35%; two candidate self-calibrations had 5.81% and
6.19% timing noise, so no matched speed run occurred. A separate five-pair
memory-only diagnostic then found a 2,932,736-byte median peak-RSS rise and
2,899,992-byte sampled footprint rise, versus at most 437,237 bytes of
local RSS self-noise. All ten digest checks passed. The lane used 44.10
measured command CPU seconds total, at most 45,809,664 bytes command RSS,
and zero swaps. Reject the lean overlay on memory; speed is inconclusive.
The earlier quote comparison used the Rust fork stage, while this lane used
the no-Rust stage, so their absolute memory changes are context rather than
a matched before/after result. See `url-quote-lean-comparison-20260924.md`.

## Eleventh cycle (base `c12e3c6`)

An unrelated `cargo test` in `/Users/josh/d/laputa-systems/xsh` spawned Rust
compilers during the URL quote lane's first self-comparison, so that run is
diagnostic only. The URL lane will recalibrate after that external job ends;
it may not publish an overlapping comparison. Its cloned control and proof
stage remain isolated under its worktree.

## Tenth cycle (base `43e65fe`)

At scheduling, one-minute host load was 2.12 on ten logical CPUs, with
348.38 MiB allocated swap, OrbStack Helper near one CPU, and no compiler or
other benchmark. The URL quote comparison lane uses
`/private/tmp/python-build-exp-url-compare-20260924i`, branch
`exp/rust-cpython-url-compare-20260924i`. It owns only a new
`url-quote-comparison-20260924.md` and compact raw evidence. It clones the
existing Rust fork stage using copy-on-write files inside its worktree, installs
the proof overlay only into that clone, verifies imports and hashes, then
runs control self-comparison followed by serial standard paired catalog
workloads if self-noise permits. Budget: 120 command CPU seconds, 1 GiB
reported RSS. No other lane may compile or benchmark concurrently. The
coordinator will decide the verdict and preserve the unmodified control.
The first two self comparisons were diagnostic because one overlapped an
unrelated Rust compiler and the next had 8.86% wall noise. A later clean
self-comparison had 2.97% noise. The serial full catalog comparison then
showed a 0.8073 candidate/control paired wall ratio (−19.3%) and 17.4%
less root user-plus-system CPU per batch, but median peak RSS rose 3,194,880
bytes (+12.4%) above a 947,346-byte comparison allowance; sampled physical
footprint rose 3,096,576 bytes. All 1,500-batch output digests matched, and
the clone/source hashes stayed intact. Four controller commands used 56.10
actual CPU seconds total, at most 47,005,696 bytes reported RSS, and zero
swaps. The 1.47 MB Rust extension and memory increase reject this overlay
under the current resource rule. See `url-quote-comparison-20260924.md` and
its compact raw data. The executable hash resolves to the Rust fork stage,
not the no-Rust stage originally named in the lane brief; both paired sides
still used identical bytes. A smaller-resident proof is a distinct experiment.

## Ninth cycle (base `b24b689`)

The macOS region probe uses
`/private/tmp/python-build-exp-mac-region-20260924h`, branch
`exp/rust-cpython-mac-region-20260924h`, and owns a new diagnostic script,
report, and uniquely named compact data only. It tests the installed SDK's
`PROC_PIDREGIONINFO` counters against controlled child memory states without
adding a benchmark field or claiming exact USS/PSS. Budget: 30 command CPU
seconds, 512 MiB observer RSS. Its timed diagnostic has priority over any
compiler or benchmark on this host.
It rejected a mapped-private benchmark field from this interface. Touching
32 MiB of anonymous pages raised RSS and raw private-page counts by 32 MiB,
but each address walk encountered 18 submaps and ended with zero/EINVAL;
the public `proc_pidinfo` address argument did not permit a sound recursive
traversal. Raw totals were unqualified, so COW/alias trials stopped. The
final command used 0.06 user plus 0.04 system CPU seconds, 20,004,864 bytes
observer peak RSS, 52,953,088 bytes command/child maximum RSS, and zero
swaps. See `mac-region-probe-20260924.md`. USS/PSS remain unavailable.

The URL quote proof uses `/private/tmp/python-build-exp-url-proof-20260924h`,
branch `exp/rust-cpython-url-proof-20260924h`, and owns only the new
`experiments/url-quote-proof/` and its report. It prototypes a guarded
domain-specific Rust quote kernel without changing the pinned build or adding
a dependency. It may prepare source and focused semantic checks, but holds
substantial compilation until the region probe's timed diagnostic finishes;
no paired benchmark runs without a separate coordinator decision. Budget:
300 command CPU seconds and 2 GiB maximum reported RSS. All generated files
remain inside its isolated worktree.
The proof compiled with pinned nightly Rust and locked clang, without a new
dependency or source pin. It passed 2,177 differential public quotation
cases, 182 unchanged `test_urlparse`/`test_urllib` tests (7 skipped), and a
complete catalog batch with its fixed digest. The final build used 0.21 user
plus 0.14 system CPU seconds, 114,278,400 bytes maximum reported RSS, and
zero swaps. Its unstripped arm64 extension is 1,473,544 bytes and depends
dynamically only on libSystem. See `url-quote-proof-20260924.md`. This is an
isolated overlay proof; there is no paired performance or memory verdict yet.

## Eighth cycle (base `1a426e6`)

At scheduling, the earlier compiler had exited and one-minute load fell to
2.40 on ten logical CPUs, with 348.38 MiB allocated swap. The catalog URL
sizing lane uses `/private/tmp/python-build-exp-url-sizing-20260924h`, branch
`exp/rust-cpython-url-sizing-20260924h`. It owns only the registered
`catalog_url_normalize` loop count in `benchmarks/workloads/registry.py`, a
new `catalog-url-quiet-baseline-20260924.md`, and compact uniquely named raw
evidence. It first sizes the existing fixed batch to a roughly 0.5–1.0
second internal interval, then self-compares serially. A matched upstream
comparison is conditional on a <=3% self timing allowance and quiet host.
Budget: 120 command CPU seconds and 1 GiB reported RSS. No other lane will
run a benchmark or compiler concurrently.
The registered count is now 1,500 batches, with a measured 0.64081-second
internal loop on the pinned no-Rust fork. Its corrected standard
self-comparison returned a 2.61% wall noise allowance, 1.00368 paired median
ratio, and a 376,832-byte root RSS median difference inside a 765,164-byte
self allowance. With that gate met, the lane compared matched vanilla
upstream serially against the no-Rust fork: paired wall median 0.99995,
root CPU +0.39% per batch on the fork, and root RSS −196,608 bytes, just
inside the diagnostic allowance. All fixed digests matched. Source ancestry
and independent PGO profiles limit attribution; macOS unique memory and
allocations remain unavailable. Sizing and completed comparisons used about
41.8 controller command CPU seconds in total, at most 45,416,448 bytes
reported RSS, and no swaps. The report and compact observations are in
`catalog-url-quiet-baseline-20260924.md` and its `data/` JSON. No Rust URL
implementation was built or measured.

## Seventh cycle (base `57a7a54`)

An unrelated Rust compiler was observed near 590% process CPU at the start
of this cycle, and host load remained about 7–8 on ten logical CPUs. No
comparative timing run is scheduled under that contention.

| Lane | Worktree and branch | Owned paths | Question | Budget and status |
| --- | --- | --- | --- | --- |
| Catalog URL headroom | `/private/tmp/python-build-exp-url-headroom-20260924g`, `exp/rust-cpython-url-headroom-20260924g` | New `experiments/catalog-url-headroom-20260924.md` and narrow probe | Does `quote_from_bytes` materially contribute to the complete registered batch, and what share reaches an exact-bytes guard? | Integrated; 0.31 CPU seconds, 26.0 MB RSS maximum across two commands |
| macOS private-memory feasibility | `/private/tmp/python-build-exp-mac-unique-20260924g`, `exp/rust-cpython-mac-unique-20260924g` | New `experiments/mac-unique-memory-feasibility-20260924.md` only | Which host API can give an honest unique/private or proportional memory gate, and which allocation metric is feasible? | Integrated; read-only source research, no measured command |

The coordinator owns target selection, integration, and updates to the shared
objective. These agents may not edit each other's files or run a build or
long comparative benchmark.

The complete registered catalog batch made 15,000 `quote_from_bytes` calls
over 100 iterations. In an instrumented profile, it used 0.03063 of 0.16536
seconds cumulatively (18.5%, an optimistic upper bound); 9,600 calls passed
the proposed guard after existing fast exits, and 9,200 of those inputs were
at most 17 bytes. The diagnostic is not a speed result. See
`catalog-url-headroom-20260924.md` and its probe for method and limits.

The macOS feasibility report found private-resident page counters in the
installed SDK's `PROC_PIDREGIONINFO`, but no evidence that their sum is exact
USS or PSS. Its next step is a bounded region-accounting probe against a
controlled child, labeled as a diagnostic until submaps, aliasing, access,
and overhead are checked. Physical footprint remains a separate ledger.
The allocation pass also needs a CPython 3.16 compatibility decision before
using Memray. See `mac-unique-memory-feasibility-20260924.md`.

## Sixth cycle (base `2aec7d7`)

The catalog URL baseline lane uses
`/private/tmp/python-build-exp-url-baseline-20260924f`, branch
`exp/rust-cpython-url-baseline-20260924f`, and owns only a new
`catalog-url-baseline-20260924.md` and uniquely named compact raw evidence.
It reads the already built no-Rust fork and matched upstream control without
mutating either. At scheduling, host load averages were 5.58/8.04/8.51 on
ten logical CPUs, with stable 356.38 MiB allocated swap and no active
compiler. The lane first calibrates the new registered workload against the
no-Rust control itself. It may compare matched upstream serially only if
self-noise and host conditions permit; otherwise it records the diagnostic
and stops. Budget: 120 command CPU seconds and 1 GiB reported RSS. Generated
benchmark outputs stay in the lane worktree.
The self-comparison completed with five timing pairs and three memory pairs
over 100 complete catalog batches per process; all input/output digests
matched. Paired median wall ratio was 1.0096, inside a 6.62% timing noise
allowance. Root CPU per batch differed by +0.87%, and median peak RSS by
+1.42%, inside an 801,600-byte self-noise allowance. The controller command
used 1.94 user plus 0.83 system CPU seconds, 45,301,760 bytes maximum
reported RSS, and zero swaps. Host load rose from 4.75 to 5.89 during the
run, so the lane stopped before upstream-versus-fork comparison. See
`catalog-url-baseline-20260924.md` and its compact raw evidence. This is a
calibration with an incomplete macOS memory verdict, not a speed result.

## Fifth cycle (base `097693b`)

The next-target scout uses
`/private/tmp/python-build-exp-next-target-20260924e`, branch
`exp/rust-cpython-next-target-20260924e`, and owns only a new
`next-target-after-zlib-20260924.md`. It compares application call paths and
narrow profiles for `ipaddress`, `urllib.parse`, `json`, or a better supported
stdlib hypothesis after the rejected `difflib` row reuse and deferred
`tomllib` parser. It may not build or run a long benchmark on this busy host.
Budget: 30 process CPU seconds and 512 MB maximum RSS. The coordinator
retains target choice and any follow-on implementation assignment.
The scout selected catalog URL normalization as the next bounded public
workload hypothesis. A short pinned-fork `cProfile` run over 2,000
normalize/key pairs located calls to `urllib.parse.quote_from_bytes`, but did
not establish a speed opportunity. Its command used 0.13 user plus 0.02
system CPU seconds and 26,574,848 bytes maximum RSS. The report
`next-target-after-zlib-20260924.md` defers a native kernel until the full
catalog task shows useful headroom.

The follow-on workload lane uses
`/private/tmp/python-build-exp-url-workload-20260924e`, branch
`exp/rust-cpython-url-workload-20260924e`, based on `f1c7626`. It owns only
`benchmarks/workloads/registry.py`, a new catalog URL workload and focused
test, and `catalog-url-workload-20260924.md`. It may validate registration
and content with a bounded smoke but may not run a long comparison or build.
Budget: 60 process CPU seconds and 512 MB maximum RSS. The lane integrated
as `5f3d14b`. Each complete operation processes 48 URLs and 48 stable keys
through the checked-in catalog functions, with fixed length-framed input and
output digests. Two focused tests passed, and a 100-operation smoke returned
the fixed digest. The test command used 0.05 user plus 0.02 system CPU
seconds and 26,034,176 bytes maximum RSS; the smoke used 0.08 user plus 0.01
system seconds and 22,429,696 bytes maximum RSS, with zero swaps. No
comparative benchmark or Rust build ran. The existing catalog fixture strips
IPv6 hostname brackets; the workload pins its current output without
claiming URL validity. See `catalog-url-workload-20260924.md` for inputs and
limits. A quiet-host control self-comparison is the next measurement gate.

## Fourth cycle (base `e1a5eb7`)

The host remained busy at load averages 8.74/8.40/9.04 on ten logical CPUs,
with OrbStack Helper near one CPU and 7.5 GB RSS. Its allocated swap remained
356.38 MiB. No comparative timing run is scheduled during this cycle.

| Lane | Worktree and branch | Owned paths | Question | Budget and status |
| --- | --- | --- | --- | --- |
| Child CPU accounting | `/private/tmp/python-build-exp-child-cpu-20260924d`, `exp/rust-cpython-child-cpu-20260924d` | `benchmarks/harness/process.py`, `benchmarks/harness/runner.py`, `benchmarks/workloads/zlib.py`, relevant focused tests, new `experiments/child-cpu-accounting-20260924.md` | Can the cold ZIP import report direct reaped child CPU without implying arbitrary descendant coverage? | Integrated; no long benchmark/build |
| ZIP memory diagnosis | `/private/tmp/python-build-exp-zlib-memory-20260924d`, `exp/rust-cpython-zlib-memory-20260924d` | New `experiments/zlib-memory-followup-20260924.md` only | What does the raw paired ZIP read RSS/footprint evidence support, and which quiet-host measurement should follow? | Integrated; no benchmark/build |

The coordinator owns this ledger and the integration order. The agents have
distinct source and report paths, may not delegate, and keep any scratch in
their own worktrees.

The ZIP memory diagnosis found paired root-kernel peak RSS differences of
+3.801, −0.131, and +3.129 MB. The 3.129 MB median gap is below the 4.028 MB
ZIP repeatability allowance. Sampled footprint gaps were +5.177, +9.749,
and +0.754 MB; a missing final sample in the third candidate shows this is
not an exact lifetime peak. The root kernel footprint median gap was 2.916
MB. `zlib-memory-followup-20260924.md` records the raw-data interpretation
and a quiet-host ZIP self-comparison plan. Four small analysis commands each
used about 0.03 CPU seconds and below 19 MB reported RSS. This is an
inconclusive memory signal, not a parity pass or established regression.

The child CPU lane corrected `wait4` labels to root-only and added the
`zipimport_cold` workload's separate `RUSAGE_CHILDREN` delta for directly
reaped interpreter children. The runner validates and combines the ledgers
while retaining both raw components. A two-operation smoke observed 0.077071
user plus 0.039596 system seconds in the root and 0.03858 user plus 0.019014
system seconds in its children. Its 47 focused tests passed with 10
platform-specific skips; that command used 0.51 user plus 0.28 system CPU
seconds and 48,398,336 bytes maximum reported RSS. The direct smoke command
used 0.12 user plus 0.08 system CPU seconds and 23,986,176 bytes maximum RSS.
`child-cpu-accounting-20260924.md` records scope and limits. The earlier cold
ZIP CPU figure is still root-only and must be remeasured under this contract.

## Third cycle (base `87b0eec`)

The optional zlib build recipe was integrated through `87b0eec` after a
successful whole build of the first link recipe and a bounded incremental
correction that leaves `binascii` on platform zlib. The revised recipe still
needs its own clean full PGO build. Its isolated worktree is retained, and the
coordinator scheduled that build after a separate Cargo job stopped spawning
compilers. The full-build budget was 1,200 kernel user-plus-system CPU
seconds and 3 GiB maximum reported RSS. No published timing run overlapped it.
The revised clean build succeeded: 736.23 user plus 120.87 system CPU seconds,
1,739,423,744 bytes maximum reported RSS, no command swaps. The installed
`zlib` module uses the pinned Rust backend, while `binascii` loads platform
`libz.1.dylib`; the two unstripped extensions total 1,767,256 bytes, which
is 1,591,440 bytes above the existing platform control. Exact hashes and
link evidence are in `zlib-build-candidate.md`. This proves the build and
installed identity, not runtime speed or memory parity.

The macOS sampler overhead lane owns only
`benchmarks/harness/process.py`, `benchmarks/harness/macos_resource.py`, and a
new `rust-cpython/experiments/mac-sampler-overhead-20260924.md` in
`/private/tmp/python-build-exp-mac-sampler-20260924c`, branch
`exp/rust-cpython-mac-sampler-20260924c`. It may run one bounded sleeping-child
diagnostic but no benchmark. Its budget is 150 process CPU seconds and 1 GiB
peak RSS. It must preserve Linux behavior and report physical footprint as a
sampled charged-memory diagnostic, never USS/PSS or an exact tree peak.
Its filtered `libproc` implementation was integrated as `8f98278`. In one
uncontrolled before/after 0.5-second child diagnostic, the old `ps` path
gave five valid footprint samples and consumed 0.16 user plus 0.48 system
command CPU seconds; the new path gave 12 samples and consumed 0.10 user plus
0.05 system seconds. Host activity and possible overlap with PGO limit the
comparison. See `mac-sampler-overhead-20260924.md` for the SDK layout,
identity checks, and residual races. No behavioral suite ran for this change.

The serial zlib qualification lane used
`/private/tmp/python-build-exp-zlib-qual-20260924c`, branch
`exp/rust-cpython-zlib-qual-20260924c`, based on `484cbe4`. It owned a new
`rust-cpython/experiments/zlib-full-candidate-20260924.md` and uniquely named
raw JSON under `rust-cpython/experiments/data/`. It read the two built
interpreters but kept benchmark outputs in its own worktree. It calibrated
the platform control against itself, then compared public zlib, gzip, ZIP,
and import workloads serially. The six completed commands used 16.83
controller process CPU seconds; the largest reported RSS was 48.61 MB, with
zero command swaps. All five workload content checks passed. Paired operation
wall ratios were 0.492 for one-shot zlib, 0.644 for streaming zlib, 0.573 for
gzip extraction, 0.909 for ZIP read, and 1.088 for cold ZIP import against a
13.79% self-comparison wall noise allowance. ZIP read's median peak RSS rose
3.13 MB and sampled physical footprint rose 5.18 MB. Memory parity remains
incomplete because unique/proportional and allocation metrics are unavailable;
the cold import root CPU measure also excludes its child interpreter. The
optional candidate stays experimental. The report and raw observations are in
`zlib-full-candidate-20260924.md` and `data/zlib-full-evidence-20260924.json`.
No separate CPython/Cargo suite ran in this lane.

## Second cycle (base `ffb6205`)

The coordinator committed the first cycle as `ffb6205` and opened four
separate worktrees. Current host load was 5.43/5.49/5.23; OrbStack Helper
occupied about one CPU and 6.5 GiB RSS. No published timing run is scheduled
under this load. Each lane has a limit of 300 process CPU seconds and 2 GiB
peak RSS before asking the coordinator to schedule more. Substantial commands
must report kernel user/system CPU time and memory; elapsed time alone is not
resource evidence.

| Lane | Worktree and branch | Owned paths | Question | Status |
| --- | --- | --- | --- | --- |
| Reproducible zlib candidate build | `/private/tmp/python-build-exp-zlib-build-20260924b`, `exp/rust-cpython-zlib-build-20260924b` | `rust-cpython/build.py`, `rust-cpython/patches/`, new `experiments/zlib-build-candidate.md` | Can the existing pinned zlib-rs backend be an optional full candidate-build input without changing the no-Rust control? | Active; one isolated full build scheduled after code review |
| macOS footprint | `/private/tmp/python-build-exp-mac-footprint-20260924b`, `exp/rust-cpython-mac-footprint-20260924b` | `benchmarks/harness/memory.py`, `benchmarks/harness/macos_resource.py`, `benchmarks/harness/process.py`, new `experiments/mac-footprint-20260924.md` | Can native counters give a sounder root/tree memory gate? | Integrated as diagnostic; no parity claim |
| zlib compressed bytes | `/private/tmp/python-build-exp-zlib-bytes-20260924b`, `exp/rust-cpython-zlib-bytes-20260924b` | New `experiments/zlib-byte-compat.py` and `.md` | Which public compressed-byte differences are observable across backends? | Integrated; 210/876 byte differences, interoperability in sampled cases |
| tomllib scout | `/private/tmp/python-build-exp-tomllib-scout-20260924b`, `exp/rust-cpython-tomllib-scout-20260924b` | New `experiments/tomllib-target.md` | Is whole-document parsing a viable independent next target? | Integrated; defer implementation until public workload evidence |

The coordinator owns this ledger and integration order. The agents cannot
write each other's files. Generated artifacts stay in their worktrees; the
compressed-byte lane may read the existing proved interpreters and overlay
without mutating them. The candidate build will be scheduled separately
after the integration proposal is reviewed.

The footprint lane's bounded 0.5-second child diagnostic returned five
valid tree-footprint samples. The complete controller command used 0.13 user
plus 0.44 system CPU seconds and 25,755,648 bytes maximum RSS. Its two `ps`
scans per sample slowed the effective sampling interval below the requested
50 ms cadence. The raw field and compact runner mapping are diagnostic only;
no memory gate uses them yet. No behavioral tests were run for this second
cycle change. See `mac-footprint-20260924.md` for source-backed limits.

The compressed-byte lane ran 876 deterministic public zlib/gzip/ZIP encoding
cases against platform zlib and the proved zlib-rs overlay. Exactly 666
encoded streams matched byte for byte; 210 differed. All sampled streams
decoded whole and in chunks under both backends, with matching decoded
checksums. Its complete diagnostic used 4.31 user plus 0.20 system CPU
seconds and 106,577,920 bytes maximum RSS. The case details and scope limits
are in `zlib-byte-compat.md`; this is semantic evidence, not a timing result.

The tomllib scout's short profile on 400 complete loads of four 133–798-byte
local files used 0.05 user plus 0.01 system CPU seconds and 23,117,824 bytes
maximum RSS for the instrumented command. It found parser work but no
representative application bottleneck. No new crate is in the pinned Cargo
lock. `tomllib-target.md` recommends a bounded public workload before any
native parser implementation. The profile is location evidence only.

## First cycle (base `04667bb`, then `0224e8f`)

The first three lanes started at `04667bb013cf40443aaa0203e737a900d44e4464`.
The upstream control and zlib workload lanes started at
`0224e8fa4be570f287f2b46a05191a46ebe0c681`.
The root coordinator owns integration. The repo-local coordination skill is
`.agents/skills/rust-cpython-coordinator/SKILL.md`.

| Lane | Worktree and branch | Owned paths | Status | Heavy work |
| --- | --- | --- | --- | --- |
| Durable source patches | `/private/tmp/python-build-exp-patches-20260924`, `exp/rust-cpython-patches-20260924` | `rust-cpython/build.py`, `rust-cpython/tests/test_build.py`, new `rust-cpython/patches/` | Integrated; full build pending | Focused checks only |
| macOS CPU and memory | `/private/tmp/python-build-exp-resources-20260924`, `exp/rust-cpython-resources-20260924` | `benchmarks/bench.py`, `benchmarks/harness/`, `benchmarks/tests/` except `test_zlib_workloads.py`, `benchmarks/README.md` | Integrated; unique memory still open | Long benchmark deferred |
| First target selection | `/private/tmp/python-build-exp-target-20260924`, `exp/rust-cpython-target-20260924` | New `rust-cpython/experiments/first-target.md` only | Integrated; zlib provisional | No builds or timing runs |
| Matched upstream control | `/private/tmp/python-build-exp-upstream-20260924`, `exp/rust-cpython-upstream-20260924` | New `rust-cpython/experiments/upstream-baseline.md`, separate control script/lock and focused test | Integrated; full build succeeded | One isolated upstream PGO build |
| Native macOS memory | `/private/tmp/python-build-exp-mac-memory-20260924`, `exp/rust-cpython-mac-memory-20260924` | New `benchmarks/harness/macos_resource.py` and `benchmarks/tests/test_macos_resource.py` only | Integrated; harness wired by coordinator | Focused checks only |
| Next target scout | `/private/tmp/python-build-exp-next-target-20260924`, `exp/rust-cpython-next-target-20260924` | New `rust-cpython/experiments/next-target.md` only | Integrated; difflib hypothesis | Short diagnostic profile only |
| Public difflib workload | `/private/tmp/python-build-exp-difflib-workloads-20260924`, `exp/rust-cpython-difflib-workloads-20260924` | New `benchmarks/workloads/difflib.py` and `benchmarks/tests/test_difflib_workloads.py` only | Integrated; two public diff fixtures | Focused checks only |
| Difflib kernel probe | `/private/tmp/python-build-exp-difflib-kernel-20260924`, `exp/rust-cpython-difflib-kernel-20260924` | New `rust-cpython/experiments/difflib-kernel-probe.py` and `.md` only | Integrated as a rejected candidate; no product patch | Serial paired short probe |
| Public zlib workloads | `/private/tmp/python-build-exp-zlib-workloads-20260924`, `exp/rust-cpython-zlib-workloads-20260924` | `benchmarks/workloads/zlib.py`, `benchmarks/workloads/registry.py`, new `benchmarks/tests/test_zlib_workloads.py` if needed | Integrated; backend verdict pending | Long benchmark deferred |

No simultaneously owned files overlap. All generated builds and results stay in their lane
worktrees. At start, this Mac reported 10 logical CPUs, 32 GiB RAM, about
380 MiB swap used, load averages 6.07/5.54/4.89, and an OrbStack helper
near one CPU. Published timing measurements wait for a quieter host.
For this round, agents may use focused checks, but no full CPython build or
long benchmark. Any command likely to exceed 300 process CPU seconds or
2 GiB peak resident memory needs coordinator scheduling first.

The coordinator will record per-lane actual user and system CPU seconds,
peak memory and coverage in each lane's result before integration. Elapsed
time is recorded only as latency or scheduling context. Integrate one lane
at a time, inspect the combined diff, and remeasure interactions after the
host is suitable for timing work.

The target-selection lane produced `first-target.md` from existing reports
only; it ran no substantial command to account. The patch lane's first
review found a stale-manifest check in `test()` and returned that lane for a
focused correction before integration. Its final focused run passed 15 tests
and reported 0.14 user plus 0.11 system CPU seconds through `/usr/bin/time -l`,
37,257,216 bytes maximum RSS and 25,018,872 bytes peak footprint. These are
command-level resource figures, not CPython workload results. A complete
candidate build has not yet checked the integrated patch path.
The coordinator's focused rerun after adding required patch reproducers
passed the same 15 tests: 0.13 user plus 0.09 system CPU seconds,
37,240,832 bytes maximum RSS and 25,002,488 bytes peak footprint.
The resource lane's first focused run passed 57 tests (10 Linux-specific
skips) at 0.49 user plus 0.59 system CPU seconds and 48.2 MB maximum RSS.
After preserving the Linux PSS report keys, 34 focused report/baseline tests
passed at 0.14 user plus 0.05 system CPU seconds and 37.0 MB maximum RSS.
The zlib workload lane's focused check passed at 0.08 user plus 0.03 system
CPU seconds and 42,205,184 bytes maximum RSS; that RSS figure may omit its
short-lived zipimport child. The upstream lane's source fetch, extraction,
doctor, and focused test resource figures are in `upstream-baseline.md`.

The integrated focused check passed 60 tests with 10 Linux-specific skips:
0.56 user plus 0.63 system CPU seconds, 51,216,384 bytes maximum RSS, and
38,765,048 bytes peak footprint (`/usr/bin/time -l`). This did not build a
new interpreter or test Linux at runtime. `git diff --check` was clean.

The coordinator's first serial zlib probe used the existing no-Rust fork and
the already tested zlib-rs overlay. It checked identical input and output
digests for every pair and recorded raw wall/CPU observations in `data/`.
The 5-pair CPU pass cost 6.33 user plus 4.12 system CPU seconds, with
49,774,592 bytes maximum RSS for the probe command. The 3-pair CPU plus RSS
pass cost 9.09 user plus 13.01 system CPU seconds, with 49,283,072 bytes
maximum RSS. These command-level figures include the harness; workload CPU
figures are in the raw reports. See `zlib-probe-20260924.md` for the verdict.

The first upstream `fetch` failed because the host Python's default CA path
could not validate the download. With `SSL_CERT_FILE=/etc/ssl/cert.pem`, the
exact locked source, LLVM archive, and attestation were fetched and verified.
That command used 155.77 user plus 3.38 system CPU seconds, 79,085,568 bytes
maximum RSS and 51,069,456 bytes peak footprint; elapsed time was 191.81 s.
The subsequent `doctor` passed at 0.13 user plus 0.06 system CPU seconds and
35,438,592 bytes maximum RSS. The verified LLVM cache was cloned into the
upstream lane worktree because the toolchain identity requires paths local to
that checkout. The nine-worker PGO build succeeded there: 678.55 user plus
102.69 system CPU seconds, 1,780,416,512 bytes maximum resident set size,
and no swap events reported by `/usr/bin/time -l`; elapsed time was 260.54 s.
The tool's 29,098,488-byte peak footprint describes its waited parent rather
than a simultaneous build-process-tree peak. `data/upstream-build-20260924.json`
records the exact source and recipe; build outputs remain isolated in the
worktree. Host swap usage stayed at about 380 MiB through the build.

The macOS memory research found `proc_pid_rusage` V4 can read current RSS,
physical footprint, and lifetime maximum footprint for a live or zombie PID.
`waitid(..., WNOWAIT)` allows reading the root after exit but before `wait4`
reaps it. This gives a short-lived root a kernel peak even when polling misses
it. The API does not provide a simultaneous tree peak or a Linux-style USS/PSS;
the external tree sampler remains a lower-bound observation for children.
The isolated API wrapper's five focused tests passed at 0.08 user plus 0.03
system CPU seconds and 31,506,432 bytes maximum RSS. After coordinator wiring,
50 combined harness/control tests passed with 10 Linux skips at 0.50 user plus
0.55 system CPU seconds and 48,218,112 bytes maximum RSS. No long benchmark
was run concurrently with the upstream build.

After the build, the zlib kernel-RSS probe used 8.65 user plus 12.17 system
CPU seconds and 50,741,248 bytes maximum RSS for the harness command. The
platform-zlib self-comparison used 10.69 user plus 13.70 system CPU seconds
and 49,741,824 bytes maximum RSS. Both were serial; their exact workload
observations and host load are in `data/` and summarized in
`zlib-probe-20260924.md`.

An initial local upstream-versus-Rust-fork zlib workload attempt exposed that
the benchmark controller prepared the entire Linux 3.14 wheelhouse even for a
selected stdlib-only workload; it stopped before measurement. A failing
focused regression preceded the fix to prepare wheels only when selected
workloads consume them. The corrected local run reached the workload and
reported wall latency -2.59%, CPU per decoded byte -1.01%, and sampled/kernel
peak RSS +14.20% for the Rust-enabled fork with platform zlib. Its diagnostic
report marked memory FAIL, but the run had host load 5.12 and only three
memory pairs, with no unique-memory metric. A follow-on provenance check found
the report listed unused core wheel identities; that bookkeeping bug now has
a focused regression and fix. The original run remains under the upstream
worktree's ignored `rust-cpython/results/upstream-vs-fork-zlib-v2/` and is not
a qualification result. The subsequent upstream self-comparison used 1.77
user plus 2.49 system CPU seconds and 47,792,128 bytes maximum RSS for the
harness command. It produced no package-provenance claims. Its three paired
root-RSS ratios ranged 0.853–1.071; the cross run's paired RSS ratios ranged
0.978–1.257. The exact raw data and interpretation are in
`upstream-zlib-control-20260924.md`. Repeat on a quiet host before interpreting
the memory difference.

The next-target scout used a short instrumented `difflib.unified_diff`
diagnostic and selected `SequenceMatcher` as the next independent hypothesis.
The profiled process used 0.18 user plus 0.01 system CPU seconds and
25,214,976 bytes maximum RSS. This identifies a hot matching loop, not a
candidate speedup. The semantics, public-state hazard, and stop criteria are
in `next-target.md`.

The difflib workload lane added two fixed complete `unified_diff` cases and
passed its focused test. Its 500-iteration reordered diagnostic used 0.13
user plus 0.01 system CPU seconds and 20,758,528 bytes maximum RSS. The
coordinator registered the workloads at 500 mostly-equal and 1,000 reordered
diffs per process after short iteration-sizing diagnostics. Those sizing
commands ran concurrently and are not comparative performance evidence.

A later integrated focused check passed 71 tests, with 10 Linux-specific
skips: 0.59 user plus 0.68 system CPU seconds and 55,623,680 bytes maximum
RSS. It did not run a full CPython regression suite or Linux runtime checks.

The first difflib candidate reused alternating `find_longest_match` row
dictionaries in a pinned-source monkeypatch. It matched 132 differential
matcher cases, 11 complete public-output cases, and 59 unchanged
`test_difflib` tests. Five serial pairs per public workload showed no useful
gain; reordered input was slower in internal wall and user CPU, and root
peak RSS rose about 0.3 MiB in both workloads. The host had material competing
CPU load, so small time differences are uncertain. The idea was rejected and
left outside the candidate build. Child `wait4` CPU and peak RSS per complete
workload, with all 20 raw observations, are in `difflib-kernel-probe.md`.
