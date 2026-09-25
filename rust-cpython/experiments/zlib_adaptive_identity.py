"""Record output identity and process resources without speed comparisons."""

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
WORK = LANE / "work" / "variants" / "zlib-adaptive" / "identity"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(name: str, python: Path, args: list[str]) -> dict[str, object]:
    env = os.environ.copy()
    for key in list(env):
        if key in {"PYTHONPATH", "PYTHONHOME"} or key.startswith("DYLD_"):
            env.pop(key)
    env.update(PYTHONHASHSEED="1", PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
    argv = ["/usr/bin/time", "-l", "-p", str(python), *args]
    result = subprocess.run(argv, cwd=ROOT, env=env, text=True, capture_output=True)
    record: dict[str, object] = {"id": name, "returncode": result.returncode}
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--control", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    reserve_evidence(args.output)
    WORK.mkdir(parents=True, exist_ok=True)
    evidence = {"kind": "loaded-host output identity; elapsed fields are not speed evidence",
                "recipe": "python3.14 rust-cpython/experiments/zlib_adaptive_identity.py --candidate <adaptive-stage-python> --control <pinned-fork-platform-python> --output <fresh-evidence.json>",
                "candidate_python_sha256": digest(args.candidate),
                "control_python_sha256": digest(args.control),
                "environment": {"PYTHONHASHSEED": "1", "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": None, "PYTHONHOME": None, "DYLD_*": None},
                "seeds": [], "pairs": []}
    checkpoint_evidence(args.output, evidence, sort_keys=True)
    tasks = [
        ("decode_1m", ["-m", "benchmarks.workloads.zlib", "zlib_decode_1m", "--iterations", "1"]),
    ]
    for name in ("smallblobs", "mixedblobs"):
        script = f"rust-cpython/experiments/zlib_oneshot_{name}.py"
        fixture = WORK / f"{name}.sqlite"
        fixture.unlink(missing_ok=True)
        seed = run(f"seed_{name}", args.control, [script, "seed", str(fixture)])
        evidence["seeds"].append(seed)
        checkpoint_evidence(args.output, evidence, sort_keys=True)
        if "failure" in seed:
            raise RuntimeError(f"{seed['id']} failed; see {args.output}")
        tasks.append((name, [script, "read", str(fixture), "--loops", "1"]))
    for name, command in tasks:
        pair = {"task": name}
        evidence["pairs"].append(pair)
        control = run(f"control_{name}", args.control, command)
        pair["control"] = control
        checkpoint_evidence(args.output, evidence, sort_keys=True)
        if "failure" in control:
            raise RuntimeError(f"{control['id']} failed; see {args.output}")
        candidate = run(f"candidate_{name}", args.candidate, command)
        pair["candidate"] = candidate
        checkpoint_evidence(args.output, evidence, sort_keys=True)
        if "failure" in candidate:
            raise RuntimeError(f"{candidate['id']} failed; see {args.output}")
        if {k: v for k, v in control["output"].items() if k != "elapsed_seconds"} != {k: v for k, v in candidate["output"].items() if k != "elapsed_seconds"}:
            pair["output_match"] = False
            checkpoint_evidence(args.output, evidence, sort_keys=True)
            raise RuntimeError(f"{name} output differs")
        pair["output_match"] = True
        checkpoint_evidence(args.output, evidence, sort_keys=True)
    evidence["fixtures"] = {name: digest(WORK / f"{name}.sqlite") for name in ("smallblobs", "mixedblobs")}
    checkpoint_evidence(args.output, evidence, sort_keys=True)
    print(args.output)


if __name__ == "__main__":
    main()
