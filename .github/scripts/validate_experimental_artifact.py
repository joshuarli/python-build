from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
REVISION_PATTERN = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_digest(value: object, name: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{name} is not a SHA-256 digest")
    return value


def is_arm64(value: object) -> bool:
    return isinstance(value, str) and value in {"arm64", "aarch64"}


def validate_docker_receipt(receipt: dict, name: str, revision: str) -> None:
    if receipt.get("schema") != 1:
        raise ValueError(f"{name} has an unsupported schema")
    if receipt.get("target_triple") != "aarch64-unknown-linux-musl":
        raise ValueError(f"{name} has the wrong target")
    if receipt.get("platform") != "linux/arm64":
        raise ValueError(f"{name} has the wrong platform")
    if receipt.get("source_revision") != revision:
        raise ValueError(f"{name} has the wrong source revision")
    if receipt.get("source_dirty") is not False:
        raise ValueError(f"{name} does not prove a clean source tree")
    if receipt.get("daemon_os") != "linux":
        raise ValueError(f"{name} did not run on Linux")
    for field in ("daemon_architecture", "image_architecture", "container_architecture"):
        if not is_arm64(receipt.get(field)):
            raise ValueError(f"{name} does not prove arm64: {field}")
    if receipt.get("network_mode") != "none":
        raise ValueError(f"{name} did not use an isolated network")
    if receipt.get("isolation") != "docker-network-none":
        raise ValueError(f"{name} has an unexpected isolation mode")
    if type(receipt.get("exit_code")) is not int or receipt["exit_code"] != 0:
        raise ValueError(f"{name} does not record success")
    if not isinstance(receipt.get("command"), list) or not receipt["command"]:
        raise ValueError(f"{name} does not record the executed command")


def validate_build_receipts(directory: Path, revision: str) -> dict:
    linux_build_path = directory / "linux-build.json"
    docker_build_path = directory / "docker-build.json"
    docker_runtime_path = directory / "docker-runtime.json"
    linux_build = json.loads(linux_build_path.read_text(encoding="utf-8"))
    docker_build = json.loads(docker_build_path.read_text(encoding="utf-8"))
    docker_runtime = json.loads(docker_runtime_path.read_text(encoding="utf-8"))

    if linux_build.get("schema_version") != 1:
        raise ValueError("Linux build receipt has an unsupported schema")
    if linux_build.get("target") != "aarch64-unknown-linux-musl":
        raise ValueError("Linux build receipt has the wrong target")
    if linux_build.get("source_revision") != revision:
        raise ValueError("Linux build receipt has the wrong source revision")
    if linux_build.get("pgo") is not False:
        raise ValueError("Linux build receipt unexpectedly enabled PGO")

    validate_docker_receipt(docker_build, "Docker build receipt", revision)
    validate_docker_receipt(docker_runtime, "Docker runtime receipt", revision)
    expected_build_sha256 = require_digest(
        docker_build.get("linux_build_sha256"), "Docker build receipt's Linux build SHA-256"
    )
    if expected_build_sha256 != sha256_file(linux_build_path):
        raise ValueError("Linux build receipt bytes do not match the Docker build receipt")
    return docker_runtime


def validate(directory: Path, revision: str, build_directory: Path | None) -> None:
    if REVISION_PATTERN.fullmatch(revision) is None:
        raise ValueError("expected source revision is not a full commit hash")
    directory = directory.resolve(strict=True)
    build_directory = (build_directory or directory).resolve(strict=True)
    docker_runtime = validate_build_receipts(build_directory, revision)
    report_path = directory / "qualification report.json"
    manifest_path = directory / "EXPERIMENTALartifact.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if report.get("ok") is not True:
        raise ValueError("qualification report does not record success")
    if manifest.get("source_revision") != revision:
        raise ValueError("artifact source revision differs from the dispatched commit")
    if manifest.get("build", {}).get("source", {}).get("revision") != revision:
        raise ValueError("build record source revision differs from the dispatched commit")
    if manifest.get("target", {}).get("triple") != "aarch64-unknown-linux-musl":
        raise ValueError("artifact target is not native Linux arm64 musl")
    if manifest.get("product", {}).get("version") != "3.15.1":
        raise ValueError("artifact is not CPython 3.15.1")
    bundled = manifest.get("components", {}).get("bundled", [])
    if not isinstance(bundled, list) or any(
        isinstance(component, dict) and component.get("name") == "openssl"
        for component in bundled
    ):
        raise ValueError("artifact manifest includes bundled OpenSSL")

    archive_record = manifest.get("archive", {})
    archive_name = archive_record.get("filename")
    if (
        not isinstance(archive_name, str)
        or Path(archive_name).name != archive_name
        or archive_name in {"", ".", ".."}
    ):
        raise ValueError("artifact manifest has an unsafe archive filename")
    archive_path = directory / archive_name
    if archive_path.is_symlink() or not archive_path.is_file():
        raise ValueError("qualified archive is missing or is not a regular file")

    archive_sha256 = sha256_file(archive_path)
    if require_digest(archive_record.get("sha256"), "manifest archive SHA-256") != archive_sha256:
        raise ValueError("archive bytes do not match the manifest SHA-256")
    if require_digest(
        docker_runtime.get("archive_sha256"), "Docker runtime archive SHA-256"
    ) != archive_sha256:
        raise ValueError("archive bytes differ from the Docker runtime receipt")
    runtime_archive_path = docker_runtime.get("archive_path")
    if not isinstance(runtime_archive_path, str) or Path(runtime_archive_path).name != archive_name:
        raise ValueError("Docker runtime receipt names a different archive")

    archive_check = report.get("checks", {}).get("archive_roundtrip", {})
    if require_digest(
        archive_check.get("archive_sha256"), "qualification archive SHA-256"
    ) != archive_sha256:
        raise ValueError("archive bytes do not match the qualification report")

    manifest_sha256 = sha256_file(manifest_path)
    manifest_check = report.get("artifact_manifest", {})
    if require_digest(
        manifest_check.get("sha256"), "qualification manifest SHA-256"
    ) != manifest_sha256:
        raise ValueError("manifest bytes do not match the qualification report")

    print(
        f"validated {archive_name}: source={revision} archive_sha256={archive_sha256}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--build-directory", type=Path)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    validate(args.directory, args.revision, args.build_directory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
