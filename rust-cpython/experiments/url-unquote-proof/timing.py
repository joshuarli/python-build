"""Collect serial complete-task timing with unique raw child records."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
WORK = ROOT / "rust-cpython/work/url-unquote-proof-20260925a"
BENCH = HERE / "bench.py"


def run(name: str, side: str, task: str, count: int) -> None:
    stem = WORK / name
    if any(stem.with_suffix(suffix).exists() for suffix in (".json", ".stderr", ".time")):
        raise RuntimeError(f"attempt already exists: {name}")
    command = ["/usr/bin/time", "-l", "-o", str(stem.with_suffix(".time")),
               "env", "-i", f"PYTHONPATH={ROOT}", "PYTHONDONTWRITEBYTECODE=1",
               "PYTHONHASHSEED=1", str(WORK / side / "bin/python3.16"),
               str(BENCH), side, task, str(count)]
    with stem.with_suffix(".json").open("w") as output, stem.with_suffix(".stderr").open("w") as error:
        completed = subprocess.run(command, stdout=output, stderr=error)
    if completed.returncode:
        raise RuntimeError(f"attempt failed: {name}: {completed.returncode}")
    result = json.loads(stem.with_suffix(".json").read_text())
    print(name, result["result"]["elapsed_seconds"], flush=True)


def main() -> None:
    task, count_text, label, *options = sys.argv[1:]
    candidate_self_only = options == ["--candidate-self-only"]
    matched_control = options == ["--matched-control"]
    if options and not (candidate_self_only or matched_control):
        raise SystemExit("usage: timing.py TASK COUNT LABEL [--candidate-self-only|--matched-control]")
    count = int(count_text)
    tag = ("search" if task == "catalog_search_form" else "normalize") + "-" + label
    control = "matched-control" if matched_control else "control"
    for pair in range(1, 6):
        side = "candidate" if candidate_self_only else control
        run(f"{tag}-self-{pair}-a", side, task, count)
        run(f"{tag}-self-{pair}-b", side, task, count)
    if candidate_self_only:
        return
    for pair in range(1, 6):
        order = (control, "candidate") if pair % 2 else ("candidate", control)
        for position, side in enumerate(order, 1):
            run(f"{tag}-paired-{pair}-{position}-{side}", side, task, count)


if __name__ == "__main__":
    main()
