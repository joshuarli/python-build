"""Measure one-shot difflib snapshot/eligibility overhead on registered tasks.

The proxy adds work before each original unified_diff generator is created.
It deliberately does not substitute a matching implementation.
"""

from __future__ import annotations

import argparse
import atexit
import difflib
import hashlib
import json
import os
from pathlib import Path
import sys

from evidence_checkpoint import checkpoint_evidence, reserve_evidence


TASKS = {"difflib_unified_mostly_equal": 500, "difflib_unified_reordered": 1000}


def task_child(side: str, task: str, iterations: int) -> None:
    original = difflib.unified_diff
    calls = 0
    elements = 0

    def proxy(a, b, *args, **kwargs):
        nonlocal calls, elements
        snapshot_a, snapshot_b = tuple(a), tuple(b)
        elements += len(snapshot_a) + len(snapshot_b)
        if not all(type(item) is str for item in snapshot_a):
            raise TypeError("ineligible a")
        if not all(type(item) is str for item in snapshot_b):
            raise TypeError("ineligible b")
        calls += 1
        return original(a, b, *args, **kwargs)

    if side == "proxy":
        difflib.unified_diff = proxy
    atexit.register(lambda: print(json.dumps({"proxy_calls": calls, "scanned_elements": elements}), file=sys.stderr))
    from benchmarks.workloads.difflib import main
    raise SystemExit(main([task, "--iterations", str(iterations)]))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def controller(args: argparse.Namespace) -> None:
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    from benchmarks.harness.process import run_command
    copies = {side: Path(path) for side, path in (("control", args.control), ("proxy", args.proxy))}
    pythons = {side: path / "bin/python3.16" for side, path in copies.items()}
    for path in pythons.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    if sha(pythons["control"]) != sha(pythons["proxy"]):
        raise RuntimeError("installed executables differ")
    env = dict(os.environ)
    env.update(PYTHONPATH=str(root), PYTHONHASHSEED="1", PYTHONNOUSERSITE="1",
               PYTHONDONTWRITEBYTECODE="1", PYTHONMALLOC="default")
    records: list[dict] = []
    cpu_total = 0.0
    reserve_evidence(args.output)

    def save() -> None:
        checkpoint_evidence(args.output, {
            "identity": {"copies": {k: str(v) for k, v in copies.items()},
                         "executable_sha256": sha(pythons["control"]),
                         "environment": {k: env[k] for k in ("PYTHONPATH", "PYTHONHASHSEED", "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE", "PYTHONMALLOC")},
                         "counts": TASKS, "child_cpu_seconds": cpu_total},
            "observations": records}, separators=(",", ":"))

    def measure(task: str, side: str, phase: str, pair: int, sample_memory: bool) -> None:
        nonlocal cpu_total
        count = TASKS[task]
        command = [str(pythons[side]), str(Path(__file__).resolve()), "task-child",
                   side, task, str(count)]
        result = run_command(command, env=env, cwd=root, timeout=60,
                             sample_interval_seconds=0.01 if sample_memory else None)
        record = result.as_dict()
        record.update(task=task, side=side, phase=phase, pair=pair)
        cpu_total += (result.cpu_user_seconds or 0) + (result.cpu_system_seconds or 0)
        try:
            payload = json.loads(record["stdout"].strip())
            assert result.returncode == 0 and not result.timed_out and result.cleanup_complete
            assert payload["operation_count"] == count
            assert payload["input_digest"] and payload["digest"]
            record["payload"] = payload
            marker = json.loads(record["stderr"].strip().splitlines()[-1])
            assert marker["proxy_calls"] == (count if side == "proxy" else 0)
            record["proxy_marker"] = marker
            if sample_memory:
                assert record["memory"] is not None
            record["status"] = "valid"
        except Exception as error:
            record["status"] = "failed"
            record["failure"] = repr(error)
        records.append(record)
        save()
        if record["status"] != "valid":
            raise RuntimeError(f"{task} {side} {phase} {pair}: {record['failure']}")
        if cpu_total > args.cpu_budget:
            raise RuntimeError(f"child CPU budget exceeded: {cpu_total:.2f}s")

    try:
        for task in TASKS:
            # Two control orders measure local timing and memory repeatability.
            phases = ((("timing_proxy_self", 3), ("memory_proxy_self", 3))
                      if args.proxy_self_only else
                      (("calibration", 2), ("timing", 5), ("memory_self", 3), ("memory", 5)))
            for phase, pairs in phases:
                if phase == "memory_self" and args.skip_memory_self:
                    continue
                for pair in range(pairs):
                    order = (("proxy", "proxy") if phase.endswith("proxy_self") else
                             ("control", "control") if "self" in phase or phase == "calibration" else
                             (("control", "proxy") if pair % 2 == 0 else ("proxy", "control")))
                    for side in order:
                        measure(task, side, phase, pair, phase.startswith("memory"))
        for task in TASKS:
            digests = {(r["payload"]["input_digest"], r["payload"]["digest"])
                       for r in records if r["task"] == task and r["status"] == "valid"}
            if len(digests) != 1:
                raise RuntimeError(f"digest mismatch for {task}: {digests}")
        save()
    finally:
        save()


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    child = sub.add_parser("task-child")
    child.add_argument("side", choices=("control", "proxy"))
    child.add_argument("task", choices=TASKS)
    child.add_argument("iterations", type=int)
    run = sub.add_parser("run")
    run.add_argument("--control", required=True)
    run.add_argument("--proxy", required=True)
    run.add_argument("--output", required=True, type=Path)
    run.add_argument("--cpu-budget", type=float, default=110)
    run.add_argument("--skip-memory-self", action="store_true")
    run.add_argument("--proxy-self-only", action="store_true")
    args = parser.parse_args()
    if args.mode == "task-child":
        task_child(args.side, args.task, args.iterations)
    else:
        controller(args)


if __name__ == "__main__":
    main()
