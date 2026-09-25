# Rust-for-CPython stdlib optimization

## Objective and decision rule

Make the standard library faster and less resource intensive on representative
application workloads. Work independently in the isolated CPython 3.16
`rust-cpython/` lane: find a measured bottleneck, improve the smallest useful
implementation boundary, prove unchanged behavior, and measure the result.
The primary goal is a repeatable workload improvement without an unexplained
resource regression. A secondary goal is broad, useful Rust implementation
coverage of important public stdlib modules. Existing C and Python paths are
the semantic and performance comparison.

A coverage port may be retained in the experimental lane even when it is
slower, larger, or uses more memory. Record that cost plainly and keep working
on it; an important module can become faster over later iterations. A port
with a material default-workload regression may remain selectable behind an
explicit build option while its performance debt is addressed. Coverage
retention does not turn a regression into a performance win or change the
production CPython 3.14.6 contract.

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
3. For performance acceptance, keep peak and retained process memory at or
   below a comparable upstream CPython baseline within empirically measured
   noise. For coverage retention, measure and record any excess as debt.
   Track native and Python allocation counts and bytes per unit of work.
4. Record installed native size, build complexity, and maintenance cost.
   Prefer the simpler change when performance is indistinguishable.

Individual important workloads determine the verdict. An aggregate speedup
cannot hide a clear time or memory regression. Do not silently exchange a
speed gain for more RAM. Coverage can justify retaining a port in this
experimental lane, but its tradeoffs remain explicit and unresolved for any
product decision.

## Scope and comparison controls

The production product remains CPython **3.14.6**. Its frozen Linux recipes,
packaging, and release workflow are outside this experiment. The lane runs
natively on Apple Silicon macOS and, since 2026-09-25, on x86_64 glibc Linux
(Ubuntu 24.04) with the same source pins, patches, LLVM 23.1.2 release, and
controls; the Linux toolchain and host packages are pinned in
`rust-cpython/linux-toolchain.lock.json`. Report which platform each result
comes from; a verdict on one platform does not transfer to the other. The experimental
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

Only macOS arm64 and Linux x86-64/arm64 are in scope. Windows, Intel macOS,
other Linux architectures, and all other platforms are explicitly
unsupported; do not spend coverage effort on their platform branches. The
product already builds both Linux architectures. The Rust experiment currently
builds macOS arm64 and Linux x86-64; Linux arm64 remains an unimplemented
experimental target. Public APIs available on supported hosts, including
lexical `PureWindowsPath` parsing, still need their normal behavior preserved.

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
7. **Decide and repeat.** Mark a behavior-preserving change as a performance
   gain when it improves meaningful workloads beyond noise without an
   unexplained material regression elsewhere. A high-value Rust port can
   instead be retained for coverage with its measured performance and memory
   debt visible, often behind an option until that debt is reduced. Reject an
   incorrect or unsafe boundary. Update the evidence and choose the next
   target or optimization of a retained port.

Commit each finished experiment's source or patch, exact build and workload
recipe, compact measurements for every attempt, relevant failure excerpts,
noise bounds, verdict, and next action. Record the shared command and
environment once; each observation needs only its ID, side and order, outcome,
wall and kernel CPU, memory and swap where measured. Avoid per-attempt log
paths and coordinator status files. Generated interpreters and raw compiler
output are rebuildable and stay outside Git. Preserve rejected ideas as
findings without leaving their code in the active build. A later unattended
run should be able to resume from checked-in evidence after a reboot. Continue
through independent, reversible experiments. If
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

For performance acceptance against a matched upstream build, each important
workload's peak and steady/retained memory must remain within a noise
allowance established by self-comparison. For coverage retention, record the
same differences as debt and keep the port selectable while optimizing it.
Report raw direction even within noise and investigate material allocation
growth. An unavailable metric is neither zero nor a pass. Report installed
interpreter, extension, and Rust runtime bytes separately from process memory.
When an installed Python source file changes, verify equal bytecode-cache
policy before timing or memory measurement: each side must have valid cache
bytes for its own source, or both must compile source. Prepare caches outside
measured processes and record their hashes and invalidation mode. A stale
candidate cache under `PYTHONDONTWRITEBYTECODE=1` made the URL overlay appear
roughly 3 MB heavier at import; see the
[`cache-attribution experiment`](rust-cpython/experiments/url-quote-memory-attribution-20260924.md).
`PYTHONDONTWRITEBYTECODE=1` blocks cache writes but still permits reads from
existing installed `.pyc` files; an absent `PYTHONPYCACHEPREFIX` does not
change that. An import audit is needed before describing a run as source-only.
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

