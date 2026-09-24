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
2. Improve real application time, including startup/import and steady work.
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
`rust-cpython/work/source/` disappear on re-extraction. The current builder
extracts a fresh tree for each build and has no patch application step, so
adding a verified patch/overlay step is a prerequisite for a durable source
migration. Do not add a dependency,
change a source/toolchain pin, or expand product scope without an explicit
scope decision.

Use two separate controls. `rust-cpython/build_no_rust.py` builds the pinned
fork with Cargo disabled; it isolates the effect of Rust integration and can
help compare a replacement against the current C/Python path. A comparably
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
| Time | Serial, counterbalanced control/candidate pairs with equal logical work. No memory sampler, profiler, forced GC, or special allocator in the timed candidate. Keep ordinary GC, ASLR, and hash randomization. Use baseline-derived loop counts where supported. |
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

### Present measurement boundary

`benchmarks/` already provides paired timings, locked CPython 3.14 Linux
inputs, application macros, pyperformance, an external Linux process-tree
sampler, Memray passes, self-comparison, and noise-aware per-workload verdicts.
Native Apple Silicon currently supports timing only for a small local suite.
It cannot yet issue a memory or allocation pass for this macOS 3.16 lane.
The Linux wheel lock targets CPython 3.14 musl and must not be silently reused
for 3.16.

The next benchmark infrastructure work is native macOS process-memory
observation and a compatible allocation pass, followed by a matched upstream
3.16 control and compatible locked benchmark inputs. Keep workload definitions
interpreter-agnostic and record unsupported workloads rather than substituting
unmatched package versions for one interpreter. Focused timing and correctness
experiments may proceed while those gaps remain, with their limits stated
explicitly.

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

## Immediate work queue

- **The zlib proof is not a production migration.** The ordinary lane build
  still links `Modules/zlibmodule.c` to platform zlib; the Rust backend exists
  only in the separate proof overlay. Performance and compressed-byte
  comparisons remain open.
- No public stdlib API in the experiment has yet been shown to improve
  broadly in Rust. The ranked entries in `rust-cpython/README.md` remain
  candidates, not completed work.
- Establish the missing macOS resource measurements and matched upstream
  control, and add a reproducible source patch path. Profile the existing
  workload set for the first public API
  target. The `_base64` bulk slowdown and zlib backend are concrete
  hypotheses; select among them and the ranked candidates by measured
  end-to-end potential and compatibility cost.
