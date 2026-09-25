"""Record complete-process numeric timestamp workload comparisons."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from evidence_checkpoint import checkpoint_evidence, reserve_evidence


ROOT = Path(__file__).resolve().parents[2]
WORKLOAD = ROOT / "rust-cpython/experiments/strptime_numeric_workload.py"
DATA = ROOT / "rust-cpython/experiments/data/strptime-numeric-20260925.json"
TIME = re.compile(r"^real ([\d.]+)\nuser ([\d.]+)\nsys ([\d.]+)$", re.M)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def field(stderr: str, label: str) -> int:
    match = re.search(r"^\s*(\d+)\s+" + re.escape(label) + r"$", stderr, re.M)
    if match is None:
        raise ValueError(f"missing kernel field {label}")
    return int(match.group(1))


def attempt(family: str, pair: int, position: int, side: str,
            env: dict[str, str], control: Path, candidate: Path) -> dict:
    stage = control if side == "control" else candidate
    python = stage / "bin/python3.16"
    kind = "cold-import" if family == "cold" else "log-ingest"
    command = ([str(python), "-S", "-B", "-c", "import datetime, _strptime"]
               if kind == "cold-import" else
               [str(python), "-B", str(WORKLOAD), "--count", "30000", "--rounds", "2"])
    started = time.perf_counter()
    result = subprocess.run(["/usr/bin/time", "-l", "-p", *command],
                            capture_output=True, text=True, env=env)
    record = {"id": f"{family}-{pair:02d}-{position:02d}-{side}",
              "family": family, "pair": pair, "position": position,
              "side": side, "kind": kind, "returncode": result.returncode,
              "wall_seconds": time.perf_counter() - started}
    match = TIME.search(result.stderr)
    if match:
        record.update(kernel_real_seconds=float(match.group(1)),
                      user_seconds=float(match.group(2)),
                      system_seconds=float(match.group(3)),
                      peak_rss_bytes=field(result.stderr, "maximum resident set size"),
                      peak_footprint_bytes=field(result.stderr, "peak memory footprint"),
                      swaps=field(result.stderr, "swaps"))
    if result.returncode == 0:
        if kind == "cold-import":
            record["output"] = {"empty_stdout": result.stdout == ""}
        else:
            try:
                record["output"] = json.loads(result.stdout)
            except json.JSONDecodeError:
                record["failure"] = {"reason": "invalid output JSON", "stdout": result.stdout[-800:]}
    else:
        record["failure"] = {"stdout": result.stdout[-800:],
                             "stderr": result.stderr[-1200:]}
    return record


def main(control: Path, candidate: Path, output: Path, *, source_evidence: Path | None = None,
         self_only: bool = False) -> None:
    if source_evidence is not None and not source_evidence.exists():
        raise FileNotFoundError(source_evidence)
    reserve_evidence(output)
    env = os.environ.copy()
    for key in tuple(env):
        if key in ("PYTHONPATH", "PYTHONPYCACHEPREFIX") or key.startswith("DYLD_"):
            env.pop(key)
    cache = ROOT / "rust-cpython/work/strptime-empty-pycache"
    cache.mkdir(parents=True, exist_ok=True)
    if any(cache.iterdir()):
        raise ValueError("measurement pycache prefix must be empty")
    env.update(PYTHONHASHSEED="1", PYTHONNOUSERSITE="1",
               PYTHONDONTWRITEBYTECODE="1", PYTHONPYCACHEPREFIX=str(cache))
    evidence = json.loads(source_evidence.read_text()) if source_evidence else {
        "recipe": {
            "workload": "strptime_numeric_workload.py --count 30000 --rounds 2",
            "workload_sha256": digest(WORKLOAD),
            "control_interpreter_sha256": digest(control / "bin/python3.16"),
            "candidate_interpreter_sha256": digest(candidate / "bin/python3.16"),
            "control_strptime_sha256": digest(control / "lib/python3.16/_strptime.py"),
            "candidate_strptime_sha256": digest(candidate / "lib/python3.16/_strptime.py"),
            "candidate_extension_sha256": digest(next((candidate / "lib/python3.16/lib-dynload").glob("_rust_strptime_numeric*.so"))),
            "measurement": "/usr/bin/time -l -p around one direct Python process; perf_counter around time",
            "cache_policy": "empty PYTHONPYCACHEPREFIX with PYTHONDONTWRITEBYTECODE=1 and -B; both sides import source",
            "environment": {key: env[key] for key in ("PYTHONHASHSEED", "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE")},
            "order": "three control/control pairs, five alternating control/candidate pairs, five alternating cold-import pairs",
        },
        "host_swap_before": subprocess.check_output(["sysctl", "vm.swapusage"], text=True).strip(),
        "host_load_before": subprocess.check_output(["uptime"], text=True).strip(),
        "attempts": [], "pairs": [],
    }
    if source_evidence:
        evidence["source_evidence"] = str(source_evidence)
        evidence["host_swap_resume"] = subprocess.check_output(["sysctl", "vm.swapusage"], text=True).strip()
        evidence["host_load_resume"] = subprocess.check_output(["uptime"], text=True).strip()
    try:
        reference = evidence["attempts"][0]["output"] if source_evidence else None
        plan = (("comparison", 5), ("cold", 5)) if source_evidence else (
            (("self", 3),) if self_only else
            (("self", 3), ("comparison", 5), ("cold", 5)))
        for family, count in plan:
            for number in range(1, count + 1):
                sides = (("control", "control") if family == "self" else
                         (("control", "candidate") if number % 2 else
                          ("candidate", "control")))
                ids = []
                for position, side in enumerate(sides, 1):
                    record = attempt(family, number, position, side, env,
                                     control, candidate)
                    evidence["attempts"].append(record)
                    checkpoint_evidence(output, evidence, sort_keys=True)
                    ids.append(record["id"])
                    if record["returncode"] or "failure" in record or "user_seconds" not in record:
                        raise ValueError(f"failed attempt {record['id']}")
                    if family == "cold":
                        if record["output"] != {"empty_stdout": True}:
                            raise ValueError(f"unexpected cold output {record['id']}")
                    elif reference is None:
                        reference = record["output"]
                    elif record["output"] != reference:
                        record["failure"] = {"reason": "public output differs from first control"}
                        raise ValueError(f"output mismatch {record['id']}")
                evidence["pairs"].append({"family": family, "number": number,
                                          "order": sides, "attempts": ids})
    finally:
        evidence["host_swap_after"] = subprocess.check_output(["sysctl", "vm.swapusage"], text=True).strip()
        evidence["host_load_after"] = subprocess.check_output(["uptime"], text=True).strip()
        checkpoint_evidence(output, evidence, sort_keys=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--control-stage", type=Path, required=True)
    parser.add_argument("--candidate-stage", type=Path, default=ROOT / "rust-cpython/stage-strptime-numeric")
    parser.add_argument("--output", type=Path, default=DATA)
    parser.add_argument("--source-evidence", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--self-only", action="store_true")
    mode.add_argument("--continue", dest="resume", action="store_true")
    options = parser.parse_args()
    if options.resume and options.source_evidence is None:
        parser.error("--continue requires --source-evidence and a new --output")
    if options.source_evidence is not None and not options.resume:
        parser.error("--source-evidence requires --continue")
    main(options.control_stage, options.candidate_stage, options.output,
         source_evidence=options.source_evidence, self_only=options.self_only)
