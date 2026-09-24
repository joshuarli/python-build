"""Linux host, CPU-placement, and installed-interpreter provenance."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
from collections.abc import Mapping, Sequence


_CPU_DIR = re.compile(r"^cpu(\d+)$")
_PYTHON_VERSIONED = re.compile(r"^python\d+\.\d+$")


@dataclass(frozen=True)
class PhysicalCore:
    """One physical core and the online logical CPUs visible to this process."""

    package_id: int | None
    core_id: int
    numa_node: int | None
    logical_cpus: tuple[int, ...]
    allowed_cpus: tuple[int, ...]


@dataclass(frozen=True)
class CpuTopology:
    """CPU topology constrained to the current process's allowed CPU set."""

    allowed_cpus: tuple[int, ...]
    online_cpus: tuple[int, ...]
    cores: tuple[PhysicalCore, ...]
    numa_nodes: tuple[int, ...]

    @property
    def physical_core_count(self) -> int:
        return len(self.cores)


@dataclass(frozen=True)
class InstallSizeMetrics:
    """Unique installed regular-file sizes for a relocatable Python tree."""

    root: str
    total_installed_bytes: int
    interpreter_executable_bytes: int | None
    interpreter_executable: str | None
    libpython_bytes: int
    extension_module_bytes: int
    stdlib_source_bytes: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def parse_cpu_list(value: str) -> tuple[int, ...]:
    """Parse Linux cpulist syntax such as `0-3,8,10-11`."""

    result: set[int] = set()
    for item in value.strip().split(","):
        item = item.strip()
        if not item:
            continue
        if "-" in item:
            low_text, high_text = item.split("-", maxsplit=1)
            low, high = int(low_text), int(high_text)
            if low < 0 or high < low:
                raise ValueError(f"invalid CPU range {item!r}")
            result.update(range(low, high + 1))
        else:
            cpu = int(item)
            if cpu < 0:
                raise ValueError(f"invalid CPU id {item!r}")
            result.add(cpu)
    return tuple(sorted(result))


