"""Export compact, checked-in baseline snapshots from completed benchmark runs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import tempfile
from typing import Any


BASELINE_SCHEMA_VERSION = 1


def _mapping(value: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{where} must be a JSON object")
    return value


def _number(value: Any) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    if not math.isfinite(numeric):
        return None
    return int(value) if isinstance(value, int) else numeric


def _sample_summary(values: Any) -> dict[str, Any]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        values = ()
    samples = [number for value in values if (number := _number(value)) is not None]
    if not samples:
        return {"sample_count": 0, "median": None, "stdev": None, "min": None, "max": None}
    return {
        "sample_count": len(samples),
        "median": statistics.median(samples),
        "stdev": statistics.stdev(samples) if len(samples) > 1 else None,
        "min": min(samples),
        "max": max(samples),
    }


def _workload_measurement(raw: Mapping[str, Any], identity: Mapping[str, Any]) -> dict[str, Any]:
    baseline = _mapping(raw.get("baseline"), "workload baseline")
    timing = _mapping(baseline.get("timing", {}), "workload baseline timing")
    memory = _mapping(baseline.get("memory", {}), "workload baseline memory")
    allocations = _mapping(baseline.get("allocations", {}), "workload baseline allocations")

    memory_fields = (
        "peak_pss",
        "peak_rss",
        "peak_private",
        "peak_swap",
        "steady_pss",
        "postload_pss",
        "process_count",
    )
    memory_rounds: list[dict[str, Any]] = []
    for round_value in memory.get("rounds", ()):
        round_data = _mapping(round_value, "memory round")
        memory_rounds.append({field: round_data.get(field) for field in memory_fields})

    allocation_fields = (
        "status",
        "operations",
        "total_num_allocations",
        "total_bytes_allocated",
        "allocations_per_operation",
        "bytes_allocated_per_operation",
        "heap_peak_bytes",
        "heap_peak_status",
        "profiler",
        "profiler_version",
        "native_origins_status",
    )
    allocation_rounds: list[dict[str, Any]] = []
    for round_value in allocations.get("rounds", ()):
        round_data = _mapping(round_value, "allocation round")
        allocation_rounds.append({field: round_data.get(field) for field in allocation_fields})

    return {
        "name": identity.get("name"),
        "category": identity.get("category"),
        "operation": identity.get("operation"),
        "operation_count": identity.get("operation_count"),
        "digest": identity.get("digest"),
        "timing_seconds": _sample_summary(timing.get("samples", ())),
        "memory_bytes": {
            "round_count": len(memory_rounds),
            "rounds": memory_rounds,
            "peak_pss": _sample_summary([item["peak_pss"] for item in memory_rounds]),
            "peak_rss": _sample_summary([item["peak_rss"] for item in memory_rounds]),
            "peak_private": _sample_summary([item["peak_private"] for item in memory_rounds]),
            "steady_pss": _sample_summary([item["steady_pss"] for item in memory_rounds]),
            "postload_pss": _sample_summary([item["postload_pss"] for item in memory_rounds]),
        },
        "allocations": {
            "status": "recorded" if allocation_rounds else "not_run",
            "round_count": len(allocation_rounds),
            "rounds": allocation_rounds,
        },
    }


def _pyperformance_measurements(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    comparison = _mapping(value, "pyperformance comparison")
    benchmarks: list[dict[str, Any]] = []
    for item in comparison.get("benchmarks", ()):
        row = _mapping(item, "pyperformance benchmark")
        timing = _mapping(row.get("baseline_timing", {}), "pyperformance baseline timing")
        memory = _mapping(row.get("baseline_memory", {}), "pyperformance baseline memory")
        benchmarks.append(
            {
                "name": row.get("name"),
                "groups": row.get("groups", []),
                "timing_seconds": _sample_summary(timing.get("samples", ())),
                "memory_bytes": {
                    **_sample_summary(memory.get("samples", ())),
                    "mem_max_rss": memory.get("mem_max_rss"),
                    "command_max_rss": memory.get("command_max_rss"),
                },
            }
        )
    return {
        "suite_version": comparison.get("suite_version"),
        "pyperf_version": comparison.get("pyperf_version"),
        "groups": comparison.get("groups", {}),
        "benchmarks": benchmarks,
    }


def baseline_snapshot_path(snapshot: Mapping[str, Any], baseline_directory: Path) -> Path:
    """Return the stable tracked path for a runner, reference, and workload set."""

    source = _mapping(snapshot.get("source"), "baseline source")
    runner = _mapping(snapshot.get("runner"), "baseline runner")
    reference = _mapping(snapshot.get("reference_interpreter"), "baseline interpreter")
    pyperformance = snapshot.get("pyperformance")
    pyperformance_names = []
    if isinstance(pyperformance, Mapping):
        pyperformance_names = sorted(
            row.get("name")
            for row in pyperformance.get("benchmarks", ())
            if isinstance(row, Mapping) and isinstance(row.get("name"), str)
        )
    workload_names = sorted(
        row.get("name")
        for row in snapshot.get("workloads", ())
        if isinstance(row, Mapping) and isinstance(row.get("name"), str)
    )
    host_key = {
        key: runner.get(key)
        for key in (
            "system",
            "machine",
            "cpu_model",
            "physical_core_count",
            "logical_cpu_count",
            "memory_total_bytes",
        )
    }
    # Keep Linux snapshot names stable; distinguish Apple Silicon runners by
    # model and core mix because their sysctl topology is not Linux topology.
    if runner.get("system") == "Darwin":
        host_key.update({
            key: runner.get(key)
            for key in (
                "hardware_model",
                "performance_core_count",
                "efficiency_core_count",
            )
        })
    reference_key = {
        key: reference.get(key)
        for key in ("kind", "version", "abi", "platform")
    }
    target_key = {
        "suite": source.get("suite"),
        "profile": source.get("profile"),
        "workloads": workload_names,
        "pyperformance": pyperformance_names,
    }
    key = json.dumps(
        {"host": host_key, "reference": reference_key, "targets": target_key},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(key).hexdigest()[:12]

    def slug(value: Any, *, limit: int = 36) -> str:
        result = re.sub(r"[^a-z0-9]+", "-", str(value or "unknown").lower()).strip("-")
        return result[:limit].strip("-") or "unknown"

    name = "-".join(
        (
            slug(runner.get("system")),
            slug(runner.get("machine")),
            slug(runner.get("cpu_model")),
            slug(source.get("suite")),
            slug(source.get("profile")),
            slug(reference.get("kind")),
            digest,
        )
    )
    return baseline_directory.resolve() / f"{name}.json"


def build_baseline_snapshot(
    result_directory: Path,
    *,
    recorded_at: datetime | None = None,
) -> dict[str, Any]:
    """Create a small baseline-side snapshot from a completed run directory."""

    result_directory = result_directory.resolve()
    provenance = _mapping(json.loads((result_directory / "provenance.json").read_text()), "provenance")
    summary = _mapping(json.loads((result_directory / "summary.json").read_text()), "summary")
    reference = _mapping(provenance.get("baseline"), "baseline interpreter")

    workloads: list[dict[str, Any]] = []
    for comparison in summary.get("workloads", ()):
        row = _mapping(comparison, "workload comparison")
        identity = _mapping(row.get("identity"), "workload identity")
        name = identity.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("workload identity.name must be a non-empty string")
        raw_path = result_directory / "realworld" / name / "raw.json"
        raw = _mapping(json.loads(raw_path.read_text()), f"raw workload result {name}")
        raw_identity = _mapping(raw.get("identity"), f"raw workload identity {name}")
        workloads.append(_workload_measurement(raw, raw_identity))

    runner = _mapping(provenance.get("host", {}), "runner host")
    run_timestamp = provenance.get("timestamp_utc")
    if recorded_at is None and isinstance(run_timestamp, str):
        try:
            recorded_at = datetime.fromisoformat(run_timestamp)
        except ValueError:
            recorded_at = None
    snapshot: dict[str, Any] = {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "recorded_at_utc": (recorded_at or datetime.now(timezone.utc)).isoformat(),
        "comparison_role": "self_control_calibration" if reference.get("kind") == "self" else "interpreter_baseline",
        "source": {
            key: provenance.get(key)
            for key in (
                "git_commit",
                "timestamp_utc",
                "suite",
                "profile",
                "offline_boundary",
                "benchmark_lock_sha256",
                "benchmark_tool_versions",
                "benchmark_image_id",
                "container_runtime_version",
                "memory_sampling_interval_seconds",
            )
        },
        "runner": {
            "system": runner.get("system"),
            "machine": runner.get("machine"),
            "kernel_release": runner.get("kernel_release"),
            "macos_version": runner.get("macos_version"),
            "hardware_model": runner.get("hardware_model"),
            "cpu_model": runner.get("cpu_model"),
            "physical_core_count": runner.get("physical_core_count"),
            "logical_cpu_count": runner.get("logical_cpu_count"),
            "performance_core_count": runner.get("performance_core_count"),
            "efficiency_core_count": runner.get("efficiency_core_count"),
            "cpu_topology": runner.get("cpu_topology"),
            "numa_topology": runner.get("numa_topology"),
            "memory_total_bytes": runner.get("memory_total_bytes"),
            "swap_total_bytes": runner.get("swap_total_bytes"),
            "cpu_governors": runner.get("cpu_governors"),
            "cpu_boost_state": runner.get("cpu_boost_state"),
            "cpu_affinity": runner.get("cpu_affinity"),
            "load_average": runner.get("load_average"),
            "memory_available_bytes": runner.get("memory_available_bytes"),
            "cpu_frequency_control": runner.get("cpu_frequency_control"),
        },
        "reference_interpreter": dict(reference),
        "workloads": workloads,
        "pyperformance": _pyperformance_measurements(summary.get("pyperformance")),
    }
    return snapshot


def _write_snapshot(snapshot: Mapping[str, Any], destination: Path, *, overwrite: bool) -> Path:
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary, destination)
        else:
            os.link(temporary, destination)
    except FileExistsError as exc:
        raise ValueError(f"refusing to overwrite existing baseline file: {destination}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def save_baseline_snapshot(
    result_directory: Path,
    destination: Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Write a baseline snapshot, refusing replacement unless requested."""

    return _write_snapshot(
        build_baseline_snapshot(result_directory), destination, overwrite=overwrite
    )


def update_baseline_snapshot(result_directory: Path, baseline_directory: Path) -> Path:
    """Refresh the stable snapshot for a completed run."""

    snapshot = build_baseline_snapshot(result_directory)
    destination = baseline_snapshot_path(snapshot, baseline_directory)
    return _write_snapshot(snapshot, destination, overwrite=True)


__all__ = [
    "BASELINE_SCHEMA_VERSION",
    "baseline_snapshot_path",
    "build_baseline_snapshot",
    "save_baseline_snapshot",
    "update_baseline_snapshot",
]
