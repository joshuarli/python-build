# Rust-for-CPython stdlib optimization

## Objective and decision rule

Make the standard library faster and less resource intensive on representative
application workloads. Work independently in the isolated CPython 3.16
`rust-cpython/` lane: find a measured bottleneck, improve the smallest useful
implementation boundary, prove unchanged behavior, and measure the result.
Keep a change when it produces a repeatable, useful improvement without a
material regression; then select the next bottleneck. Rust is an implementation
option, not the success criterion. Existing C and Python paths are the
semantic and performance competition.

Judge each candidate in this order:

1. Preserve public API behavior: values and bytes, exceptions, callbacks,
   subclass behavior, and relevant platform behavior. Unchanged CPython
   regression tests remain the compatibility judge.
2. Improve real application latency and process CPU time, including
   startup/import and steady work. Report kernel-accounted user and system CPU
   seconds per logical operation, including child processes where applicable.
   Wall time remains the measure of user-visible latency; it is not a proxy
   for CPU consumption.
   A private microbenchmark win is insufficient unless a public stdlib path
   uses it and a representative workload benefits.
3. Keep peak and retained process memory at or below a comparable upstream
   CPython baseline within empirically measured noise. Track native and Python
   allocation counts and bytes per unit of work, and investigate increases.
4. Record installed native size, build complexity, and maintenance cost.
   Prefer the simpler change when performance is indistinguishable.

Individual important workloads determine the verdict. An aggregate speedup
cannot hide a clear time or memory regression. Do not silently exchange a
speed gain for more RAM. Leave a genuine tradeoff as an experiment with its
evidence if it needs a product-policy decision.

## Scope and comparison controls

The production product remains CPython **3.14.6**. Its frozen Linux recipes,
packaging, and release workflow are outside this experiment. The experimental
source and Rust toolchain pins live in `rust-cpython/sources.lock.json` and
`rust-cpython/rust-toolchain.toml`. Use the commands and ranked candidate map
in [`rust-cpython/README.md`](rust-cpython/README.md). Persist source changes
as checked-in patches or other reproducible inputs; edits only under generated
`rust-cpython/work/source/` disappear on re-extraction. The candidate builder
now applies digest-checked patches from `rust-cpython/patches/manifest.json`
after each fresh extraction. Its no-Rust control remains unpatched. The patch
path has a full patched-build qualification for the URL quotation candidate,
and the optional zlib-rs recipe has completed a full candidate build. Do not
add a dependency, change a source/toolchain pin, or expand product scope
without an explicit scope decision.

Use distinct controls. The immediate control for each change is the last
accepted fork build without that change; it isolates the proposed module
patch. `rust-cpython/build_no_rust.py` builds the pinned fork with Cargo
disabled and isolates the existing Rust integration as a whole. A comparably
built vanilla upstream CPython 3.16 from the closest appropriate revision is
the primary baseline for claims about CPython improvement and upstream memory
parity. Match architecture, compiler, PGO, LTO, GIL, optimization flags, and
benchmark inputs as closely as practical, and record mismatches. PBS or 3.14
comparisons are secondary or exploratory. Label cross-version and unmatched
comparisons accordingly; they cannot pass the upstream resource gate.

## Unattended hill-climb loop

1. **Establish the baseline.** Read current build, test, and benchmark reports.
   Record exact revisions, toolchains, flags, host, and fixture identities.
   Calibrate control against itself to learn local timing and memory noise.
2. **Choose from evidence.** Profile representative workloads, then consult
   the ranked map in `rust-cpython/README.md`. That map is a hypothesis queue,
   not a required port order. Prefer a hot, coarse stdlib operation whose
   public callers and current implementation are clear.
3. **State the contract.** Identify callers, existing Python/C semantics,
   edge cases, relevant CPython tests, and the realistic workload expected to
   improve. For a behavior bug, first add an isolated failing regression test.
4. **Change one boundary.** Keep public APIs and CPython-owned C-ABI
   boundaries. Use the fork's `cpython-sys` and internal Rust model where Rust
   fits. Keep an existing implementation as an oracle or fallback when useful,
   but do not hide a slow path in the performance claim.
5. **Prove correctness.** Run focused unchanged CPython tests on control and
   candidate, differential checks for semantic edges, and broader regression
   coverage when warranted. Verify that the public API reaches the new path.
