"""Fetch locked source inputs and provision the official macOS toolchain."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from buildsys.bootstrap import load_macos_toolchain  # noqa: E402
from buildsys.inputs import Cache, InputError, load_lock  # noqa: E402
from buildsys.llvm import (  # noqa: E402
    extract_llvm_archive,
    verify_llvm_attestation_metadata,
)
from buildsys.targets import native_target, target_for_triple  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch verified build inputs")
    parser.add_argument("--target", default=native_target().triple)
    args = parser.parse_args(argv)
    target = target_for_triple(args.target)
    source_cache = Cache(REPO / ".cache")
    try:
        inputs = load_lock(REPO / "sources.lock.json")
        for entry in inputs:
            if entry.role == "reference":
                continue
            try:
                path = source_cache.require(entry)
                print(f"cached  {entry.name}")
            except InputError:
                print(f"fetch   {entry.name} ...", flush=True)
                path = source_cache.fetch(entry)
                print(f"ok      {entry.name} -> {path}")

        if target.is_macos:
            locked = load_macos_toolchain(REPO / "bootstrap.lock.json")
            llvm_cache = Cache(REPO / ".cache" / "llvm")
            try:
                archive = llvm_cache.require(locked.llvm_input())
                print("cached  llvm-macos-aarch64")
            except InputError:
                print("fetch   llvm-macos-aarch64 ...", flush=True)
                archive = llvm_cache.fetch(locked.llvm_input())
                print(f"ok      llvm-macos-aarch64 -> {archive}")
            try:
                provenance = llvm_cache.require(locked.llvm_attestation_input())
                print("cached  llvm-macos-aarch64-provenance")
            except InputError:
                print("fetch   llvm-macos-aarch64-provenance ...", flush=True)
                provenance = llvm_cache.fetch(locked.llvm_attestation_input())
                print(f"ok      llvm-macos-aarch64-provenance -> {provenance}")
            verify_llvm_attestation_metadata(
                provenance,
                archive_filename=Path(locked.llvm_archive_url).name,
                archive_sha256=locked.llvm_archive_sha256,
                release_tag=locked.llvm_release_tag,
                source_commit=locked.llvm_source_commit,
                workflow=locked.llvm_workflow,
            )
            prefix = extract_llvm_archive(
                archive,
                locked.llvm_prefix,
                archive_root=locked.llvm_archive_root,
                sha256=locked.llvm_archive_sha256,
                size=locked.llvm_archive_size,
                version=locked.llvm_version,
            )
            print(f"ready   llvm-macos-aarch64 -> {prefix}")
    except (InputError, OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
