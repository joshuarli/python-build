# One-shot zlib public-workload comparison, 2026-09-25

**Verdict: retain as an experiment, without promotion.** The one-shot candidate
reduces complete `zlib_decode_1m` process wall time by 36.6% and kernel CPU by
38.4% against the accepted fork's platform-zlib control. `gzip_extract_1m`,
the real source-tar read, and `zlib_stream_4k` remain within control/self
noise. This removes the source-tar regression seen with the all-stream hybrid,
while preserving a direct one-shot gain. Three memory pairs per selected task
change sign and do not establish memory parity. This is a matched-fork
comparison, not an upstream CPython acceptance claim.

## Identity and controls

The control interpreter is
`/private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage/bin/python3.16`;
the one-shot candidate is
`/private/tmp/python-build-exp-zlib-oneshot-build-20260925a/rust-cpython/stage/bin/python3.16`.
Before measurement, their SHA-256 values were respectively
`622ef6135d157b61254ebbce3778fb424a26d91d1fdc365a66d5fd19ba3797d6`
and `a2f682948c50217a77393cc636ffaec1066fff1ee61da2eeba2102504f3a5296`.
The installed `zlib` extension hashes were
`2aef4049da6abe4b4e6725f2f79f692ef8f8b3148aa87903a0d40cdef3ef50bd`
and `e2f9a02bffe3f7277e5766d29adfbb6ef316d3f412422918325baabecfd11a38`.
The candidate defines prefixed Rust init/inflate/end symbols, while its
unprefixed inflate references remain unresolved platform imports, consistent
with the one-shot route. The builds have distinct PGO profiles, limiting
fine-grained attribution.

Both arms used `PYTHONHASHSEED=1`, `PYTHONNOUSERSITE=1`,
`PYTHONMALLOC=default`, `PYTHONDONTWRITEBYTECODE=1`, and the same nonexistent
`PYTHONPYCACHEPREFIX` inside the lane. In both import audits, every inspected
source module's `__cached__` path pointed under that prefix; it stayed absent
through all attempts. Thus both arms compiled source on import rather than
reading their different installed caches. No inherited `PYTHONPATH` or
`DYLD_*` was passed. Ordinary GC and ASLR remained enabled. A host preflight
found no compiler or competing benchmark; background UI and OrbStack activity
remained. Timing ran serially with no sampler.

The pinned source archive was copied read-only into lane scratch and verified
at 44,210,863 bytes and SHA-256
`965dbc9c847b0ed779a16134495b8690c9fc957996d8bcbb83c47089d4e81467`.
The same public-workload files ran on both interpreters. `zlib_stream_4k` used
1,598 iterations from a 400-iteration control pilot; the other counts were
1,707 decode, 2,700 gzip, and three archive passes. Control internal work was
0.697, 0.774, 0.991, and 0.938 seconds respectively. Pilots and audits are
retained in the raw record.

## Five serial pairs per workload

Five control/control pairs preceded five counterbalanced control/candidate
pairs for each complete task. `/usr/bin/time -l` captured kernel user and
system CPU, lifetime maximum RSS, footprint, and swaps for every direct
workload process. An external clock around process spawn and exit captured
full-process wall. Internal task timers are separate. All 98 attempts exited
successfully; each workload process had no descendants. Differences are
candidate minus its paired control. Values per byte count decoded or
extracted logical bytes, including repeated operations.

| Workload and logical bytes/process | Control wall / CPU ns per byte | Paired wall change median (range) | Paired CPU change median (range) | Control/control wall range |
| --- | ---: | ---: | ---: | ---: |
| `zlib_decode_1m`, 3,579,838,464 | 0.250 / 0.240 | −36.61% (−37.00 to −35.93%) | −38.37% (−39.08 to −37.21%) | −1.24 to +0.41% |
| `source_tar_hybrid`, 408,192,093 | 2.797 / 2.719 | −0.65% (−1.08 to +0.28%) | 0% (−0.90 to 0%) | −0.69 to +0.28% |
| `gzip_extract_1m`, 2,831,155,200 | 0.341 / 0.332 | +0.62% (+0.10 to +1.00%) | 0% (−1.05 to 0%) | −0.85 to +1.16% |
| `zlib_stream_4k`, 3,351,248,896 | 0.342 / 0.328 | +0.76% (−0.19 to +1.11%) | +0.91% (0 to +1.82%) | +0.12 to +1.85% |

The corresponding median candidate wall/CPU rates were 0.158/0.148,
2.791/2.719, 0.344/0.332, and 0.343/0.334 ns per byte in table order.
The internal timer's paired median changed −47.17%, −0.59%, +0.21%, and
+0.80%. CPU counters have 0.01-second resolution, so small CPU differences
are quantized. The non-decode results overlap self noise; they support no
directional performance claim.

Every decode and stream result had compressed-input digest
`d890765be28e2a1df58b1c67ddf0579416ebf4165e021fae6cffc13bfd68cba4`
and decoded-content digest
`a316f38cceaae9765acdb3de5b4a4ca9d59be014d03d053c10002baa3dad51fb`.
Gzip's input/output pair was
`1de194e61a7ceece437084b2fae6152edf3c6258f9ff0854f05869524ba3d960` /
`6eb307fbef685d28bb65e832fe7c3601720b61272f303e9f66f816f55ef89055`.
Each source-tar process saw 6,539 members, 6,031 regular files, 136,064,031
regular-file bytes per pass, and digest
`4274d870abacbefea6bbdb2175de8b4073198e1fd39f34ede1c065b3faf1a805`.

## Memory, size, and resource coverage

A separate three-pair pass for decode and source-tar used the same complete
workloads and `/usr/bin/time -l` lifetime root maxima. These instrumented
attempts are excluded from timing verdicts. Candidate-minus-control peak RSS
differences were +294,912, +1,490,944, and −2,736,128 bytes for decode;
−311,296, −212,992, and +262,144 bytes for source-tar. Peak physical
footprint differences were +163,840, +1,359,872, and −2,867,200 bytes for
decode; −311,296, −212,992, and +262,144 bytes for source-tar. These
three-pair sign-changing readings cannot qualify upstream memory parity;
physical footprint is macOS charged memory, not USS or PSS. There was no
external interval sampler or allocation pass.

The installed unstripped `zlib` extension is 82,760 bytes on the control and
1,676,056 bytes on the candidate, an increase of 1,593,296 bytes. This is
an installed-extension comparison, not a packaged-product size claim.

[Raw evidence](data/zlib-oneshot-comparison-20260925.json) indexes every
command, output, paired observation, and unique stdout/resource log under
ignored `rust-cpython/results/zlib-oneshot-comparison-20260925/`. The
`/usr/bin/time -l` controller covered all 98 child attempts and reported
92.64 user + 2.43 system = **95.07 kernel CPU seconds** and 96.72 seconds
elapsed, below the 180-second budget. Its maximum process RSS was
60,243,968 bytes, below 1 GiB, and it recorded zero swaps. Per-attempt
rounded CPU summed to 93.18 seconds; the controller total also includes
runner work and avoids summing rounded counters. `/usr/bin/time -l` maximum
RSS is a per-process maximum, not simultaneous tree RSS. No test suite,
formatter, linter, hook, push, or production source edit was involved.
