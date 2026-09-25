"""Record paired zlib workload diagnostics while the host is externally loaded."""

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from evidence_checkpoint import checkpoint_evidence, reserve_evidence


ROOT = Path(__file__).resolve().parents[2]
LANE = Path(__file__).resolve().parents[1]
FIXTURE = LANE / "work" / "variants" / "zlib-adaptive" / "identity" / "mixedblobs.sqlite"
PYCACHE = LANE / "work" / "variants" / "zlib-adaptive" / "loaded-pairs-pycache-absent"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(name: str, arm: str, python: Path, arguments: list[str]) -> dict[str, object]:
    env = os.environ.copy()
    for key in list(env):
        if key in {"PYTHONPATH", "PYTHONHOME", "PYTHONPYCACHEPREFIX"} or key.startswith("DYLD_"):
            env.pop(key)
    env.update(PYTHONHASHSEED="1", PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1",
               PYTHONMALLOC="default", PYTHONPYCACHEPREFIX=str(PYCACHE))
    argv = ["/usr/bin/time", "-l", "-p", str(python), *arguments]
    result = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True)
    record: dict[str, object] = {"id": name, "arm": arm, "returncode": result.returncode}
    fields = {}
    for label, pattern in {
        "external_wall_seconds": r"(?m)^real ([0-9.]+)$",
        "kernel_user_seconds": r"(?m)^user ([0-9.]+)$",
        "kernel_system_seconds": r"(?m)^sys ([0-9.]+)$",
        "max_rss_bytes": r"(?m)^\s*(\d+)\s+maximum resident set size$",
        "peak_footprint_bytes": r"(?m)^\s*(\d+)\s+peak memory footprint$",
        "swaps": r"(?m)^\s*(\d+)\s+swaps$",
    }.items():
        match = re.search(pattern, result.stderr)
        if match is None:
            record["failure"] = {"reason": f"missing {label}",
                                 "stdout": result.stdout[-1000:], "stderr": result.stderr[-1000:]}
            return record
        fields[label] = float(match.group(1)) if label.endswith("seconds") else int(match.group(1))
    record["resources"] = fields
    if result.returncode:
        record["failure"] = {"stdout": result.stdout[-1000:], "stderr": result.stderr[-1000:]}
        return record
    try:
        record["output"] = json.loads(result.stdout)
    except json.JSONDecodeError:
        record["failure"] = {"reason": "invalid JSON output",
                             "stdout": result.stdout[-1000:], "stderr": result.stderr[-1000:]}
    return record


def swap() -> str:
    return subprocess.check_output(["sysctl", "-n", "vm.swapusage"], text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--control", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    reserve_evidence(args.output)
    if PYCACHE.exists():
        raise RuntimeError("the common no-write cache prefix already exists")
    if digest(FIXTURE) != "dd3f25573c9307a466c9e1d374d698d242a3c7249fac691c18d5177ce891a2df":
        raise RuntimeError("mixed SQLite fixture changed")
    tasks = {
        "decode_1m": ["-m", "benchmarks.workloads.zlib", "zlib_decode_1m", "--iterations", "1707"],
        "mixedblobs": ["rust-cpython/experiments/zlib_oneshot_mixedblobs.py", "read", str(FIXTURE), "--loops", "604"],
    }
    before_swap = swap()
    evidence = {"kind": "loaded-host diagnostic only; not quiet-host speed or memory acceptance",
                "recipe": "python3.14 rust-cpython/experiments/zlib_adaptive_loaded_pairs.py --candidate <adaptive-stage-python> --control <same-branch-platform-stage-python> --output <fresh-evidence.json>",
                "control_python_sha256": digest(args.control),
                "candidate_python_sha256": digest(args.candidate),
                "fixture_sha256": digest(FIXTURE),
                "environment": {"PYTHONHASHSEED": "1", "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONMALLOC": "default", "PYTHONPYCACHEPREFIX": "common absent no-write prefix", "PYTHONPATH": None, "PYTHONHOME": None, "DYLD_*": None},
                "host_swap_before": before_swap,
                "resource_coverage": "Each task process had no descendants; /usr/bin/time -l accounts for its kernel user/system CPU, peak RSS, footprint, and swaps. CPU resolves to 0.01 s. No memory sampler ran.",
                "pairs": []}
    checkpoint_evidence(args.output, evidence, sort_keys=True)
    for task, command in tasks.items():
        for kind, count in (("self", 3), ("candidate", 5)):
            for index in range(1, count + 1):
                order = ("control", "control") if kind == "self" else (
                    ("control", "candidate") if index % 2 else ("candidate", "control"))
                pair = {"task": task, "kind": kind, "pair": index,
                        "order": list(order), "attempts": []}
                evidence["pairs"].append(pair)
                for position, arm in enumerate(order, 1):
                    attempt = run(f"{task}-{kind}-{index}-{position}", arm,
                                  args.candidate if arm == "candidate" else args.control,
                                  command)
                    pair["attempts"].append(attempt)
                    checkpoint_evidence(args.output, evidence, sort_keys=True)
                    if "failure" in attempt:
                        raise RuntimeError(f"{attempt['id']} failed; see {args.output}")
                attempts = pair["attempts"]
                outputs = [{key: value for key, value in attempt["output"].items()
                            if key != "elapsed_seconds"} for attempt in attempts]
                if outputs[0] != outputs[1]:
                    pair["output_match"] = False
                    checkpoint_evidence(args.output, evidence, sort_keys=True)
                    raise RuntimeError(f"{task} output mismatch in {kind} pair {index}")
                pair["output_match"] = True
                checkpoint_evidence(args.output, evidence, sort_keys=True)
    if PYCACHE.exists():
        raise RuntimeError("no-write cache prefix was unexpectedly created")
    evidence["host_swap_after"] = swap()
    checkpoint_evidence(args.output, evidence, sort_keys=True)
    print(args.output)


if __name__ == "__main__":
    main()
