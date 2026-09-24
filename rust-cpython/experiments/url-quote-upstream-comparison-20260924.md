# Guarded URL quotation against matched upstream CPython

## Result

The installed guarded URL quotation fork completed the registered full
`catalog_url_normalize` workload faster than the shared-ancestry vanilla
upstream CPython 3.16 control. In five serial, counterbalanced 1,500-batch
pairs, the median candidate/upstream external wall ratio was **0.80954**
(19.0% less wall time), and the median root kernel user-plus-system CPU ratio
was **0.80796** (19.2% less CPU). Every child checked the full 48-URL and
48-key batch input/output digests, its installed parser and extension paths,
and the repository workload and fixture paths.

This is a useful, repeatable workload speed result against upstream, with
upstream and candidate timing self-noise allowances of 1.76% and 1.53%.
It is **not an upstream memory-parity pass**. The separate three-pair root
peak-RSS differences were +49,152, −163,840, and +475,136 bytes; the paired
median was +49,152 bytes, inside both self-comparison noise allowances.
The highest pair exceeds those allowances, while the direction changes
across pairs. Unique/proportional memory, PSS, compatible native/Python
allocation counts, and a steady retained-memory boundary are unavailable
here. Keep the patch as a speed-qualified experiment; leave the upstream
resource gate open.

The cross-build speed difference cannot be assigned to the URL patch alone.
The candidate is the later Rust-for-CPython fork, containing 35 intervening
fork commits and the existing `_base64` extension. Both builds used the
same configuration switches and optimization flags, but independent PGO runs
produced different merged profiles. The earlier same-executable,
cache-matched overlay comparison and prior-fork installed comparison support
the patch's speed direction independently; this run establishes the
upstream-facing workload result.

## Inputs and comparable boundaries

I APFS-cloned the upstream stage from
`/private/tmp/python-build-exp-upstream-20260924/rust-cpython/work/upstream-control/stage`
and the patched candidate stage from
`/private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage`
into this lane's ignored
`rust-cpython/work/url-quote-upstream-comparison-20260924/{control,candidate}`.
Neither source stage was changed. The upstream source is merge-base
`0983642c966d9c536416101e99b7d2b085483847`; the candidate is fork
`b812b4a7b9efaca46b98544a8633b7d7e454166b` plus the guarded source
patch. Both interpreters report CPython 3.16.0a0 and GIL-enabled release
ABI. Their common build switches include shared libpython, ThinLTO,
`--enable-optimizations`, no JIT or tail-call interpreter, and
`--without-ensurepip`. Both used LLVM 23.1.2, macOS 26 SDK, `-O3`,
`-mcpu=apple-m1`, deployment 26.0, and
`PROFILE_TASK="-m test --pgo -j 9"`. The upstream merged profile SHA-256
was `72af2df052926ea4a755e8ba2145c380c6e202ce7fa54ac13949262b16029245`;
the candidate's was
`7c065b61e6aad9afa2c8bf2fa49d7fbad3f5de847e149339a149066f987a51d9`.

Upstream `urllib/parse.py` SHA-256 is
`178fce6bb504b9e544ac22015778554234c63865d94374913f988bb731e0d825`,
byte-identical to the prior accepted fork parser. The patched candidate
parser is `85ac4db38a30e3b12dd78ff0a5b83baa61caedebc3a44c33cd45c85c3279acee`.
The catalog's other checked Python modules, `hashlib.py`,
`re/__init__.py`, and `pathlib/__init__.py`, are byte-identical across
these stages; installed `_hashlib` binary hashes differ. The candidate
alone has `_rust_url_quote` (51,288 bytes) and `_base64` (389,696 bytes).
The launchers and shared libpython have different hashes, consistent with
source ancestry and separately generated PGO code.