On x86_64 Linux the lane has what macOS lacks: the external sampler reads
`/proc/*/smaps_rollup`, so peak PSS and peak private (USS) memory are measured
for every workload, and the matched upstream 3.16 control is built on the
same host. The shared KVM host is noisy (standard-profile self-comparison
limits of 4.5–56%), so Linux verdicts use
[`linux_paired.py`](rust-cpython/experiments/linux_paired.py): 20 timing and
10 memory alternating pairs with bootstrap intervals and matching
self-comparisons. Allocation counts remain unavailable on both platforms
(no Memray build for 3.16).

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
Xcode's Allocations export was also probed on the pinned 3.16 interpreter.
Its aggregate buckets round requested bytes and do not establish allocation
totals for spawned children; it is diagnostic only. See
[`mac-allocation-probe-20260924.md`](rust-cpython/experiments/mac-allocation-probe-20260924.md).
An experiment-only dyld interposer did capture controlled parent, spawned
child, and threaded `malloc` requests with exact sizes. It still lacks broad
allocator-API, abnormal-exit, phase-boundary, and complete process-tree
coverage, so it is a diagnostic rather than an allocation benchmark gate;
see [`mac-malloc-interpose-feasibility-20260924.md`](rust-cpython/experiments/mac-malloc-interpose-feasibility-20260924.md).
The Mach per-page object reference count also cannot establish USS or PSS;
the bounded diagnostic route and stop conditions are in
[`mac-memory-next-method-20260925.md`](rust-cpython/experiments/mac-memory-next-method-20260925.md).
The local `rustybench` now offers a Rust `Allocator`/`GlobalAlloc` profiler
under its Rust 1.100 toolchain. It may explain allocation changes inside a
focused Rust kernel, but cannot count CPython's C allocator activity or
qualify a whole Python process. Keep the experimental lane's pinned toolchain
and existing interpreter comparisons coherent; evaluate any toolchain update
as a separate baseline change.

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
  remained within timing noise. The first ZIP memory pass showed higher peak
  RSS and sampled physical footprint, but macOS memory parity is still
  unqualified. See
  [`zlib-build-candidate.md`](rust-cpython/experiments/zlib-build-candidate.md)
  and [`zlib-full-candidate-20260924.md`](rust-cpython/experiments/zlib-full-candidate-20260924.md).
  A paired follow-up found the 3.13 MB ZIP peak-RSS increase below local
  repeatability noise; the footprint signal remains sample-sensitive. See
  [`zlib-memory-followup-20260924.md`](rust-cpython/experiments/zlib-memory-followup-20260924.md).
  A quieter eight-pair ZIP repeat with matched source-only bytecode policy
  measured candidate-minus-control median root peak RSS of −0.15 MB and root
  peak footprint of −0.36 MB, both inside same-session control variation.
  The prior positive signal did not repeat; this does not establish parity
  under installed-cache behavior or supply USS/PSS and allocation counts.
  See [`zlib-quiet-memory-20260924.md`](rust-cpython/experiments/zlib-quiet-memory-20260924.md).
- A separate prefixed zlib-rs inflate hybrid keeps compression, checksums,
  public version identity, and `binascii` on platform zlib. Its installed
  interpreter matched all 876 sampled compressed byte outputs, cross-decoded
  both ways, and passed 1,892 focused CPython tests with 39 skips. The first
  full build command failed only at a post-install symbol check that matched
  part of a prefixed name; corrected exact symbol validation passed on the
  installed bytes without rebuilding. See
  [`zlib-hybrid-proof-20260924.md`](rust-cpython/experiments/zlib-hybrid-proof-20260924.md).
- A longer seven-pair public decode/gzip pass found about 35% lower complete
  process wall time and 36% lower kernel CPU for that hybrid, beyond control
  self-noise. All 118 checked attempts matched decoded digests. Sampled memory
  differences changed sign, and equal debug stripping left a 1.45 MB
  extension-size cost. That result established a decode-heavy speed candidate,
  subject to broader application and resource evidence; see
  [`zlib-sustained-20260925.md`](rust-cpython/experiments/zlib-sustained-20260925.md).
- A synthetic public `tarfile` extraction task showed no hybrid speed gain.
  A second task read all 6,031 regular files from the locked CPython source
  `.tar.gz`; every output digest matched, but all seven hybrid pairs were
  slower. Median full-process CPU rose 10.81%, far beyond control self-noise,
  and three memory pairs had a +688 KB peak-RSS median. This blocks promotion
  of the current hybrid until the regression is understood and removed; see
  [`tarfile-hybrid-breadth-20260925.md`](rust-cpython/experiments/tarfile-hybrid-breadth-20260925.md)
  and [`source-tar-hybrid-20260925.md`](rust-cpython/experiments/source-tar-hybrid-20260925.md).
