# Rust-for-CPython experiment lanes

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
