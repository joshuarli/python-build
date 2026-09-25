"""Collect serial complete-task timing in one checkpointed evidence file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evidence_checkpoint import checkpoint_evidence, reserve_evidence


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
WORK = ROOT / "rust-cpython/work/url-unquote-proof-20260925a"
BENCH = HERE / "bench.py"
RESOURCE_FIELDS = {
    "external_wall_seconds": r"(?m)^real ([0-9.]+)$",
    "kernel_user_seconds": r"(?m)^user ([0-9.]+)$",
    "kernel_system_seconds": r"(?m)^sys ([0-9.]+)$",
    "max_rss_bytes": r"(?m)^\s*(\d+)\s+maximum resident set size$",
    "peak_footprint_bytes": r"(?m)^\s*(\d+)\s+peak memory footprint$",
    "swaps": r"(?m)^\s*(\d+)\s+swaps$",
}


def run(name: str, side: str, task: str, count: int) -> dict[str, object]:
    command = ["/usr/bin/time", "-l", "-p", "env", "-i", f"PYTHONPATH={ROOT}",
               "PYTHONDONTWRITEBYTECODE=1", "PYTHONHASHSEED=1",
               str(WORK / side / "bin/python3.16"), str(BENCH), side, task, str(count)]
    completed = subprocess.run(command, capture_output=True, text=True)
    record: dict[str, object] = {"id": name, "side": side, "returncode": completed.returncode}
    resources = {}
    for field, pattern in RESOURCE_FIELDS.items():
        match = re.search(pattern, completed.stderr)
        if match is None:
            record["failure"] = {"reason": f"missing {field}",
                                 "stdout": completed.stdout[-1000:],
                                 "stderr": completed.stderr[-1000:]}
            return record
        resources[field] = float(match.group(1)) if field.endswith("seconds") else int(match.group(1))
    record["resources"] = resources
    if completed.returncode:
        record["failure"] = {"stdout": completed.stdout[-1000:],
                             "stderr": completed.stderr[-1000:]}
        return record
    try:
        record["output"] = json.loads(completed.stdout)
    except json.JSONDecodeError:
        record["failure"] = {"reason": "invalid JSON output",
                             "stdout": completed.stdout[-1000:],
                             "stderr": completed.stderr[-1000:]}
        return record
    try:
        record["output"]["result"]["elapsed_seconds"]
    except (KeyError, TypeError):
        record["failure"] = {"reason": "missing elapsed_seconds in output",
                             "stdout": completed.stdout[-1000:]}
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task")
    parser.add_argument("count", type=int)
    parser.add_argument("label")
    parser.add_argument("--output", required=True, type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--candidate-self-only", action="store_true")
    modes.add_argument("--matched-control", action="store_true")
    args = parser.parse_args()
    reserve_evidence(args.output)
    tag = ("search" if args.task == "catalog_search_form" else "normalize") + "-" + args.label
    control = "matched-control" if args.matched_control else "control"
    evidence: dict[str, object] = {
        "recipe": "python3 rust-cpython/experiments/url-unquote-proof/timing.py TASK COUNT LABEL --output <fresh-evidence.json> [--candidate-self-only|--matched-control]",
        "task": args.task, "count": args.count, "label": args.label,
        "mode": "candidate-self-only" if args.candidate_self_only else (
            "matched-control" if args.matched_control else "control"),
        "attempts": [],
    }
    checkpoint_evidence(args.output, evidence, sort_keys=True)

    def attempt(name: str, side: str) -> None:
        record = run(name, side, args.task, args.count)
        evidence["attempts"].append(record)
        checkpoint_evidence(args.output, evidence, sort_keys=True)
        if "failure" in record:
            raise RuntimeError(f"attempt failed: {name}; see {args.output}")
        print(name, record["output"]["result"]["elapsed_seconds"], flush=True)

    for pair in range(1, 6):
        side = "candidate" if args.candidate_self_only else control
        attempt(f"{tag}-self-{pair}-a", side)
        attempt(f"{tag}-self-{pair}-b", side)
    if args.candidate_self_only:
        return
    for pair in range(1, 6):
        order = (control, "candidate") if pair % 2 else ("candidate", control)
        for position, side in enumerate(order, 1):
            attempt(f"{tag}-paired-{pair}-{position}-{side}", side)


if __name__ == "__main__":
    main()
