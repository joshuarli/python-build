# Cold ZIP import CPU accounting

`zipimport_cold` launches one fresh interpreter per operation. The harness's
`wait4` counter belongs to the workload root and excludes CPU spent by those
interpreters, even though the workload reaps them. Earlier CPU rounds labeled
that root counter as including reaped descendants; those rounds undercounted
this workload's CPU. The prior zlib full candidate report must not be used as
evidence of complete cold import CPU consumption.

`benchmarks.workloads.zlib.zipimport_cold` now records a before/after
`resource.getrusage(RUSAGE_CHILDREN)` delta around its direct, synchronous
`subprocess.run` calls. Its correctness payload names the child user and
system seconds and the number of reaped interpreters. The harness validates
that ledger, adds it once to the distinct root `wait4` user and system
seconds, and retains both raw components in each timing and memory CPU round.
The combined coverage is the root plus those direct reaped interpreters.
It does not establish CPU use for arbitrary grandchildren, detached processes,
or children left alive at the workload boundary. Other workloads continue to
report root-only `wait4` CPU unless they explicitly report a child ledger.

The focused regression test first failed because `_cpu_dict` accepted only a
root usage value. After the change, 47 focused result, runner, zlib, and
process tests passed (10 platform-specific process tests skipped on this host).
A direct
two-operation command reported root CPU 0.077071 user / 0.039596 system
seconds and reaped child CPU 0.03858 user / 0.019014 system seconds; the
combined values were 0.115651 user / 0.05861 system seconds. This was a
contract smoke check, not a paired performance benchmark.

Resource records from `/usr/bin/time -l` on the final focused test command were
0.51 user seconds, 0.28 system seconds, and 48,398,336 bytes maximum resident
set size. The direct smoke command recorded 0.12 user seconds, 0.08 system
seconds, and 23,986,176 bytes maximum resident set size. These external
figures describe each invoked command; the workload's own root and child CPU
fields above provide the accounting used by benchmark comparisons.
