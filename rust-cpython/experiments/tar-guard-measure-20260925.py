"""Measure the current optional TAR guard on one accepted interpreter."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from evidence_checkpoint import checkpoint_evidence, reserve_evidence


ROOT = Path(__file__).resolve().parents[2]
RUN_ID = sys.argv[1] if len(sys.argv) == 2 else ""
if not re.fullmatch(r"[a-z][a-z0-9-]*", RUN_ID):
    raise SystemExit("pass a distinct lowercase run ID")
WORK = ROOT / "rust-cpython/work" / f"tar-guard-measure-20260925-{RUN_ID}"
DATA = ROOT / "rust-cpython/experiments/data" / f"tar-guard-measure-20260925-{RUN_ID}.json"
PATCH = ROOT / "rust-cpython/patches/0005-rust-tar-checksum.patch"
SOURCE = Path("/Users/josh/d/python-build/rust-cpython/stage")
ARCHIVE = ROOT / "rust-cpython/work/tar-guard-measure-20260925a/source.tar.gz"
WORKLOAD = ROOT / "rust-cpython/experiments/source_tar_rewrite.py"
EXPECTED = ("4274d870abacbefea6bbdb2175de8b4073198e1fd39f34ede1c065b3faf1a805",
            "8026bc5b211c69b1d7cda5a929b506cb7bf61d70290a3dfa5e51d275c4f85efd",
            147763200, 6539, 6031, 136064031)


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1 << 20):
            h.update(block)
    return h.hexdigest()


def checkpoint(data):
    checkpoint_evidence(DATA, data, sort_keys=True)


def measured(command, label, env):
    output = WORK / f"{label}.stdout"
    error = WORK / f"{label}.stderr"
    with output.open("xb") as stdout, error.open("xb") as stderr:
        start = time.perf_counter()
        child = subprocess.Popen(command, stdout=stdout, stderr=stderr, env=env)
        _, status, usage = os.wait4(child.pid, 0)
        wall = time.perf_counter() - start
    return {"id": label, "command": command, "status": os.waitstatus_to_exitcode(status),
            "wall_seconds": wall, "user_seconds": usage.ru_utime,
            "system_seconds": usage.ru_stime, "peak_rss_bytes": usage.ru_maxrss,
            "swaps": usage.ru_nswap, "process_count": 1,
            "output": output.name, "stderr": error.name}


def section(patch, name):
    marker = f"diff --git a/{name} b/{name}\n"
    return marker + patch.split(marker, 1)[1].split("diff --git ", 1)[0]


def new_file(patch, name, target):
    lines = section(patch, name).splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines) if line.startswith("@@")) + 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(line[1:] for line in lines[start:] if line.startswith("+")))


def main():
    if WORK.exists():
        raise FileExistsError("run ID already has scratch; pass a distinct run ID")
    reserve_evidence(DATA)
    WORK.mkdir(parents=True)
    data = {"run_id": RUN_ID, "attempts": [], "build": [], "pairs": [],
            "host_before": {"uptime": subprocess.check_output(["uptime"], text=True).strip(),
                            "swap": subprocess.check_output(["sysctl", "vm.swapusage"], text=True).strip()},
            "recipe": {"interpreter": str(SOURCE / "bin/python3.16"),
                       "interpreter_sha256": digest(SOURCE / "bin/python3.16"),
                       "libpython_sha256": digest(SOURCE / "lib/libpython3.16.dylib"),
                       "patch_sha256": digest(PATCH), "workload_sha256": digest(WORKLOAD),
                       "archive_sha256": digest(ARCHIVE),
                       "source_cache_policy": "empty PYTHONPYCACHEPREFIX; PYTHONDONTWRITEBYTECODE=1; no pyc reads or writes",
                       "measurement": "os.wait4 on direct child; macOS ru_maxrss in bytes; direct process tree has no child processes"}}
    checkpoint(data)
    if digest(ARCHIVE) != "965dbc9c847b0ed779a16134495b8690c9fc957996d8bcbb83c47089d4e81467":
        raise ValueError("wrong source archive")
    control_source = SOURCE / "lib/python3.16/tarfile.py"
    pinned_source = Path("/Users/josh/d/python-build/rust-cpython/work/source/cpython-b812b4a7b9efaca46b98544a8633b7d7e454166b/Lib/tarfile.py")
    if digest(control_source) != digest(pinned_source):
        raise ValueError("accepted tarfile differs from pure pinned source")
    overlay = WORK / "overlay"
    (overlay / "Lib").mkdir(parents=True)
    shutil.copy2(control_source, overlay / "Lib/tarfile.py")
    patch = PATCH.read_text()
    tar_patch = WORK / "tar.patch"
    tar_patch.write_text(section(patch, "Lib/tarfile.py"))
    apply = subprocess.run(["/usr/bin/patch", "-p1", "-i", str(tar_patch)], cwd=overlay,
                           text=True, capture_output=True)
    data["patch_application"] = {"status": apply.returncode, "stdout": apply.stdout,
                                 "stderr": apply.stderr}
    checkpoint(data)
    if apply.returncode or digest(overlay / "Lib/tarfile.py") == digest(control_source):
        raise ValueError("TAR patch did not change source")
    module = overlay / "Modules/_rust_tar_checksum"
    new_file(patch, "Modules/_rust_tar_checksum/module.c", module / "module.c")
    new_file(patch, "Modules/_rust_tar_checksum/checksum.rs", module / "checksum.rs")
    data["recipe"].update(control_tarfile_sha256=digest(control_source),
                          guarded_tarfile_sha256=digest(overlay / "Lib/tarfile.py"),
                          module_c_sha256=digest(module / "module.c"),
                          checksum_rs_sha256=digest(module / "checksum.rs"))
    clone = WORK / "candidate"
    subprocess.run(["cp", "-cR", str(SOURCE), str(clone)], check=True)
    candidate_source = clone / "lib/python3.16/tarfile.py"
    shutil.copy2(overlay / "Lib/tarfile.py", candidate_source)
    rustc = subprocess.check_output(["rustup", "which", "rustc", "--toolchain", "nightly-2026-09-15"], text=True).strip()
    clang = subprocess.check_output([str(SOURCE / "bin/python3.16"), "-c",
                                     "import sysconfig; print(sysconfig.get_config_var('CC').split()[0])"], text=True).strip()
    sdk = subprocess.check_output(["xcrun", "--sdk", "macosx", "--show-sdk-path"], text=True).strip()
    archive = WORK / "libtar_checksum.a"
    obj = WORK / "module.o"
    extension = clone / "lib/python3.16/lib-dynload/_rust_tar_checksum.cpython-316-darwin.so"
    build_env = dict(os.environ, MACOSX_DEPLOYMENT_TARGET="26.0")
    commands = [
        [rustc, "--edition=2024", "--crate-type=staticlib", "-C", "opt-level=3", "-C", "panic=abort",
         str(module / "checksum.rs"), "-o", str(archive)],
        [clang, "-O3", "-fPIC", "-mmacosx-version-min=26.0", "-isysroot", sdk,
         "-I", str(SOURCE / "include/python3.16"), "-c", str(module / "module.c"), "-o", str(obj)],
        [clang, "-bundle", "-undefined", "dynamic_lookup", "-mmacosx-version-min=26.0",
         "-isysroot", sdk, str(obj), str(archive), "-o", str(extension)],
    ]
    for index, command in enumerate(commands, 1):
        record = measured(command, f"build-{index}", build_env)
        data["build"].append(record)
        checkpoint(data)
        if record["status"]:
            raise ValueError(f"build failed: {record['id']}")
    data["recipe"]["extension_sha256"] = digest(extension)
    data["recipe"]["candidate_tarfile_sha256"] = digest(candidate_source)
    if data["recipe"]["candidate_tarfile_sha256"] != data["recipe"]["guarded_tarfile_sha256"]:
        raise ValueError("installed source mismatch")
    cache = WORK / "empty-pycache"
    cache.mkdir()
    env = dict(os.environ)
    for key in tuple(env):
        if key in ("PYTHONPATH", "PYTHONPYCACHEPREFIX") or key.startswith("DYLD_"):
            env.pop(key)
    env.update(PYTHONPYCACHEPREFIX=str(cache), PYTHONDONTWRITEBYTECODE="1",
               PYTHONNOUSERSITE="1", PYTHONHASHSEED="1")
    data["recipe"]["environment"] = {k: env[k] for k in
                                      ("PYTHONPYCACHEPREFIX", "PYTHONDONTWRITEBYTECODE",
                                       "PYTHONNOUSERSITE", "PYTHONHASHSEED")}
    # A new cache prefix forces both tarfile variants to compile their source.
    for side, python in (("control", SOURCE / "bin/python3.16"),
                         ("candidate", clone / "bin/python3.16")):
        command = [str(python), "-v", "-c", "import tarfile; print(tarfile.__file__)" ]
        record = measured(command, f"audit-{side}", env)
        data["attempts"].append(record)
        checkpoint(data)
        audit_log = (WORK / record["stderr"]).read_text()
        if record["status"] or re.search(r"code object from .*tarfile.*\.pyc", audit_log):
            raise ValueError(f"source import audit failed: {side}")
        if f"/lib/python3.16/tarfile.py" not in audit_log:
            raise ValueError(f"tarfile source import missing: {side}")
    probe = measured([str(clone / "bin/python3.16"), "-c",
                      "import tarfile,sys; assert '_rust_tar_checksum' not in sys.modules; "
                      "tarfile.calc_chksums(bytes(512)); "
                      "import _rust_tar_checksum; print(_rust_tar_checksum.__file__)"],
                     "extension-probe", env)
    data["attempts"].append(probe)
    checkpoint(data)
    if probe["status"] or str(extension) not in (WORK / probe["output"]).read_text():
        raise ValueError("candidate did not load the matched private extension")
    data["cache_entries_after_audit"] = [str(p.relative_to(cache)) for p in cache.rglob("*")]
    checkpoint(data)
    sides = {"control": SOURCE / "bin/python3.16", "candidate": clone / "bin/python3.16"}
    try:
        for family, count in (("self", 3), ("comparison", 5), ("memory", 2)):
            for pair in range(1, count + 1):
                order = ("control", "control") if family == "self" else ("control", "candidate")
                if pair % 2 == 0:
                    order = tuple(reversed(order))
                ids = []
                for position, side in enumerate(order, 1):
                    label = f"{family}-{pair:02d}-{position}-{side}"
                    output = WORK / f"{label}.tar"
                    command = [str(sides[side]), str(WORKLOAD), str(ARCHIVE), str(output)]
                    record = measured(command, label, env)
                    record.update(family=family, pair=pair, position=position, side=side)
                    if record["status"] == 0:
                        try:
                            result = json.loads((WORK / record["output"]).read_text())
                            values = tuple(result[k] for k in ("source_digest", "output_digest",
                                                               "output_bytes", "members", "regular_files",
                                                               "regular_bytes"))
                            if values != EXPECTED or digest(output) != EXPECTED[1]:
                                raise ValueError("workload digest/count mismatch")
                            record["output_identity"] = result
                        except (ValueError, KeyError) as error:
                            record["failure"] = str(error)
                    else:
                        record["failure"] = (WORK / record["stderr"]).read_text()[-1000:]
                    data["attempts"].append(record)
                    checkpoint(data)
                    if record.get("failure"):
                        raise ValueError(f"failed attempt {label}: {record['failure']}")
                    ids.append(label)
                    output.unlink()
                data["pairs"].append({"family": family, "pair": pair, "attempts": ids})
                checkpoint(data)
    finally:
        data["host_after"] = {"uptime": subprocess.check_output(["uptime"], text=True).strip(),
                              "swap": subprocess.check_output(["sysctl", "vm.swapusage"], text=True).strip()}
        data["cache_entries_after"] = [str(p.relative_to(cache)) for p in cache.rglob("*")]
        checkpoint(data)


if __name__ == "__main__":
    main()
