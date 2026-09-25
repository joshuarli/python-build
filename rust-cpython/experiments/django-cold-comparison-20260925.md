# Paired Django WSGI first-request and warm-request comparison

## Result

The URL-patched CPython 3.16 stage shows **no established speed improvement**
on either Django WSGI workload against the prior Rust fork stage. Five serial,
counterbalanced timing pairs per run put both candidate/control ratios inside
the same-interpreter timing variation. One cold-request memory pass found a
+573,440-byte candidate peak-RSS increase beyond its local noise allowance;
the repeat found +163,840 bytes inside its allowance. The positive direction
is worth retaining, but these observations do not establish the size of a
cold-request memory regression. macOS whole-tree unique/proportional memory
and allocation counts remain unavailable, so memory parity is open.

| Run | Paired wall ratio | Paired root CPU ratio | Peak RSS median delta | Sampled footprint median delta |
| --- | ---: | ---: | ---: | ---: |
| Prior fork / itself, cold | 1.0718 | 1.0805 | +16,384 B | +16,384 B |
| URL stage / itself, cold | 0.9774 | 0.9770 | +49,152 B | +49,152 B |
| URL stage / prior fork, cold | 0.9867 | 0.9974 | +573,440 B | +475,136 B |
| URL stage / prior fork, cold repeat | 1.0495 | 1.0380 | +163,840 B | +81,944 B |
| Prior fork / itself, warm | 0.9740 | 1.0004 | -32,768 B | 0 B |
| URL stage / itself, warm | 0.9951 | 0.9987 | -180,224 B | -163,840 B |
| URL stage / prior fork, warm | 1.0086 | 1.0013 | +229,376 B | +163,840 B |

Ratios are medians of corresponding candidate/baseline pairs, where values
below 1 favor the candidate. CPU is kernel `wait4` user plus system time for
the workload root per request. The cold task's unit is a fresh process and
one complete first request; the warm task reports its internal request
interval per request, excluding setup and validation. Cold wall ratios of
0.9867 and 1.0495 are within the respective run's 8.22% and 16.03% timing
limits. The warm 1.0086 ratio is within its 10.64% limit; the separate
control and candidate self runs showed 9.18% and 6.81% limits. The first cold
RSS difference exceeded that run's 163,840-byte local allowance and the
control self-run's 300,324-byte allowance; the repeat was within its
364,364-byte allowance. The two candidate/control memory passes each used
three pairs of separate, externally observed processes.

## Matched inputs and boundaries

The baseline was `/Users/josh/d/python-build/rust-cpython/stage/bin/python3.16`
(executable SHA-256 `6eeeb64b9eb161d4d5edb9200e79146dabd8acc0f73fcdca48417d0e3c9531bd`).
The candidate was `/private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage/bin/python3.16`
(executable SHA-256 `622ef6135d157b61254ebbce3778fb424a26d91d1fdc365a66d5fd19ba3797d6`).
Both reported CPython 3.16.0, `cpython-316-darwin`, the same native macOS
target, ThinLTO, and PGO build policy. This is a prior-fork comparison, not an
upstream CPython comparison.

The macOS Django lock SHA-256 was
`a03a5cc754430152997a5ecd6a9d2c061a09890647e4595f33612e24d3626295`.
The cached wheel bytes matched its three entries: Django 6.1.1
`585fb82bf15053c42cf52e67c2f1b54a032dca384759315fd6678ab1870d1d72`,
asgiref 3.12.1
`fe386d1c2bff7259ea95929266d12a8cf9a8b5a1c2598402967d8792e7a7c094`,
and sqlparse 0.6.0
`b861c0288ce2fa56209a9a6412d2e066ac664b3873b89c26c9d8415e8e32996f`.
Each controller run prepared one shared site from these verified wheels and
precompiled it with the baseline outside the measured children. The workload
environment fixed `PYTHONHASHSEED=1`, disabled user sites and bytecode writes,
and used the same site path on both sides.

