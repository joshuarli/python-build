"""Package a validated staged install into dist/ (plan Section 9).

Packaging is intentionally separate from compilation: it operates on the
already-built `build/stage/cpython-staged/install` tree so a validated
installation can be repackaged without rebuilding it.

Only three things are format- or platform-specific — how a binary is
stripped (and, on macOS, re-signed), what the binary checks are, and what the
comparison baseline is. Everything else is one pipeline shared by both
families, per plan Section 3's "one package layout".

On the Linux targets this runs inside a Docker stage, because it strips and
inspects ELF binaries and executes the staged interpreter. On macOS it runs
directly: the qualification boundary is the sealed `sandbox-exec` build that
produced the tree, not the packaging step.
"""

from __future__ import annotations

import json
import math
import os
import platform
import random
import shutil
import statistics
import subprocess
import sys
import tarfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from buildsys import macho  # noqa: E402
from buildsys.bootstrap import load_macos_toolchain  # noqa: E402
from buildsys.elf import gnu_stack_report, hardening_report  # noqa: E402
from buildsys.cpython import (  # noqa: E402
    CPYTHON_PGO_HASH_SEED, pgo_profile_task,
)
from buildsys.inputs import Cache, InputError, canonical_json, load_lock, safe_extract  # noqa: E402
from buildsys.relocate import find_elfs  # noqa: E402
from buildsys.scope import (  # noqa: E402
    DISTRIBUTION_EXCLUDED_STDLIB_DIRS,
    EXCLUDED_STDLIB_DIRS,
    ScopeError,
    prune_distribution_payload,
)
from buildsys.standalone_compat import run_standalone_compatibility  # noqa: E402
from buildsys.targets import native_target  # noqa: E402
from buildsys.testsuite import (  # noqa: E402
    classify, report_payload, run_suite, verify_excluded_failures,
)
from buildsys.validate_macos import run_validation  # noqa: E402

TARGET_DESCRIPTION = native_target()
TARGET = TARGET_DESCRIPTION.triple
REVISION = "r2"
ARCHIVE_NAME = f"cpython-3.14.6-{TARGET}-{REVISION}.tar.gz"
SOURCE_DATE_EPOCH = 1704067200

# Non-platform native dependencies actually bundled into the product
# (plan 4/9); Tcl/Tk and the X11 closure are excluded by scope and must never
# appear here even if a stale build/prefix has them. The two families bundle
# different sets because macOS supplies several of these itself (plan 5.2),
# and `pip` is not a component on either — it is deliberately not shipped
# (2026-09-18 scope decision), so listing it would make the manifest claim
# something the tree does not contain.
BUNDLED_DEPENDENCIES_BY_FAMILY = {
    "linux-musl": (
        "openssl", "sqlite", "expat", "zlib", "bzip2", "xz", "zstd",
        "mpdecimal", "libffi", "libedit", "ncurses", "libuuid", "bdb",
    ),
    "macos": (
        "openssl", "sqlite", "expat", "bzip2", "xz", "zstd", "mpdecimal",
        "libffi",
    ),
}

# Taken from the operating system rather than bundled. Listed so the parity
# report can name them instead of leaving their absence unexplained.
PLATFORM_PROVIDED_BY_FAMILY = {
    "linux-musl": (),
    "macos": (
        "zlib", "libedit", "ncurses", "ndbm (dbm backend)",
    ),
}

BUNDLED_DEPENDENCIES = BUNDLED_DEPENDENCIES_BY_FAMILY["linux-musl"]

