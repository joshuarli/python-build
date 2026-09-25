# Native macOS pyperformance timing path

`pyperformance_macos_timing.py` runs one inspected, stdlib-only pyperformance
manifest script at a time on native macOS arm64 CPython 3.16. It verifies and
extracts the existing vendored pyperf 2.10.0 and pyperformance 1.14.0 wheels
into ignored `rust-cpython/work/`, then invokes the manifest script directly.
It does not install a package, use pyperformance's venv path, fetch an input,
or change a benchmark lock. The selectable subset is `python_startup`,
`python_startup_no_site`, `base64`, `json_dumps`, `json_loads`, `pickle`, and
`unpickle`. Other manifest scripts remain unsupported by this narrow recipe;
their dependency and compatibility closure has not been qualified for the
experimental interpreter.

For each selected script, the baseline first performs one pyperf process with
one measured value. The script's measured run metadata determines one fixed
loop count through the existing `baseline_loop_counts` rule. Every following
baseline and candidate value-bearing run must report that count. `--pairs N`
runs serial pairs with baseline/candidate order reversed on alternating pairs.
Each arm compiles from source using an empty per-attempt
`PYTHONPYCACHEPREFIX` and `PYTHONDONTWRITEBYTECODE=1`. It records the pyperf
value, external wall time, and kernel root `wait4` user/system CPU. On this
Darwin host, root `wait4` includes the CPU of waited descendants. Root and
worker `RUSAGE_CHILDREN` ledgers are retained as diagnostics; adding them to
root `wait4` would double count. Escaped or unreaped descendants remain
unavailable. The launcher writes its ledger after the benchmark body and runs
identically in both arms.

The [nested CPU probe](data/pyperformance_macos_cpu_probe_20260925.json) is
reproducible with `pyperformance_macos_cpu_probe.py --output NEW.json`. Its
grandchild spent 0.081537 user and 0.124827 system CPU seconds; the child's
`RUSAGE_CHILDREN` reported those same values. Parent `wait4` for that child
reported 0.081712 user and 0.125643 system seconds, equal to grandchild plus
child CPU within 0.2 ms. Parent `RUSAGE_CHILDREN` matched parent `wait4`.

The [compact proof](data/pyperformance_macos_plumbing_20260925.json) used the
same installed Rust-for-CPython 3.16 interpreter for both arms. Its launcher
SHA-256 is `6eeeb64b9eb161d4d5edb9200e79146dabd8acc0f73fcdca48417d0e3c9531bd`;
the loaded `libpython3.16.dylib` SHA-256 is
`a81b7abb07a9837ef7c2eecd08729fd86c1b9dd01613f13f809ef9f7cb61065c`.
The baseline calibrated `python_startup` at **8 loops**. Both measured arms
reported the same benchmark name, `second` unit, and 8 loops. The baseline
arm took 0.903 seconds external wall, 0.653 user CPU seconds, and 0.117 system
CPU seconds across the accounted process tree. The candidate arm took 0.918,
0.653, and 0.117 seconds respectively. The evidence contains exact wheel,
manifest, script, executable, libpython, and pyperf JSON hashes, as well as
commands and CPU components. The startup task has no application payload to
hash; a successful pyperf command and its recorded name, unit, loop count,
and JSON digest are the available output identity.

An unrelated Docker container was consuming host CPU during this bounded
command proof. The single self pair cannot establish a timing difference or
repeatability. No memory or allocation pass was made, and neither parity is
claimed. A later quiet-host run can use the same command with `--pairs 5` and
distinct baseline/candidate paths and evidence names. Control and candidate
self-comparisons and wider workload coverage remain open before any close
performance verdict.

```sh
python3 rust-cpython/experiments/pyperformance_macos_timing.py \
  --baseline /path/to/control/bin/python3.16 \
  --candidate /path/to/candidate/bin/python3.16 \
  --benchmark python_startup --pairs 5 \
  --evidence rust-cpython/experiments/data/pyperformance_macos_quiet.json
```

Each invocation requires a fresh ignored `--work` directory and a new
`--evidence` path. This prevents accidental mixing of pyperf files from
different interpreter pairs. The bounded proof did not run test suites,
formatters, linters, or hooks.
