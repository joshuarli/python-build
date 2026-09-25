#!/usr/bin/env python3
"""CPython benchmark controller for Linux amd64 and native Apple Silicon.

Linux `run` enters the generic benchmark image with networking disabled.
Native macOS runs are local with optional external RSS observation.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.harness.runner import run_workload
from benchmarks.workloads.registry import Workload, select_workloads

BENCH = Path(__file__).resolve().parent
IMAGE = "python-build-bench:local"


def _requires_macro_inputs(workloads: list[Workload]) -> bool:
    """Install locked wheels only for selected workloads that consume them."""
    return any(workload.packages or workload.name == "pip_install_wheelhouse"
               for workload in workloads)


def _macos_django_inputs(workloads: list[Workload]) -> bool:
    """The experimental macOS lock covers Django workloads only."""
    packaged = [workload for workload in workloads if workload.packages]
    unsupported = [workload.name for workload in packaged if workload.packages != ("Django",)]
    if unsupported:
        raise ValueError(f"macOS CPython 3.16 has no approved inputs for: {', '.join(unsupported)}")
    return bool(packaged)


def _used_input_provenance(lock: Any, groups: set[str]) -> list[dict[str, Any]]:
    """Describe only input groups actually installed for this measurement."""
    return lock.provenance(groups) if lock is not None and groups else []


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _identity(python: Path, label: str, source: str, kind: str) -> dict[str, Any]:
    code = (
        "import json,platform,sys,sysconfig; "
        "print(json.dumps({'version':list(sys.version_info[:3]),"
        "'implementation':platform.python_implementation(),"
        "'abi':sysconfig.get_config_var('SOABI'),"
        "'compiler':platform.python_compiler(),"
        "'config_args':sysconfig.get_config_var('CONFIG_ARGS'),"
        "'platform':sysconfig.get_platform()}))"
    )
    completed = subprocess.run([str(python), "-c", code], capture_output=True, text=True, timeout=30, check=True)
    data = json.loads(completed.stdout)
    data.update({"label": label, "kind": kind, "source": source, "executable": str(python),
                 "executable_sha256": _sha256(python.resolve())})
    return data


def _extract_interpreter(descriptor: str, destination: Path) -> tuple[Path, str]:
    if descriptor == "image-python":
        return Path("/usr/bin/python3"), "benchmark image Python"
    path = Path(descriptor).resolve()
    if path.is_file() and path.suffixes[-2:] == [".tar", ".gz"]:
        destination.mkdir(parents=True, exist_ok=True)
        with tarfile.open(path, "r:gz") as archive:
            archive.extractall(destination, filter="data")
        candidates = sorted(destination.glob("**/bin/python3.*"))
        candidates = [candidate for candidate in candidates if candidate.is_file() and os.access(candidate, os.X_OK)]
        if not candidates:
            raise ValueError(f"no Python executable in {path}")
        return candidates[0], f"artifact {path.name} sha256:{_sha256(path)}"
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError(f"Python executable not found: {descriptor}")
    return path, f"executable {path}"


def _check_versions(baseline: dict[str, Any], candidate: dict[str, Any], allow_cross_version: bool) -> None:
    if baseline["implementation"] != "CPython" or candidate["implementation"] != "CPython":
        raise ValueError("both interpreters must be CPython")
    if baseline["version"][:2] != candidate["version"][:2] and not allow_cross_version:
        raise ValueError("major.minor versions differ; use --allow-cross-version for research")


def _macos_host_provenance() -> dict[str, Any]:
    def command_output(argv: list[str]) -> str | None:
        try:
            result = subprocess.run(
                argv, capture_output=True, text=True, timeout=5, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    def sysctl_value(name: str) -> str | None:
        return command_output(["sysctl", "-n", name])

    def sysctl_integer(name: str) -> int | None:
        value = sysctl_value(name)
        try:
            return int(value) if value is not None else None
        except ValueError:
            return None

    try:
        load_average: list[float] | None = list(os.getloadavg())
    except OSError:
        load_average = None
    return {
        "system": platform.system(),
        "kernel_release": platform.release(),
        "machine": platform.machine(),
        "macos_version": command_output(["sw_vers", "-productVersion"]),
        "hardware_model": sysctl_value("hw.model"),
        "cpu_model": sysctl_value("machdep.cpu.brand_string"),
        "logical_cpu_count": sysctl_integer("hw.logicalcpu"),
        "physical_core_count": sysctl_integer("hw.physicalcpu"),
        "performance_core_count": sysctl_integer("hw.perflevel0.physicalcpu"),
        "efficiency_core_count": sysctl_integer("hw.perflevel1.physicalcpu"),
        "memory_total_bytes": sysctl_integer("hw.memsize"),
        "load_average": load_average,
        "cpu_affinity": None,
        "cpu_frequency_control": "not recorded; macOS host policy",
    }


def _run_internal(args: argparse.Namespace) -> Path:
    linux_amd64 = platform.system() == "Linux" and platform.machine() == "x86_64"
    macos_arm64_local = (
        platform.system() == "Darwin"
        and platform.machine() in {"arm64", "aarch64"}
        and args.local
    )
    if not linux_amd64 and not macos_arm64_local:
        raise RuntimeError(
            "measurements require Linux amd64, or native Apple Silicon with --local"
        )
    if args.timing_only and not macos_arm64_local:
        raise ValueError("--timing-only is currently supported only for local Apple Silicon runs")
    if macos_arm64_local and args.profile == "rigorous":
        raise ValueError("macOS allocation profiling is unsupported; use quick or standard")
    if macos_arm64_local and args.suite in {"pyperformance", "full"}:
        raise ValueError("macOS pyperformance memory profiling is unsupported")
    if macos_arm64_local and args.perf_stat:
        raise ValueError("--perf-stat is a Linux-only diagnostic")
    if os.environ.get("BENCH_OFFLINE_CONTAINER") != "1" and not args.local:
        raise RuntimeError("measurement requires the offline benchmark container; use `run` on the host")
    if not 1 <= args.memory_interval_ms <= 1000:
        raise ValueError("--memory-interval-ms must be between 1 and 1000")
    from benchmarks.harness.environment import (
        collect_host_provenance, discover_cpu_topology, measure_install_size,
        select_physical_cpus,
    )
    from benchmarks.harness.report import compare_workload, save_summary

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    lock_snapshot = output / "inputs.lock.json"
    input_lock_name = "inputs.macos-cp316.lock.json" if macos_arm64_local else "inputs.lock.json"
    shutil.copyfile(BENCH / input_lock_name, lock_snapshot)
    with tempfile.TemporaryDirectory(prefix="bench-interpreters-") as temp:
        scratch = Path(temp)
        baseline, baseline_source = _extract_interpreter(args.baseline, scratch / "baseline")
        candidate, candidate_source = _extract_interpreter(args.candidate, scratch / "candidate")
        base_identity = _identity(baseline, args.baseline_label, baseline_source, args.baseline_kind)
        cand_identity = _identity(candidate, args.candidate_label, candidate_source, args.candidate_kind)
        base_identity["input_descriptor"] = os.environ.get("BENCH_BASELINE_HOST_INPUT", args.baseline)
        cand_identity["input_descriptor"] = os.environ.get("BENCH_CANDIDATE_HOST_INPUT", args.candidate)
        _check_versions(base_identity, cand_identity, args.allow_cross_version)
        cross_version = base_identity["version"][:2] != cand_identity["version"][:2]
        workload_specs = select_workloads(args.suite, args.profile, args.workload, args.category)
        wheelhouse = args.wheelhouse or BENCH / ".cache" / "wheelhouse"
        macro_site = None
        perf_site = None
        memray_site = None
        lock = None
        used_input_groups: set[str] = set()
        if args.suite != "smoke" or args.profile == "rigorous":
            from benchmarks.harness.inputs import load_lock, prepare_site

            lock = load_lock(lock_snapshot)
        needs_inputs = _macos_django_inputs(workload_specs) if macos_arm64_local else _requires_macro_inputs(workload_specs)
        if needs_inputs:
            if macos_arm64_local:
                for identity in (base_identity, cand_identity):
                    if identity["version"][:2] != [3, 16] or identity["implementation"] != "CPython" or not identity["platform"].startswith("macosx-"):
                        raise ValueError("macOS Django inputs require two native CPython 3.16 interpreters")
            group = "django" if macos_arm64_local else "macros"
            used_input_groups.add(group)
            macro_site = prepare_site(baseline, scratch / "macro-site", wheelhouse=wheelhouse,
                                      groups={group}, lock=lock)
            # A shared bytecode tree is fair only when both interpreters have
            # the same major.minor cache format. Cross-version research uses
            # source imports on both sides with bytecode writes disabled.
            if not cross_version:
                subprocess.run([str(baseline), "-m", "compileall", "-q", str(macro_site.site_packages)],
                               check=True, timeout=300)
        if args.suite in {"pyperformance", "full"}:
            used_input_groups.add("pyperformance")
            perf_site = prepare_site(baseline, scratch / "perf-site", wheelhouse=wheelhouse,
                                     groups={"core", "pyperformance"}, lock=lock)
            if not cross_version:
                subprocess.run([str(baseline), "-m", "compileall", "-q", str(perf_site.site_packages)],
                               check=True, timeout=300)
        if args.profile == "rigorous":
            used_input_groups.add("memray")
            memray_site = prepare_site(baseline, scratch / "memray-site", wheelhouse=wheelhouse,
                                       groups={"memray"}, lock=lock)
        if linux_amd64:
            topology = discover_cpu_topology()
            # A single discovered physical core is used for paired CPU-heavy macros.
            affinity = set(select_physical_cpus(topology, 1)) if topology.cores else None
            host_provenance = collect_host_provenance(
                selected_affinity=sorted(affinity) if affinity else None
            )
        else:
            affinity = None
            host_provenance = _macos_host_provenance()
        raw: list[dict[str, Any]] = []
        comparisons: list[dict[str, Any]] = []
        for workload in workload_specs:
            print(f"running {workload.name}", flush=True)
            site = getattr(macro_site, "site_packages", macro_site)
            allocation_site = getattr(memray_site, "site_packages", memray_site)
            result = run_workload(
                workload, baseline, candidate, profile=args.profile, site_packages=site,
                output_dir=output / "realworld" / workload.name,
                wheelhouse=getattr(macro_site, "wheelhouse", args.wheelhouse),
                pip_packages=getattr(macro_site, "pip_packages", ()),
                allocation_site=allocation_site,
                affinity=affinity,
                memory_interval_seconds=args.memory_interval_ms / 1000,
                perf_stat=args.perf_stat,
                measure_memory=not args.timing_only,
            )
            raw.append(result)
            comparisons.append(compare_workload(result, baseline_label=args.baseline_label,
                                                candidate_label=args.candidate_label,
                                                baseline_kind=args.baseline_kind,
                                                memory_gate=not args.timing_only,
                                                memory_primary_metric=("peak_rss" if macos_arm64_local else "peak_pss"),
                                                allocation_gate=(args.profile == "rigorous"
                                                                 and not args.timing_only)))
        perf_comparison = None
        if perf_site is not None:
            from benchmarks.harness.pyperformance import (
                compare_pyperformance_runs, run_pyperformance,
            )

            perf_dir = output / "pyperformance"
            perf_dir.mkdir()
            selection = args.pyperformance_selection or (
                "all" if args.profile == "rigorous" else "fastapi" if args.profile == "standard" else "python_startup"
            )
            runs = {}
            for mode in ("timing", "memory"):
                for side, python in (("baseline", baseline), ("candidate", candidate)):
                    runs[(mode, side)] = run_pyperformance(
                        python, perf_site.site_packages, perf_site.benchmark_root,
                        perf_dir / side, selection=selection, mode=mode,
                        affinity=",".join(map(str, sorted(affinity))) if affinity else None,
                    )
            sys.path.insert(0, str(perf_site.site_packages))
            try:
                perf_comparison = compare_pyperformance_runs(
                    runs[("timing", "baseline")], runs[("timing", "candidate")],
                    runs[("memory", "baseline")], runs[("memory", "candidate")],
                )
            finally:
                sys.path.remove(str(perf_site.site_packages))
            (perf_dir / "comparison.json").write_text(json.dumps(perf_comparison, indent=2, sort_keys=True) + "\n")
        locked_inputs = _used_input_provenance(lock, used_input_groups)
        provenance = {
            "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "git_commit": _git_commit(),
            "baseline": base_identity,
            "candidate": cand_identity,
            "installed_size": {
                "baseline": measure_install_size(baseline.parent.parent, executable=baseline).as_dict(),
                "candidate": measure_install_size(candidate.parent.parent, executable=candidate).as_dict(),
            },
            "suite": args.suite,
            "profile": args.profile,
            "offline_boundary": "docker --network none" if not args.local else "local diagnostic; network not denied",
            "benchmark_lock_sha256": _sha256(lock_snapshot),
            "benchmark_packages": [
                {key: entry[key] for key in ("name", "version", "filename", "sha256", "groups") if key in entry}
                for entry in locked_inputs
            ],
            "benchmark_tool_versions": {
                entry["name"]: entry["version"] for entry in locked_inputs
                if entry["name"] in {"pyperformance", "pyperf", "memray"}
            },
            "benchmark_image_id": os.environ.get("BENCH_IMAGE_ID"),
            "container_runtime_version": os.environ.get("BENCH_DOCKER_VERSION"),
            "perf_tool_path": shutil.which("perf"),
            "host": host_provenance,
            "cpu_affinity": sorted(affinity) if affinity else None,
            "memory_sampling_interval_seconds": args.memory_interval_ms / 1000,
            "memory_primary_metric": "peak_rss" if macos_arm64_local else "peak_pss",
            "measurement_mode": (
                "timing-only; process memory and allocation passes are not measured"
                if args.timing_only else "timing plus sampled macOS tree RSS and kernel root peak; PSS/private/swap unsupported"
                if macos_arm64_local else "timing plus configured resource passes"
            ),
            "python_environment": {name: os.environ.get(name) for name in
                                   ("PYTHONHASHSEED", "PYTHONMALLOC", "PYTHONPATH", "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE")},
            "run_order": "alternating BC/CB",
            "bytecode_policy": (
                "source imports for cross-version run" if cross_version else
                "shared baseline-precompiled site" if macro_site or perf_site else
                "no third-party site prepared"
            ),
        }
        (output / "provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True, default=str) + "\n")
        summary = {"schema_version": 1, "baseline": base_identity, "candidate": cand_identity,
                   "workloads": comparisons, "suite": args.suite, "profile": args.profile,
                   "cross_version": cross_version,
                   "measurement_mode": provenance["measurement_mode"]}
        if perf_comparison is not None:
            summary["pyperformance"] = perf_comparison
        save_summary(summary, output, provenance)
        return output


def _git_commit() -> str | None:
    supplied = os.environ.get("BENCH_GIT_COMMIT")
    if supplied:
        return supplied
    try:
        completed = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                   capture_output=True, text=True)
    except FileNotFoundError:
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


def _docker_descriptor(descriptor: str, side: str, mounts: list[str]) -> str:
    if descriptor == "image-python":
        return descriptor
    path = Path(descriptor).resolve()
    if not path.exists():
        raise ValueError(f"input does not exist: {path}")
    if path.is_file() and path.suffixes[-2:] == [".tar", ".gz"]:
        mounts.extend(["-v", f"{path}:/inputs/{side}.tar.gz:ro"])
        return f"/inputs/{side}.tar.gz"
    # Bind the whole installation prefix so interpreter-relative libraries work.
    prefix = path.parent.parent
    mounts.extend(["-v", f"{prefix}:/interpreters/{side}:ro"])
    return f"/interpreters/{side}/{path.relative_to(prefix)}"


def _run_container(args: argparse.Namespace) -> Path:
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("benchmark measurements require a native Linux amd64 host")
    output = args.output.resolve()
    if output.exists():
        raise ValueError(f"refusing to overwrite result directory: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    mounts = ["-v", f"{BENCH}:/workspace/benchmarks:ro", "-v", f"{output}:/results"]
    baseline = _docker_descriptor(args.baseline, "baseline", mounts)
    candidate = _docker_descriptor(args.candidate, "candidate", mounts)
    if args.wheelhouse:
        mounts += ["-v", f"{args.wheelhouse.resolve()}:/wheelhouse:ro"]
    inspected = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", IMAGE],
                               capture_output=True, text=True, check=True)
    image_id = inspected.stdout.strip()
    docker_version = subprocess.run(
        ["docker", "version", "--format", "{{.Client.Version}}/{{.Server.Version}}"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    command = ["docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
               "--user", f"{os.getuid()}:{os.getgid()}",
               "-e", "BENCH_OFFLINE_CONTAINER=1", "-e", f"BENCH_IMAGE_ID={image_id}",
               "-e", f"BENCH_GIT_COMMIT={_git_commit() or 'unknown'}",
               "-e", f"BENCH_DOCKER_VERSION={docker_version}",
               "-e", f"BENCH_BASELINE_HOST_INPUT={args.baseline}",
               "-e", f"BENCH_CANDIDATE_HOST_INPUT={args.candidate}",
               "-w", "/workspace", *mounts, IMAGE,
               "python3", "/workspace/benchmarks/bench.py", "_run",
               "--baseline", baseline, "--candidate", candidate,
               "--baseline-label", args.baseline_label, "--candidate-label", args.candidate_label,
               "--baseline-kind", args.baseline_kind, "--candidate-kind", args.candidate_kind,
               "--suite", args.suite, "--profile", args.profile,
               "--memory-interval-ms", str(args.memory_interval_ms),
               "--output", "/results/run"]
    if args.wheelhouse:
        command += ["--wheelhouse", "/wheelhouse"]
    if args.workload:
        command += ["--workload", args.workload]
    if args.category:
        command += ["--category", args.category]
    if args.allow_cross_version:
        command += ["--allow-cross-version"]
    if args.pyperformance_selection:
        command += ["--pyperformance-selection", args.pyperformance_selection]
    if args.perf_stat:
        command += ["--perf-stat"]
    subprocess.run(command, check=True)
    return output / "run"


def _resolve_preset(args: argparse.Namespace) -> None:
    if args.preset != "pbs":
        return
    from buildsys.targets import native_target
    from benchmarks.harness.inputs import resolve_pbs

    target = native_target().triple
    if not args.baseline:
        artifact = resolve_pbs(target=target)
        args.baseline = str(getattr(artifact, "path", artifact))
        args.baseline_label = "Astral PBS 20260610"
        args.baseline_kind = "pbs"
    if not args.candidate:
        candidates = sorted((ROOT / "dist" / target).glob("*.tar.gz"))
        if len(candidates) != 1:
            raise ValueError(
                f"PBS preset requires exactly one {target} dist archive; specify --candidate"
            )
        args.candidate = str(candidates[0])
        args.candidate_label = "python-build CPython 3.14.6"
        args.candidate_kind = "python-build"


def _record_baseline(result_directory: Path, destination: Path) -> Path:
    from benchmarks.harness.baseline import save_baseline_snapshot

    destination = destination.resolve()
    baseline_directory = (BENCH / "baselines").resolve()
    if not destination.is_relative_to(baseline_directory):
        raise ValueError("baseline output must be inside benchmarks/baselines/")
    if destination.suffix.lower() != ".json":
        raise ValueError("baseline output must end in .json")
    return save_baseline_snapshot(result_directory, destination, overwrite=True)


def _update_baseline(result_directory: Path) -> Path:
    from benchmarks.harness.baseline import update_baseline_snapshot

    return update_baseline_snapshot(result_directory, BENCH / "baselines")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    fetch = sub.add_parser("fetch")
    fetch.add_argument(
        "--target",
        choices=("x86_64-unknown-linux-musl", "aarch64-apple-darwin"),
        help="product/reference target; macOS timing runs fetch only the matching PBS archive",
    )
    sub.add_parser("prepare")
    run = sub.add_parser("run")
    internal = sub.add_parser("_run", help=argparse.SUPPRESS)
    self_compare = sub.add_parser("self-compare")
    for command in (run, internal, self_compare):
        command.add_argument("--baseline")
        command.add_argument("--candidate")
        command.add_argument("--baseline-label", default="baseline CPython")
        command.add_argument("--candidate-label", default="candidate CPython")
        command.add_argument("--baseline-kind", choices=("upstream", "pbs", "python-build", "self", "custom"), default="custom")
        command.add_argument("--candidate-kind", choices=("upstream", "pbs", "python-build", "self", "custom"), default="custom")
        command.add_argument("--suite", choices=("smoke", "realworld", "pyperformance", "full"), default="smoke")
        command.add_argument("--profile", choices=("quick", "standard", "rigorous"), default="quick")
        command.add_argument("--memory-interval-ms", type=float, default=10.0,
                             help="external process-tree sampling interval (1 to 1000 ms)")
        command.add_argument("--workload")
        command.add_argument("--category")
        command.add_argument("--pyperformance-selection", help="pyperformance group or benchmark name")
        command.add_argument("--wheelhouse", type=Path)
        command.add_argument("--output", type=Path)
        command.add_argument("--allow-cross-version", action="store_true")
        command.add_argument("--perf-stat", action="store_true", help="optional separate Linux perf stat diagnostics")
        command.add_argument("--local", action="store_true", help="diagnostic only: no offline network boundary")
        command.add_argument("--timing-only", action="store_true",
                             help="local Apple Silicon timing run without the external RSS pass")
    run.add_argument("--preset", choices=("pbs",))
    run.add_argument("--container", action="store_true", help="use offline container (the default)")
    run.add_argument(
        "--record-baseline",
        type=Path,
        metavar="PATH",
        help="write baseline-side measurements and runner specs under benchmarks/baselines/",
    )
    self_compare.add_argument("--python", required=True)
    self_compare.add_argument(
        "--record-baseline",
        type=Path,
        metavar="PATH",
        help="write self-control measurements and runner specs under benchmarks/baselines/",
    )
    self_compare.set_defaults(profile="rigorous")
    record = sub.add_parser("record-baseline", help="export a completed run's baseline-side measurements")
    record.add_argument("result_directory", type=Path)
    record.add_argument("--output", type=Path, help="override the automatically selected baseline path")
    compare = sub.add_parser("compare")
    compare.add_argument("result_directory", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            print(json.dumps({"platform": platform.platform(), "machine": platform.machine(),
                              "docker": shutil.which("docker"), "image": IMAGE}, indent=2))
        elif args.command == "fetch":
            from benchmarks.harness.inputs import fetch_inputs, fetch_pbs, load_lock

            from buildsys.targets import native_target

            target = args.target or native_target().triple
            if target == "aarch64-apple-darwin":
                from benchmarks.harness.inputs import MACOS_CP316_LOCK_PATH

                print(fetch_inputs(load_lock(MACOS_CP316_LOCK_PATH), groups={"django"}))
            else:
                print(fetch_inputs(load_lock()))
            print(fetch_pbs(target=target).path)
        elif args.command == "prepare":
            subprocess.run(["docker", "build", "--platform", "linux/amd64", "-t", IMAGE, str(BENCH)], check=True)
        elif args.command == "record-baseline":
            if args.output is None:
                print(_update_baseline(args.result_directory))
            else:
                print(_record_baseline(args.result_directory, args.output))
        elif args.command == "compare":
            from benchmarks.harness.report import compare_workload, save_summary

            raw_paths = sorted((args.result_directory / "realworld").glob("*/raw.json"))
            provenance = json.loads((args.result_directory / "provenance.json").read_text())
            summary = {"schema_version": 1, "baseline": provenance["baseline"],
                       "candidate": provenance["candidate"],
                       "workloads": [compare_workload(json.loads(path.read_text()),
                                      baseline_label=provenance["baseline"]["label"],
                                      candidate_label=provenance["candidate"]["label"],
                                      baseline_kind=provenance["baseline"].get("kind"),
                                      memory_primary_metric=provenance.get("memory_primary_metric", "peak_pss"),
                                      memory_gate="timing-only" not in provenance.get("measurement_mode", ""),
                                      allocation_gate=provenance["profile"] == "rigorous") for path in raw_paths],
                       "suite": provenance["suite"], "profile": provenance["profile"],
                       "cross_version": provenance["baseline"]["version"][:2] != provenance["candidate"]["version"][:2]}
            pyperformance_comparison = args.result_directory / "pyperformance" / "comparison.json"
            if pyperformance_comparison.exists():
                summary["pyperformance"] = json.loads(pyperformance_comparison.read_text())
            save_summary(summary, args.result_directory, provenance)
            print(args.result_directory / "summary.md")
        else:
            if args.command == "self-compare":
                args.baseline = args.candidate = args.python
                args.baseline_label = args.candidate_label = "self-comparison control"
                args.baseline_kind = args.candidate_kind = "self"
            elif args.command == "run":
                _resolve_preset(args)
                if args.baseline_kind == "pbs" and args.local:
                    native_macos = (
                        platform.system() == "Darwin"
                        and platform.machine() in {"arm64", "aarch64"}
                    )
                    if not native_macos:
                        raise ValueError(
                            "PBS references require the offline Linux container, except for "
                            "native macOS local comparisons"
                        )
                if args.local and args.container:
                    raise ValueError("--local and --container select incompatible execution boundaries")
                if args.timing_only and not args.local:
                    raise ValueError("--timing-only requires --local")
            if not args.baseline or not args.candidate:
                raise ValueError("--baseline and --candidate are required")
            if args.output is None:
                stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                args.output = BENCH / "results" / stamp
            if args.command == "_run" or args.local:
                result = _run_internal(args)
            else:
                result = _run_container(args)
            print(result)
            if args.command != "_run":
                baseline_destination = getattr(args, "record_baseline", None)
                if baseline_destination is None:
                    print(_update_baseline(result))
                else:
                    print(_record_baseline(result, baseline_destination))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
