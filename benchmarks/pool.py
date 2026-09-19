"""Concatenate pyperformance result files, grouping runs by benchmark (stdlib only).

Used to merge parallel per-shard files into one JSON per interpreter before
running benchmarks/compare.py. Values are pooled, not averaged: every
 recorded run value is preserved under its benchmark name, so downstream
means are value-weighted. Per-benchmark metadata is taken from its first
occurrence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def pool(paths: list[Path]) -> dict:
    """Merge result files into a pyperformance-shaped suite dict."""
    if not paths:
        raise ValueError("no input files")
    merged: dict[str, dict] = {}
    order: list[str] = []
    for path in paths:
        suite = json.loads(Path(path).read_text(encoding="utf-8"))
        # Single-benchmark files carry the name in top-level metadata;
        # multi-benchmark files carry it per benchmark. Accept both and
        # normalize, so the pooled file always has per-benchmark names.
        top_name = suite.get("metadata", {}).get("name")
        for benchmark in suite["benchmarks"]:
            meta = benchmark.get("metadata") or {}
            name = meta.get("name") or top_name
            if not name:
                raise ValueError(f"benchmark without a name in {path}")
            if name not in merged:
                merged[name] = {
                    "metadata": meta if meta.get("name") else {"name": name},
                    "runs": [],
                }
                order.append(name)
            merged[name]["runs"].extend(benchmark["runs"])
    if not order:
        raise ValueError("no benchmarks in input files")
    return {"benchmarks": [merged[name] for name in order]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("inputs", type=Path, nargs="+")
    args = parser.parse_args(argv)
    try:
        suite = pool(args.inputs)
    except (OSError, ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    args.output.write_text(json.dumps(suite, indent=2) + "\n")
    total_runs = sum(len(b["runs"]) for b in suite["benchmarks"])
    print(f"pooled {len(args.inputs)} files, "
          f"{len(suite['benchmarks'])} benchmarks, {total_runs} runs -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