6. **Measure.** Use targeted kernels to explain the mechanism and realistic
   workloads to decide its value. Keep timing, memory, and allocation passes
   separate. Run broad pyperformance coverage for changes with broad reach.
   Repeat close results when host noise could change the verdict.
7. **Decide and repeat.** Keep only a behavior-preserving change with a gain
   beyond measured noise in a meaningful workload and no unexplained material
   regression elsewhere. Investigate a concrete failure, or revert the
   candidate and record why. Update the evidence and choose the next target.

Keep a compact experiment record beside the lane's performance evidence:
question, source/patch revision, controls, workload and operation count,
tests, raw report paths, time/memory/allocation deltas, noise bounds, verdict,
and next action. Preserve rejected ideas as findings, without leaving their
code in the active build. A later unattended run should be able to resume
from that record. Continue through independent, reversible experiments. If
progress needs a new dependency, pin, production scope change, or a choice
between material resource tradeoffs, complete the preparatory analysis and
record the proposed decision before pausing for that decision.

## Benchmark contract from the older plan

The earlier benchmark plan specified a generic interpreter benchmark system.
Much is already implemented in `benchmarks/`; use
[`benchmarks/README.md`](benchmarks/README.md) and `benchmarks/bench.py` as the
current interface. The rules below govern Rust-for-CPython qualification.

| Pass | Requirement |
| --- | --- |
| Time and CPU | Serial, counterbalanced control/candidate pairs with equal logical work. Report wall latency and actual process-tree user/system CPU time per unit separately. No memory sampler, profiler, forced GC, or special allocator in the timed candidate. Keep ordinary GC, ASLR, and hash randomization. Use baseline-derived loop counts where supported. |
| Memory | Run separately under an external process-tree observer. Keep raw samples, peak and steady/retained memory, RSS and unique/private memory, and PSS where available. Count children. Report absolute and relative deltas. Post-GC retention is diagnostic. |
| Allocation | Run separately under Memray where compatible, with native/system and Python allocator activity distinguished. Report counts and bytes per logical work unit. Profiled elapsed time is never a speed result. |
| Diagnostic | Use native profiles, `perf`, or CPython stats to locate changes. Instrumented or differently configured builds produce diagnostic evidence only. |

The primary workload set is the repository-owned application suite: Django
WSGI/ASGI/ORM, startup and imports, tooling, packaging/compileall,
serialization, and multiprocessing. Add a missing high-value workload when
it exposes a relevant gap, such as Django cold start, mixed requests,
serialization or form validation, wheel extraction, or a compatible selected
Pyston macrobenchmark. The full pyperformance suite gives broad context;
targeted kernels explain a module. Keep group and per-workload results visible.
PBS comparison remains a distribution reference.

For an upstream-matched comparison, each important workload's peak and
steady/retained memory must remain within a noise allowance established by
self-comparison. Report raw direction even within noise. Investigate material
allocation growth. An unavailable metric is neither zero nor a pass. Report
installed interpreter, extension, and Rust runtime bytes separately from
process memory.
When an installed Python source file changes, verify equal bytecode-cache
policy before timing or memory measurement: each side must have valid cache
bytes for its own source, or both must compile source. Prepare caches outside
measured processes and record their hashes and invalidation mode. A stale
candidate cache under `PYTHONDONTWRITEBYTECODE=1` made the URL overlay appear
roughly 3 MB heavier at import; see the
[`cache-attribution experiment`](rust-cpython/experiments/url-quote-memory-attribution-20260924.md).
Calibrate both control against itself and candidate against itself before
accepting a close result. Use baseline-derived fixed loop counts for
pyperformance where its interface supports them; that path is still open in
the current harness. Record child-CPU coverage for each workload. A numeric
CPU comparison with root-only coverage is not a process-tree total.

### Present measurement boundary