Both installed `urllib/parse.py` files had a valid checked-hash
`parse.cpython-316.pyc` before measurement. The baseline source and bytecode
SHA-256 values were `178fce6bb504b9e544ac22015778554234c63865d94374913f988bb731e0d825`
and `62e4d142ffc3008ac624aea6bc54575e0efce919efe3f465fdddceb9d24b6124`;
the candidate values were `85ac4db38a30e3b12dd78ff0a5b83baa61caedebc3a44c33cd45c85c3279acee`
and `5953842c30178f7269a4c94a854020b658b90bd37d3a5a2f862b4b96203365fd`.
Each pyc had magic `780e0d0a`, flags `3`, and a source-hash header matching
its own interpreter's `importlib.util.source_hash()` result (`fcbbd960190070b8`
for baseline, `fb86b91008046490` for candidate).

All seven runs produced the same full response digest,
`b609c04885f4c3ca00a0535939258e2f5595ee991874540da00d20f0d29806cf`.
The cold task's file-backed, read-only SQLite fixture was 3,919,872 bytes and
had SHA-256 `3257bc071d043b7d7a67b1f3fe4bf034fc44c73430a0d858abed09ccb2245a30`
before and after every run. The cold first request includes interpreter
startup, Django import/setup, handler creation, the file open, the request,
response validation, hashing, and process exit; fixture preparation and
full-file hashing happen outside its timer. The warm request keeps its
separate internal timing boundary.

## Resource ledger and limits

The host was an Apple M1 Pro with 10 logical cores, 32 GiB RAM, and macOS
26.5.2. Preflight showed 85% free memory, 243.88 MiB system swap already in
use, load about 5.2, and no active compiler or benchmark. An unrelated host
Python 3.13 process was observed after the first candidate/control cold run;
that run remains a pilot in the record. It exited before the warm comparison.
WindowServer, OrbStack, and browser activity continued, and the cold repeat
began at load 3.57. No benchmark commands overlapped. These local runs had no
offline network boundary.

`/usr/bin/time -l` measured each complete controller command, including its
reaped child processes. Its real time is not CPU time. It reported the
following user and system CPU seconds, controller maximum resident size, and
swap counts:

| Attempt | Real s | User s | System s | Max RSS MiB | Swaps |
| --- | ---: | ---: | ---: | ---: | ---: |
| `01-control-cold` | 13.37 | 6.18 | 5.39 | 72.8 | 0 |
| `02-control-warm` | 17.09 | 10.05 | 5.32 | 75.7 | 0 |
| `03-candidate-cold` (pilot) | 12.77 | 6.08 | 5.12 | 72.7 | 0 |
| `04-candidate-warm` | 16.13 | 9.77 | 4.93 | 75.5 | 0 |
| `05-candidate-self-cold` | 12.23 | 5.80 | 4.97 | 73.3 | 0 |
| `06-candidate-self-warm` | 16.06 | 9.76 | 4.92 | 75.7 | 0 |
| `07-candidate-cold-repeat` | 12.31 | 5.80 | 5.02 | 72.8 | 0 |

Total controller kernel CPU was **89.11 seconds**. The maximum controller
resident size was 79,396,864 bytes, below 1 GiB. Separate workload memory
passes observed one process on every round. Their peak RSS combines tree
sampling with the root's kernel lifetime peak; physical footprint is sampled
per PID and may miss transients. Workload `wait4` CPU covers the root only;
the sampled one-process count supports that boundary but does not prove no
short-lived child escaped observation. Per-process swap bytes, steady or
retained RSS, whole-tree unique/PSS, and allocations were unavailable, not
zero. Every command's raw process observations, correctness payloads,
provenance, and full `/usr/bin/time -l` output are retained in
[`data/django-cold-comparison-20260925.json`](data/django-cold-comparison-20260925.json).
The ignored result directories remain under
`rust-cpython/work/django-cold-comparison-20260925/`.

## Recommendation

Keep the URL patch's earlier focused speed evidence, but make no broader
Django performance or memory-parity claim from these runs. The cold RSS
direction deserves another memory comparison if the patch is promoted;
whole-tree unique memory and allocation attribution remain the larger open
qualification gaps.
