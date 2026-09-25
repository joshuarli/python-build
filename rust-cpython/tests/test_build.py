from __future__ import annotations

import importlib.util
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "rust_cpython_build", ROOT / "rust-cpython" / "build.py"
)
assert SPEC is not None and SPEC.loader is not None
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


class SourcePinTests(unittest.TestCase):
    def test_source_archive_and_cargo_lock_are_exactly_pinned(self) -> None:
        metadata, archive = build._read_lock()
        self.assertEqual(metadata["repository"], "https://github.com/Rust-for-CPython/cpython")
        self.assertEqual(metadata["commit"], "b812b4a7b9efaca46b98544a8633b7d7e454166b")
        self.assertEqual(metadata["version"], "3.16.0a0")
        self.assertEqual(
            archive.url,
            "https://codeload.github.com/Rust-for-CPython/cpython/tar.gz/"
            "b812b4a7b9efaca46b98544a8633b7d7e454166b",
        )
        self.assertEqual(
            metadata["cargo_lock_sha256"],
            "55f5f3bf547d3b9e7896a5feb6d17aa3b607610c7c21d919164f0877a8d05023",
        )
        self.assertEqual(archive.role, "build-source")
        # The source archive predates the Linux lane and is platform independent.
        self.assertEqual(archive.target, "aarch64-apple-darwin")
        self.assertIn(archive.target, build.LANE_TARGETS)

    def test_source_tree_rejects_a_different_cargo_lock(self) -> None:
        metadata = {"cargo_lock_sha256": "0" * 64}
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "cpython"
            source.mkdir()
            for name in ("configure", "Cargo.toml", "Cargo.lock", "Lib", "Modules"):
                path = source / name
                path.mkdir() if name in {"Lib", "Modules"} else path.write_text("locked\n")
            patch_header = source / "Include" / "patchlevel.h"
            patch_header.parent.mkdir()
            patch_header.write_text("/* version */\n")
            with patch.object(build, "_read_lock", return_value=(metadata, None)):
                with self.assertRaisesRegex(build.LaneError, "Cargo.lock digest"):
                    build._source_root(source.parent)