def discover_cpu_topology(
    *,
    sysfs_root: str | os.PathLike[str] = "/sys/devices/system/cpu",
    node_root: str | os.PathLike[str] = "/sys/devices/system/node",
    allowed_cpus: Sequence[int] | None = None,
) -> CpuTopology:
    """Discover physical cores, SMT siblings, and NUMA nodes on Linux.

    `allowed_cpus` may be supplied for deterministic tests. Otherwise the
    process affinity mask is used, so containers and cpusets are respected.
    Missing sysfs topology fields degrade to one core per visible logical CPU.
    """

    root = Path(sysfs_root)
    nodes_path = Path(node_root)
    if allowed_cpus is None:
        if hasattr(os, "sched_getaffinity"):
            allowed = tuple(sorted(os.sched_getaffinity(0)))
        else:
            allowed = tuple(range(os.cpu_count() or 1))
    else:
        raw_allowed = tuple(allowed_cpus)
        if any(type(cpu) is not int or cpu < 0 for cpu in raw_allowed):
            raise ValueError("allowed_cpus must contain non-negative integers")
        allowed = tuple(sorted(set(raw_allowed)))
    if not allowed:
        raise RuntimeError("the current CPU affinity mask is empty")

    try:
        root_entries = tuple(root.iterdir()) if root.is_dir() else ()
    except OSError:
        root_entries = ()
    cpu_directories = {
        int(match.group(1)): path
        for path in root_entries
        if (match := _CPU_DIR.match(path.name)) is not None and path.is_dir()
    }
    online_file = root / "online"
    try:
        online = set(parse_cpu_list(online_file.read_text(encoding="ascii")))
    except (OSError, ValueError):
        online = set(cpu_directories) if cpu_directories else set(allowed)
    online &= set(cpu_directories) if cpu_directories else set(online)
    visible = tuple(cpu for cpu in allowed if cpu in online)
    if not visible:
        # Some synthetic sysfs trees expose the online mask but no cpuN
        # directories. Treat the caller's allowed set as singleton cores.
        visible = allowed

    node_cpu_lists: dict[int, set[int]] = {}
    if nodes_path.is_dir():
        for node_path in nodes_path.glob("node[0-9]*"):
            match = re.match(r"node(\d+)$", node_path.name)
            if match is None:
                continue
            try:
                node_cpu_lists[int(match.group(1))] = set(
                    parse_cpu_list((node_path / "cpulist").read_text(encoding="ascii"))
                )
            except (OSError, ValueError):
                continue

    def read_integer(path: Path) -> int | None:
        try:
            return int(path.read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            return None

    cpu_identity: dict[int, tuple[int | None, int, int | None]] = {}
    for cpu in visible:
        cpu_path = cpu_directories.get(cpu)
        package_id = read_integer(cpu_path / "topology" / "physical_package_id") if cpu_path else None
        core_id = read_integer(cpu_path / "topology" / "core_id") if cpu_path else None
        if core_id is None:
            core_id = cpu
        numa_node: int | None = None
        if cpu_path is not None:
            node_matches = [
                int(match.group(1))
                for child in cpu_path.glob("node[0-9]*")
                if (match := re.match(r"node(\d+)$", child.name)) is not None
            ]
            if node_matches:
                numa_node = min(node_matches)
        if numa_node is None:
            memberships = [node for node, cpus in node_cpu_lists.items() if cpu in cpus]
            if memberships:
                numa_node = min(memberships)
        cpu_identity[cpu] = (package_id, core_id, numa_node)

    grouped: dict[tuple[int | None, int], list[int]] = {}
    group_nodes: dict[tuple[int | None, int], int | None] = {}
    for cpu, (package_id, core_id, numa_node) in cpu_identity.items():
        key = package_id, core_id
        grouped.setdefault(key, []).append(cpu)
        group_nodes[key] = numa_node

    cores: list[PhysicalCore] = []
    for (package_id, core_id), logical in grouped.items():
        siblings: set[int] = set(logical)
        cpu_path = cpu_directories.get(logical[0])
        if cpu_path is not None:
            siblings_file = cpu_path / "topology" / "thread_siblings_list"
            try:
                siblings.update(parse_cpu_list(siblings_file.read_text(encoding="ascii")))
            except (OSError, ValueError):
                pass
        online_siblings = tuple(sorted(cpu for cpu in siblings if cpu in online))
        allowed_siblings = tuple(cpu for cpu in online_siblings if cpu in allowed)
        # The core itself is visible by construction. `siblings` may mention
        # disallowed threads; those are represented but never selected.
        if not allowed_siblings:
            allowed_siblings = tuple(sorted(logical))
        cores.append(
            PhysicalCore(
                package_id=package_id,
                core_id=core_id,
                numa_node=group_nodes[(package_id, core_id)],
                logical_cpus=online_siblings,
                allowed_cpus=allowed_siblings,
            )
        )

    ordered_cores = _interleave_core_groups(cores)
    numa_nodes = tuple(
        sorted({core.numa_node for core in ordered_cores if core.numa_node is not None})
    )
    return CpuTopology(
        allowed_cpus=visible,
        online_cpus=tuple(sorted(online)),
        cores=tuple(ordered_cores),
        numa_nodes=numa_nodes,
    )


def _interleave_core_groups(cores: Sequence[PhysicalCore]) -> list[PhysicalCore]:
    """Order physical cores evenly across NUMA nodes and packages."""

    groups: dict[tuple[int | None, int | None], list[PhysicalCore]] = {}
    for core in cores:
        groups.setdefault((core.numa_node, core.package_id), []).append(core)
    for group in groups.values():
        group.sort(key=lambda core: (core.core_id, min(core.allowed_cpus)))
    keys = sorted(
        groups,
        key=lambda key: (
            key[0] is None,
            -1 if key[0] is None else key[0],
            key[1] is None,
            -1 if key[1] is None else key[1],
        ),
    )
    ordered: list[PhysicalCore] = []
    depth = 0
    while True:
        added = False
        for key in keys:
            group = groups[key]
            if depth < len(group):
                ordered.append(group[depth])
                added = True
        if not added:
            return ordered
        depth += 1


def select_physical_cpus(
    topology: CpuTopology, count: int | None = None, *, offset: int = 0
) -> tuple[int, ...]:
    """Select one allowed hardware thread from each selected physical core."""

    if offset < 0:
        raise ValueError("offset must be non-negative")
    available = [min(core.allowed_cpus) for core in topology.cores]
    if count is None:
        count = max(0, len(available) - offset)
    if count < 0:
        raise ValueError("count must be non-negative or None")
    chosen = available[offset : offset + count]
    if len(chosen) != count:
        raise ValueError(
            f"requested {count} physical cores starting at {offset}, "
            f"but only {max(0, len(available) - offset)} are available"
        )
    return tuple(chosen)


def split_physical_cores(
    topology: CpuTopology, groups: int
) -> tuple[tuple[int, ...], ...]:
    """Split physical cores into disjoint, topology-balanced affinity groups.

    The interleaved core order spreads each group across NUMA nodes and CPU
    packages when available. Alternating which side receives each group across
    paired rounds further reduces placement bias.
    """

    if groups < 1:
        raise ValueError("groups must be positive")
    cpus = [min(core.allowed_cpus) for core in topology.cores]
    if groups > len(cpus):
        raise ValueError(f"cannot split {len(cpus)} physical cores into {groups} groups")
    result: list[list[int]] = [[] for _ in range(groups)]
    for index, cpu in enumerate(cpus):
        result[index % groups].append(cpu)
    return tuple(tuple(group) for group in result)


def collect_host_provenance(
    *,
    selected_affinity: Sequence[int] | None = None,
    environment: Mapping[str, str] | None = None,
    sysfs_root: str | os.PathLike[str] = "/sys/devices/system/cpu",
    node_root: str | os.PathLike[str] = "/sys/devices/system/node",
    proc_root: str | os.PathLike[str] = "/proc",
) -> dict[str, object]:
    """Collect host and Python-environment details without changing host state."""

    proc = Path(proc_root)
    topology = discover_cpu_topology(
        sysfs_root=sysfs_root,
        node_root=node_root,
    )
    env = os.environ if environment is None else environment
    cpu_info = _read_cpu_info(proc / "cpuinfo")
    memory_info = _read_meminfo(proc / "meminfo")
    cpu_root = Path(sysfs_root)
    governor_paths = sorted(
        set(cpu_root.glob("cpu*/cpufreq/scaling_governor"))
        | set(cpu_root.glob("cpufreq/policy*/scaling_governor"))
    )
    governor_values = sorted(
        {
            value
            for path in governor_paths
            if (value := _read_text(path)) is not None
        }
    )
    boost_state = _boost_state(Path(sysfs_root))
    microcode = cpu_info.get("microcode")
    container = _container_provenance(proc)
    try:
        load_average = list(os.getloadavg())
    except OSError:
        load_average = None

    python_environment = {
        name: env.get(name)
        for name in (
            "PYTHONHASHSEED",
            "PYTHONMALLOC",
            "PYTHONPATH",
            "PYTHONNOUSERSITE",
            "PYTHONDONTWRITEBYTECODE",
        )
    }
    return {
        "system": platform.system(),
        "kernel_release": platform.release(),
        "machine": platform.machine(),
        "cpu_model": cpu_info.get("model name") or cpu_info.get("hardware") or cpu_info.get("processor"),
        "microcode": microcode,
        "logical_cpu_count": len(topology.allowed_cpus),
        "physical_core_count": topology.physical_core_count,
        "cpu_topology": {
            "allowed_cpus": list(topology.allowed_cpus),
            "online_cpus": list(topology.online_cpus),
            "numa_nodes": list(topology.numa_nodes),
            "cores": [
                {
                    "package_id": core.package_id,
                    "core_id": core.core_id,
                    "numa_node": core.numa_node,
                    "logical_cpus": list(core.logical_cpus),
                    "allowed_cpus": list(core.allowed_cpus),
                }
                for core in topology.cores
            ],
        },
        "cpu_affinity": {
            "allowed_cpus": list(topology.allowed_cpus),
            "selected_cpus": None if selected_affinity is None else list(selected_affinity),
        },
        "numa_topology": {
            "nodes": list(topology.numa_nodes),
            "core_counts": {
                str(node): sum(core.numa_node == node for core in topology.cores)
                for node in topology.numa_nodes
            },
        },
        "cpu_governors": governor_values,
        "cpu_boost_state": boost_state,
        "load_average": load_average,
        "memory_total_bytes": memory_info.get("MemTotal"),
        "memory_available_bytes": memory_info.get("MemAvailable"),
        "swap_total_bytes": memory_info.get("SwapTotal"),
        "swap_free_bytes": memory_info.get("SwapFree"),
        "container": container,
        "python_environment": python_environment,
    }


def _read_cpu_info(path: Path) -> dict[str, str]:
    keys = {"model name", "hardware", "processor", "microcode"}
    result: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if ":" not in line:
                continue
            key, value = (part.strip() for part in line.split(":", maxsplit=1))
            if key in keys and value:
                result.setdefault(key, value)
    except OSError:
        pass
    return result


def _read_meminfo(path: Path) -> dict[str, int]:
    result: dict[str, int] = {}
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except OSError:
        return result
    wanted = {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}
    for line in lines:
        key, separator, raw = line.partition(":")
        if not separator or key not in wanted:
            continue
        fields = raw.split()
        if not fields:
            continue
        try:
            value = int(fields[0])
        except ValueError:
            continue
        # Linux meminfo values are normally kB. Treat an absent unit as bytes
        # for compatibility with simple fixtures.
        result[key] = value * (1024 if len(fields) > 1 and fields[1] == "kB" else 1)
    return result


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="ascii").strip()
    except OSError:
        return None


