# Retired benchmark plan versus the 3.16 experiment

This is a source and recorded-evidence audit, not a fresh measurement. The
34 numbered rows below correspond to `plan.md`'s acceptance criteria near
the end of its benchmark section. **Built** means the repository has a path
for the requirement, **partial** means coverage is narrower than the old
criterion or this experiment needs, and **open** means no qualifying path or
evidence was found. None of these labels means a Rust optimization passed.

The current authority is `AGENTS.md` plus `rust-for-cpython.md`. Production
CPython 3.14.6 and its frozen Linux recipes are separate from the native
macOS CPython 3.16.0a0 experiment. The old `benchmarks/run.py` spelling and
directory layout are design sketches; `benchmarks/bench.py` and its current
result schema supersede them.

| Old criterion | Current status and evidence limit |
| --- | --- |
| 1. Supply two interpreters | **Built:** explicit paths or artifacts in `benchmarks/bench.py`; `benchmarks/README.md` §Compare interpreters. |
| 2. Retain 3.14.6 | **Built:** Linux product comparison is the harness's primary prepared path. |
| 3. Accept 3.16/Rust | **Partial:** native macOS local runs accept its interpreter, but third-party wheels and allocation support are pinned to 3.14 Linux. |
| 4. Preserve PBS reference | **Built:** `--preset pbs`; explicitly secondary in `rust-for-cpython.md`. |
| 5. Designate upstream primary | **Built:** `--baseline-kind upstream`; matched vanilla 3.16 was built (`experiments/upstream-baseline.md`), but no full qualification followed. |
| 6. Offline execution after fetch | **Partial:** Linux container runs disable networking; local macOS runs have no network boundary (`benchmarks/README.md` §Prepare and run). |
| 7. Byte-pin external inputs | **Partial:** `benchmarks/inputs.lock.json` covers 3.14 musl wheels; it cannot silently supply 3.16 macOS applications. |
| 8. Full pyperformance | **Partial:** Linux full suite exists; macOS `bench.py` rejects `full` and `pyperformance`. |
| 9. Selected Pyston macros | **Open:** no selected Pyston suite or explicit per-macro incompatibility record in the current manifest. |
| 10. First-party Django app | **Built:** `benchmarks/workloads/django.py` and registered request/ORM/template cases. |
| 11. Django cold, WSGI, ASGI, ORM, serialization | **Partial:** handlers, ORM, JSON responses, and import are registered; `import_django` is import timing, not a cold first-request scenario. |
| 12. Packaging/install/import | **Built:** `registry.py` has wheel install, compileall, startup, app imports, ZIP read/import. |
| 13. Clean authoritative timing | **Built:** `harness/runner.py` separates unsampled timing from resource passes. |
| 14. External memory observer | **Built:** Linux `/proc` and macOS `libproc` paths; limitations below. |
| 15. RSS, USS, PSS where available | **Partial:** Linux records private/PSS; macOS has RSS/physical footprint but no qualified USS/PSS (`experiments/mac-region-probe-20260924.md`). |
| 16. Account for process trees | **Partial:** memory samples descendants but can miss short lives; CPU is root-only except direct children of cold ZIP import (`experiments/child-cpu-accounting-20260924.md`). |
| 17. Preserve raw memory series | **Built:** raw samples retained under ignored `benchmarks/results/`; sampled tree peak has coverage limits. |
| 18. Memray allocation lane | **Partial:** Linux 3.14 has it; macOS 3.16 rejects rigorous mode. |
| 19. Separate native/Python allocator pressure | **Partial:** Linux Memray reports allocator distribution and native origins (`harness/allocations.py`); no validated 3.16/Rust allocator observation. |
| 20. Normalize allocations per operation | **Built for supported lane:** `harness/allocations.py` divides counts/bytes by operation count. |
| 21. Exclude Memray time from speed | **Built:** allocation report marks elapsed time noncomparable. |
| 22. Individual primary-workload memory verdicts | **Partial:** per-workload verdicts exist; macOS RSS is diagnostic and cannot establish upstream parity. |
| 23. No aggregate masking | **Built:** `benchmarks/README.md` §Verdicts and per-workload report logic. |
| 24. Self-comparison calibration | **Partial:** `self-compare` exists and local controls were measured; candidate self-noise and quiet-host calibration are not yet complete for accepting a 3.16 change. |
| 25. Counterbalanced order | **Built:** `harness/runner.py` alternates baseline/candidate order. |
| 26. Baseline-derived pyperformance loops | **Open:** `harness/pyperformance.py` invokes each interpreter's script independently, without passing calibrated loop counts from baseline. Custom macros do use fixed counts. |
| 27. Linux tuning/affinity metadata | **Built for amd64:** affinity, topology, governor/turbo information in `harness/environment.py`; no native arm64 Linux execution path. |
| 28. Native macOS host metadata | **Partial:** model/CPU/OS recorded; power and thermal state are not established in current provenance. |
| 29. Native Linux arm64 architecture | **Open:** `bench.py` accepts Linux amd64 or macOS arm64 only; native Linux arm64 benchmark support is not present. This is harness breadth, not a 3.16 Mac gate. |
| 30. Stable JSON schema | **Built:** versioned summaries and detailed files (`bench.py`, `harness/report.py`). |
| 31. Concise Markdown report | **Built:** each result has `summary.md`; raw data retained separately. |
| 32. Existing tests green | **Unverified here:** the coordination log records focused checks, not a fresh full repository test run. |
| 33. Retire old entry points | **Partial:** current front door is documented, but this audit did not establish that every older script/doc is removed or a clear wrapper. |
| 34. Accurate measurement README | **Mostly built:** `benchmarks/README.md` names RSS/footprint, CPU, offline, and allocation limits; its coverage remains broader than what 3.16 can run. |

