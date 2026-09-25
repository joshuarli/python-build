"""Build and read a deterministic SQLite table of compressed small blobs."""

import argparse
import hashlib
import json
import sqlite3
import time
import zlib
from pathlib import Path


ROWS = 256


def payload(index: int) -> bytes:
    size = 1024 + (index * 1013) % 3073
    pattern = hashlib.sha256(f"small-blob:{index}".encode()).digest()
    varied = bytes((index * 17 + offset * 29) % 256 for offset in range(128))
    return (pattern + varied + pattern[:11]) * (size // 171) + (
        pattern + varied + pattern[:11]
    )[: size % 171]


def seed(path: Path) -> None:
    if path.exists():
        raise FileExistsError(path)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE blobs (id INTEGER PRIMARY KEY, body BLOB NOT NULL)")
        connection.executemany(
            "INSERT INTO blobs (id, body) VALUES (?, ?)",
            ((index, zlib.compress(payload(index), 6)) for index in range(ROWS)),
        )
    print(json.dumps({"fixture": str(path), "rows": ROWS, "bytes": path.stat().st_size}))


def read(path: Path, loops: int) -> None:
    digest = hashlib.sha256()
    logical_bytes = 0
    row_count = 0
    connection = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    started = time.perf_counter()
    for _ in range(loops):
        for index, compressed in connection.execute("SELECT id, body FROM blobs ORDER BY id"):
            decoded = zlib.decompress(compressed)
            digest.update(index.to_bytes(4, "little"))
            digest.update(decoded)
            logical_bytes += len(decoded)
            row_count += 1
    elapsed = time.perf_counter() - started
    connection.close()
    print(json.dumps({"digest": digest.hexdigest(), "logical_bytes": logical_bytes,
                      "row_count": row_count, "elapsed_seconds": elapsed, "loops": loops},
                     sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("seed", "read"))
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--loops", type=int, default=1)
    args = parser.parse_args()
    if args.mode == "seed":
        seed(args.fixture)
    else:
        if args.loops < 1:
            parser.error("--loops must be positive")
        read(args.fixture, args.loops)


if __name__ == "__main__":
    main()
