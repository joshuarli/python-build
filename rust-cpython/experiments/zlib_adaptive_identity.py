"""Record output identity and process resources without speed comparisons."""

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LANE = Path(__file__).resolve().parents[1]
LOGS = LANE / "logs" / "variants" / "zlib-adaptive" / "identity"
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
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / f"{name}.stdout").write_text(result.stdout)
    (LOGS / f"{name}.stderr").write_text(result.stderr)
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
            raise RuntimeError(f"missing {label} from {name} resource record")
        fields[label] = float(match.group(1)) if label.endswith("seconds") else int(match.group(1))
    if result.returncode:
        raise RuntimeError(f"{name} exited {result.returncode}: {result.stderr[-300:]}")
    return {"id": name, "arguments": args, "returncode": result.returncode,
            "output": json.loads(result.stdout), "resources": fields}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--control", required=True, type=Path)
    args = parser.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    pairs = []
    seed_records = []
    tasks = [
        ("decode_1m", ["-m", "benchmarks.workloads.zlib", "zlib_decode_1m", "--iterations", "1"]),
    ]
    for name in ("smallblobs", "mixedblobs"):
        script = f"rust-cpython/experiments/zlib_oneshot_{name}.py"
        fixture = WORK / f"{name}.sqlite"
        fixture.unlink(missing_ok=True)
        seed_records.append(run(f"seed_{name}", args.control, [script, "seed", str(fixture)]))
        tasks.append((name, [script, "read", str(fixture), "--loops", "1"]))
    for name, command in tasks:
        control = run(f"control_{name}", args.control, command)
        candidate = run(f"candidate_{name}", args.candidate, command)
        if {k: v for k, v in control["output"].items() if k != "elapsed_seconds"} != {k: v for k, v in candidate["output"].items() if k != "elapsed_seconds"}:
            raise RuntimeError(f"{name} output differs")
        pairs.append({"task": name, "output_match": True, "control": control,
                      "candidate": candidate})
    print(json.dumps({"kind": "loaded-host output identity; elapsed fields are not speed evidence",
                      "recipe": "python3.14 rust-cpython/experiments/zlib_adaptive_identity.py --candidate <adaptive-stage-python> --control <pinned-fork-platform-python>",
                      "candidate_python_sha256": digest(args.candidate),
                      "control_python_sha256": digest(args.control),
                      "environment": {"PYTHONHASHSEED": "1", "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": None, "PYTHONHOME": None, "DYLD_*": None},
                      "fixtures": {name: digest(WORK / f"{name}.sqlite") for name in ("smallblobs", "mixedblobs")},
                      "seeds": seed_records, "pairs": pairs}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
