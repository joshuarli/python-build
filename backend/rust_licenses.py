from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import deque
from pathlib import Path

TARGET = "aarch64-apple-darwin"
NOTICE_PREFIXES = ("LICENSE", "COPYING", "NOTICE")


class LicenseCollectionError(Exception):
    pass


def _is_notice(path: Path) -> bool:
    name = path.name.upper()
    return name in NOTICE_PREFIXES or any(
        name.startswith(prefix + suffix)
        for prefix in NOTICE_PREFIXES
        for suffix in ("-", ".", "_")
    )


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _cargo_metadata(
    cargo: Path,
    cargo_home: Path,
    manifest: Path,
    temporary_root: Path,
) -> dict:
    environment = os.environ.copy()
    environment.update(
        {
            "CARGO_HOME": str(cargo_home),
            "CARGO_NET_OFFLINE": "true",
            "CARGO_TARGET_DIR": str(temporary_root / "cargo-target"),
            "CARGO_TERM_COLOR": "never",
            "TMPDIR": str(temporary_root),
        }
    )
    result = subprocess.run(
        [
            str(cargo),
            "metadata",
            "--locked",
            "--offline",
            "--format-version",
            "1",
            "--filter-platform",
            TARGET,
            "--manifest-path",
            str(manifest),
        ],
        cwd=manifest.parent,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise LicenseCollectionError(
            f"offline Cargo metadata failed for {manifest.name}: "
            f"{(result.stdout + result.stderr)[-4000:]}"
        )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise LicenseCollectionError(
            f"Cargo metadata returned invalid JSON for {manifest.name}"
        ) from error
    if not isinstance(data, dict):
        raise LicenseCollectionError(f"Cargo metadata is not an object: {manifest}")
    return data


def _resolved_packages(metadata: dict) -> list[dict]:
    resolve = metadata.get("resolve")
    packages = metadata.get("packages")
    if not isinstance(resolve, dict) or not isinstance(packages, list):
        raise LicenseCollectionError("Cargo metadata omitted the dependency resolution")
    root_id = resolve.get("root")
    nodes = resolve.get("nodes")
    if not isinstance(root_id, str) or not isinstance(nodes, list):
        raise LicenseCollectionError("Cargo metadata has no resolved manifest root")
    nodes_by_id = {}
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str):
            raise LicenseCollectionError("Cargo metadata contains an invalid resolution node")
        if node["id"] in nodes_by_id:
            raise LicenseCollectionError("Cargo metadata repeats a resolution node")
        nodes_by_id[node["id"]] = node
    packages_by_id = {}
    for package in packages:
        if not isinstance(package, dict) or not isinstance(package.get("id"), str):
            raise LicenseCollectionError("Cargo metadata contains an invalid package")
        packages_by_id[package["id"]] = package
    if root_id not in nodes_by_id or root_id not in packages_by_id:
        raise LicenseCollectionError("Cargo metadata root is unresolved")
    found = set()
    pending = deque((root_id,))
    while pending:
        package_id = pending.popleft()
        if package_id in found:
            continue
        found.add(package_id)
        node = nodes_by_id.get(package_id)
        if node is None:
            raise LicenseCollectionError("Cargo dependency has no resolution node")
        dependencies = node.get("deps")
        if not isinstance(dependencies, list):
            raise LicenseCollectionError("Cargo resolution node has no dependency list")
        for dependency in dependencies:
            if not isinstance(dependency, dict) or not isinstance(
                dependency.get("pkg"), str
            ):
                raise LicenseCollectionError("Cargo metadata contains an invalid dependency")
            dependency_id = dependency["pkg"]
            if dependency_id not in nodes_by_id or dependency_id not in packages_by_id:
                raise LicenseCollectionError("Cargo dependency source identity is unresolved")
            pending.append(dependency_id)
    return [packages_by_id[package_id] for package_id in sorted(found)]


def _package_location(
    package: dict,
    source_roots: dict[str, Path],
    registry_root: Path,
) -> tuple[Path, str]:
    manifest_value = package.get("manifest_path")
    if not isinstance(manifest_value, str):
        raise LicenseCollectionError("resolved Cargo package has no manifest path")
    manifest = Path(manifest_value)
    if not manifest.is_absolute():
        raise LicenseCollectionError("resolved Cargo manifest path is not absolute")
    try:
        manifest = manifest.resolve(strict=True)
    except OSError as error:
        raise LicenseCollectionError(
            f"resolved Cargo manifest is missing: {package.get('name')}"
        ) from error
    package_root = manifest.parent.resolve(strict=True)
    source = package.get("source")
    if source is None:
        for label, source_root in source_roots.items():
            if _inside(manifest, source_root):
                relative = package_root.relative_to(source_root).as_posix() or "."
                return package_root, f"local:{label}/{relative}"
        raise LicenseCollectionError(
            f"local Cargo package is outside the checked source roots: {package.get('name')}"
        )
    if not isinstance(source, str) or not source.startswith("registry+"):
        raise LicenseCollectionError(
            f"Cargo package has an unsupported source identity: {package.get('name')}"
        )
    if not _inside(manifest, registry_root):
        raise LicenseCollectionError(
            f"registry package is outside the locked Cargo source cache: {package.get('name')}"
        )
    return package_root, source


