# macOS resource sampler overhead (2026-09-24)

## Recommendation

Keep the narrower libproc process-table path as a diagnostic improvement. It
gave more samples at a requested 50 ms interval in this one observation, with
lower measured command CPU. Retain the existing labels: sampled tree RSS and sampled
tree physical footprint are sequential sums, not exact simultaneous peaks.
Physical footprint is Apple's charged dirty-memory ledger, neither USS nor
PSS. The separate root lifetime footprint peak remains a single-PID kernel
counter.

## API and identity contract

The installed Xcode macOS SDK (macOS 26.5.2) declares `proc_listpids` and
`proc_pidinfo` in `usr/include/libproc.h`. Its `usr/include/sys/proc_info.h`
defines `PROC_PGRP_ONLY`, `PROC_PPID_ONLY`, `PROC_PIDTASKALLINFO`, and the full
`proc_taskallinfo` layout. The latter contains BSD PID, parent, group, status,
birth timestamp, and task resident bytes. The declared layout has 136 bytes
of `proc_bsdinfo` followed by 96 bytes of `proc_taskinfo`, for a 232-byte
`proc_taskallinfo`; the ctypes definition includes every declared field and
passes its full size to `proc_pidinfo`. `usr/include/sys/proc.h` defines
`SZOMB` as status 5. These are the authoritative definitions used by
`benchmarks/harness/macos_resource.py`; no dependency was added.

Each table read lists the isolated process group, then recursively lists
direct children of each discovered live process. `proc_pidinfo` supplies one
BSD/task read for each selected PID. A PID that vanishes during the read is
omitted. The footprint path still reads `proc_pid_rusage` twice per PID; it
compares both `ri_proc_start_abstime` values, repeats the table read, and requires the
same live members, parent/group relationships, and BSD birth timestamps.
The second rusage read must show no exit timestamp. A detected change makes
the footprint sample unavailable. RSS stays a sampled tree sum.

The filtered listings avoid scanning every process or launching `ps` twice
per sample. They cannot provide an atomic process-tree snapshot. A child can
be born and exit between listings, and an escaped descendant can be missed
after its parent exits. The separate listing and task-info calls may also
race; the repeated table and rusage identity checks limit but cannot erase
that window. `proc_listpids` buffer growth handles a list that fills the
initial buffer.

## Bounded sleeping-child diagnostic

Command: `/usr/bin/time -l python3 -c ...` invoking `run_command` with a
Python root that waits for a Python child sleeping 0.5 seconds; sampler
interval 50 ms. `/usr/bin/time` accounts the controller and all child commands,
including the old `ps` processes. One before and one after observation were
collected on the same macOS 26.5.2 host on 2026-09-24. The commands took 0.94
and 0.70 seconds, respectively. Other host activity was not monitored; the
coordinator reported a PGO build active after these commands, so overlap or
contention during the diagnostic cannot be ruled out. These are diagnostic
observations, not published benchmark data or a calibrated speedup.

| Observation | Existing `ps` path | Filtered libproc path |
| --- | ---: | ---: |
| Command elapsed, seconds | 0.94 | 0.70 |
| Command user CPU, seconds | 0.16 | 0.10 |
| Command system CPU, seconds | 0.48 | 0.05 |
| Command maximum resident set size, bytes | 26,181,632 | 25,624,576 |
| Sampler workload duration, seconds | 0.674 | 0.602 |
| RSS samples | 5 | 12 |
| Valid footprint samples | 5 | 12 |
| Samples observing both root and child | 4 | 10 |
| Sampled peak tree RSS, bytes | 32,292,864 | 32,391,168 |
| Sampled peak tree footprint, bytes | 14,336,888 | 14,451,600 |
| Sampling errors | none | none |

The workload's kernel-accounted CPU was 0.03802 user / 0.021448 system
seconds before and 0.039518 user / 0.022235 system seconds after. Those values
exclude the controller and sampler, so command CPU is the relevant overhead
indicator. The command's highest resident set is not the workload tree peak;
both are reported above. Sample counts depend on launch timing, process-table
load, and the host scheduler. No calibration or noise bound was attempted.

No CPython build, network package installation, formatter, linter, hook, or
test was run. The two diagnostics consumed under 2 CPU seconds in total and
stayed below 27 MiB maximum resident set size for the measured command,
within the 150 CPU-second and 1 GiB lane budget.