`benchmarks/` already provides paired timings, locked CPython 3.14 Linux
inputs, application macros, pyperformance, an external Linux process-tree
sampler, Memray passes, self-comparison, and noise-aware per-workload verdicts.
Native Apple Silicon supports paired wall and kernel CPU time plus a separate
external process-tree RSS and sampled physical-footprint pass for a small local suite. A kernel lifetime peak
for the workload root catches short runs that sampling misses, but its
per-PID physical footprint is not a whole-tree unique-memory measure. RSS growth is useful
regression evidence, but summed RSS can double-count shared pages. Unique or
proportional memory and allocation passes remain unavailable for this macOS
3.16 lane, so upstream memory parity is still unqualified.
The sampled footprint is a kernel ledger of charged dirty memory across the
observed process tree; it is neither USS/PSS nor an exact tree peak. The
[`mac-footprint-20260924.md`](rust-cpython/experiments/mac-footprint-20260924.md)
report records its coverage and sampler cost.
The generic `wait4` CPU counter covers the workload root only. The cold ZIP
import workload now adds a separate kernel ledger for its directly reaped
interpreter children. Other subprocess workloads need explicit child coverage
before their CPU values can be called process-tree totals; each result records
its coverage.
The Linux wheel lock targets CPython 3.14 musl and must not be silently reused
for 3.16.

The next benchmark infrastructure work is native macOS unique/proportional
memory observation and a compatible allocation pass, followed by self-comparison
of the newly built matched upstream 3.16 control and compatible locked benchmark inputs. Keep
workload definitions interpreter-agnostic and record unsupported workloads rather than substituting
unmatched package versions for one interpreter. Focused timing and correctness
experiments may proceed while those gaps remain, with their limits stated
explicitly.
The installed macOS SDK exposes per-region private-resident counters as a
possible sampled diagnostic, but current evidence does not establish exact
USS or PSS. A bounded probe must check traversal, aliases, COW behavior,
permissions, and overhead before adding a field. See
[`mac-unique-memory-feasibility-20260924.md`](rust-cpython/experiments/mac-unique-memory-feasibility-20260924.md).
That bounded `PROC_PIDREGIONINFO` probe failed the traversal gate: submaps
made its raw page sums incomplete or overlapping. No mapped-private benchmark
field was added; see
[`mac-region-probe-20260924.md`](rust-cpython/experiments/mac-region-probe-20260924.md).

## Current evidence

- The isolated lane builds and tests Rust-for-CPython CPython 3.16.0a0.
- The Rust `_base64` extension builds, imports, and passes byte-for-byte checks
  against `binascii` for representative bytes, `bytearray`, and `memoryview`
  inputs. Its measured performance is in
  [`rust-cpython/PERFORMANCE.md`](rust-cpython/PERFORMANCE.md).
- `_base64` is an integration proof, not a public stdlib optimization:
  `Lib/base64.py` still routes through `binascii`. The Rust path is faster for
  64-byte inputs but 42–48% slower at 4 KiB and above in the measured cases.
- A separate [`zlib-proof`](rust-cpython/zlib-proof/README.md) links the pinned
  `zlib-rs` 0.6.7 C ABI beneath the unchanged CPython `Modules/zlibmodule.c`.
  `test_zlib` passed 85 tests (2 skipped); `test_gzip`, `test_tarfile`,
  `test_zipfile`, `test_zipimport`, and `test_binascii` passed 1,807 tests
  (37 skipped). The extension had no dynamic `libz` dependency.
- The first public-path zlib probe found lower CPU use for one-shot,
  streaming, and gzip decompression on the existing no-Rust fork, but ZIP
  results were mixed and memory observations were incomplete. See
  [`zlib-probe-20260924.md`](rust-cpython/experiments/zlib-probe-20260924.md).
- A compressed-byte probe found 210 different encodings among 876 sampled
  public zlib/gzip/ZIP cases. Every sampled stream decoded with both backends,
  but the backend cannot be called byte-equivalent. See
  [`zlib-byte-compat.md`](rust-cpython/experiments/zlib-byte-compat.md).
- An optional whole-build zlib-rs candidate retains platform zlib for
  `binascii`. Its clean PGO build succeeded, but the two unstripped extensions
  are 1.59 MB larger than the platform-zlib control. Five public decompression
  workloads preserved checked output. One-shot zlib, streaming zlib, and gzip
  operations improved in the local paired run; ZIP read and cold ZIP import
  remained within timing noise. ZIP read's peak RSS and sampled physical
  footprint increased, and macOS memory parity is still unqualified. See
  [`zlib-build-candidate.md`](rust-cpython/experiments/zlib-build-candidate.md)
  and [`zlib-full-candidate-20260924.md`](rust-cpython/experiments/zlib-full-candidate-20260924.md).
  A paired follow-up found the 3.13 MB ZIP peak-RSS increase below local
  repeatability noise; the footprint signal remains sample-sensitive. See
  [`zlib-memory-followup-20260924.md`](rust-cpython/experiments/zlib-memory-followup-20260924.md).