def _license_file(package: dict, package_root: Path) -> tuple[Path | None, str | None]:
    value = package.get("license_file")
    if value is None:
        return None, None
    if not isinstance(value, str):
        raise LicenseCollectionError("Cargo license_file is not a path")
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = package_root / candidate
    try:
        candidate = candidate.resolve(strict=True)
    except OSError as error:
        raise LicenseCollectionError(
            f"declared Cargo license file is missing: {package.get('name')}"
        ) from error
    if not candidate.is_file() or not _inside(candidate, package_root):
        raise LicenseCollectionError(
            f"declared Cargo license file escapes its source package: {package.get('name')}"
        )
    return candidate, candidate.relative_to(package_root).as_posix()


def _notice_files(package_root: Path, declared: Path | None) -> list[Path]:
    found = set()
    if declared is not None:
        found.add(declared)
    for path in package_root.rglob("*"):
        relative = path.relative_to(package_root)
        license_directory = any(
            part.upper() in {"LICENSE", "LICENSES", "COPYING", "NOTICES"}
            for part in relative.parts[:-1]
        )
        named_license_directory = path.name.upper() in {
            "LICENSE",
            "LICENSES",
            "COPYING",
            "NOTICES",
        }
        if not _is_notice(path) and not license_directory and not named_license_directory:
            continue
        if path.is_symlink():
            raise LicenseCollectionError(
                f"license notice is a symbolic link: {path.name}"
            )
        if path.is_file():
            resolved = path.resolve(strict=True)
            if not _inside(resolved, package_root):
                raise LicenseCollectionError("license notice escapes its source package")
            found.add(resolved)
    return sorted(found, key=lambda path: path.relative_to(package_root).as_posix())


def _safe_component(value: str) -> str:
    component = re.sub(r"[^A-Za-z0-9._+-]+", "-", value).strip(".-")
    if not component or component in {".", ".."}:
        raise LicenseCollectionError("Cargo package has an invalid output name")
    return component


def _copy_notice(
    source: Path,
    source_root: Path,
    staging: Path,
    relative_destination: Path,
) -> str:
    relative_source = source.relative_to(source_root)
    destination = staging / relative_destination / relative_source
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return destination.relative_to(staging).as_posix()


