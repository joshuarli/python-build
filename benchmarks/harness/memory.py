"""Linux process-memory measurements used by benchmark memory passes.

`smaps_rollup` is read by the controller, outside the interpreter under test.
All public sizes are bytes; procfs labels its values in KiB (`kB`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from typing import Mapping


class SmapsRollupError(ValueError):
    """A `/proc/<pid>/smaps_rollup` value is missing or malformed."""


_ENTRY = re.compile(r"^([A-Za-z_]+):\s+(\d+)\s+(\S+)\s*$")
_REQUIRED = ("Rss", "Pss", "Private_Clean", "Private_Dirty", "Swap")
_OPTIONAL = (
    "Private_Hugetlb",
    "Shared_Clean",
    "Shared_Dirty",
    "Shared_Hugetlb",
)


@dataclass(frozen=True)
class SmapsRollup:
    """Memory totals parsed from one process's `smaps_rollup`, in bytes."""

    rss_bytes: int
    pss_bytes: int
    private_clean_bytes: int
    private_dirty_bytes: int
    private_hugetlb_bytes: int = 0
    shared_clean_bytes: int = 0
    shared_dirty_bytes: int = 0
    shared_hugetlb_bytes: int = 0
    swap_bytes: int = 0

    @property
    def private_bytes(self) -> int:
        """Return USS-like private resident memory, including hugetlb pages."""

        return (
            self.private_clean_bytes
            + self.private_dirty_bytes
            + self.private_hugetlb_bytes
        )


def parse_smaps_rollup(text: str) -> SmapsRollup:
    """Parse Linux `smaps_rollup` text into byte-valued memory fields.

    Unknown kernel fields are ignored. Core fields are required so an
    incomplete or unexpected procfs response cannot quietly become zero.
    Hugetlb and shared fields are zero when an older kernel omits them.
    """

    values: dict[str, int] = {}
    recognized = {*_REQUIRED, *_OPTIONAL}
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = _ENTRY.match(line)
        if match is None:
            name = line.partition(":")[0].strip()
            if name in recognized:
                raise SmapsRollupError(
                    f"line {line_number}: malformed smaps_rollup field {name}"
                )
            # The header line and unrelated kernel extensions are not memory
            # counters.
            continue
        name, raw_value, unit = match.groups()
        if name not in recognized:
            continue
        if unit != "kB":
            raise SmapsRollupError(
                f"line {line_number}: {name} uses unsupported unit {unit!r}"
            )
        if name in values:
            raise SmapsRollupError(f"line {line_number}: duplicate field {name}")
        values[name] = int(raw_value) * 1024

    missing = [name for name in _REQUIRED if name not in values]
    if missing:
        raise SmapsRollupError(
            "missing required smaps_rollup field(s): " + ", ".join(missing)
        )

    def value(name: str) -> int:
        return values.get(name, 0)

    return SmapsRollup(
        rss_bytes=value("Rss"),
        pss_bytes=value("Pss"),
        private_clean_bytes=value("Private_Clean"),
        private_dirty_bytes=value("Private_Dirty"),
        private_hugetlb_bytes=value("Private_Hugetlb"),
        shared_clean_bytes=value("Shared_Clean"),
        shared_dirty_bytes=value("Shared_Dirty"),
        shared_hugetlb_bytes=value("Shared_Hugetlb"),
        swap_bytes=value("Swap"),
    )


@dataclass(frozen=True)
class MemorySample:
    """One total across the sampled workload process tree."""

    elapsed_seconds: float
    rss_bytes: int
    pss_bytes: int | None
    private_bytes: int | None
    swap_bytes: int | None
    process_count: int
    pids: tuple[int, ...] = ()
    cgroup_current_bytes: int | None = None
    cgroup_peak_bytes: int | None = None


