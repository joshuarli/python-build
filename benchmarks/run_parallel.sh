#!/bin/sh
# In-container parallel driver: shard the suite across pinned workers.
#
# Usage: run_parallel.sh <shards-per-side> <pbs-cpus> <ours-cpus> [outdir]
#   e.g. run_parallel.sh 8 0,1,2,3,4,5,6,7 8,9,10,11,12,13,14,15 /results
#
# Fairness model (see README.md): each suite stays internally contention-
# free — one single-threaded benchmark per pinned real core — while the
# two interpreters run concurrently on disjoint cores with IDENTICAL
# shard contents. Per-side shards merge with `pyperf combine` into one
# JSON per interpreter for benchmarks/compare.py.
#
# Fully offline: venvs install pyperformance from /bench/vendor.
set -eu

SHARDS="${1:?usage: run_parallel.sh <shards-per-side> <pbs-cpus> <ours-cpus> [outdir]}"
PBS_CPUS="${2:?usage: run_parallel.sh <shards-per-side> <pbs-cpus> <ours-cpus> [outdir]}"
OURS_CPUS="${3:?usage: run_parallel.sh <shards-per-side> <pbs-cpus> <ours-cpus> [outdir]}"
# Benchmarks binding fixed loopback ports. Parallel shards of the two
# interpreters race for the port (observed: Errno 98 on 127.0.0.1:8882),
# so these run in a serial tail phase instead: pbs then ours. Note
# asyncio_tcp_ssl is a separate benchmark sharing asyncio_tcp's port.
SERIAL_BENCHMARKS="asyncio_tcp,asyncio_tcp_ssl,asyncio_websockets"

OUTDIR="${4:-/results}"

mkdir -p /bench/ours
if [ ! -x /bench/ours/python/bin/python3.14 ]; then
  tar -xzf /inputs/ours.tar.gz -C /bench/ours
fi
OURS=/bench/ours/python/bin/python3.14
PBS=/bench/pbs/python/bin/python3.14

"$OURS" -c "import sys; assert sys.version_info[:3] == (3, 14, 6), sys.version_info"
"$PBS" -c "import sys; assert sys.version_info[:3] == (3, 14, 6), sys.version_info"

# One shared venv per interpreter, built once up front (offline).
for pair in "pbs:$PBS" "ours:$OURS"; do
  id="${pair%%:*}"; py="${pair#*:}"
  if [ ! -x "/bench/$id-env/bin/pyperformance" ]; then
    "$py" -m venv "/bench/$id-env"
    "/bench/$id-env/bin/python" -m pip install --no-index \
        --find-links /bench/vendor "pyperformance==1.14.0"
  fi
done

# Pre-warm worker venvs serially. Each `pyperformance run` first ensures a
# shared per-interpreter worker venv (/venv/...); concurrent invocations
# race on creating it. One tiny benchmark per interpreter is enough: the
# common venv is per-interpreter, and per-benchmark venvs are
# shard-disjoint by construction, so nothing else is shared.
for pair in "pbs:$PBS" "ours:$OURS"; do
  id="${pair%%:*}"; py="${pair#*:}"
  /bench/run_single.sh "warmup-$id" "$py" /tmp \
      --benchmarks python_startup --venv "/bench/$id-env" > /tmp/warmup-"$id".log 2>&1
done
rm -f /tmp/warmup-pbs-*.json /tmp/warmup-ours-*.json

# Enumerate the suite once (pinned pyperformance: same list for both sides).
/bench/pbs-env/bin/pyperformance list | sed -n 's/^- //p' > /tmp/benchmarks.txt
wc -l /tmp/benchmarks.txt
/bench/pbs-env/bin/python /bench/shard.py /tmp/benchmarks.txt \
    --shards "$SHARDS" --exclude "$SERIAL_BENCHMARKS" > /tmp/shards.txt

STAMP="$(date +%Y-%m-%dT%H%M%S)"
mkdir -p "$OUTDIR/$STAMP"
i=0
pids=""
fail=0
while IFS= read -r csv; do
  i=$((i + 1))
  pbs_cpu="$(echo "$PBS_CPUS" | cut -d, -f"$i")"
  ours_cpu="$(echo "$OURS_CPUS" | cut -d, -f"$i")"
  [ -n "$pbs_cpu" ] || { echo "not enough PBS cpus for $SHARDS shards" >&2; exit 2; }
  [ -n "$ours_cpu" ] || { echo "not enough ours cpus for $SHARDS shards" >&2; exit 2; }
  /bench/run_single.sh "pbs-314-musl-s$i" "$PBS" "$OUTDIR/$STAMP" \
      --benchmarks "$csv" --affinity "$pbs_cpu" --venv /bench/pbs-env &
  pids="$pids $!"
  /bench/run_single.sh "ours-musl-s$i" "$OURS" "$OUTDIR/$STAMP" \
      --benchmarks "$csv" --affinity "$ours_cpu" --venv /bench/ours-env &
  pids="$pids $!"
done < /tmp/shards.txt

for pid in $pids; do
  if ! wait "$pid"; then fail=1; fi
done
if [ "$fail" -ne 0 ]; then echo "a shard failed" >&2; exit 1; fi

# Serial tail for fixed-port benchmarks (see SERIAL_BENCHMARKS): pbs then
# ours, pinned to each side's first core. No contention: nothing else runs.
FIRST_PBS_CPU="$(echo "$PBS_CPUS" | cut -d, -f1)"
FIRST_OURS_CPU="$(echo "$OURS_CPUS" | cut -d, -f1)"
/bench/run_single.sh "pbs-314-musl-serial" "$PBS" "$OUTDIR/$STAMP" \
    --benchmarks "$SERIAL_BENCHMARKS" --affinity "$FIRST_PBS_CPU" --venv /bench/pbs-env
/bench/run_single.sh "ours-musl-serial" "$OURS" "$OUTDIR/$STAMP" \
    --benchmarks "$SERIAL_BENCHMARKS" --affinity "$FIRST_OURS_CPU" --venv /bench/ours-env

# Merge per-side shards into one JSON per interpreter (pooling values).
for side in pbs-314-musl ours-musl; do
  # shellcheck disable=SC2086
  /bench/pbs-env/bin/python /bench/pool.py \
      "$OUTDIR/$side-$STAMP.json" $OUTDIR/$STAMP/$side-*.json
done
echo "merged: $OUTDIR/pbs-314-musl-$STAMP.json $OUTDIR/ours-musl-$STAMP.json"
# Snapshot benchmark payload versions actually installed in worker venvs
# (pyperformance pins most, transitive deps float): provenance for the
# merged pair, sourced from this run's logs only.
grep -hoE "^[A-Za-z0-9_.-]+==[A-Za-z0-9_.+-]+$" "$OUTDIR/$STAMP"/log-*.txt \
  | sort -u > "$OUTDIR/payload-versions-$STAMP.txt"
