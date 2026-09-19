#!/bin/sh
# Run one pyperformance suite with the given interpreter.
#
# Usage: run_single.sh <identifier> <python-bin> [output-dir]
#        [--benchmarks csv] [--affinity cpu-list] [--venv dir]
#
# Fully offline: pyperformance is installed from /bench/vendor (see
# vendor/SHA256SUMS) with --no-index --find-links, never from a package index. The
# venv is created by the benchmarked interpreter itself, exactly as in
# astral-sh/python-build-standalone PR #1192, so pyperformance measures
# that interpreter: pyperformance==1.14.0, `--rigorous --warmups 2`.
# --venv reuses a pre-built venv (for parallel shards sharing one venv
# per interpreter); otherwise a throwaway venv is created per invocation.
set -eu

ID="${1:?usage: run_single.sh <identifier> <python-bin> [output-dir] [options]}"
PYTHON="${2:?usage: run_single.sh <identifier> <python-bin> [output-dir] [options]}"
shift 2
OUTDIR="/results"
if [ $# -gt 0 ]; then
  case "$1" in
    --*) ;;
    *) OUTDIR="$1"; shift ;;
  esac
fi

BENCHMARKS=""
AFFINITY=""
VENV=""

while [ $# -gt 0 ]; do
  case "$1" in
    --benchmarks) BENCHMARKS="${2:?--benchmarks needs a value}"; shift 2 ;;
    --affinity) AFFINITY="${2:?--affinity needs a value}"; shift 2 ;;
    --venv) VENV="${2:?--venv needs a value}"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

PYPERFORMANCE_PIN="1.14.0"

"$PYTHON" -c "import sys; print(sys.version)"

if [ -z "$VENV" ]; then
  WORK_DIR="$(mktemp -d "$OUTDIR/.work-XXXXXX")"
  trap 'rm -rf "$WORK_DIR"' EXIT INT TERM
  cd "$WORK_DIR"
  VENV="$WORK_DIR/bench_env"
fi

if [ ! -x "$VENV/bin/pyperformance" ]; then
  if [ ! -x "$VENV/bin/python" ]; then
    "$PYTHON" -m venv "$VENV"
  fi
  "$VENV/bin/python" -m pip install --no-index \
      --find-links /bench/vendor "pyperformance==$PYPERFORMANCE_PIN"
fi

STAMP="$(date +%Y-%m-%dT%H%M%S)"
OUT="$OUTDIR/$ID-$STAMP.json"
EXTRA=""
if [ -n "$BENCHMARKS" ]; then
  EXTRA="$EXTRA --benchmarks $BENCHMARKS"
fi
if [ -n "$AFFINITY" ]; then
  # Pin worker processes to the given CPUs (pyperf-level affinity:
  # the timed code itself is pinned, not just the controller).
  EXTRA="$EXTRA --affinity $AFFINITY"
fi

# Two-tier provenance (see README.md): the caller venv above is fully
# offline from /bench/vendor. Benchmark payload packages (pinned by
# pyperformance's own per-benchmark requirements.txt) resolve from the
# package index identically on both sides; their versions are snapshotted
# from the run logs as result provenance. PIP_* is deliberately left
# alone: forcing --no-index here would fail those payload installs
# instead of resolving the same pinned bytes both sides get anyway.

# shellcheck disable=SC2086
"$VENV/bin/pyperformance" run --rigorous \
    --warmups 2 $EXTRA --output "$OUT" 2>&1 | tee "$OUTDIR/log-$ID-$STAMP.txt"