- A narrow Rust checksum scan under public `tarfile` reduced five paired
  complete source-archive reads by 10.18% wall and 10.38% kernel CPU. It
  preserved the checked output digest; three memory pairs were inconclusive.
  That same-interpreter proof is retained in
  [`tar-checksum-proof-20260925.md`](rust-cpython/experiments/tar-checksum-proof-20260925.md).
  A later optional source patch built on macOS and repeated the complete-read
  gain: five corrected-build pairs improved median wall by 9.22% and kernel
  CPU by 9.48%, with identical output; see
  [`tar-checksum-integrated-20260925.md`](rust-cpython/experiments/tar-checksum-integrated-20260925.md).
  A TAR-owned private extension subsequently removed the URL-module coupling
  and loads lazily. Five new complete-archive pairs improved median wall by
  9.24% and user CPU by 9.17%, with unchanged output. Cold `tarfile` import
  left the extension unloaded and showed no established regression. The route
  remains opt-in while helper-replacement semantics, broader behavior, and
  memory remain unqualified. See
  [`tar-owned-module-20260925.md`](rust-cpython/experiments/tar-owned-module-20260925.md).
  A second complete workload streamed every member through public
  `tarfile` read and write calls into a new archive. All 12 runs produced
  identical output; five candidate pairs reduced median wall by 11.87% and
  kernel CPU by 12.05%, with mixed peak-memory directions. See
  [`source-tar-rewrite-20260925.md`](rust-cpython/experiments/source-tar-rewrite-20260925.md).
  An import-time helper guard now sends ordinary Python-function replacements
  made before `tarfile` imports through the original checksum expressions;
  later replacements retain the existing fallback. Five new archive pairs
  kept a 9.01% median wall gain over quote-only. Against the earlier TAR-owned
  stage, the guard's 0.90% median wall increase was within local control
  drift. Deliberately spoofed native helpers and custom importers remain
  outside the established behavior boundary; no separate semantic probe or
  CPython suite ran. See
  [`tar-helper-guard-20260925.md`](rust-cpython/experiments/tar-helper-guard-20260925.md).
- An optional canonical IPv4 Rust scan under public `ipaddress` calls improved
  five complete mixed IPv4/IPv6 routing-task pairs by a median 9.77% wall and
  0.08 s kernel CPU per process on macOS. All output digests matched; paired
  peak RSS and footprint changed in both directions. The guard preserves
  ordinary `_parse_octet` descriptor replacements and sends malformed inputs
  through Python. Focused semantic checks and Linux measurements remain open,
  so keep `--ipv4-scan` opt-in and count it as partial coverage. See
  [`ipaddress-v4-scan-20260925.md`](rust-cpython/experiments/ipaddress-v4-scan-20260925.md).
- An optional one-shot split routes only public `zlib.decompress` to Rust.
  Five complete-process pairs reduced sustained direct decode wall/CPU by
  36.6%/38.4%, while source-tar, gzip, and streaming remained within self-noise.
  Seven further pairs on a synthetic SQLite task with many small, highly
  compressible BLOBs reduced wall/CPU by 10.8%/10.9%. Seven pairs on a
  mixed-compressibility SQLite task instead raised wall/CPU by 8.4%/9.0%,
  beyond self-noise. That breadth regression blocks general promotion; the
  extension also adds 1.59 MB unstripped, and memory readings do not
  establish parity. See
  [`zlib-oneshot-comparison-20260925.md`](rust-cpython/experiments/zlib-oneshot-comparison-20260925.md)
  and [`zlib-oneshot-mixedblobs-20260925.md`](rust-cpython/experiments/zlib-oneshot-mixedblobs-20260925.md).
  The link-size audit found many unused exported Rust entry points but
  defers a dead-strip experiment until the mixed-input regression is fixed;
  see [`zlib-oneshot-size-feasibility-20260925.md`](rust-cpython/experiments/zlib-oneshot-size-feasibility-20260925.md).
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
  [`tomllib-boundary-20260925.md`](rust-cpython/experiments/tomllib-boundary-20260925.md)
  report narrows a possible guarded boundary and defers a native parser until
  a representative complete metadata task justifies its cost.
- The three pinned macOS Django wheel metadata records are parsed during host
  benchmark setup, before either compared interpreter starts. The currently
  admitted macOS tasks have no substantial `importlib.metadata` inventory;
  defer an email-parser proof until a real measured caller is pinned.
