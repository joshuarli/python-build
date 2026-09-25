#!/usr/bin/env python3
"""Compare pinned zlib backends on one CPython build without changing its tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
from typing import Any

from evidence_checkpoint import checkpoint_evidence, reserve_evidence

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from benchmarks.harness.process import run_command  # noqa: E402
from benchmarks.workloads.registry import BY_NAME  # noqa: E402

LANE = REPO / "rust-cpython"
PYTHON = LANE / "stage-no-rust" / "bin" / "python3.16"
OVERLAY = LANE / "work" / "zlib-proof" / "overlay"
PROOF_REPORT = LANE / "results" / "zlib-proof.json"
WORKLOADS = (
    "zlib_decode_1m",
    "zlib_stream_4k",
    "gzip_extract_1m",
    "zip_read_wheel",
    "zipimport_cold",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_inputs() -> dict[str, Any]:
    proof = json.loads(PROOF_REPORT.read_text())
    if proof.get("status") != "complete":
        raise RuntimeError("zlib proof is not complete")
    module = proof["module"]
    extension = Path(module["path"])
    if extension != OVERLAY / extension.name or _sha256(extension) != module["sha256"]:
        raise RuntimeError("zlib-rs overlay disagrees with its completed proof")
    if not PYTHON.is_file():
        raise RuntimeError("same-source no-Rust interpreter is missing")
    return {
        "python": str(PYTHON),
        "python_sha256": _sha256(PYTHON),
        "overlay": str(extension),
        "overlay_sha256": module["sha256"],
        "proof_source_commit": proof["source_cpython"]["commit"],
        "backend_version": proof["backend"]["version"],
    }


def _run(name: str, side: str, *, iterations: int,
         observe_memory: bool = False) -> dict[str, Any]:
    environment = dict(os.environ)
    environment.update({
        "PYTHONPATH": os.pathsep.join((
            *((str(OVERLAY),) if side == "zlib_rs" else ()), str(REPO),
        )),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "1",
    })
    command = [str(PYTHON), "-m", "benchmarks.workloads.zlib", name,
               "--iterations", str(iterations)]
    measured = run_command(command, env=environment, cwd=REPO, timeout=120,
                           sample_interval_seconds=0.02 if observe_memory else None)
    if measured.timed_out or measured.returncode or not measured.cleanup_complete:
        raise RuntimeError(f"{name} {side} failed: {measured.stderr.decode(errors='replace')[-1000:]}")
    if measured.cpu_user_seconds is None or measured.cpu_system_seconds is None:
        raise RuntimeError(f"{name} {side} has no kernel CPU accounting")
    if not measured.cpu_coverage.startswith("wait4 root"):
        raise RuntimeError(f"{name} {side} has incomplete CPU coverage: {measured.cpu_coverage}")
    payload = json.loads(measured.stdout.decode().splitlines()[-1])
    if payload["operation_count"] < iterations or not payload.get("input_digest"):
        raise RuntimeError(f"{name} {side} has an invalid workload result")
    result = {
        "side": side,
        "payload": payload,
        "cpu_user_seconds": measured.cpu_user_seconds,
        "cpu_system_seconds": measured.cpu_system_seconds,
        "cpu_total_seconds": measured.cpu_user_seconds + measured.cpu_system_seconds,
        "cpu_coverage": measured.cpu_coverage,
        "external_wall_seconds": measured.duration_seconds,
    }
    if observe_memory:
        memory = None if measured.memory is None else measured.memory.as_dict()
        result["memory"] = memory
        result["memory_status"] = (
            "sampled" if memory and memory["samples"] and not memory["sampling_errors"]
            else "incomplete"
        )
    return result


def probe(*, rounds: int, scale: int, memory_rounds: int,
          evidence: Path | None = None) -> dict[str, Any]:
    if rounds < 1 or scale < 1 or memory_rounds < 0:
        raise ValueError("rounds and scale must be positive; memory rounds must be nonnegative")
    identity = _check_inputs()
    load_at_start = os.getloadavg()
    workloads: dict[str, Any] = {}
    progress: dict[str, Any] = {}
    for name in WORKLOADS:
        spec = BY_NAME[name]
        iterations = spec.iterations * scale
        for side in ("platform_zlib", "zlib_rs"):
            _run(name, side, iterations=iterations)
        observations = []
        memory_observations = []
        progress[name] = {"rounds": observations, "memory_rounds": memory_observations}
        for round_index in range(rounds):
            order = (("platform_zlib", "zlib_rs") if round_index % 2 == 0
                     else ("zlib_rs", "platform_zlib"))
            pair = []
            for side in order:
                pair.append(_run(name, side, iterations=iterations))
                if evidence is not None:
                    checkpoint_evidence(evidence, {"workloads": progress,
                                        "current_round": {"workload": name,
                                                          "kind": "timing", "round": round_index,
                                                          "runs": pair}}, sort_keys=True)
            by_side = {row["side"]: row for row in pair}
            common = ("digest", "input_digest", "operation_count")
            if any(by_side["platform_zlib"]["payload"][key] !=
                   by_side["zlib_rs"]["payload"][key] for key in common):
                raise RuntimeError(f"{name}: control/candidate workload identity differs")
            observations.append({"round": round_index, "order": list(order),
                                 "runs": pair,
                                 "cpu_ratio_zlib_rs_over_platform": (
                                     by_side["zlib_rs"]["cpu_total_seconds"] /
                                     by_side["platform_zlib"]["cpu_total_seconds"]
                                 )})
            if evidence is not None:
                checkpoint_evidence(evidence, {"workloads": progress}, sort_keys=True)
        for round_index in range(memory_rounds):
            order = (("platform_zlib", "zlib_rs") if round_index % 2 == 0
                     else ("zlib_rs", "platform_zlib"))
            pair = []
            for side in order:
                pair.append(_run(name, side, iterations=iterations, observe_memory=True))
                if evidence is not None:
                    checkpoint_evidence(evidence, {"workloads": progress,
                                        "current_round": {"workload": name,
                                                          "kind": "memory", "round": round_index,
                                                          "runs": pair}}, sort_keys=True)
            by_side = {row["side"]: row for row in pair}
            common = ("digest", "input_digest", "operation_count")
            if any(by_side["platform_zlib"]["payload"][key] !=
                   by_side["zlib_rs"]["payload"][key] for key in common):
                raise RuntimeError(f"{name}: memory-pass workload identity differs")
            memory_observations.append({"round": round_index, "order": list(order),
                                        "runs": pair})
            if evidence is not None:
                checkpoint_evidence(evidence, {"workloads": progress}, sort_keys=True)
        valid_rss_ratios = []
        root_kernel_rss_ratios = []
        for observation in memory_observations:
            by_side = {row["side"]: row for row in observation["runs"]}
            if all(row["memory"] and row["memory"]["root_kernel_peak_rss_bytes"]
                   for row in by_side.values()):
                root_kernel_rss_ratios.append(
                    by_side["zlib_rs"]["memory"]["root_kernel_peak_rss_bytes"] /
                    by_side["platform_zlib"]["memory"]["root_kernel_peak_rss_bytes"]
                )
            if all(row["memory_status"] == "sampled" and
                   len(row["memory"]["samples"]) >= 10
                   for row in by_side.values()):
                baseline_rss = by_side["platform_zlib"]["memory"]["peak_rss_bytes"]
                candidate_rss = by_side["zlib_rs"]["memory"]["peak_rss_bytes"]
                if baseline_rss and candidate_rss is not None:
                    valid_rss_ratios.append(candidate_rss / baseline_rss)
        complete_rss_sampling = (
            bool(memory_observations)
            and len(valid_rss_ratios) == len(memory_observations)
        )
        complete_root_peak = (
            bool(memory_observations)
            and len(root_kernel_rss_ratios) == len(memory_observations)
        )
        workloads[name] = {
            "operation": spec.operation,
            "operation_count": observations[0]["runs"][0]["payload"]["operation_count"],
            "paired_cpu_ratio_median": statistics.median(
                pair["cpu_ratio_zlib_rs_over_platform"] for pair in observations
            ),
            "rounds": observations,
            "memory_rounds": memory_observations,
            "paired_peak_rss_ratio_median": (
                statistics.median(valid_rss_ratios) if complete_rss_sampling else None
            ),
            "paired_root_kernel_peak_rss_ratio_median": (
                statistics.median(root_kernel_rss_ratios) if complete_root_peak else None
            ),
            "rss_status": (
                "sampled peak diagnostic only" if complete_rss_sampling
                else "inconclusive: sparse or missing process samples"
            ),
        }
    return {
        "kind": "exploratory CPU and sampled RSS probe under current host load; no unique-memory or allocation verdict",
        "identity": identity,
        "host_load_average_at_start": load_at_start,
        "host_load_average_at_end": os.getloadavg(),
        "workloads": workloads,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--scale", type=int, default=4,
                        help="multiply each registered workload repetition count")
    parser.add_argument("--memory-rounds", type=int, default=3,
                        help="separate paired external RSS passes; zero disables")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reserve_evidence(args.output)
    report = probe(rounds=args.rounds, scale=args.scale,
                   memory_rounds=args.memory_rounds, evidence=args.output)
    checkpoint_evidence(args.output, report, sort_keys=True)
    for name, value in report["workloads"].items():
        rss = value["paired_peak_rss_ratio_median"]
        rss_label = "unavailable" if rss is None else f"{rss:.3f}"
        root_rss = value["paired_root_kernel_peak_rss_ratio_median"]
        root_label = "unavailable" if root_rss is None else f"{root_rss:.3f}"
        print(f"{name}: paired CPU ratio {value['paired_cpu_ratio_median']:.3f}, "
              f"sampled peak RSS ratio {rss_label}, "
              f"root kernel peak RSS ratio {root_label} (zlib-rs / platform)")
    print(f"raw report: {args.output}")


if __name__ == "__main__":
    main()