@dataclass
class ProcessMemoryMetrics:
    """Peak and boundary memory values plus the raw process-tree timeline."""

    peak_rss_bytes: int = 0
    peak_pss_bytes: int | None = None
    peak_private_bytes: int | None = None
    peak_swap_bytes: int | None = None
    peak_process_count: int = 0
    first: MemorySample | None = None
    last: MemorySample | None = None
    samples: list[MemorySample] = field(default_factory=list)
    phase_samples: dict[str, MemorySample] = field(default_factory=dict)
    sampling_errors: list[str] = field(default_factory=list)
    cgroup_current_bytes: int | None = None
    cgroup_peak_bytes: int | None = None
    cgroup_events: dict[str, int] | None = None
    cgroup_error: str | None = None
    # macOS kernel lifetime peaks are per root process (or its reaped family),
    # not a simultaneous process-tree total. Keep them distinct from samples.
    root_kernel_peak_rss_bytes: int | None = None
    root_kernel_peak_phys_footprint_bytes: int | None = None

    @classmethod
    def from_samples(cls, samples: list[MemorySample]) -> ProcessMemoryMetrics:
        """Build peak and boundary metrics from raw samples."""

        if not samples:
            return cls()
        ordered = sorted(samples, key=lambda sample: sample.elapsed_seconds)
        return cls(
            peak_rss_bytes=max(sample.rss_bytes for sample in ordered),
            peak_pss_bytes=max((sample.pss_bytes for sample in ordered if sample.pss_bytes is not None), default=None),
            peak_private_bytes=max((sample.private_bytes for sample in ordered if sample.private_bytes is not None), default=None),
            peak_swap_bytes=max((sample.swap_bytes for sample in ordered if sample.swap_bytes is not None), default=None),
            peak_process_count=max(sample.process_count for sample in ordered),
            first=ordered[0],
            last=ordered[-1],
            samples=ordered,
            cgroup_current_bytes=ordered[-1].cgroup_current_bytes,
            cgroup_peak_bytes=max(
                (sample.cgroup_peak_bytes for sample in ordered if sample.cgroup_peak_bytes is not None),
                default=None,
            ),
        )

    @property
    def steady_pss_bytes(self) -> int | None:
        """Return PSS only for an explicitly marked steady-state boundary.

        The final sample of a short-lived batch process can occur during
        teardown and is not evidence of steady memory use.
        """

        sample = self.phase_samples.get("steady")
        return None if sample is None else sample.pss_bytes

    @property
    def steady_rss_bytes(self) -> int | None:
        """Return resident bytes only at an explicit steady-state boundary."""
        sample = self.phase_samples.get("steady")
        return None if sample is None else sample.rss_bytes

    @property
    def postload_pss_bytes(self) -> int | None:
        """Return a caller-marked post-load PSS sample when one was recorded."""

        sample = self.phase_samples.get("postload")
        return None if sample is None else sample.pss_bytes

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-ready representation with explicit byte units."""

        def sample_dict(sample: MemorySample | None) -> dict[str, object] | None:
            if sample is None:
                return None
            return {
                "elapsed_seconds": sample.elapsed_seconds,
                "rss_bytes": sample.rss_bytes,
                "pss_bytes": sample.pss_bytes,
                "private_bytes": sample.private_bytes,
                "swap_bytes": sample.swap_bytes,
                "process_count": sample.process_count,
                "pids": list(sample.pids),
                "cgroup_current_bytes": sample.cgroup_current_bytes,
                "cgroup_peak_bytes": sample.cgroup_peak_bytes,
            }

        return {
            "peak_rss_bytes": self.peak_rss_bytes if self.samples or self.root_kernel_peak_rss_bytes is not None else None,
            "peak_pss_bytes": self.peak_pss_bytes if self.samples else None,
            "peak_private_bytes": self.peak_private_bytes if self.samples else None,
            "peak_swap_bytes": self.peak_swap_bytes if self.samples else None,
            "peak_process_count": self.peak_process_count if self.samples else None,
            "first": sample_dict(self.first),
            "last": sample_dict(self.last),
            "steady_pss_bytes": self.steady_pss_bytes,
            "steady_rss_bytes": self.steady_rss_bytes,
            "postload_pss_bytes": self.postload_pss_bytes,
            "samples": [sample_dict(sample) for sample in self.samples],
            "phase_samples": {
                name: sample_dict(sample)
                for name, sample in self.phase_samples.items()
            },
            "sampling_errors": list(self.sampling_errors),
            "cgroup_current_bytes": self.cgroup_current_bytes,
            "cgroup_peak_bytes": self.cgroup_peak_bytes,
            "cgroup_events": self.cgroup_events,
            "cgroup_error": self.cgroup_error,
            "root_kernel_peak_rss_bytes": self.root_kernel_peak_rss_bytes,
            "root_kernel_peak_phys_footprint_bytes": self.root_kernel_peak_phys_footprint_bytes,
            "peak_rss_coverage": (
                "sampled tree and kernel root-family lifetime peak; tree peak is a lower bound"
                if self.root_kernel_peak_rss_bytes is not None
                else "sampled process tree; short-lived children may be missed"
                if self.samples else "unavailable: no process samples or kernel peak"
            ),
        }


def sum_rollups(rollups: Mapping[int, SmapsRollup], elapsed_seconds: float) -> MemorySample:
    """Sum per-process rollups into one tree-level memory sample."""

    return MemorySample(
        elapsed_seconds=elapsed_seconds,
        rss_bytes=sum(item.rss_bytes for item in rollups.values()),
        pss_bytes=sum(item.pss_bytes for item in rollups.values()),
        private_bytes=sum(item.private_bytes for item in rollups.values()),
        swap_bytes=sum(item.swap_bytes for item in rollups.values()),
        process_count=len(rollups),
        pids=tuple(sorted(rollups)),
    )


@dataclass(frozen=True)
class CgroupV2MemorySnapshot:
    """Secondary memory counters from one isolated cgroup v2 subtree."""

    current_bytes: int
    peak_bytes: int
    events: dict[str, int]


def parse_cgroup_memory_events(text: str) -> dict[str, int]:
    """Parse `memory.events` counters, preserving kernel-added event names."""

    events: dict[str, int] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        fields = line.split()
        if len(fields) != 2 or not fields[1].isdecimal():
            raise ValueError(f"invalid memory.events line {line_number}: {line!r}")
        name, raw_count = fields
        if name in events:
            raise ValueError(f"duplicate memory.events counter {name!r}")
        events[name] = int(raw_count)
    return events


def _read_cgroup_value(path: Path) -> int:
    raw = path.read_text(encoding="ascii").strip()
    if not raw.isdecimal():
        raise ValueError(f"invalid non-negative integer in {path}: {raw!r}")
    return int(raw)


class CgroupV2MemoryScope:
    """A fresh delegated cgroup used only during one process memory pass."""

    REQUIRED_FILES = ("cgroup.procs", "memory.current", "memory.peak", "memory.events")

    def __init__(self, path: Path):
        self.path = path
        self._closed = False
        self.cleanup_error: str | None = None

    @classmethod
    def detect_and_create(
        cls, *, proc_root: str | os.PathLike[str] = "/proc"
    ) -> CgroupV2MemoryScope | None:
        """Create a private child only when the current cgroup delegated memory."""

        parent = _current_cgroup_v2_directory(Path(proc_root))
        if parent is None:
            return None
        return cls.create_under(parent)

    @classmethod
    def create_under(cls, parent: str | os.PathLike[str]) -> CgroupV2MemoryScope | None:
        """Create a fresh child beneath an already resolved v2 cgroup parent.

        The memory controller must already be enabled for descendants. This
        method never changes `cgroup.subtree_control` or any host controller.
        """

        parent_path = Path(parent)
        try:
            controllers = set((parent_path / "cgroup.controllers").read_text(encoding="ascii").split())
            enabled = {
                item.lstrip("+")
                for item in (parent_path / "cgroup.subtree_control").read_text(encoding="ascii").split()
            }
        except OSError:
            return None
        if "memory" not in controllers or "memory" not in enabled:
            return None
        try:
            child_path = _create_child_cgroup(parent_path)
        except OSError:
            return None
        try:
            if not all((child_path / name).is_file() for name in cls.REQUIRED_FILES):
                _remove_cgroup_directory(child_path)
                return None
            # Prove that the empty scope's files are readable and that the
            # process membership file can be opened before launching anything.
            scope = cls(child_path)
            scope.read_snapshot()
            if not os.access(child_path / "cgroup.procs", os.W_OK):
                scope.close()
                return None
            return scope
        except (OSError, ValueError):
            _remove_cgroup_directory(child_path)
            return None

    @property
    def procs_file(self) -> Path:
        return self.path / "cgroup.procs"

    def attach_pid(self, pid: int) -> None:
        """Move one newly forked process into this scope before it execs."""

        if pid <= 0:
            raise ValueError("pid must be positive")
        fd = os.open(self.procs_file, os.O_WRONLY | os.O_CLOEXEC)
        try:
            os.write(fd, f"{pid}\n".encode("ascii"))
        finally:
            os.close(fd)

    def read_snapshot(self) -> CgroupV2MemorySnapshot:
        """Read current/peak bytes and the current memory event counters."""

        return CgroupV2MemorySnapshot(
            current_bytes=_read_cgroup_value(self.path / "memory.current"),
            peak_bytes=_read_cgroup_value(self.path / "memory.peak"),
            events=parse_cgroup_memory_events(
                (self.path / "memory.events").read_text(encoding="ascii")
            ),
        )

    def close(self) -> None:
        """Remove the empty per-command subtree; never recursively delete."""

        if self._closed:
            return
        try:
            _remove_cgroup_directory(self.path)
        except OSError as error:
            self.cleanup_error = str(error)
        else:
            self._closed = True


def _create_child_cgroup(parent: Path) -> Path:
    return Path(tempfile.mkdtemp(prefix="python-build-bench-", dir=parent))


def _remove_cgroup_directory(path: Path) -> None:
    os.rmdir(path)


def _unescape_mountinfo_path(value: str) -> str:
    return re.sub(
        r"\\([0-7]{3})",
        lambda match: chr(int(match.group(1), 8)),
        value,
    )


def _current_cgroup_v2_directory(proc_root: Path) -> Path | None:
    """Map the process's unified cgroup path through a cgroup2 mount record."""

    try:
        cgroup_text = (proc_root / "self" / "cgroup").read_text(encoding="utf-8")
        mountinfo_text = (proc_root / "self" / "mountinfo").read_text(encoding="utf-8")
    except OSError:
        return None
    current_path: PurePosixPath | None = None
    for line in cgroup_text.splitlines():
        hierarchy, separator, rest = line.partition(":")
        controllers, separator2, cgroup_path = rest.partition(":")
        if separator and separator2 and hierarchy == "0" and not controllers:
            current_path = PurePosixPath(cgroup_path)
            break
    if current_path is None or not current_path.is_absolute():
        return None

    for line in mountinfo_text.splitlines():
        left, separator, right = line.partition(" - ")
        if not separator:
            continue
        filesystem = right.split()
        fields = left.split()
        if len(filesystem) < 1 or filesystem[0] != "cgroup2" or len(fields) < 5:
            continue
        mount_root = PurePosixPath(_unescape_mountinfo_path(fields[3]))
        mountpoint = Path(_unescape_mountinfo_path(fields[4]))
        if not mount_root.is_absolute() or not mountpoint.is_absolute():
            continue
        if mount_root == PurePosixPath("/"):
            suffix = current_path.relative_to("/")
        elif current_path == mount_root:
            suffix = PurePosixPath()
        elif current_path.is_relative_to(mount_root):
            suffix = current_path.relative_to(mount_root)
        else:
            # Namespace-relative `/` can map to the mount root. Other paths
            # cannot be mapped safely without guessing host cgroup ancestry.
            if current_path == PurePosixPath("/"):
                suffix = PurePosixPath()
            else:
                continue
        candidate = mountpoint.joinpath(*suffix.parts)
        try:
            candidate.resolve(strict=True).relative_to(mountpoint.resolve(strict=True))
        except (OSError, ValueError):
            continue
        if candidate.is_dir():
            return candidate
    return None
