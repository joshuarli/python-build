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
    if receipt.get("daemon_platform") != "linux/arm64":
        raise ValueError(f"{name} did not use a native Linux arm64 daemon")
    if not is_arm64(receipt.get("daemon_architecture")):
        raise ValueError(f"{name} did not report an arm64 Docker daemon")
    if receipt.get("container_architecture") != "aarch64":
        raise ValueError(f"{name} did not run an arm64 container")
    if receipt.get("image_architecture") not in {"aarch64", "arm64"}:
        raise ValueError(f"{name} did not use an arm64 image")
    if not isinstance(receipt.get("image_id"), str) or re.fullmatch(
        r"sha256:[0-9a-f]{64}", receipt["image_id"]
    ) is None:
        raise ValueError(f"{name} has no immutable image identity")
    if receipt.get("network_mode") != "none":
        raise ValueError(f"{name} did not use an isolated network")
    if receipt.get("isolation") != "docker-network-none":
        raise ValueError(f"{name} has an unexpected isolation mode")
    if type(receipt.get("exit_code")) is not int or receipt["exit_code"] != 0:
        raise ValueError(f"{name} does not record success")
    if not isinstance(receipt.get("command"), list) or not receipt["command"]:
        raise ValueError(f"{name} does not record the executed command")
    command = receipt["command"]
    if any(not isinstance(argument, str) for argument in command):
        raise ValueError(f"{name} has an invalid command record")
    if not any(
        command[index : index + 2] == ["--network", "none"]
        or command[index] == "--network=none"
        for index in range(len(command))
    ):
        raise ValueError(f"{name} command did not disable networking")
    if not any(
        command[index : index + 2] == ["--platform", "linux/arm64"]
        or command[index] == "--platform=linux/arm64"
        for index in range(len(command))
    ):
        raise ValueError(f"{name} command did not request the native arm64 platform")
    bootstrap_path = Path(__file__).resolve().parents[2] / "bootstrap.lock.json"
    bootstrap = json.loads(bootstrap_path.read_text(encoding="utf-8"))
    expected_image = bootstrap["linux_toolchain"]["images"]["arm64"]["digest"]
    if receipt.get("locked_image_digest") != expected_image:
        raise ValueError(f"{name} does not use the locked arm64 image")
    if not isinstance(receipt.get("container_id"), str) or not receipt["container_id"]:
        raise ValueError(f"{name} does not record a container identity")


def command_has_option(command: list[str], option: str, value: str) -> bool:
    return any(
        argument == f"{option}={value}"
        or (argument == option and command[index + 1 : index + 2] == [value])
        for index, argument in enumerate(command)
    )


def effective_capabilities(receipt: dict, name: str) -> int:
    value = receipt.get("effective_capabilities")
    if isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]+", value):
        return int(value, 16)
    if type(value) is int and value >= 0:
        return value
    raise ValueError(f"{name} has an invalid effective capability mask")


