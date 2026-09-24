"""Public decompression paths for the CPython zlib backend experiment.

Inputs are generated before timing. Each operation checks exact decoded bytes;
the reported digest describes that content and is stable across backends.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import random
import resource
import struct
import subprocess
import sys
import tempfile
import time
import zipfile
import zlib
from pathlib import Path
from typing import Any, Callable


class WorkloadError(RuntimeError):
    """A public decompression path produced unexpected content."""


_MIB = 1 << 20
# zlib level-6 stream for b"A" * 1 MiB, generated once with platform zlib.
# Its long run of zero bytes is written as a count so the fixture stays readable.
_COMPRESSIBLE_ZLIB_STREAM = (bytes.fromhex("789cedc13101000000c2a06ceb5fca10be4001")
                             + bytes(1015) + bytes.fromhex("7c06b18c3cf1"))


def _payload(size: int, *, compressible: bool) -> bytes:
    if compressible:
        return b"A" * size
    return random.Random(0x5A17).randbytes(size)


def _stored_zlib_stream(data: bytes) -> bytes:
    """Wrap fixed uncompressed DEFLATE blocks in a valid zlib stream."""
    blocks = bytearray(b"\x78\x01")
    for offset in (range(0, len(data), 65535) if data else (0,)):
        chunk = data[offset:offset + 65535]
        final = offset + len(chunk) == len(data)
        blocks.append(int(final))
        blocks.extend(struct.pack("<HH", len(chunk), len(chunk) ^ 0xFFFF))
        blocks.extend(chunk)
    blocks.extend(struct.pack(">I", zlib.adler32(data)))
    return bytes(blocks)


def _encoded_cases() -> list[tuple[str, bytes, bytes]]:
    compressible = _payload(_MIB, compressible=True)
    incompressible = _payload(_MIB, compressible=False)
    if zlib.decompress(_COMPRESSIBLE_ZLIB_STREAM) != compressible:
        raise WorkloadError("fixed compressible zlib fixture is invalid")
    return [("compressible", compressible, _COMPRESSIBLE_ZLIB_STREAM),
            ("incompressible", incompressible, _stored_zlib_stream(incompressible))]


def _digest(parts: list[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    for name, data in parts:
        digest.update(len(name).to_bytes(4, "big"))
        digest.update(name.encode("utf-8"))
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def _fixed_input_digest(data: bytes, expected: str) -> str:
    """Refuse to time a different compressed stream on another interpreter."""
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise WorkloadError(f"compressed fixture changed: {actual} != {expected}")
    return actual


def _fixed_zip(members: list[tuple[str, bytes]]) -> bytes:
    """Build a stable method-8 ZIP from fixed DEFLATE streams.

    ZIP metadata uses one DOS timestamp. The only checksum calculation is
    CRC-32, whose result is defined by the archive format.
    """
    local = bytearray()
    central = bytearray()
    dos_date = ((2024 - 1980) << 9) | (1 << 5) | 1
    for name, data in members:
        filename = name.encode("utf-8")
        compressed = (_COMPRESSIBLE_ZLIB_STREAM if len(data) == _MIB and data == b"A" * _MIB
                      else _stored_zlib_stream(data))[2:-4]
        checksum = zlib.crc32(data)
        offset = len(local)
        local.extend(struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, 0, 8, 0,
                                 dos_date, checksum, len(compressed), len(data),
                                 len(filename), 0))
        local.extend(filename)
        local.extend(compressed)
        central.extend(struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20,
                                   0, 8, 0, dos_date, checksum, len(compressed),
                                   len(data), len(filename), 0, 0, 0, 0, 0, offset))
        central.extend(filename)
    central_offset = len(local)
    local.extend(central)
    local.extend(struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, len(members),
                             len(members), len(central), central_offset, 0))
    return bytes(local)


def _result(iterations: int, units_per_iteration: int, digest: str, elapsed: float,
            input_digest: str) -> dict[str, int | float | str]:
    return {
        "operation_count": iterations * units_per_iteration,
        "digest": digest,
        "elapsed_seconds": elapsed,
        "input_digest": input_digest,
    }


def zlib_decode_1m(iterations: int) -> dict[str, int | float | str]:
    """Decode both compressible and incompressible 1 MiB buffers in one shot."""
    encoded = _encoded_cases()
    cases = [(name, data) for name, data, _ in encoded]
    expected = _digest(cases)
    input_digest = _digest([(name, stream) for name, _, stream in encoded])
    if input_digest != "d890765be28e2a1df58b1c67ddf0579416ebf4165e021fae6cffc13bfd68cba4":
        raise WorkloadError("fixed zlib fixture changed")
    started = time.perf_counter()
    for _ in range(iterations):
        decoded = [(name, zlib.decompress(stream)) for name, _, stream in encoded]
        if decoded != cases:
            raise WorkloadError("zlib.decompress changed decoded content")
    elapsed = time.perf_counter() - started
    return _result(iterations, 2 * _MIB, expected, elapsed, input_digest)


def zlib_stream_4k(iterations: int) -> dict[str, int | float | str]:
    """Decode 1 MiB through 4 KiB compressed-input streaming calls."""
    encoded = _encoded_cases()
    cases = [(name, data) for name, data, _ in encoded]
    expected = _digest(cases)
    input_digest = _digest([(name, stream) for name, _, stream in encoded])
    if input_digest != "d890765be28e2a1df58b1c67ddf0579416ebf4165e021fae6cffc13bfd68cba4":
        raise WorkloadError("fixed zlib fixture changed")
    started = time.perf_counter()
    for _ in range(iterations):
        for _, data, stream in encoded:
            decoder = zlib.decompressobj()
            chunks = [decoder.decompress(stream[offset:offset + 4096])
                      for offset in range(0, len(stream), 4096)]
            chunks.append(decoder.flush())
            if not decoder.eof or decoder.unused_data or b"".join(chunks) != data:
                raise WorkloadError("zlib streaming changed decoded content or stream boundary")
    elapsed = time.perf_counter() - started
    return _result(iterations, 2 * _MIB, expected, elapsed, input_digest)


def gzip_extract_1m(iterations: int) -> dict[str, int | float | str]:
    """Extract a 1 MiB gzip file through the public file API."""
    data = _payload(_MIB, compressible=True)
    # Fixed gzip header and trailer around the same fixed DEFLATE payload.
    stream = (bytes.fromhex("1f8b0800000000000003") + _COMPRESSIBLE_ZLIB_STREAM[2:-4]
              + struct.pack("<II", zlib.crc32(data), len(data)))
    input_digest = _fixed_input_digest(
        stream, "1de194e61a7ceece437084b2fae6152edf3c6258f9ff0854f05869524ba3d960")
    expected = _digest([("document", data)])
    started = time.perf_counter()
    for _ in range(iterations):
        with gzip.GzipFile(fileobj=io.BytesIO(stream), mode="rb") as source:
            decoded = source.read()
        if decoded != data:
            raise WorkloadError("gzip extraction changed decoded content")
    elapsed = time.perf_counter() - started
    return _result(iterations, len(data), expected, elapsed, input_digest)


def _wheel_archive() -> tuple[bytes, list[tuple[str, bytes]]]:
    """Build a wheel-shaped in-memory ZIP with small files and large resources."""
    def module_source(index: int) -> bytes:
        prefix = f"VALUE = {index}\n#".encode()
        return prefix + b"A" * (64 + index - len(prefix) - 1) + b"\n"

    members = [(f"sample_pkg/module_{index:03d}.py", module_source(index))
               for index in range(64)]
    members += [("sample_pkg/data/compressible.bin", _payload(_MIB, compressible=True)),
                ("sample_pkg/data/incompressible.bin", _payload(_MIB, compressible=False)),
                ("sample_pkg-1.0.dist-info/METADATA", b"Metadata-Version: 2.1\nName: sample-pkg\nVersion: 1.0\n")]
    return _fixed_zip(members), members


def zip_read_wheel(iterations: int) -> dict[str, int | float | str]:
    """Open and extract every member of a wheel-shaped in-memory ZIP."""
    stream, members = _wheel_archive()
    input_digest = _fixed_input_digest(
        stream, "216b735da6639be9f3f2b60e2973ca8f41539161648b74d5547d68877a713df7")
    expected = _digest(members)
    started = time.perf_counter()
    for _ in range(iterations):
        with zipfile.ZipFile(io.BytesIO(stream)) as archive:
            if archive.namelist() != [name for name, _ in members]:
                raise WorkloadError("ZIP member inventory changed")
            decoded = [(name, archive.read(name)) for name, _ in members]
        if decoded != members:
            raise WorkloadError("ZIP member content changed")
    elapsed = time.perf_counter() - started
    return _result(iterations, sum(len(data) for _, data in members), expected, elapsed,
                   input_digest)


_IMPORT_SCRIPT = """import importlib, json, sys
sys.path.insert(0, sys.argv[1])
module = importlib.import_module('zbench_pkg.payload')
print(json.dumps([module.VALUE, module.LABEL]))
"""


def zipimport_cold(iterations: int) -> dict[str, Any]:
    """Import a compressed package from ZIP in a new interpreter per operation.

    Report RUSAGE_CHILDREN deltas for the direct interpreters reaped here.
    Their CPU is absent from the harness's wait4 usage for this workload root.
    """
    expected_value = sum(range(1000))
    sources = {
        "zbench_pkg/__init__.py": b"",
        "zbench_pkg/payload.py": b"VALUE = sum(range(1000))\nLABEL = 'zipimport-deflate'\n",
    }
    expected = [expected_value, "zipimport-deflate"]
    with tempfile.TemporaryDirectory(prefix="zbench-zipimport-") as temporary:
        path = Path(temporary) / "package.zip"
        path.write_bytes(_fixed_zip(list(sources.items())))
        input_digest = _fixed_input_digest(
            path.read_bytes(), "8b14660fa9a0783095a7c28e4c0e05d24960d826de7516afab28e71597193a6a")
        elapsed = 0.0
        child_before = resource.getrusage(resource.RUSAGE_CHILDREN)
        for _ in range(iterations):
            started = time.perf_counter()
            completed = subprocess.run(
                [sys.executable, "-B", "-c", _IMPORT_SCRIPT, str(path)],
                capture_output=True, text=True, check=False,
            )
            elapsed += time.perf_counter() - started
            if completed.returncode or json.loads(completed.stdout) != expected:
                raise WorkloadError(f"cold ZIP import failed: {completed.stderr[-500:]}")
        child_after = resource.getrusage(resource.RUSAGE_CHILDREN)
    result: dict[str, Any] = _result(
        iterations, 1, _digest(sorted(sources.items())), elapsed, input_digest)
    result["reaped_child_cpu"] = {
        "user_seconds": child_after.ru_utime - child_before.ru_utime,
        "system_seconds": child_after.ru_stime - child_before.ru_stime,
        "process_count": iterations,
    }
    return result


_SCENARIOS: dict[str, Callable[[int], dict[str, Any]]] = {
    "zlib_decode_1m": zlib_decode_1m,
    "zlib_stream_4k": zlib_stream_4k,
    "gzip_extract_1m": gzip_extract_1m,
    "zip_read_wheel": zip_read_wheel,
    "zipimport_cold": zipimport_cold,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=sorted(_SCENARIOS))
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args(argv)
    if args.iterations < 1:
        parser.error("--iterations must be positive")
    try:
        result = _SCENARIOS[args.scenario](args.iterations)
    except WorkloadError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
