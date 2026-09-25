"""Bounded native macOS pyperformance timing from the pinned pure Python wheels."""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / "benchmarks" / "vendor"
LAUNCHER = Path(__file__).with_name("pyperformance_macos_launcher.py")
sys.path.insert(0, str(ROOT / "benchmarks"))
from harness.inputs import _extract_wheel
from harness.pyperformance import (
    baseline_loop_counts,
    parse_raw_json,
    select_benchmarks,
    PyperformanceRun,
)


SUPPORTED = (
    "python_startup", "python_startup_no_site", "base64", "json_dumps",
    "json_loads", "pickle", "unpickle",
)


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def prepare_site(work: Path) -> tuple[Path, Path, list[dict[str, str]]]:
    pins = json.loads((VENDOR / "pins.json").read_text(encoding="utf-8"))
    names = (
        "pyperf-2.10.0-py3-none-any.whl",
        "pyperformance-1.14.0-py3-none-any.whl",
    )
    wheels = []
    site = work / "site"
    site.mkdir(parents=True, exist_ok=True)
    for name in names:
        path = VENDOR / name
        actual = digest(path)
        if actual != pins[name]:
            raise ValueError(f"vendored wheel hash mismatch: {name}")
        wheels.append({"filename": name, "sha256": actual})
        _extract_wheel(path, site)
    benchmark_root = site / "pyperformance" / "data-files" / "benchmarks"
    if not (benchmark_root / "MANIFEST").is_file():
        raise ValueError("pinned pyperformance manifest missing")
    return site, benchmark_root, wheels


def identity(python: Path) -> dict[str, str]:
    path = python.resolve(strict=True)
    command = [str(path), "-c", "import json,platform,sys,sysconfig;print(json.dumps({'version':sys.version,'implementation':platform.python_implementation(),'executable':sys.executable,'prefix':sys.prefix,'libdir':sysconfig.get_config_var('LIBDIR'),'ldlibrary':sysconfig.get_config_var('LDLIBRARY')},sort_keys=True))"]
    details = json.loads(subprocess.check_output(command, text=True, timeout=10))
    details.update({"requested_path": str(python), "resolved_path": str(path), "executable_sha256": digest(path)})
    if details["implementation"] != "CPython" or not details["version"].startswith("3.16"):
        raise ValueError(f"expected CPython 3.16: {python}")
    library = Path(details["libdir"]) / details["ldlibrary"]
    details["libpython_sha256"] = digest(library)
    details["libpython_path"] = str(library)
    return details


