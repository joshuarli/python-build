"""Build CPython 3.14.6 from verified sources against the private prefix (plan 5.3).

The staged installation lands in build/stage; the relocation decision
(destining a neutral prefix rather than the checkout) belongs to packaging.

The relocation step is per-format: the frozen Linux targets rewrite ELF
rpaths with patchelf, macOS rewrites Mach-O install names and adds
`@loader_path` search paths. Both run immediately after `make install`, so
the tree that later phases see is already relocatable.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from buildsys import macho  # noqa: E402
from buildsys.bootstrap import BootstrapError, toolchain_for  # noqa: E402
from buildsys.cpython import configuration  # noqa: E402
from buildsys.inputs import Cache, InputError, load_lock, safe_extract  # noqa: E402
from buildsys.patches import PatchError, apply_patch_set  # noqa: E402
from buildsys.recipes import BuildError, run  # noqa: E402
from buildsys.relocate import RelocationError, macho_relocate, relocate  # noqa: E402
from buildsys.scope import (
    ScopeError, enforce_exclusions, probe_in_process, verify_exclusions,
)  # noqa: E402
from buildsys.targets import Target, UnsupportedTargetError, native_target  # noqa: E402

CONFIGURE_PREFIX = "/install"
JOBS = str(max(1, (os.cpu_count() or 4) - 1))


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


def build(work: Path, prefix: Path, stage: Path, logs: Path, cache: Cache) -> Path:
    target = native_target()
    pin = next(
        entry for entry in load_lock(REPO / "sources.lock.json") if entry.name == "cpython"
    )
    blob = cache.require(pin)
    # safe_extract refuses an existing destination, so clear our own scratch
    # rather than making the caller do it before every rebuild.
    if (work / "cpython").exists():
        shutil.rmtree(work / "cpython")
    source = safe_extract(blob, work / "cpython") / "Python-3.14.6"
    apply_patch_set(source, REPO / "patches" / "cpython")
    build_directory = work / "cpython-build"
    if build_directory.exists():
        shutil.rmtree(build_directory)
    build_directory.mkdir(parents=True)
    args, env_overrides = configuration(prefix, target)
    toolchain = toolchain_for(target, REPO / "bootstrap.lock.json")
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
        [toolchain.make, "-j", JOBS],
        cwd=build_directory,
        env=env,
        log=logs / "cpython-make.log",
    )
    staged = stage / "cpython-staged"
    if staged.exists():
        shutil.rmtree(staged)
    staged.parent.mkdir(parents=True, exist_ok=True)
    run(
        [toolchain.make, "install", f"DESTDIR={staged}"],
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
    print(f"      removed {len(report['removed'])} excluded path(s)", flush=True)
    return staged


def main() -> int:
    work = REPO / "build" / "work"
    prefix = (REPO / "build" / "prefix").resolve()
    stage = REPO / "build" / "stage"
    logs = REPO / "build" / "logs"
    work.mkdir(parents=True, exist_ok=True)
    stage.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    cache = Cache(REPO / ".cache")
    print("BUILD cpython 3.14.6", flush=True)
    try:
        staged = build(work, prefix, stage, logs, cache)
    except (BuildError, InputError, PatchError, BootstrapError,
            UnsupportedTargetError, RelocationError, ScopeError) as error:
        print(f"FAIL cpython: {error}")
        return 1
    print(f"OK    cpython -> {staged}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
