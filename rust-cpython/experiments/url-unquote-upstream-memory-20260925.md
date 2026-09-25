# Installed URL unquote memory against upstream, 2026-09-25

## Finding

Across five serial, counterbalanced pairs of the complete `catalog_search_form`
task, the optional unquote build's root lifetime peak RSS was **114,688 bytes
lower** at the median than vanilla upstream CPython 3.16. The pair differences
were `+32,768, -212,992, -114,688, -212,992, +81,920` bytes (unquote minus
upstream). Their maximum absolute size was below the upstream five-pair
self-comparison allowance of 360,448 bytes. Against the accepted quote-only
fork, the unquote build was also 114,688 bytes lower at the paired median;
all five differences were within the quote side's 262,144-byte RSS allowance.
The direction is a small observation, not proof of lower memory use.

The sampled process-tree physical-footprint median was 180,224 bytes lower
than upstream and 229,376 bytes lower than the quote-only fork. All five
upstream/unquote footprint differences were negative; two exceeded the
unquote self-noise maximum by roughly 0.2 MB in the favorable direction.
Physical footprint is Apple's charged dirty-memory ledger, not USS or PSS.
The test has no comparable allocation counts and no explicit steady or
post-GC boundary, so **upstream memory parity remains open** under the
experiment contract. These readings establish no measured RSS or footprint
regression on this one workload.

## Workload, identities, and controls

Each of 60 observed children performed 500 complete `catalog_search_form`
batches: 48 records, 480 parsed fields, and 240 parsed pairs per batch.
Every child independently validated input digest
`7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f`
and output digest
`a56d64f19accb1be3bb302cc60f406928d15182828c2b7e975e957d503dc1f22`.
The exact repository workload was used; no synthetic inner decoder loop
substituted for the registered task.

The immutable source stages were APFS-cloned into this lane's ignored
`rust-cpython/work/url-unquote-upstream-memory-20260925a/` directory:

| Side | Source stage | `urllib/parse.py` SHA-256 | `_rust_url_quote` size |
| --- | --- | --- | ---: |
| Upstream | `/private/tmp/python-build-exp-upstream-20260924/rust-cpython/work/upstream-control/stage` | `178fce6bb504b9e544ac22015778554234c63865d94374913f988bb731e0d825` | absent |
| Quote-only fork | `/private/tmp/python-build-exp-url-full-build-retry-20260924p/rust-cpython/stage` | `85ac4db38a30e3b12dd78ff0a5b83baa61caedebc3a44c33cd45c85c3279acee` | 51,288 B |
| Optional unquote | `/private/tmp/python-build-exp-url-unquote-build-20260925a/rust-cpython/stage` | `ad11741ef88e9b7175ef0e1ffb311fdee865c073194743e08eb61adee828f4dd` | 51,720 B |

Each clone's launcher, shared libpython, parser, and extension, where present,
matched its stage byte for byte. Its own interpreter regenerated a valid
checked-hash parser cache with flags `3`; source hashes were
`fcbbd960190070b8`, `fb86b91008046490`, and `0cbdbaed6fde156b`,
respectively. The measured child checked its actual prefix, parser, cache,
extension identity, cache header/source hash, helper presence, and full
digests. Separate verbose imports confirmed that all three interpreters
loaded the matching parser cache code object. Children suppressed bytecode
writes and used the same default allocator and ordinary hash randomization.
The [compact data](data/url-unquote-upstream-memory-20260925.json) retains
the executable, library, source, extension, and cache hashes and sizes.

The upstream build is vanilla CPython 3.16.0a0 at merge base
`0983642c966d9c536416101e99b7d2b085483847`; the fork has later Rust
integration and other changes. All stages used the locked LLVM 23.1.2,
ThinLTO, and nine-worker PGO task, but their source ancestry and generated
PGO profiles differ. The three-way comparison therefore describes installed
artifacts and cannot attribute every memory difference to the unquote helper.

## Separate resource pass

The existing `benchmarks.harness.process.run_command` observed each fresh
workload process with 10 ms sampling, using macOS libproc RSS and physical
footprint plus `wait4` root user and system CPU. The root's kernel lifetime
peak RSS and physical footprint were captured before reap. Ten self attempts
per side formed five same-side pairs; fifteen cross-side pairs compared
upstream/quote, upstream/unquote, and quote/unquote in alternating order.
No timing verdict comes from these instrumented runs.

| Metric | Upstream self median / max pair noise | Quote self median / max pair noise | Unquote self median / max pair noise | Upstream → quote paired median | Upstream → unquote paired median | Quote → unquote paired median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Root kernel peak RSS | 33,390,592 / 360,448 B | 33,472,512 / 262,144 B | 33,292,288 / 98,304 B | +49,152 B | -114,688 B | -114,688 B |
| Sampled tree peak RSS | 33,390,592 / 360,448 B | 33,472,512 / 262,144 B | 33,292,288 / 98,304 B | +49,152 B | -114,688 B | -114,688 B |
| Root kernel peak footprint | 19,866,104 / 376,856 B | 19,882,488 / 262,144 B | 19,718,636 / 98,328 B | -16,360 B | -180,224 B | -81,920 B |
| Sampled tree peak footprint | 19,866,092 / 360,472 B | 19,849,720 / 278,528 B | 19,620,332 / 196,632 B | -16,360 B | -180,224 B | -229,376 B |

The complete paired differences and all 60 compact per-attempt records are in
the JSON data. Unique raw JSON for each attempt, including all samples and
controller logs, remains under the lane's ignored work directory. The first
verbose audit attempt failed an overly narrow log substring assertion; its
raw files were retained. The actual upstream cache line matched the source,
and the corrected second audit passed all three sides before measurement.
There were no failed memory attempts. Each had 32–66 samples, one observed
workload process, no sampler error, and a valid complete digest. The task
creates no workload children, so root and sampled tree RSS peaks coincided
in this pass. `wait4` still covers root CPU only; there were no workload
children to add. The sampled footprint sums sequential per-PID reads and
can miss transient peaks or short-lived descendants. Neither it nor the root
kernel peak is an exact whole-tree peak in a workload that spawns children.

The final sample can occur during teardown and was not designated a retained
or steady-state boundary. No USS, PSS, allocation count, or allocation-byte
measurement was available; none is inferred from RSS or footprint. The prior
[installed timing report](url-unquote-installed-comparison-20260925.md) is
the separate uninstrumented performance evidence.

## Resource accounting and limit

`/usr/bin/time -l` around the 60-attempt memory controller reported
**41.16 user + 2.37 system = 43.53 kernel CPU seconds**, including its
children. The two separately recorded audit commands, including the failed
assertion, used **1.06 + 0.12 = 1.18** and **2.25 + 0.20 = 2.45** seconds.
The exact sum of recorded commands was **44.47 user + 2.69 system = 47.16
kernel CPU seconds**, below the **120-second cap**. Summed child `wait4` CPU
was 40.69017 user + 1.50716 system seconds and is already included in the
controller total. Clone creation and subsequent report reduction were not
kernel timed, so 47.16 seconds is the recorded command total, not a claimed
whole-lane total.

The largest measured child root peak RSS was **33,734,656 bytes**. The
largest recorded controller/audit process RSS was **39,944,192 bytes**, below
the **1 GiB per-process limit**. All three `/usr/bin/time -l` commands
reported zero swaps; host swap use was 243.88 MiB before and after the pass.
The host was a MacBookPro18,3 on Darwin 25.5.0, with 86% free memory at
preflight. No competing compiler or benchmark was observed. No build, test
suite, formatter, linter, hook, or push ran in this lane.
