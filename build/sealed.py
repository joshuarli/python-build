"""Sealed qualification build for macOS.

Qualification evidence has to come from a run whose inputs were declared and
whose network boundary was enforced. This driver does that: it verifies the
toolchain against the lock, proves the network denial is real *before*
trusting it, builds every bundled dependency and CPython inside the profile,
and records what the containment actually was.

The host development build remains available for iteration. This run records
the enforced network boundary and containment used for qualification.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from buildsys.bootstrap import (  # noqa: E402
    BootstrapError, load_macos_toolchain, problems,
)
from buildsys.inputs import Cache, InputError  # noqa: E402
from buildsys.llvm import (  # noqa: E402
    extract_llvm_archive,
    verify_llvm_attestation_metadata,
)
from buildsys.sandbox import SealedRun, available, describe, network_boundary_selftest  # noqa: E402
from buildsys.targets import UnsupportedTargetError, native_target  # noqa: E402


def _positive_int(value: str) -> int:
    try:
        result = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if result < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sealed offline macOS build")
    parser.add_argument(
        "--pgo-jobs", type=_positive_int,
        help="number of workers for CPython's --pgo training task "
             "(default: CPython compile jobs, one fewer than host CPUs)",
    )
    args = parser.parse_args(argv)

    try:
        target = native_target()
    except UnsupportedTargetError as error:
        print(f"FAIL sealed: {error}")
        return 1
    if not target.is_macos:
        print("FAIL sealed: the sealed runner is the macOS path; the Linux targets "
              "qualify through the Dockerfile's --network=none stage")
        return 1
    if not available():
        print("FAIL sealed: sandbox-exec is unavailable; refusing to fall back to an "
              "unsealed host build and call it qualification")
        return 1

    lock_path = REPO / "bootstrap.lock.json"
    try:
        locked = load_macos_toolchain(lock_path)
    except BootstrapError as error:
        print(f"FAIL sealed: {error}")
        return 1
    try:
        cache = Cache(REPO / ".cache" / "llvm")
        archive = cache.require(locked.llvm_input())
        provenance = cache.require(locked.llvm_attestation_input())
        verify_llvm_attestation_metadata(
            provenance,
            archive_filename=Path(locked.llvm_archive_url).name,
            archive_sha256=locked.llvm_archive_sha256,
            release_tag=locked.llvm_release_tag,
            source_commit=locked.llvm_source_commit,
            workflow=locked.llvm_workflow,
            workflow_path=locked.llvm_workflow_path,
        )
        extract_llvm_archive(
            archive,
            locked.llvm_prefix,
            archive_root=locked.llvm_archive_root,
            sha256=locked.llvm_archive_sha256,
            size=locked.llvm_archive_size,
            version=locked.llvm_version,
            force_recreate=True,
        )
    except (InputError, OSError, ValueError) as error:
        print(f"FAIL sealed: locked LLVM archive is not ready: {error}")
        return 1

    found = problems(locked, host_floor=locked.host_floor)
    if found:
        print("FAIL sealed: toolchain lock does not match this machine: " + "; ".join(found))
        return 1

    workdir = REPO / "build" / "sealed"
    workdir.mkdir(parents=True, exist_ok=True)
    started = time.time()

    # Prove the boundary before relying on it: a "sealed" build under a
    # profile that does not actually deny anything is worse than no claim.
    boundary = network_boundary_selftest(Path(sys.executable), workdir / "network")
    if not boundary["ok"]:
        print(f"FAIL sealed: network boundary self-test failed: {json.dumps(boundary)}")
        return 1
    print("SEAL  network denied (verified against a loopback listener)", flush=True)

    run = SealedRun(
        write_paths=[REPO / "build", REPO / "dist"],
        home=workdir / "home",
    )
    (workdir / "home").mkdir(parents=True, exist_ok=True)
    host_tool_directories = [
        str(tool.parent)
        for tool in (locked.make, locked.pkgconf)
        if tool is not None
    ]
    env = run.environment({
        "PATH": ":".join([
            str(locked.llvm_prefix / "bin"),
            *dict.fromkeys(host_tool_directories),
            "/usr/bin",
            "/bin",
            "/usr/sbin",
            "/sbin",
        ]),
        "PYTHON_BUILD_BUILD_MODE": "sealed",
        "PYTHON_BUILD_ISOLATION": "sandbox-exec-network-selftest",
    })

    commands = []
    for script in ("build/deps.py", "build/cpython.py"):
        log = REPO / "build" / "sealed" / f"{Path(script).stem}-sealed.log"
        print(f"SEAL  {script}", flush=True)
        command = [sys.executable, script]
        if script == "build/cpython.py" and args.pgo_jobs is not None:
            command.extend(["--pgo-jobs", str(args.pgo_jobs)])
        result = run.run(command, cwd=REPO, env=env, log=log)
        commands.append(" ".join(["python3", script, *command[2:]]))
        if result.returncode != 0:
            print(f"FAIL sealed: {script} exited {result.returncode}; log {log}")
            return 1

    # The boundary must still hold after the build, not merely before it: a
    # build that silently widened the profile would otherwise go unnoticed.
    after = network_boundary_selftest(Path(sys.executable), workdir / "network-after")
    if not after["ok"]:
        print("FAIL sealed: network boundary no longer holds after the build")
        return 1

    recipe_path = REPO / "build" / "logs" / "build-record.json"
    try:
        recipe = json.loads(recipe_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL sealed: CPython build recipe is missing or invalid: {error}")
        return 1
    recipe["isolation"] = {
        "mechanism": "sandbox-exec",
        "network": "disabled",
        "network_boundary_before": boundary,
        "network_boundary_after": after,
        "containment": describe(),
    }
    record_json = json.dumps(recipe, indent=2, sort_keys=True) + "\n"
    recipe_path.write_text(record_json)
    (REPO / "build" / "stage" / "cpython-staged" / "build-record.json").write_text(
        record_json
    )

    record = {
        "target": target.triple,
        "sealed": True,
        "network_boundary": boundary,
        "network_boundary_after_build": after,
        "containment": describe(),
        "toolchain": locked.identity(),
        "toolchain_observed": locked.observed_facts(),
        "commands": commands,
        "duration_seconds": round(time.time() - started, 1),
        "environment": {k: v for k, v in sorted(env.items())},
        "host": {"macos": os.uname().release, "machine": os.uname().machine},
    }
    (REPO / "build" / "sealed" / "sealed.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n"
    )
    print(f"OK    sealed build complete in {record['duration_seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
