"""Build CPython 3.14.6 from verified sources against the private prefix (plan 5.3).

The staged installation lands in build/stage; the relocation decision
(destining a neutral prefix rather than the checkout) belongs to packaging.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from buildsys.cpython import configuration  # noqa: E402
from buildsys.inputs import Cache, InputError, load_lock, safe_extract  # noqa: E402
from buildsys.recipes import BuildError, Toolchain, run  # noqa: E402

JOBS = str(max(1, (os.cpu_count() or 4) - 1))


def build(work: Path, prefix: Path, stage: Path, logs: Path, cache: Cache) -> Path:
    pin = next(
        entry for entry in load_lock(REPO / "sources.lock.json") if entry.name == "cpython"
    )
    blob = cache.require(pin)
    source = safe_extract(blob, work / "cpython") / "Python-3.14.6"
    build_directory = work / "cpython-build"
    if build_directory.exists():
        shutil.rmtree(build_directory)
    build_directory.mkdir(parents=True)
    args, env_overrides = configuration(prefix)
    toolchain = Toolchain(pkg_config_path=f"{prefix}/lib/pkgconfig:{prefix}/share/pkgconfig")
    env = toolchain.env(
        {
            **env_overrides,
            "SOURCE_DATE_EPOCH": "1704067200",
            "PKG_CONFIG": "pkg-config",
        }
    )
    configure = source / "configure"
    run(
        [str(configure), f"--prefix=/install", *args],
        cwd=build_directory,
        env=env,
        log=logs / "cpython-configure.log",
    )
    run(
        ["make", "-j", JOBS],
        cwd=build_directory,
        env=env,
        log=logs / "cpython-make.log",
    )
    staged = stage / "cpython-staged"
    if staged.exists():
        shutil.rmtree(staged)
    staged.parent.mkdir(parents=True, exist_ok=True)
    run(
        ["make", "install", f"DESTDIR={staged}"],
        cwd=build_directory,
        env=env,
        log=logs / "cpython-install.log",
    )
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
    except (BuildError, InputError) as error:
        print(f"FAIL cpython: {error}")
        return 1
    print(f"OK    cpython -> {staged}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