Each clone regenerated its own `urllib/parse.py` cache before measurement
using its own interpreter and checked-hash invalidation. Both cache headers
had CPython 3.16 magic and flags `3`, with source hashes
`fcbbd960190070b8` upstream and `fb86b91008046490` candidate.
Measured children set `PYTHONDONTWRITEBYTECODE=1`, fixed
`PYTHONHASHSEED=1`, default allocator, and the same repository
`PYTHONPATH`. The complete batch input SHA-256 was
`7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f`;
complete output SHA-256 was
`a6fedf33e0fd5e72b79af8d77499b9a7bb8e8d53491955f2e554570679e04941`
for all measured children. The script checked each measured `sys.prefix`,
`urllib.parse.__file__`, candidate extension `__file__`, workload module
path, and fixture path.

## Measurements

The host's one-minute load was 2.90 before the first self-comparison, 3.44
before the candidate retry, and about 3.5 before the paired pass. No compiler
or competing benchmark appeared in sampled `ps` preflights; the coordinator
confirmed no competing build or benchmark lane. OrbStack and desktop
processes remained active. The first candidate self-comparison reached
3.024% timing noise, just above the 3% gate, and was discarded. One bounded
retry reached 1.527%. Upstream self-comparison noise was 1.761%.

| Per 1,500 complete batches | Upstream median | Candidate median | Paired result |
| --- | ---: | ---: | ---: |
| External wall, no sampler | 0.690785 s | 0.559476 s | ratio 0.80954 |
| Root user + system CPU | 0.671984 s | 0.544239 s | ratio 0.80796 |
| Wall per batch | 0.4605 ms | 0.3730 ms | same paired ratio |
| Root CPU per batch | 0.4480 ms | 0.3628 ms | same paired ratio |
| Root lifetime peak RSS, separate pass | 26,755,072 B | 26,738,688 B | paired median +49,152 B |
| Sampled peak physical footprint, separate pass | 13,894,112 B | 13,812,216 B | paired median −32,744 B |

The five wall ratios were `0.80726, 0.82664, 0.80954, 0.82025, 0.80578`;
the five root total-CPU ratios were
`0.80796, 0.82165, 0.80756, 0.81260, 0.80429`. The three paired
peak-RSS deltas were `+49,152, −163,840, +475,136` bytes. The upstream
RSS self-noise allowance was 473,673 bytes and the candidate allowance
was 218,618 bytes. Sampled footprint deltas were
`−32,744, −245,736, +409,616` bytes; footprint is an Apple charged-dirty
ledger, not USS or PSS, and a 10 ms sampler can miss a brief peak.

The timing pass used external monotonic wall time and `wait4` root user and
system CPU. It had no sampler or profiler. The separate memory observer
counted one process in every memory run with no sampling errors, and the
workload source does not spawn children. Timing CPU is still recorded as
root-only coverage. The five retained `/usr/bin/time -l` controller records
(including the discarded self-comparison) sum to 40.31 user-plus-system CPU
seconds, with 28,213,248 bytes maximum per-process RSS and zero reported
swaps. **That 40.31-second total excludes an initial exploratory four-pass
run** before the import-path assertions were strengthened. Its
`/usr/bin/time -l` files and runner `wait4` rows were overwritten by the
final passes; no reliable CPU, peak-RSS, or swap totals remain for those four
commands, so total lane resource consumption cannot be stated. The
exploratory timing showed the same speed direction but is not used for the
verdict. The retained controller maximum RSS is not aggregate tree memory.

The original installed stage trees contain 304,743,592 upstream versus
305,040,274 candidate regular-file bytes, a **+296,682-byte** candidate
delta. That whole-tree comparison includes the fork's existing `_base64`,
the new URL extension, parser bytes, and binary/profile differences; it is
not a URL-patch-only size cost. The two native extensions together are
440,984 bytes in the candidate. The candidate shared libpython is 34,736
bytes smaller than upstream, and its launcher is 16 bytes smaller.

The compact [raw observations](data/url-quote-upstream-comparison-20260924.json)
retain per-child wall, CPU, RSS, footprint, process count, cache and binary
identities, recipe checks, the discarded calibration, and controller
resource accounting. Full controller output remains in this lane's ignored
work area. No formatter, linter, hook, or remote push ran.
