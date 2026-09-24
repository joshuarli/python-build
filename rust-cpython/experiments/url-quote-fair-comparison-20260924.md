# Cache-matched lean URL quotation comparison

## Decision

**Keep the lean guarded overlay as a source-patch candidate within the last
accepted Rust fork stage.** Five serial, counterbalanced pairs of the complete
public `catalog_url_normalize` task gave a median external wall ratio of
0.81324 (−18.7%) and a median root kernel CPU ratio of 0.81353 (−18.6%). Both
control/control and candidate/candidate timing self-calibrations passed the 3%
gate, with 2.05% and 1.90% allowances. The separate three-pair memory run had
mixed signs and a +131,072-byte paired median peak-RSS difference, within the
327,927-byte control and 169,160-byte candidate self-noise allowances. An
earlier, separately sampled three-pair memory diagnostic had a −65,536-byte
paired median. The previous multi-megabyte RSS rejection does not recur with
valid parser caches on both sides.

This is a same-stage overlay verdict, not a product or upstream-memory
qualification. macOS unique/proportional and allocation measurements remain
unavailable, and this lane made no reproducible CPython source patch. The next
action is to apply and qualify that patch, then compare against a suitably
matched upstream control before claiming upstream resource parity.

## Matched inputs and cache validity

I APFS-cloned `/Users/josh/d/python-build/rust-cpython/stage` independently
into ignored `rust-cpython/work/url-quote-fair-comparison-20260924/{control,candidate}`.
The stage, both cloned executables, and both original parsers were hash-checked.
Only the guarded parser and lean extension from the earlier proof overlay were
installed in the candidate. Source stage and proof overlay remained read-only.

| Item | SHA-256 or size |
| --- | --- |
| Source stage and both cloned `bin/python3.16` | `6eeeb64b9eb161d4d5edb9200e79146dabd8acc0f73fcdca48417d0e3c9531bd` |
| Source stage and control `urllib/parse.py` | `178fce6bb504b9e544ac22015778554234c63865d94374913f988bb731e0d825` |
| Candidate guarded `urllib/parse.py` | `8e29cff7399e7bae9e243bcc022afa43d73ad85912b9468b1e3cc73875079576` |
| Candidate `_rust_url_quote.cpython-316-darwin.so` | `74feaae8a1f52c735a61b94a4abe82daf2f65c4896434aca2b874200ce93a344`; 50,712 installed bytes |

Outside measured processes, **each clone's own interpreter** generated its
`urllib/__pycache__/parse.cpython-316.pyc` with checked-hash invalidation.
The pyc magic and flags `3` were verified; its header source hash matched
`importlib.util.source_hash()` of that clone's parser: control
`fcbbd960190070b8`, candidate `08e1c2739578432c`. The measurement
controller checked those headers and source hashes before each process. Every
workload child asserted its own `sys.prefix`, parser import path, and candidate
extension import path. `PYTHONDONTWRITEBYTECODE=1` then kept the cache state
fixed during measurement. No CPython, extension, or dependency compilation
occurred; parser pyc preparation was the only compilation.

All measured children completed 1,500 registered batches of 48 URLs and 48
stable keys. Every child checked input digest
`7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f`
and complete output digest
`a6fedf33e0fd5e72b79af8d77499b9a7bb8e8d53491955f2e554570679e04941`.
The earlier [lean proof](url-quote-lean-proof-20260924.md) supplies the 2,177
public differential cases and unchanged CPython URL-suite pass; this lane ran
no new semantic suite. Its host was native Apple Silicon macOS. The accepted
Rust fork stage includes its existing `_base64` integration; both sides here
used that same executable and stage contents.

## Serial timing and memory evidence

The first control self-calibration was **discarded for timing**: unrelated
`rustc` rose to about 477% CPU, the one-minute host load reached about 19.7,
and the measured timing-noise allowance was 28.53%. After compiler and heavy
Git activity cleared, the bounded control retry began around load 5.2;
candidate calibration began around 4.8; the matched timing run began around
5.5. Preflights found no compiler or benchmark competitor. OrbStack and normal
desktop processes remained active. No simultaneous workload processes ran.

| Pass | External wall median per 1,500 batches | Root CPU median per batch | Peak RSS median | Sampled footprint median |
| --- | ---: | ---: | ---: | ---: |
| Matched timing control | 0.71037 s | 0.46357 ms | — | — |
| Matched timing candidate | 0.57704 s | 0.37614 ms | — | — |
| Separate memory control | diagnostic only | diagnostic only | 26,394,624 B | 13,484,512 B |
| Separate memory candidate | diagnostic only | diagnostic only | 26,492,928 B | 13,566,432 B |

The five paired external wall ratios were `0.80697`, `0.81610`, `0.81230`,
`0.81324`, and `0.81865`; the corresponding root CPU ratios were `0.80202`,
`0.81369`, `0.81353`, `0.81396`, and `0.80881`. Each timing child ran without
a sampler. Three separate memory pairs, with a 10 ms external sampler, yielded
candidate-minus-control root lifetime peak RSS of `+131,072`, `−262,144`, and
`+229,376` bytes; sampled physical-footprint differences were `+114,688`,
`−278,528`, and `+196,608` bytes. The paired footprint median was +114,688
bytes. These sampled-process wall and CPU fields are resource accounting, not
speed evidence. Each memory run observed one process and no sampling errors.
The workload has no marked steady boundary, so retained memory is unavailable.

[`data/url-quote-fair-comparison-20260924.json`](data/url-quote-fair-comparison-20260924.json)
retains per-process raw wall, root CPU, RSS, footprint, process count, path and
digest validation, paired summaries, both self-calibrations, and an earlier
three-pair memory diagnostic. The complete controller results and `/usr/bin/time
-l` logs remain ignored under the clone work directory. `wait4` CPU covers each
workload root, including startup and imports; each had no children. The kernel
root lifetime peak RSS catches a short-lived maximum, while 10 ms footprint
sampling can miss one. The footprint is an Apple charged-memory ledger, not
USS or PSS.

`/usr/bin/time -l` measured the discarded calibration, quiet control retry,
candidate calibration, matched timing, two memory passes, and candidate memory
self-calibration at **52.88 total user plus system CPU seconds**. The largest
controller command maximum RSS was 28,082,176 bytes and every command reported
zero swaps. The maximum is per process, not an aggregate. All commands stayed
below the lane's 120 CPU-second and 1 GiB reported-RSS budgets. The discarded
calibration's per-process rows were overwritten by the bounded retry; its
timing-noise summary and command resources remain in the compact data.

The old [guarded comparison](url-quote-comparison-20260924.md) and
[lean comparison](url-quote-lean-comparison-20260924.md) had invalid candidate
parser bytecode and remain historical, unequal-cache observations. The
[memory attribution](url-quote-memory-attribution-20260924.md) identified that
confounder. This run is the direct cache-matched comparison against the last
accepted Rust fork stage.
