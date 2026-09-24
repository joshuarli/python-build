# macOS `PROC_PIDREGIONINFO` feasibility probe (2026-09-24)

## Verdict: reject a complete mapped-private field from this interface

The installed macOS 26.5.2 SDK's `proc_pidinfo(PROC_PIDREGIONINFO)` returned
per-region private and shared resident counters for an ordinary same-user
child. A 32 MiB anonymous mapping added exactly 2,048 private resident pages
when touched, matching the 16 KiB page size and the child's 32 MiB RSS rise.
This confirms that the counter reacts to this simple allocation. It does not
establish a complete process total: every address walk encountered 18 submaps,
and the API accepts only a virtual address, with no public depth parameter to
descend them. It ended with a zero return and `EINVAL`, which is not a proven
end-of-map marker. The probe marks all three scans failed and publishes no
memory metric. Do not call these raw counters USS or PSS.

The stop condition in `mac-unique-memory-feasibility-20260924.md` applies:
traversal cannot handle submaps soundly. COW and double-map alias trials were
therefore not run. Aliases remain a separate risk even if a future interface
can enumerate leaves: distinct virtual mappings can refer to the same physical
page, while these counters do not provide a page identity for deduplication.

## Controlled observation

`mac-region-probe-20260924.py` launched one Python 3.13.7 child and held it at
three acknowledged checkpoints. The child reserved 32 MiB with anonymous
`mmap`, then wrote one byte per 16 KiB page. The observer read libproc's
`PROC_PIDTASKINFO` RSS and attempted a bounded address walk. The script is
read-only with respect to the target process and stops after 4,096 regions.

| State | RSS bytes | Region returns | Submaps | Raw private pages | Raw resident pages | Scan time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| idle | 19,398,656 | 109 full, 1 zero | 18 | 577 | 7,258 | 3.13 ms |
| reserved | 19,398,656 | 110 full, 1 zero | 18 | 577 | 7,258 | 1.48 ms |
| touched | 52,953,088 | 110 full, 1 zero | 18 | 2,625 | 9,306 | 2.16 ms |

Each `PROC_PIDTASKINFO` call returned its expected 96 bytes. Every successful
region call returned the expected 96 bytes; none returned a short record or a
negative code. Each scan's final zero return occurred at `0x7000000000` with
`errno=22`. Raw private and resident page sums are deliberately unqualified.
For example, the idle raw resident sum is about 119 MiB, far above the 19 MiB
libproc RSS. The scan includes submap records and has no established rule for
counting their contents. No denied region was observed, but no claim of full
region coverage follows from these return codes. The child protocol held the
same PID at each checkpoint; the probe did not independently verify its birth
timestamp because all scans already failed the traversal gate.

## Resource cost and scope

The final complete command was
`/usr/bin/time -l python3 rust-cpython/experiments/mac-region-probe-20260924.py`.
It used 0.06 user and 0.04 system CPU seconds, 0.16 seconds elapsed, zero
swaps, and a 52,953,088 byte maximum RSS reported by `time` for the command
including its child. The observer's own `getrusage(RUSAGE_SELF)` maximum RSS
was 20,004,864 bytes. The three scan calls took 6.77 ms total by monotonic
clock, about 2.26 ms per scan; this is an estimate of sparse checkpoint
sampler overhead, not a corrected workload timing. This stayed below the
30 CPU second and 512 MiB observer limits. An earlier development run used
0.05 user and 0.03 system seconds, 0 swaps, and a 52,543,488 byte maximum RSS.

The test used the system Python child, not the experiment's pinned 3.16 build.
That does not change the ABI/traversal stop condition, but it limits claims
about 3.16's particular mapping mix. No benchmark field, build, dependency,
formatter, linter, or hook was added or run.
