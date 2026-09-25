"""Build and read deterministic SQLite BLOBs with varied compressibility."""

import argparse
import hashlib
import json
import sqlite3
import time
import zlib
from pathlib import Path


ROWS = 256
CATEGORIES = ("repetitive", "modest", "mostly_random", "random")


def random_bytes(index: int, size: int) -> bytes:
    return b"".join(
        hashlib.sha256(f"mixed-blob:{index}:{block}".encode()).digest()
        for block in range((size + 31) // 32)
    )[:size]


def payload(index: int) -> bytes:
    size = 1024 + (index * 1013) % 3073
    category = index % len(CATEGORIES)
    noise = random_bytes(index, size)
    if category == 0:
        pattern = hashlib.sha256(f"pattern:{index}".encode()).digest()
        return (pattern * ((size + 31) // 32))[:size]
    if category == 1:
        # Alternating fixed and random chunks produce moderate compression.
        return b"".join(
            noise[offset : offset + 128] if (offset // 128) % 2 else b"A" * min(128, size - offset)
            for offset in range(0, size, 128)
        )
    if category == 2:
        return b"A" * (size // 8) + noise[size // 8 :]
    return noise


def seed(path: Path) -> None:
    if path.exists():
        raise FileExistsError(path)
    sizes = {name: [] for name in CATEGORIES}
    records = []
    for index in range(ROWS):
        decoded = payload(index)
        compressed = zlib.compress(decoded, 6)
        sizes[CATEGORIES[index % len(CATEGORIES)]].append(len(compressed))
        records.append((index, compressed))
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE blobs (id INTEGER PRIMARY KEY, body BLOB NOT NULL)")
        connection.executemany("INSERT INTO blobs (id, body) VALUES (?, ?)", records)
    summary = {name: {"count": len(values), "min": min(values), "median": sorted(values)[len(values) // 2],
                      "max": max(values)} for name, values in sizes.items()}
    print(json.dumps({"fixture": str(path), "rows": ROWS, "bytes": path.stat().st_size,
                      "compressed_sizes": summary}, sort_keys=True))


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