## Contract carried forward, and its weaker edges

`rust-for-cpython.md` preserves the durable decision: exact public behavior
first, then useful public-path wall and kernel CPU gains, upstream-matched
peak/steady memory within measured noise, allocation churn, and native size.
It specifies separate serial paired timing, external memory, allocation,
and diagnostic passes, fixed logical work, visible individual regressions,
and rejected-candidate records. `rust-cpython/README.md` names CPython test
oracles and the same-source no-Rust control. These are stronger and more
relevant than the retired CLI proposal.

Three old safeguards are weaker in the working contract: baseline-derived
pyperformance loop counts are aspirational; both control and candidate
self-comparison are not an enforced acceptance precondition; and the old
allocation self-test for Python, native C, and eventual Rust allocation
classes has not qualified the Mac lane. The old plan's numeric 1%/1 MiB
memory example should remain only a starting hypothesis: the current
empirical noise rule is the appropriate contract. `rust-cpython/README.md`
§Performance comparison still describes its local Base64 path as timing-only,
while the later `benchmarks/README.md` and `rust-for-cpython.md` document a
separate macOS RSS pass; update that stale description when editing the
experiment guide.

## What the present experiments establish

`_base64` proves integration but does not serve public `base64`; its large
input results regress (`rust-cpython/PERFORMANCE.md`). The optional zlib-rs
candidate reaches public decompression and has local gains in three cases,
but ZIP timing is noise-bound, encoded bytes differ in 210/876 sampled cases,
installed extensions grow 1.59 MB, and upstream memory parity remains open
(`experiments/zlib-full-candidate-20260924.md`, `zlib-byte-compat.md`,
`zlib-memory-followup-20260924.md`). The matched vanilla upstream control
exists, but its zlib memory comparison was made under noisy host conditions
(`upstream-zlib-control-20260924.md`). The guarded URL quote proof has semantic
checks yet no paired public-task speed or memory verdict (`url-quote-proof-20260924.md`).
The rejected difflib reuse and deferred tomllib parser are findings, not
accepted optimizations. Therefore the objective has no accepted public
stdlib improvement in Rust yet.

## Next three concrete steps

1. Finish one public-path candidate decision on the quiet host: pair the
   guarded URL quote proof against the calibrated complete catalog task, or
   repeat zlib ZIP/cold-import first if that backend is the promotion target.
   Use the same-source control, full output checks, wall and covered CPU
   units, raw observations, candidate/control self-noise, and an explicit
   keep/reject verdict. Do not infer benefit from a kernel profile.
2. Qualify macOS resource evidence for the matched upstream 3.16 baseline:
   find a page-accounting interface that survives alias/COW and process-tree
   probes, and establish a compatible allocation tracer plus native/Rust
   allocation self-test. If an exact USS/PSS metric remains unavailable,
   record that gate as unqualified rather than passing on RSS.
3. Prepare byte-pinned, interpreter-compatible application inputs for the
   3.16 Mac pair and run the primary Django/startup/tooling/packaging suite
   with identical workload bytes. Add a true cold Django request scenario
   if import-only timing misses the selected bottleneck; then broaden to
   pyperformance with baseline-derived loops and selected Pyston macros
   where compatible. This supplies the real-workload evidence required for
   promotion beyond the isolated proof.
