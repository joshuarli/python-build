from __future__ import annotations

import json
import re
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

from resolve_release import resolve_release_tag, verify_existing_tag_target
from verify_uv_python import verify_identity


class ReleaseTagTests(unittest.TestCase):
    def test_empty_tag_defaults_to_utc_date(self) -> None:
        commit = "a" * 40
        now = datetime(2026, 10, 22, 1, tzinfo=timezone.utc)
        self.assertEqual(resolve_release_tag("", commit, commit, now), "20261022")

    def test_valid_tag_requires_matching_checkout_and_existing_ref(self) -> None:
        commit = "a" * 40
        self.assertEqual(
            resolve_release_tag("3.15.1-20261022", commit, commit),
            "3.15.1-20261022",
        )
        verify_existing_tag_target("3.15.1-20261022", commit, commit)

    def test_invalid_tag_and_mismatched_commit_fail(self) -> None:
        commit = "a" * 40
        with self.assertRaisesRegex(ValueError, "invalid release tag"):
            resolve_release_tag("$(touch bad)", commit, commit)
        with self.assertRaisesRegex(ValueError, "checked out commit"):
            resolve_release_tag("20261022", commit, "b" * 40)
        with self.assertRaisesRegex(ValueError, "different commit"):
            verify_existing_tag_target("20261022", commit, "b" * 40)
        with self.assertRaisesRegex(ValueError, "full commit hash"):
            resolve_release_tag("20261022", "deadbeef", "deadbeef")


class UvInterpreterTests(unittest.TestCase):
    def test_verifies_interpreter_identity_and_fresh_install_location(self) -> None:
        install_dir = ROOT / ".work" / "ci-test-install"
        verify_identity(
            install_dir,
            (3, 15, 1),
            (3, 15, 1),
            "linux",
            "aarch64",
            "cpython",
            "linux",
            "aarch64",
            install_dir / "bin" / "python3.15",
            install_dir,
        )

    def test_rejects_wrong_identity_version_and_paths(self) -> None:
        install_dir = ROOT / ".work" / "ci-test-install"
        arguments = (
            install_dir,
            (3, 15, 1),
            (3, 15, 1),
            "linux",
            "aarch64",
            "cpython",
            "linux",
            "aarch64",
            install_dir / "bin" / "python3.15",
            install_dir,
        )
        wrong_version = (*arguments[:2], (3, 15, 0), *arguments[3:])
        with self.assertRaisesRegex(ValueError, "Python version"):
            verify_identity(*wrong_version)
        wrong_machine = (*arguments[:4], "x86_64", *arguments[5:])
        with self.assertRaisesRegex(ValueError, "machine"):
            verify_identity(*wrong_machine)
        outside_install = (*arguments[:8], Path("/usr/bin/python3"), *arguments[9:])
        with self.assertRaisesRegex(ValueError, "escaped"):
            verify_identity(*outside_install)


class WorkflowContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text()

    def test_all_actions_use_full_commit_pins(self) -> None:
        references = re.findall(r"^\s+uses: ([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@([^\s]+)", self.workflow, re.M)
        self.assertTrue(references)
        for action, revision in references:
            with self.subTest(action=action):
                self.assertRegex(revision, r"\A[0-9a-f]{40}\Z")

    def test_preflight_validates_tag_and_runs_tests_before_builds(self) -> None:
        tests = self.workflow.index("- name: Run fast controller tests")
        macos_build = self.workflow.index("  build-macos:")
        linux_build = self.workflow.index("  build-linux:")
        self.assertLess(tests, macos_build)
        self.assertLess(tests, linux_build)
        self.assertIn("RELEASE_TAG_INPUT: ${{ inputs.release_tag }}", self.workflow)
        self.assertIn("python3.15 .github/scripts/resolve_release.py", self.workflow)
        self.assertIn("needs: [prepare]", self.workflow)
        self.assertNotIn('TAG="${{ inputs.release_tag }}"', self.workflow)

    def test_targets_and_release_gate_use_current_contract(self) -> None:
        self.assertIn('PYTHON_VERSION: "3.15.1"', self.workflow)
        self.assertEqual(self.workflow.count("runs-on: xcode-27"), 2)
        self.assertIn("runs-on: ubuntu-24.04", self.workflow)
        self.assertIn("runs-on: ubuntu-24.04-arm", self.workflow)
        self.assertIn("aarch64-apple-darwin", self.workflow)
        self.assertIn("x86_64-unknown-linux-musl", self.workflow)
        self.assertIn("aarch64-unknown-linux-musl", self.workflow)
        self.assertIn("backend/build-no-openssl.py", self.workflow)
        self.assertIn("backend/docker-linux.py", self.workflow)
        self.assertIn("build/promote_openssl_free.py", self.workflow)
        self.assertIn('gh release create "$RELEASE_TAG" --target "$GITHUB_SHA"', self.workflow)
        self.assertNotIn("GH_TOKEN", self.workflow.split("  publish:", 1)[0])
        self.assertNotIn("3.14", self.workflow)
        self.assertNotIn("macos-26", self.workflow)
        self.assertNotIn("1.2x", self.workflow)
        self.assertNotIn("python-build-standalone size", self.workflow)
        self.assertNotIn("brew update", self.workflow)
        self.assertNotIn("brew upgrade", self.workflow)
        self.assertNotIn("openssl-free-linux-arm64", self.workflow)

    def test_linux_smoke_images_match_locked_architecture_digests(self):
        lock = json.loads((ROOT / "bootstrap.lock.json").read_text())
        for arch in ("amd64", "arm64"):
            digest = lock["linux_toolchain"]["images"][arch]["digest"]
            with self.subTest(arch=arch):
                self.assertIn(f"runtime_image: alpine@{digest}", self.workflow)

    def test_build_jobs_bind_artifacts_to_the_checked_out_revision(self):
        self.assertIn("PYTHON_BUILD_SOURCE_REVISION: ${{ github.sha }}", self.workflow)
        self.assertIn("PYTHON_BUILD_SOURCE_DIRTY", self.workflow)
        self.assertIn('--source-revision "$GITHUB_SHA"', self.workflow)
        self.assertIn('--revision "$GITHUB_SHA"', self.workflow)
        self.assertIn("build/promote_openssl_free.py", self.workflow)

    def test_uv_smokes_verify_exact_assets_and_fresh_install_paths(self) -> None:
        self.assertIn("UV_VERSION: \"0.13.4\"", self.workflow)
        self.assertIn("shasum -a 256 --check", self.workflow)
        self.assertIn("sha256sum --check SHA256SUMS", self.workflow)
        self.assertIn("UV_PYTHON_INSTALL_DIR", self.workflow)
        self.assertIn("UV_PYTHON_CACHE_DIR", self.workflow)
        self.assertIn("UV_CACHE_DIR", self.workflow)
        self.assertIn("verify_uv_python.py", self.workflow)
        self.assertNotIn("uv/install.sh", self.workflow)


if __name__ == "__main__":
    unittest.main()