- A package-free catalog export workload now checks one complete 512-record,
  259,349-byte JSON document per operation. The pinned interpreter completed
  300 exports in 1.33 process CPU seconds. A separate instrumented profile
  found many `json.dumps`/`json.loads` calls, but their ordinary paths already
  use `_json`'s C encoder and scanner. The application repeatedly encodes and
  decodes each record before its final array encode, so defer a Rust JSON
  kernel pending evidence of C-level headroom. See
  [`catalog-json-workload-20260924.md`](rust-cpython/experiments/catalog-json-workload-20260924.md)
  and [`catalog-json-profile-20260924.md`](rust-cpython/experiments/catalog-json-profile-20260924.md).
  A repeat profile on the accepted fork control reached the same conclusion;
  see [`json-headroom-20260925.md`](rust-cpython/experiments/json-headroom-20260925.md).
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
- Against the matched upstream 3.16 build, five complete catalog pairs had
  19.0% less wall time and 19.2% less root CPU. Three separate peak-RSS pairs
  had mixed signs and a +49,152-byte median inside measured self-noise; one
  pair was higher than the candidate's memory-noise allowance. The fork and
  upstream have different ancestry and PGO profiles, and macOS unique memory,
  PSS, and allocations remain unavailable. Keep the patch speed-qualified,
  with resource acceptance open; see
  [`url-quote-upstream-comparison-20260924.md`](rust-cpython/experiments/url-quote-upstream-comparison-20260924.md).
- Two further complete URL tasks reuse the catalog inputs: outbound search
  forms and request-path canonicalization. Against the prior fork build,
  five-pair wall/CPU medians improved by about 14% and 4–5% respectively;
  upstream comparisons had the same direction. All complete digests and the
  200,000-byte fallback boundary passed. Initial request-path peak RSS was
  about 0.25–0.49 MB higher; one upstream pair exceeded the candidate noise
  allowance. Fresh-import timing was too noisy for a verdict. See
  [`url-quote-breadth-comparison-20260924.md`](rust-cpython/experiments/url-quote-breadth-comparison-20260924.md).
- A ten-pair request-path memory follow-up with byte-identical child checker
  code had a −8,192-byte candidate/control median and did not reproduce that
  RSS direction. The earlier checker difference is a likely confounder, not
  proven causation. Fresh `urllib.parse` import used about 0.594 ms more
  process CPU per run across batched fresh processes; wall time remained
  inconclusive and peak RSS was within self-noise. See
  [`url-quote-memory-followup-20260924.md`](rust-cpython/experiments/url-quote-memory-followup-20260924.md).
- A same-executable lazy extension-import overlay preserved 2,177 public
  cases and unchanged URL tests, but fresh-import speed stayed within
  self-comparison noise and request-path peak RSS rose in three small paired
  runs. The overlay also delays a missing-extension failure until first use.
  Keep the eager source patch; see
  [`url-quote-lazy-import-20260924.md`](rust-cpython/experiments/url-quote-lazy-import-20260924.md).
- On that installed quote candidate, public `unquote` had 182 eligible
  escaped calls per complete 48-record search-form batch. A bounded Rust
  decoder proof, compared with a same-compiler quote-only extension, reduced
  complete search-form wall time by 43.6% and kernel CPU by 44.7% across
  five pairs with exact output digests. The extension added 368 bytes.
  Full-tree and bytecode-cache audits isolated the parser source/cache and
  extension; broad public semantic behavior and upstream memory remain
  unqualified. See
  [`url-unquote-headroom-20260925.md`](rust-cpython/experiments/url-unquote-headroom-20260925.md)
  and [`url-unquote-proof-20260925.md`](rust-cpython/experiments/url-unquote-proof-20260925.md).
- The decoder proof is now a digest-checked optional `build --url-unquote`
  source patch. Fresh verified source selections differed only in the parser,
  C wrapper, and Rust byte scanner; the default build remains quote-only.
  At source-selection time, the full build and broad public semantic checks
  remained open. The
  eligible path bypasses lazy initialization and replacement of private
  parser globals. A follow-up source trace found that both exact UTF-8 paths
  reach the same built-in decoder; public differential behavior still needs
  checking. See
  [`url-unquote-source-patch-20260925.md`](rust-cpython/experiments/url-unquote-source-patch-20260925.md)
  and [`url-unquote-contract-audit-20260925.md`](rust-cpython/experiments/url-unquote-contract-audit-20260925.md).
- The fresh opt-in native build succeeded with the locked LLVM, SDK, and PGO
  recipe. Its installed parser matches the selected source, its extension
  exports the Rust decoder, and both complete catalog URL output digests
  matched. The build consumed 802.40 kernel CPU seconds and peaked at 1.79 GB
  reported process RSS with no swaps. A separate serial installed-tree
  performance comparison and broad semantic qualification remain open. See
  [`url-unquote-build-20260925.md`](rust-cpython/experiments/url-unquote-build-20260925.md).
  After the Linux lane merge, the revised cross-platform quote patch plus
  optional unquote patch also completed a fresh macOS LLVM/PGO build. The
  installed parser bytes still match; see
  [`merged-macos-url-build-20260925.md`](rust-cpython/experiments/merged-macos-url-build-20260925.md).
