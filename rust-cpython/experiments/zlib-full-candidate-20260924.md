# Clean whole-build zlib-rs: public-workload qualification

**Provisional verdict: keep the optional candidate for further qualification.**
The clean zlib-rs build preserved the checked output of all five public
decompression paths. One-shot zlib, streaming zlib, and gzip extraction were
clearly faster in this local run. ZIP read and cold ZIP import were within the
measured timing noise. Process-memory parity and allocation behavior remain
inconclusive on this macOS host; the candidate must not be promoted on this
evidence alone. In particular, ZIP read's median peak RSS rose 3.13 MB and
sampled physical footprint rose 5.18 MB, warranting a quiet-host repeat.

## Builds and measurement boundary

Control: `/Users/josh/d/python-build/rust-cpython/stage/bin/python3.16`,
platform zlib 1.2.12, executable SHA-256
`6eeeb64b9eb161d4d5edb9200e79146dabd8acc0f73fcdca48417d0e3c9531bd`.
Candidate: `/private/tmp/python-build-exp-zlib-build-20260924b/rust-cpython/stage/bin/python3.16`,
zlib-rs 0.6.7 runtime `1.3.0-zlib-rs-0.6.7`. Their source build reports are
`/Users/josh/d/python-build/rust-cpython/results/build.json` and
`/private/tmp/python-build-exp-zlib-build-20260924b/rust-cpython/results/build.json`.
Both report CPython source commit `b812b4a7b9efaca46b98544a8633b7d7e454166b`,
source archive SHA-256 `965dbc9c847b0ed779a16134495b8690c9fc957996d8bcbb83c47089d4e81467`,
Clang/LLVM 23.1.2 archive SHA-256
`d7c26fc6177e42842e2d1ffaad31aec057c56a924392b1a23d830abe2c5d53b1`,
nightly Rust 2026-09-15, Xcode 26.6 / SDK 26.5, Apple M1 baseline, macOS
26.0 deployment, `-O3`, ThinLTO, and `PROFILE_TASK="-m test --pgo -j 9"`.
Both are GIL-enabled CPython 3.16.0a0 with `cpython-316-darwin` extension ABI.
Their build paths differ. The retained merged PGO files
`rust-cpython/work/build/code.profclangd` differ too: control SHA-256
`a8e76452af8e624a41d19f06511e7a27ed1b1d3fb677bd1bea349e6fd868437e`,
candidate `b78352650078c1e882f2ccc3532ffa7d1d608446749cec98ee54a42852a9cc4c`.
The build reports do not record these profile hashes. Therefore compiled
differences are not exclusively attributable to zlib-rs. The installed control
`zlib` extension SHA-256 is `5612288b143dfa1130ef645f54f30cd701c1950419260326950b2a7395d60f07`;
the candidate's is `ae105fee7dddc3fa9001f3bfc0ad24af5be5061ebde4e85bb62ab2d9fc8b3a3e`.
The candidate retains platform `libz` for `binascii`, as its build report
checks. Both interpreters were read-only inputs.

The harness was the current `benchmarks/bench.py` from this worktree. Its
first self-comparison failed before a workload round because
`benchmarks/harness/process.py` referenced `shutil` without importing it.
After the coordinator repaired this on main, this worktree cherry-picked
commit `193a3d0` as `ee14c0b` and reran. The second attempt used an existing
output directory and stopped before a round; the completed run used a fresh
directory. Neither failed attempt contributes measurements. No other harness
or interpreter code changed in this lane.

This was a native macOS local diagnostic on a MacBookPro18,3, Apple M1 Pro,
macOS 26.5.2. Before measurement, the host had 356.38 MiB allocated swap;
it remained 356.38 MiB afterward. No compiler, PGO job, or benchmark process
was active at the serial run boundaries. WebKit and WindowServer each used
about 30% process CPU, with other desktop activity. One-minute load averages
recorded in the six run provenances ranged from 8.38 to 10.13 on ten logical
cores. This is not a quiet host, so near-noise results remain inconclusive.
The harness used five alternating control/candidate timing pairs, separate
external memory passes (three pairs, or five for cold ZIP import), 10 ms
sampling, and no allocation pass. The run was local, without network denial
or CPU affinity.

## Commands and resource budget

All commands ran from `/private/tmp/python-build-exp-zlib-qual-20260924c`.
The exact complete invocations and controller `/usr/bin/time -l` fields are
retained in the ignored `rust-cpython/results/zlib-full-*-time-20260924.txt`
files. The self-comparison invocation was:

```sh
/usr/bin/time -l python3 benchmarks/bench.py self-compare \
  --python /Users/josh/d/python-build/rust-cpython/stage/bin/python3.16 \
  --suite realworld --workload zlib_decode_1m --profile standard --local \
  --output /private/tmp/python-build-exp-zlib-qual-20260924c/rust-cpython/results/zlib-full-self-fixed-20260924
```

Each cross run substituted one name from the table below into this command:

```sh
/usr/bin/time -l python3 benchmarks/bench.py run \
  --baseline /Users/josh/d/python-build/rust-cpython/stage/bin/python3.16 \
  --candidate /private/tmp/python-build-exp-zlib-build-20260924b/rust-cpython/stage/bin/python3.16 \
  --baseline-label platform-zlib-control --candidate-label clean-zlib-rs \
  --baseline-kind custom --candidate-kind custom \
  --suite realworld --workload NAME --profile standard --local \
  --output /private/tmp/python-build-exp-zlib-qual-20260924c/rust-cpython/results/zlib-full-NAME-20260924
```

