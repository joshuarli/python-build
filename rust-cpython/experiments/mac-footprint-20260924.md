# Native macOS physical footprint evidence (2026-09-24)

## Verdict

Keep a **sampled process-tree physical footprint** diagnostic alongside the
existing exact, per-root lifetime physical-footprint peak. Neither is unique
resident memory (USS), proportional set size (PSS), or an exact whole-tree
peak. The new field can detect a sustained increase in charged dirty memory
across a workload tree. A non-regression in it cannot qualify upstream memory
parity, especially for short-lived children.

## Source and interpretation

The installed Xcode macOS SDK's `usr/share/man/man1/footprint.1`, under
“Physical Footprint” and “Auxiliary Data,” says the kernel maintains a
per-process ledger for dirty memory owned by a process. The ledger can charge
memory outside that process's mappings, includes sub-ledgers such as network
and graphics memory, and has a definition subject to change. Its current
value is `phys_footprint`; `phys_footprint_peak` is the maximum since process
launch. The same manual says a VM-object dirty breakdown is expensive and
cannot be done in real time. Xcode SDK `usr/include/sys/resource.h` defines
the `rusage_info_v4` fields `ri_phys_footprint`,
`ri_lifetime_max_phys_footprint`, `ri_proc_start_abstime`, and
`ri_proc_exit_abstime` used by
`proc_pid_rusage`. `usr/include/mach/task_info.h` defines separate resident,
footprint, and ledger peak counters. Apple XNU's
[`coalition.c`](https://github.com/apple-oss-distributions/xnu/blob/main/osfmk/kern/coalition.c)
reads each task's `phys_footprint` ledger balance for a coalition rollup,
supporting a sum of per-task charges as a diagnostic, but that rollup does not
make sequential external reads atomic.

These sources do not establish a public, cheap macOS USS or PSS interface.
The footprint ledger's ownership and nonmapped charges make either label
incorrect. A sum across process footprints measures aggregate charges; it
does not count resident physical pages uniquely across the tree.

## JSON contract

`benchmarks/harness/macos_resource.py` reads a PID's current
`ri_phys_footprint` and lifetime peak. The existing
`root_kernel_peak_phys_footprint_bytes` is the kernel's lifetime maximum for
the workload root, captured before reap; children do not become an exact
whole-tree peak through that field.

`benchmarks/harness/process.py` now sums current per-PID footprint values for
members of the sampled workload process group and discovered descendant tree.
Each raw sample carries `phys_footprint_bytes`, or JSON `null` when any
member cannot be read or membership changes. `peak_phys_footprint_bytes` is
the maximum of available sampled tree values, or `null` when none are valid.
`phys_footprint_coverage` describes the sampling limit. `MemorySample` and
`ProcessMemoryMetrics` in `benchmarks/harness/memory.py` keep these fields
separate from PSS, private bytes, RSS, and the root lifetime peak. A
`null` sample is omitted from the maximum, never treated as zero.

For each candidate tree, the collector reads every PID twice through libproc
and checks `ri_proc_start_abstime`; it also repeats the process-table scan
and requires the same live PID set and parent/process-group relationships.
An exit timestamp on the final libproc read also invalidates the sample.
This rejects detected PID reuse or a child exiting during collection.
Process creation and exits can still occur between scans, and per-PID values
are read sequentially. Escaped or short-lived descendants can be missed.
The maximum is therefore a sampled approximation, not a kernel tree peak.

The compact benchmark report does not yet surface this new aggregate;
`benchmarks/harness/runner.py` needs an explicit follow-on mapping. Existing
benchmark documentation and parity policy need corresponding integration by
the coordinator. The new raw JSON field alone must not change a pass/fail
decision.

## Bounded diagnostic and resource cost

No full build, benchmark suite, formatter, linter, hook, or test was run.
One 0.5-second sleeping child with 50 ms sampling produced six RSS samples,
five valid footprint samples, and no sampling errors; sampled peak footprint
was 5,603,736 bytes. `/usr/bin/time -l` for the complete diagnostic command
reported 0.86 s elapsed, 0.13 s user CPU, 0.44 s system CPU, and 25,755,648
bytes maximum resident set size. The command's 0.57 CPU seconds include the
Python controller, child, and repeated `ps` scans; this is an overhead
indicator, not a calibrated per-sample cost. Repeated process-table scans
can make an effective sample interval longer than the configured interval.
The diagnostic stayed far below the lane's 300 CPU-second and 2 GiB limits.

The implementation was reviewed with `git diff --check`; behavioral tests
were deferred under the lane's no-tests instruction. Before using this field
for candidate comparisons, run the scheduled focused macOS process test and
a matched control self-comparison on a quiet host to establish noise bounds.
