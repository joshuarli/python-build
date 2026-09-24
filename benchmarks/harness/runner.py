"""Paired, isolated passes over repository-owned application workloads.

Timing uses an uninstrumented child. Memory and allocation collection run
the same semantic operation in fresh children; their elapsed times are never
used as timing observations.
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from typing import Any

from benchmarks.harness.process import run_command
from benchmarks.workloads.registry import Workload


PROFILE_ROUNDS = {
    "quick": (2, 2),
    "standard": (5, 3),
    "rigorous": (10, 5),
}


def workload_command(python: Path, workload: Workload, iterations: int, *, memory: bool = False) -> list[str]:
    if workload.name == "python_startup":
        if memory:
            # The near-empty interpreter would otherwise exit between 10 ms
            # smaps polls. Hold its initialized address space long enough to
            # observe PSS; only the separate timing pass measures startup.
            return [str(python), "-c", "import time; time.sleep(0.12)"]
        return [str(python), "-c", "pass"]
    return [
        str(python), "-m", f"benchmarks.workloads.{workload.module}",
        workload.name, "--iterations", str(iterations),
    ]


def workload_environment(
    site_packages: Path | None,
    *,
    wheelhouse: Path | None = None,
    pip_packages: tuple[str, ...] = (),
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    paths = [str(root)]
    if site_packages is not None:
        paths.insert(0, str(site_packages))
    env.update({
        "PYTHONPATH": os.pathsep.join(paths),
        "PYTHONHASHSEED": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONMALLOC": "default",
    })
    if wheelhouse is not None:
        env["BENCH_WHEELHOUSE"] = str(wheelhouse)
    if pip_packages:
        env["BENCH_PIP_PACKAGES"] = " ".join(pip_packages)
    if extra:
        env.update(extra)
    return env


def _measurement_payload(stdout: str, workload: Workload, iterations: int) -> dict[str, Any]:
    if workload.name == "python_startup":
        return {"operation_count": 1, "digest": "empty-interpreter"}
    lines = stdout.strip().splitlines()
    if not lines:
        raise RuntimeError(f"{workload.name}: missing correctness payload")
    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{workload.name}: invalid correctness payload: {lines[-1]!r}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("operation_count"), int):
        raise RuntimeError(f"{workload.name}: missing operation count")
    if payload["operation_count"] < iterations or not isinstance(payload.get("digest"), str):
        raise RuntimeError(f"{workload.name}: failed correctness payload")
    if not payload["digest"]:
        raise RuntimeError(f"{workload.name}: empty correctness digest")
    return payload


def _memory_dict(value: Any) -> dict[str, Any]:
    if value is None:
        raise RuntimeError("memory sampler returned no memory metrics")
    if hasattr(value, "as_dict"):
        value = value.as_dict()
    if dataclasses.is_dataclass(value):
        value = dataclasses.asdict(value)
    if not isinstance(value, dict):
        raise RuntimeError("memory sampler returned unexpected type")
    return {
        "peak_pss": value.get("peak_pss_bytes"),
        "peak_rss": value.get("peak_rss_bytes"),
        "peak_private": value.get("peak_private_bytes"),
        "peak_swap": value.get("peak_swap_bytes"),
        "process_count": value.get("peak_process_count"),
        "steady_pss": value.get("steady_pss_bytes"),
        "postload_pss": value.get("postload_pss_bytes"),
        "cgroup_current": value.get("cgroup_current_bytes"),
        "cgroup_peak": value.get("cgroup_peak_bytes"),
        "cgroup_events": value.get("cgroup_events"),
        "cgroup_error": value.get("cgroup_error"),
        "samples": value.get("samples", []),
        "sampling_errors": value.get("sampling_errors", []),
    }


def _ensure_clean(result: Any, workload: Workload, side: str, pass_name: str) -> None:
    if not result.cleanup_complete or result.remaining_pids:
        raise RuntimeError(
            f"{workload.name} {pass_name} {side} left processes behind: {result.remaining_pids}"
        )


def run_workload(
    workload: Workload,
    baseline: Path,
    candidate: Path,
    *,
    profile: str,
    site_packages: Path | None,
    output_dir: Path,
    wheelhouse: Path | None = None,
    pip_packages: tuple[str, ...] = (),
    allocation_site: Path | None = None,
    affinity: set[int] | None = None,
    timeout_seconds: float = 300,
    memory_interval_seconds: float = 0.01,
    perf_stat: bool = False,
) -> dict[str, Any]:
    if profile not in PROFILE_ROUNDS:
        raise ValueError(f"unknown profile: {profile}")
    output_dir.mkdir(parents=True, exist_ok=True)
    timing_rounds, memory_rounds = PROFILE_ROUNDS[profile]
    if workload.noise_class == "noisy":
        # Scheduling and child overlap make process-tree peaks less stable in
        # ASGI, pip, and multiprocessing workloads. Five separate memory
        # processes give their medians enough observations to resist one
        # transient peak without relaxing the baseline-derived gate.
        memory_rounds = max(memory_rounds, 5)
    sides = {"baseline": baseline, "candidate": candidate}
    env = workload_environment(site_packages, wheelhouse=wheelhouse, pip_packages=pip_packages)
    result: dict[str, Any] = {
        "identity": {
            "name": workload.name,
            "category": workload.category,
            "operation": workload.operation,
            "operation_count": workload.iterations,
            "noise_class": workload.noise_class,
            "packages": list(workload.packages),
        },
        "baseline": {"timing": {"samples": []}, "memory": {"rounds": []}},
        "candidate": {"timing": {"samples": []}, "memory": {"rounds": []}},
    }
    digests: set[str] = set()
    operation_counts: set[int] = set()
    for side, python in sides.items():
        warmup = run_command(workload_command(python, workload, workload.iterations),
                             env=env, cwd=Path(__file__).resolve().parents[2],
                             timeout=timeout_seconds, affinity=affinity,
                             sample_interval_seconds=None)
        _ensure_clean(warmup, workload, side, "warmup")
        if warmup.returncode != 0 or warmup.timed_out:
            raise RuntimeError(f"{workload.name} warmup {side} failed: {warmup.stderr[-2000:]}")
        warmup_payload = _measurement_payload(warmup.stdout.decode("utf-8", errors="replace"), workload,
                                              workload.iterations)
        digests.add(warmup_payload["digest"])
        operation_counts.add(warmup_payload["operation_count"])
    # Alternating BC/CB order prevents one side from always running cold.
    order = [side for index in range(timing_rounds) for side in
             (("baseline", "candidate") if index % 2 == 0 else ("candidate", "baseline"))]
    for index, side in enumerate(order):
        command = workload_command(sides[side], workload, workload.iterations)
        measured = run_command(command, env=env, cwd=Path(__file__).resolve().parents[2],
                               timeout=timeout_seconds, affinity=affinity,
                               sample_interval_seconds=None)
        _ensure_clean(measured, workload, side, "timing")
        if measured.returncode != 0 or measured.timed_out:
            raise RuntimeError(f"{workload.name} timing {side} failed: {measured.stderr[-2000:]}")
        payload = _measurement_payload(measured.stdout.decode("utf-8", errors="replace"), workload,
                                       workload.iterations)
        digests.add(payload["digest"])
        operation_counts.add(payload["operation_count"])
        elapsed = payload.get("elapsed_seconds", measured.duration_seconds)
        if not isinstance(elapsed, (int, float)) or elapsed <= 0:
            raise RuntimeError(f"{workload.name}: invalid elapsed time")
        result[side]["timing"]["samples"].append(elapsed)
        (output_dir / f"timing-{index:02d}-{side}.json").write_text(
            json.dumps({"payload": payload, "elapsed_seconds_external": measured.duration_seconds}, indent=2) + "\n"
        )
    for index in range(memory_rounds):
        for side in (("baseline", "candidate") if index % 2 == 0 else ("candidate", "baseline")):
            command = workload_command(sides[side], workload, workload.iterations, memory=True)
            measured = run_command(command, env=env, cwd=Path(__file__).resolve().parents[2],
                                   timeout=timeout_seconds, affinity=affinity,
                                   sample_interval_seconds=memory_interval_seconds)
            _ensure_clean(measured, workload, side, "memory")
            if measured.returncode != 0 or measured.timed_out:
                raise RuntimeError(f"{workload.name} memory {side} failed: {measured.stderr[-2000:]}")
            payload = _measurement_payload(measured.stdout.decode("utf-8", errors="replace"), workload,
                                           workload.iterations)
            digests.add(payload["digest"])
            operation_counts.add(payload["operation_count"])
            memory = _memory_dict(measured.memory)
            result[side]["memory"]["rounds"].append(memory)
            (output_dir / f"memory-{index:02d}-{side}.json").write_text(
                json.dumps({"payload": payload, "memory": memory}, indent=2) + "\n"
            )
    if len(digests) != 1:
        raise RuntimeError(f"{workload.name}: correctness digest differs across runs: {digests}")
    if len(operation_counts) != 1:
        raise RuntimeError(f"{workload.name}: operation count differs across runs: {operation_counts}")
    result["identity"]["digest"] = next(iter(digests))
    result["identity"]["operation_count"] = next(iter(operation_counts))
    if allocation_site is not None:
        from benchmarks.harness.allocations import run_allocation_pass

        allocation_rounds = 3 if profile == "rigorous" else 2 if profile == "standard" else 1
        for side, python in sides.items():
            command = workload_command(python, workload, workload.allocation_iterations)
            allocation_operations = (
                result["identity"]["operation_count"] * workload.allocation_iterations
                // workload.iterations
            )
            allocation_samples = []
            for index in range(allocation_rounds):
                allocation_samples.append(run_allocation_pass(
                    command,
                    memray_pythonpath=[allocation_site, *([site_packages] if site_packages else [])],
                    output_json=output_dir / f"allocations-{side}-{index:02d}.json",
                    operations=allocation_operations,
                    env=env,
                    follow_fork=workload.name == "multiprocess_pool",
                    timeout_seconds=timeout_seconds,
                ))
            result[side]["allocations"] = {"rounds": allocation_samples}
    if perf_stat:
        from benchmarks.harness.perf import run_perf_stat

        for side, python in sides.items():
            result[side]["perf"] = run_perf_stat(
                workload_command(python, workload, workload.iterations),
                enabled=True,
                operations=result["identity"]["operation_count"],
                env=env,
                output_json=output_dir / f"perf-{side}.json",
            )
    (output_dir / "raw.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result
