"""Reproduce the guarded shlex overlay and measure complete command processing."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import time

from evidence_checkpoint import checkpoint_evidence, reserve_evidence


LANE = Path(__file__).resolve().parents[1]
BASE = Path("/Users/josh/d/python-build/rust-cpython/stage")
PATCH = LANE / "patches/0009-rust-shlex-split.patch"
WORKLOAD = LANE / "experiments/shlex_split_workload.py"
SCRATCH = LANE / "work/shlex-guard-measure-20260925"
DATA = LANE / "experiments/data/shlex-guard-measure-20260925.json"
EXPECTED = {"buckets": 14, "digest": "f3044038f323d044f07ff99da59314f8861473624726d4483aeb1b9cea1f4afe",
            "errors": 632, "records": 12632, "rounds": 2, "tokens": 163580}
SOURCE_SHA = "10afd968308c933f2c7ec0928deebfa1e1ecb075950e29d4143565c1d24a96e1"
PURE_SHA = "3e75f98ddd7a8dd4f492183c25f480d34a8f9e4f1868f2ca2196d5018eb24150"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def host() -> dict[str, str]:
    return {
        "uptime": subprocess.check_output(["uptime"], text=True).strip(),
        "swap": subprocess.check_output(["sysctl", "-n", "vm.swapusage"], text=True).strip(),
        "top_cpu": subprocess.check_output(
            ["ps", "-Ao", "pid,%cpu,comm"], text=True
        ).splitlines()[:1] + sorted(
            subprocess.check_output(["ps", "-Ao", "pid,%cpu,comm"], text=True).splitlines()[1:],
            key=lambda line: float(line.split()[1]), reverse=True,
        )[:3],
    }


def extract_new_file(patch: str, name: str) -> str:
    section = patch.split(f"diff --git a/{name} b/{name}\n", 1)[1].split("diff --git ", 1)[0]
    return "\n".join(line[1:] for line in section.splitlines() if line.startswith("+") and not line.startswith("+++")) + "\n"


def run_child(argv: list[str], env: dict[str, str], tag: str, *, workload: bool = True) -> dict:
    out = SCRATCH / "child.stdout"
    err = SCRATCH / "child.stderr"
    with out.open("wb") as stdout, err.open("wb") as stderr:
        start = time.perf_counter()
        child = subprocess.Popen(argv, env=env, stdout=stdout, stderr=stderr)
        _pid, status, usage = os.wait4(child.pid, 0)
        wall = time.perf_counter() - start
    record = {"tag": tag, "returncode": os.waitstatus_to_exitcode(status),
              "wall_seconds": wall, "user_seconds": usage.ru_utime,
              "system_seconds": usage.ru_stime, "peak_rss_bytes": usage.ru_maxrss,
              "swaps": usage.ru_nswap}
    stdout_text = out.read_text()
    stderr_text = err.read_text()
    out.unlink()
    err.unlink()
    if record["returncode"]:
        record["failure"] = {"stdout_tail": stdout_text[-500:], "stderr_tail": stderr_text[-1000:]}
    elif workload:
        output = json.loads(stdout_text)
        record["output_digest"] = output.get("digest")
        if output != EXPECTED:
            record["failure"] = "complete workload output differs"
    return record


def memory_pass(source_evidence: Path, evidence_path: Path, scratch_path: Path) -> None:
    global SCRATCH
    SCRATCH = scratch_path
    evidence = json.loads(source_evidence.read_text())
    if evidence.get("failure") or "memory_attempts" in evidence:
        raise ValueError("timing evidence failed or memory pass already exists")
    reserve_evidence(evidence_path)
    overlays = {side: SCRATCH / side / "Lib" for side in ("control", "guarded")}
    if (sha(overlays["control"] / "shlex.py") != PURE_SHA or
            sha(overlays["guarded"] / "shlex.py") != SOURCE_SHA or
            sha(overlays["guarded"] / "_rust_shlex_split.cpython-316-darwin.so") != evidence["recipe"]["extension_sha256"]):
        raise ValueError("overlay bytes changed")
    env = os.environ.copy()
    for key in list(env):
        if key in {"PYTHONPATH", "PYTHONPYCACHEPREFIX"} or key.startswith("DYLD_"):
            env.pop(key)
    cache = SCRATCH / "empty-pycache"
    if any(cache.iterdir()):
        raise ValueError("bytecode cache prefix is not empty")
    env.update(PYTHONHASHSEED="1", PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1",
               PYTHONPYCACHEPREFIX=str(cache))
    evidence["memory_attempts"] = []
    evidence["memory_method"] = "/usr/bin/time -l -p wraps complete child for peak physical footprint; output digest checked"
    checkpoint_evidence(evidence_path, evidence)
    for pair in range(1, 4):
        group = {"pair": pair, "host_before_pair": host(), "runs": []}
        evidence["memory_attempts"].append(group)
        sides = ("control", "guarded") if pair % 2 else ("guarded", "control")
        for side in sides:
            child_env = env | {"PYTHONPATH": str(overlays[side])}
            argv = ["/usr/bin/time", "-l", "-p", str(BASE / "bin/python3.16"), "-S", "-B",
                    str(WORKLOAD), "--count", "12000", "--rounds", "2"]
            out = SCRATCH / "memory.stdout"
            err = SCRATCH / "memory.stderr"
            with out.open("wb") as stdout, err.open("wb") as stderr:
                start = time.perf_counter()
                child = subprocess.Popen(argv, env=child_env, stdout=stdout, stderr=stderr)
                _pid, status, usage = os.wait4(child.pid, 0)
                wall = time.perf_counter() - start
            stderr_text = err.read_text()
            result = {"tag": side, "returncode": os.waitstatus_to_exitcode(status),
                      "wall_seconds": wall, "wrapper_user_seconds": usage.ru_utime,
                      "wrapper_system_seconds": usage.ru_stime,
                      "peak_rss_bytes": usage.ru_maxrss, "swaps": usage.ru_nswap}
            for label, key in (("maximum resident set size", "child_peak_rss_bytes"),
                               ("peak memory footprint", "child_peak_footprint_bytes"),
                               ("swaps", "child_swaps")):
                match = re.search(r"^\s*(\d+)\s+" + re.escape(label) + r"$", stderr_text, re.M)
                if match:
                    result[key] = int(match.group(1))
            if result["returncode"] == 0:
                output = json.loads(out.read_text())
                result["output_digest"] = output.get("digest")
                if output != EXPECTED:
                    result["failure"] = "complete workload output differs"
            else:
                result["failure"] = stderr_text[-800:]
            out.unlink()
            err.unlink()
            group["runs"].append(result)
            checkpoint_evidence(evidence_path, evidence)
            if result.get("failure") or "child_peak_footprint_bytes" not in result:
                evidence["memory_failure"] = f"pair {pair} {side} failed output or footprint"
                break
        group["host_after_pair"] = host()
        checkpoint_evidence(evidence_path, evidence)
        if evidence.get("memory_failure"):
            raise RuntimeError(evidence["memory_failure"])
    deltas = []
    for group in evidence["memory_attempts"]:
        sides = {run["tag"]: run for run in group["runs"]}
        deltas.append(sides["guarded"]["child_peak_footprint_bytes"] - sides["control"]["child_peak_footprint_bytes"])
    evidence["memory_summary"] = {"footprint_delta_bytes": deltas,
                                   "median_footprint_delta_bytes": statistics.median(deltas)}
    checkpoint_evidence(evidence_path, evidence)


def main(evidence_path: Path, scratch_path: Path) -> None:
    global SCRATCH
    SCRATCH = scratch_path
    if SCRATCH.exists():
        raise FileExistsError(f"scratch already exists: {SCRATCH}; choose a new --scratch path")
    reserve_evidence(evidence_path)
    SCRATCH.mkdir(parents=True)
    evidence: dict = {"recipe": {}, "build": {}, "attempts": [], "host_before": host()}
    checkpoint_evidence(evidence_path, evidence)
    try:
        patch_text = PATCH.read_text()
        if sha(PATCH) != "de3ae62647a02df5722c6da57db3fe34cab9bc39676a3cc8087d494b2b4ffbaf":
            raise ValueError("current 0009 patch differs from guarded revision")
        pure = BASE / "lib/python3.16/shlex.py"
        if sha(pure) != PURE_SHA:
            raise ValueError("accepted pure parser differs")
        overlays = {side: SCRATCH / side for side in ("control", "guarded")}
        for side, directory in overlays.items():
            (directory / "Lib").mkdir(parents=True, exist_ok=True)
            (directory / "Lib/shlex.py").write_bytes(pure.read_bytes())
        guard = overlays["guarded"] / "Lib/shlex.py"
        parser_patch = patch_text.split("diff --git a/Makefile.pre.in", 1)[0]
        patch_file = SCRATCH / "parser.patch"
        patch_file.write_text(parser_patch)
        apply = subprocess.run(["patch", "-p1", "--batch", "-i", str(patch_file)],
                               cwd=SCRATCH / "guarded", capture_output=True, text=True)
        if apply.returncode or sha(guard) != SOURCE_SHA:
            raise ValueError(f"guarded parser patch or hash failed: {apply.stdout} {apply.stderr}")
        source_dir = SCRATCH / "native"
        source_dir.mkdir(exist_ok=True)
        native = {}
        for name in ("module.c", "scan.rs"):
            path = source_dir / name
            path.write_text(extract_new_file(patch_text, f"Modules/_rust_shlex_split/{name}"))
            native[name] = sha(path)
        archive = source_dir / "libshlex_split.a"
        extension = overlays["guarded"] / "Lib/_rust_shlex_split.cpython-316-darwin.so"
        llvm = Path("/Users/josh/d/python-build/.cache/llvm/toolchains/23.1.2-d7c26fc6177e42842e2d1ffaad31aec057c56a924392b1a23d830abe2c5d53b1/bin/clang")
        sdk = subprocess.check_output(["xcrun", "--sdk", "macosx", "--show-sdk-path"], text=True).strip()
        commands = [
            ["rustup", "run", "nightly-2026-09-15", "rustc", "--edition=2024", "--crate-type=staticlib", "-C", "opt-level=3", "-C", "panic=abort", str(source_dir / "scan.rs"), "-o", str(archive)],
            [str(llvm), "-O3", "-mcpu=apple-m1", "-fPIC", "-mmacosx-version-min=26.0", "-isysroot", sdk, "-bundle", "-undefined", "dynamic_lookup", "-I", str(BASE / "include/python3.16"), str(source_dir / "module.c"), str(archive), "-o", str(extension)],
        ]
        build_start = time.perf_counter()
        for index, command in enumerate(commands):
            result = run_child(command, os.environ.copy(), f"build-{index+1}", workload=False)
            evidence["build"][f"step_{index+1}"] = result
            checkpoint_evidence(evidence_path, evidence)
            if result.get("failure"):
                raise RuntimeError(result["failure"])
        evidence["build"]["wall_seconds"] = time.perf_counter() - build_start
        evidence["build"]["source_sha256"] = native
        evidence["build"]["archive_sha256"] = sha(archive)
        evidence["build"]["extension_sha256"] = sha(extension)
        evidence["build"]["extension_bytes"] = extension.stat().st_size
        evidence["build"]["sdk"] = sdk
        evidence["build"]["host_after"] = host()
        evidence["recipe"] = {"accepted_interpreter": str(BASE / "bin/python3.16"),
            "interpreter_sha256": sha(BASE / "bin/python3.16"), "pure_shlex_sha256": sha(pure),
            "guarded_shlex_sha256": sha(guard), "patch_sha256": sha(PATCH),
            "workload_sha256": sha(WORKLOAD), "native_source_sha256": native,
            "extension_sha256": sha(extension), "cache": "-B, PYTHONDONTWRITEBYTECODE=1, empty PYTHONPYCACHEPREFIX; both compile source",
            "command": "shlex_split_workload.py --count 12000 --rounds 2; same accepted interpreter in both arms",
            "measurement": "direct os.wait4 child rusage and parent perf_counter; serial complete processes",
            "sequence": "control/control, guarded/guarded, five alternating control/guarded pairs"}
        cache = SCRATCH / "empty-pycache"
        cache.mkdir(exist_ok=True)
        if any(cache.iterdir()):
            raise ValueError("bytecode cache prefix is not empty")
        base_env = os.environ.copy()
        for key in list(base_env):
            if key in {"PYTHONPATH", "PYTHONPYCACHEPREFIX"} or key.startswith("DYLD_"):
                base_env.pop(key)
        base_env.update(PYTHONHASHSEED="1", PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", PYTHONPYCACHEPREFIX=str(cache))
        for family, pairs in (("control_self", 2), ("guarded_self", 2), ("comparison", 5)):
            for pair in range(1, pairs + 1):
                sides = (("control", "control") if family == "control_self" else
                         ("guarded", "guarded") if family == "guarded_self" else
                         ("control", "guarded") if pair % 2 else ("guarded", "control"))
                evidence["attempts"].append({"host_before_pair": host(), "family": family, "pair": pair, "runs": []})
                group = evidence["attempts"][-1]
                for side in sides:
                    env = base_env | {"PYTHONPATH": str(overlays[side] / "Lib")}
                    argv = [str(BASE / "bin/python3.16"), "-S", "-B", str(WORKLOAD), "--count", "12000", "--rounds", "2"]
                    result = run_child(argv, env, side)
                    group["runs"].append(result)
                    checkpoint_evidence(evidence_path, evidence)
                    if result.get("failure"):
                        raise RuntimeError(f"{family} {pair} {side}: {result['failure']}")
                group["host_after_pair"] = host()
        evidence["summary"] = {}
        for family in ("control_self", "guarded_self", "comparison"):
            rows = [group for group in evidence["attempts"] if group["family"] == family]
            ratios = {metric: [] for metric in ("wall_seconds", "cpu_seconds")}
            for row in rows:
                first, second = row["runs"]
                for record in (first, second):
                    record["cpu_seconds"] = record["user_seconds"] + record["system_seconds"]
                numerator, denominator = ((second, first) if family != "comparison" else
                                          (next(run for run in row["runs"] if run["tag"] == "guarded"),
                                           next(run for run in row["runs"] if run["tag"] == "control")))
                for metric in ratios:
                    ratios[metric].append(numerator[metric] / denominator[metric])
            evidence["summary"][family] = {metric: {"median": statistics.median(values), "range": [min(values), max(values)]}
                                           for metric, values in ratios.items()}
    except Exception as exc:
        evidence["failure"] = str(exc)
        raise
    finally:
        evidence["host_after"] = host()
        checkpoint_evidence(evidence_path, evidence)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--memory", action="store_true")
    parser.add_argument("--source-evidence", type=Path, default=DATA,
                        help="completed timing evidence for a memory pass")
    parser.add_argument("--evidence", type=Path,
                        help="unique JSON output path for this run")
    parser.add_argument("--scratch", type=Path, default=SCRATCH,
                        help="unique scratch path for a new run, or earlier scratch for --memory")
    args = parser.parse_args()
    if args.memory:
        memory_pass(args.source_evidence, args.evidence or DATA.with_name(DATA.stem + "-memory.json"),
                    args.scratch)
    else:
        main(args.evidence or DATA, args.scratch)
