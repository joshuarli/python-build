"""Record serial public UUID indexing and cold import process measurements."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from evidence_checkpoint import checkpoint_evidence, reserve_evidence


LANE = Path(__file__).resolve().parents[1]
WORKLOAD = LANE / "experiments/uuid_canonical_workload.py"
TIME = re.compile(r"^real ([\d.]+)\nuser ([\d.]+)\nsys ([\d.]+)$", re.M)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def field(stderr: str, label: str) -> int:
    match = re.search(r"^\s*(\d+)\s+" + re.escape(label) + r"$", stderr, re.M)
    if match is None:
        raise ValueError(f"missing kernel field {label}")
    return int(match.group(1))


def attempt(family: str, kind: str, pair: int, position: int, side: str, stage: Path,
            env: dict[str, str]) -> dict:
    python = stage / "bin/python3.16"
    command = ([str(python), "-S", "-B", "-c", "import uuid"]
               if kind == "cold-import" else
               [str(python), "-B", str(WORKLOAD), "--count", "50000", "--rounds", "2"])
    started = time.perf_counter()
    result = subprocess.run(["/usr/bin/time", "-l", "-p", *command],
                            capture_output=True, text=True, env=env)
    record = {"id": f"{family}-{pair:02d}-{position:02d}-{side}",
              "family": family, "kind": kind, "pair": pair,
              "position": position, "side": side,
              "returncode": result.returncode, "wall_seconds": time.perf_counter() - started}
    match = TIME.search(result.stderr)
    if match:
        record.update(kernel_real_seconds=float(match.group(1)),
                      user_seconds=float(match.group(2)),
                      system_seconds=float(match.group(3)),
                      peak_rss_bytes=field(result.stderr, "maximum resident set size"),
                      peak_footprint_bytes=field(result.stderr, "peak memory footprint"),
                      swaps=field(result.stderr, "swaps"))
    if result.returncode == 0:
        record["output"] = (json.loads(result.stdout) if kind == "uuid-index" else
                            {"empty_stdout": result.stdout == ""})
    else:
        record["failure"] = {"stdout": result.stdout[-800:],
                             "stderr": result.stderr[-1200:]}
    return record


def main(control: Path, candidate: Path, output: Path) -> None:
    reserve_evidence(output)
    env = os.environ.copy()
    for key in tuple(env):
        if key in ("PYTHONPATH", "PYTHONPYCACHEPREFIX") or key.startswith("DYLD_"):
            env.pop(key)
    cache = LANE / "work/uuid-empty-pycache"
    cache.mkdir(parents=True, exist_ok=True)
    if any(cache.iterdir()):
        raise ValueError("measurement pycache prefix must be empty")
    env.update(PYTHONHASHSEED="1", PYTHONNOUSERSITE="1",
               PYTHONDONTWRITEBYTECODE="1", PYTHONPYCACHEPREFIX=str(cache))
    evidence = {"recipe": {
        "workload": "uuid_canonical_workload.py --count 50000 --rounds 2",
        "workload_sha256": digest(WORKLOAD),
        "control_interpreter_sha256": digest(control / "bin/python3.16"),
        "candidate_interpreter_sha256": digest(candidate / "bin/python3.16"),
        "control_uuid_sha256": digest(control / "lib/python3.16/uuid.py"),
        "candidate_uuid_sha256": digest(candidate / "lib/python3.16/uuid.py"),
        "candidate_extension_sha256": digest(next((candidate / "lib/python3.16/lib-dynload").glob("_rust_uuid_canonical*.so"))),
        "measurement": "/usr/bin/time -l -p around direct Python child, with parent perf_counter wall; Darwin wait4 kernel child usage",
        "cache_policy": "empty PYTHONPYCACHEPREFIX, PYTHONDONTWRITEBYTECODE=1, -B; both sides compile source",
        "environment": {key: env[key] for key in ("PYTHONHASHSEED", "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE")},
        "order": "three self pairs, five alternating comparison pairs, five alternating cold import pairs",
    }, "host_swap_before": subprocess.check_output(["sysctl", "vm.swapusage"], text=True).strip(),
       "host_load_before": subprocess.check_output(["uptime"], text=True).strip(),
       "attempts": []}
    try:
        expected = None
        for kind, count in (("self", 3), ("uuid-index", 5), ("cold-import", 5)):
            for pair in range(1, count + 1):
                sides = (("control", "control") if kind == "self" else
                         (("control", "candidate") if pair % 2 else ("candidate", "control")))
                for position, side in enumerate(sides, 1):
                    stage = control if side == "control" else candidate
                    record = attempt(kind, "uuid-index" if kind == "self" else kind,
                                     pair, position, side, stage, env)
                    evidence["attempts"].append(record)
                    checkpoint_evidence(output, evidence)
                    if record["returncode"] != 0:
                        raise RuntimeError(f"attempt {record['id']} failed")
                    if kind != "cold-import":
                        if expected is None:
                            expected = record["output"]
                        elif record["output"] != expected:
                            raise RuntimeError(f"attempt {record['id']} output differs")
    except Exception as error:
        evidence["failure"] = str(error)
        raise
    finally:
        evidence["host_swap_after"] = subprocess.check_output(["sysctl", "vm.swapusage"], text=True).strip()
        evidence["host_load_after"] = subprocess.check_output(["uptime"], text=True).strip()
        checkpoint_evidence(output, evidence)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("control", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    main(args.control, args.candidate, args.output)