def invoke(python: Path, script: Path, opts: tuple[str, ...], site: Path, directory: Path, timeout: float) -> dict:
    directory.mkdir(parents=True, exist_ok=False)
    ledger = directory / "ledger"
    ledger.mkdir()
    cache = directory / "empty-pycache"
    cache.mkdir()
    output = directory / "pyperf.json"
    log = directory / "command.log"
    command = [str(python), str(LAUNCHER), *opts, "--output", str(output)]
    excluded = {"PYTHONHOME", "PYTHONPATH", "PYTHONUSERBASE", "PYTHONSTARTUP", "VIRTUAL_ENV"}
    env = {key: value for key, value in os.environ.items() if key not in excluded and not key.startswith("PIP_")}
    env.update({
        "PYTHONPATH": str(site), "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPYCACHEPREFIX": str(cache),
        "PYPERFORMANCE_SCRIPT": str(script), "PYPERFORMANCE_CPU_LEDGER": str(ledger),
        "PIP_NO_INDEX": "1", "PIP_CONFIG_FILE": os.devnull,
    })
    started = time.monotonic_ns()
    with log.open("x", encoding="utf-8") as stream:
        process = subprocess.Popen(command, cwd=script.parent, env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while True:
                pid, status, usage = os.wait4(process.pid, os.WNOHANG)
                if pid:
                    break
                if (time.monotonic_ns() - started) / 1e9 > timeout:
                    raise TimeoutError(f"pyperformance command exceeded {timeout} seconds")
                time.sleep(0.05)
        except BaseException:
            os.killpg(process.pid, signal.SIGKILL)
            os.wait4(process.pid, 0)
            raise
    elapsed = (time.monotonic_ns() - started) / 1e9
    process.returncode = os.waitstatus_to_exitcode(status)
    if process.returncode != 0 or not output.is_file():
        raise RuntimeError(f"pyperformance failed: {command}; see {log}")
    records = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(ledger.glob("*.json"))]
    root = next((record for record in records if record["pid"] == process.pid), None)
    if root is None:
        raise RuntimeError(f"pyperf root CPU ledger missing: {directory}")
    workers = [record for record in records if record["worker"]]
    if not workers:
        raise RuntimeError(f"pyperf worker CPU ledger missing: {directory}")
    if any(record["ppid"] != process.pid for record in workers):
        raise RuntimeError(f"unexpected nested pyperf worker: {directory}")
    worker_child_user = sum(record["child_user_seconds"] for record in workers)
    worker_child_system = sum(record["child_system_seconds"] for record in workers)
    direct_child_user = root["child_user_seconds"]
    direct_child_system = root["child_system_seconds"]
    parsed = parse_raw_json(output)
    benchmarks = []
    for benchmark in parsed.benchmarks.values():
        measured = [meta.get("loops") for values, meta in zip(benchmark.runs, benchmark.run_metadata, strict=True) if values]
        benchmarks.append({"name": benchmark.name, "unit": benchmark.unit, "measured_loops": measured, "values": list(benchmark.samples)})
    return {
        "command": command, "wall_seconds": elapsed,
        "cpu_user_seconds": usage.ru_utime,
        "cpu_system_seconds": usage.ru_stime,
        "root_wait4_user_seconds": usage.ru_utime,
        "root_wait4_system_seconds": usage.ru_stime,
        "root_reaped_child_user_seconds": direct_child_user,
        "root_reaped_child_system_seconds": direct_child_system,
        "worker_reaped_child_user_seconds": worker_child_user,
        "worker_reaped_child_system_seconds": worker_child_system,
        "coverage": "Darwin wait4 pyperf root includes waited descendants; escaped or unreaped descendants unavailable. Nested RUSAGE_CHILDREN ledgers are diagnostics and are not added to the total",
        "root_pid": process.pid, "worker_count": len(workers),
        "pyperf_json_sha256": digest(output), "benchmarks": benchmarks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--benchmark", default="python_startup")
    parser.add_argument("--pairs", type=int, default=1)
    parser.add_argument("--work", type=Path, default=ROOT / "rust-cpython" / "work" / "pyperformance_macos")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        parser.error("this experiment requires native macOS arm64")
    if args.benchmark not in SUPPORTED:
        parser.error(f"selected benchmark is outside the inspected stdlib-only subset: {args.benchmark}")
    if args.pairs < 1:
        parser.error("--pairs must be positive")
    work = args.work.resolve()
    if work.exists() and any(work.iterdir()):
        parser.error(f"work directory must be empty: {work}")
    if args.evidence.exists():
        parser.error(f"refusing to overwrite evidence: {args.evidence}")
    work.mkdir(parents=True, exist_ok=True)
    site, benchmark_root, wheels = prepare_site(work)
    selected = select_benchmarks(benchmark_root, args.benchmark)
    if len(selected) != 1:
        parser.error("select exactly one manifest script")
    spec = selected[0]
    baseline = identity(args.baseline)
    candidate = identity(args.candidate)
    common = (*spec.extra_opts, "--processes", "1", "--values", "1", "--warmups", "0", "--inherit-environ", "PYPERFORMANCE_SCRIPT,PYPERFORMANCE_CPU_LEDGER,PYTHONPATH,PYTHONDONTWRITEBYTECODE,PYTHONNOUSERSITE,PYTHONPYCACHEPREFIX")
    calibration = invoke(args.baseline, spec.script, common, site, work / "calibration", args.timeout)
    parsed = parse_raw_json(work / "calibration" / "pyperf.json")
    calib_benchmarks = tuple(replace(benchmark, manifest_name=spec.name) for benchmark in parsed.benchmarks.values())
    calibration_run = PyperformanceRun(str(args.baseline), "timing", (spec.name,), work / "calibration", calib_benchmarks, (work / "calibration" / "pyperf.json",) * len(calib_benchmarks), calibration=True)
    counts, unsupported = baseline_loop_counts(calibration_run)
    if spec.name not in counts:
        raise RuntimeError(f"benchmark unsupported: {unsupported}")
    loops = counts[spec.name]
    measured_opts = (*common, "--loops", str(loops))
    arms = []
    for pair in range(args.pairs):
        order = (("baseline", args.baseline), ("candidate", args.candidate))
        if pair % 2:
            order = tuple(reversed(order))
        for label, python in order:
            attempt = invoke(python, spec.script, measured_opts, site, work / f"pair-{pair + 1:02d}-{label}", args.timeout)
            if not attempt["benchmarks"] or any(
                not item["measured_loops"] or any(value != loops for value in item["measured_loops"])
                for item in attempt["benchmarks"]
            ):
                raise RuntimeError(f"fixed-loop metadata mismatch in {label}")
            attempt["arm"] = label
            attempt["pair"] = pair + 1
            arms.append(attempt)
    if len({tuple((item["name"], item["unit"]) for item in arm["benchmarks"]) for arm in arms}) != 1:
        raise RuntimeError("pyperf output names or units differ between arms")
    evidence = {
        "status": "bounded command and semantic proof under concurrent host load; timings are not publishable",
        "host": {"system": platform.system(), "machine": platform.machine(), "macos": platform.mac_ver()[0], "processor": platform.processor()},
        "input": {"wheels": wheels, "manifest_sha256": digest(benchmark_root / "MANIFEST"), "script_sha256": digest(spec.script), "script": str(spec.script.relative_to(site)), "extra_opts": list(spec.extra_opts)},
        "bytecode_policy": "empty per-attempt PYTHONPYCACHEPREFIX and PYTHONDONTWRITEBYTECODE=1; source compiled on both arms",
        "interpreters": {"baseline": baseline, "candidate": candidate},
        "benchmark": spec.name, "fixed_loops": loops, "pairs": args.pairs, "calibration": calibration, "timing_arms": arms,
        "unsupported_coverage": {
            "selected_script": unsupported,
            "supported_subset_not_selected": [name for name in SUPPORTED if name != spec.name],
            "other_manifest_scripts": "outside inspected stdlib-only subset or not selected",
            "memory": "not measured", "allocation": "not measured",
            "output_digest": "pyperf JSON hashes identify recorded samples; startup script has no application payload digest",
        },
    }
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.evidence}; fixed loops={loops}; benchmark={spec.name}")


if __name__ == "__main__":
    main()
