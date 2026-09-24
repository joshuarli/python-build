"""Dedicated Memray allocation profiling for a target Python command.

Allocation profiles are resource diagnostics. The traced process has
substantial profiler overhead, so these results must not be treated as timing
measurements or compared with ordinary benchmark elapsed time.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Mapping, Sequence

from .process import ProcessResult, run_command


_NATIVE_ORIGINS_SCRIPT = r'''
import json
import sys
from collections import Counter

from memray import FileReader

def frame_name(frame):
    function = getattr(frame, "function", None)
    filename = getattr(frame, "file", None)
    line = getattr(frame, "line", None)
    if function is None and isinstance(frame, (tuple, list)):
        values = list(frame)
        function = values[0] if values else None
        filename = values[1] if len(values) > 1 else None
        line = values[2] if len(values) > 2 else None
    parts = [str(part) for part in (function, filename, line) if part is not None]
    return ":".join(parts) or str(frame)

allocations = Counter()
allocated_bytes = Counter()
reader = FileReader(sys.argv[1])
for record in reader.get_allocation_records():
    allocator = getattr(record.allocator, "name", str(record.allocator))
    if allocator in {"FREE", "MUNMAP", "PYMALLOC_FREE", "OBJECT_DESTROYED"}:
        continue
    try:
        trace = record.native_stack_trace()
    except (NotImplementedError, RuntimeError):
        continue
    if not trace:
        continue
    origin = frame_name(trace[0])
    allocations[origin] += 1
    allocated_bytes[origin] += int(record.size)

origins = [
    {"origin": origin, "allocations": count, "bytes": allocated_bytes[origin]}
    for origin, count in allocations.most_common()
]
origins.sort(key=lambda item: (-item["bytes"], -item["allocations"], item["origin"]))
print(json.dumps({"status": "available", "origins": origins[:50]}))
'''


def _pythonpath_env(
    extra_paths: Path | Sequence[Path], env: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Build a child environment with the external Memray prefix first."""

    child_env = os.environ.copy()
    if env is not None:
        child_env.update({str(key): str(value) for key, value in env.items()})
    paths = [extra_paths] if isinstance(extra_paths, (str, os.PathLike)) else list(extra_paths)
    prefix = [os.fspath(path) for path in paths]
    inherited = child_env.get("PYTHONPATH")
    if inherited:
        prefix.append(inherited)
    child_env["PYTHONPATH"] = os.pathsep.join(prefix)
    return child_env


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    """Publish a JSON result atomically so interrupted writes are not mistaken for data."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.",
        suffix=".tmp", delete=False,
    ) as stream:
        temporary = Path(stream.name)
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _unavailable_report(command: Sequence[str], reason: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "unavailable",
        "profiler": "memray",
        "profiler_version": None,
        "reason": reason,
        "command": list(command),
        "diagnostic_only": True,
        "elapsed_time_comparable": False,
        "total_num_allocations": None,
        "total_bytes_allocated": None,
        "heap_peak_bytes": None,
        "allocator_type_distribution": None,
        "top_allocations_by_size": None,
        "top_allocations_by_count": None,
        "top_modules_by_allocation_size": None,
        "top_modules_by_allocation_count": None,
        "allocations_per_operation": None,
        "bytes_allocated_per_operation": None,
        "native_origins_status": "unavailable",
        "native_origins": None,
    }


class AllocationCommandTimeout(subprocess.TimeoutExpired):
    """A timed-out allocation subprocess after its process group was cleaned."""

    def __init__(self, command: Sequence[str], timeout: float, result: ProcessResult):
        super().__init__(command, timeout, output=result.stdout, stderr=result.stderr)
        self.cleanup_complete = result.cleanup_complete
        self.remaining_pids = result.remaining_pids

    def __str__(self) -> str:
        message = super().__str__()
        if self.cleanup_complete:
            return message
        return f"{message}; process cleanup left live pids {list(self.remaining_pids)}"


def _run_child_command(
    command: Sequence[str],
    *,
    env: Mapping[str, str],
    timeout_seconds: float,
    check: bool = False,
) -> ProcessResult:
    """Capture a Memray stage in an isolated process group with a hard timeout."""

    result = run_command(
        command,
        env=env,
        timeout=timeout_seconds,
        sample_interval_seconds=None,
    )
    if result.timed_out:
        raise AllocationCommandTimeout(command, timeout_seconds, result)
    if not result.cleanup_complete:
        raise RuntimeError(
            f"allocation command left live descendant processes: {list(result.remaining_pids)}"
        )
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            command,
            output=result.stdout,
            stderr=result.stderr,
        )
    return result


def _run_native_origins(
    python_prefix: Sequence[str],
    capture_path: Path,
    env: Mapping[str, str],
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Summarize the top native frame of each allocation when traces exist."""

    command = [*python_prefix, "-c", _NATIVE_ORIGINS_SCRIPT, os.fspath(capture_path)]
    result = _run_child_command(command, env=env, timeout_seconds=timeout_seconds)
    if result.returncode != 0:
        detail = (
            result.stderr.decode("utf-8", errors="replace").strip()
            or result.stdout.decode("utf-8", errors="replace").strip()
            or "native trace read failed"
        )
        return {"status": "unavailable", "reason": detail[:1000], "origins": None}
    try:
        report = json.loads(result.stdout.decode("utf-8"))
    except json.JSONDecodeError as error:
        return {
            "status": "unavailable",
            "reason": f"invalid native-origin JSON: {error}",
            "origins": None,
        }
    if not isinstance(report, dict) or report.get("status") != "available":
        return {
            "status": "unavailable",
            "reason": "Memray returned an invalid native-origin report",
            "origins": None,
        }
    return report


