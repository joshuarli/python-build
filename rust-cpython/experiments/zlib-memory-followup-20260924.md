# ZIP read memory follow-up (2026-09-24)

**Verdict: a directional signal, not a qualified memory regression.** In the
clean zlib-rs whole-build comparison, `zip_read_wheel` had a 3.129 MB larger
median peak RSS and a 5.177 MB larger median *sampled* physical footprint.
Both are decimal MB. The three pairs are too few, and this host was too busy,
to separate a small backend effect from launch and sampling variation. This
does not clear the candidate's process-memory parity gate either: unique or
proportional memory, retained memory, and allocation data are unavailable.

The measurements below are from committed
[`data/zlib-full-evidence-20260924.json`](data/zlib-full-evidence-20260924.json),
with build and workload context in
[`zlib-full-candidate-20260924.md`](zlib-full-candidate-20260924.md).
The external memory pass launched a fresh interpreter for each run, with one
observed process per ZIP read round and 10 ms requested sampling. Memory pairs
alternated launch order: control/candidate, candidate/control,
control/candidate. The table pairs runs by round, not by their chronological
position inside each pair.

| Pair | Root kernel peak RSS, control → candidate (MB) | RSS delta (MB) | Sampled peak footprint, control → candidate (MB) | Sampled footprint delta (MB) | Root kernel peak footprint, control → candidate (MB) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 38.519 → 42.320 | +3.801 | 19.088 → 24.265 | +5.177 | 25.478 → 29.066 |
| 2 | 42.893 → 42.762 | −0.131 | 19.760 → 29.508 | +9.749 | 29.836 → 29.508 |
| 3 | 39.338 → 42.467 | +3.129 | 18.875 → 19.629 | +0.754 | 26.297 → 29.213 |
| Median of each side | 39.338 → 42.467 | +3.129 | 19.088 → 24.265 | +5.177 | 26.297 → 29.213 |

The RSS result is the root's kernel lifetime peak in every round. It is not
limited by the sampling interval: sampled RSS maxima were only 31.457–32.801
MB for controls and 37.241–42.697 MB for candidates, generally below the
kernel peaks. Thus the RSS direction is real in these executions, but its
attribution and repeatability remain uncertain. Pair 2's control peak is
4.375 MB above pair 1's control peak; its candidate peak is 0.442 MB above
pair 1's candidate peak. This varying control level can explain much of the
apparent effect.

Sampled footprint is a different observation. At roughly 63–68 ms the
controls were 26.36–26.51 MB RSS and the candidates were 26.53–27.46 MB,
before the final rise. The largest gap is near termination: the last valid
control samples at 76–82 ms were 31.46–32.80 MB RSS and 18.87–19.76 MB
footprint; candidate samples near 79 ms reached 37.39/42.70 MB RSS and
24.27/29.51 MB footprint in pairs 1/2. Pair 3's final candidate footprint
sample is null; its reported sampled peak is the earlier 73.8 ms value,
19.629 MB. Its kernel lifetime footprint peak was 29.213 MB, showing how a
late transient could escape this sampled field. The root kernel footprint
median gap is 2.916 MB, with pair deltas +3.588, −0.328, +2.916 MB. The
5.177 MB sampled median gap therefore cannot be treated as an exact lifetime
footprint increase, still less as unique memory. The footprint ledger is
charged dirty memory, not USS/PSS; the sampler's sequential process reads
also do not establish an exact simultaneous tree peak.

The comparison's own repeatability allowance for ZIP peak RSS is 4.028 MB,
larger than its 3.129 MB median gap. The same-session control/control
`zlib_decode_1m` self-comparison in the source report gave a 5.68 MB RSS
allowance. A separate committed ZIP control/control experiment in
[`data/zlib-self-control-20260924.json`](data/zlib-self-control-20260924.json)
had RSS pair differences +6.210, +0.410, and +0.147 MB between its identically
configured A/B sides. That experiment is contextual evidence, not an exact
calibration for this build and run. There is no same-session ZIP footprint
self-comparison, so the +5.177 MB sampled footprint gap has no defensible
noise threshold. The near-terminal sample sensitivity further weakens it.
With two positive RSS pairs and one tie, a small true increase remains
plausible; a claim that it exceeds measured noise does not.

**Next qualification:** wait for a quiet host with no concurrent build or
benchmark. Run a serial `zip_read_wheel` control/control self-comparison and
then the same control/candidate comparison, using the same binaries and
workload digest, counterbalanced order, and more than three paired external
memory rounds. Retain raw samples and kernel root peaks; compare paired RSS
and root lifetime footprint against the ZIP-specific self noise before
assigning a memory verdict. Capture a stage marker or denser observations
around ZIP output materialization and interpreter exit to distinguish a
sustained difference from the final transient. Keep the separate timing pass;
do not infer a speed result from instrumented memory runs. The present host
load makes another substantial pass now a poor qualification. A later
upstream memory-parity claim still needs compatible unique/proportional and
allocation measurements under the repository's benchmark contract.

This follow-up used read-only inspection and short JSON summaries only; it
ran no build or benchmark. The four Python summary commands each used about
0.02 s user plus 0.01 s system CPU by `/usr/bin/time -l`, with maximum
reported RSS below 19 MB. No formatter, linter, or hook ran.
