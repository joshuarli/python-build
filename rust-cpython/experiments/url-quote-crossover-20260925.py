"""Build and measure a length and safe set URL quote dispatch."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from evidence_checkpoint import checkpoint_evidence, reserve_evidence


ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "rust-cpython/work/url-quote-crossover-20260925"
DATA = ROOT / "rust-cpython/experiments/data/url-quote-crossover-20260925.json"
PATCH = ROOT / "rust-cpython/patches/0001-rust-url-quote.patch"
EXPERIMENT_PATCH = ROOT / "rust-cpython/experiments/url-quote-crossover-20260925.patch"
STAGE = Path("/Users/josh/d/python-build/rust-cpython/stage")
PYTHON = STAGE / "bin/python3.16"
STDLIB = STAGE / "lib/python3.16"
LLVM = Path("/Users/josh/d/python-build/.cache/llvm/toolchains/23.1.2-d7c26fc6177e42842e2d1ffaad31aec057c56a924392b1a23d830abe2c5d53b1")
SDK = Path("/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX26.5.sdk")
EXPECTED = {
    "catalog_search_form": (500, "a56d64f19accb1be3bb302cc60f406928d15182828c2b7e975e957d503dc1f22"),
    "catalog_request_path": (1000, "52db5e5b89587be9b6690dde7ffccaf709c6c2592b31f881c05354d1475d2eff"),
    "catalog_url_normalize": (2000, "a6fedf33e0fd5e72b79af8d77499b9a7bb8e8d53491955f2e554570679e04941"),
}
INPUT_DIGEST = "7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def host() -> dict[str, object]:
    rows = subprocess.check_output(["ps", "-axo", "pid,pcpu,rss,comm"], text=True).splitlines()[1:]
    top = sorted((row.strip() for row in rows), key=lambda row: float(row.split()[1]), reverse=True)[:4]
    return {"load": os.getloadavg(), "swap": subprocess.check_output(
        ["sysctl", "-n", "vm.swapusage"], text=True).strip(), "top": top,
        "vm_stat": subprocess.check_output(["vm_stat"], text=True).splitlines()[:8]}


def save(path: Path, data: dict[str, object]) -> None:
    checkpoint_evidence(path, data)


def measured(argv: list[str], *, env: dict[str, str] | None = None) -> dict[str, object]:
    started = time.monotonic()
    child = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
    pid, status, usage = os.wait4(child.pid, 0)
    wall = time.monotonic() - started
    assert pid == child.pid
    stdout = child.stdout.read().decode() if child.stdout else ""
    stderr = child.stderr.read().decode() if child.stderr else ""
    return {"returncode": os.waitstatus_to_exitcode(status), "wall_seconds": wall,
            "user_seconds": usage.ru_utime, "system_seconds": usage.ru_stime,
            "peak_rss_bytes": usage.ru_maxrss, "swaps": usage.ru_nswap,
            "stdout_excerpt": stdout[:2000], "stderr_excerpt": stderr[:300]}


def prepare(data: dict[str, object], evidence_path: Path) -> None:
    source = WORK / "source"
    (source / "Lib/urllib").mkdir(parents=True, exist_ok=True)
    shutil.copy2(STDLIB / "urllib/parse.py", source / "Lib/urllib/parse.py")
    patch_text = PATCH.read_text().split("diff --git a/Makefile.pre.in", 1)[0]
    applied = subprocess.run(["patch", "-p1", "-d", str(source), "--fuzz=0"],
                             input=patch_text, text=True, capture_output=True)
    if applied.returncode or "offset" in applied.stdout or "fuzz" in applied.stdout:
        raise RuntimeError(f"parser patch failed: {applied.stdout} {applied.stderr}")
    current = (source / "Lib/urllib/parse.py").read_text()
    if current == (STDLIB / "urllib/parse.py").read_text():
        raise RuntimeError("parser patch changed no bytes")
    source_modules = source / "Modules/_rust_url_quote"
    source_modules.mkdir(parents=True, exist_ok=True)
    for filename in ("module.c", "quote.rs"):
        section = PATCH.read_text().split(f"diff --git a/Modules/_rust_url_quote/{filename}", 1)[1]
        section = section.split("diff --git ", 1)[0]
        hunk = section.split("@@ -0,0 +1,", 1)[1].split("\n", 1)[1]
        lines = [line[1:] for line in hunk.splitlines(keepends=True) if line.startswith("+")]
        if not lines:
            raise RuntimeError(f"{filename} has no new-file hunk")
        (source_modules / filename).write_text("".join(lines))
    (WORK / "native").mkdir(parents=True, exist_ok=True)
    for side in ("pure", "current", "proposed"):
        directory = WORK / side / "urllib"
        directory.mkdir(parents=True, exist_ok=True)
        for file in (STDLIB / "urllib").glob("*.py"):
            shutil.copy2(file, directory / file.name)
    shutil.copy2(source / "Lib/urllib/parse.py", WORK / "current/urllib/parse.py")
    proposed = current.replace("_rust_url_type(bs) is bytes and _rust_url_type(safe) is bytes and",
                               "_rust_url_type(bs) is bytes and _rust_url_type(safe) is bytes and\n            not (safe and bs_len < 32) and")
    if proposed == current or proposed.count("not (safe and bs_len < 32)") != 1:
        raise RuntimeError("proposed guard replacement failed")
    (WORK / "proposed/urllib/parse.py").write_text(proposed)
    EXPERIMENT_PATCH.write_text("".join(difflib.unified_diff(
        current.splitlines(keepends=True), proposed.splitlines(keepends=True),
        fromfile="a/Lib/urllib/parse.py", tofile="b/Lib/urllib/parse.py")))
    data["identities"] = {"patch": digest(PATCH), "python": digest(PYTHON),
                          "experimental_patch": digest(EXPERIMENT_PATCH),
                          "stage_parse": digest(STDLIB / "urllib/parse.py"),
                          **{side + "_parse": digest(WORK / side / "urllib/parse.py")
                             for side in ("pure", "current", "proposed")},
                          "module_c": digest(source_modules / "module.c"),
                          "quote_rs": digest(source_modules / "quote.rs")}
    data["build_recipe"] = {
        "rust": "rustup run nightly-2026-09-15 rustc --edition=2024 --crate-type=staticlib -C opt-level=3 -C panic=abort --target=aarch64-apple-darwin quote.rs -o libquote_ascii.a",
        "c": "locked LLVM 23.1.2 clang -O3 -fPIC -mcpu=apple-m1 -mmacosx-version-min=26.0 -isysroot Xcode26.5SDK -I stage/include/python3.16 -c module.c -o module.o",
        "link": "locked LLVM clang -bundle -undefined dynamic_lookup -mmacosx-version-min=26.0 -isysroot Xcode26.5SDK module.o libquote_ascii.a -o _rust_url_quote.cpython-316-darwin.so",
    }
    save(evidence_path, data)
    native = WORK / "native"
    commands = [
        ["rustup", "run", "nightly-2026-09-15", "rustc", "--edition=2024", "--crate-type=staticlib", "-C", "opt-level=3", "-C", "panic=abort", "--target=aarch64-apple-darwin", str(source_modules / "quote.rs"), "-o", str(native / "libquote_ascii.a")],
        [str(LLVM / "bin/clang"), "-O3", "-fPIC", "-mcpu=apple-m1", "-mmacosx-version-min=26.0", "-isysroot", str(SDK), "-I", str(STAGE / "include/python3.16"), "-c", str(source_modules / "module.c"), "-o", str(native / "module.o")],
        [str(LLVM / "bin/clang"), "-bundle", "-undefined", "dynamic_lookup", "-mmacosx-version-min=26.0", "-isysroot", str(SDK), str(native / "module.o"), str(native / "libquote_ascii.a"), "-o", str(native / "_rust_url_quote.cpython-316-darwin.so")],
    ]
    for number, command in enumerate(commands):
        result = measured(command)
        result["id"] = f"build-{number}"
        data["attempts"].append(result)
        save(evidence_path, data)
        if result["returncode"]:
            raise RuntimeError(f"build-{number}: {result['stderr_excerpt']}")
    data["identities"]["extension"] = digest(native / "_rust_url_quote.cpython-316-darwin.so")
    save(evidence_path, data)


def workload(task: str, side: str, attempt_id: str) -> dict[str, object]:
    iterations, expected = EXPECTED[task]
    env = dict(os.environ)
    env.update(PYTHONPATH=os.pathsep.join((str(WORK / side), str(WORK / "native"), str(ROOT))),
               PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="1")
    module = "benchmarks.workloads.catalog_url" if task == "catalog_url_normalize" else "benchmarks.workloads.catalog_url_breadth"
    record = measured([str(PYTHON), "-B", "-m", module, task, "--iterations", str(iterations)], env=env)
    record.update(id=attempt_id, side=side, task=task)
    try:
        output = json.loads(record.pop("stdout_excerpt"))
        record.update(output_digest=output["digest"], input_digest=output["input_digest"],
                      operation_count=output["operation_count"])
        record["valid"] = (record["returncode"] == 0 and output["digest"] == expected and
                           output["input_digest"] == INPUT_DIGEST and output["operation_count"] == iterations)
    except (ValueError, KeyError, TypeError):
        record["valid"] = False
    return record


def calibrate(length: int, safe: bytes, side: str, attempt_id: str) -> dict[str, object]:
    env = dict(os.environ)
    env.update(PYTHONPATH=os.pathsep.join((str(WORK / side), str(WORK / "native"), str(ROOT))),
               PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="1")
    record = measured([str(PYTHON), "-B", str(ROOT / "rust-cpython/experiments/url-quote-crossover-20260925-calibrate.py"),
                       "--length", str(length), "--safe-hex", safe.hex()], env=env)
    record.update(id=attempt_id, side=side, length=length, safe_hex=safe.hex())
    try:
        output = json.loads(record.pop("stdout_excerpt"))
        record.update(output_digest=output["digest"], quoted_value=output["value"],
                      operation_count=output["iterations"])
        record["valid"] = (record["returncode"] == 0 and output["length"] == length
                           and output["safe_hex"] == safe.hex() and output["iterations"] == 30000)
    except (ValueError, KeyError, TypeError):
        record["valid"] = False
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--calibration-only", action="store_true")
    parser.add_argument("--skip-calibration", action="store_true")
    parser.add_argument("--evidence", type=Path, default=DATA,
                        help="unique JSON output path for this run")
    args = parser.parse_args()
    reserve_evidence(args.evidence)
    data: dict[str, object] = {"hypothesis": "short inputs with any nonempty exact-byte safe set favor the cached Python quoter; empty safe favors the Rust kernel",
        "rule": "after existing fast exit and exact type checks, nonempty safe and 1 < input length < 32 use original Python route",
        "accounting": "wait4 direct child; monotonic external wall; ru_maxrss and ru_nswap; workloads have no descendants; rustup launcher may spawn rustc and its wait4 CPU excludes that child",
        "cache": "all overlays source-only, -B and PYTHONDONTWRITEBYTECODE=1; fresh copied urllib directory has no __pycache__",
        "environment": "PYTHONPATH=SIDE:NATIVE:ROOT; PYTHONHASHSEED=1",
        "host_initial": host(), "attempts": [], "groups": []}
    save(args.evidence, data)
    prepare(data, args.evidence)
    if args.prepare_only:
        return
    if not args.skip_calibration:
        for length in (8, 24, 64):
            for safe in (b"", b"/", b"+", b"/:?"):
                group_id = f"calibration-{length}-{safe.hex()}"
                order = ("pure", "current", "proposed") if length != 24 else ("proposed", "current", "pure")
                data["groups"].append({"id": group_id, "order": order, "host_before": host()})
                records = []
                for position, side in enumerate(order):
                    result = calibrate(length, safe, side, f"{group_id}-{position}")
                    data["attempts"].append(result)
                    records.append(result)
                    save(args.evidence, data)
                    if not result["valid"]:
                        raise RuntimeError(f"invalid {result['id']}")
                if len({(record["output_digest"], record["quoted_value"]) for record in records}) != 1:
                    raise RuntimeError(f"calibration output mismatch: {group_id}")
    if args.calibration_only:
        data["host_final"] = host()
        save(args.evidence, data)
        return
    for task in EXPECTED:
        for side_a, side_b, pairs in (("current", "proposed", 2), ("pure", "proposed", 2),
                                      ("current", "current", 1), ("proposed", "proposed", 1)):
            for pair in range(pairs):
                order = (side_a, side_b) if pair % 2 == 0 else (side_b, side_a)
                group_id = f"{task}-{side_a}-{side_b}-{pair}"
                data["groups"].append({"id": group_id, "order": order, "host_before": host()})
                for position, side in enumerate(order):
                    result = workload(task, side, f"{group_id}-{position}")
                    data["attempts"].append(result)
                    save(args.evidence, data)
                    if not result["valid"]:
                        raise RuntimeError(f"invalid {result['id']}")
    data["host_final"] = host()
    save(args.evidence, data)


if __name__ == "__main__":
    main()
