#!/usr/bin/env python3
"""Measure the pinned Rust Base64 proof against CPython's C/public paths."""

from __future__ import annotations

import base64
import binascii
import json
import platform
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LANE = Path(__file__).resolve().parent
PYPERF_WHEEL = REPO / "benchmarks" / "vendor" / "pyperf-2.10.0-py3-none-any.whl"
sys.path.insert(0, str(PYPERF_WHEEL))

import pyperf  # noqa: E402
import _base64  # noqa: E402

SIZES = (64, 4_096, 1_048_576, 16_777_216)


def _binascii_encode(data: bytes) -> bytes:
    return binascii.b2a_base64(data, newline=False)


def _payload(size: int) -> bytes:
    pattern = bytes(range(256))
    return pattern * (size // len(pattern)) + pattern[: size % len(pattern)]


def main() -> None:
    if sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 16):
        raise SystemExit("run this benchmark with the staged CPython 3.16 interpreter")
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise SystemExit("this benchmark report is scoped to native Apple Silicon macOS")
    if not PYPERF_WHEEL.is_file():
        raise SystemExit(f"pinned pyperf wheel is missing: {PYPERF_WHEEL}")

    source = json.loads((LANE / "sources.lock.json").read_text())["source"]
    result = json.loads((LANE / "results" / "build.json").read_text())
    if result.get("status") != "complete" or result["source"]["commit"] != source["commit"]:
        raise SystemExit("the build report does not match a fully tested pinned build")

    rust = _base64.standard_b64encode
    functions = (
        ("rust", rust),
        ("binascii_c", _binascii_encode),
        ("stdlib_base64", base64.b64encode),
    )
    for size in SIZES:
        data = _payload(size)
        expected = binascii.b2a_base64(data, newline=False)
        for _name, function in functions:
            if function(data) != expected:
                raise SystemExit(f"Base64 output mismatch at {size} input bytes")

    runner = pyperf.Runner(metadata={
        "experiment": "Rust-for-CPython _base64 encoding proof",
        "source_commit": source["commit"],
        "target": "aarch64-apple-darwin",
        "rust_channel": result["rust"]["active_toolchain"],
        "c_toolchain": (
            f"LLVM {result['c_toolchain']['llvm_version']}; "
            f"Xcode {result['c_toolchain']['xcode_version']}"
        ),
        "scope": "single-process encoding microbenchmark; no whole-interpreter comparison",
    })
    for size in SIZES:
        data = _payload(size)
        for name, function in functions:
            runner.bench_func(f"base64_{size}_{name}", function, data)


if __name__ == "__main__":
    main()
