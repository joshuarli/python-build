"""Build the locked CPython release against the private prefix (plan 5.3).

The staged installation lands in build/stage; the relocation decision
(destining a neutral prefix rather than the checkout) belongs to packaging.

The relocation step is per-format: the frozen Linux targets rewrite ELF
rpaths with patchelf, macOS rewrites Mach-O install names and adds
`@loader_path` search paths. Both run immediately after `make install`, so
the tree that later phases see is already relocatable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from buildsys import macho  # noqa: E402
from buildsys.bootstrap import (  # noqa: E402
    BootstrapError, load_macos_toolchain, toolchain_for,
)
from buildsys.cpython import (  # noqa: E402
    configuration, resolve_build_jobs, resolve_pgo_jobs,
)
from buildsys.inputs import Cache, InputError, load_lock, safe_extract  # noqa: E402
from buildsys.filc_runtime import relocate_filc  # noqa: E402
from buildsys.patches import (  # noqa: E402
    PatchError, apply_patch_set, cpython_patch_directories,
)
from buildsys.recipes import BuildError, run  # noqa: E402
from buildsys.relocate import RelocationError, macho_relocate, relocate  # noqa: E402
from buildsys.scope import (
    ScopeError, enforce_exclusions, probe_in_process, verify_exclusions,
)  # noqa: E402
from buildsys.targets import (  # noqa: E402
    Target, UnsupportedTargetError, native_target, target_for_host,
)

CONFIGURE_PREFIX = "/install"
JOBS = str(resolve_build_jobs())


def verify_deployment_floor(install: Path, target: Target) -> dict:
    """Every shipped image must declare the target's macOS floor (plan 5.1).

    An unset `-mmacosx-version-min` silently inherits the SDK's version, which
    is newer than the declared floor and would make the artifact refuse to run
    on macOS releases the manifest claims. This is checked rather than
    assumed because the failure is invisible until someone runs it.
    """
    report: dict[str, object] = {
        "expected_minos": target.deployment_target,
        "images": {},
        "mismatches": [],
    }
    images = report["images"]
    mismatches = report["mismatches"]
    for image in macho.find_machos(install):
        version = macho.build_version(image)
        name = str(image.relative_to(install))
        if version is None:
            mismatches.append(f"{name}: no LC_BUILD_VERSION")
            continue
        images[name] = {"minos": version.minos, "sdk": version.sdk}
        if version.minos != target.deployment_target:
            mismatches.append(f"{name}: minos {version.minos} != {target.deployment_target}")
    return report


def build(
    work: Path,
    prefix: Path,
    stage: Path,
    logs: Path,
    cache: Cache,
    *,
    target: Target | None = None,
    pgo_jobs: int | None = None,
) -> Path:
    target = target or native_target()
    if pgo_jobs is not None and not target.is_macos:
        raise BuildError("--pgo-jobs is only supported for the macOS PGO build")
    resolved_pgo_jobs = resolve_pgo_jobs(pgo_jobs) if target.is_macos else None
    if target.is_macos:
        # Never let a failed rebuild leave an older PGO recipe looking current.
        (logs / "cpython-build.json").unlink(missing_ok=True)
    pin = next(
        entry for entry in load_lock(REPO / "sources.lock.json") if entry.name == "cpython"
    )
    blob = cache.require(pin)
    # safe_extract refuses an existing destination, so clear our own scratch
    # rather than making the caller do it before every rebuild.
    if (work / "cpython").exists():
        shutil.rmtree(work / "cpython")
    source = safe_extract(blob, work / "cpython") / f"Python-{pin.version}"
    for patch_dir in cpython_patch_directories(REPO / "patches", target):
        apply_patch_set(source, patch_dir)
    build_directory = work / "cpython-build"
    if build_directory.exists():
        shutil.rmtree(build_directory)
    build_directory.mkdir(parents=True)
    toolchain = toolchain_for(target, REPO / "bootstrap.lock.json")
    profile_toolchain = (
        load_macos_toolchain(REPO / "bootstrap.lock.json")
        if target.is_macos else None
    )
    args, env_overrides = configuration(
        prefix, target, pgo_jobs=resolved_pgo_jobs
    )
    if target.is_macos:
        # CPython's configure probe can find Apple's generic llvm-profdata,
        # which may not match the locked clang bitcode. Name the profiler from
        # the same digest-pinned official LLVM prefix as CC.
        assert profile_toolchain is not None
        env_overrides["LLVM_PROFDATA"] = str(profile_toolchain.llvm_profdata)
    env = toolchain.env(
        {
            **env_overrides,
            "SOURCE_DATE_EPOCH": "1704067200",
            "PKG_CONFIG": "pkg-config",
        }
    )
    configure = source / "configure"
    run(
        [str(configure), f"--prefix={CONFIGURE_PREFIX}", *args],
        cwd=build_directory,
        env=env,
        log=logs / "cpython-configure.log",
    )
    run(
        [toolchain.make, "-j", str(toolchain.jobs) if target.is_filc else JOBS],
        cwd=build_directory,
        env=env,
        log=logs / "cpython-make.log",
    )
    staged = stage / "cpython-staged"
    if staged.exists():
        shutil.rmtree(staged)
    staged.parent.mkdir(parents=True, exist_ok=True)
    install_command = [toolchain.make, "install", f"DESTDIR={staged}"]
    if target.is_filc:
        # CPython's default compileall -j0 sees all host CPUs even when the
        # Fil-C build container has a much smaller CPU and memory budget.
        install_command.append("COMPILEALL_OPTS=-j2")
    run(
        install_command,
        cwd=build_directory,
        env=env,
        log=logs / "cpython-install.log",
    )
    install = staged / CONFIGURE_PREFIX.lstrip("/")
    if target.is_macos:
        macho_relocate(install, prefix, configure_prefix=CONFIGURE_PREFIX)
        floor = verify_deployment_floor(install, target)
        (logs / "minos.json").write_text(
            json.dumps(floor, indent=2, sort_keys=True) + "\n"
        )
        if floor["mismatches"]:
            raise RelocationError(
                "deployment floor mismatch: " + "; ".join(floor["mismatches"][:5])
            )
    elif target.is_filc:
        if toolchain.filc_pizfix is None:
            raise BuildError("Fil-C toolchain has no verified Pizfix runtime")
        relocate_filc(install, prefix, toolchain.filc_pizfix, target)
    else:
        relocate(install, prefix)
    # Scope enforcement runs after relocation so the shebang rewrite cannot
    # resurrect a launcher that was meant to be removed, and before anything
    # downstream treats the tree as shippable.
    report = enforce_exclusions(install)
    (logs / "scope.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    remaining = verify_exclusions(install)
    if remaining:
        raise ScopeError("excluded components still present: " + ", ".join(remaining))
    importable = probe_in_process(install / "bin" / "python3.14")
    leaked = sorted(name for name, present in importable.items() if present)
    if leaked:
        raise ScopeError(f"excluded modules are still importable: {', '.join(leaked)}")
    if target.is_macos:
        profile_path = build_directory / "code.profclangd"
        try:
            profile_bytes = profile_path.read_bytes()
        except OSError as error:
            raise BuildError(
                f"CPython did not leave merged PGO data at {profile_path}: {error}"
            ) from error
        recipe = {
            "target": target.triple,
            "build_mode": "development",
            "source": {
                "name": pin.name,
                "version": pin.version,
                "sha256": pin.sha256,
            },
            "optimization": {
                "pgo": True,
                "pgo_jobs": resolved_pgo_jobs,
                "profile_task": env["PROFILE_TASK"],
                "llvm_profdata": env["LLVM_PROFDATA"],
                "profile_data": {
                    "path": profile_path.name,
                    "sha256": hashlib.sha256(profile_bytes).hexdigest(),
                    "size_bytes": len(profile_bytes),
                },
                "lto": "thin",
                "configure_args": args,
            },
            "toolchain": profile_toolchain.identity(),
            "commands": {
                "configure": [str(configure), f"--prefix={CONFIGURE_PREFIX}", *args],
                "build": [toolchain.make, "-j", JOBS],
                "install": [toolchain.make, "install", f"DESTDIR={staged}"],
            },
            "environment": {
                key: env[key]
                for key in (
                    "CC", "CFLAGS", "CPPFLAGS", "LDFLAGS", "LLVM_PROFDATA",
                    "MACOSX_DEPLOYMENT_TARGET", "PROFILE_TASK", "SDKROOT",
                    "SOURCE_DATE_EPOCH", "PYTHONHASHSEED",
                )
                if key in env
            },
        }
        (logs / "cpython-build.json").write_text(
            json.dumps(recipe, indent=2, sort_keys=True) + "\n"
        )
    print(f"      removed {len(report['removed'])} excluded path(s)", flush=True)
    return staged


def _positive_int(value: str) -> int:
    try:
        result = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if result < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the locked CPython source")
    parser.add_argument("--target", default=native_target().triple)
    parser.add_argument(
        "--pgo-jobs", type=_positive_int,
        help="number of workers for the macOS CPython --pgo training task "
             "(default: CPython compile jobs, one fewer than host CPUs)",
    )
    args = parser.parse_args(argv)
    work = REPO / "build" / "work"
    prefix = (REPO / "build" / "prefix").resolve()
    stage = REPO / "build" / "stage"
    logs = REPO / "build" / "logs"
    work.mkdir(parents=True, exist_ok=True)
    stage.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    cache = Cache(REPO / ".cache")
    version = next(
        entry.version for entry in load_lock(REPO / "sources.lock.json")
        if entry.name == "cpython"
    )
    print(f"BUILD cpython {version}", flush=True)
    try:
        target = target_for_host(args.target)
        staged = build(
            work, prefix, stage, logs, cache, target=target,
            pgo_jobs=args.pgo_jobs,
        )
    except (BuildError, InputError, PatchError, BootstrapError,
            UnsupportedTargetError, RelocationError, ScopeError) as error:
        print(f"FAIL cpython: {error}")
        return 1
    print(f"OK    cpython -> {staged}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
