"""Compare the Rust-for-CPython Base64 proof with the public C-backed API."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import time
from typing import Any, Callable


class WorkloadError(RuntimeError):
    """The Base64 operation failed its correctness contract."""


def _payload(size: int) -> bytes:
    pattern = bytes(range(256))
    return pattern * (size // len(pattern)) + pattern[: size % len(pattern)]


def _result(name: str, iterations: int, size: int) -> dict[str, int | float | str]:
    data = _payload(size)
    expected = base64.b64encode(data)
    try:
        import _base64
    except ModuleNotFoundError as error:
        if error.name != "_base64":
            raise
        encode: Callable[[bytes], bytes] = base64.b64encode
        backend = "binascii through base64.b64encode"
    else:
        encode = _base64.standard_b64encode
        backend = "Rust _base64.standard_b64encode"

    if encode(data) != expected:
        raise WorkloadError(f"{name}: output differs from base64.b64encode")
    started = time.perf_counter()
    output = b""
    for _ in range(iterations):
        output = encode(data)
    elapsed = time.perf_counter() - started
    if output != expected:
        raise WorkloadError(f"{name}: repeated output differs from base64.b64encode")
    return {
        "operation_count": iterations,
        "digest": hashlib.sha256(output).hexdigest(),
        "elapsed_seconds": elapsed,
        "backend": backend,
        "input_bytes_per_operation": size,
    }


def rust_base64_small(iterations: int) -> dict[str, int | float | str]:
    """Encode 64-byte buffers repeatedly to expose call and setup costs."""
    return _result("rust_base64_small", iterations, 64)


def rust_base64_large(iterations: int) -> dict[str, int | float | str]:
    """Encode 1-MiB buffers repeatedly to expose bulk throughput."""
    return _result("rust_base64_large", iterations, 1_048_576)


_SCENARIOS: dict[str, Callable[[int], dict[str, int | float | str]]] = {
    "rust_base64_small": rust_base64_small,
    "rust_base64_large": rust_base64_large,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=sorted(_SCENARIOS))
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args(argv)
    if args.iterations < 1:
        parser.error("--iterations must be positive")
    try:
        result: dict[str, Any] = _SCENARIOS[args.scenario](args.iterations)
    except WorkloadError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