class SourcePatchTests(unittest.TestCase):
    def _fixture(self, root: Path, patch_text: str) -> tuple[Path, Path]:
        source = root / "source"
        source.mkdir()
        (source / "Lib").mkdir()
        (source / "Lib" / "example.py").write_text("before\n")
        (source / "Cargo.lock").write_text("locked\n")
        patches = root / "patches"
        patches.mkdir()
        (patches / "example.patch").write_text(patch_text)
        manifest = {
            "source_commit": "pinned-commit",
            "patches": [{
                "file": "example.patch",
                "sha256": hashlib.sha256(patch_text.encode()).hexdigest(),
                "author": "Experiment author",
                "origin": "local experiment",
                "license": "PSF-2.0",
                "reason": "Exercise a reproducible source edit",
                "compatibility": "Pinned source has before in Lib/example.py",
                "reproducer": "Run SourcePatchTests against the pinned source fixture",
            }],
        }
        (patches / "manifest.json").write_text(json.dumps(manifest))
        return source, patches / "manifest.json"

    def test_patch_applies_and_reports_exact_inputs(self) -> None:
        diff = "--- a/Lib/example.py\n+++ b/Lib/example.py\n@@ -1 +1 @@\n-before\n+after\n"
        with tempfile.TemporaryDirectory() as temporary:
            source, manifest = self._fixture(Path(temporary), diff)
            with (
                patch.object(build, "PATCH_MANIFEST", manifest),
                patch.object(build, "_read_lock", return_value=(
                    {"commit": "pinned-commit", "cargo_lock_sha256": hashlib.sha256(b"locked\n").hexdigest()}, None,
                )),
            ):
                report = build._apply_source_patches(source)
            self.assertEqual((source / "Lib" / "example.py").read_text(), "after\n")
            self.assertEqual(report["manifest_sha256"], hashlib.sha256(manifest.read_bytes()).hexdigest())
            self.assertEqual(report["patches"][0]["sha256"], hashlib.sha256(diff.encode()).hexdigest())

    def test_patch_applies_inside_outer_git_worktree(self) -> None:
        diff = (
            "diff --git a/Lib/example.py b/Lib/example.py\n"
            "--- a/Lib/example.py\n+++ b/Lib/example.py\n@@ -1 +1 @@\n-before\n+after\n"
        )
        work = ROOT / "rust-cpython" / "work"
        work.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work) as temporary:
            source, manifest = self._fixture(Path(temporary), diff)
            lock = {"commit": "pinned-commit", "cargo_lock_sha256": hashlib.sha256(b"locked\n").hexdigest()}
            with patch.object(build, "PATCH_MANIFEST", manifest), patch.object(build, "_read_lock", return_value=(lock, None)):
                build._apply_source_patches(source)
            self.assertEqual((source / "Lib" / "example.py").read_text(), "after\n")

    def test_patch_rejects_drift_without_fuzzy_application(self) -> None:
        diff = "--- a/Lib/example.py\n+++ b/Lib/example.py\n@@ -1 +1 @@\n-before\n+after\n"
        with tempfile.TemporaryDirectory() as temporary:
            source, manifest = self._fixture(Path(temporary), diff)
            (source / "Lib" / "example.py").write_text("changed\n")
            with (
                patch.object(build, "PATCH_MANIFEST", manifest),
                patch.object(build, "_read_lock", return_value=(
                    {"commit": "pinned-commit", "cargo_lock_sha256": hashlib.sha256(b"locked\n").hexdigest()}, None,
                )),
            ):
                with self.assertRaisesRegex(build.LaneError, "does not apply"):
                    build._apply_source_patches(source)
            self.assertEqual((source / "Lib" / "example.py").read_text(), "changed\n")

    def test_patch_rejects_changed_digest_and_source_pin(self) -> None:
        diff = "--- a/Lib/example.py\n+++ b/Lib/example.py\n@@ -1 +1 @@\n-before\n+after\n"
        with tempfile.TemporaryDirectory() as temporary:
            source, manifest = self._fixture(Path(temporary), diff)
            lock = {"commit": "pinned-commit", "cargo_lock_sha256": hashlib.sha256(b"locked\n").hexdigest()}
            (manifest.parent / "example.patch").write_text(diff + "# changed\n")
            with patch.object(build, "PATCH_MANIFEST", manifest), patch.object(build, "_read_lock", return_value=(lock, None)):
                with self.assertRaisesRegex(build.LaneError, "digest"):
                    build._apply_source_patches(source)
            (manifest.parent / "example.patch").write_text(diff)
            lock["commit"] = "different-commit"
            with patch.object(build, "PATCH_MANIFEST", manifest), patch.object(build, "_read_lock", return_value=(lock, None)):
                with self.assertRaisesRegex(build.LaneError, "source commit"):
                    build._apply_source_patches(source)

    def test_patch_cannot_change_cargo_lock(self) -> None:
        diff = "--- a/Cargo.lock\n+++ b/Cargo.lock\n@@ -1 +1 @@\n-locked\n+changed\n"
        with tempfile.TemporaryDirectory() as temporary:
            source, manifest = self._fixture(Path(temporary), diff)
            lock = {"commit": "pinned-commit", "cargo_lock_sha256": hashlib.sha256(b"locked\n").hexdigest()}
            with patch.object(build, "PATCH_MANIFEST", manifest), patch.object(build, "_read_lock", return_value=(lock, None)):
                with self.assertRaisesRegex(build.LaneError, "changed the pinned Cargo.lock"):
                    build._apply_source_patches(source)

    def test_patch_cannot_escape_source_tree(self) -> None:
        diff = "--- a/../outside\n+++ b/../outside\n@@ -1 +1 @@\n-before\n+after\n"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, manifest = self._fixture(root, diff)
            (root / "outside").write_text("before\n")
            lock = {"commit": "pinned-commit", "cargo_lock_sha256": hashlib.sha256(b"locked\n").hexdigest()}
            with patch.object(build, "PATCH_MANIFEST", manifest), patch.object(build, "_read_lock", return_value=(lock, None)):
                with self.assertRaisesRegex(build.LaneError, "does not apply"):
                    build._apply_source_patches(source)
            self.assertEqual((root / "outside").read_text(), "before\n")

    def test_test_command_rejects_changed_patch_inputs_with_existing_source(self) -> None:
        diff = "--- a/Lib/example.py\n+++ b/Lib/example.py\n@@ -1 +1 @@\n-before\n+after\n"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, manifest = self._fixture(root, diff)
            (source / "Cargo.toml").write_text("[workspace]\n")
            python = root / "python"
            python.write_text("")
            report_path = root / "build.json"
            lock = {"commit": "pinned-commit", "cargo_lock_sha256": hashlib.sha256(b"locked\n").hexdigest()}
            with (
                patch.object(build, "PATCH_MANIFEST", manifest),
                patch.object(build, "_read_lock", return_value=(lock, None)),
                patch.object(build, "SOURCE", source),
                patch.object(build, "BUILD_REPORT", report_path),
                patch.object(build, "_build_python", return_value=python),
                patch.object(build, "_require_host"),
            ):
                original_inputs = build._source_patch_inputs()
                report_path.write_text(json.dumps({"status": "built", "source": {"patches": original_inputs}}))
                (manifest.parent / "example.patch").write_text(diff + "# changed\n")
                with self.assertRaisesRegex(build.LaneError, "digest"):
                    build.test()
                (manifest.parent / "example.patch").write_text(diff)
                document = json.loads(manifest.read_text())
                document["patches"][0]["reason"] = "Changed experiment meaning"
                manifest.write_text(json.dumps(document))
                with self.assertRaisesRegex(build.LaneError, "disagree with the completed build report"):
                    build.test()


