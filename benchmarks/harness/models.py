"""Typed validation and JSON helpers for benchmark result records.

The runner writes one result per workload.  Keeping the validation boundary
here means comparisons fail clearly when a run is incomplete or malformed,
instead of silently turning missing measurements into zeroes.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from typing import Any


RESULT_SCHEMA_VERSION = 1
IDENTITY_FIELDS = ("name", "category", "operation", "operation_count")
MEMORY_METRICS = (
    "peak_pss",
    "peak_rss",
    "peak_private",
    "steady_pss",
    "postload_pss",
    "memory_growth",
    "cgroup_peak",
    "process_count",
    "peak_swap",
)
ALLOCATION_METRICS = (
    "total_num_allocations",
    "total_allocations",
    "total_bytes_allocated",
    "heap_peak",
    "heap_peak_bytes",
    "peak_memory",
    "allocations_per_operation",
    "bytes_per_operation",
    "bytes_allocated_per_operation",
)


class ResultSchemaError(ValueError):
    """A benchmark result does not follow the supported result contract."""


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ResultSchemaError(f"{path} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise ResultSchemaError(f"{path} keys must be strings")
    return value


def _number(value: Any, path: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ResultSchemaError(f"{path} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ResultSchemaError(f"{path} must be finite")
    if positive and number <= 0:
        raise ResultSchemaError(f"{path} must be greater than zero")
    if not positive and number < 0:
        raise ResultSchemaError(f"{path} must not be negative")
    return number


def _json_compatible(value: Any, path: str) -> None:
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ResultSchemaError(f"{path} must contain JSON-compatible values: {error}") from error


def _validate_identity(value: Any) -> None:
    identity = _mapping(value, "identity")
    for field in IDENTITY_FIELDS:
        if field not in identity:
            raise ResultSchemaError(f"identity.{field} is required")
    for field in ("name", "category", "operation"):
        if not isinstance(identity[field], str) or not identity[field].strip():
            raise ResultSchemaError(f"identity.{field} must be a non-empty string")
    count = identity["operation_count"]
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise ResultSchemaError("identity.operation_count must be a positive integer")
    _json_compatible(identity, "identity")


def _validate_timing(value: Any, side: str) -> None:
    timing = _mapping(value, f"{side}.timing")
    samples = timing.get("samples")
    if not isinstance(samples, Sequence) or isinstance(samples, (str, bytes)):
        raise ResultSchemaError(f"{side}.timing.samples must be an array")
    if not samples:
        raise ResultSchemaError(f"{side}.timing.samples must contain at least one sample")
    for index, sample in enumerate(samples):
        _number(sample, f"{side}.timing.samples[{index}]", positive=True)
    _json_compatible(timing, f"{side}.timing")


def _validate_memory(value: Any, side: str) -> None:
    if value is None:
        return
    memory = _mapping(value, f"{side}.memory")
    rounds = memory.get("rounds", ())
    if not isinstance(rounds, Sequence) or isinstance(rounds, (str, bytes)):
        raise ResultSchemaError(f"{side}.memory.rounds must be an array")
    for index, raw_round in enumerate(rounds):
        sample = _mapping(raw_round, f"{side}.memory.rounds[{index}]")
        for metric in MEMORY_METRICS:
            if metric not in sample or sample[metric] is None:
                continue
            allow_negative = metric == "memory_growth"
            if allow_negative:
                number = sample[metric]
                if isinstance(number, bool) or not isinstance(number, (int, float)):
                    raise ResultSchemaError(
                        f"{side}.memory.rounds[{index}].{metric} must be a number"
                    )
                if not math.isfinite(float(number)):
                    raise ResultSchemaError(
                        f"{side}.memory.rounds[{index}].{metric} must be finite"
                    )
            else:
                _number(sample[metric], f"{side}.memory.rounds[{index}].{metric}")
    _json_compatible(memory, f"{side}.memory")


def _validate_allocations(value: Any, side: str) -> None:
    if value is None:
        return
    allocations = _mapping(value, f"{side}.allocations")
    if "operations" in allocations and allocations["operations"] is not None:
        operations = allocations["operations"]
        if isinstance(operations, bool) or not isinstance(operations, int) or operations <= 0:
            raise ResultSchemaError(f"{side}.allocations.operations must be a positive integer")
    rounds = allocations.get("rounds", ())
    if not isinstance(rounds, Sequence) or isinstance(rounds, (str, bytes)):
        raise ResultSchemaError(f"{side}.allocations.rounds must be an array")
    for index, raw_round in enumerate(rounds):
        sample = _mapping(raw_round, f"{side}.allocations.rounds[{index}]")
        if "operations" in sample and sample["operations"] is not None:
            operations = sample["operations"]
            if isinstance(operations, bool) or not isinstance(operations, int) or operations <= 0:
                raise ResultSchemaError(
                    f"{side}.allocations.rounds[{index}].operations must be a positive integer"
                )
        for metric in ALLOCATION_METRICS:
            if metric not in sample or sample[metric] is None:
                continue
            _number(sample[metric], f"{side}.allocations.rounds[{index}].{metric}")
    for metric in ALLOCATION_METRICS:
        if metric in allocations and allocations[metric] is not None:
            _number(allocations[metric], f"{side}.allocations.{metric}")
    _json_compatible(allocations, f"{side}.allocations")


def validate_workload_result(value: Any) -> dict[str, Any]:
    """Validate the runner's common `{identity, baseline, candidate}` record.

    Additional JSON-safe identity or measurement fields are preserved.  A
    `schema_version`, when present, must match this implementation.
    """
    record = _mapping(value, "workload result")
    version = record.get("schema_version")
    if version is not None and (
        isinstance(version, bool) or version != RESULT_SCHEMA_VERSION
    ):
        raise ResultSchemaError(
            f"unsupported result schema version {version!r}; "
            f"expected {RESULT_SCHEMA_VERSION}"
        )
    if "identity" not in record:
        raise ResultSchemaError("identity is required")
    _validate_identity(record["identity"])
    for side in ("baseline", "candidate"):
        if side not in record:
            raise ResultSchemaError(f"{side} is required")
        result = _mapping(record[side], side)
        if "timing" not in result:
            raise ResultSchemaError(f"{side}.timing is required")
        _validate_timing(result["timing"], side)
        _validate_memory(result.get("memory"), side)
        _validate_allocations(result.get("allocations"), side)
        _json_compatible(result, side)
    _json_compatible(record, "workload result")
    return dict(record)


def validate_summary(value: Any) -> dict[str, Any]:
    """Validate a machine-readable report document."""
    summary = _mapping(value, "summary")
    version = summary.get("schema_version")
    if isinstance(version, bool) or version != RESULT_SCHEMA_VERSION:
        raise ResultSchemaError(
            f"summary.schema_version must be {RESULT_SCHEMA_VERSION}"
        )
    for field in ("baseline", "candidate"):
        if field not in summary:
            raise ResultSchemaError(f"summary.{field} is required")
    workloads = summary.get("workloads")
    if not isinstance(workloads, Sequence) or isinstance(workloads, (str, bytes)):
        raise ResultSchemaError("summary.workloads must be an array")
    for index, workload in enumerate(workloads):
        item = _mapping(workload, f"summary.workloads[{index}]")
        for field in ("identity", "baseline", "candidate", "comparison", "verdict"):
            if field not in item:
                raise ResultSchemaError(
                    f"summary.workloads[{index}].{field} is required"
                )
        _validate_identity(item["identity"])
        for field in ("baseline", "candidate", "comparison", "verdict"):
            _mapping(item[field], f"summary.workloads[{index}].{field}")
        _json_compatible(item, f"summary.workloads[{index}]")
    _json_compatible(summary, "summary")
    return dict(summary)


def result_to_json(value: Any) -> str:
    """Serialize one validated workload result as stable UTF-8 JSON text."""
    record = validate_workload_result(value)
    return json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n"


def result_from_json(payload: str | bytes) -> dict[str, Any]:
    """Parse and validate one serialized workload result."""
    try:
        raw = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as error:
        raise ResultSchemaError(f"invalid result JSON: {error}") from error
    return validate_workload_result(raw)


def summary_to_json(value: Any) -> str:
    """Serialize a validated summary document as stable JSON text."""
    summary = validate_summary(value)
    return json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n"


def summary_from_json(payload: str | bytes) -> dict[str, Any]:
    """Parse and validate a serialized summary document."""
    try:
        raw = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as error:
        raise ResultSchemaError(f"invalid summary JSON: {error}") from error
    return validate_summary(raw)
