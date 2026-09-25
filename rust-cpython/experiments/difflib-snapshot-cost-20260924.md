# `difflib.unified_diff` one-shot snapshot cost, 2026-09-24

## Decision

**The tuple snapshot and exact-string scan cost alone does not rule out a
one-shot native matching trial.** With the same child driver on both sides,
the added root CPU is about 23.4 microseconds per mostly-equal complete diff
(4.7% of control) and 18.1 microseconds per reordered complete diff (9.6%).
The reordered wall penalty is also above local self-noise. The mostly-equal
wall penalty is below one early cold control self-comparison outlier, so its
wall magnitude is less certain. No material peak-memory penalty is resolved
above local self-noise. This is a cost bound for extra Python work beside the
existing matcher, **not** a native speed estimate or approval of the
one-shot dispatch contract.

Before a kernel, specify how the internal one-shot route preserves the
generator's lazy evaluation and public monkeypatch points
(`SequenceMatcher`, its methods, `Match`, and `unified_diff`), plus mutation
or reentrancy during matching and rendering. The visible-state audit in
`difflib-guard-audit-20260924.md` still rules out the public matcher-level
kernel under a cheap guard. A native trial would also need a meaningful
gain in both full tasks, unchanged public behavior, and a separate upstream
resource gate.

## Setup and verification

- Base: `4cf97ba84a97cabcdb928cd0362f64384e8b44b8`; accepted fork stage
  from `/Users/josh/d/python-build/rust-cpython/stage`, copied twice with
  `cp -cR` into ignored `rust-cpython/work/difflib-snapshot-cost/`. The two
  installed `bin/python3.16` files have SHA-256
  `6eeeb64b9eb161d4d5edb9200e79146dabd8acc0f73fcdca48417d0e3c9531bd`;
  both `Lib/difflib.py` files have SHA-256
  `3a5bb23205537cd9a2a68255b4ca00d710573e0a18129b0166351bf126875cf3`.
  Both checked-hash `difflib.cpython-316.pyc` files have SHA-256
  `753894d57bff7bcbffb277d3bf932f6a2315b0375229dc9386bad6a1fd99e394`;
  their stored hash matched `importlib.util.source_hash()` of the copied
  source. No stage source, benchmark workload, or tracked build input changed.
- Host: macOS 26.5.2 (25F84), Apple M1 Pro, arm64. Swap remained 243.88 MB
  before and after. No compiler or PGO process was seen. The host had
  background OrbStack and system activity; paired order and self runs bound
  its observed effect. Both children use the same installed executable
  bytes, `PYTHONPATH` pointing at this worktree, `PYTHONHASHSEED=1`,
  `PYTHONNOUSERSITE=1`, `PYTHONDONTWRITEBYTECODE=1`, and default allocator.
- The [reproducible probe](difflib_snapshot_probe.py) calls the registered
  `benchmarks.workloads.difflib` function unchanged in both arms. The same
  child script defines the proxy wrapper in both arms; the proxy arm alone
  installs it on `difflib.unified_diff`. Once per complete diff, the wrapper
  makes `tuple(a)`, `tuple(b)`, scans *every* element with `type(item) is str`,
  then invokes the original generator with the original inputs and arguments.
  It does no native work. The controls do not wrap the call. Counts are the
  registered 500 mostly-equal and 1,000 reordered diffs; control intervals
  were about 0.20–0.26 seconds and gave stable root CPU measurements.
- Every child completed its expected operation count. Proxy calls were
  exactly 500 or 1,000, scanning 511,500 or 792,000 elements respectively;
  control wrapper calls were zero. All observations retained the pinned
  complete input/output digest pair: mostly-equal
  `25b83537c564e95a74f38ae2a79a710f92c832660a7c7e9f660b4a3dee2fe842` /
  `b5e86d88c7cad40f06a1ca79c7c2869a223315fdb30bdc7cd8940849414af2a3`;
  reordered
  `4534585365055d7f64ab4c2582f9dd14ae83bdd90055f920bdb7a35a7f0e20f3` /
  `26585b44b4a4ced0dbb5f717454d1cbc7fd290ad798a767f0de0ecd41497f7c8`.