class ToolchainIsolationTests(unittest.TestCase):
    def test_generated_cargo_entrypoint_runs_only_the_pinned_nightly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            private_home = Path(temporary) / "private cargo home"
            rustup = str(Path(temporary) / "rust tools" / "rustup")
            with patch.object(build, "CARGO_HOME", private_home):
                wrapper = build._cargo_wrapper(rustup)
            self.assertEqual(
                wrapper.read_text(),
                "#!/bin/sh\nexec "
                f"{build.shlex.quote(rustup)} run nightly-2026-09-15 cargo \"$@\"\n",
            )
            self.assertTrue(wrapper.stat().st_mode & 0o111)

    def test_build_environment_forces_private_offline_cargo_and_nightly(self) -> None:
        toolchain, _target = build._toolchain()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                patch.object(build, "CARGO_HOME", root / "cargo"),
                patch.object(build, "WORK", root / "work"),
            ):
                env = build._environment(toolchain, offline=True, build_dir=root / "build")
        self.assertEqual(env["RUSTUP_TOOLCHAIN"], "nightly-2026-09-15")
        self.assertEqual(env["CARGO_HOME"], str(root / "cargo"))
        self.assertEqual(env["CARGO_NET_OFFLINE"], "true")
        self.assertEqual(env["CARGO_TARGET_DIR"], str(root / "build" / "target"))
        self.assertEqual(env["PATH"].split(":")[0], str(root / "cargo" / "bin"))
        self.assertEqual(
            env["BINDGEN_EXTRA_CLANG_ARGS"],
            f"-resource-dir={toolchain.llvm_resource_dir}",
        )

    def test_cpython_test_environment_can_write_into_the_isolated_cache(self) -> None:
        toolchain, _target = build._toolchain()
        with patch.object(
            build,
            "_environment",
            return_value={
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPYCACHEPREFIX": "/isolated/pycache",
                "CARGO_NET_OFFLINE": "true",
            },
        ):
            env = build._test_environment(toolchain)
        self.assertNotIn("PYTHONDONTWRITEBYTECODE", env)
        self.assertEqual(env["PYTHONPYCACHEPREFIX"], "/isolated/pycache")
        self.assertEqual(env["CARGO_NET_OFFLINE"], "true")


