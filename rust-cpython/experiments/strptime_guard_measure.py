"""Compare source-only numeric strptime guards on one pinned interpreter."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "rust-cpython/work"
PYTHON = Path(os.environ.get(
    "STRPTIME_GUARD_BASE_PYTHON",
    ROOT / "rust-cpython/stage-fraction-rational/bin/python3.16",
))
INSTALLED_PYTHON = ROOT / "rust-cpython/stage-strptime-guard/bin/python3.16"
WORKLOAD = ROOT / "rust-cpython/experiments/strptime_numeric_workload.py"
OUTPUT = ROOT / "rust-cpython/experiments/data/strptime-guard-20260925.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def swap() -> str:
    return subprocess.run(
        ["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True, check=True
    ).stdout.strip()


def measure(side: str, number: int, position: int,
            python: Path = PYTHON) -> dict[str, object]:
    source = WORK / f"strptime-guard-{side}/Lib"
    env = os.environ.copy()
    env.update(
        PYTHONPATH=str(source),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONNOUSERSITE="1",
        PYTHONHASHSEED="1",
    )
    if side == "installed":
        env.pop("PYTHONPATH")
    if python == INSTALLED_PYTHON:
        env["PYTHONPYCACHEPREFIX"] = str(WORK / "strptime-empty-pycache")
    command = [
        "/usr/bin/time", "-l", "-p", str(python), "-S", "-B", str(WORKLOAD),
        "--count", "30000", "--rounds", "2",
    ]
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    fields = {}
    for label, pattern in {
        "wall_seconds": r"^real ([0-9.]+)$",
        "user_seconds": r"^user ([0-9.]+)$",
        "system_seconds": r"^sys ([0-9.]+)$",
        "peak_rss_bytes": r"^\s*(\d+)  maximum resident set size$",
        "swaps": r"^\s*(\d+)  swaps$",
        "peak_footprint_bytes": r"^\s*(\d+)  peak memory footprint$",
    }.items():
        match = re.search(pattern, result.stderr, re.MULTILINE)
        fields[label] = float(match.group(1)) if label.endswith("seconds") and match else (
            int(match.group(1)) if match else None
        )
    return {
        "id": f"{number:02d}-{position:02d}-{side}",
        "side": side,
        "returncode": result.returncode,
        "output": json.loads(result.stdout) if result.returncode == 0 else result.stdout,
        "failure": result.stderr if result.returncode else None,
        **fields,
    }


def main() -> None:
    attempts = []
    pairs = []
    before = swap()
    for number in range(1, 6):
        order = ("old", "audit") if number % 2 else ("audit", "old")
        ids = []
        for position, side in enumerate(order, 1):
            entry = measure(side, number, position)
            attempts.append(entry)
            ids.append(entry["id"])
        pairs.append(ids)
    old = WORK / "strptime-guard-old/Lib/_strptime.py"
    audit = WORK / "strptime-guard-audit/Lib/_strptime.py"
    report = {
        "kind": "source-override complete-workload diagnostic under unrelated host CPU load",
        "recipe": {
            "command": "stage python3.16 -S -B strptime_numeric_workload.py --count 30000 --rounds 2",
            "measurement": "/usr/bin/time -l -p; each process includes startup and 60000 public parses",
            "environment": {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "PYTHONHASHSEED": "1"},
            "interpreter_sha256": digest(PYTHON),
            "old_source_sha256": digest(old),
            "audit_source_sha256": digest(audit),
            "workload_sha256": digest(WORKLOAD),
        },
        "host_swap_before": before,
        "host_swap_after": swap(),
        "pairs": pairs,
        "attempts": attempts,
    }
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n")
    print(OUTPUT)


def append_control_comparison() -> None:
    report = json.loads(OUTPUT.read_text())
    before = swap()
    pairs = []
    for number in range(1, 6):
        order = ("control", "audit") if number % 2 else ("audit", "control")
        ids = []
        for position, side in enumerate(order, 1):
            entry = measure(side, number, position)
            entry["id"] = "control-comparison-" + entry["id"]
            report["attempts"].append(entry)
            ids.append(entry["id"])
        pairs.append(ids)
    report["control_comparison"] = {
        "source_sha256": digest(WORK / "strptime-guard-control/Lib/_strptime.py"),
        "host_swap_before": before,
        "host_swap_after": swap(),
        "pairs": pairs,
    }
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n")
    print(OUTPUT)


def append_installed_comparison() -> None:
    report = json.loads(OUTPUT.read_text())
    before = swap()
    pairs = []
    for number in range(1, 4):
        order = ("control", "installed") if number % 2 else ("installed", "control")
        ids = []
        for position, side in enumerate(order, 1):
            entry = measure(side, number, position, INSTALLED_PYTHON)
            entry["id"] = "final-installed-comparison-" + entry["id"]
            report["attempts"].append(entry)
            ids.append(entry["id"])
        pairs.append(ids)
    report["installed_comparison_final"] = {
        "interpreter_sha256": digest(INSTALLED_PYTHON),
        "installed_source_sha256": digest(ROOT / "rust-cpython/stage-strptime-guard/lib/python3.16/_strptime.py"),
        "host_swap_before": before,
        "host_swap_after": swap(),
        "pairs": pairs,
        "cache_policy": "-S -B; PYTHONDONTWRITEBYTECODE=1; empty worktree-local PYTHONPYCACHEPREFIX for both arms",
    }
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n")
    print(OUTPUT)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--append-control", action="store_true")
    parser.add_argument("--append-installed", action="store_true")
    arguments = parser.parse_args()
    if arguments.append_installed:
        append_installed_comparison()
    elif arguments.append_control:
        append_control_comparison()
    else:
        main()
