"""Run benchmark commands and sample Linux process trees.

The Linux sampler stays outside the target interpreter and reads `/proc`
directly. On macOS, `sample_interval_seconds=None` selects the unmonitored
timing runner; process memory sampling is available only on Linux.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from typing import IO

from .memory import (
    CgroupV2MemoryScope,
    CgroupV2MemorySnapshot,
    MemorySample,
    ProcessMemoryMetrics,
    SmapsRollup,
    parse_smaps_rollup,
    sum_rollups,
)


@dataclass(frozen=True)
class ProcessResult:
    """Command output, status, elapsed time, and optional process-tree data."""

    command: tuple[str, ...]
    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool
    duration_seconds: float
    memory: ProcessMemoryMetrics | None
    cleanup_complete: bool
    remaining_pids: tuple[int, ...]

    def as_dict(self) -> dict[str, object]:
        """Return JSON-ready status and memory data (output is UTF-8 decoded)."""

        return {
            "command": list(self.command),
            "returncode": self.returncode,
            "stdout": self.stdout.decode("utf-8", errors="replace"),
            "stderr": self.stderr.decode("utf-8", errors="replace"),
            "timed_out": self.timed_out,
            "duration_seconds": self.duration_seconds,
            "memory": None if self.memory is None else self.memory.as_dict(),
            "cleanup_complete": self.cleanup_complete,
            "remaining_pids": list(self.remaining_pids),
        }


@dataclass(frozen=True)
class _ProcInfo:
    pid: int
    parent_pid: int
    process_group: int
    state: str
    start_ticks: int


@dataclass
class _Collected:
    samples: list[MemorySample] = field(default_factory=list)
    phases: dict[str, MemorySample] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    seen: dict[int, int] = field(default_factory=dict)


def _read_proc_info(path: Path) -> _ProcInfo | None:
    """Read stable fields from `/proc/<pid>/stat`; names may contain `)` ."""

    try:
        raw = (path / "stat").read_text(encoding="ascii")
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
        return None
    close = raw.rfind(")")
    if close < 0:
        return None
    try:
        pid = int(raw[: raw.find(" ")])
        fields = raw[close + 1 :].split()
        # Fields start at stat field 3 (state). PPID, process group and start
        # time are fields 4, 5 and 22 respectively.
        return _ProcInfo(
            pid=pid,
            state=fields[0],
            parent_pid=int(fields[1]),
            process_group=int(fields[2]),
            start_ticks=int(fields[19]),
        )
    except (IndexError, ValueError):
        return None


def _proc_table(proc_root: Path) -> dict[int, _ProcInfo]:
    infos: dict[int, _ProcInfo] = {}
    try:
        entries = tuple(proc_root.iterdir())
    except OSError as error:
        raise RuntimeError(f"cannot read procfs at {proc_root}: {error}") from error
    for entry in entries:
        if not entry.name.isdecimal():
            continue
        info = _read_proc_info(entry)
        if info is not None:
            infos[info.pid] = info
    return infos


def _tree_members(
    infos: Mapping[int, _ProcInfo], root_pid: int, process_group: int
) -> dict[int, _ProcInfo]:
    """Find root descendants plus every member of its isolated process group."""

    children: dict[int, list[int]] = {}
    for info in infos.values():
        children.setdefault(info.parent_pid, []).append(info.pid)
    members = {pid: info for pid, info in infos.items() if info.process_group == process_group}
    pending = [root_pid]
    visited = {root_pid}
    while pending:
        parent_pid = pending.pop()
        info = infos.get(parent_pid)
        if info is not None:
            members[parent_pid] = info
        for child_pid in children.get(parent_pid, ()):
            if child_pid not in visited:
                visited.add(child_pid)
                pending.append(child_pid)
    return members


def _read_rollup(proc_root: Path, info: _ProcInfo) -> SmapsRollup | None:
    path = proc_root / str(info.pid) / "smaps_rollup"
    try:
        text = path.read_text(encoding="ascii")
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
        return None
    # Detect PID reuse between stat discovery and the smaps read.
    after = _read_proc_info(proc_root / str(info.pid))
    if after is None or after.start_ticks != info.start_ticks:
        return None
    try:
        return parse_smaps_rollup(text)
    except ValueError:
        return None


def _process_is_live(info: _ProcInfo) -> bool:
    return info.state not in {"Z", "X", "x"}


class ProcessSampler:
    """Start a command in its own process group and sample its Linux tree.

    `mark_phase()` captures a named boundary snapshot, for example
    `steady_before_load`, `postload`, or `post_gc`. Call `wait()` after the
    workload; the sampler terminates any process-group descendants the command
    left behind. The context manager also cleans up if the caller raises.
    """

    def __init__(
        self,
        command: Sequence[str | os.PathLike[str]],
        *,
        env: Mapping[str, str] | None = None,
        cwd: str | os.PathLike[str] | None = None,
        timeout: float | None = None,
        affinity: Sequence[int] | None = None,
        sample_interval_seconds: float | None = 0.015,
        terminate_grace_seconds: float = 0.25,
        proc_root: str | os.PathLike[str] = "/proc",
    ) -> None:
        self.command = _normalize_command(command)
        if timeout is not None and timeout < 0:
            raise ValueError("timeout must be non-negative or None")
        if sample_interval_seconds is not None and sample_interval_seconds <= 0:
            raise ValueError("sample_interval_seconds must be positive or None")
        if terminate_grace_seconds < 0:
            raise ValueError("terminate_grace_seconds must be non-negative")
        self.timeout = timeout
        self.affinity = _normalize_affinity(affinity)
        self.sample_interval_seconds = sample_interval_seconds
        self.terminate_grace_seconds = terminate_grace_seconds
        self.proc_root = Path(proc_root)
        self.cwd = None if cwd is None else os.fspath(cwd)
        self.env = None if env is None else dict(env)
        self._process: subprocess.Popen[bytes] | None = None
        self._stdout_file: IO[bytes] | None = None
        self._stderr_file: IO[bytes] | None = None
        self._started_at: float | None = None
        self._process_group: int | None = None
        self._stop_sampler = threading.Event()
        self._sampler_thread: threading.Thread | None = None
        self._collected = _Collected()
        self._cgroup_scope: CgroupV2MemoryScope | None = None
        self._cgroup_error: str | None = None
        self._last_cgroup_snapshot: CgroupV2MemorySnapshot | None = None
        self._final_cgroup_snapshot: CgroupV2MemorySnapshot | None = None
        self._remaining_pids: tuple[int, ...] = ()
        self._lock = threading.Lock()
        self._finished_result: ProcessResult | None = None

    def __enter__(self) -> ProcessSampler:
        return self.start()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._finished_result is None and self._process is not None:
            self._terminate_process_group()
            self._stop_and_join_sampler()
            self._close_cgroup_scope()
            self._close_output_files()

    def start(self) -> ProcessSampler:
        """Start the command and optional external sampling loop."""

        if self._process is not None:
            raise RuntimeError("process sampler has already been started")
        if not self.proc_root.is_dir():
            raise RuntimeError(f"procfs is not available at {self.proc_root}")

        self._stdout_file = tempfile.TemporaryFile(mode="w+b")
        self._stderr_file = tempfile.TemporaryFile(mode="w+b")
        argv = list(self.command)
        if self.sample_interval_seconds is not None:
            self._cgroup_scope = CgroupV2MemoryScope.detect_and_create(
                proc_root=self.proc_root
            )
        set_affinity = self._make_preexec(self._cgroup_scope)
        self._started_at = time.monotonic()
        try:
            self._process = self._launch(argv, set_affinity)
        except subprocess.SubprocessError as error:
            if self._cgroup_scope is None:
                self._close_output_files()
                raise
            self._cgroup_error = f"cgroup attach unavailable: {error}"
            self._close_cgroup_scope()
            assert self._stdout_file is not None and self._stderr_file is not None
            self._stdout_file.seek(0)
            self._stdout_file.truncate()
            self._stderr_file.seek(0)
            self._stderr_file.truncate()
            try:
                self._process = self._launch(argv, self._make_preexec(None))
            except BaseException:
                self._close_output_files()
                raise
        except BaseException:
            self._close_cgroup_scope()
            self._close_output_files()
            raise
        self._process_group = self._process.pid
        if self.sample_interval_seconds is not None:
            # Capture immediately so short but resident commands have a chance
            # to be observed before their first polling interval elapses.
            self._capture_sample()
            self._sampler_thread = threading.Thread(
                target=self._sample_loop,
                name=f"process-memory-{self._process.pid}",
                daemon=True,
            )
            self._sampler_thread.start()
        return self

    def _make_preexec(
        self, cgroup_scope: CgroupV2MemoryScope | None
    ) -> Callable[[], None] | None:
        if self.affinity is None and cgroup_scope is None:
            return None
        if self.affinity is not None and not hasattr(os, "sched_setaffinity"):
            raise RuntimeError("CPU affinity is supported only on Linux")

        def prepare_child() -> None:
            if self.affinity is not None:
                os.sched_setaffinity(0, self.affinity)
            if cgroup_scope is not None:
                cgroup_scope.attach_pid(os.getpid())

        return prepare_child

    def _launch(
        self, argv: list[str], preexec_fn: Callable[[], None] | None
    ) -> subprocess.Popen[bytes]:
        assert self._stdout_file is not None and self._stderr_file is not None
        return subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=self._stdout_file,
            stderr=self._stderr_file,
            cwd=self.cwd,
            env=self.env,
            preexec_fn=preexec_fn,
            start_new_session=True,
            close_fds=True,
        )

    def _close_cgroup_scope(self) -> None:
        if self._cgroup_scope is None:
            return
        self._cgroup_scope.close()
        if self._cgroup_scope.cleanup_error is not None:
            self._cgroup_error = self._cgroup_scope.cleanup_error
        self._cgroup_scope = None

    @property
    def pid(self) -> int:
        if self._process is None:
            raise RuntimeError("process sampler has not been started")
        return self._process.pid

    def mark_phase(self, name: str) -> MemorySample | None:
        """Record the latest tree state under a caller-defined phase name."""

        if self._process is None:
            raise RuntimeError("process sampler has not been started")
        if not name or not name.strip():
            raise ValueError("phase name must not be empty")
        if self.sample_interval_seconds is None:
            return None
        sample = self._capture_sample()
        if sample is not None:
            with self._lock:
                self._collected.phases[name] = sample
        return sample

    def wait(self) -> ProcessResult:
        """Wait for completion or timeout, clean remaining descendants, return."""

        if self._process is None or self._started_at is None:
            raise RuntimeError("process sampler has not been started")
        if self._finished_result is not None:
            return self._finished_result

        timed_out = False
        try:
            if self.timeout is None:
                self._process.wait()
            else:
                try:
                    self._process.wait(timeout=self.timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
            # Preserve the workload boundary before stopping the sampler or
            # cleaning leaked descendants; cleanup time is not command time.
            if self.sample_interval_seconds is not None:
                self._capture_sample()
            duration = time.monotonic() - self._started_at
        finally:
            self._stop_and_join_sampler()
            self._terminate_process_group()
            self._final_cgroup_snapshot = self._read_cgroup_snapshot()
            self._close_cgroup_scope()

        assert self._stdout_file is not None and self._stderr_file is not None
        self._stdout_file.seek(0)
        self._stderr_file.seek(0)
        stdout = self._stdout_file.read()
        stderr = self._stderr_file.read()
        self._close_output_files()
        memory = None
        if self.sample_interval_seconds is not None:
            with self._lock:
                memory = ProcessMemoryMetrics.from_samples(self._collected.samples)
                memory.phase_samples.update(self._collected.phases)
                memory.sampling_errors.extend(self._collected.errors)
            cgroup_snapshot = self._final_cgroup_snapshot or self._last_cgroup_snapshot
            if cgroup_snapshot is not None:
                memory.cgroup_current_bytes = cgroup_snapshot.current_bytes
                memory.cgroup_peak_bytes = max(
                    memory.cgroup_peak_bytes or 0, cgroup_snapshot.peak_bytes
                )
                memory.cgroup_events = dict(cgroup_snapshot.events)
            memory.cgroup_error = self._cgroup_error
        result = ProcessResult(
            command=self.command,
            returncode=self._process.returncode if self._process.returncode is not None else 0,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            duration_seconds=duration,
            memory=memory,
            cleanup_complete=not self._remaining_pids,
            remaining_pids=self._remaining_pids,
        )
        self._finished_result = result
        return result

    def _sample_loop(self) -> None:
        assert self.sample_interval_seconds is not None
        while not self._stop_sampler.is_set():
            self._capture_sample()
            self._stop_sampler.wait(self.sample_interval_seconds)

    def _capture_sample(self) -> MemorySample | None:
        if self._started_at is None or self._process is None or self._process_group is None:
            return None
        try:
            infos = _proc_table(self.proc_root)
        except RuntimeError as error:
            self._record_error(str(error))
            return None
        members = _tree_members(infos, self._process.pid, self._process_group)
        rollups: dict[int, SmapsRollup] = {}
        for pid, info in members.items():
            with self._lock:
                self._collected.seen[pid] = info.start_ticks
            rollup = _read_rollup(self.proc_root, info)
            if rollup is not None:
                rollups[pid] = rollup
            elif _process_is_live(info):
                current = _read_proc_info(self.proc_root / str(pid))
                if (
                    current is not None
                    and current.start_ticks == info.start_ticks
                    and _process_is_live(current)
                ):
                    self._record_error(f"pid {pid}: smaps_rollup unavailable")
        if not rollups:
            return None
        sample = sum_rollups(rollups, time.monotonic() - self._started_at)
        cgroup_snapshot = self._read_cgroup_snapshot()
        if cgroup_snapshot is not None:
            sample = replace(
                sample,
                cgroup_current_bytes=cgroup_snapshot.current_bytes,
                cgroup_peak_bytes=cgroup_snapshot.peak_bytes,
            )
        with self._lock:
            self._collected.samples.append(sample)
        return sample

    def _read_cgroup_snapshot(self) -> CgroupV2MemorySnapshot | None:
        if self._cgroup_scope is None:
            return None
        try:
            snapshot = self._cgroup_scope.read_snapshot()
        except (OSError, ValueError) as error:
            if self._cgroup_error is None:
                self._cgroup_error = f"cgroup memory counters unavailable: {error}"
            return None
        self._last_cgroup_snapshot = snapshot
        return snapshot

    def _record_error(self, message: str) -> None:
        with self._lock:
            if message not in self._collected.errors:
                self._collected.errors.append(message)

    def _stop_and_join_sampler(self) -> None:
        self._stop_sampler.set()
        if self._sampler_thread is not None:
            self._sampler_thread.join()
            self._sampler_thread = None

    def _terminate_process_group(self) -> None:
        if self._process is None or self._process_group is None:
            return
        self._signal_process_group(signal.SIGTERM)
        self._signal_seen_processes(signal.SIGTERM)
        deadline = time.monotonic() + self.terminate_grace_seconds
        while time.monotonic() < deadline and self._has_live_processes():
            if self._process.poll() is None:
                self._process.poll()
            time.sleep(min(0.02, max(0.0, deadline - time.monotonic())))
        if self._has_live_processes():
            self._signal_process_group(signal.SIGKILL)
            # Kill any previously discovered descendants that escaped their
            # parent's session/process group, guarding against PID reuse.
            self._signal_seen_processes(signal.SIGKILL)
            kill_deadline = time.monotonic() + max(1.0, self.terminate_grace_seconds)
            while time.monotonic() < kill_deadline and self._has_live_processes():
                time.sleep(0.01)
        if self._process.poll() is None:
            try:
                self._process.wait(timeout=max(0.1, self.terminate_grace_seconds))
            except subprocess.TimeoutExpired:
                self._signal_process_group(signal.SIGKILL)
                self._process.wait()
        self._remaining_pids = self._live_process_ids()

    def _signal_process_group(self, sig: signal.Signals) -> None:
        assert self._process_group is not None
        if self._process is not None and self._process.poll() is None:
            try:
                os.killpg(self._process_group, sig)
            except ProcessLookupError:
                pass
            except PermissionError as error:
                self._record_error(
                    f"cannot signal process group {self._process_group}: {error}"
                )
            return
        # Once the root has exited, signal live group members by verified PID
        # and start time. This avoids a late killpg racing with reuse of the
        # former process-group ID.
        try:
            infos = _proc_table(self.proc_root)
        except RuntimeError:
            return
        for info in infos.values():
            if info.process_group != self._process_group or not _process_is_live(info):
                continue
            current = _read_proc_info(self.proc_root / str(info.pid))
            if current is None or current.start_ticks != info.start_ticks:
                continue
            try:
                os.kill(info.pid, sig)
            except (ProcessLookupError, PermissionError):
                continue

    def _signal_seen_processes(self, sig: signal.Signals) -> None:
        with self._lock:
            seen = tuple(self._collected.seen.items())
        for pid, start_ticks in seen:
            info = _read_proc_info(self.proc_root / str(pid))
            if info is None or info.start_ticks != start_ticks or not _process_is_live(info):
                continue
            try:
                os.kill(pid, sig)
            except (ProcessLookupError, PermissionError):
                continue

    def _has_live_processes(self) -> bool:
        return bool(self._live_process_ids())

    def _live_process_ids(self) -> tuple[int, ...]:
        live: set[int] = set()
        try:
            infos = _proc_table(self.proc_root)
        except RuntimeError:
            infos = {}
        if self._process_group is not None:
            live.update(
                info.pid
                for info in infos.values()
                if info.process_group == self._process_group and _process_is_live(info)
            )
        with self._lock:
            seen = tuple(self._collected.seen.items())
        for pid, start_ticks in seen:
            info = _read_proc_info(self.proc_root / str(pid))
            if info is not None and info.start_ticks == start_ticks and _process_is_live(info):
                live.add(pid)
        return tuple(sorted(live))

    def _close_output_files(self) -> None:
        for stream_name in ("_stdout_file", "_stderr_file"):
            stream = getattr(self, stream_name)
            if stream is not None:
                stream.close()
                setattr(self, stream_name, None)


def _normalize_command(command: Sequence[str | os.PathLike[str]]) -> tuple[str, ...]:
    if isinstance(command, (str, bytes)):
        raise TypeError("command must be a sequence of arguments, not a string")
    normalized = tuple(os.fspath(argument) for argument in command)
    if not normalized:
        raise ValueError("command must contain at least one argument")
    if any(not isinstance(argument, str) or "\0" in argument for argument in normalized):
        raise ValueError("command arguments must be NUL-free strings")
    return normalized


def _normalize_affinity(affinity: Sequence[int] | None) -> tuple[int, ...] | None:
    if affinity is None:
        return None
    raw_cpus = tuple(affinity)
    if not raw_cpus or any(type(cpu) is not int or cpu < 0 for cpu in raw_cpus):
        raise ValueError("affinity must contain one or more non-negative CPU ids")
    cpus = tuple(sorted(set(raw_cpus)))
    if not hasattr(os, "sched_getaffinity"):
        raise RuntimeError("CPU affinity is supported only on Linux")
    allowed = os.sched_getaffinity(0)
    unavailable = sorted(set(cpus) - allowed)
    if unavailable:
        raise ValueError(f"requested CPUs are outside the current affinity: {unavailable}")
    return cpus


def run_command(
    command: Sequence[str | os.PathLike[str]],
    *,
    env: Mapping[str, str] | None = None,
    cwd: str | os.PathLike[str] | None = None,
    timeout: float | None = None,
    affinity: Sequence[int] | None = None,
    sample_interval_seconds: float | None = 0.015,
    terminate_grace_seconds: float = 0.25,
) -> ProcessResult:
    """Run any command in a fresh process group and collect its output.

    Supply `sample_interval_seconds=None` for timing passes. Memory passes
    should use an interval near 0.01–0.02 seconds. `env` follows subprocess
    semantics and replaces the inherited environment when provided. Affinity
    is applied in the forked child before target code runs.
    """

    if sys.platform == "darwin" and sample_interval_seconds is None:
        if affinity is not None:
            raise RuntimeError("CPU affinity is not supported by the macOS timing runner")
        return _run_unmonitored(
            command,
            env=env,
            cwd=cwd,
            timeout=timeout,
            terminate_grace_seconds=terminate_grace_seconds,
        )

    sampler = ProcessSampler(
        command,
        env=env,
        cwd=cwd,
        timeout=timeout,
        affinity=affinity,
        sample_interval_seconds=sample_interval_seconds,
        terminate_grace_seconds=terminate_grace_seconds,
    ).start()
    return sampler.wait()


def _run_unmonitored(
    command: Sequence[str | os.PathLike[str]],
    *,
    env: Mapping[str, str] | None,
    cwd: str | os.PathLike[str] | None,
    timeout: float | None,
    terminate_grace_seconds: float,
) -> ProcessResult:
    """Run a timing-only macOS command and clean its process group."""
    normalized = _normalize_command(command)
    if timeout is not None and timeout < 0:
        raise ValueError("timeout must be non-negative or None")
    if terminate_grace_seconds < 0:
        raise ValueError("terminate_grace_seconds must be non-negative")
    ps = shutil.which("ps")
    if ps is None:
        raise RuntimeError("ps is required to verify macOS benchmark process cleanup")

    with (
        tempfile.TemporaryFile(mode="w+b") as stdout_file,
        tempfile.TemporaryFile(mode="w+b") as stderr_file,
    ):
        started = time.monotonic()
        process = subprocess.Popen(
            normalized,
            stdin=subprocess.DEVNULL,
            stdout=stdout_file,
            stderr=stderr_file,
            cwd=None if cwd is None else os.fspath(cwd),
            env=None if env is None else dict(env),
            start_new_session=True,
            close_fds=True,
        )
        timed_out = False
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
        duration = time.monotonic() - started

        def group_pids() -> tuple[int, ...]:
            result = subprocess.run(
                [ps, "-A", "-o", "pid=,pgid=,stat="],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(f"cannot inspect process groups with ps: {result.stderr.strip()}")
            pids = []
            for line in result.stdout.splitlines():
                fields = line.split()
                if len(fields) < 3:
                    continue
                try:
                    pid, process_group = int(fields[0]), int(fields[1])
                except ValueError:
                    continue
                if process_group == process.pid and not fields[2].startswith("Z"):
                    pids.append(pid)
            return tuple(sorted(pids))

        def signal_group(sig: signal.Signals) -> None:
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                pass
            except PermissionError as error:
                raise RuntimeError(f"cannot signal benchmark process group {process.pid}: {error}") from error

        remaining = group_pids()
        if remaining:
            signal_group(signal.SIGTERM)
            deadline = time.monotonic() + terminate_grace_seconds
            while remaining and time.monotonic() < deadline:
                time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
                remaining = group_pids()
            if remaining:
                signal_group(signal.SIGKILL)
                deadline = time.monotonic() + max(1.0, terminate_grace_seconds)
                while remaining and time.monotonic() < deadline:
                    time.sleep(0.01)
                    remaining = group_pids()
        if process.poll() is None:
            signal_group(signal.SIGKILL)
            process.wait()

        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout = stdout_file.read()
        stderr = stderr_file.read()
    return ProcessResult(
        command=normalized,
        returncode=process.returncode if process.returncode is not None else 0,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        duration_seconds=duration,
        memory=None,
        cleanup_complete=not remaining,
        remaining_pids=remaining,
    )
