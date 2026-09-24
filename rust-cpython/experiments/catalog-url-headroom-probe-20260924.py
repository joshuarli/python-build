"""Diagnostic only: profile and count calls in complete catalog URL batches."""

from __future__ import annotations

import cProfile
import json
import pstats
import sys
from collections import Counter
from urllib import parse

from benchmarks.workloads.catalog_url import catalog_url_normalize


ITERATIONS = 100


def profile() -> None:
    profiler = cProfile.Profile()
    profiler.enable()
    result = catalog_url_normalize(ITERATIONS)
    profiler.disable()
    stats = pstats.Stats(profiler)
    rows = []
    for (filename, line, name), (primitive, calls, self_time, cumulative, _) in stats.stats.items():
        rows.append({"file": filename, "line": line, "name": name,
                     "primitive_calls": primitive, "calls": calls,
                     "self_seconds": self_time, "cumulative_seconds": cumulative})
    print(json.dumps({"mode": "profile", "result": result,
                      "total_calls": stats.total_calls, "total_seconds": stats.total_tt,
                      "by_self": sorted(rows, key=lambda row: row["self_seconds"], reverse=True)[:30],
                      "by_cumulative": sorted(rows, key=lambda row: row["cumulative_seconds"], reverse=True)[:30]},
                     indent=2, sort_keys=True))


def count() -> None:
    original = parse.quote_from_bytes
    counts: Counter[str] = Counter()
    lengths: Counter[int] = Counter()

    def observed(bs: bytes | bytearray, safe: str | bytes = "/") -> str:
        counts["calls"] += 1
        if type(bs) is bytes:
            counts["exact_bytes"] += 1
        if isinstance(safe, str):
            normalized_safe = safe.encode("ascii", "ignore")
        else:
            normalized_safe = bytes([c for c in safe if c < 128])
        if type(normalized_safe) is bytes:
            counts["exact_normalized_safe_bytes"] += 1
        if type(bs) is bytes and type(normalized_safe) is bytes:
            counts["guard_eligible"] += 1
            if not bs:
                counts["empty_fast_exit"] += 1
            elif not bs.rstrip(parse._ALWAYS_SAFE_BYTES + normalized_safe):
                counts["already_safe_fast_exit"] += 1
            else:
                counts["would_scan"] += 1
                lengths[len(bs)] += 1
        return original(bs, safe)

    parse.quote_from_bytes = observed
    try:
        result = catalog_url_normalize(ITERATIONS)
    finally:
        parse.quote_from_bytes = original
    print(json.dumps({"mode": "count", "result": result,
                      "counts": counts, "scan_input_lengths": sorted(lengths.items())},
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("profile", "count"):
        raise SystemExit("usage: catalog-url-headroom-probe-20260924.py profile|count")
    (profile if sys.argv[1] == "profile" else count)()
