# Rust-for-CPython experiment lanes

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
