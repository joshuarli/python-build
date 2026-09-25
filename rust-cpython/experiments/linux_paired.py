#!/usr/bin/env python3
"""Many-pair control/candidate comparison for one registered workload.

The standard `benchmarks/bench.py run` profile takes five timing and three
memory pairs. On a shared KVM host its self-comparison noise can exceed the
effect being measured, so this driver repeats the same child command many
more times with the same harness pieces:

* children are built by `benchmarks.harness.runner.workload_command` and run
  with `workload_environment` (PYTHONHASHSEED=1, no bytecode writes, default
  allocator), pinned to one CPU;
* timing pairs use no sampler; wall time is the external monotonic duration
  and CPU is the root `wait4` user+system time, both per logical operation;
* memory pairs run separately under the 10 ms process-tree sampler and record
  peak PSS, peak private (USS: Private_Clean + Private_Dirty) and peak RSS;
* each pair alternates order (AB, BA, ...), every child's correctness digest
  must match across sides, and a warm-up child per side is discarded.

The summary reports median paired ratios with a seeded bootstrap 95%
interval. A self-comparison (the same interpreter on both sides) gives the
noise floor for the same host and pair count.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from benchmarks.harness.process import run_command  # noqa: E402
from benchmarks.harness.runner import workload_command, workload_environment  # noqa: E402
from benchmarks.workloads.registry import BY_NAME  # noqa: E402


def _run(python: Path, workload, iterations: int, cpu: int, *, memory: bool) -> dict[str, Any]:
    command = workload_command(python, workload, iterations, memory=memory)
    result = run_command(
        command, env=workload_environment(None), cwd=REPO, timeout=900,
        affinity=[cpu], sample_interval_seconds=0.01 if memory else None,
    )
    if result.returncode != 0 or result.timed_out:
        raise SystemExit(f"{python} {workload.name} failed: {result.stderr.decode()[-2000:]}")
    payload = json.loads(result.stdout.decode().strip().splitlines()[-1])
    operations = payload["operation_count"]
    row: dict[str, Any] = {
        "digest": payload["digest"],
        "operations": operations,
        "wall_seconds": result.duration_seconds,
        "wall_per_op": result.duration_seconds / operations,
        "payload_elapsed_seconds": payload.get("elapsed_seconds"),
        "cpu_coverage": result.cpu_coverage,
    }
    if result.cpu_user_seconds is not None and result.cpu_system_seconds is not None:
        row["cpu_user_seconds"] = result.cpu_user_seconds
        row["cpu_system_seconds"] = result.cpu_system_seconds
        row["cpu_per_op"] = (result.cpu_user_seconds + result.cpu_system_seconds) / operations
    if memory:
        metrics = result.memory.as_dict() if result.memory is not None else {}
        for key in ("peak_pss_bytes", "peak_private_bytes", "peak_rss_bytes",
                    "peak_process_count"):
            row[key] = metrics.get(key)
        row["sampling_errors"] = len(metrics.get("sampling_errors") or [])
        row["samples"] = len(metrics.get("samples") or [])
    return row


def _bootstrap(values: list[float], seed: int = 20260925, rounds: int = 4000) -> list[float]:
    generator = random.Random(seed)
    medians = sorted(
        statistics.median(generator.choices(values, k=len(values))) for _ in range(rounds)
    )
    return [medians[int(0.025 * rounds)], medians[int(0.975 * rounds) - 1]]


def _summary(pairs: list[dict[str, Any]], key: str, *, ratio: bool) -> dict[str, Any] | None:
    values = []
    for pair in pairs:
        baseline, candidate = pair["baseline"].get(key), pair["candidate"].get(key)
        if baseline is None or candidate is None:
            return None
        values.append(candidate / baseline if ratio else candidate - baseline)
    return {
        "kind": "candidate/baseline ratio" if ratio else "candidate-baseline difference",
        "median": statistics.median(values),
        "bootstrap95_median": _bootstrap(values),
        "min": min(values),
        "max": max(values),
        "candidate_lower_count": sum(value < (1 if ratio else 0) for value in values),
        "n": len(values),
        "values": values,
        "baseline_median": statistics.median(p["baseline"][key] for p in pairs),
        "candidate_median": statistics.median(p["candidate"][key] for p in pairs),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--workload", required=True)
    parser.add_argument("--pairs", type=int, default=20)
    parser.add_argument("--memory-pairs", type=int, default=10)
    parser.add_argument("--iterations", type=int)
    parser.add_argument("--cpu", type=int, default=(os.cpu_count() or 1) - 1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    workload = BY_NAME[args.workload]
    if workload.packages:
        raise SystemExit("packaged workloads need a prepared site; use benchmarks/bench.py")
    iterations = args.iterations or workload.iterations
    sides = {"baseline": args.baseline.resolve(), "candidate": args.candidate.resolve()}
    started = time.time()
    load_before = os.getloadavg()
    for python in sides.values():
        _run(python, workload, iterations, args.cpu, memory=False)
    timing: list[dict[str, Any]] = []
    memory: list[dict[str, Any]] = []
    for phase, count, rows in (("timing", args.pairs, timing), ("memory", args.memory_pairs, memory)):
        for index in range(count):
            order = ("baseline", "candidate") if index % 2 == 0 else ("candidate", "baseline")
            pair = {"index": index, "order": list(order)}
            for side in order:
                pair[side] = _run(sides[side], workload, iterations, args.cpu,
                                  memory=phase == "memory")
            if pair["baseline"]["digest"] != pair["candidate"]["digest"]:
                raise SystemExit(f"{workload.name}: correctness digests differ in {phase} pair {index}")
            rows.append(pair)
    report = {
        "workload": workload.name,
        "iterations": iterations,
        "operation": workload.operation,
        "baseline": str(sides["baseline"]),
        "candidate": str(sides["candidate"]),
        "self_comparison": sides["baseline"] == sides["candidate"],
        "cpu_affinity": [args.cpu],
        "host": {"platform": platform.platform(), "cpu_count": os.cpu_count(),
                 "load_before": load_before, "load_after": os.getloadavg()},
        "started_unix": started,
        "elapsed_seconds": time.time() - started,
        "digest": timing[0]["baseline"]["digest"] if timing else None,
        "summary": {
            "wall_per_op_ratio": _summary(timing, "wall_per_op", ratio=True),
            "cpu_per_op_ratio": _summary(timing, "cpu_per_op", ratio=True),
            "peak_pss_delta_bytes": _summary(memory, "peak_pss_bytes", ratio=False),
            "peak_private_delta_bytes": _summary(memory, "peak_private_bytes", ratio=False),
            "peak_rss_delta_bytes": _summary(memory, "peak_rss_bytes", ratio=False),
        },
        "timing_pairs": timing,
        "memory_pairs": memory,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    compact = {name: None if value is None else
               {k: value[k] for k in ("median", "bootstrap95_median", "candidate_lower_count", "n")}
               for name, value in report["summary"].items()}
    print(json.dumps({"workload": workload.name, "summary": compact}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
