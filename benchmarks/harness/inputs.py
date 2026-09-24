"""Locked benchmark inputs and external site-packages preparation.

Benchmark dependencies are verified before a measurement run and extracted
into an external site-packages prefix. The tested interpreter is never asked
to install packages and never needs pip or venv.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import tempfile
from typing import Any, Iterable, Mapping
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen
import zipfile


BENCHMARKS = Path(__file__).resolve().parents[1]
REPOSITORY = BENCHMARKS.parent
DEFAULT_WHEELHOUSE = BENCHMARKS / ".cache" / "wheelhouse"
DEFAULT_REFERENCE_CACHE = BENCHMARKS / ".cache" / "references"
LOCK_PATH = BENCHMARKS / "inputs.lock.json"
SOURCES_LOCK_PATH = REPOSITORY / "sources.lock.json"


class InputError(ValueError):
    """A benchmark lock or cached input violates its declared contract."""


@dataclass(frozen=True)
class LockedInput:
    name: str
    version: str
    url: str
    sha256: str
    size: int
    license: str
    purpose: str
    filename: str
    kind: str
    wheel_tags: tuple[str, ...]
    groups: tuple[str, ...]
    module_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class BenchmarkLock:
    target: Mapping[str, str]
    groups: Mapping[str, Mapping[str, Any]]
    inputs: tuple[LockedInput, ...]
    notes: tuple[str, ...]
    sha256: str

    def provenance(self, groups: Iterable[str] | None = None) -> list[dict[str, Any]]:
        """Return the exact selected input identities for result provenance."""
        selected = _select_groups(self, groups)
        return [
            {
                "name": item.name,
                "version": item.version,
                "filename": item.filename,
                "sha256": item.sha256,
                "size": item.size,
                "license": item.license,
                "groups": list(item.groups),
            }
            for item in self.inputs
            if selected.intersection(item.groups)
        ]


@dataclass(frozen=True)
class PreparedSite:
    """One immutable-by-convention dependency prefix shared by both sides."""

    site_packages: Path
    wheelhouse: Path
    benchmark_root: Path | None
    pip_packages: tuple[str, ...]
    groups: tuple[str, ...]
    lock_sha256: str
    inputs: tuple[LockedInput, ...]


@dataclass(frozen=True)
class PBSArtifact:
    name: str
    version: str
    url: str
    sha256: str
    license: str
    purpose: str
    path: Path


def _normal_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_input(raw: Mapping[str, Any]) -> LockedInput:
    required = (
        "name", "version", "url", "sha256", "size", "license", "purpose",
        "filename", "kind", "wheel_tags", "groups",
    )
    missing = [key for key in required if key not in raw]
    if missing:
        raise InputError(f"lock input is missing fields: {', '.join(missing)}")
    name = str(raw["name"])
    version = str(raw["version"])
    filename = str(raw["filename"])
    url = str(raw["url"])
    sha256 = str(raw["sha256"])
    if not name or not version or not filename or Path(filename).name != filename:
        raise InputError(f"invalid benchmark input identity: {raw!r}")
    parsed_url = urlparse(url)
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise InputError(f"benchmark input URL must use HTTPS: {url}")
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise InputError(f"invalid sha256 for {filename}")
    size = raw["size"]
    if not isinstance(size, int) or size <= 0:
        raise InputError(f"invalid size for {filename}")
    kind = str(raw["kind"])
    if kind not in {"wheel", "sdist"}:
        raise InputError(f"unsupported input kind for {filename}: {kind}")
    tags = tuple(str(tag) for tag in raw["wheel_tags"])
    if kind == "wheel":
        if not filename.endswith(".whl") or not tags:
            raise InputError(f"wheel input lacks wheel tags: {filename}")
        fields = filename[:-4].rsplit("-", 3)
        if len(fields) != 4 or "-".join(fields[-3:]) not in tags:
            raise InputError(f"wheel tags do not match filename: {filename}")
    elif tags:
        raise InputError(f"source input must not declare wheel tags: {filename}")
    groups = tuple(sorted(set(str(group) for group in raw["groups"])))
    if not groups:
        raise InputError(f"benchmark input has no group: {filename}")
    license_name = str(raw["license"]).strip()
    purpose = str(raw["purpose"]).strip()
    if not license_name or not purpose:
        raise InputError(f"benchmark input lacks license or purpose: {filename}")
    module_paths = tuple(str(path) for path in raw.get("module_paths", ()))
    for module_path in module_paths:
        parts = PurePosixPath(module_path).parts
        if not parts or PurePosixPath(module_path).is_absolute() or ".." in parts:
            raise InputError(f"unsafe module path for {filename}: {module_path}")
    return LockedInput(
        name=name,
        version=version,
        url=url,
        sha256=sha256,
        size=size,
        license=license_name,
        purpose=purpose,
        filename=filename,
        kind=kind,
        wheel_tags=tags,
        groups=groups,
        module_paths=module_paths,
    )


def load_lock(path: Path | str | None = None) -> BenchmarkLock:
    """Load and validate the locked Linux amd64 benchmark input manifest."""
    lock_path = Path(path) if path is not None else LOCK_PATH
    raw_bytes = lock_path.read_bytes()
    try:
        raw = json.loads(raw_bytes)
    except json.JSONDecodeError as exc:
        raise InputError(f"invalid JSON benchmark lock: {lock_path}") from exc
    if raw.get("schema_version") != 1:
        raise InputError(f"unsupported benchmark lock schema: {raw.get('schema_version')!r}")
    target = raw.get("target")
    if not isinstance(target, dict) or target.get("os") != "linux" or target.get("architecture") != "x86_64":
        raise InputError("benchmark lock must target Linux x86_64")
    raw_groups = raw.get("groups")
    if not isinstance(raw_groups, dict) or "core" not in raw_groups:
        raise InputError("benchmark lock must define the core input group")
    groups: dict[str, Mapping[str, Any]] = {}
    for group_name, group_data in raw_groups.items():
        if not isinstance(group_name, str) or not isinstance(group_data, dict):
            raise InputError("invalid benchmark group entry")
        includes = group_data.get("include_groups", [])
        package_specs = group_data.get("packages", [])
        if not isinstance(includes, list) or not all(isinstance(value, str) for value in includes):
            raise InputError(f"invalid included groups for {group_name}")
        if not isinstance(package_specs, list) or not all(isinstance(value, str) for value in package_specs):
            raise InputError(f"invalid package roots for {group_name}")
        groups[group_name] = {
            **group_data,
            "include_groups": tuple(includes),
            "packages": tuple(package_specs),
        }
    for group_name, group_data in groups.items():
        unknown = set(group_data["include_groups"]) - groups.keys()
        if unknown:
            raise InputError(f"{group_name} includes unknown groups: {', '.join(sorted(unknown))}")
    raw_inputs = raw.get("inputs")
    if not isinstance(raw_inputs, list):
        raise InputError("benchmark lock must contain an inputs list")
    inputs = tuple(_parse_input(item) for item in raw_inputs)
    names: set[tuple[str, str]] = set()
    filenames: dict[str, str] = {}
    for item in inputs:
        unknown_groups = set(item.groups) - groups.keys()
        if unknown_groups:
            raise InputError(f"{item.filename} references unknown groups: {', '.join(sorted(unknown_groups))}")
        package_key = (_normal_name(item.name), item.version)
        artifact_key = f"{package_key[0]}=={package_key[1]}"
        if package_key in names:
            raise InputError(f"duplicate package version in lock: {artifact_key}")
        names.add(package_key)
        previous_hash = filenames.setdefault(item.filename, item.sha256)
        if previous_hash != item.sha256:
            raise InputError(f"filename has multiple hashes in lock: {item.filename}")
    notes = raw.get("notes", [])
    if not isinstance(notes, list) or not all(isinstance(note, str) for note in notes):
        raise InputError("benchmark lock notes must be strings")
    return BenchmarkLock(
        target={str(key): str(value) for key, value in target.items()},
        groups=groups,
        inputs=inputs,
        notes=tuple(notes),
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
    )


def _select_groups(lock: BenchmarkLock, requested: Iterable[str] | str | None) -> set[str]:
    if requested is None:
        requested_groups = set(lock.groups) - {"core"}
    elif isinstance(requested, str):
        requested_groups = {requested}
    else:
        requested_groups = set(requested)
    requested_groups.add("core")
    selected: set[str] = set()
    pending = list(requested_groups)
    while pending:
        group = pending.pop()
        if group in selected:
            continue
        if group not in lock.groups:
            raise InputError(f"unknown benchmark input group: {group}")
        selected.add(group)
        pending.extend(lock.groups[group]["include_groups"])
    return selected


def _requested_groups(lock: BenchmarkLock, requested: Iterable[str] | str | None) -> set[str]:
    if requested is None:
        return set(lock.groups) - {"core"}
    if isinstance(requested, str):
        return {requested} - {"core"}
    return set(requested) - {"core"}


def _selected_inputs(lock: BenchmarkLock, groups: Iterable[str] | str | None) -> tuple[LockedInput, ...]:
    selected = _select_groups(lock, groups)
    return tuple(item for item in lock.inputs if selected.intersection(item.groups))


def _check_selected_versions(inputs: Iterable[LockedInput]) -> None:
    versions: dict[str, str] = {}
    for item in inputs:
        name = _normal_name(item.name)
        prior = versions.setdefault(name, item.version)
        if prior != item.version:
            raise InputError(
                f"selected groups contain conflicting versions of {item.name}: {prior} and {item.version}"
            )


def _verify_file(path: Path, item: LockedInput, *, verify_size: bool = True) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"benchmark input is missing: {path}")
    if verify_size and path.stat().st_size != item.size:
        raise InputError(f"benchmark input size mismatch for {item.filename}")
    if _sha256_file(path) != item.sha256:
        raise InputError(f"benchmark input sha256 mismatch for {item.filename}")


def _download(item: LockedInput, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{destination.name}.", dir=destination.parent, delete=False) as output:
            temporary_path = Path(output.name)
            digest = hashlib.sha256()
            total = 0
            request = Request(item.url, headers={"User-Agent": "python-build-benchmarks/1"})
            with urlopen(request, timeout=60) as response:
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    digest.update(chunk)
                    output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if total != item.size:
            raise InputError(f"downloaded size mismatch for {item.filename}: {total} != {item.size}")
        if digest.hexdigest() != item.sha256:
            raise InputError(f"downloaded sha256 mismatch for {item.filename}")
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def fetch_inputs(
    lock: BenchmarkLock | None = None,
    *,
    cache_dir: Path | str | None = None,
    groups: Iterable[str] | str | None = None,
) -> Path:
    """Fetch and verify selected locked artifacts into a flat offline wheelhouse."""
    manifest = lock or load_lock()
    wheelhouse = Path(cache_dir) if cache_dir is not None else DEFAULT_WHEELHOUSE
    wheelhouse.mkdir(parents=True, exist_ok=True)
    for item in _selected_inputs(manifest, groups):
        destination = wheelhouse / item.filename
        if destination.exists():
            _verify_file(destination, item)
        elif (BENCHMARKS / "vendor" / item.filename).is_file():
            vendored = BENCHMARKS / "vendor" / item.filename
            _verify_file(vendored, item)
            temporary: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    prefix=f".{destination.name}.", dir=wheelhouse, delete=False
                ) as output:
                    temporary = Path(output.name)
                    with vendored.open("rb") as source:
                        shutil.copyfileobj(source, output)
                _verify_file(temporary, item)
                os.replace(temporary, destination)
                temporary = None
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        else:
            _download(item, destination)
    return wheelhouse


def _safe_member_path(root: Path, member_name: str) -> Path:
    relative = PurePosixPath(member_name)
    if relative.is_absolute() or not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise InputError(f"unsafe archive path: {member_name}")
    target = root.joinpath(*relative.parts)
    try:
        target.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise InputError(f"archive path escapes destination: {member_name}") from exc
    return target


def _extract_wheel(wheel_path: Path, site_packages: Path) -> None:
    with zipfile.ZipFile(wheel_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            mode = member.external_attr >> 16
            if mode and (mode & 0o170000) == 0o120000:
                raise InputError(f"wheel contains a symbolic link: {member.filename}")
            parts = PurePosixPath(member.filename).parts
            if not parts or PurePosixPath(member.filename).is_absolute() or ".." in parts:
                raise InputError(f"unsafe wheel member path: {member.filename}")
            destination_parts = parts
            if len(parts) >= 3 and parts[0].endswith(".data"):
                scheme = parts[1]
                if scheme in {"purelib", "platlib", "data"}:
                    destination_parts = parts[2:]
                elif scheme in {"scripts", "headers"}:
                    continue
                else:
                    raise InputError(f"unsupported wheel install scheme {scheme!r}: {member.filename}")
            if not destination_parts:
                continue
            destination = _safe_member_path(site_packages, "/".join(destination_parts))
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)


def _extract_sdist(item: LockedInput, archive_path: Path, site_packages: Path) -> None:
    if not item.module_paths:
        raise InputError(f"source archive has no declared import paths: {item.filename}")
    with tarfile.open(archive_path, "r:*") as archive:
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise InputError(f"unsafe source archive path: {member.name}")
            if not member.isfile():
                if member.issym() or member.islnk() or member.isdev():
                    raise InputError(f"unsupported source archive entry: {member.name}")
                continue
            for module_path in item.module_paths:
                module_parts = PurePosixPath(module_path).parts
                match_at = next(
                    (index for index in range(len(path.parts) - len(module_parts) + 1)
                     if path.parts[index:index + len(module_parts)] == module_parts),
                    None,
                )
                if match_at is None:
                    continue
                relative = PurePosixPath(*path.parts[match_at:])
                destination = _safe_member_path(site_packages, relative.as_posix())
                destination.parent.mkdir(parents=True, exist_ok=True)
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise InputError(f"cannot read source archive entry: {member.name}")
                with extracted, destination.open("wb") as output:
                    shutil.copyfileobj(extracted, output)


def prepare_site(
    interpreter_or_site: Path | str,
    site_dir: Path | str | None = None,
    *,
    groups: Iterable[str] | str | None = None,
    wheelhouse: Path | str | None = None,
    inputs_dir: Path | str | None = None,
    lock: BenchmarkLock | None = None,
) -> PreparedSite:
    """Prepare a locked dependency prefix without invoking the tested Python.

    `interpreter_or_site` accepts the baseline executable for compatibility
    with the controller call shape; extraction is interpreter-independent.
    The site and its filtered wheelhouse are produced once and then shared by
    baseline and candidate processes.
    """
    if site_dir is None:
        destination = Path(interpreter_or_site)
    else:
        destination = Path(site_dir)
    manifest = lock or load_lock()
    selected_groups = _select_groups(manifest, groups)
    requested_groups = _requested_groups(manifest, groups)
    selected_inputs = _selected_inputs(manifest, selected_groups)
    _check_selected_versions(selected_inputs)
    source_dir = Path(inputs_dir or wheelhouse) if (inputs_dir or wheelhouse) else DEFAULT_WHEELHOUSE
    if destination.exists():
        raise FileExistsError(f"prepared benchmark destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    site_packages = temporary / "site-packages"
    filtered_wheelhouse = temporary / "wheelhouse"
    site_packages.mkdir()
    filtered_wheelhouse.mkdir()
    try:
        for item in selected_inputs:
            artifact = source_dir / item.filename
            _verify_file(artifact, item)
            if item.kind == "wheel":
                _extract_wheel(artifact, site_packages)
            else:
                _extract_sdist(item, artifact, site_packages)
            shutil.copyfile(artifact, filtered_wheelhouse / item.filename)
        selected_pip_packages: list[str] = []
        for group in sorted(requested_groups):
            selected_pip_packages.extend(manifest.groups[group]["packages"])
        pip_packages = tuple(dict.fromkeys(selected_pip_packages))
        benchmark_root: Path | None = None
        if "pyperformance" in selected_groups:
            candidate = site_packages / "pyperformance" / "data-files" / "benchmarks"
            if not (candidate / "MANIFEST").is_file():
                raise InputError("pyperformance benchmark wheel did not provide data-files/benchmarks/MANIFEST")
            benchmark_root = destination / "site-packages" / "pyperformance" / "data-files" / "benchmarks"
        prepared_inputs = tuple(selected_inputs)
        descriptor = {
            "groups": sorted(selected_groups),
            "lock_sha256": manifest.sha256,
            "inputs": [
                {"name": item.name, "version": item.version, "filename": item.filename,
                 "sha256": item.sha256, "size": item.size}
                for item in prepared_inputs
            ],
        }
        (temporary / "inputs.json").write_text(json.dumps(descriptor, indent=2, sort_keys=True) + "\n")
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return PreparedSite(
        site_packages=destination / "site-packages",
        wheelhouse=destination / "wheelhouse",
        benchmark_root=benchmark_root,
        pip_packages=pip_packages,
        groups=tuple(sorted(selected_groups)),
        lock_sha256=manifest.sha256,
        inputs=prepared_inputs,
    )


def _pbs_reference_record(raw: Mapping[str, Any], target: str) -> Mapping[str, Any]:
    records = raw.get("inputs", [])
    if not isinstance(records, list):
        raise InputError("sources.lock.json must contain an inputs list")
    matches = [
        item for item in records
        if isinstance(item, Mapping)
        and item.get("role") == "reference"
        and (
            item.get("target") == target
            or (item.get("target") is None and target in str(item.get("url", "")))
        )
    ]
    if len(matches) != 1:
        raise InputError(f"sources.lock.json must contain exactly one PBS reference for {target}")
    return matches[0]


def resolve_pbs(
    sources_lock: Path | str | None = None,
    *,
    cache_dir: Path | str | None = None,
    offline: bool = True,
    target: str = "x86_64-unknown-linux-musl",
) -> PBSArtifact:
    """Resolve a pinned target-specific PBS artifact from its verified cache.

    Resolution is offline by default. Fetch the artifact explicitly during
    `fetch` with :func:`fetch_pbs`; measurement runs only read this cache.
    """
    lock_path = Path(sources_lock) if sources_lock is not None else SOURCES_LOCK_PATH
    raw = json.loads(lock_path.read_text())
    item = _pbs_reference_record(raw, target)
    url = str(item["url"])
    filename = Path(unquote(urlparse(url).path)).name
    if not filename:
        raise InputError("reference-pbs URL has no archive filename")
    cache = Path(cache_dir) if cache_dir is not None else DEFAULT_REFERENCE_CACHE
    artifact_path = cache / filename
    artifact = PBSArtifact(
        name=str(item["name"]),
        version=str(item["version"]),
        url=url,
        sha256=str(item["sha256"]),
        license=str(item.get("license", "")),
        purpose=str(item.get("purpose", "")),
        path=artifact_path,
    )
    if artifact_path.is_file():
        if _sha256_file(artifact_path) != artifact.sha256:
            raise InputError(f"cached PBS reference sha256 mismatch: {artifact_path}")
        return artifact
    if offline:
        raise FileNotFoundError(
            f"pinned PBS artifact is not cached: {artifact_path}; run `python3 benchmarks/bench.py fetch` first"
        )
    return fetch_pbs(sources_lock=lock_path, cache_dir=cache, target=target)


def fetch_pbs(
    sources_lock: Path | str | None = None,
    *,
    cache_dir: Path | str | None = None,
    target: str = "x86_64-unknown-linux-musl",
) -> PBSArtifact:
    """Download and hash-verify the pinned PBS artifact during the fetch phase."""
    try:
        return resolve_pbs(sources_lock, cache_dir=cache_dir, offline=True, target=target)
    except FileNotFoundError:
        pass
    lock_path = Path(sources_lock) if sources_lock is not None else SOURCES_LOCK_PATH
    raw = json.loads(lock_path.read_text())
    item = _pbs_reference_record(raw, target)
    url = str(item["url"])
    filename = Path(unquote(urlparse(url).path)).name
    cache = Path(cache_dir) if cache_dir is not None else DEFAULT_REFERENCE_CACHE
    destination = cache / filename
    cache.mkdir(parents=True, exist_ok=True)
    expected_hash = str(item["sha256"])
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{filename}.", dir=cache, delete=False) as output:
            temporary = Path(output.name)
            digest = hashlib.sha256()
            request = Request(url, headers={"User-Agent": "python-build-benchmarks/1"})
            with urlopen(request, timeout=120) as response:
                while chunk := response.read(1024 * 1024):
                    digest.update(chunk)
                    output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if digest.hexdigest() != expected_hash:
            raise InputError("downloaded PBS reference sha256 mismatch")
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return resolve_pbs(lock_path, cache_dir=cache, offline=True, target=target)
