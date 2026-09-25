"""Deterministic numeric-slash log ingestion through the public datetime API."""

import argparse
from datetime import datetime
import hashlib
import json


FORMAT = "%Y/%m/%d %H:%M:%S"


def run(count: int, rounds: int) -> dict[str, object]:
    rows = []
    for index in range(count):
        year = 2020 + index % 6
        month = 1 + (index * 7) % 12
        day = 1 + (index * 11) % 28
        hour = (index * 13) % 24
        minute = (index * 17) % 60
        second = (index * 19) % 60
        timestamp = f"{year:04d}/{month:02d}/{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
        rows.append((timestamp, index % 17 + 1))

    buckets: dict[str, list[int]] = {}
    for _ in range(rounds):
        for timestamp, size in rows:
            instant = datetime.strptime(timestamp, FORMAT)
            key = f"{instant.year:04d}-{instant.month:02d}-{instant.day:02d}"
            bucket = buckets.setdefault(key, [0, 0])
            bucket[0] += 1
            bucket[1] += size + instant.hour * 3600 + instant.minute * 60 + instant.second

    payload = json.dumps(sorted(buckets.items()), separators=(",", ":")).encode()
    return {"count": count, "rounds": rounds, "records": count * rounds,
            "buckets": len(buckets), "digest": hashlib.sha256(payload).hexdigest()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=30000)
    parser.add_argument("--rounds", type=int, default=2)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.count, arguments.rounds), sort_keys=True))
