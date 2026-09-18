"""Package a validated staged install into dist/ (plan Section 9).

Packaging is intentionally separate from compilation: it operates on the
already-built `build/stage/cpython-staged/install` tree so a validated
installation can be repackaged without rebuilding it. It must run inside a
Docker stage (plan "Current scope decision"), since it strips and inspects
real ELF binaries and executes the staged interpreter for validation.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from buildsys.inputs import Cache, InputError, canonical_json, load_lock, safe_extract  # noqa: E402
from buildsys.relocate import find_elfs  # noqa: E402

TARGET = "x86_64-unknown-linux-musl"
REVISION = "r1"
ARCHIVE_NAME = f"cpython-3.14.6-{TARGET}-{REVISION}.tar.gz"
SOURCE_DATE_EPOCH = 1704067200

# Non-platform native dependencies actually bundled into the product
# (plan 4/9); Tcl/Tk and the X11 closure are excluded by the current scope
# decision and must never appear here even if a stale build/prefix has them.
BUNDLED_DEPENDENCIES = (
    "openssl", "sqlite", "expat", "zlib", "bzip2", "xz", "zstd",
    "mpdecimal", "libffi", "libedit", "ncurses", "libuuid", "bdb", "pip",
)

REQUIRED_MODULES = (
    "ssl", "hashlib", "sqlite3", "dbm", "decimal", "uuid",
    "xml.etree.ElementTree", "zlib", "bz2", "lzma", "compression.zstd",
    "ctypes", "readline", "curses", "zoneinfo", "socket", "threading",
    "concurrent.futures", "subprocess", "multiprocessing",
)
EXPECTED_MISSING_MODULES = ("_tkinter", "tkinter", "_gdbm")


class PackagingError(Exception):
    """The staged tree could not be turned into a validated artifact."""


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if result.returncode != 0:
        raise PackagingError(f"{cmd}: {result.stderr or result.stdout}")
    return result


def strip_tree(install: Path, *, strip: str = "llvm-strip") -> list[Path]:
    """Strip debug info from shipped ELFs, keeping the dynamic symbol table.

    --strip-unneeded removes local/debug symbols but keeps .dynsym, which
    is what extension modules and embedders resolve PyXxx symbols against
    (plan Section 9: "Stripping must preserve required exported symbols and
    extension-loading behavior").
    """
    stripped = []
    for elf in find_elfs(install):
        _run([strip, "--strip-unneeded", str(elf)])
        stripped.append(elf)
    return stripped


def _reset_metadata(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mtime = SOURCE_DATE_EPOCH
    if info.isfile() and (info.mode & 0o111):
        info.mode = 0o755
    elif info.isfile():
        info.mode = 0o644
    elif info.isdir():
        info.mode = 0o755
    return info


def build_archive(install: Path, dist: Path) -> Path:
    """Deterministic tar.gz: sorted entries, fixed epoch/owner/mode (plan 9)."""
    archive_path = dist / ARCHIVE_NAME
    tmp_path = archive_path.with_suffix(".tmp")
    entries = sorted(install.rglob("*"))
    with tarfile.open(tmp_path, "w:gz", compresslevel=9) as tar:
        for entry in entries:
            arcname = "python/" + str(entry.relative_to(install))
            info = tar.gettarinfo(entry, arcname=arcname)
            info = _reset_metadata(info)
            if entry.is_symlink():
                tar.addfile(info)
            elif entry.is_file():
                with entry.open("rb") as handle:
                    tar.addfile(info, handle)
            elif entry.is_dir():
                tar.addfile(info)
    if archive_path.exists():
        raise PackagingError(f"refusing to overwrite existing {archive_path}")
    os.replace(tmp_path, archive_path)
    return archive_path


def write_sha256sums(dist: Path, archive: Path) -> Path:
    import hashlib
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    path = dist / "SHA256SUMS"
    path.write_text(f"{digest}  {archive.name}\n")
    return path


def compute_inputs(lock_path: Path) -> dict:
    entries = load_lock(lock_path)
    return {
        "target": TARGET,
        "inputs": [
            {
                "name": e.name, "version": e.version, "url": e.url,
                "sha256": e.sha256, "role": e.role, "license": e.license,
                "purpose": e.purpose, "identity": e.identity(),
            }
            for e in entries
        ],
    }


def compute_components(lock_path: Path) -> dict:
    entries = {e.name: e for e in load_lock(lock_path)}
    components = []
    for name in ("cpython", *BUNDLED_DEPENDENCIES):
        entry = entries.get(name)
        if entry is None:
            continue
        components.append({
            "name": entry.name, "version": entry.version,
            "license": entry.license, "purpose": entry.purpose,
            "static": entry.name != "pip",
        })
    return {
        "components": components,
        "excluded_by_scope": {
            "tcl": "GUI-only; excluded by the 2026-09-17 scope decision",
            "tk": "GUI-only; excluded by the 2026-09-17 scope decision",
            "x11": "solely a Tcl/Tk dependency; excluded with it",
        },
    }


def compute_provenance(archive: Path, commands: list[str]) -> dict:
    git_commit = None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True
        )
        if result.returncode == 0:
            git_commit = result.stdout.strip()
    except FileNotFoundError:
        pass
    uname = os.uname()
    return {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_date_epoch": SOURCE_DATE_EPOCH,
        "git_commit": git_commit,
        "host": {
            "kernel": uname.release, "machine": uname.machine,
            "in_container": Path("/.dockerenv").is_file(),
        },
        "python_controller": platform.python_version(),
        "commands": commands,
        "archive_sha256_reported_in": "SHA256SUMS",
    }


def _smoke_import(python: Path) -> tuple[bool, str]:
    modules = ", ".join(REQUIRED_MODULES)
    code = f"import sys; import {modules}; print(sys.version_info[:3])"
    result = subprocess.run([str(python), "-c", code], capture_output=True, text=True)
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def compute_validation(install: Path) -> dict:
    python = install / "bin" / "python3.14"
    ok, output = _smoke_import(python)
    elfs = find_elfs(install)
    elf_report = []
    bad = []
    for elf in elfs:
        readelf = _run(["readelf", "-d", str(elf)])
        needed = [
            line.split("[")[1].rstrip("]")
            for line in readelf.stdout.splitlines() if "NEEDED" in line
        ]
        runpath = [line for line in readelf.stdout.splitlines() if "RUNPATH" in line or "RPATH" in line]
        forbidden = [n for n in needed if n.startswith("libc.so.6") or "GLIBC" in n]
        if forbidden:
            bad.append(str(elf))
        elf_report.append({
            "path": str(elf.relative_to(install)), "needed": needed,
            "runpath": runpath[0].split("[")[1].rstrip("]") if runpath else None,
        })
    interp = _run(["readelf", "-l", str(python)])
    interp_line = next(
        (line for line in interp.stdout.splitlines() if "interpreter" in line), ""
    )
    sysconfig_check = subprocess.run(
        [str(python), "-c",
         "import sysconfig; v=sysconfig.get_config_var('LDFLAGS') or ''; "
         "print('LEAK' if 'build/prefix' in v else 'CLEAN')"],
        capture_output=True, text=True,
    )
    return {
        "sys_version_check": {"ok": ok, "output": output},
        "musl_loader": interp_line.strip(),
        "elf_leak_free": bad == [],
        "elf_forbidden_needed": bad,
        "sysconfig_private_prefix_leak": sysconfig_check.stdout.strip() != "CLEAN",
        "elf_count": len(elf_report),
        "elf_report": elf_report,
        "expected_missing_modules": list(EXPECTED_MISSING_MODULES),
    }


def compute_parity(install: Path, reference_root: Path | None) -> dict:
    rows = []

    def row(area, status, evidence):
        rows.append({"area": area, "status": status, "evidence": evidence})

    python = install / "bin" / "python3.14"
    version = subprocess.run(
        [str(python), "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"],
        capture_output=True, text=True,
    ).stdout.strip()
    row("cpython_version", "match" if version == "3.14.6" else "gap", version)

    row(
        "tcl_tk_gui", "intentional_difference",
        "Tcl/Tk, _tkinter, and the X11 closure are excluded by the "
        "2026-09-17 scope decision; the reference distribution ships them.",
    )
    row(
        "module_build_layout", "intentional_difference",
        "This build ships most extension modules as separate shared "
        ".so files (configure default); the reference statically links "
        "most modules into the interpreter/libpython (plan 2.3 permits "
        "this as a documented difference).",
    )

    if reference_root is not None and (reference_root / "python" / "bin" / "python3.14").is_file():
        ref_python = reference_root / "python" / "bin" / "python3.14"
        for name, code in (
            ("openssl_version", "import ssl; print(ssl.OPENSSL_VERSION)"),
            ("sqlite_version", "import sqlite3; print(sqlite3.sqlite_version)"),
            ("mpdecimal_version", "import decimal; print(decimal.__libmpdec_version__)"),
        ):
            ours = subprocess.run([str(python), "-c", code], capture_output=True, text=True).stdout.strip()
            theirs = subprocess.run([str(ref_python), "-c", code], capture_output=True, text=True).stdout.strip()
            row(name, "match" if ours == theirs else "intentional_difference",
                f"ours={ours!r} reference={theirs!r}")
    else:
        row("reference_binary_comparison", "untested", "reference archive not extracted in this run")

    return {"target": TARGET, "reference": "python-build-standalone 20260610", "rows": rows}


def _time_runs(python: Path, code: str, runs: int = 7) -> dict:
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        result = subprocess.run([str(python), "-c", code], capture_output=True, text=True)
        samples.append(time.perf_counter() - start)
        if result.returncode != 0:
            return {"error": result.stderr.strip(), "runs": runs}
    samples.sort()
    return {
        "runs": runs, "min_s": samples[0], "median_s": samples[len(samples) // 2],
        "max_s": samples[-1],
    }


def compute_benchmarks(python: Path, reference_root: Path | None) -> dict:
    """Lightweight, honestly-labeled timing comparison (plan 8.3).

    This is a handful of wall-clock samples on shared, possibly noisy CI/dev
    hardware, not a controlled pyperf benchmark suite; it is reported as
    such rather than as a precise performance claim.
    """
    workloads = {
        "startup": "pass",
        "json_roundtrip": (
            "import json\n"
            "data=[{'i': i, 's': str(i)*8} for i in range(20000)]\n"
            "for _ in range(20): json.loads(json.dumps(data))"
        ),
        "sha256_1mb": (
            "import hashlib\n"
            "buf=b'x'*1_000_000\n"
            "for _ in range(50): hashlib.sha256(buf).digest()"
        ),
        "decimal_sum": (
            "import decimal\n"
            "d=decimal.Decimal\n"
            "sum(d(i)/d(3) for i in range(20000))"
        ),
    }
    report = {"methodology": (
        "Wall-clock `python3 -c <code>` subprocess timing, 7 samples per "
        "workload, min/median/max reported; no warm-cache pyperf isolation. "
        "Investigate before drawing conclusions from small deltas."
    ), "ours": {}, "reference": {}}
    for name, code in workloads.items():
        report["ours"][name] = _time_runs(python, code)
    if reference_root is not None:
        ref_python = reference_root / "python" / "bin" / "python3.14"
        if ref_python.is_file():
            for name, code in workloads.items():
                report["reference"][name] = _time_runs(ref_python, code)
    return report


def write_parity_md(parity: dict, path: Path) -> None:
    lines = [
        f"# Parity report: {parity['target']} vs {parity['reference']}", "",
        "| Area | Status | Evidence |", "| --- | --- | --- |",
    ]
    for row in parity["rows"]:
        lines.append(f"| {row['area']} | {row['status']} | {row['evidence']} |")
    path.write_text("\n".join(lines) + "\n")


def extract_reference(cache: Cache, lock_path: Path, dest: Path) -> Path | None:
    """Extract the pinned PBS comparison archive; reference-only, never a build input."""
    try:
        entry = next(e for e in load_lock(lock_path) if e.name == "reference-pbs")
        blob = cache.require(entry)
    except (StopIteration, InputError):
        return None
    if dest.exists():
        shutil.rmtree(dest)
    return safe_extract(blob, dest)


def main(argv: list[str] | None = None) -> int:
    compare_only = "--compare-only" in (argv if argv is not None else sys.argv[1:])
    stage = REPO / "build" / "stage" / "cpython-staged" / "install"
    if not stage.is_dir():
        print("FAIL package: no staged install at build/stage/cpython-staged/install; run `build` first")
        return 1
    dist = REPO / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    work = REPO / "build" / "package-work" / "install"
    if work.parent.exists():
        shutil.rmtree(work.parent)
    work.parent.mkdir(parents=True)
    shutil.copytree(stage, work, symlinks=True)

    commands = ["python3 build/deps.py", "python3 build/cpython.py", "python3 build/package.py"]
    try:
        reference_root = extract_reference(
            Cache(REPO / ".cache"), REPO / "sources.lock.json",
            REPO / "build" / "reference-extracted",
        )
        if compare_only:
            parity = compute_parity(stage, reference_root)
            (dist / "parity.json").write_text(canonical_json(parity) + "\n")
            write_parity_md(parity, dist / "parity.md")
            print(f"OK    compare-reference -> {dist / 'parity.md'}")
            return 0

        strip_tree(work)
        validation = compute_validation(work)
        if not validation["sys_version_check"]["ok"]:
            raise PackagingError(f"post-strip smoke import failed: {validation['sys_version_check']['output']}")
        archive = build_archive(work, dist)
        write_sha256sums(dist, archive)
        (dist / "inputs.json").write_text(canonical_json(compute_inputs(REPO / "sources.lock.json")) + "\n")
        (dist / "components.json").write_text(canonical_json(compute_components(REPO / "sources.lock.json")) + "\n")
        (dist / "provenance.json").write_text(canonical_json(compute_provenance(archive, commands)) + "\n")
        (dist / "validation.json").write_text(canonical_json(validation) + "\n")
        parity = compute_parity(work, reference_root)
        (dist / "parity.json").write_text(canonical_json(parity) + "\n")
        write_parity_md(parity, dist / "parity.md")
        benchmarks = compute_benchmarks(work / "bin" / "python3.14", reference_root)
        (dist / "benchmarks.json").write_text(canonical_json(benchmarks) + "\n")
    except (PackagingError, InputError) as error:
        print(f"FAIL package: {error}")
        return 1

    print(f"OK    package -> {dist / ARCHIVE_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
