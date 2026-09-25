#!/usr/bin/env python3
"""Tabulate linux_paired.py reports as Markdown rows (one per comparison)."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _ratio(summary: dict | None) -> str:
    if summary is None:
        return "n/a"
    low, high = summary["bootstrap95_median"]
    return f"{summary['median']:.3f} [{low:.3f}, {high:.3f}]"


def _delta(summary: dict | None) -> str:
    if summary is None:
        return "n/a"
    low, high = summary["bootstrap95_median"]
    return f"{summary['median'] / 1e6:+.3f} [{low / 1e6:+.3f}, {high / 1e6:+.3f}]"


def main() -> None:
    print("| Comparison | Wall/op ratio [95%] | CPU/op ratio [95%] | Peak PSS Δ MB [95%] | Peak USS Δ MB [95%] | Pairs t/m |")
    print("| --- | ---: | ---: | ---: | ---: | ---: |")
    for path in sorted(Path(sys.argv[1]).glob("*.json")):
        report = json.loads(path.read_text())
        summary = report["summary"]
        pairs = f"{len(report['timing_pairs'])}/{len(report['memory_pairs'])}"
        print(f"| `{path.stem}` | {_ratio(summary['wall_per_op_ratio'])} | "
              f"{_ratio(summary['cpu_per_op_ratio'])} | {_delta(summary['peak_pss_delta_bytes'])} | "
              f"{_delta(summary['peak_private_delta_bytes'])} | {pairs} |")


if __name__ == "__main__":
    main()
