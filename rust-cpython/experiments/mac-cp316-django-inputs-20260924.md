# macOS CPython 3.16 Django benchmark inputs

The separate `benchmarks/inputs.macos-cp316.lock.json` pins Django 6.1.1,
asgiref 3.12.1, and sqlparse 0.6.0. These are the same three `py3-none-any`
wheel bytes already recorded in the Linux benchmark lock. Their URL, size,
SHA-256, filename, version, license, and wheel tag remain pinned. This is an
experimental benchmark input set, not a CPython 3.14.6 product dependency.

`benchmarks/harness/inputs.py` accepts the exact macOS arm64 CPython 3.16
target descriptor and only this three-wheel Django closure. It checks wheel
identity, Python requirement, and dependency metadata before extraction.
`benchmarks/bench.py` selects the Django group for local macOS workloads that
require Django, rejects unapproved package workloads, checks both tested
interpreters before preparing the group, and snapshots the selected lock and
input digests in results. Package-free local comparisons retain their previous
interpreter flexibility. Linux keeps its original lock and routing.

Evidence on 2026-09-24:

- All three wheels downloaded from their locked URLs via `curl` and passed
  exact byte-size and SHA-256 checks. `urllib` could not verify the local
  certificate chain; this was a host trust issue, and `curl` succeeded with
  its configured trust store. No pinned byte was changed.
- The three wheel `METADATA` records declare Python floors of 3.10 or 3.12.
  Django's unconditional runtime requirements are `asgiref>=3.9.1` and
  `sqlparse>=0.5.0`; their pinned versions satisfy them. Other requirements
  are guarded by non-macOS, older-Python, or unselected extra markers.
- A prepared external site imported all three packages under
  `rust-cpython/stage/bin/python3.16` and printed `6.1.1 3.12.1 0.6.0`.
- `python3 -m unittest benchmarks.tests.test_inputs benchmarks.tests.test_bench_inputs`
  passed 12 tests. No application timing or cold-request workload was run.

The fetch and import attempts have separate raw output and `/usr/bin/time -l`
records under ignored `rust-cpython/work/mac-cp316-django-inputs-20260924ak/`.
The successful curl fetch recorded 0.45 s elapsed, 0.11 s user CPU, 0.06 s
system CPU, and 32,931,840 bytes maximum resident size; the import check
recorded 1.68 s elapsed, 0.62 s user CPU, 0.87 s system CPU, and 36,978,688
bytes maximum resident size. These are validation costs, not workload results.
