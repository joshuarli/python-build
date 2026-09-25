# One-shot zlib with small SQLite BLOBs, 2026-09-25

**Verdict: keep the one-shot route as an experiment.** On this synthetic
application task, its median complete-process wall time fell **10.83%** and
kernel user + system CPU fell **10.89%** in seven paired runs. Every candidate wall
result was faster than its paired control, outside the seven control/control
pair range of −1.38% to +1.51%. The earlier sustained 1 MiB decode gain was
larger (36.6% complete wall); this task gives evidence that the route also
helps many small public calls, but does not establish an upstream acceptance
case or memory parity.

## Task and identity

[`zlib_oneshot_smallblobs.py`](zlib_oneshot_smallblobs.py) seeds an SQLite
fixture outside measured processes. Its 256 rows contain distinct zlib streams
for decoded payloads of 1–4 KiB. The payload generator deliberately repeats
patterns; the compressed streams are only 190–219 bytes. This is a synthetic,
highly compressible workload, not an observed application data distribution.
Each timed process opens the same 65,536-byte fixture read-only, makes 1,075
ordered table scans, calls public `zlib.decompress` once per row, and hashes
the row ID and every decoded byte. It processes 275,200 rows and 710,009,550
logical decoded bytes. Every timed and memory process returned the same
SHA-256 digest,
`00f668bac63999a7a18f5b95be4b05d9f62bc05d7911dd12d096bf5a89f46402`.
The fixture SHA-256 was
`3d8ea9d0f3ed65175bf5c0602b26ab0b1c42bc33d0022474a46326b65cf3ae76`;
the workload source SHA-256 was
`63f1abc09d03ed3c0206da04c0b23972029fdce051eb1b263bdf5f337d7ea6be`.

Control and candidate were the same staged interpreters as the prior one-shot
comparison. Their executable SHA-256 values were respectively
`622ef6135d157b61254ebbce3778fb424a26d91d1fdc365a66d5fd19ba3797d6`
and `a2f682948c50217a77393cc636ffaec1066fff1ee61da2eeba2102504f3a5296`;
installed `zlib` extension SHA-256 values were
`2aef4049da6abe4b4e6725f2f79f692ef8f8b3148aa87903a0d40cdef3ef50bd`
and `e2f9a02bffe3f7277e5766d29adfbb6ef316d3f412422918325baabecfd11a38`.
The installed unstripped extension size increase remains 1,593,296 bytes.
The builds have distinct PGO profiles, so fine-grained attribution to this
route alone remains limited.

Both arms used `PYTHONHASHSEED=1`, `PYTHONNOUSERSITE=1`,
`PYTHONMALLOC=default`, `PYTHONDONTWRITEBYTECODE=1`, and the same nonexistent
`PYTHONPYCACHEPREFIX`. The import audits found `__cached__ = null` for
`encodings`, `json`, `sqlite3`, and `hashlib` on both sides; the cache prefix
stayed absent. The `zlib` extension paths resolved to the expected staged
modules. No inherited `PYTHONPATH`, `PYTHONHOME`, or `DYLD_*` was passed.
Background OrbStack and UI activity remained, with no competing compiler or
benchmark. Ordinary GC and ASLR remained enabled.

## Paired results

The 50-scan control pilot took 0.042 seconds internally. Calibration chose
1,075 scans; its control internal task time was 0.901 seconds. Seven serial
control/control pairs preceded seven control/candidate pairs, with candidate
first in alternating pairs. `/usr/bin/time -l` recorded kernel CPU for each
complete workload process; an external clock recorded spawn-to-exit wall.
No sampler ran during timing. CPU counters resolve to 0.01 seconds.

| Measure per complete process | Control median | Candidate median | Candidate paired change | Control/control range |
| --- | ---: | ---: | ---: | ---: |
| External wall | 1.036 s | 0.922 s | −10.83% (−11.40% to −9.92%) | −1.38% to +1.51% |
| Kernel user + system CPU | 1.01 s | 0.90 s | −10.89% (−11.88% to −10.00%) | −0.99% to +1.00% |

The wall rates were about 1.46 ns and 1.30 ns per logical decoded byte for
control and candidate. The corresponding kernel CPU rates were about 1.42 ns
and 1.27 ns per byte. SQLite reads, Python row iteration, hashing, startup,
and JSON output are included in complete-process measurements; the result
therefore represents this whole task rather than isolated decompression.

Three separate control/candidate pairs observed peak RSS changes of +327,680,
+16,384, and +262,144 bytes, and peak physical-footprint changes of +147,456,
−114,712, and +163,816 bytes. The signs and sizes are close to run variation;
these readings do not establish memory parity. Physical footprint is macOS
charged memory, not USS or PSS. There was no allocation or interval memory
sampler.

## Raw evidence and resource budget

[Raw evidence](data/zlib-oneshot-smallblobs-20260925.json) contains all 39
attempts, their commands, outputs, pair ordering, external wall, kernel CPU,
RSS, footprint, swaps, and unique raw-log paths under ignored
`rust-cpython/results/zlib-oneshot-smallblobs-20260925/`. All child attempts
exited successfully and recorded zero swaps. One controller attempt stopped
after the calibration pilots because its digest guard compared different scan
counts. Its raw log is retained; a second controller resumed with the chosen
count and completed all pairs. Across both `/usr/bin/time -l` controllers,
kernel process-tree CPU was **35.10 seconds** (34.39 user + 0.71 system),
below the 180-second cap. Maximum observed process RSS was **35,094,528
bytes**, below 1 GiB; controller and child swap counts were zero. The
maximum RSS is for one process, not simultaneous process-tree RSS. The first
controller took 1.58 seconds and the second 34.17 seconds of elapsed time.

No test suite, formatter, linter, hook, push, build, or production source edit
was involved.