- Five serial installed-tree search-form pairs then showed 42.9% lower
  complete-process wall time and 44.0% lower kernel CPU with exact output
  digests. The control/control wall variation reached 2.6%. The normalization
  task's 2.6% wall change is too small to attribute across different PGO
  builds. The same-executable decoder proof remains the cleaner attribution;
  this comparison shows the gain survives the reproducible opt-in build. See
  [`url-unquote-installed-comparison-20260925.md`](rust-cpython/experiments/url-unquote-installed-comparison-20260925.md).
- The merged Linux/macOS builder's fresh quote-only and optional-unquote
  macOS stages repeated the search-form benefit across five pairs: 42.29%
  less full-process wall and 42.84% less kernel CPU. Separate memory pairs
  changed sign, and the two independent PGO profiles limit attribution.
  Normalization had a small directional gain; request paths showed no clear
  change. See
  [`merged-macos-url-comparison-20260925.md`](rust-cpython/experiments/merged-macos-url-comparison-20260925.md).
- A separate three-way resource pass compared the fresh decoder, quote-only
  fork, and vanilla upstream on the complete search task. Decoder minus
  upstream median root peak RSS was -114,688 bytes, with every pair inside
  upstream self-noise; sampled physical footprint was 180,224 bytes lower at
  the paired median. The pass found no RSS regression on this workload, but
  it cannot qualify USS/PSS, allocations, or retained memory. See
  [`url-unquote-upstream-memory-20260925.md`](rust-cpython/experiments/url-unquote-upstream-memory-20260925.md).
- The complete search-form task then ran with decoder/upstream median wall
  and kernel CPU ratios of 0.504 and 0.492 across five pairs. Quote-only fork
  ratios were 0.841 and 0.841. All 60 self and cross attempts returned the
  same complete digests. This is an installed-artifact improvement; differing
  fork ancestry and PGO profiles limit attribution to the decoder. See
  [`url-unquote-upstream-speed-20260925.md`](rust-cpython/experiments/url-unquote-upstream-speed-20260925.md).
- On the new decoder build, complete search and normalization profiles found
  no convincing further URL kernel. The largest remaining individual parser
  self-time row was `quote_from_bytes` at 7.5% and 8.6% of instrumented time,
  including existing native calls and fast exits. Defer another URL port and
  find a representative `tomllib` application task before implementation;
  see [`url-residual-profile-20260925.md`](rust-cpython/experiments/url-residual-profile-20260925.md).
- The pinned CPython `stable_abi.py --dump` tooling command reads a real
  72,592-byte TOML manifest three times. `tomllib` Python frames occupied
  53.4% of its instrumented complete-task self time, but the direct command
  used only 0.07 kernel CPU seconds. Current approved inputs lack a substantial
  application metadata task, so defer a broad Rust TOML parser until one is
  pinned and profiled. See
  [`tomllib-workload-scout-20260925.md`](rust-cpython/experiments/tomllib-workload-scout-20260925.md).
- The real pinned CPython source `.tar.gz` read spends 43.23–43.27 ms of a
  581 ms instrumented task in two TAR header checksum conventions across
  6,540 calls. The 7.4% instrumented share identified a narrow boundary; it
  did not predict the uninstrumented speed gain. Full header/PAX replacement
  remains deferred. See
  [`tarfile-boundary-scout-20260925.md`](rust-cpython/experiments/tarfile-boundary-scout-20260925.md).
- A new cold Django WSGI first-request workload includes process startup,
  Django setup, the first read-only SQLite open, and one checked response.
  Seven serial standard-profile controller runs compared that workload and
  the warm WSGI request against the prior fork. Neither showed a wall or CPU
  change beyond same-interpreter noise. A cold candidate RSS increase exceeded
  noise in one host-load pilot, but the quieter repeat was within noise;
  upstream memory parity remains open. See
  [`django-cold-comparison-20260925.md`](rust-cpython/experiments/django-cold-comparison-20260925.md).
- A one-shot `difflib.unified_diff` snapshot and exact-string scan proxy added
  4.7% root CPU per mostly-equal complete diff and 9.6% per reordered diff.
  Its peak-RSS deltas were within measured self-noise after equalizing child
  entry points. This cost alone does not rule out a native kernel; public
  monkeypatch, generator, and reentrancy behavior still need a sound route.
  See [`difflib-snapshot-cost-20260924.md`](rust-cpython/experiments/difflib-snapshot-cost-20260924.md).