def install_rust_licenses(
    prefix: Path,
    manifests: dict[str, Path],
    source_roots: dict[str, Path],
    cargo_home: Path,
    cargo: Path,
    temporary_root: Path,
) -> dict[str, int]:
    prefix = Path(prefix).resolve()
    cargo_home = Path(cargo_home).resolve()
    cargo = Path(cargo).resolve()
    temporary_root = Path(temporary_root).resolve()
    if set(manifests) != {"rtls", "hashing"} or set(source_roots) != set(manifests):
        raise LicenseCollectionError("expected RTLS and hashing Cargo roots")
    if not cargo.is_file() or not cargo_home.is_dir() or not temporary_root.is_dir():
        raise LicenseCollectionError("offline Cargo tools or work directories are missing")
    roots = {name: Path(root).resolve(strict=True) for name, root in source_roots.items()}
    manifests = {name: Path(path).resolve(strict=True) for name, path in manifests.items()}
    for name, manifest in manifests.items():
        if not manifest.is_file() or not _inside(manifest, roots[name]):
            raise LicenseCollectionError(f"Cargo manifest is outside its checked source root: {name}")
    registry_root = (cargo_home / "registry" / "src").resolve(strict=True)

    packages: dict[str, dict] = {}
    for name in sorted(manifests):
        metadata = _cargo_metadata(cargo, cargo_home, manifests[name], temporary_root)
        for package in _resolved_packages(metadata):
            package_id = package["id"]
            item = packages.setdefault(package_id, {"package": package, "used_by": set()})
            if item["package"] != package:
                raise LicenseCollectionError("Cargo returned conflicting package identities")
            item["used_by"].add(name)

    records = []
    for package_id, item in packages.items():
        package = item["package"]
        package_name = package.get("name")
        version = package.get("version")
        if not isinstance(package_name, str) or not isinstance(version, str):
            raise LicenseCollectionError("resolved Cargo package has no name or version")
        normalized_name = package_name.lower().replace("_", "-")
        if "openssl" in normalized_name or normalized_name in {"libssl", "libcrypto"}:
            raise LicenseCollectionError(f"OpenSSL dependency is active: {package_name}")
        package_root, source_identity = _package_location(package, roots, registry_root)
        declared_path, declared_relative = _license_file(package, package_root)
        license_expression = package.get("license")
        if license_expression is not None and not isinstance(license_expression, str):
            raise LicenseCollectionError("Cargo license expression is not text")
        notices = _notice_files(package_root, declared_path)
        records.append(
            {
                "id": package_id,
                "name": package_name,
                "version": version,
                "source_identity": source_identity,
                "package_root": package_root,
                "license": license_expression,
                "license_file": declared_relative,
                "notices": notices,
                "used_by": sorted(item["used_by"]),
            }
        )
    records.sort(key=lambda item: (item["name"], item["version"], item["source_identity"]))

    names = [f"{record['name']}-{record['version']}" for record in records]
    duplicates = {name for name in names if names.count(name) > 1}
    output_names = {}
    for record in records:
        base = f"{record['name']}-{record['version']}"
        output_name = _safe_component(base)
        if base in duplicates:
            output_name += "--" + _safe_component(record["source_identity"])
        if output_name in output_names:
            raise LicenseCollectionError("Cargo packages collide in the license output")
        output_names[output_name] = record["id"]
        record["output_name"] = output_name

    license_parent = prefix / "share" / "licenses" / "python-build"
    for directory in (prefix / "share", prefix / "share/licenses", license_parent):
        if directory.is_symlink():
            raise LicenseCollectionError("license destination contains a symbolic link")
    license_parent.mkdir(parents=True, exist_ok=True)
    destination = license_parent / "rust"
    if destination.exists() or destination.is_symlink():
        raise LicenseCollectionError(f"Rust license destination already exists: {destination}")

    with tempfile.TemporaryDirectory(dir=license_parent, prefix=".rust-licenses-") as temporary:
        staging = Path(temporary) / "rust"
        (staging / "notices").mkdir(parents=True)
        notice_paths = set()
        for record in records:
            package_destination = Path("notices") / "packages" / record["output_name"]
            for notice in record["notices"]:
                notice_paths.add(
                    _copy_notice(
                        notice,
                        record["package_root"],
                        staging,
                        package_destination,
                    )
                )

        for notice in sorted(roots["rtls"].iterdir()):
            if notice.is_symlink() and _is_notice(notice):
                raise LicenseCollectionError("RTLS root notice is a symbolic link")
            if notice.is_file() and _is_notice(notice):
                rel = _copy_notice(
                    notice,
                    roots["rtls"],
                    staging,
                    Path("notices") / "projects" / "rtls",
                )
                notice_paths.add(rel)

        hashing_record = roots["hashing"] / "THIRD_PARTY_LICENSES.md"
        if not hashing_record.is_file() or hashing_record.is_symlink():
            raise LicenseCollectionError("hashing source license record is missing")
        notice_paths.add(
            _copy_notice(
                hashing_record,
                roots["hashing"],
                staging,
                Path("notices") / "projects" / "hashing",
            )
        )

        lines = [
            "# Rust package licenses",
            "",
            f"Target: `{TARGET}`",
            "",
            "Package entries are the active resolved Cargo dependency closures for the RTLS and hashing manifests.",
            "Source notices are copied byte-for-byte below `notices/`.",
            "",
            "## Active packages",
            "",
        ]
        for record in records:
            license_text = record["license"] or "not declared in Cargo metadata"
            license_file_text = record["license_file"] or "not declared"
            lines.extend(
                (
                    f"### `{record['name']}` {record['version']}",
                    f"- Source: `{record['source_identity']}`",
                    f"- Cargo license: `{license_text}`",
                    f"- Cargo license file: `{license_file_text}`",
                    f"- Used by: {', '.join(record['used_by'])}",
                )
            )
            if record["notices"]:
                lines.append("- Notices:")
                prefix_path = Path("notices") / "packages" / record["output_name"]
                for notice in record["notices"]:
                    relative = (
                        prefix_path / notice.relative_to(record["package_root"])
                    ).as_posix()
                    lines.append(f"  - `{relative}`")
            else:
                lines.append("- Notices: none bundled with the Cargo source")
            lines.append("")
        lines.extend(("## Project notices", ""))
        lines.append("- `notices/projects/rtls/` contains top-level RTLS license and notice files.")
        lines.append("- `notices/projects/hashing/THIRD_PARTY_LICENSES.md` preserves the hashing source record.")
        record_text = "\n".join(lines)
        for path in (*roots.values(), cargo_home, temporary_root):
            if str(path) in record_text:
                raise LicenseCollectionError("license record contains a builder path")
        (staging / "THIRD_PARTY_LICENSES.md").write_text(record_text, encoding="utf-8")

        builder_paths = tuple(
            str(path).encode("utf-8") for path in (*roots.values(), cargo_home, temporary_root)
        )
        for path in staging.rglob("*"):
            if path.is_symlink():
                raise LicenseCollectionError("license output contains a symbolic link")
            if path.is_file():
                content = path.read_bytes()
                if any(builder_path in content for builder_path in builder_paths):
                    raise LicenseCollectionError("license output contains a builder path")
        os.replace(staging, destination)

    return {"packages": len(records), "notices": len(notice_paths)}
