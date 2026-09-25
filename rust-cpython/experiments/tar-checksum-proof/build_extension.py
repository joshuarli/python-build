"""Build the checksum proof once and install identical bytes in two staged interpreters."""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
SOURCE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from buildsys.bootstrap import load_macos_toolchain


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("control_stage", type=Path)
    parser.add_argument("candidate_stage", type=Path)
    args = parser.parse_args()
    stages = (args.control_stage.resolve(), args.candidate_stage.resolve())
    for stage in stages:
        if not (stage / "include/python3.16/Python.h").is_file():
            parser.error(f"not a CPython 3.16 stage: {stage}")
    toolchain = load_macos_toolchain(ROOT / "bootstrap.lock.json")
    work = ROOT / "rust-cpython/work/tar-checksum-proof"
    work.mkdir(parents=True, exist_ok=True)
    rust_object = work / "checksum.o"
    extension = work / "_tar_checksum_proof.so"
    subprocess.run([
        "rustup", "run", "nightly-2026-09-15", "rustc", "--edition=2021",
        "--crate-type=lib", "--emit=obj", "--target=aarch64-apple-darwin",
        "-C", "opt-level=3", "-C", "panic=abort", "-o", str(rust_object),
        str(SOURCE / "checksum.rs"),
    ], check=True)
    subprocess.run([
        str(toolchain.llvm_prefix / "bin/clang"), "-bundle", "-undefined",
        "dynamic_lookup", "-arch", "arm64", "-mmacosx-version-min=26.0",
        "-O3", f"-I{stages[0] / 'include/python3.16'}",
        str(SOURCE / "checksum_module.c"), str(rust_object), "-o", str(extension),
    ], check=True)
    for stage in stages:
        destination = stage / "lib/python3.16/lib-dynload/_tar_checksum_proof.so"
        if destination.exists():
            parser.error(f"extension already exists: {destination}")
        shutil.copyfile(extension, destination)


if __name__ == "__main__":
    main()