def _split_python_invocation(arguments: Sequence[str]) -> tuple[list[str], list[str]]:
    """Separate interpreter switches from the script/module/code invocation."""

    interpreter_options: list[str] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument in {"-c", "-m"}:
            return interpreter_options, list(arguments[index:])
        if argument == "--":
            return interpreter_options, list(arguments[index:])
        if argument in {"-X", "-W", "--check-hash-based-pycs"}:
            if index + 1 >= len(arguments):
                raise ValueError(f"Python option {argument!r} needs a value")
            interpreter_options.extend((argument, arguments[index + 1]))
            index += 2
            continue
        if argument.startswith(("-X", "-W")) and len(argument) > 2:
            interpreter_options.append(argument)
            index += 1
            continue
        if argument.startswith("--check-hash-based-pycs="):
            interpreter_options.append(argument)
            index += 1
            continue
        if argument.startswith("-") and len(argument) > 1:
            # Python permits combining these single-letter switches (for
            # example, -bb or -OO). Unknown options are rejected instead of
            # being reinterpreted as a script path by `memray run`.
            if all(flag in "bdEIOPqsvx" for flag in argument[1:]):
                interpreter_options.append(argument)
                index += 1
                continue
            raise ValueError(f"unsupported Python interpreter option {argument!r}")
        return interpreter_options, list(arguments[index:])
    return interpreter_options, []


