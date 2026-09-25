#!/usr/bin/env python3
"""Compare public zlib encoder bytes from platform zlib and a zlib-rs overlay.

The parent writes full encoded streams only under its ignored result directory.
The child modes run with the same CPython executable and distinct PYTHONPATHs.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys

from evidence_checkpoint import checkpoint_evidence, reserve_evidence


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def corpus() -> dict[str, bytes]:
    return {
        "empty": b"",
        "repeated": (b"abcabcabc -- predictable text\n" * 1024),
        "binary": bytes(range(256)) * 48,
        "mixed": (bytes(range(256)) * 16) + (b"abcdefgh" * 2048),
    }


def encodings() -> dict[str, tuple[bytes, int, str]]:
    import gzip
    import zipfile
    import zlib

    results: dict[str, tuple[bytes, int, str]] = {}
    for name, plain in corpus().items():
        for level in (0, 1, 6, 9):
            key = f"zlib.compress/{name}/level={level}"
            results[key] = (zlib.compress(plain, level), 15, name)
            for wbits in (-15, -9, 9, 15, 31):
                for strategy, label in (
                    (zlib.Z_DEFAULT_STRATEGY, "default"),
                    (zlib.Z_FILTERED, "filtered"),
                    (zlib.Z_HUFFMAN_ONLY, "huffman"),
                    (zlib.Z_RLE, "rle"),
                    (zlib.Z_FIXED, "fixed"),
                ):
                    for chunks, boundary in ((None, "one"), (7, "chunks7")):
                        compressor = zlib.compressobj(level, zlib.DEFLATED, wbits,
                                                      zlib.DEF_MEM_LEVEL, strategy)
                        if chunks is None:
                            encoded = compressor.compress(plain)
                        else:
                            encoded = b"".join(compressor.compress(plain[i:i + chunks])
                                               for i in range(0, len(plain), chunks))
                        encoded += compressor.flush()
                        key = (f"zlib.compressobj/{name}/level={level}/wbits={wbits}"
                               f"/strategy={label}/boundary={boundary}")
                        results[key] = (encoded, wbits, name)
                if level == 6 and wbits in (-15, 15, 31):
                    for flush_mode, flush_label in (
                        (zlib.Z_SYNC_FLUSH, "sync"),
                        (zlib.Z_FULL_FLUSH, "full"),
                    ):
                        compressor = zlib.compressobj(level, zlib.DEFLATED, wbits)
                        split = len(plain) // 2
                        encoded = (compressor.compress(plain[:split])
                                   + compressor.flush(flush_mode)
                                   + compressor.compress(plain[split:])
                                   + compressor.flush())
                        key = (f"zlib.compressobj/{name}/level={level}/wbits={wbits}"
                               f"/strategy=default/boundary={flush_label}")
                        results[key] = (encoded, wbits, name)
        for level in (1, 6, 9):
            # Fixed gzip metadata permits byte comparison of the full container.
            buffer = io.BytesIO()
            with gzip.GzipFile(filename="", mode="wb", fileobj=buffer,
                               compresslevel=level, mtime=0) as writer:
                writer.write(plain)
            results[f"gzip.GzipFile/{name}/level={level}"] = (buffer.getvalue(), 31, name)
            results[f"gzip.compress/{name}/level={level}"] = (
                gzip.compress(plain, compresslevel=level, mtime=0), 31, name)
            buffer = io.BytesIO()
            info = zipfile.ZipInfo(f"{name}.bin", (2024, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=level) as archive:
                archive.writestr(info, plain, compress_type=zipfile.ZIP_DEFLATED,
                                 compresslevel=level)
            results[f"zipfile.ZipFile/{name}/level={level}"] = (
                buffer.getvalue(), 0, name)
    return results


def decode(encoded: bytes, wbits: int, name: str, *, streamed: bool) -> bytes:
    import gzip
    import zipfile
    import zlib

    if wbits == 0:
        with zipfile.ZipFile(io.BytesIO(encoded)) as archive:
            with archive.open(f"{name}.bin") as member:
                if streamed:
                    return b"".join(iter(lambda: member.read(7), b""))
                return member.read()
    if wbits == 31 and streamed:
        with gzip.GzipFile(fileobj=io.BytesIO(encoded)) as member:
            return b"".join(iter(lambda: member.read(7), b""))
    if streamed:
        obj = zlib.decompressobj(wbits)
        plain = b"".join(obj.decompress(encoded[i:i + 7])
                         for i in range(0, len(encoded), 7)) + obj.flush()
        if not obj.eof:
            raise AssertionError("stream ended before final block")
        return plain
    return zlib.decompress(encoded, wbits)


def child_encode() -> None:
    import zlib

    items = {}
    for key, (encoded, wbits, name) in encodings().items():
        plain = corpus()[name]
        if decode(encoded, wbits, name, streamed=False) != plain:
            raise AssertionError(key)
        if decode(encoded, wbits, name, streamed=True) != plain:
            raise AssertionError(key)
        items[key] = {
            "base64": base64.b64encode(encoded).decode("ascii"),
            "sha256": digest(encoded),
            "bytes": len(encoded),
            "plain_sha256": digest(plain),
            "adler32": zlib.adler32(plain),
            "crc32": zlib.crc32(plain),
            "wbits": wbits,
            "name": name,
        }
    print(json.dumps({"runtime": zlib.ZLIB_RUNTIME_VERSION,
                      "module": zlib.__file__, "items": items}, sort_keys=True))


def child_decode(path: Path) -> None:
    import zlib

    payload = json.loads(path.read_text())
    for key, item in payload["items"].items():
        encoded = base64.b64decode(item["base64"])
        if digest(encoded) != item["sha256"]:
            raise AssertionError(f"damaged stream: {key}")
        for streamed in (False, True):
            decoded = decode(encoded, item["wbits"], item["name"], streamed=streamed)
            if digest(decoded) != item["plain_sha256"]:
                raise AssertionError(f"cross-backend decode mismatch: {key}")
            if (zlib.adler32(decoded) != item["adler32"]
                    or zlib.crc32(decoded) != item["crc32"]):
                raise AssertionError(f"cross-backend checksum mismatch: {key}")
    print(json.dumps({"decoded": len(payload["items"])}))


def run_child(python: Path, script: Path, overlay: Path | None,
              *args: str) -> dict:
    env = dict(os.environ)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTHONPATH", None)
    if overlay is not None:
        env["PYTHONPATH"] = str(overlay)
    completed = subprocess.run([str(python), "-B", str(script), *args],
                               env=env, check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def parent(python: Path, overlay: Path | None, output: Path,
           candidate_python: Path | None = None) -> None:
    """Compare platform zlib with an overlay, or with a second installed interpreter."""
    script = Path(__file__).resolve()
    output.mkdir(parents=True, exist_ok=False)
    sides = {"platform": (python, None),
             "zlib_rs": (candidate_python or python, None if candidate_python else overlay)}
    raw = {}
    for side, (side_python, path) in sides.items():
        payload = run_child(side_python, script, path, "--encode")
        raw_path = output / f"zlib-byte-{side}.json"
        reserve_evidence(raw_path)
        checkpoint_evidence(raw_path, payload, sort_keys=True)
        repeat = run_child(side_python, script, path, "--encode")
        if payload != repeat:
            raise AssertionError(f"{side} compressed output changed on repeat")
        raw[side] = payload
    if raw["platform"]["items"].keys() != raw["zlib_rs"]["items"].keys():
        raise AssertionError("case inventory differs")
    cross = {}
    for decoder, (side_python, path) in sides.items():
        producer = "zlib_rs" if decoder == "platform" else "platform"
        cross[decoder] = run_child(side_python, script, path, "--decode",
                                   str(output / f"zlib-byte-{producer}.json"))
    cases = {}
    for key, control in raw["platform"]["items"].items():
        candidate = raw["zlib_rs"]["items"][key]
        if (control["plain_sha256"], control["adler32"], control["crc32"]) != (
                candidate["plain_sha256"], candidate["adler32"], candidate["crc32"]):
            raise AssertionError(f"checksum or plain data mismatch: {key}")
        cases[key] = {
            "byte_equal": control["sha256"] == candidate["sha256"],
            "platform_sha256": control["sha256"],
            "zlib_rs_sha256": candidate["sha256"],
            "platform_bytes": control["bytes"],
            "zlib_rs_bytes": candidate["bytes"],
        }
    report = {
        "python": str(python), "overlay": str(overlay),
        "candidate_python": str(candidate_python) if candidate_python else None,
        "module_sha256": {side: digest(Path(payload["module"]).read_bytes())
                          for side, payload in raw.items()},
        "repeat_identical": True,
        "runtimes": {side: payload["runtime"] for side, payload in raw.items()},
        "modules": {side: payload["module"] for side, payload in raw.items()},
        "cross_decoded": cross,
        "case_count": len(cases),
        "byte_equal_count": sum(case["byte_equal"] for case in cases.values()),
        "cases": cases,
    }
    report_path = output / "zlib-byte-comparison.json"
    reserve_evidence(report_path)
    checkpoint_evidence(report_path, report, sort_keys=True)
    print(json.dumps({key: value for key, value in report.items() if key != "cases"},
                     sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--encode", action="store_true")
    action.add_argument("--decode", type=Path)
    action.add_argument("--compare", action="store_true")
    parser.add_argument("--python", type=Path)
    parser.add_argument("--overlay", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--candidate-python", type=Path,
                        help="installed zlib-rs or hybrid interpreter in place of --overlay")
    args = parser.parse_args()
    if args.encode:
        child_encode()
    elif args.decode:
        child_decode(args.decode)
    else:
        if not (args.python and args.output and (args.overlay or args.candidate_python)):
            parser.error("--compare requires --python, --output, and --overlay or --candidate-python")
        parent(args.python, args.overlay, args.output, args.candidate_python)


if __name__ == "__main__":
    main()
