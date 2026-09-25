"""Bounded complete-ledger diagnostic of the current optional Fraction guard."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from evidence_checkpoint import checkpoint_evidence, reserve_evidence


LANE = Path(__file__).resolve().parents[1]
RUN_ID = os.environ.get("FRACTION_RUN_ID", "01")
PATCH = LANE / "patches/0010-rust-fraction-rational.patch"
WORKLOAD = LANE / "experiments/fraction_rational_workload.py"
STAGE = Path("/Users/josh/d/python-build/rust-cpython/stage")
PYTHON = STAGE / "bin/python3.16"
SOURCE = STAGE / "lib/python3.16/fractions.py"
OUT = LANE / f"experiments/data/fraction-current-guard-measure-20260925-run{RUN_ID}.json"
SCRATCH = LANE / f"work/fraction-current-guard-measure-20260925-run{RUN_ID}"
EXPECTED = "356356bd5c02a8e41cfb64a19ec168f35a6a752ed9c5e1c7b3b15b2635d284e9"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checkpoint(data):
    checkpoint_evidence(OUT, data, indent=None, separators=(",", ":"))


def host():
    return {"uptime": subprocess.check_output(["uptime"], text=True).strip(),
            "swap": subprocess.check_output(["sysctl", "vm.swapusage"], text=True).strip()}


def patch_file(text, name):
    header = f"diff --git a/{name} b/{name}\n"
    section = text.split(header, 1)[1].split("diff --git ", 1)[0]
    return header + section


def new_file(section):
    return "".join(line[1:] for line in section.splitlines(keepends=True)
                   if line.startswith("+") and not line.startswith("+++"))


def measured(command, env):
    start = time.perf_counter()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env=env)
    stdout = process.stdout.read()
    stderr = process.stderr.read()
    _, status, usage = os.wait4(process.pid, 0)
    elapsed = time.perf_counter() - start
    return {"returncode": os.waitstatus_to_exitcode(status), "wall_seconds": elapsed,
            "user_seconds": usage.ru_utime, "system_seconds": usage.ru_stime,
            "peak_rss_bytes": usage.ru_maxrss, "swaps": usage.ru_nswap,
            "voluntary_context_switches": usage.ru_nvcsw,
            "involuntary_context_switches": usage.ru_nivcsw,
            "stdout": stdout.decode(errors="replace"),
            "stderr_tail": stderr.decode(errors="replace")[-1000:]}


def record_attempt(data, phase, side, command, env):
    attempt_id = f"run{RUN_ID}-{phase}-{len(data['attempts']) + 1:02d}-{side}"
    result = measured(command, env)
    record = {"id": attempt_id, "phase": phase, "side": side,
              **{key: value for key, value in result.items() if key != "stdout"}}
    if phase in ("timing", "memory") and result["returncode"] == 0:
        try:
            output = json.loads(result["stdout"])
            record["output"] = output
            if output != {"accounts": 16, "canonical_records": 160000,
                          "count": 100000, "digest": EXPECTED, "records": 200000,
                          "rounds": 2}:
                record["failure"] = "complete-ledger output mismatch"
        except json.JSONDecodeError as exc:
            record["failure"] = f"invalid output: {exc}: {result['stdout'][-500:]}"
    elif result["returncode"]:
        record["failure"] = result["stdout"][-500:] or result["stderr_tail"]
    elif phase == "import-audit":
        record["import"] = json.loads(result["stdout"])
    data["attempts"].append(record)
    checkpoint(data)
    if result["returncode"] or "failure" in record:
        raise RuntimeError(f"{attempt_id} failed: {record.get('failure', record['stderr_tail'])}")
    return record


def main():
    if SCRATCH.exists():
        raise FileExistsError("existing scratch; choose a distinct FRACTION_RUN_ID")
    reserve_evidence(OUT)
    SCRATCH.mkdir(parents=True)
    patch = PATCH.read_text()
    manifest = LANE / "patches/manifest.json"
    entry = next(x for x in json.loads(manifest.read_text())["patches"]
                 if x["file"] == PATCH.name)
    if digest(PATCH) != entry["sha256"]:
        raise ValueError("current patch differs from manifest")
    control = SCRATCH / "control"
    candidate = SCRATCH / "candidate"
    control.mkdir()
    candidate.mkdir()
    shutil.copyfile(SOURCE, control / "fractions.py")
    (candidate / "Lib").mkdir()
    shutil.copyfile(SOURCE, candidate / "Lib/fractions.py")
    fraction_patch = SCRATCH / "fractions.patch"
    fraction_patch.write_text(patch_file(patch, "Lib/fractions.py"))
    applied = subprocess.run(["patch", "--batch", "--forward", "-p1", "-i", str(fraction_patch)],
                             cwd=candidate, capture_output=True, text=True)
    if applied.returncode:
        raise RuntimeError(applied.stderr + applied.stdout)
    (candidate / "Lib/fractions.py").replace(candidate / "fractions.py")
    if digest(candidate / "fractions.py") != "8275fd7933de5062f6d8f82169caa306980ed398fe1376fe1be1906ae458ee6c":
        raise ValueError("patched fractions.py identity mismatch")
    for name, target in (("Modules/_rust_fraction_rational/module.c", "module.c"),
                         ("Modules/_rust_fraction_rational/scan.rs", "scan.rs")):
        (SCRATCH / target).write_text(new_file(patch_file(patch, name)))

    config = json.loads(subprocess.check_output(
        [str(PYTHON), "-S", "-B", "-c",
         "import json,sysconfig; print(json.dumps({k:sysconfig.get_config_var(k) for k in ('EXT_SUFFIX','CC')}))"],
        text=True))
    suffix = config["EXT_SUFFIX"]
    clang = config["CC"].split()[0]
    sdk = subprocess.check_output(["xcrun", "--show-sdk-path"], text=True).strip()
    include = STAGE / "include/python3.16"
    archive = SCRATCH / "libfraction_rational.a"
    extension = candidate / ("_rust_fraction_rational" + suffix)
    rust_command = ["rustup", "run", "nightly-2026-09-15", "rustc", "--edition=2024",
                    "--crate-type=staticlib", "-C", "opt-level=3", "-C", "panic=abort",
                    str(SCRATCH / "scan.rs"), "-o", str(archive)]
    clang_command = [clang, "-bundle", "-undefined", "dynamic_lookup", "-isysroot", sdk,
                     "-mmacosx-version-min=26.0", "-O3", "-I", str(include),
                     str(SCRATCH / "module.c"), str(archive), "-o", str(extension)]
    data = {"recipe": {"patch_sha256": digest(PATCH), "manifest_sha256": digest(manifest),
                       "control_fractions_sha256": digest(control / "fractions.py"),
                       "candidate_fractions_sha256": digest(candidate / "fractions.py"),
                       "module_c_sha256": digest(SCRATCH / "module.c"),
                       "scan_rs_sha256": digest(SCRATCH / "scan.rs"),
                       "interpreter_sha256": digest(PYTHON),
                       "workload_sha256": digest(WORKLOAD),
                       "compiler": {"rust": rust_command, "c": clang_command},
                       "workload": [str(PYTHON), "-B", str(WORKLOAD), "--count", "100000", "--rounds", "2"],
                       "cache": "fresh empty PYTHONPYCACHEPREFIX, PYTHONDONTWRITEBYTECODE=1, -B; overlay fractions.py has no pyc",
                       "accounting": "Darwin wait4 direct child rusage: wall perf_counter, user/system CPU, peak RSS, swaps; ledger workload is one process and starts no children; waited compiler children are included in reaped-child totals, while compiler peak RSS is a process peak rather than a simultaneous sum",
                       "timing_order": ["control/control", "control/candidate", "candidate/control", "control/candidate", "control/control"],
                       "memory_order": ["control", "candidate"]},
            "host_before": host(), "attempts": []}
    checkpoint(data)
    try:
        for side, command in (("rust-compile", rust_command), ("c-link", clang_command)):
            record_attempt(data, "build", side, command, os.environ.copy())
        data["recipe"]["extension_sha256"] = digest(extension)
        data["recipe"]["extension_bytes"] = extension.stat().st_size
        cache = SCRATCH / "empty-pycache"
        cache.mkdir()
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("PYTHON") or key.startswith("DYLD_"):
                env.pop(key)
        env.update(PYTHONHASHSEED="1", PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1",
                   PYTHONPYCACHEPREFIX=str(cache))
        data["recipe"]["environment"] = {key: env[key] for key in
                                          ("PYTHONHASHSEED", "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX")}
        for side, overlay in (("control", control), ("candidate", candidate)):
            env["PYTHONPATH"] = str(overlay)
            command = [str(PYTHON), "-B", "-c",
                       "import fractions,json,sys; value=str(fractions.Fraction('12/35')); print(json.dumps({'file':fractions.__file__,'cached':getattr(fractions,'__cached__',None),'extension':('_rust_fraction_rational' in sys.modules),'value':value}))"]
            identity = record_attempt(data, "import-audit", side, command, env)
            imported = identity["import"]
            if (Path(imported["file"]) != overlay / "fractions.py" or
                    imported["value"] != "12/35" or
                    imported["extension"] != (side == "candidate") or
                    any(cache.iterdir())):
                identity["failure"] = "overlay, extension, or source-only cache audit failed"
                checkpoint(data)
                raise RuntimeError(identity["failure"])
            checkpoint(data)
        for pair, sides in enumerate((("control", "control"), ("control", "candidate"),
                                      ("candidate", "control"), ("control", "candidate"),
                                      ("control", "control")), 1):
            for side in sides:
                env["PYTHONPATH"] = str(control if side == "control" else candidate)
                record_attempt(data, "timing", side, data["recipe"]["workload"], env)
        for side in ("control", "candidate"):
            env["PYTHONPATH"] = str(control if side == "control" else candidate)
            record_attempt(data, "memory", side, data["recipe"]["workload"], env)
        data["status"] = "complete"
    except Exception as exc:
        data["status"] = "failed"
        data["failure"] = str(exc)
        raise
    finally:
        data["host_after"] = host()
        checkpoint(data)


if __name__ == "__main__":
    main()
