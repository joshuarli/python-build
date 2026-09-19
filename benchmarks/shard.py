"""Split pyperformance benchmark names into balanced shards (stdlib only).

Reads benchmark names (one per line, as parsed from `pyperformance list`
output), sorts them for determinism, and deals them round-robin into K
shards so slow benchmarks spread evenly. Prints one comma-separated shard
per line; shard i of K is line i.
"""

from __future__ import annotations

import argparse
import sys


def shard(names: list[str], count: int) -> list[list[str]]:
    """Deal sorted unique names round-robin into `count` shards."""
    if count < 1:
        raise ValueError("--shards must be positive")
    unique = sorted(set(names))
    if not unique:
        raise ValueError("no benchmark names")
    if count > len(unique):
        raise ValueError(f"{count} shards for {len(unique)} benchmarks")
    shards: list[list[str]] = [[] for _ in range(count)]
    for index, name in enumerate(unique):
        shards[index % count].append(name)
    return shards


def main(argv: list[str] | None = None) -> list[str]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names_file", help="file with one benchmark name per line")
    parser.add_argument("--shards", type=int, required=True)
    parser.add_argument("--exclude", default="",
                        help="comma-separated benchmark names to leave out")
    args = parser.parse_args(argv)
    excluded = {n.strip() for n in args.exclude.split(",") if n.strip()}
    names = [
        line.strip()
        for line in open(args.names_file, encoding="utf-8")
        if line.strip() and line.strip() not in excluded
    ]
    lines = [",".join(part) for part in shard(names, args.shards)]
    sys.stdout.write("\n".join(lines) + "\n")
    return lines


if __name__ == "__main__":
    main()