- Cold ZIP import now records directly reaped child CPU separately from the
  root's `wait4` usage. Earlier cold-import CPU data remain root-only; see
  [`child-cpu-accounting-20260924.md`](rust-cpython/experiments/child-cpu-accounting-20260924.md).
- The vanilla upstream 3.16.0a0 merge-base control built with the locked LLVM,
  ThinLTO, and the fork's nine-worker PGO task. Its recipe and limits are in
  [`upstream-baseline.md`](rust-cpython/experiments/upstream-baseline.md).
- One local upstream-versus-fork public zlib decode comparison found an
  unresolved peak-RSS signal under a busy host. The paired data and
  self-comparison are in
  [`upstream-zlib-control-20260924.md`](rust-cpython/experiments/upstream-zlib-control-20260924.md).
- A `difflib` row-dictionary reuse probe preserved tested behavior but gave
  no useful complete-workload gain and increased root peak RSS. It was
  rejected; see
  [`difflib-kernel-probe.md`](rust-cpython/experiments/difflib-kernel-probe.md).
- `tomllib` remains a possible whole-document target, but a short profile of
  small local files does not establish an application bottleneck. The
  [`tomllib-target.md`](rust-cpython/experiments/tomllib-target.md) report
  defers a native parser until complete public workloads justify its cost.
- A registered catalog URL workload now exercises the checked-in application's
  `normalize_url` and `stable_key` functions over 48 mixed records with fixed
  complete-output digests. A short profile identified `urllib.parse.quote`
  calls but did not establish a speed opportunity. See
  [`next-target-after-zlib-20260924.md`](rust-cpython/experiments/next-target-after-zlib-20260924.md)
  and [`catalog-url-workload-20260924.md`](rust-cpython/experiments/catalog-url-workload-20260924.md).
  Its first control self-comparison had 6.62% timing noise under rising host
  load, so no upstream or candidate speed claim follows from that run. See
  [`catalog-url-baseline-20260924.md`](rust-cpython/experiments/catalog-url-baseline-20260924.md).
- Sizing the same fixed batch to 1,500 iterations gave a 0.64-second timed
  interval and reduced control self-comparison noise to 2.61%. Matched vanilla
  upstream and the no-Rust fork had a 0.99995 paired wall ratio on the URL
  task; this establishes a control, not a Rust speedup. See
  [`catalog-url-quiet-baseline-20260924.md`](rust-cpython/experiments/catalog-url-quiet-baseline-20260924.md).
- A complete-batch diagnostic attributed 18.5% of instrumented cumulative
  time to `quote_from_bytes`, an optimistic bound for a helper. After current
  fast exits, 64% of calls would reach an exact-bytes guard; nearly all of
  those scan inputs were at most 17 bytes. See
  [`catalog-url-headroom-20260924.md`](rust-cpython/experiments/catalog-url-headroom-20260924.md).
- An isolated guarded Rust quote proof passes 2,177 differential public cases,
  182 unchanged CPython URL tests, and the complete catalog output check. Its
  unstripped extension is 1.47 MB. It has no paired speed or memory verdict;
  see [`url-quote-proof-20260924.md`](rust-cpython/experiments/url-quote-proof-20260924.md).
- The proof's paired complete-task run reduced wall time by 19.3% and root
  CPU per batch by 17.4%, but the candidate's parser bytecode cache was
  invalid while the control's was valid, confounding its 3.19 MB peak-RSS
  increase. The memory verdict is withdrawn; see
  [`url-quote-comparison-20260924.md`](rust-cpython/experiments/url-quote-comparison-20260924.md).
- A no-std, direct-Unicode variant shrank the extension from 1.47 MB to 50,712
  bytes and passed the same public semantic checks. Its first five paired
  memory runs showed a 2,932,736-byte peak-RSS rise, but also had the invalid
  candidate parser cache. Timing self-calibration was too noisy for a speed
  verdict. See
  [`url-quote-lean-proof-20260924.md`](rust-cpython/experiments/url-quote-lean-proof-20260924.md)
  and [`url-quote-lean-comparison-20260924.md`](rust-cpython/experiments/url-quote-lean-comparison-20260924.md).
