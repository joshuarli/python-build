# Exploratory zlib-rs backend probe, 2026-09-24

## Question and controls

Does the already proved zlib-rs 0.6.7 C ABI backend reduce CPU use in public
stdlib decompression paths? This probe ran one pinned **no-Rust fork**
interpreter twice: its platform zlib extension as control and its previously
built zlib-rs overlay as candidate. The executable, CPython source, flags,
stdlib, workload code, and compressed inputs were identical within each pair.
The overlay's SHA-256 was checked against `rust-cpython/results/zlib-proof.json`.
This is an isolated backend comparison, not the final Rust-enabled fork or
vanilla upstream CPython comparison.

The five workloads in `benchmarks/workloads/zlib.py` exercised public
`zlib.decompress`, streaming `zlib.decompressobj`, `gzip.GzipFile`,
`zipfile.ZipFile.read`, and cold `zipimport`. Every pair checked the same
compressed-input digest, decoded-content digest, and logical operation count.
The probe `probe_zlib.py` alternated order, ran each side serially, and read
kernel user plus system CPU seconds via `wait4`. Wall latency includes process
startup; CPU totals include children reaped by the workload process. Detached
or unreaped children would be outside that CPU total. For ZIP import, the unit
is one new import process; for the other rows, it is one decoded byte.

## Observations

The first pass used five pairs at four times the registered workload counts.
The Mac's load average moved from 5.01 to 4.54 during it; another sustained
CPU user was present. Ratios below are paired medians, zlib-rs divided by
platform zlib. Values below 1 favor zlib-rs. The independent three-pair pass
is shown to expose sensitivity to host conditions.

| Public path | CPU ratio, 5 pairs | Wall ratio, 5 pairs | CPU ratio, 3 pairs | Wall ratio, 3 pairs |
| --- | ---: | ---: | ---: | ---: |
| 1 MiB zlib decode, mixed compressibility | 0.858 | 0.887 | 0.868 | 0.878 |
| 4 KiB streaming zlib decode | 0.948 | 0.951 | 0.917 | 0.919 |
| 1 MiB gzip extraction | 0.915 | 0.908 | 0.894 | 0.875 |
| Read all members of a wheel-shaped ZIP | 0.978 | 0.942 | 1.033 | 1.025 |
| Cold import from compressed ZIP | 1.028 | 1.019 | 1.056 | 1.025 |

The first pass used about 0.684 ns/decoded byte of CPU for platform zlib
versus 0.588 ns/decoded byte for zlib-rs in the mixed one-shot path; cold ZIP
import used about 31.0 ms versus 32.0 ms of CPU per import. These are medians
of per-run totals, so their ratio need not equal the paired-median ratio.
`data/zlib-cpu-20260924.json` and `data/zlib-cpu-rss-20260924.json` retain every
run's user/system CPU, wall latency, order, input/output digests, operation
count, and host load.

The separate RSS pass sampled the process tree with macOS `ps`. Four of five
workloads had only two or three samples per run, enough to miss a short peak.
Cold ZIP import had roughly 9–11 samples per run. The raw samples remain in
`data/zlib-cpu-rss-20260924.json`; its peak-RSS summary is explicitly null
because at least one pair per workload had fewer than ten samples. The sampler
also cannot report unique/private memory or native allocation counts. No
memory improvement or nonregression follows from these observations.

After adding a macOS kernel root-process peak, a third independent three-pair
pass and a five-pair platform-zlib self-comparison ran at load averages near
3–4. The candidate's paired CPU ratios were 0.857 for mixed one-shot decode,
0.983 for streaming, 0.894 for gzip, 1.006 for whole ZIP reads, and 1.076 for
cold ZIP import. Its paired root-kernel peak-RSS ratios were 1.041, 1.017,
1.001, 1.015, and 0.999 in that order. The self-comparison showed one-shot
root-RSS ratios from 0.943 to 1.050 and whole-ZIP ratios from 1.003 to 1.143;
these overlap the candidate observations. Its whole-ZIP CPU ratios ranged
from 0.940 to 1.118. Thus the kernel peak catches short processes, but these
host conditions and three memory pairs do not establish a memory delta. The
raw reports are `data/zlib-kernel-rss-20260924.json` and
`data/zlib-self-control-20260924.json`. Kernel `wait4` root-family max RSS is
a lower bound on a simultaneous process-tree peak; the V4 physical-footprint
peak describes the root PID only.

## Decision

**Keep zlib-rs as an experiment; do not promote this backend yet.** The
one-shot and gzip CPU reductions warrant a quiet-host follow-up. Streaming and
whole ZIP results vary, while cold ZIP import used more CPU in all three
candidate passes. The self-comparison characterizes local noise but was also
run under load; upstream memory parity remains unqualified. The next
qualification needs a quiet serial run, robust peak/retained and unique memory
measurements, and a comparison with the now-built upstream control. A source
patch must then make the backend reproducible in a fresh Rust-enabled
candidate build before it can be accepted.
