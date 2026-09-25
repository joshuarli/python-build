# One-shot zlib with mixed SQLite BLOBs, 2026-09-25

**Verdict: reject a general small-BLOB speed claim for the one-shot route.**
With 256 distinct payloads spanning repetitive through effectively random
content, candidate median complete-process wall time was **8.41% slower** and
kernel user + system CPU was **9.00% higher** in seven paired runs. Every
candidate pair regressed, while seven control/control pairs ranged from
−1.12% to +0.58% in wall time. This reverses the prior 10.83% gain on
highly compressible small BLOBs. The route may still suit a narrow
compressibility distribution; this result does not isolate which category
caused the regression.

## Task and identity

[`zlib_oneshot_mixedblobs.py`](zlib_oneshot_mixedblobs.py) seeded a read-only
SQLite fixture outside timing. It contains 64 distinct 1–4 KiB payloads in
each of four deterministic categories. The level-6 zlib compressed-size
distributions, in bytes, were:

| Category | Minimum | Median | Maximum |
| --- | ---: | ---: | ---: |
| Repetitive | 51 | 63 | 75 |
| Modest (alternating 128-byte fixed/random chunks) | 565 | 1,367 | 2,101 |
| Mostly random (one-eighth fixed) | 1,045 | 2,399 | 3,635 |
| Random | 1,055 | 2,605 | 4,101 |

Every timed process opened the same 561,152-byte fixture read-only, made 604
ordered scans, called public `zlib.decompress` once per row, and hashed the
row ID and every decoded byte. It processed 154,624 rows and 398,926,296
logical decoded bytes. Every calibrated and paired process returned SHA-256
`40fa20924c332b4304ea3b7f680c3b11fb692b3df14075901091744a33f38cc3`.
The fixture SHA-256 was
`dd3f25573c9307a466c9e1d374d698d242a3c7249fac691c18d5177ce891a2df`;
the workload source SHA-256 was
`d97b4a49ed5f23f859db26ddb6c86fea526cb08b89ed800cf5c6ad276fd551f7`.

The control interpreter SHA-256 was
`622ef6135d157b61254ebbce3778fb424a26d91d1fdc365a66d5fd19ba3797d6`
and its installed `zlib` extension SHA-256 was
`2aef4049da6abe4b4e6725f2f79f692ef8f8b3148aa87903a0d40cdef3ef50bd`.
Candidate values were
`a2f682948c50217a77393cc636ffaec1066fff1ee61da2eeba2102504f3a5296`
and `e2f9a02bffe3f7277e5766d29adfbb6ef316d3f412422918325baabecfd11a38`.
The staged interpreters are the same ones used for the prior small-BLOB
comparison. Their builds have distinct PGO profiles, which limits exact
attribution to the one-shot route.

Both arms used `PYTHONHASHSEED=1`, `PYTHONNOUSERSITE=1`,
`PYTHONMALLOC=default`, `PYTHONDONTWRITEBYTECODE=1`, and the same nonexistent
`PYTHONPYCACHEPREFIX`. Import audits found `__cached__ = null` for
`encodings`, `json`, `sqlite3`, and `hashlib` in both interpreters; the cache
prefix stayed absent. The `zlib` extension paths resolved to the staged
modules above. No inherited `PYTHONPATH`, `PYTHONHOME`, or `DYLD_*` was passed.
The host had ordinary UI and OrbStack activity, with load averages around
3–4 and 243.88 MiB swap allocated before and after; no compiler or other
benchmark was observed in the initial process check. Ordinary GC and ASLR
remained enabled.

## Paired results

The 100-scan control pilot set 604 scans; the control calibration took 0.899
seconds internally. Seven serial control/control pairs preceded seven
control/candidate pairs, with candidate first in alternating pairs.
`/usr/bin/time -l` recorded kernel CPU for each complete process, and an
external clock recorded spawn-to-exit wall. CPU counters resolve to 0.01
seconds. No sampler ran during timing.

| Measure per complete process | Control median | Candidate median | Candidate paired change | Control/control range |
| --- | ---: | ---: | ---: | ---: |
| External wall | 1.030 s | 1.114 s | +8.41% (+6.93% to +14.22%) | −1.12% to +0.58% |
| Kernel user + system CPU | 1.00 s | 1.09 s | +9.00% (+6.93% to +14.00%) | −1.00% to 0.00% |

The complete-process wall rates were about 2.58 ns and 2.79 ns per logical
decoded byte for control and candidate. Kernel CPU rates were about 2.51 ns
and 2.73 ns per byte. SQLite reads, row iteration, hashing, startup, and
JSON output are included, so this is an end-to-end task result rather than a
decompression-only measurement.

Three separate memory pairs showed candidate peak RSS changes of +245,760,
+114,688, and +851,968 bytes; peak physical-footprint changes were +147,456,
+16,384, and +753,664 bytes. Control/control RSS changes spanned −917,504 to
+835,584 bytes, so these readings do not establish a stable memory effect.
Physical footprint is macOS charged memory, not USS or PSS. No allocation or
interval memory sampler ran.

## Raw evidence and resource budget

[Raw evidence](data/zlib-oneshot-mixedblobs-20260925.json) retains all 39
successful attempts, exact commands and outputs, pair ordering, external
wall, kernel CPU, RSS, footprint, swaps, and unique raw-log paths under
ignored `rust-cpython/results/zlib-oneshot-mixedblobs-20260925/`. This includes
both import audits, fixture seed, pilot, calibration, 14 control/control
processes, 14 control/candidate processes, and six memory processes. All
paired outputs matched the calibrated digest and all process logs recorded
zero swaps.

The whole `/usr/bin/time -l` controller recorded **37.10 kernel CPU seconds**
(36.31 user + 0.79 system) and 37.73 seconds elapsed, below the 120-second
cap. Maximum reported process RSS was **35,979,264 bytes**, below 1 GiB;
controller and child swaps were zero. The controller measurement includes
its short-lived children; per-process RSS peaks are not a simultaneous
process-tree RSS total. Child CPU fields sum to 36.41 seconds; the difference
from the controller reflects its own work and 0.01-second counter resolution.

No test suite, formatter, linter, hook, push, build, dependency, or
production source edit was involved.
