#!/usr/bin/env python3
"""Materialize the pinned Nix bootstrap contexts as native Linux Docker images.

Nix verifies and supplies the bytes; the repository's existing Dockerfiles
install them. This is deliberately separate from the production builder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "amd64": ("x86_64", "linux/amd64", "x86_64-unknown-linux-musl", "linux-bootstrap-x86_64.json"),
    "arm64": ("aarch64", "linux/arm64", "aarch64-unknown-linux-musl", "linux-bootstrap.lock.json"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def inputs(arch: str) -> tuple[dict, dict, str]:
    machine, platform, triple, lock_name = TARGETS[arch]
    base = json.loads((ROOT / "bootstrap.lock.json").read_text())
    lock_path = ROOT / "research/rtls-graviola" / lock_name
    experiment = json.loads(lock_path.read_text())
    assert experiment["target"] == {
        "triple": triple, "platform": platform, "architecture": machine,
    }
    assert base["linux_toolchain"]["images"][arch]["platform"] == platform
    digest = canonical_digest({
        "lock": sha256(lock_path),
        "inputs": sorted(
            [item["sha256"] for item in experiment["apk_closure"]]
            + [item["sha256"] for item in experiment["rust"]["components"]]
        ),
    })
    return base, experiment, digest


def expected_apks(base: dict, experiment: dict, machine: str) -> set[str]:
    combined = dict(item.split("=", 1) for item in base["linux_toolchain"]["base_packages"])
    combined.update({
        item["name"]: item["version"]
        for item in base["linux_toolchain"]["apk_closure"][machine]
    })
    combined.update({item["name"]: item["version"] for item in experiment["apk_closure"]})
    return {f"{name}-{version}" for name, version in combined.items()}


def output(argv: list[str]) -> str:
    return subprocess.check_output(argv, text=True, cwd=ROOT).strip()


def nix_context(name: str) -> Path:
    value = output([
        "nix", "--extra-experimental-features", "nix-command flakes",
        "build", "--no-update-lock-file", "--no-link", "--print-out-paths", f".#{name}",
    ])
    paths = value.splitlines()
    if len(paths) != 1 or not Path(paths[0]).is_dir():
        raise RuntimeError(f"expected one Nix context directory for {name}: {value!r}")
    return Path(paths[0])


def image_info(image: str) -> dict:
    result = json.loads(output(["docker", "image", "inspect", image]))
    if len(result) != 1:
        raise RuntimeError(f"expected exactly one image for {image}")
    return result[0]


def require_native(arch: str) -> None:
    daemon = output(["docker", "info", "--format", "{{.OSType}}|{{.Architecture}}"])
    expected = {"amd64": {"amd64", "x86_64"}, "arm64": {"arm64", "aarch64"}}
    try:
        os_name, machine = daemon.split("|", 1)
    except ValueError as exc:
        raise RuntimeError(f"unexpected Docker daemon response: {daemon}") from exc
    if os_name != "linux" or machine not in expected[arch]:
        raise RuntimeError(f"native Linux {arch} Docker daemon required; found {daemon}")


def _verify_cached(path: Path, pin: dict) -> None:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"missing or unsafe pinned input: {path}")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != pin["sha256"] or ("size" in pin and path.stat().st_size != pin["size"]):
        raise RuntimeError(f"pinned input hash/size mismatch: {path}")


def _seed_one(common: Path, source: Path, destination: Path, pin: dict) -> None:
    _verify_cached(source, pin)
    current = common
    for part in destination.relative_to(common).parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise RuntimeError(f"unsafe symlink in bootstrap cache: {current}")
        current.mkdir(exist_ok=True)
    if destination.exists() or destination.is_symlink():
        _verify_cached(destination, pin)
        return
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        shutil.copyfile(source, temporary)
        _verify_cached(temporary, pin)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def seed_input_cache(arch: str, base_context: Path, overlay_context: Path,
                     base: dict, experiment: dict) -> None:
    # The original Docker driver still verifies its own cache before sealed
    # execution. Seed it from independently hash-verified Nix context bytes.
    git_dir = Path(output([
        "git", "rev-parse", "--path-format=absolute", "--git-common-dir",
    ]))
    common = git_dir.resolve().parent
    machine = TARGETS[arch][0]
    for item in base["linux_toolchain"]["apk_closure"][machine]:
        name = f"{item['sha256']}.apk"
        _seed_one(common, base_context / ".cache/bootstrap/apk" / arch / name,
                  common / ".cache/bootstrap/apk" / arch / name, item)
    for item in experiment["apk_closure"]:
        name = f"{item['sha256']}.apk"
        _seed_one(common, overlay_context / ".cache/bootstrap/rtls-linux/apk" / name,
                  common / ".cache/bootstrap" / f"rtls-linux-{arch}" / "apk" / name, item)
    for item in experiment["rust"]["components"]:
        _seed_one(common, overlay_context / ".cache/bootstrap/rtls-linux/rust" / item["file"],
                  common / ".cache/bootstrap" / f"rtls-linux-{arch}" / "rust" / item["file"], item)


def build(arch: str, record_path: Path) -> dict:
    require_native(arch)
    base, experiment, input_digest = inputs(arch)
    machine, platform, triple, _ = TARGETS[arch]
    base_context = nix_context(f"base-{arch}")
    overlay_context = nix_context(f"rtls-{arch}")
    base_tag = f"python-build-nix-{arch}:base-{base_context.name.split('-', 1)[0]}"
    overlay_tag = f"python-build-nix-{arch}:rtls-{overlay_context.name.split('-', 1)[0]}"
    base_digest = base["linux_toolchain"]["images"][arch]["digest"]
    seed_input_cache(arch, base_context, overlay_context, base, experiment)

    subprocess.run([
        "docker", "build", "--platform", platform, "--network", "none",
        "--target", "toolchain", "--tag", base_tag, str(base_context),
    ], cwd=ROOT, check=True)
    subprocess.run([
        "docker", "build", "--platform", platform, "--network", "none",
        "--target", "experimental-toolchain", "--tag", overlay_tag,
        "--file", str(overlay_context / "Dockerfile.linux"),
        "--build-arg", f"TOOLCHAIN_IMAGE={base_tag}",
        "--build-arg", f"RUNTIME_BASE_IMAGE=alpine@{base_digest}",
        "--build-arg", f"LOCKED_IMAGE_DIGEST={base_digest}",
        "--build-arg", f"BOOTSTRAP_INPUTS_SHA256={input_digest}",
        "--build-arg", f"EXPECTED_TRIPLE={triple}",
        "--build-arg", f"EXPECTED_PLATFORM={platform}",
        "--build-arg", f"EXPECTED_MACHINE={machine}",
        str(overlay_context),
    ], cwd=ROOT, check=True)

    base_image = image_info(base_tag)
    image = image_info(overlay_tag)
    if base_image["Os"] != "linux" or base_image["Architecture"] not in {arch, machine}:
        raise RuntimeError("Nix-produced base image architecture mismatch")
    if image["Os"] != "linux" or image["Architecture"] not in {arch, machine}:
        raise RuntimeError("Nix-produced RTLS image architecture mismatch")
    labels = image["Config"].get("Labels") or {}
    if labels.get("org.python-build.rtls.locked-image-digest") != base_digest:
        raise RuntimeError("RTLS image has an incorrect base-image lock label")
    if labels.get("org.python-build.rtls.bootstrap-inputs-sha256") != input_digest:
        raise RuntimeError("RTLS image has an incorrect bootstrap-input lock label")

    installed = set(output([
        "docker", "run", "--rm", "--platform", platform, "--network", "none",
        overlay_tag, "apk", "info", "-v",
    ]).splitlines())
    expected = expected_apks(base, experiment, machine)
    if installed != expected:
        raise RuntimeError(f"APK closure mismatch: missing={sorted(expected-installed)} extra={sorted(installed-expected)}")
    probe = output([
        "docker", "run", "--rm", "--platform", platform, "--network", "none",
        overlay_tag, "sh", "-ec", "clang --version | head -n 1; rustc -vV",
    ])
    if "clang version 23.1.3" not in probe:
        raise RuntimeError(f"unexpected compiler: {probe}")
    if f"release: {experiment['rust']['version']}" not in probe or f"host: {experiment['rust']['host']}" not in probe:
        raise RuntimeError(f"unexpected Rust toolchain: {probe}")

    result = {
        "schema": 1,
        "status": "builder-environment-verified-not-release-qualified",
        "target": triple,
        "platform": platform,
        "nixpkgs_lock_sha256": sha256(ROOT / "flake.lock"),
        "base_context": str(base_context),
        "overlay_context": str(overlay_context),
        "alpine_base_digest": base_digest,
        "bootstrap_inputs_sha256": input_digest,
        "base_image": base_tag,
        "base_image_id": base_image["Id"],
        "toolchain_image": overlay_tag,
        "toolchain_image_id": image["Id"],
        "installed_apks": sorted(installed),
        "toolchain_probe": probe.splitlines(),
    }
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", choices=TARGETS, required=True)
    parser.add_argument("--record", type=Path, help="JSON provenance output (defaults under .work/tmp)")
    args = parser.parse_args()
    record_path = args.record or ROOT / ".work/tmp" / f"nix-toolchain-{args.arch}.json"
    try:
        result = build(args.arch, record_path)
    except (OSError, KeyError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Nix toolchain prototype failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "record": str(record_path),
        "PYTHON_BUILD_NIX_BASE_IMAGE": result["base_image"],
        "PYTHON_BUILD_NIX_TOOLCHAIN_IMAGE": result["toolchain_image"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