def _boost_state(cpu_root: Path) -> dict[str, str | None]:
    return {
        "generic_boost": _read_text(cpu_root / "cpufreq" / "boost"),
        "intel_no_turbo": _read_text(cpu_root / "intel_pstate" / "no_turbo"),
        "amd_pstate_status": _read_text(cpu_root / "amd_pstate" / "status"),
    }


def _container_provenance(proc_root: Path) -> dict[str, object]:
    cgroup = _read_text(proc_root / "1" / "cgroup") or ""
    mountinfo = _read_text(proc_root / "1" / "mountinfo") or ""
    current_cgroup = _read_text(proc_root / "self" / "cgroup") or ""
    evidence = "\n".join((cgroup, current_cgroup, mountinfo)).lower()
    runtimes = [
        runtime
        for marker, runtime in (
            ("docker", "docker"),
            ("containerd", "containerd"),
            ("kubepods", "kubernetes"),
            ("podman", "podman"),
            ("libpod", "podman"),
            ("lxc", "lxc"),
        )
        if marker in evidence
    ]
    cli_versions: dict[str, str] = {}
    for executable in ("docker", "podman"):
        path = shutil.which(executable)
        if path is None:
            continue
        try:
            completed = subprocess.run(
                [path, "--version"],
                capture_output=True,
                text=True,
                timeout=1.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        version = completed.stdout.strip() or completed.stderr.strip()
        if completed.returncode == 0 and version:
            cli_versions[executable] = version
    return {
        "detected_runtimes": sorted(set(runtimes)),
        "available_cli_versions": cli_versions,
        "cgroup_excerpt": current_cgroup[:1000] or None,
    }


def measure_install_size(
    root: str | os.PathLike[str],
    *,
    executable: str | os.PathLike[str] | None = None,
) -> InstallSizeMetrics:
    """Measure installed files and Python binary/source subsets in bytes.

    The total is the sum of unique regular-file inode sizes beneath `root`;
    symlink entries do not add bytes. Extension modules and stdlib source are
    classified beneath `lib/pythonX.Y`, with site/dist-packages excluded from
    the stdlib `.py` source total.
    """

    install_root = Path(root).resolve()
    if not install_root.is_dir():
        raise ValueError(f"installation root is not a directory: {install_root}")
    files: list[Path] = []
    for directory, dirnames, filenames in os.walk(install_root, followlinks=False):
        dirnames[:] = [
            name
            for name in dirnames
            if not (Path(directory) / name).is_symlink()
        ]
        for filename in filenames:
            path = Path(directory) / filename
            try:
                if stat.S_ISREG(path.lstat().st_mode):
                    files.append(path)
            except OSError:
                continue

    total = _unique_inode_size(files)
    libpython_files = [
        path
        for path in files
        if path.name.startswith("libpython")
        and path.parent.name in {"lib", "lib64"}
    ]
    extension_files: list[Path] = []
    stdlib_sources: list[Path] = []
    for path in files:
        try:
            relative = path.relative_to(install_root)
        except ValueError:
            continue
        parts = relative.parts
        python_library_index = next(
            (
                index
                for index in range(len(parts) - 1)
                if parts[index] in {"lib", "lib64"}
                and parts[index + 1].startswith("python")
            ),
            None,
        )
        if python_library_index is None:
            continue
        python_library_parts = parts[python_library_index + 1 :]
        if len(python_library_parts) < 2:
            continue
        if any(part in {"site-packages", "dist-packages"} for part in python_library_parts):
            if path.name.endswith(".so") or ".so." in path.name:
                extension_files.append(path)
            continue
        if path.name.endswith(".so") or ".so." in path.name:
            extension_files.append(path)
        if path.suffix == ".py":
            stdlib_sources.append(path)

    executable_path = _find_interpreter(install_root, executable)
    try:
        executable_size = executable_path.stat().st_size if executable_path is not None else None
    except OSError:
        executable_size = None
    return InstallSizeMetrics(
        root=str(install_root),
        total_installed_bytes=total,
        interpreter_executable_bytes=executable_size,
        interpreter_executable=None if executable_path is None else str(executable_path),
        libpython_bytes=_unique_inode_size(libpython_files),
        extension_module_bytes=_unique_inode_size(extension_files),
        stdlib_source_bytes=_unique_inode_size(stdlib_sources),
    )


def _unique_inode_size(paths: Sequence[Path]) -> int:
    total = 0
    seen: set[tuple[int, int]] = set()
    for path in paths:
        try:
            info = path.stat()
        except OSError:
            continue
        key = info.st_dev, info.st_ino
        if key in seen:
            continue
        seen.add(key)
        total += info.st_size
    return total


def _find_interpreter(
    root: Path, executable: str | os.PathLike[str] | None
) -> Path | None:
    if executable is not None:
        path = Path(executable)
        candidate = path if path.is_absolute() else root / path
        return candidate if candidate.exists() else None
    bin_path = root / "bin"
    if not bin_path.is_dir():
        return None
    candidates = [
        path
        for path in bin_path.glob("python*")
        if path.is_file() and (_PYTHON_VERSIONED.match(path.name) or path.name in {"python", "python3"})
    ]
    candidates.sort(
        key=lambda path: (
            not bool(_PYTHON_VERSIONED.match(path.name)),
            path.name,
        )
    )
    return candidates[0] if candidates else None