def run_allocation_pass(
    command: Sequence[str],
    *,
    memray_pythonpath: Path | Sequence[Path],
    output_json: Path,
    operations: int | None = None,
    env: Mapping[str, str] | None = None,
    native: bool = True,
    trace_python_allocators: bool = True,
    follow_fork: bool = False,
    timeout_seconds: float = 300,
) -> dict[str, Any]:
    """Run a Python command under Memray and write normalized JSON metrics.

    ``command`` is the full ordinary invocation, for example
    ``[python, "-m", "module", "--rows", "100"]`` or
    ``[python, "-X", "dev", "script.py"]``. Standard Python interpreter
    switches are applied before Memray starts the target. Memray and its
    native extension are loaded from ``memray_pythonpath`` outside the target
    installation. Existing ``PYTHONPATH`` values supplied by the runner are
    retained after that external prefix.

    If Memray cannot be imported by the target interpreter, a JSON report is
    still written with ``status="unavailable"`` and null metrics. A target
    command or profiler failure raises ``subprocess.CalledProcessError`` so
    an incomplete profile cannot be mistaken for a valid zero-allocation run.
    A stage that exceeds its timeout raises ``AllocationCommandTimeout`` after
    process-group cleanup; cleanup failures include the remaining process IDs.
    ``operations`` is the number of semantic operations completed by the
    target, supplied by its workload definition; Memray does not infer it.
    With ``follow_fork=True``, child capture files are analyzed separately.
    Allocation counts and bytes are summed across process profiles; no single
    heap peak is reported because the captures do not encode a combined
    process-tree high-water mark. Every Memray subprocess has the same
    ``timeout_seconds`` limit and is run in an isolated process group so a
    timeout also cleans up descendants.
    """

    if not command or not command[0]:
        raise ValueError("command must start with the target Python executable")
    if operations is not None and operations <= 0:
        raise ValueError("operations must be a positive integer")
    if timeout_seconds < 0:
        raise ValueError("timeout_seconds must be non-negative")
    command = tuple(str(part) for part in command)
    interpreter_options, target_arguments = _split_python_invocation(command[1:])
    python_prefix = [command[0], *interpreter_options]
    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    capture_path = output_json.with_name(f"{output_json.stem}.memray.bin")
    stats_path = output_json.with_name(f"{output_json.stem}.memray-stats.json")
    for artifact in (output_json, capture_path, stats_path):
        if artifact.exists():
            raise FileExistsError(f"refusing to overwrite allocation artifact: {artifact}")
    existing_children = list(capture_path.parent.glob(capture_path.name + ".*"))
    if existing_children:
        raise FileExistsError(
            f"refusing to overwrite allocation child capture: {existing_children[0]}"
        )
    existing_child_stats = list(
        output_json.parent.glob(f"{output_json.stem}.memray-stats-*.json")
    )
    if existing_child_stats:
        raise FileExistsError(
            f"refusing to overwrite allocation stats: {existing_child_stats[0]}"
        )

    child_env = _pythonpath_env(memray_pythonpath, env)
    python = command[0]
    probe = _run_child_command(
        [*python_prefix, "-c", (
            "import importlib.metadata, json, memray; "
            "print(json.dumps({'version': importlib.metadata.version('memray')}))"
        )],
        env=child_env,
        timeout_seconds=timeout_seconds,
    )
    if probe.returncode != 0:
        detail = (
            probe.stderr.decode("utf-8", errors="replace").strip()
            or probe.stdout.decode("utf-8", errors="replace").strip()
            or "Memray import failed"
        )
        report = _unavailable_report(command, detail[:1000])
        _write_json(output_json, report)
        return report
    try:
        profiler_version = str(json.loads(probe.stdout.decode("utf-8"))["version"])
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise RuntimeError(f"target interpreter returned invalid Memray version data: {error}")

    profile_command = [*python_prefix, "-m", "memray", "run"]
    if native:
        profile_command.append("--native")
    if trace_python_allocators:
        profile_command.append("--trace-python-allocators")
    if follow_fork:
        profile_command.append("--follow-fork")
    profile_command.extend(("--quiet", "--output", os.fspath(capture_path)))
    profile_command.extend(target_arguments)
    # Keep workload JSON digests out of the benchmark driver's stdout. The
    # process runner captures output for failure diagnostics and discards it on
    # success, while preserving stderr for any raised CalledProcessError.
    _run_child_command(
        profile_command,
        check=True,
        env=child_env,
        timeout_seconds=timeout_seconds,
    )

    capture_paths = [capture_path]
    if follow_fork:
        capture_paths.extend(sorted(capture_path.parent.glob(capture_path.name + ".*")))
    capture_paths = [path for path in capture_paths if path.is_file()]
    if not capture_paths:
        raise RuntimeError("Memray completed without writing an allocation capture")

    process_profiles: list[dict[str, Any]] = []
    for index, process_capture in enumerate(capture_paths):
        process_stats_path = (
            stats_path
            if index == 0
            else output_json.with_name(f"{output_json.stem}.memray-stats-{index:03d}.json")
        )
        if process_stats_path.exists():
            raise FileExistsError(f"refusing to overwrite allocation artifact: {process_stats_path}")
        stats_command = [
            python, "-m", "memray", "stats", "--json", "--force", "--output",
            os.fspath(process_stats_path), os.fspath(process_capture),
        ]
        _run_child_command(
            stats_command,
            check=True,
            env=child_env,
            timeout_seconds=timeout_seconds,
        )
        process_stats = json.loads(process_stats_path.read_text(encoding="utf-8"))
        if not isinstance(process_stats, dict):
            raise ValueError("Memray stats JSON must contain an object")
        metadata = process_stats.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise ValueError("Memray stats metadata must contain an object")
        if not native:
            native_report = {"status": "disabled", "origins": None}
        elif metadata.get("has_native_traces") is False:
            native_report = {
                "status": "unavailable",
                "reason": "capture has no native traces",
                "origins": None,
            }
        else:
            native_report = _run_native_origins(
                python_prefix,
                process_capture,
                child_env,
                timeout_seconds=timeout_seconds,
            )
        process_profiles.append({
            "pid": metadata.get("pid"),
            "capture_path": os.fspath(process_capture),
            "stats_path": os.fspath(process_stats_path),
            "total_num_allocations": process_stats.get("total_num_allocations"),
            "total_bytes_allocated": process_stats.get("total_bytes_allocated"),
            "heap_peak_bytes": metadata.get("peak_memory"),
            "native_origins_status": native_report["status"],
            "native_origins": native_report.get("origins"),
            "native_origins_reason": native_report.get("reason"),
            "memray_metadata": metadata,
            "memray_stats": process_stats,
        })

    def sum_metric(name: str) -> int | float | None:
        values = [profile[name] for profile in process_profiles]
        if not all(isinstance(value, (int, float)) for value in values):
            return None
        return sum(values)

    total_allocations = sum_metric("total_num_allocations")
    total_bytes = sum_metric("total_bytes_allocated")
    allocator_distribution: Counter[str] = Counter()
    for profile in process_profiles:
        distribution = profile["memray_stats"].get("allocator_type_distribution") or {}
        if isinstance(distribution, dict):
            allocator_distribution.update({
                str(name): int(count)
                for name, count in distribution.items()
                if isinstance(count, int) and not isinstance(count, bool)
            })
    combined_metadata: dict[str, Any]
    if len(process_profiles) == 1:
        combined_metadata = process_profiles[0]["memray_metadata"]
    else:
        combined_metadata = {
            "process_count": len(process_profiles),
            "peak_memory": None,
            "has_native_traces": all(
                profile["memray_metadata"].get("has_native_traces") is True
                for profile in process_profiles
            ),
        }
    native_origins_status = (
        process_profiles[0]["native_origins_status"]
        if len(process_profiles) == 1
        else "per_process"
    )
    native_origins: Any = (
        process_profiles[0]["native_origins"]
        if len(process_profiles) == 1
        else [
            {"pid": profile["pid"], "origins": profile["native_origins"]}
            for profile in process_profiles
        ]
    )
    main_stats = process_profiles[0]["memray_stats"] if len(process_profiles) == 1 else None
    main_metadata = process_profiles[0]["memray_metadata"] if len(process_profiles) == 1 else combined_metadata

    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "complete",
        "profiler": "memray",
        "profiler_version": profiler_version,
        "command": list(command),
        "diagnostic_only": True,
        "elapsed_time_comparable": False,
        "profile_options": {
            "native": native,
            "trace_python_allocators": trace_python_allocators,
            "follow_fork": follow_fork,
        },
        "operations": operations,
        "total_num_allocations": total_allocations,
        "total_bytes_allocated": total_bytes,
        "heap_peak_bytes": main_metadata.get("peak_memory"),
        "heap_peak_status": "available" if len(process_profiles) == 1 else "per_process_only",
        "process_heap_peaks": [
            {"pid": profile["pid"], "heap_peak_bytes": profile["heap_peak_bytes"]}
            for profile in process_profiles
        ],
        "allocator_type_distribution": dict(allocator_distribution),
        "top_allocations_by_size": (
            main_stats.get("top_allocations_by_size") if main_stats is not None else None
        ),
        "top_allocations_by_count": (
            main_stats.get("top_allocations_by_count") if main_stats is not None else None
        ),
        "top_modules_by_allocation_size": (
            main_stats.get("top_modules_by_allocation_size") if main_stats is not None else None
        ),
        "top_modules_by_allocation_count": (
            main_stats.get("top_modules_by_allocation_count") if main_stats is not None else None
        ),
        "allocations_per_operation": (
            total_allocations / operations
            if operations is not None and isinstance(total_allocations, (int, float))
            else None
        ),
        "bytes_allocated_per_operation": (
            total_bytes / operations
            if operations is not None and isinstance(total_bytes, (int, float))
            else None
        ),
        "native_origins_status": native_origins_status,
        "native_origins": native_origins,
        "process_profiles": process_profiles,
        "memray_metadata": combined_metadata,
        "memray_stats": main_stats,
        "capture_path": os.fspath(capture_path),
        "stats_path": os.fspath(stats_path),
    }
    _write_json(output_json, report)
    return report