- A pinned-interpreter dispatch probe found an exact `list[str]` mutation
  during `find_longest_match` that changes the emitted diff. A one-shot native
  snapshot would miss it; identity/type guards cannot exclude all callbacks
  and reentrancy under the unchanged public contract. Stop the proposed
  transparent `unified_diff` kernel; see
  [`difflib-one-shot-contract-20260924.md`](rust-cpython/experiments/difflib-one-shot-contract-20260924.md).
- A source and workload scout identified `ZipFile._RealGetContents` as a
  possible directory-parsing cost. The wheel task also extracts and checks
  member data; cold ZIP import uses a separate directory reader. See
  [`zipfile-headroom-20260925.md`](rust-cpython/experiments/zipfile-headroom-20260925.md).
- A warmed complete-wheel profile put that directory reader at 10.0% of
  instrumented task time, down from 18.6% when first-use codec loading was
  included. Seven longer control/control pairs had at most 0.89% wall and
  1.79% kernel-CPU differences. The possible gain is resolvable but capped,
  while arbitrary file-like inputs and replaceable Python objects make a
  transparent native parser costly. Defer it pending stronger application
  headroom; see
  [`zipfile-profile-20260925.md`](rust-cpython/experiments/zipfile-profile-20260925.md)
  and [`zipfile-baseline-20260925.md`](rust-cpython/experiments/zipfile-baseline-20260925.md).

- The x86_64 Linux lane builds the candidate, unpatched fork, no-Rust fork,
  vanilla upstream, zlib hybrid, and full zlib-rs offline in about five
  minutes each. Bring-up found and fixed four portability defects: the URL
  patch lacked its `SRCDIRS` entry, a fork cargo rule destroyed `$ORIGIN`,
  an inherited ignored SIGINT failed the PGO task, and host proxy variables
  leaked into tests. The candidate passed 2,177 URL differential cases, the
  unchanged URL tests, and the Cargo and targeted suites. The broad
  regression run (50,567 tests) failed only in `test_socket`, on vsock
  errors that vanilla upstream shares on this host. `_decimal` is absent on
  Linux because the 3.16 sources no longer bundle libmpdec. See
  [`linux-lane-bringup-20260925.md`](rust-cpython/experiments/linux-lane-bringup-20260925.md).
- On Linux, the URL patch cut `catalog_url_normalize` process CPU by 12.3%
  against the unpatched fork and 12.7% against upstream (95% intervals
  exclude no-change). `catalog_search_form` and `catalog_request_path`
  improved 6.3% and 3.5% against upstream. Peak USS/PSS differences
  (±0.06 MB) stayed within same-interpreter bias. The zlib hybrid matched
  876/876 encodings and the focused zlib tests. On a sustained public
  decode pass it cut process CPU by 38–40% for zlib and 13% for gzip, but
  added a steady +1.0 MB of USS/PSS. That is almost entirely clean private
  pages of its 1.8 MB larger extension, which still carries unused deflate
  code. See
  [`linux-comparison-20260925.md`](rust-cpython/experiments/linux-comparison-20260925.md).

## Immediate work queue

