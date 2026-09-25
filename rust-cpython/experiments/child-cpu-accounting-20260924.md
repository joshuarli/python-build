# Cold ZIP import CPU accounting

`zipimport_cold` launches one fresh interpreter per operation. The harness's
`wait4` counter on Linux belongs to the workload root and excludes CPU spent
by those interpreters, even though the workload reaps them. This original
experiment incorrectly generalized that Linux behavior to macOS. On macOS,
earlier rounds already included waited descendants in root `wait4`; adding
their separate child ledger double counted CPU.

`benchmarks.workloads.zlib.zipimport_cold` now records a before/after
`resource.getrusage(RUSAGE_CHILDREN)` delta around its direct, synchronous
`subprocess.run` calls. Its correctness payload names the child user and
system seconds and the number of reaped interpreters. The harness validates
that ledger and retains both raw components in each timing and memory CPU
round. The harness adds it to root `wait4` only on Linux. On macOS root
`wait4` already includes those reaped interpreters. The Linux sum does not
establish CPU use for grandchildren, detached processes, or children left alive
at the workload boundary. Other Linux workloads continue to report root-only
`wait4` CPU unless they explicitly report a child ledger.

The later [native macOS nested-process probe](pyperformance_macos_timing_20260925.md)
established that Darwin root `wait4` includes the CPU of descendants reaped
through the workload process tree. The macOS cold ZIP result now retains its
`RUSAGE_CHILDREN` ledger for diagnosis without adding it to root `wait4`.
Detached and unreaped descendants remain outside that total.

The original focused regression test first failed because `_cpu_dict` accepted
only a root usage value. After that change, 47 focused result, runner, zlib,
and process tests passed (10 platform-specific process tests skipped on this
host). A direct two-operation macOS command reported root `wait4` CPU 0.077071
user / 0.039596 system seconds and reaped-child ledger CPU 0.03858 user /
0.019014 system seconds. The originally reported sum of 0.115651 user /
0.05861 system seconds double counted the child; the root `wait4` values are
the correct reaped-tree CPU for that command. This was a contract smoke check,
not a paired performance benchmark.

Resource records from `/usr/bin/time -l` on the final focused test command were
0.51 user seconds, 0.28 system seconds, and 48,398,336 bytes maximum resident
set size. The direct smoke command recorded 0.12 user seconds, 0.08 system
seconds, and 23,986,176 bytes maximum resident set size. These external
figures describe each invoked command; the workload's own root and child CPU
fields above provide the accounting used by benchmark comparisons.
