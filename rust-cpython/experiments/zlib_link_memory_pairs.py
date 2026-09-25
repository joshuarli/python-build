"""Compare two zlib extension links in one interpreter's memory pass."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import statistics
import subprocess


ROOT = Path(__file__).resolve().parents[2]
SCRATCH = ROOT / "rust-cpython" / "work" / "zlib-link-memory"
MODULE_NAME = "zlib.cpython-316-darwin.so"
FIELDS = {
    "wall_seconds": r"(?m)^real ([0-9.]+)$",
    "user_seconds": r"(?m)^user ([0-9.]+)$",
    "system_seconds": r"(?m)^sys ([0-9.]+)$",
    "peak_rss_bytes": r"(?m)^\s*(\d+)\s+maximum resident set size$",
    "peak_footprint_bytes": r"(?m)^\s*(\d+)\s+peak memory footprint$",
    "swaps": r"(?m)^\s*(\d+)\s+swaps$",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_module(source: Path, name: str) -> Path:
    if not source.is_file():
        raise RuntimeError(f"module is missing: {source}")
    directory = SCRATCH / name
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / MODULE_NAME
    if target.exists() and sha256(target) != sha256(source):
        raise RuntimeError(f"refusing to replace a different module: {target}")
    if not target.exists():
        shutil.copy2(source, target)
    return target


def observation(python: Path, module: Path, label: str) -> dict[str, object]:
    env = os.environ.copy()
    for key in tuple(env):
        if key in {"PYTHONPATH", "PYTHONHOME", "PYTHONPYCACHEPREFIX"} or key.startswith("DYLD_"):
            env.pop(key)
    env.update({
        "PYTHONPATH": os.pathsep.join((str(module.parent), str(ROOT))),
        "PYTHONHASHSEED": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPYCACHEPREFIX": str(SCRATCH / "absent-pycache"),
        "PYTHONMALLOC": "default",
    })
    command = ["/usr/bin/time", "-l", "-p", str(python), "-S", "-B", "-m",
               "benchmarks.workloads.zlib", "zlib_decode_1m", "--iterations", "1707"]
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"{label} exited {result.returncode}: {result.stderr[-1000:]}")
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{label} produced invalid workload output: {result.stdout[-500:]}") from error
    output.pop("elapsed_seconds", None)
    resources: dict[str, float | int] = {}
    for name, pattern in FIELDS.items():
        match = re.search(pattern, result.stderr)
        if match is None:
            raise RuntimeError(f"{label} lacks {name}: {result.stderr[-1000:]}")
        resources[name] = float(match.group(1)) if name.endswith("seconds") else int(match.group(1))
    return {"id": label, "arm": module.parent.name, "output": output, "resources": resources}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--control", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if platform.system() != "Darwin" or platform.machine().lower() not in {"arm64", "aarch64"}:
        raise RuntimeError("this memory pass requires native macOS arm64")
    python = args.python.resolve()
    if not python.is_file():
        raise RuntimeError(f"interpreter is missing: {python}")
    if (SCRATCH / "absent-pycache").exists():
        raise RuntimeError("the no-write bytecode cache prefix already exists")
    modules = {
        "control": prepare_module(args.control.resolve(), "control"),
        "smaller": prepare_module(args.candidate.resolve(), "smaller"),
    }
    pairs = []
    expected = None
    for kind, count in (("self", 3), ("candidate", 5)):
        for index in range(1, count + 1):
            order = ("control", "control") if kind == "self" else (
                ("control", "smaller") if index % 2 else ("smaller", "control"))
            attempts = [observation(python, modules[arm], f"{kind}-{index:02d}-{position}-{arm}")
                        for position, arm in enumerate(order, 1)]
            for attempt in attempts:
                if expected is None:
                    expected = attempt["output"]
                elif attempt["output"] != expected:
                    raise RuntimeError(f"workload output changed in {attempt['id']}")
            pairs.append({"kind": kind, "index": index, "order": order, "attempts": attempts})
    if (SCRATCH / "absent-pycache").exists():
        raise RuntimeError("the no-write bytecode cache prefix was unexpectedly created")
    differences = {
        metric: [
            next(attempt for attempt in pair["attempts"] if attempt["arm"] == "smaller")["resources"][metric]
            - next(attempt for attempt in pair["attempts"] if attempt["arm"] == "control")["resources"][metric]
            for pair in pairs if pair["kind"] == "candidate"
        ]
        for metric in ("peak_rss_bytes", "peak_footprint_bytes")
    }
    report = {
        "scope": "diagnostic macOS arm64 process-memory pass under current host load",
        "recipe": "one interpreter, two signed stripped zlib extensions selected by equal-length PYTHONPATH directories; -S -B; 1707 iterations of compressible and incompressible 1 MiB public decodes per process",
        "interpreter_sha256": sha256(python),
        "module_sha256": {arm: sha256(path) for arm, path in modules.items()},
        "output": expected,
        "memory_difference_bytes": {
            metric: {"observations": values, "median": statistics.median(values)}
            for metric, values in differences.items()
        },
        "pairs": pairs,
    }
    output_path = args.output.resolve()
    if output_path.exists():
        raise RuntimeError(f"refusing to replace existing evidence: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n")
    print(output_path)


if __name__ == "__main__":
    main()