- **The optional zlib-rs build is an experiment, not a production migration.**
  The ordinary lane build still links `Modules/zlibmodule.c` to platform zlib.
  The decompression-only hybrid matched compressed bytes and focused tests.
  Against the closest platform-zlib fork control, short complete tasks had no
  established wall or process-CPU gain, while the longer public decode/gzip
  jobs now show roughly 35% lower wall and 36% lower CPU beyond self-noise.
  ZIP and sustained-job memory differences changed sign, and the extension
  added 1.45 MB after equal debug stripping. See
  [`zlib-hybrid-qualification-20260924.md`](rust-cpython/experiments/zlib-hybrid-qualification-20260924.md).
  The macOS sustained measurements are in
  [`zlib-sustained-20260925.md`](rust-cpython/experiments/zlib-sustained-20260925.md).
  A pinned source-tar read then exposed a 10.81% CPU regression, so the
  all-stream hybrid fails the important-workload gate. Linux sustained decode
  reduced CPU 38–40% for zlib and 13% for gzip, with +1.0 MB steady USS/PSS;
  this remains a speed and memory tradeoff. See
  [`source-tar-hybrid-20260925.md`](rust-cpython/experiments/source-tar-hybrid-20260925.md)
  and [`linux-comparison-20260925.md`](rust-cpython/experiments/linux-comparison-20260925.md).
  The built one-shot split avoids the regressing stream path and improved
  sustained direct decode, but a mixed-compressibility SQLite workload
  regressed wall and CPU by 8.4% and 9.0%. It cannot be promoted generally.
  Its module adds 1.59 MB unstripped; see
  [`zlib-oneshot-comparison-20260925.md`](rust-cpython/experiments/zlib-oneshot-comparison-20260925.md)
  and [`zlib-oneshot-mixedblobs-20260925.md`](rust-cpython/experiments/zlib-oneshot-mixedblobs-20260925.md).
  A separate `--zlib-adaptive` trial selects Rust for compressed inputs of
  at least 8 KiB and platform zlib below that cutoff. Matched-fork macOS
  builds and complete output checks succeeded. Five loaded-host pairs showed
  6.74% lower median CPU on combined 1 MiB direct decode and no median CPU
  change on mixed SQLite BLOBs; the cutoff gives up Rust gains on highly
  compressible inputs that remain small after compression. Keep it opt-in
  until quiet-host speed, memory, and broad semantic qualification. Its
  unstripped extension still costs about 1.59 MB. See
  [`zlib-adaptive-oneshot-20260925.md`](rust-cpython/experiments/zlib-adaptive-oneshot-20260925.md).
  A separate macOS-only `--zlib-adaptive-small` build kept the same adaptive
  source and Rust feature recipe while limiting the extension's exported
  symbols and stripping unreachable code at link time. The installed module
  passed the builder's import and round-trip checks. After equal stripping
  and signing, its size fell from 1,538,000 to 483,264 bytes, with a real
  code-section reduction. This is a size result, not quiet-host speed or
  memory qualification; the adaptive workload tradeoff remains open. See
  [`zlib-adaptive-small-link-20260925.md`](rust-cpython/experiments/zlib-adaptive-small-link-20260925.md).
- The optional TAR checksum source patch produced a repeatable macOS
  complete-archive speed and CPU gain with unchanged output. Its TAR-owned
  private extension now loads only when an eligible checksum is needed.
  A complete read-and-rewrite task also gained 11.87% wall and 12.05% kernel
  CPU with identical output. The added import-time guard handles ordinary
  Python-function checksum-helper replacements before import and retained a
  9.01% median read gain over quote-only. Keep it behind `--tar-checksum`
  while broader semantic and memory costs are qualified. It is useful
  coverage progress but does not yet complete the `tarfile` checklist item.
  See [`source-tar-rewrite-20260925.md`](rust-cpython/experiments/source-tar-rewrite-20260925.md)
  and [`tar-helper-guard-20260925.md`](rust-cpython/experiments/tar-helper-guard-20260925.md).
- The optional `ipaddress` IPv4 parser improved a complete mixed routing task
  beyond its local self-comparison, with matching public output. Keep it
  behind `--ipv4-scan` while focused behavior, other important workloads,
  and Linux/memory qualification are open. It does not complete the broader
  `ipaddress` coverage item, which also includes network-range operations.
  A follow-up complete-task profile put IPv4 integer formatting at no more
  than 4% of instrumented time. Larger network costs depend on replaceable
  public properties, so defer a second narrow network kernel.
  See [`ipaddress-v4-scan-20260925.md`](rust-cpython/experiments/ipaddress-v4-scan-20260925.md).
- The optional fixed-width numeric `datetime.strptime` path matched the
  complete 60,000-record log-ingest output in five macOS pairs. Median
  candidate/control wall and kernel CPU ratios were 0.641 and 0.613; median
  paired peak RSS changed by +32 KiB. Cold import was neutral. Keep
  `--strptime-numeric` opt-in because eligible calls bypass `_strptime` locale
  checks and regex-cache side effects. Broader semantic, memory, and Linux
  qualification remain open. See
  [`strptime-numeric-20260925.md`](rust-cpython/experiments/strptime-numeric-20260925.md).
- The optional canonical UUID text scanner reaches public `uuid.UUID` calls,
  but five complete 100,000-record index pairs showed no speed or CPU gain
  beyond control variation: median candidate/control ratios were 1.003 and
  1.000. Median paired peak RSS rose 376,832 bytes within local self-pair
  variation, and the new extension is 51,272 bytes. Retain
  `--uuid-canonical` for partial priority-0 coverage with this performance
  debt; it is not a performance promotion or a completed `uuid` port.
  Broader semantics and Linux resource costs remain open. See
  [`uuid-canonical-20260925.md`](rust-cpython/experiments/uuid-canonical-20260925.md).