- An isolated memory attribution reproduced the multi-megabyte RSS rise only
  when the candidate's checked-hash parser cache was invalid. With valid
  caches on both sides, the lean candidate's paired catalog peak-RSS median
  was 65,536 bytes lower across four diagnostic pairs. Extension import alone
  stayed near control. This removes the earlier RSS rejection but is not a
  standard speed or upstream-memory qualification; see
  [`url-quote-memory-attribution-20260924.md`](rust-cpython/experiments/url-quote-memory-attribution-20260924.md).
- A cache-matched comparison against the last accepted Rust fork stage found
  the lean guarded overlay 18.7% faster in paired complete-task wall time and
  18.6% lower in root CPU, with +131,072 bytes median peak RSS inside measured
  self-noise. All complete digests matched. Keep it as a source-patch
  candidate, not yet an accepted build or upstream parity claim; see
  [`url-quote-fair-comparison-20260924.md`](rust-cpython/experiments/url-quote-fair-comparison-20260924.md).
- The first full URL candidate build exposed a silent `git apply` no-op inside
  the enclosing worktree; its `built` report was invalid as candidate evidence.
  The driver now isolates patch application and rejects zero-file application.
  A fresh full build changed all seven intended source paths, installed the
  guarded extension, and passed 2,177 differential public cases, 182 URL
  tests, the catalog digest, and a subinterpreter check. This qualifies build
  and behavior, while installed-build paired timing and memory remain open;
  see [`url-quote-full-build-20260924.md`](rust-cpython/experiments/url-quote-full-build-20260924.md)
  and [`url-quote-full-build-retry-20260924.md`](rust-cpython/experiments/url-quote-full-build-retry-20260924.md).
- On the installed candidate, five cache-matched complete catalog pairs had
  17.7% less wall time and 17.9% less root CPU than the prior Rust fork build.
  Separate peak-RSS pairs had a +294,912-byte median within both sides'
  measured self-noise. The executables differ after PGO, so this corroborates
  rather than isolates the patch effect; upstream resource parity remains
  open. See
  [`url-quote-installed-comparison-20260924.md`](rust-cpython/experiments/url-quote-installed-comparison-20260924.md).

## Immediate work queue

- **The optional zlib-rs build is an experiment, not a production migration.**
  The ordinary lane build still links `Modules/zlibmodule.c` to platform zlib.
  Repeat ZIP and memory measurements on a quieter host, including cold import
  with the corrected direct-child CPU ledger, and decide whether the compressed-byte differences
  and installed-size cost fit the desired contract before promotion.
- No public stdlib API in the experiment has yet been shown to improve
  broadly in Rust. The ranked entries in `rust-cpython/README.md` remain
  candidates, not completed work.
- Establish the missing macOS unique/proportional memory and allocation
  measurements and matched upstream control comparison. The simple libproc
  region probe failed; any further USS/PSS work needs a different interface
  with proven page identity and coverage. The installed Xcode Allocations
  tool may offer a bounded diagnostic route, but its export and child coverage
  need proof; see
  [`mac-allocation-feasibility-20260924.md`](rust-cpython/experiments/mac-allocation-feasibility-20260924.md).
  Continue zlib's
  quiet-host and memory qualification.
  A native kernel on arbitrary public `difflib.SequenceMatcher` instances has
  no cheap sound guard for their mutable state; stop that route. A one-shot
  `unified_diff` path is a separate hypothesis whose snapshot and validation
  cost should be measured first; see
  [`difflib-guard-audit-20260924.md`](rust-cpython/experiments/difflib-guard-audit-20260924.md).
- Compare the installed, patched URL candidate with the matched upstream
  control under the same cache and quiet-host rules, then investigate other
  relevant workloads before an integration verdict. Unique/proportional
  memory and allocations remain unqualified even if RSS stays within noise.
- Prepare byte-pinned application inputs compatible with the 3.16 macOS lane,
  including a true cold Django request. Extend the primary public-workload
  suite before claiming broad stdlib gains; then add baseline-derived loops
  for pyperformance and document which selected Pyston macros can run.
