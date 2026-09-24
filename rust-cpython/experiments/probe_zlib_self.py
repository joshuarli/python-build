#!/usr/bin/env python3
"""Calibrate zlib probe noise by pairing the same platform backend with itself."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import statistics

from probe_zlib import _check_inputs, _run, BY_NAME, WORKLOADS


def _paired(name: str, iterations: int, rounds: int, *, memory: bool) -> list[dict]:
    observations = []
    for index in range(rounds):
        order = ("A", "B") if index % 2 == 0 else ("B", "A")
        runs = {}
        for label in order:
            runs[label] = _run(name, "platform_zlib", iterations=iterations,
                               observe_memory=memory)
        common = ("digest", "input_digest", "operation_count")
        if any(runs["A"]["payload"][key] != runs["B"]["payload"][key]
               for key in common):
            raise RuntimeError(f"{name}: self-control workload identity differs")
        ratio = {
            "cpu": runs["B"]["cpu_total_seconds"] / runs["A"]["cpu_total_seconds"],
            "wall": runs["B"]["external_wall_seconds"] / runs["A"]["external_wall_seconds"],
        }
        if memory:
            a = runs["A"]["memory"]["root_kernel_peak_rss_bytes"]
            b = runs["B"]["memory"]["root_kernel_peak_rss_bytes"]
            ratio["root_kernel_peak_rss"] = b / a if a and b else None
        observations.append({"round": index, "order": order, "runs": runs,
                             "ratio_B_over_A": ratio})
    return observations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--memory-rounds", type=int, default=3)
    parser.add_argument("--scale", type=int, default=4)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.rounds < 1 or args.memory_rounds < 1 or args.scale < 1:
        parser.error("round counts and scale must be positive")
    identity = _check_inputs()
    report = {"kind": "platform-zlib self-control noise probe",
              "identity": identity, "host_load_average_at_start": os.getloadavg(),
              "workloads": {}}
    for name in WORKLOADS:
        iterations = BY_NAME[name].iterations * args.scale
        _run(name, "platform_zlib", iterations=iterations)
        timing = _paired(name, iterations, args.rounds, memory=False)
        memory = _paired(name, iterations, args.memory_rounds, memory=True)
        report["workloads"][name] = {
            "operation_count": timing[0]["runs"]["A"]["payload"]["operation_count"],
            "timing_pairs": timing,
            "memory_pairs": memory,
            "median_cpu_ratio_B_over_A": statistics.median(
                row["ratio_B_over_A"]["cpu"] for row in timing),
            "median_wall_ratio_B_over_A": statistics.median(
                row["ratio_B_over_A"]["wall"] for row in timing),
            "median_root_kernel_peak_rss_ratio_B_over_A": statistics.median(
                row["ratio_B_over_A"]["root_kernel_peak_rss"] for row in memory
                if row["ratio_B_over_A"]["root_kernel_peak_rss"] is not None),
        }
    report["host_load_average_at_end"] = os.getloadavg()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    for name, value in report["workloads"].items():
        print(name, "CPU", round(value["median_cpu_ratio_B_over_A"], 3),
              "wall", round(value["median_wall_ratio_B_over_A"], 3),
              "root RSS", round(value["median_root_kernel_peak_rss_ratio_B_over_A"], 3))
    print(f"raw report: {args.output}")


if __name__ == "__main__":
    main()
