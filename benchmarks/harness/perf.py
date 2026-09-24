"""Optional Linux ``perf stat`` counters for diagnostic benchmark runs."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Mapping, Sequence

from .allocations import _write_json


DEFAULT_EVENTS = (
    "task-clock",
    "cycles",
    "instructions",
    "branches",
    "branch-misses",
    "cache-references",
    "cache-misses",
    "page-faults",
    "minor-faults",
    "major-faults",
    "context-switches",
    "cpu-migrations",
)
_EVENT_NAME = re.compile(r"^[A-Za-z0-9_.:/-]+$")
_PERMISSION_ERRORS = (
    "no permission",
    "permission denied",
    "perf_event_paranoid",
    "not supported",
    "not permitted",
    "unsupported",
    "unknown event",
    "invalid event",
    "event syntax error",
)


def _result(
    status: str,
    command: Sequence[str],
    *,
    reason: str | None = None,
    events: Sequence[str] = DEFAULT_EVENTS,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": status,
        "profiler": "perf stat",
        "command": list(command),
        "requested_events": list(events),
        "diagnostic_only": True,
        "elapsed_time_comparable": False,
        "reason": reason,
        "command_exit_status": None,
        "counters": None,
        "normalized": None,
        "raw_output": None,
    }


def parse_perf_stat(text: str, events: Sequence[str] = DEFAULT_EVENTS) -> dict[str, float | None]:
    """Parse `perf stat -x,` rows while preserving unsupported counters as null."""

    result: dict[str, float | None] = {}
    requested = set(events)
    for line in text.splitlines():
        columns = line.split(",")
        if len(columns) < 3:
            continue
        event = columns[2].strip()
        if event not in requested:
            continue
        value = columns[0].strip()
        if not value or value.startswith("<"):
            result[event] = None
            continue
        try:
            result[event] = float(value)
        except ValueError:
            result[event] = None
    return result


def run_perf_stat(
    command: Sequence[str],
    *,
    enabled: bool = False,
    operations: int | None = None,
    events: Sequence[str] = DEFAULT_EVENTS,
    env: Mapping[str, str] | None = None,
    output_json: Path | None = None,
    perf_executable: str | None = None,
) -> dict[str, Any]:
    """Run one command under optional Linux performance counter collection.

    Missing ``perf`` and permission or kernel restrictions return an explicit
    unavailable result. This function never changes ``perf_event_paranoid`` or
    any other host setting. Target command failures are reported separately in
    the result so a missing event cannot disguise a failed workload.
    """

    if not command or not command[0]:
        raise ValueError("command must not be empty")
    command = tuple(str(part) for part in command)
    events = tuple(events)
    if not events or any(not _EVENT_NAME.fullmatch(event) for event in events):
        raise ValueError("events must contain one or more valid perf event names")
    if len(set(events)) != len(events):
        raise ValueError("events must not contain duplicates")
    if operations is not None and operations <= 0:
        raise ValueError("operations must be a positive integer")
    if not enabled:
        report = _result("skipped", command, reason="perf diagnostics were not enabled", events=events)
        if output_json is not None:
            _write_json(Path(output_json), report)
        return report

    child_env = os.environ.copy()
    if env is not None:
        child_env.update({str(key): str(value) for key, value in env.items()})
    # perf's CSV number formatting follows the locale, so force decimal dots.
    target_locale = {
        name: value
        for name, value in child_env.items()
        if name == "LANG" or name.startswith("LC_")
    }
    child_env["LC_ALL"] = "C"
    executable = perf_executable or shutil.which("perf", path=child_env.get("PATH"))
    if executable is None:
        report = _result("unavailable", command, reason="perf executable was not found", events=events)
        if output_json is not None:
            _write_json(Path(output_json), report)
        return report
    if not Path("/proc/sys/kernel/perf_event_paranoid").exists():
        report = _result("unavailable", command, reason="Linux perf events are unavailable on this host", events=events)
        if output_json is not None:
            _write_json(Path(output_json), report)
        return report

    env_executable = shutil.which("env", path=child_env.get("PATH"))
    if env_executable is None:
        report = _result(
            "unavailable",
            command,
            reason="env executable is needed to preserve the target locale",
            events=events,
        )
        if output_json is not None:
            _write_json(Path(output_json), report)
        return report
    target_command = [env_executable, "-u", "LC_ALL"]
    target_command.extend(f"{name}={value}" for name, value in sorted(target_locale.items()))
    target_command.extend(("--", *command))
    perf_command = [executable, "stat", "-x,", "-e", ",".join(events), "--", *target_command]
    try:
        completed = subprocess.run(perf_command, text=True, capture_output=True, env=child_env)
    except OSError as error:
        report = _result("unavailable", command, reason=str(error), events=events)
        if output_json is not None:
            _write_json(Path(output_json), report)
        return report
    raw_output = completed.stderr
    counters = parse_perf_stat(raw_output, events)
    if completed.returncode != 0:
        detail = raw_output.strip() or f"perf stat exited with status {completed.returncode}"
        lower_detail = detail.lower()
        if any(marker in lower_detail for marker in _PERMISSION_ERRORS):
            status = "unavailable"
            exit_status = None
            reason = detail[-2000:]
        else:
            status = "command_failed"
            exit_status = completed.returncode
            reason = detail[-2000:]
    else:
        status = "complete"
        exit_status = 0
        reason = None

    normalized: dict[str, float | None] | None = None
    if operations is not None:
        normalized = {
            f"{name.replace('-', '_')}_per_operation": (
                value / operations if value is not None else None
            )
            for name, value in counters.items()
        }
    cycles = counters.get("cycles")
    instructions = counters.get("instructions")
    cache_misses = counters.get("cache-misses")
    faults = counters.get("page-faults")
    if normalized is None:
        normalized = {}
    normalized["instructions_per_operation"] = (
        instructions / operations if instructions is not None and operations else None
    )
    normalized["cycles_per_operation"] = (
        cycles / operations if cycles is not None and operations else None
    )
    normalized["cache_misses_per_operation"] = (
        cache_misses / operations if cache_misses is not None and operations else None
    )
    normalized["faults_per_operation"] = (
        faults / operations if faults is not None and operations else None
    )
    normalized["ipc"] = (
        instructions / cycles
        if instructions is not None and cycles is not None and cycles > 0
        else None
    )
    report = {
        "schema_version": 1,
        "status": status,
        "profiler": "perf stat",
        "command": list(command),
        "requested_events": list(events),
        "diagnostic_only": True,
        "elapsed_time_comparable": False,
        "reason": reason,
        "operations": operations,
        "command_exit_status": exit_status,
        "counters": counters,
        "normalized": normalized,
        "raw_output": raw_output,
    }
    if output_json is not None:
        _write_json(Path(output_json), report)
    return report