## Paired results

The timing pass ran five serial, counterbalanced control/proxy pairs per
task, without a sampler. External wall includes process startup and imports;
kernel `wait4` user and system CPU covers the single workload root. Values
below are medians of paired proxy-minus-control differences divided by the
registered diff count. Relative percentages use the control median. The
raw pairs, including both CPU components and internal workload elapsed
time, are in [same-child raw data](data/difflib-snapshot-cost-20260924.json).

| Complete task | Extra external wall/diff | Extra root CPU/diff | Paired full-task wall differences | Paired full-task CPU differences |
| --- | ---: | ---: | --- | --- |
| Mostly equal (500) | 22.9 µs (4.4%) | 23.4 µs (4.7%) | +11.5, -1.7, +11.0, +29.2, +15.9 ms | +13.3, +7.2, +11.7, +15.3, +9.1 ms |
| Reordered (1,000) | 15.2 µs (7.5%) | 18.1 µs (9.6%) | +14.2, +13.1, +15.2, +19.6, +27.2 ms | +18.7, +18.8, +17.4, +17.3, +18.1 ms |

Two control/control calibration pairs per task gave maximum absolute
full-task wall differences of 32.2 ms (mostly equal; the first cold pair)
and 0.94 ms (reordered), and CPU differences of 8.47 and 3.62 ms.
Three proxy/proxy timing self pairs gave maximum absolute wall differences
of 5.21 and 5.18 ms, and CPU differences of 4.20 and 2.78 ms. Thus the
reordered penalty clears both timing self spreads; mostly-equal CPU clears
both CPU self spreads, while its wall delta does not clear the first cold
control spread. No statistical significance claim is made from these short
sequences.

The separate memory pass used five counterbalanced pairs per task and a
10-ms external process observer. `wait4` gives the root's kernel lifetime
peak RSS, and `proc_pid_rusage` gives its kernel lifetime peak physical
footprint; samples are retained in the raw file. Every observed tree had
one process and no sampling errors. Median paired RSS / footprint deltas
were +16 / +16 KB for mostly equal and +229 / +246 KB for reordered. Three
control/control memory self pairs had maximum absolute RSS spreads of
246 / 377 KB across the two tasks; three proxy/proxy self pairs had
66 / 131 KB. Both memory deltas are inside control self spread. Sampled
footprint and kernel peak footprint show the same direction and scale.
There is no macOS USS/PSS or allocation-count gate here, and no steady
retention boundary in these short processes.

## Discarded pilot and resource accounting

An initial 52-observation pilot used `-m benchmarks.workloads.difflib` for
control and a separate script entry point for proxy. Its apparent roughly
1.2 MB peak-RSS penalty includes different startup imports and is discarded
for attribution. All its valid digest-checked observations remain in
[pilot raw data](data/difflib-snapshot-cost-pilot-20260924.json). The
same-child rerun has 60 valid observations; the separate
[proxy self raw data](data/difflib-snapshot-cost-proxy-self-20260924.json)
has 24. A first controller invocation failed before spawning any child
because the script path omitted the repository root from `sys.path`; that
failure and every substantial `/usr/bin/time -l` command are preserved in
[command records](data/difflib-snapshot-cost-commands-20260924.json).

The three measured controller runs consumed 12.50, 14.50, and 6.08 seconds
of `/usr/bin/time` user+system CPU, including their children; the failed
launch consumed 0.04 seconds. Two copy commands consumed 2.20 and 2.18
seconds. Total recorded CPU was 37.50 seconds, below the approximately
120-second lane budget. The highest controller maximum RSS was 30.5 MB,
below 1 GB. The child root CPU sums in the raw files are diagnostic and
are included within the controller command totals, so they are not added
again. These tasks launch no descendants; the generic `wait4` counter is
root-only. The snapshot proxy adds work before returning the original
generator and cannot predict native index cost, output storage, dispatch
checks, or behavior under patched methods or reentrant mutation.
