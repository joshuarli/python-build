#!/bin/bash
# Host driver for the head-to-head musl benchmark.
#
# Default (parallel) mode saturates the machine: the suite is sharded
# across K pinned workers per interpreter (2K concurrent single-threaded
# benchmark runs on disjoint real cores), then merged per side with
# `pyperf combine`. Each suite stays internally contention-free; the two
# interpreters run identical shard contents concurrently. See README.md
# for the fairness model.
#
# --serial runs both suites back-to-back in one process instead (slowest,
# strongest isolation; the mode for a published verdict).
#
# Usage: ./benchmarks/run_benchmarks.sh [--shards K] [--serial] [--image-tag NAME]
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="local-pybench-musl"
SHARDS=8
SERIAL=0
TARBALL="$REPO/dist/x86_64-unknown-linux-musl/cpython-3.14.6-x86_64-unknown-linux-musl-r1.tar.gz"

while [ $# -gt 0 ]; do
  case "$1" in
    --shards=*) SHARDS="${1#*=}"; shift ;;
    --shards) SHARDS="${2:?--shards needs a value}"; shift 2 ;;
    --serial) SERIAL=1; shift ;;
    --image-tag=*) IMAGE="${1#*=}"; shift ;;
    --image-tag) IMAGE="${2:?--image-tag needs a value}"; shift 2 ;;
    *) echo "usage: run_benchmarks.sh [--shards K] [--serial] [--image-tag NAME]" >&2; exit 2 ;;
  esac
done

if [ "$(uname -m)" != "x86_64" ]; then
  echo "error: benchmarks are x86_64-only (running on $(uname -m))" >&2
  exit 2
fi
if [ ! -f "$TARBALL" ]; then
  echo "error: no packaged artifact at $TARBALL; run package first" >&2
  exit 2
fi

docker build --platform linux/amd64 -t "$IMAGE" "$REPO/benchmarks"
mkdir -p "$REPO/benchmarks/results"

if [ "$SERIAL" -eq 1 ]; then
  docker run --rm --platform linux/amd64 \
    -v "$TARBALL:/inputs/ours.tar.gz:ro" \
    -v "$REPO/benchmarks/results:/results" \
    "$IMAGE" /bench/run_suite.sh
else
  NPROC="$(nproc)"
  if [ "$((2 * SHARDS))" -gt "$NPROC" ]; then
    echo "error: 2*$SHARDS workers need $((2 * SHARDS)) CPUs, host has $NPROC" >&2
    exit 2
  fi
  if [ "$((2 * SHARDS))" -gt 16 ]; then
    echo "warning: more than 16 workers shares SMT siblings; prefer --shards <= 8 on 16-core hosts" >&2
  fi
  # Interleaved assignment: pbs gets even CPUs, ours odd ones. Contiguous
  # halves (pbs 0-7, ours 8-15) park each interpreter on a different CCD
  # of dual-CCD hosts (e.g. Ryzen 9 9950X: CCD0 ~ cores 0-7), and the
  # better-binned CCD boosts higher -- a systematic few-% bias observed
  # in the first parallel run. Interleaving balances CCDs 50/50 per side.
  # For a published verdict, repeat with swapped halves and average.
  PBS_CPUS="$(seq 0 2 $((2 * SHARDS - 2)) | paste -sd, -)"
  OURS_CPUS="$(seq 1 2 $((2 * SHARDS - 1)) | paste -sd, -)"
  echo "shards=$SHARDS pbs_cpus=$PBS_CPUS ours_cpus=$OURS_CPUS"
  docker run --rm --platform linux/amd64 \
    --cpuset-cpus="0-$((2 * SHARDS - 1))" \
    -v "$TARBALL:/inputs/ours.tar.gz:ro" \
    -v "$REPO/benchmarks/results:/results" \
    "$IMAGE" /bench/run_parallel.sh "$SHARDS" "$PBS_CPUS" "$OURS_CPUS" /results
fi
echo "results in $REPO/benchmarks/results; compare merged pairs with:"
echo "  python3 benchmarks/compare.py benchmarks/results/pbs-314-musl-<t>.json benchmarks/results/ours-musl-<t>.json"