REQUIRED_MODULES = (
    "ssl", "hashlib", "sqlite3", "dbm", "decimal", "uuid",
    "xml.etree.ElementTree", "zlib", "bz2", "lzma", "compression.zstd",
    "ctypes", "readline", "curses", "zoneinfo", "socket", "threading",
    "concurrent.futures", "subprocess", "multiprocessing",
)
EXPECTED_MISSING_MODULES = ("_tkinter", "tkinter", "_gdbm", "test")
# Absent by decision, not by accident: the GUI closure (2026-09-17) and the
# packaging components (2026-09-18). `_gdbm` is absent because the dbm
# backend is the platform's ndbm and no gdbm is built. `test` remains until
# the CPython regression suite completes, then is removed before archiving.
EXPECTED_EXCLUDED_MODULES = (
    "_tkinter", "tkinter", "idlelib", "turtle", "_gdbm",
    "pip", "ensurepip", "venv", "test",
)
DELIBERATE_EXCLUDED_STDLIB_DIRS = (
    *EXCLUDED_STDLIB_DIRS,
    *DISTRIBUTION_EXCLUDED_STDLIB_DIRS,
)


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
    for name in ("cpython", *BUNDLED_DEPENDENCIES_BY_FAMILY[TARGET_DESCRIPTION.family]):
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
        "platform_provided": list(
            PLATFORM_PROVIDED_BY_FAMILY[TARGET_DESCRIPTION.family]
        ),
        "excluded_by_scope": {
            "tcl": "GUI-only; excluded by the 2026-09-17 scope decision",
            "tk": "GUI-only; excluded by the 2026-09-17 scope decision",
            "x11": "solely a Tcl/Tk dependency; excluded with it",
            "pip": "package manager; excluded by the 2026-09-18 scope decision",
            "ensurepip": "pip installer; excluded with pip",
            "venv": "environment creator; excluded by the 2026-09-18 decision",
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
    build_recipe_path = REPO / "build" / "logs" / "cpython-build.json"
    try:
        cpython_build_recipe = json.loads(build_recipe_path.read_text())
    except (OSError, json.JSONDecodeError):
        cpython_build_recipe = None
    sealed = REPO / "build" / "sealed" / "sealed.json"
    sealed_record = None
    if sealed.is_file():
        try:
            record = json.loads(sealed.read_text())
            sealed_record = {
                "sealed": record.get("sealed"),
                "network_boundary_verified": bool(
                    record.get("network_boundary", {}).get("ok")
                    and record.get("network_boundary_after_build", {}).get("ok")
                ),
                "containment": record.get("containment"),
                "duration_seconds": record.get("duration_seconds"),
                "commands": record.get("commands"),
            }
        except (OSError, json.JSONDecodeError):
            sealed_record = {"error": "unreadable"}
    recipe_mode = (
        cpython_build_recipe.get("build_mode")
        if isinstance(cpython_build_recipe, dict) else None
    )
    build_mode = recipe_mode or (
        "sealed" if sealed_record and sealed_record.get("sealed") else "development"
    )
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
        "cpython_build_recipe": cpython_build_recipe,
        # Whether the tree this archive was built from came out of a sealed
        # offline run, and what that containment actually was. A development
        # build is not qualification evidence, so the distinction is recorded
        # rather than left to whoever reads the reports later.
        "build_mode": build_mode,
        "sealed_build": sealed_record if build_mode == "sealed" else None,
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
    stack_violations = []
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
        stack = gnu_stack_report(_run(["readelf", "-lW", str(elf)]).stdout)
        if not stack["ok"]:
            stack_violations.append(str(elf.relative_to(install)))
        elf_report.append({
            "path": str(elf.relative_to(install)), "needed": needed,
            "runpath": runpath[0].split("[")[1].rstrip("]") if runpath else None,
            "gnu_stack": stack,
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
    configured = _run([
        str(python), "-c",
        "import json, sysconfig; print(json.dumps({k: sysconfig.get_config_var(k) "
        "for k in ('CFLAGS', 'CFLAGS_NODIST', 'PY_CFLAGS', 'PY_CFLAGS_NODIST', 'CPPFLAGS')}))",
    ])
    configured_flags = json.loads(configured.stdout)
    compiler_flags = " ".join(
        value for value in configured_flags.values() if isinstance(value, str)
    )
    shared_name = _run([
        str(python), "-c",
        "import sysconfig; print(sysconfig.get_config_var('INSTSONAME'))",
    ]).stdout.strip()
    libpython = install / "lib" / shared_name
    if not libpython.is_file():
        raise PackagingError(f"sysconfig names a missing shared libpython: {libpython}")
    hardening_symbols = {
        "python3.14": _run([
            "readelf", "--dyn-syms", "-W", str(python),
        ]).stdout,
        "libpython": _run([
            "readelf", "--dyn-syms", "-W", str(libpython),
        ]).stdout,
    }
    hardening = hardening_report(compiler_flags, hardening_symbols)
    return {
        "target": TARGET,
        "sys_version_check": {"ok": ok, "output": output},
        "musl_loader": interp_line.strip(),
        "musl_loader_matches_target": TARGET_DESCRIPTION.musl_loader in interp_line,
        "elf_leak_free": bad == [],
        "elf_forbidden_needed": bad,
        "sysconfig_private_prefix_leak": sysconfig_check.stdout.strip() != "CLEAN",
        "elf_count": len(elf_report),
        "elf_report": elf_report,
        "elf_stack_permissions_ok": bool(elf_report) and not stack_violations,
        "elf_stack_violations": stack_violations,
        "elf_hardening": hardening,
        "expected_missing_modules": list(EXPECTED_MISSING_MODULES),
    }


def reference_binary(reference_root: Path | None) -> Path | None:
    """The reference python3.14, only when runnable on this target.

    The pinned PBS reference archive (sources.lock.json `reference-pbs`) is
    x86_64-only. Executing it under another target would require setting up
    cross-arch emulation this project does not otherwise need; skip rather
    than silently attempt it.
    """
    if reference_root is None or TARGET_DESCRIPTION.machine != "x86_64":
        return None
    candidate = reference_root / "python" / "bin" / "python3.14"
    return candidate if candidate.is_file() else None


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

    ref_python = reference_binary(reference_root)
    if ref_python is not None:
        for name, code in (
            ("openssl_version", "import ssl; print(ssl.OPENSSL_VERSION)"),
            ("sqlite_version", "import sqlite3; print(sqlite3.sqlite_version)"),
            ("mpdecimal_version", "import decimal; print(decimal.__libmpdec_version__)"),
        ):
            ours = subprocess.run([str(python), "-c", code], capture_output=True, text=True).stdout.strip()
            theirs = subprocess.run([str(ref_python), "-c", code], capture_output=True, text=True).stdout.strip()
            row(name, "match" if ours == theirs else "intentional_difference",
                f"ours={ours!r} reference={theirs!r}")
    elif reference_root is None:
        row("reference_binary_comparison", "untested", "reference archive not extracted in this run")
    else:
        row(
            "reference_binary_comparison", "untested",
            f"the pinned PBS reference archive is x86_64-only; running it under "
            f"{TARGET} would need cross-arch emulation this project does not "
            f"set up, so the running-binary comparison is skipped on this target",
        )

    return {"target": TARGET, "reference": "python-build-standalone 20260610", "rows": rows}


BENCHMARK_WORKLOADS = {
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
    "sqlite_inserts": (
        "import sqlite3, tempfile, os\n"
        "d=tempfile.mkdtemp(); con=sqlite3.connect(os.path.join(d,'b.db'))\n"
        "con.execute('create table t(a, b)')\n"
        "con.executemany('insert into t values (?, ?)', [(i, str(i)) for i in range(20000)])\n"
        "con.commit(); con.close()"
    ),
}


def _time_runs(python: Path, code: str, runs: int = 7, *,
               sandboxed: bool = False, workdir: Path | None = None) -> dict:
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        result = _probe(python, code, sandboxed=sandboxed, workdir=workdir)
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
    workloads = BENCHMARK_WORKLOADS
    report = {"methodology": (
        "Wall-clock `python3 -c <code>` subprocess timing, 7 samples per "
        "workload, min/median/max reported; no warm-cache pyperf isolation. "
        "Investigate before drawing conclusions from small deltas."
    ), "ours": {}, "reference": {}}
    for name, code in workloads.items():
        report["ours"][name] = _time_runs(python, code)
    ref_python = reference_binary(reference_root)
    if ref_python is not None:
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


def extract_reference(
    cache: Cache, lock_path: Path, dest: Path, entry=None
) -> Path | None:
    """Extract the pinned PBS comparison archive; reference-only, never a build input.

    `entry` is the target's already-resolved reference pin. When omitted the
    legacy unqualified name is used, which is how the frozen Linux targets
    resolve theirs.
    """
    if entry is None:
        try:
            entry = next(e for e in load_lock(lock_path) if e.name == "reference-pbs")
        except StopIteration:
            return None
    try:
        blob = cache.require(entry)
    except InputError:
        return None
    if dest.exists():
        shutil.rmtree(dest)
    return safe_extract(blob, dest)


# --------------------------------------------------------------------------
# macOS packaging path (plan Sections 6, 8, 9)
#
# The pipeline above is shared; only three things are format- or
# platform-specific: how a binary is stripped (and re-signed), what the
# binary checks are, and what the comparison baseline is.
# --------------------------------------------------------------------------


def strip_tree_macos(install: Path) -> list[Path]:
    """Strip debug info, then re-sign every image touched.

    `--strip-debug` removes debug information while keeping the symbol table,
    so exported `PyInit_*` and `Py*` symbols survive and extension loading is
    unaffected. On Apple Silicon any edit invalidates the code signature and
    an unsigned Mach-O will not launch, so re-signing is part of stripping
    rather than a separate step someone has to remember (plan Section 9).
    """
    locked = load_macos_toolchain(REPO / "bootstrap.lock.json")
    strip = locked.llvm_prefix / "bin" / "llvm-strip"
    stripped = []
    for image in macho.find_machos(install):
        _run([str(strip), "--strip-debug", str(image)])
        macho.sign_adhoc(image)
        stripped.append(image)
    return stripped


def reference_entry(lock_path: Path) -> object | None:
    """The comparison-only reference pin for this target, if present."""
    entries = load_lock(lock_path)
    qualified = f"reference-pbs-{TARGET}"
    for entry in entries:
        if entry.name == qualified:
            return entry
    for entry in entries:
        if entry.name == "reference-pbs":  # legacy unqualified Linux pin
            return entry
    return None


def reference_python(reference_root: Path | None) -> Path | None:
    if reference_root is None:
        return None
    candidate = Path(reference_root) / "python" / "bin" / "python3.14"
    return candidate if candidate.is_file() else None


def _probe(python: Path, code: str, *, sandboxed: bool = False, workdir: Path | None = None):
    """Run a probe, optionally under the sealed profile.

    Reference binaries are third-party executable inputs, so they are run
    with the network denied and a scratch HOME rather than on the bare host
    (plan Section 8.2).
    """
    if not sandboxed or workdir is None:
        return subprocess.run([str(python), "-c", code], capture_output=True, text=True)
    from buildsys.sandbox import SealedRun

    workdir.mkdir(parents=True, exist_ok=True)
    sealed = SealedRun(write_paths=[workdir], home=workdir / "home")
    return sealed.run([str(python), "-c", code], cwd=workdir, env=sealed.environment())


VERSION_PROBES = {
    "openssl_version": "import ssl; print(ssl.OPENSSL_VERSION)",
    "sqlite_version": "import sqlite3; print(sqlite3.sqlite_version)",
    "mpdecimal_version": "import decimal; print(decimal.__libmpdec_version__)",
    "libffi_note": "import ctypes; print('ctypes ok')",
}


def compute_parity_macos(install: Path, reference_root: Path | None, workdir: Path) -> dict:
    """Classify this build against the pinned reference (plan Section 2.3)."""
    rows: list[dict] = []

    def row(area: str, status: str, evidence: str) -> None:
        rows.append({"area": area, "status": status, "evidence": evidence})

    python = install / "bin" / "python3.14"
    version = _probe(python, "import sys; print('.'.join(map(str, sys.version_info[:3])))")
    row("cpython_version", "match" if version.stdout.strip() == "3.14.6" else "gap",
        version.stdout.strip())

    ref_python = reference_python(reference_root)
    if ref_python is None:
        row("optimization", "untested", "reference archive not extracted in this run")
    else:
        optimization_code = (
            "import json,sysconfig; a=sysconfig.get_config_var('CONFIG_ARGS') or ''; "
            "print(json.dumps({'pgo':'--enable-optimizations' in a, "
            "'lto':'--with-lto' in a}))"
        )
        ours_optimization = _probe(python, optimization_code)
        reference_optimization = _probe(
            ref_python, optimization_code, sandboxed=True,
            workdir=workdir / "reference-optimization",
        )
        if ours_optimization.returncode or reference_optimization.returncode:
            row("optimization", "untested", "could not read configure optimization flags")
        else:
            ours_flags = json.loads(ours_optimization.stdout.strip().splitlines()[-1])
            reference_flags = json.loads(
                reference_optimization.stdout.strip().splitlines()[-1]
            )
            matched = all(ours_flags.values()) and all(reference_flags.values())
            row(
                "optimization", "match" if matched else "gap",
                f"ours={ours_flags} (ThinLTO explicit; PGO recipe in provenance.json); "
                f"reference={reference_flags} (pinned 20260610 pgo+lto archive)",
            )
    row("deployment_floor", "intentional_difference",
        "Reference LC_BUILD_VERSION minos is 11.0; this build declares 26.0 "
        "(plan scope decision 2026-09-18) and will not load on older macOS.")
    row("package_manager", "intentional_difference",
        "The reference ships pip. This distribution removes pip, ensurepip (with its "
        "bundled wheel) and venv by the 2026-09-18 scope decision; `python -m venv` "
        "and `python -m pip` fail by design. Consumers needing an isolated "
        "environment must supply their own tooling.")
    row("tcl_tk_gui", "intentional_difference",
        "Tcl/Tk, _tkinter and the X11 closure are excluded by the 2026-09-17 scope "
        "decision; the reference ships them, including its AppKit/Cocoa/Carbon links.")
    row("dependency_split", "intentional_difference",
        "Derived from the reference's own load commands, and matched: both use the "
        "platform's zlib (/usr/lib/libz.1.dylib), libedit (/usr/lib/libedit.3.dylib) "
        "and ncurses (/usr/lib/libncurses.5.4.dylib, libpanel.5.4.dylib), and both "
        "statically link their own OpenSSL, SQLite, Expat, libffi, bzip2, xz, zstd "
        "and mpdecimal.")
    row("libffi_version", "intentional_difference",
        "This build pins libffi 3.8.0; the reference uses 3.4.6, whose aarch64 "
        "sysv.S emits cfi_startproc before the function label and is rejected by "
        "LLVM's Darwin assembler. See sources.lock.json for the recorded reason.")
    row("module_build_layout", "intentional_difference",
        "This build ships extension modules as separate .so files (configure "
        "default); the reference's layout differs (plan Section 2.3 permits this).")

    if ref_python is None:
        row("reference_binary_comparison", "untested",
            "reference archive not extracted in this run")
    else:
        for name, code in VERSION_PROBES.items():
            ours = _probe(python, code)
            theirs = _probe(ref_python, code, sandboxed=True, workdir=workdir / "reference")
            same = ours.stdout.strip() == theirs.stdout.strip()
            note = "" if same else "  (expected: different bundled version)"
            row(name, "match" if same else "intentional_difference",
                f"ours={ours.stdout.strip()!r} reference={theirs.stdout.strip()!r}{note}")

    counts: dict[str, int] = {}
    for entry in rows:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    return {
        "target": TARGET,
        "reference": "python-build-standalone 20260610 (aarch64-apple-darwin, PGO+LTO)",
        "rows": rows,
        "status_counts": counts,
        "gap_rows": [r["area"] for r in rows if r["status"] == "gap"],
    }


MACOS_BENCHMARK_PAIRS = 21
MACOS_BENCHMARK_BOOTSTRAPS = 3000


def _timed_macos_probe(python: Path, code: str, workdir: Path) -> float:
    start = time.perf_counter()
    result = _probe(python, code, sandboxed=True, workdir=workdir)
    elapsed = time.perf_counter() - start
    if result.returncode != 0:
        raise PackagingError(
            f"benchmark failed for {python}: {result.stderr.strip() or result.stdout.strip()}"
        )
    return elapsed


def _bootstrap_median_interval(values: list[float], seed: int) -> list[float]:
    """Deterministic percentile interval for the median of paired ratios."""
    randomizer = random.Random(seed)
    medians = sorted(
        statistics.median(randomizer.choice(values) for _ in values)
        for _ in range(MACOS_BENCHMARK_BOOTSTRAPS)
    )

    def percentile(fraction: float) -> float:
        offset = (len(medians) - 1) * fraction
        lower = math.floor(offset)
        upper = math.ceil(offset)
        if lower == upper:
            return medians[lower]
        return medians[lower] + (medians[upper] - medians[lower]) * (offset - lower)

    return [percentile(0.025), percentile(0.975)]


def _paired_macos_benchmark(
    name: str,
    code: str,
    ours: Path,
    reference: Path,
    workdir: Path,
) -> dict:
    ours_work = workdir / "ours"
    reference_work = workdir / "reference"
    # Warm both trees once before collecting paired measurements.
    _timed_macos_probe(ours, code, ours_work)
    _timed_macos_probe(reference, code, reference_work)

    ours_samples: list[float] = []
    reference_samples: list[float] = []
    ratios: list[float] = []
    for sample in range(MACOS_BENCHMARK_PAIRS):
        if sample % 2 == 0:
            ours_elapsed = _timed_macos_probe(ours, code, ours_work)
            reference_elapsed = _timed_macos_probe(reference, code, reference_work)
        else:
            reference_elapsed = _timed_macos_probe(reference, code, reference_work)
            ours_elapsed = _timed_macos_probe(ours, code, ours_work)
        ours_samples.append(ours_elapsed)
        reference_samples.append(reference_elapsed)
        ratios.append(ours_elapsed / reference_elapsed)

    median_ratio = statistics.median(ratios)
    interval = _bootstrap_median_interval(ratios, sum(name.encode("utf-8")))

    def summary(values: list[float]) -> dict:
        ordered = sorted(values)
        return {
            "runs": len(values),
            "min_s": ordered[0],
            "median_s": statistics.median(values),
            "max_s": ordered[-1],
            "samples_s": values,
        }

    return {
        "ours": summary(ours_samples),
        "reference": summary(reference_samples),
        "paired_comparison": {
            "ratio_ours_over_reference": median_ratio,
            "relative_gap_percent": (median_ratio - 1.0) * 100.0,
            "ratio_95_percent_bootstrap_interval": interval,
            "within_noise_at_95_percent": interval[0] <= 1.0 <= interval[1],
            "paired_ratios": ratios,
        },
    }


def compute_benchmarks_macos(python: Path, reference_root: Path | None, workdir: Path) -> dict:
    """Compare same-host, paired macOS timings and estimate measurement noise."""
    recipe_path = REPO / "build" / "logs" / "cpython-build.json"
    try:
        recipe = json.loads(recipe_path.read_text())
    except (OSError, json.JSONDecodeError):
        recipe = None
    report: dict = {
        "methodology": (
            f"One warm-up per interpreter followed by {MACOS_BENCHMARK_PAIRS} paired "
            "wall-clock subprocess runs per workload. Pair order alternates to reduce "
            "time-order bias. Both interpreters run under the same network-denied "
            "sandbox with separate writable scratch directories. Timings include "
            "interpreter startup and sandbox launch. The median paired ours/reference "
            f"ratio gets a deterministic {MACOS_BENCHMARK_BOOTSTRAPS}-resample 95% "
            "bootstrap interval. CPU frequency and host load are not isolated."
        ),
        "optimization_disclosure": {
            "reference": "PGO+LTO (python-build-standalone 20260610)",
            "ours": recipe.get("optimization") if recipe else "build recipe unavailable",
        },
        "interpretation": (
            "A 95% interval containing 1.0 means this run did not resolve a "
            "difference for that workload; it does not prove equivalence on other "
            "hosts or workloads. Ratios above 1.0 mean ours took longer."
        ),
        "ours": {},
        "reference": {},
        "comparisons": {},
    }
    ref_python = reference_python(reference_root)
    if ref_python is None:
        report["reference_error"] = "pinned arm64 reference interpreter is unavailable"
        return report
    for name, code in BENCHMARK_WORKLOADS.items():
        report["comparisons"][name] = _paired_macos_benchmark(
            name, code, python, ref_python, workdir / name
        )
        paired = report["comparisons"][name]
        report["ours"][name] = paired["ours"]
        report["reference"][name] = paired["reference"]
    return report


def require_macos_pgo_recipe() -> dict:
    """Require a successful build's explicit, self-consistent PGO receipt."""
    recipe_path = REPO / "build" / "logs" / "cpython-build.json"
    try:
        recipe = json.loads(recipe_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise PackagingError(f"macOS PGO build recipe is missing or invalid: {error}") from error
    optimization = recipe.get("optimization", {})
    jobs = optimization.get("pgo_jobs")
    if recipe.get("target") != TARGET or not optimization.get("pgo"):
        raise PackagingError("staged macOS build has no matching PGO recipe")
    if type(jobs) is not int or jobs < 1:
        raise PackagingError("macOS PGO recipe has no valid worker count")
    if optimization.get("profile_task") != pgo_profile_task(jobs):
        raise PackagingError("macOS PGO recipe has an unexpected PROFILE_TASK")
    if recipe.get("environment", {}).get("PYTHONHASHSEED") != CPYTHON_PGO_HASH_SEED:
        raise PackagingError("macOS PGO recipe has no fixed Python hash seed")
    profile_data = optimization.get("profile_data", {})
    profile_hash = profile_data.get("sha256")
    profile_size = profile_data.get("size_bytes")
    if (profile_data.get("path") != "code.profclangd"
            or not isinstance(profile_hash, str)
            or len(profile_hash) != 64
            or any(char not in "0123456789abcdef" for char in profile_hash)
            or type(profile_size) is not int or profile_size < 1):
        raise PackagingError("macOS PGO recipe has no valid merged profile receipt")
    if not Path(optimization.get("llvm_profdata", "")).is_file():
        raise PackagingError("macOS PGO recipe's llvm-profdata is not present")
    source = recipe.get("source", {})
    locked_cpython = next(
        entry for entry in load_lock(REPO / "sources.lock.json")
        if entry.name == "cpython"
    )
    if (source.get("name"), source.get("version"), source.get("sha256")) != (
        locked_cpython.name, locked_cpython.version, locked_cpython.sha256
    ):
        raise PackagingError("macOS PGO recipe does not match the locked CPython source")
    if "-fno-omit-frame-pointer" in recipe.get("environment", {}).get("CFLAGS", ""):
        raise PackagingError("macOS PGO recipe unexpectedly retains frame pointers")
    return recipe


def main(argv: list[str] | None = None) -> int:
    compare_only = "--compare-only" in (argv if argv is not None else sys.argv[1:])
    stage = REPO / "build" / "stage" / "cpython-staged" / "install"
    if not stage.is_dir():
        print("FAIL package: no staged install at build/stage/cpython-staged/install; run `build` first")
        return 1
    # Namespaced by target triple: a host accumulating dist/ output from
    # both `docker build --platform linux/amd64` and `--platform linux/arm64`
    # sealed runs must not have one target's package.py silently overwrite
    # the other's reports (only the tarball name itself is already unique).
    dist = REPO / "dist" / TARGET
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "validation.json").unlink(missing_ok=True)
    work = REPO / "build" / "package-work" / "install"
    if work.parent.exists():
        shutil.rmtree(work.parent)
    work.parent.mkdir(parents=True)
    shutil.copytree(stage, work, symlinks=True)

    commands = ["python3 build/deps.py", "python3 build/cpython.py", "python3 build/package.py"]
    macos = TARGET_DESCRIPTION.is_macos
    try:
        reference_root = extract_reference(
            Cache(REPO / ".cache"), REPO / "sources.lock.json",
            REPO / "build" / "reference-extracted", reference_entry(REPO / "sources.lock.json"),
        )
        if compare_only:
            parity = (
                compute_parity_macos(stage, reference_root, REPO / "build" / "reference-work")
                if macos else compute_parity(stage, reference_root)
            )
            (dist / "parity.json").write_text(canonical_json(parity) + "\n")
            write_parity_md(parity, dist / "parity.md")
            print(f"OK    compare-reference -> {dist / 'parity.md'}")
            return 0

        if macos:
            recipe = require_macos_pgo_recipe()
            commands[1] += (
                " --pgo-jobs "
                + str(recipe["optimization"]["pgo_jobs"])
            )

        if macos:
            strip_tree_macos(work)
            validation = run_validation(work, REPO / "build" / "validate-work", TARGET_DESCRIPTION)
            # The regression suite runs against a *disposable copy* of the
            # install tree before final distribution pruning. Several tests
            # write into the tree they exercise (test_compileall compiles the
            # standard library), so running them against the tree being
            # packaged would mutate the artifact and make a second run differ
            # for reasons that have nothing to do with the product.
            suite_tree = REPO / "build" / "package-work" / "regression-copy"
            if suite_tree.exists():
                shutil.rmtree(suite_tree)
            shutil.copytree(work, suite_tree, symlinks=True)
            suite_python = suite_tree / "bin" / "python3.14"

            def fresh_python() -> Path:
                retry_tree = REPO / "build" / "package-work" / "regression-retry"
                if retry_tree.exists():
                    shutil.rmtree(retry_tree)
                shutil.copytree(work, retry_tree, symlinks=True)
                return retry_tree / "bin" / "python3.14"

            suite = run_suite(suite_python)
            solo = verify_excluded_failures(
                suite_python, suite["failed_files"], fresh_python=fresh_python
            )
            suite["classification"] = classify(solo)
            validation["regression_suite"] = report_payload(suite)
            validation["regression_suite"]["solo_findings"] = {
                name: finding["failures"] for name, finding in solo.items()
            }
            validation["regression_suite"]["solo_reruns"] = solo
            validation["regression_suite"]["failure_output_tail"] = suite["output_tail"]
            validation["regression_suite"]["ran_against"] = (
                "a disposable copy of the install tree before final distribution "
                "pruning, so test-written bytecode cannot enter the artifact"
            )
            shutil.rmtree(suite_tree, ignore_errors=True)
            failed_checks = list(validation["failed"])
            if not validation["regression_suite"]["ok"]:
                failed_checks.append("regression_suite")
                print("FAIL  regression suite reported: "
                      + ", ".join(validation["regression_suite"]["unexpected_failures"]),
                      flush=True)
            if failed_checks:
                validation["ok"] = False
                (dist / "validation.json").write_text(
                    canonical_json(validation) + "\n"
                )
                raise PackagingError("validation failed: " + ", ".join(failed_checks))
        else:
            strip_tree(work)
        distribution_scope = prune_distribution_payload(work)
        if not macos:
            # Validate the tree after both stripping and distribution pruning:
            # elf_report must describe exactly the bytes that enter the archive.
            validation = compute_validation(work)
            if not validation["sys_version_check"]["ok"]:
                raise PackagingError(f"post-strip smoke import failed: {validation['sys_version_check']['output']}")
            if not validation["musl_loader_matches_target"]:
                raise PackagingError(
                    f"PT_INTERP {validation['musl_loader']!r} does not match "
                    f"expected {TARGET_DESCRIPTION.musl_loader!r} for target {TARGET}"
                )
            if not validation["elf_stack_permissions_ok"]:
                raise PackagingError(
                    "packaged ELF objects request an executable or unknown stack: "
                    + ", ".join(validation["elf_stack_violations"][:10])
                )
            if not validation["elf_hardening"]["ok"]:
                raise PackagingError(
                    "packaged CPython does not satisfy clang/musl hardening checks"
                )
        validation["scope"] = {
            "excluded_by_scope": list(EXPECTED_EXCLUDED_MODULES),
            "excluded_stdlib_dirs": list(DELIBERATE_EXCLUDED_STDLIB_DIRS),
            "distribution_payload": distribution_scope,
        }
        compatibility = run_standalone_compatibility(
            work / "bin" / "python3.14", work, TARGET_DESCRIPTION
        )
        validation["pbs_distribution_compatibility"] = compatibility
        if not compatibility["ok"]:
            failures = [
                name for name, result in compatibility["checks"].items()
                if result.get("status") == "failed"
            ]
            (dist / "validation.json").write_text(canonical_json(validation) + "\n")
            raise PackagingError(
                "PBS distribution compatibility checks failed: " + ", ".join(failures)
            )
        archive = build_archive(work, dist)
        write_sha256sums(dist, archive)
        (dist / "inputs.json").write_text(canonical_json(compute_inputs(REPO / "sources.lock.json")) + "\n")
        (dist / "components.json").write_text(canonical_json(compute_components(REPO / "sources.lock.json")) + "\n")
        (dist / "provenance.json").write_text(canonical_json(compute_provenance(archive, commands)) + "\n")
        (dist / "validation.json").write_text(canonical_json(validation) + "\n")
        if macos:
            parity = compute_parity_macos(work, reference_root, REPO / "build" / "reference-work")
            benchmarks = compute_benchmarks_macos(
                work / "bin" / "python3.14", reference_root, REPO / "build" / "reference-work"
            )
        else:
            parity = compute_parity(work, reference_root)
            benchmarks = compute_benchmarks(work / "bin" / "python3.14", reference_root)
        (dist / "parity.json").write_text(canonical_json(parity) + "\n")
        write_parity_md(parity, dist / "parity.md")
        (dist / "benchmarks.json").write_text(canonical_json(benchmarks) + "\n")
    except (PackagingError, InputError, ScopeError) as error:
        print(f"FAIL package: {error}")
        return 1

    print(f"OK    package -> {dist / ARCHIVE_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
