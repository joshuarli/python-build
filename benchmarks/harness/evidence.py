"""Export complete benchmark observations without generated result directories."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def _observation(path: Path) -> dict[str, Any]:
    name = path.stem
    parts = name.split("-")
    if len(parts) != 3 or parts[0] not in {"timing", "memory"} or parts[2] not in {"baseline", "candidate"}:
        raise ValueError(f"unexpected benchmark observation name: {name}")
    record = _read_json(path)
    payload = record["payload"]
    if not isinstance(payload, dict):
        raise ValueError(f"invalid benchmark payload: {name}")
    memory = record.get("memory") if parts[0] == "memory" else None
    cpu = memory.get("cpu") if isinstance(memory, dict) else record.get("cpu")
    if not isinstance(cpu, dict):
        raise ValueError(f"missing kernel CPU observation: {name}")
    item: dict[str, Any] = {
        "id": name,
        "kind": parts[0],
        "side": parts[2],
        "digest": payload["digest"],
        "operation_count": payload["operation_count"],
        "user_seconds": cpu["user_seconds"],
        "system_seconds": cpu["system_seconds"],
    }
    if "backend" in payload:
        item["backend"] = payload["backend"]
    if parts[0] == "timing":
        item["external_wall_seconds"] = record["elapsed_seconds_external"]
        item["internal_wall_seconds"] = payload.get("elapsed_seconds")
    else:
        if not isinstance(memory, dict):
            raise ValueError(f"missing memory observation: {name}")
        for source, target in (
            ("peak_rss", "peak_rss_bytes"),
            ("peak_pss", "peak_pss_bytes"),
            ("peak_private", "peak_private_bytes"),
            ("peak_phys_footprint", "peak_physical_footprint_bytes"),
            ("peak_swap", "peak_swap_bytes"),
            ("steady_rss", "steady_rss_bytes"),
            ("steady_pss", "steady_pss_bytes"),
            ("process_count", "process_count"),
        ):
            item[target] = memory.get(source)
        item["sample_count"] = len(memory.get("samples", []))
        if memory.get("sampling_errors"):
            item["sampling_errors"] = memory["sampling_errors"]
    return item


def _interpreter_identity(value: dict[str, Any]) -> dict[str, Any]:
    return {key: value.get(key) for key in (
        "label", "kind", "version", "implementation", "abi", "platform",
        "compiler", "config_args", "executable_sha256",
    )}


def _installed_size(value: dict[str, Any]) -> dict[str, Any]:
    return {side: {key: record.get(key) for key in (
        "total_installed_bytes", "interpreter_executable_bytes", "libpython_bytes",
        "extension_module_bytes", "stdlib_source_bytes",
    )} for side, record in value.items()}


def compact_evidence(result_directory: Path, destination: Path) -> Path:
    """Write one reviewable record of every timed and memory attempt."""
    summary = _read_json(result_directory / "summary.json")
    provenance = _read_json(result_directory / "provenance.json")
    if summary.get("profile") == "rigorous" or summary.get("suite") in {"pyperformance", "full"}:
        raise ValueError("compact evidence currently supports smoke/realworld quick or standard runs")
    workloads = summary.get("workloads")
    if not isinstance(workloads, list):
        raise ValueError("benchmark summary has no workload list")
    document: dict[str, Any] = {
        "schema_version": 1,
        "method": {
            "suite": summary["suite"],
            "profile": summary["profile"],
            "run_order": provenance["run_order"],
            "measurement_mode": provenance["measurement_mode"],
            "offline_boundary": provenance["offline_boundary"],
            "bytecode_policy": provenance["bytecode_policy"],
            "memory_sampling_interval_seconds": provenance["memory_sampling_interval_seconds"],
            "python_environment": provenance["python_environment"],
        },
        "inputs": {
            "git_commit": provenance.get("git_commit"),
            "benchmark_lock_sha256": provenance["benchmark_lock_sha256"],
            "benchmark_packages": provenance["benchmark_packages"],
            "baseline": _interpreter_identity(provenance["baseline"]),
            "candidate": _interpreter_identity(provenance["candidate"]),
            "installed_size": _installed_size(provenance["installed_size"]),
        },
        "host": provenance["host"],
        "workloads": [],
    }
    for workload in workloads:
        if not isinstance(workload, dict) or not isinstance(workload.get("identity"), dict):
            raise ValueError("benchmark summary has an invalid workload")
        identity = workload["identity"]
        name = identity["name"]
        directory = result_directory / "realworld" / name
        paths = sorted(directory.glob("timing-*.json")) + sorted(directory.glob("memory-*.json"))
        if not paths:
            raise ValueError(f"{name}: no attempt observations")
        attempts = [_observation(path) for path in paths]
        for side in ("baseline", "candidate"):
            source = workload[side]
            for kind, expected in (("timing", len(source["timing"]["samples"])),
                                   ("memory", len(source["memory"]["rounds"]))):
                actual = sum(item["kind"] == kind and item["side"] == side for item in attempts)
                if actual != expected:
                    raise ValueError(f"{name}: {side} {kind} observations are incomplete")
        if any(item["digest"] != identity["digest"] for item in attempts):
            raise ValueError(f"{name}: attempt digest disagrees with the summary")
        document["workloads"].append({
            "identity": identity,
            "comparison": workload["comparison"],
            "verdict": workload["verdict"],
            "attempts": attempts,
        })
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite compact evidence: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(document, separators=(",", ":"), sort_keys=True) + "\n").encode()
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination
