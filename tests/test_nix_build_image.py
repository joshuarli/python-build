"""Unit tests for the optional, production-independent Nix image wrapper."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("nix_build_image", REPO / "nix/build_image.py")
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class NixBuilderTests(unittest.TestCase):
    def test_expected_apks_apply_overrides(self):
        base = {"linux_toolchain": {
            "base_packages": ["musl=1.2.6-r2", "busybox=1.0-r0"],
            "apk_closure": {"aarch64": [
                {"name": "musl", "version": "1.2.6-r6"},
                {"name": "clang23", "version": "23.1.3-r0"},
            ]},
        }}
        experiment = {"apk_closure": [{"name": "musl", "version": "1.2.6-r7"}]}
        self.assertEqual(builder.expected_apks(base, experiment, "aarch64"), {
            "busybox-1.0-r0", "clang23-23.1.3-r0", "musl-1.2.6-r7",
        })

    def test_input_identity_matches_original_docker_driver_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            exp = root / "backend"
            exp.mkdir(parents=True)
            (root / "bootstrap.lock.json").write_text(json.dumps({"linux_toolchain": {
                "images": {"arm64": {"platform": "linux/arm64"}},
                "base_packages": [], "apk_closure": {"aarch64": []},
            }}))
            lock = {"target": {
                "triple": "aarch64-unknown-linux-musl", "platform": "linux/arm64", "architecture": "aarch64",
            }, "apk_closure": [{"sha256": "a" * 64}], "rust": {
                "version": "1.100.0-nightly", "host": "aarch64-unknown-linux-musl",
                "components": [{"sha256": "b" * 64}],
            }}
            path = exp / "linux-bootstrap.lock.json"
            path.write_text(json.dumps(lock))
            with mock.patch.object(builder, "ROOT", root):
                _, _, identity = builder.inputs("arm64")
                expected = builder.canonical_digest({
                    "lock": builder.sha256(path), "inputs": ["a" * 64, "b" * 64],
                })
            self.assertEqual(identity, expected)

    def test_seed_cache_verifies_bytes_and_refuses_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            common = Path(tmp)
            source = common / "source.apk"
            source.write_bytes(b"pinned apk")
            pin = {"sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "size": 10}
            destination = common / ".cache/bootstrap/apk/arm64" / (pin["sha256"] + ".apk")
            builder._seed_one(common, source, destination, pin)
            self.assertEqual(destination.read_bytes(), source.read_bytes())
            destination.write_bytes(b"altered")
            with self.assertRaisesRegex(RuntimeError, "mismatch"):
                builder._seed_one(common, source, destination, pin)

    def test_native_daemon_is_mandatory(self):
        with mock.patch.object(builder, "output", return_value="linux|amd64"):
            builder.require_native("amd64")
            with self.assertRaisesRegex(RuntimeError, "native Linux arm64"):
                builder.require_native("arm64")
        with mock.patch.object(builder, "output", return_value="darwin|arm64"):
            with self.assertRaisesRegex(RuntimeError, "native Linux"):
                builder.require_native("arm64")

    def test_context_uses_locked_flake_without_mutating_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(builder, "ROOT", Path(tmp)), mock.patch.object(
                builder.subprocess, "check_output", return_value=tmp + "\n"
            ) as run:
                self.assertEqual(builder.nix_context("rtls-amd64"), Path(tmp))
                argv = run.call_args.args[0]
                self.assertIn("--no-update-lock-file", argv)
                self.assertIn("--no-link", argv)
                self.assertIn(".#rtls-amd64", argv)


if __name__ == "__main__":
    unittest.main()