def validate_qualification_receipt(
    receipt: dict, docker_build: dict, revision: str
) -> None:
    name = "Docker qualification receipt"
    validate_docker_receipt(receipt, name, revision)
    if receipt.get("image_id") != docker_build.get("image_id"):
        raise ValueError(f"{name} does not use the candidate build image")

    container_user = receipt.get("container_user")
    if not isinstance(container_user, str):
        raise ValueError(f"{name} does not record its main-container user")
    match = re.fullmatch(r"([0-9]+):([0-9]+)", container_user)
    if match is None or int(match.group(1)) == 0:
        raise ValueError(f"{name} did not run its main container as a non-root user")
    if receipt.get("cap_drop") != ["ALL"] or receipt.get("cap_add") != []:
        raise ValueError(f"{name} did not drop all main-container capabilities")
    if effective_capabilities(receipt, name) != 0:
        raise ValueError(f"{name} retained an effective main-container capability")
    command = receipt["command"]
    if not command_has_option(command, "--user", container_user):
        raise ValueError(f"{name} command does not match its non-root user record")
    if not command_has_option(command, "--cap-drop", "ALL"):
        raise ValueError(f"{name} command did not drop all main-container capabilities")
    if any(
        argument == "--privileged"
        or argument == "--cap-add"
        or argument.startswith("--cap-add=")
        for argument in command
    ):
        raise ValueError(f"{name} command enables privileged execution or added capabilities")

    volume = receipt.get("qualification_work_volume")
    if not isinstance(volume, dict):
        raise ValueError(f"{name} does not record its qualification work volume")
    volume_name = volume.get("name")
    if not isinstance(volume_name, str) or re.fullmatch(r"rtls-q-[0-9a-f]{12}", volume_name) is None:
        raise ValueError(f"{name} has an invalid qualification volume identity")
    volume_target = "/work/.work/tmp/q"
    if volume.get("target") != volume_target:
        raise ValueError(f"{name} has an unexpected qualification volume target")
    work_dir = volume.get("work_dir")
    if not isinstance(work_dir, str) or re.fullmatch(
        re.escape(volume_target) + r"/[0-9a-f]{8}", work_dir
    ) is None:
        raise ValueError(f"{name} has an invalid native qualification work directory")
    owner_uid, owner_gid = volume.get("owner_uid"), volume.get("owner_gid")
    if type(owner_uid) is not int or type(owner_gid) is not int or owner_uid == 0:
        raise ValueError(f"{name} has an invalid qualification volume owner")
    if (int(match.group(1)), int(match.group(2))) != (owner_uid, owner_gid):
        raise ValueError(f"{name} main user does not own its qualification work volume")

    account = volume.get("account")
    if not isinstance(account, dict):
        raise ValueError(f"{name} does not record its non-root account binding")
    username = account.get("username")
    home = account.get("home")
    if (
        not isinstance(username, str)
        or not username
        or username == "root"
        or username != volume_name
        or account.get("uid") != owner_uid
        or account.get("gid") != owner_gid
        or not isinstance(home, str)
        or not home.startswith("/")
    ):
        raise ValueError(f"{name} account binding does not match its non-root container user")
    require_digest(account.get("passwd_sha256"), f"{name} passwd SHA-256")
    require_digest(account.get("group_sha256"), f"{name} group SHA-256")
    if not any(
        f"target=/etc/passwd" in argument and "readonly" in argument
        for argument in command
    ) or not any(
        f"target=/etc/group" in argument and "readonly" in argument
        for argument in command
    ):
        raise ValueError(f"{name} does not mount its generated account files read-only")

    expected_mount = (
        f"type=volume,source={volume_name},target={volume_target},volume-nocopy"
    )
    if expected_mount not in command:
        raise ValueError(f"{name} command does not mount its recorded qualification volume")
    if not any(f"--work-dir {work_dir}" in argument for argument in command):
        raise ValueError(f"{name} did not use its recorded qualification work directory")

    initialization = volume.get("initialization")
    if not isinstance(initialization, dict):
        raise ValueError(f"{name} does not record qualification volume initialization")
    if (
        initialization.get("image_architecture") not in {"aarch64", "arm64"}
        or initialization.get("platform") not in {"linux", "linux/arm64"}
        or initialization.get("locked_image_digest") != receipt.get("locked_image_digest")
        or initialization.get("container_architecture") != "aarch64"
        or initialization.get("network_mode") != "none"
        or initialization.get("image_id") != receipt.get("image_id")
        or initialization.get("container_user") != "0:0"
        or initialization.get("owner_uid") != owner_uid
        or initialization.get("owner_gid") != owner_gid
        or initialization.get("cap_drop") != ["ALL"]
        or initialization.get("cap_add") != ["CAP_CHOWN"]
        or type(initialization.get("exit_code")) is not int
        or initialization["exit_code"] != 0
    ):
        raise ValueError(f"{name} volume initializer does not prove the expected native chown setup")
    if effective_capabilities(initialization, f"{name} volume initializer") != 1:
        raise ValueError(f"{name} volume initializer has capabilities beyond chown")
    initialization_id = initialization.get("container_id")
    if (
        not isinstance(initialization_id, str)
        or not initialization_id
        or initialization_id == receipt.get("container_id")
    ):
        raise ValueError(f"{name} volume initializer has no container identity")
    init_command = initialization.get("command")
    if not isinstance(init_command, list) or not init_command:
        raise ValueError(f"{name} volume initializer does not record its command")
    if (
        not command_has_option(init_command, "--network", "none")
        or not command_has_option(init_command, "--platform", "linux/arm64")
        or not command_has_option(init_command, "--user", "0:0")
        or not command_has_option(init_command, "--cap-drop", "ALL")
        or not command_has_option(init_command, "--cap-add", "CHOWN")
        or expected_mount not in init_command
    ):
        raise ValueError(f"{name} volume initializer command lacks the restricted native Docker setup")
    init_script = " ".join(init_command)
    if f"chown {owner_uid}:{owner_gid} {volume_target}" not in init_script or (
        f"chmod 0700 {volume_target}" not in init_script
    ):
        raise ValueError(f"{name} volume initializer did not assign the private work directory")


def validate_build_receipts(directory: Path, revision: str) -> dict:
    linux_build_path = directory / "linux-build.json"
    docker_build_path = directory / "docker-build.json"
    docker_runtime_path = directory / "docker-runtime.json"
    docker_qualification_path = directory / "docker-qualification.json"
    linux_build = json.loads(linux_build_path.read_text(encoding="utf-8"))
    docker_build = json.loads(docker_build_path.read_text(encoding="utf-8"))
    docker_runtime = json.loads(docker_runtime_path.read_text(encoding="utf-8"))
    docker_qualification = json.loads(docker_qualification_path.read_text(encoding="utf-8"))

    if linux_build.get("schema_version") != 1:
        raise ValueError("Linux build receipt has an unsupported schema")
    if linux_build.get("target") != "aarch64-unknown-linux-musl":
        raise ValueError("Linux build receipt has the wrong target")
    if linux_build.get("cpu_baseline") != "-march=armv8-a+crypto":
        raise ValueError("Linux build receipt has the wrong CPU baseline")
    if not {"aes", "pmull", "sha2", "asimd"}.issubset(linux_build.get("cpu_features", [])):
        raise ValueError("Linux build receipt does not prove the required ARM crypto features")
    if linux_build.get("source_revision") != revision:
        raise ValueError("Linux build receipt has the wrong source revision")
    if linux_build.get("pgo") is not False:
        raise ValueError("Linux build receipt unexpectedly enabled PGO")
    isolation = linux_build.get("isolation", {})
    if (
        isolation.get("build_mode") != "sealed"
        or isolation.get("mechanism") != "docker-network-none"
        or isolation.get("interfaces") != ["lo"]
        or isolation.get("default_routes") != []
    ):
        raise ValueError("Linux build receipt lacks network-disabled build evidence")

    validate_docker_receipt(docker_build, "Docker build receipt", revision)
    validate_docker_receipt(docker_runtime, "Docker runtime receipt", revision)
    validate_qualification_receipt(docker_qualification, docker_build, revision)
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
