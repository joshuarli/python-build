"""Record whole-process timing attempts as compact, portable observations."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evidence_checkpoint import checkpoint_evidence, reserve_evidence


ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / "rust-cpython/work/tar-checksum-proof"
ARCHIVE = WORK / "source.tar.gz"
RUNNER = Path(__file__).with_name("run.py")
TIME_FIELD = re.compile(r"^\s*([\d.]+) real\s+([\d.]+) user\s+([\d.]+) sys", re.M)


def kernel_field(raw, label):
    match = re.search(r"^\s*(\d+)\s+" + re.escape(label) + r"$", raw, re.M)
    if match is None:
        raise ValueError(f"missing {label}")
    return int(match.group(1))


def run_attempt(name, side, mode):
    python = WORK / side / "stage/bin/python3.16"
    command = ["/usr/bin/time", "-l", str(python), str(RUNNER), mode,
               str(ARCHIVE), "--loops", "3"]
    environment = os.environ.copy()
    for key in tuple(environment):
        if key == "PYTHONPATH" or key == "PYTHONPYCACHEPREFIX" or key.startswith("DYLD_"):
            environment.pop(key)
    environment.update(PYTHONHASHSEED="1", PYTHONNOUSERSITE="1",
                       PYTHONMALLOC="default", PYTHONDONTWRITEBYTECODE="1")
    start = time.perf_counter()
    completed = subprocess.run(command, capture_output=True, text=True, env=environment)
    external = time.perf_counter() - start
    timing = TIME_FIELD.search(completed.stderr)
    record = {"id": name, "side": side, "mode": mode,
              "returncode": completed.returncode, "external_wall_seconds": external}
    if timing:
        record.update(kernel_real_seconds=float(timing.group(1)),
                      user_seconds=float(timing.group(2)),
                      system_seconds=float(timing.group(3)),
                      peak_rss_bytes=kernel_field(completed.stderr, "maximum resident set size"),
                      peak_footprint_bytes=kernel_field(completed.stderr, "peak memory footprint"),
                      swaps=kernel_field(completed.stderr, "swaps"))
    if completed.returncode == 0:
        record["output"] = json.loads(completed.stdout)
        expected_mode = "candidate" if side == "candidate" else "control"
        if record["output"]["mode"] != expected_mode:
            raise ValueError(f"incorrect mode: {name}")
    else:
        record["failure"] = {"stdout": completed.stdout[-2000:],
                             "stderr": completed.stderr[-2000:]}
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reserve_evidence(args.output)
    evidence = {"method": "/usr/bin/time -l around one Python child per attempt; "
                          "external perf_counter around the full time process; "
                          "no sampler or profiler during speed", "attempts": [], "pairs": []}
    try:
        for family in ("self", "comparison"):
            for pair_number in range(1, 6):
                arms = [("control", "control"), ("control", "control")]
                if family == "comparison":
                    arms[1] = ("candidate", "candidate")
                if pair_number % 2 == 0:
                    arms.reverse()
                ids = []
                for arm_number, (side, mode) in enumerate(arms, 1):
                    name = f"{family}-{pair_number:02d}-{arm_number:02d}-{side}"
                    record = run_attempt(name, side, mode)
                    evidence["attempts"].append(record)
                    checkpoint_evidence(args.output, evidence, sort_keys=True)
                    ids.append(name)
                    if record["returncode"] != 0:
                        raise RuntimeError(f"failed workload: {name}")
                    output = record["output"]
                    if (output["digest"], output["members"], output["regular_files"],
                            output["regular_bytes"], output["loops"]) != (
                            "4274d870abacbefea6bbdb2175de8b4073198e1fd39f34ede1c065b3faf1a805",
                            6539, 6031, 136064031, 3):
                        raise ValueError(f"mismatched output: {name}")
                evidence["pairs"].append({"family": family, "number": pair_number,
                                          "attempts": ids})
                checkpoint_evidence(args.output, evidence, sort_keys=True)
    finally:
        checkpoint_evidence(args.output, evidence, sort_keys=True)


if __name__ == "__main__":
    main()
