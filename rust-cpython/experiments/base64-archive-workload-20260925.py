"""Hash deterministic JSON lines of Base64 encoded locked source chunks."""

import argparse
import base64
import hashlib
import json
import resource
import sys
import time


ARCHIVE_SHA256 = "965dbc9c847b0ed779a16134495b8690c9fc957996d8bcbb83c47089d4e81467"
ARCHIVE_BYTES = 44_210_863
CHUNK_BYTES = 65_536
OUTPUT_SHA256 = "108345723516149b47babd0be812f64ff40a0fea49cea23090b68828f9cde835"


def archive_identity(path):
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def encode_archive(path):
    digest = hashlib.sha256()
    chunks = input_bytes = encoded_bytes = jsonl_bytes = 0
    with open(path, "rb") as stream:
        while chunk := stream.read(CHUNK_BYTES):
            encoded = base64.b64encode(chunk)
            record = {
                "base64": encoded.decode("ascii"),
                "chunk": chunks,
                "offset": input_bytes,
                "raw_bytes": len(chunk),
            }
            line = (json.dumps(record, ensure_ascii=True, sort_keys=True,
                               separators=(",", ":")) + "\n").encode("ascii")
            digest.update(line)
            chunks += 1
            input_bytes += len(chunk)
            encoded_bytes += len(encoded)
            jsonl_bytes += len(line)
    return {
        "chunks": chunks,
        "input_bytes": input_bytes,
        "base64_bytes": encoded_bytes,
        "jsonl_bytes": jsonl_bytes,
        "jsonl_sha256": digest.hexdigest(),
    }


def peak_rss_bytes(usage):
    return usage.ru_maxrss if sys.platform == "darwin" else usage.ru_maxrss * 1024


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", help="byte-pinned CPython source tar.gz")
    args = parser.parse_args()

    start_wall = time.perf_counter_ns()
    start_usage = resource.getrusage(resource.RUSAGE_SELF)
    actual_sha256, actual_bytes = archive_identity(args.archive)
    if (actual_sha256, actual_bytes) != (ARCHIVE_SHA256, ARCHIVE_BYTES):
        raise ValueError("source archive differs from the locked CPython input")

    result = encode_archive(args.archive)
    if result["input_bytes"] != ARCHIVE_BYTES:
        raise ValueError("encoded input length differs from the locked archive")
    if result["jsonl_sha256"] != OUTPUT_SHA256:
        raise ValueError("JSON-line output differs from the fixed workload identity")

    end_usage = resource.getrusage(resource.RUSAGE_SELF)
    result.update({
        "archive_sha256": actual_sha256,
        "archive_bytes": actual_bytes,
        "chunk_bytes": CHUNK_BYTES,
        "python": sys.executable,
        "base64_module": base64.__file__,
        "wall_seconds": (time.perf_counter_ns() - start_wall) / 1e9,
        "user_cpu_seconds": end_usage.ru_utime - start_usage.ru_utime,
        "system_cpu_seconds": end_usage.ru_stime - start_usage.ru_stime,
        "peak_rss_bytes": peak_rss_bytes(end_usage),
    })
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