class VariantTests(unittest.TestCase):
    def test_variant_outputs_do_not_overlap_the_default_candidate(self) -> None:
        names = ("VARIANT", "SOURCE", "BUILD", "STAGE", "LOGS", "BUILD_REPORT",
                 "ZLIB_SOURCE", "ZLIB_TARGET", "ZLIB_ARCHIVE")
        saved = {name: getattr(build, name) for name in names}
        try:
            build._select_variant("prior-fork")
            self.assertEqual(build.STAGE, build.LANE / "stage-prior-fork")
            self.assertEqual(build.BUILD, build.WORK / "variants" / "prior-fork" / "build")
            self.assertEqual(build.BUILD_REPORT, build.RESULTS / "build-prior-fork.json")
            for name in names[1:]:
                self.assertNotEqual(getattr(build, name), saved[name])
        finally:
            for name, value in saved.items():
                setattr(build, name, value)

    def test_variant_names_are_restricted(self) -> None:
        for name in ("../x", "Upper", "no-rust", "a" * 41):
            with self.assertRaises(build.LaneError):
                build._select_variant(name)


class BuildConfigurationTests(unittest.TestCase):
    def test_pgo_and_thinlto_configuration_matches_the_python_build_policy(self) -> None:
        toolchain, target = build._toolchain()
        with (
            patch.object(build, "_environment", return_value={}),
            patch.object(build, "_brew_pkg_config_path", return_value=""),
        ):
            args, env = build._configuration(toolchain, target, jobs=7)
        self.assertIn("--enable-optimizations", args)
        self.assertIn("--with-lto=thin", args)
        self.assertIn("--enable-experimental-jit=no", args)
        self.assertIn("--with-tail-call-interp=no", args)
        self.assertIn("--without-ensurepip", args)
        self.assertEqual(env["PROFILE_TASK"], "-m test --pgo -j 7")
        self.assertEqual(env["LLVM_PROFDATA"], str(toolchain.llvm_profdata))
        self.assertIn("-O3", env["CFLAGS"])
        self.assertIn(target.cpu_baseline_cflag, env["CFLAGS"])
        self.assertNotIn("RUSTFLAGS", env)
        if build.IS_LINUX:
            self.assertEqual(target.cpu_baseline_cflag, "-march=x86-64")
            self.assertEqual(env["CPPFLAGS"], "")
            self.assertEqual(env["LDFLAGS"], f"-fuse-ld=lld -Wl,-rpath,{build.STAGE / 'lib'}")
            self.assertEqual(env["PKG_CONFIG_PATH"], "")
            return
        sysroot_flag = f"-isysroot {toolchain.sdkroot}"
        self.assertEqual(env["CPPFLAGS"], sysroot_flag)
        self.assertEqual(env["PY_CPPFLAGS"], sysroot_flag)
        self.assertIn(
            f"-mmacosx-version-min={toolchain.deployment_target}", env["CFLAGS"]
        )

    def test_host_selects_one_lane_target(self) -> None:
        self.assertIn(build.TARGET, build.LANE_TARGETS)
        self.assertEqual(build.SYMBOL_PREFIX, "" if build.IS_LINUX else "_")
        self.assertEqual(
            build._cargo_linker_variable(),
            "CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER" if build.IS_LINUX
            else "CARGO_TARGET_AARCH64_APPLE_DARWIN_LINKER",
        )

    def test_pgo_worker_count_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            build._profile_task(0)

    def test_test_runner_caps_parallel_workers(self) -> None:
        with patch.object(build.os, "cpu_count", return_value=64):
            self.assertEqual(build._test_jobs(), 4)
        with patch.object(build.os, "cpu_count", return_value=2):
            self.assertEqual(build._test_jobs(), 1)

    def test_build_interpreter_name_uses_the_makefile_extension(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            build_dir = Path(temporary)
            (build_dir / "Makefile").write_text(
                "BUILDPYTHON=\tpython$(BUILDEXE)\nBUILDEXE=\t.exe\n"
            )
            with patch.object(build, "BUILD", build_dir):
                self.assertEqual(build._build_python(), build_dir / "python.exe")


if __name__ == "__main__":
    unittest.main()
