# Pyperformance fixed loops

The pinned pyperf 2.10.0 `Runner` accepts `--loops`; zero selects automatic
calibration. Its worker records the effective count in run metadata, and its
process manager forwards a nonzero count to workers. `--track-memory` uses the
same worker path before replacing time samples with memory samples. The pinned
pyperformance 1.14.0 scripts use `pyperf.Runner` (or its imported alias) for
their benchmark runs. These checks came from the vendored wheels, without a
benchmark measurement.

The harness now uses a one-process, one-value baseline calibration per manifest
script. It requires a positive, stable `loops` value in every measured run of
each named result. A script's named results share one CLI loop count; the
largest baseline count is used only when it expands the smallest by at most
four times. Missing or inconsistent metadata and wider divergence are explicit
unsupported cases. Baseline and candidate timing and both memory passes then
use that fixed count; each output is checked for the requested count.

The raw per-script pyperf calibration files preserve source counts. The
comparison JSON records chosen counts, unsupported reasons, and selected
coverage. Syntax compilation and `git diff --check` passed. No timing or memory
comparison was run because unrelated Docker CPU load would invalidate a
published result; therefore this is implementation evidence, not a performance
verdict.
