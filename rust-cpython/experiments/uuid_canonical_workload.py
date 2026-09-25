"""Deterministic UUID index construction through the public UUID API."""

import argparse
import hashlib
import json
import uuid


def run(count: int, rounds: int) -> dict[str, object]:
    rows = []
    for index in range(count):
        value = (index * 0x9e3779b97f4a7c15c2b2ae3d27d4eb4f +
                 0x123456789abcdef00123456789abcdef) & ((1 << 128) - 1)
        digits = f"{value:032x}"
        rows.append(f"{digits[:8]}-{digits[8:12]}-{digits[12:16]}-"
                    f"{digits[16:20]}-{digits[20:]}")

    buckets: dict[str, list[int]] = {}
    for _ in range(rounds):
        for row in rows:
            identifier = uuid.UUID(row)
            key = str(identifier)[:4]
            bucket = buckets.setdefault(key, [0, 0])
            bucket[0] += 1
            bucket[1] = (bucket[1] + identifier.int) & ((1 << 128) - 1)

    payload = json.dumps(sorted((key, count, f"{value:032x}")
                                for key, (count, value) in buckets.items()),
                         separators=(",", ":")).encode()
    return {"count": count, "rounds": rounds, "records": count * rounds,
            "buckets": len(buckets), "digest": hashlib.sha256(payload).hexdigest()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=30000)
    parser.add_argument("--rounds", type=int, default=2)
    args = parser.parse_args()
    print(json.dumps(run(args.count, args.rounds), sort_keys=True))