| Workload / command | Controller user + system CPU s | Elapsed s | Maximum process RSS MB | Swaps |
| --- | ---: | ---: | ---: | ---: |
| self `zlib_decode_1m` | 1.54 + 1.00 | 3.08 | 47.64 | 0 |
| `zlib_decode_1m` | 1.51 + 0.95 | 2.87 | 48.61 | 0 |
| `zlib_stream_4k` | 1.49 + 0.93 | 2.80 | 43.61 | 0 |
| `gzip_extract_1m` | 1.42 + 0.93 | 2.75 | 43.53 | 0 |
| `zip_read_wheel` | 1.50 + 0.98 | 2.88 | 44.07 | 0 |
| `zipimport_cold` | 2.79 + 1.79 | 5.40 | 43.97 | 0 |

The six completed commands used 16.83 process CPU seconds in total, far
below the 300-second budget, and their largest reported process RSS was
48.61 MB, below 2 GiB. `/usr/bin/time -l` reports the maximum RSS of a
waited process, not a simultaneous process-tree sum. It reported zero swaps
for every command. The two failed pre-round attempts used approximately
0.25 and 0.09 process CPU seconds, respectively.

## Public workloads

The fixed compressed input SHA-256 is
`d890765be28e2a1df58b1c67ddf0579416ebf4165e021fae6cffc13bfd68cba4`
for both zlib workloads,
`1de194e61a7ceece437084b2fae6152edf3c6258f9ff0854f05869524ba3d960`
for gzip,
`216b735da6639be9f3f2b60e2973ca8f41539161648b74d5547d68877a713df7`
for ZIP read, and
`8b14660fa9a0783095a7c28e4c0e05d24960d826de7516afab28e71597193a6a`
for cold ZIP import. Each workload validated its decoded content against a
fixed expected digest on both backends. The decoded digests, operation counts,
raw rounds, and sampled process data are committed in
`data/zlib-full-evidence-20260924.json`.

In self-comparison, the control/control paired median wall ratio was 1.030;
the harness's measured wall noise allowance was **13.79%**. The three memory
pairs gave median peak RSS 44.84 versus 44.65 MB, with a 5.68 MB noise
allowance. These are local control noise estimates, not a guarantee for all
workloads.

| Public workload | Wall ratio, candidate/control | Paired wall ratios | Wait4 user+system CPU/op change | Median peak RSS, control → candidate | Sampled footprint median, control → candidate |
| --- | ---: | --- | ---: | ---: | ---: |
| `zlib_decode_1m` | 0.492 | .475, .656, .492, .430, .652 | −4.2% | 43.55 → 38.73 MB | 30.51 → 19.22 MB |
| `zlib_stream_4k` | 0.644 | .663, .727, .644, .612, .640 | −1.3% | 37.29 → 35.59 MB | 19.58 → 22.33 MB |
| `gzip_extract_1m` | 0.573 | .573, .554, .594, .620, .530 | −3.4% | 32.60 → 33.33 MB | 19.02 → 15.30 MB |
| `zip_read_wheel` | 0.909 | .959, .894, .969, .909, .802 | +1.9% | 39.34 → 42.47 MB | 19.09 → 24.27 MB |
| `zipimport_cold` | 1.088 | 1.073, 1.158, 1.027, 1.088, 1.192 | +2.5%* | 46.96 → 46.74 MB | 23.58 → 23.38 MB |

Wall is the workload's internal elapsed time per equal logical work unit.
The `wait4` CPU column uses timing-pass user plus system seconds per operation
for the root process, whose startup and fixture setup dominate these very
short workloads. That is why the large hot-operation wall improvements
produce smaller whole-process CPU changes. For cold ZIP import (*), the
workload launches and reaps a fresh child interpreter per operation. The
outer harness's root `wait4` usage does not account for those child CPU
seconds. Its +2.5% value is a root-only diagnostic, not a complete process
CPU comparison. The sampler did observe two processes in all ten cold ZIP
memory rounds, but its 10 ms samples can miss short child peaks.

The separate memory passes retained raw time-stamped RSS and physical
footprint samples. Every memory round had samples and no sampling errors.
Across 395 samples, all RSS values were present and five footprint values
were null: one each in gzip, streaming zlib, and ZIP read, and two in cold
ZIP import. The non-cold workloads observed one
process; cold ZIP observed a maximum of two. The harness combines sampled
tree RSS with kernel root-family lifetime peak RSS. Sampled footprint is a
sequential tree estimate; the root lifetime footprint is recorded separately
in the raw evidence. For example, candidate decode's sampled median footprint
is 19.22 MB but its root lifetime footprint median is 25.48 MB, showing a
missed transient. USS, PSS, allocation counts/bytes, retained RSS, and swap
per workload are unavailable, never zero or passing. RSS counts shared pages,
and footprint is Apple's charged-memory ledger, not USS or PSS. The controller
marks every workload's memory verdict incomplete. No full CPython or Cargo
suite, new build, formatter, linter, hook, or push ran in this lane.