- The optional default POSIX `shlex.split` scanner matched a complete
  25,264-call command-processing task, including its fallback cases and
  expected parse errors. Five macOS pairs improved median wall by 63.7%
  and kernel CPU by 67.2%; median paired peak RSS/footprint rose 256 KiB
  within self variation. Keep `--shlex-split` opt-in while broader semantic,
  memory, and Linux qualification remain open. Its 4,096-character ASCII
  cap bounds temporary storage; larger and nondefault calls use Python.
  This is partial priority-1 coverage, not a completed `shlex` port. See
  [`shlex-split-20260925.md`](rust-cpython/experiments/shlex-split-20260925.md).
- The optional `fractions.Fraction` scanner reaches public parsing of short
  canonical ASCII rational strings; Python still constructs and normalizes
  the value and handles all other inputs. A complete 200,000-record ledger
  matched control output. Five alternating pairs under unrelated heavy host
  load had median candidate/control wall and kernel CPU ratios of 0.927 and
  0.929, but nearby control drift reached 6.3% in wall time. Retain
  `--fraction-rational` for partial priority-1 coverage only. Clean-host
  speed, memory, broad semantics, and Linux qualification remain open. See
  [`fraction-rational-20260925.md`](rust-cpython/experiments/fraction-rational-20260925.md).
- The URL patch has targeted gains across three complete tasks, but no broad
  application-suite or upstream resource acceptance yet. The ranked entries
  in `rust-cpython/README.md` remain hypotheses, not completed ports.
- Establish the missing macOS unique/proportional memory and allocation
  measurements and matched upstream control comparison. The simple libproc
  region probe failed; any further USS/PSS work needs a different interface
  with proven page identity and coverage. Xcode Allocations export failed the
  requested-byte and child-attribution gates. The bounded malloc interposer
  is promising for diagnostics but needs API and process coverage before it
  can support an allocation verdict.
  Stop both the arbitrary public `difflib.SequenceMatcher` kernel and the
  one-shot `unified_diff` snapshot route under the unchanged behavior
  contract. The former exposes mutable matcher state; the latter changes
  trace-mediated mutation and callback timing. Their measured and semantic
  limits are in the difflib experiment records.
- The guarded URL patch is speed-qualified on three complete tasks. Its small
  fresh-import CPU cost remains visible; the tested lazy variant did not show
  a reliable benefit. The earlier request-path RSS increase did not repeat
  with identical checkers, while the lazy overlay showed a separate small
  directional RSS increase. Keep the eager patch as the current experiment.
  Unique/proportional memory and allocations remain unqualified even when
  paired RSS medians fall within noise. Extend to broader applications when
  compatible byte-pinned inputs exist. The separate `unquote` proof has a
  large search-form gain and a built opt-in source patch. Its fresh installed
  comparison repeated the gain; broad public semantic and upstream resource
  qualification remain open.
- The approved macOS CPython 3.16 Django benchmark lock now pins and verifies
  Django 6.1.1, asgiref 3.12.1, and sqlparse 0.6.0 without changing the
  product or Linux lock. See
  [`mac-cp316-django-inputs-20260924.md`](rust-cpython/experiments/mac-cp316-django-inputs-20260924.md).
  A true cold first-request workload now uses a fixed, byte-hashed SQLite
  fixture and spawn-to-exit timing; its same-interpreter correctness smoke
  passed. See
  [`django-cold-first-20260925.md`](rust-cpython/experiments/django-cold-first-20260925.md).
  The paired warm/cold comparison found no established URL-patch benefit for
  either WSGI request, with upstream memory parity still open. See
  [`django-cold-comparison-20260925.md`](rust-cpython/experiments/django-cold-comparison-20260925.md).
  A fresh matched quote-only versus optional unquote comparison also found no
  established cold or warm Django WSGI gain; its small CPU and RSS differences
  stayed within local variation. See
  [`merged-macos-url-django-20260925.md`](rust-cpython/experiments/merged-macos-url-django-20260925.md).
  Add baseline-derived loops for
  pyperformance and selected Pyston macros only with separately pinned inputs.

## Secondary goal: Rust stdlib coverage

Cover the core public operation named for every priority 0 module, then work
through priority 1. A checked item means normal public calls on at least one
native experimental target reach a maintained Rust implementation, the
specified behavior is preserved, and a complete application or stdlib
workload has measured its time, CPU, memory, and size cost. It does **not**
claim that every API in that module is written in Rust. State the covered API
and target in the result. A private extension that no public caller uses, or
a standalone kernel proof, does not complete an item. Keep partial work and
negative performance results as evidence and optimization backlog. The
checklist sets coverage value; measured bottlenecks still choose experiment
order within each priority.

The current `_base64` integration proof does not cover public `base64`; the
guarded URL quote route is a partial `urllib.parse` port pending broad
qualification; zlib, TAR, IPv4, numeric timestamp, UUID, `shlex`, and
`fractions` Rust proofs remain partial. No item below is yet marked complete.

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
