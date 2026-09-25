"""Measure quote_from_bytes across representative lengths and exact safe sets."""

from __future__ import annotations

import argparse
import hashlib
import json
from urllib.parse import quote_from_bytes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--length", type=int, required=True)
    parser.add_argument("--safe-hex", required=True)
    parser.add_argument("--iterations", type=int, default=30000)
    args = parser.parse_args()
    safe = bytes.fromhex(args.safe_hex)
    pattern = b"a/b+c ?%\xe9"
    payload = (pattern * ((args.length + len(pattern) - 1) // len(pattern)))[:args.length]
    expected = quote_from_bytes(payload, safe=safe)
    digest = hashlib.sha256()
    for _ in range(args.iterations):
        value = quote_from_bytes(payload, safe=safe)
        if value != expected:
            raise RuntimeError("quote result changed during calibration")
        digest.update(value.encode("ascii"))
    print(json.dumps({"digest": digest.hexdigest(), "value": expected,
                      "length": args.length, "safe_hex": args.safe_hex,
                      "iterations": args.iterations}))


if __name__ == "__main__":
    main()
