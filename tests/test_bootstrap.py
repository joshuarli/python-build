"""Toolchain lock and macOS toolchain construction (plan Section 4).

A lock that is never checked against the machine is a comment, so these tests
cover both halves: the lock parses, and a lock that disagrees with the host is
reported rather than silently used.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from buildsys.bootstrap import (
    BootstrapError, load_macos_toolchain, problems, toolchain_for,
)
from buildsys.targets import target_for_triple

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "bootstrap.lock.json"


class LockParsingTests(unittest.TestCase):
    def test_repository_lock_parses(self) -> None:
        toolchain = load_macos_toolchain(LOCK)
        self.assertTrue(toolchain.llvm_version)
        self.assertTrue(toolchain.deployment_target)
        self.assertTrue(toolchain.cpu_baseline)

    def test_missing_section_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lock.json"
            path.write_text(json.dumps({"alpine_release": "3.24.1"}))
            with self.assertRaises(BootstrapError):
                load_macos_toolchain(path)

    def test_malformed_json_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lock.json"
            path.write_text("{not json")
            with self.assertRaises(BootstrapError):
                load_macos_toolchain(path)

    def test_missing_field_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lock.json"
            path.write_text(json.dumps({"macos_toolchain": {"llvm": {}}}))
            with self.assertRaises(BootstrapError):
                load_macos_toolchain(path)


class ToolchainConstructionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.locked = load_macos_toolchain(LOCK)

    def test_recipe_toolchain_addresses_the_locked_llvm(self) -> None:
        toolchain = self.locked.toolchain()
        self.assertTrue(toolchain.is_macos)
        self.assertEqual(toolchain.cc, str(self.locked.llvm_prefix / "bin" / "clang"))
        self.assertEqual(toolchain.make, str(self.locked.make))
        self.assertEqual(toolchain.deployment_target, self.locked.deployment_target)

    def test_environment_pins_the_floor_and_sdk(self) -> None:
        env = self.locked.toolchain().env()
        self.assertEqual(env["MACOSX_DEPLOYMENT_TARGET"], self.locked.deployment_target)
        self.assertEqual(env["SDKROOT"], str(self.locked.sdkroot))

    def test_linker_is_left_to_the_clang_driver(self) -> None:
        # Naming LD is how a mismatched LLD gets paired with LLVM 23 bitcode
        # and rejected at link time (plan Section 5.1).
        self.assertNotIn("LD", self.locked.toolchain().env())

    def test_ambient_dyld_variables_are_scrubbed(self) -> None:
        # An inherited DYLD_* variable would substitute a different library
        # at link or run time without any change to the recipe (plan 7).
        import os
        os.environ["DYLD_INSERT_LIBRARIES"] = "/tmp/evil.dylib"
        os.environ["DYLD_LIBRARY_PATH"] = "/tmp/evil"
        try:
            env = self.locked.toolchain().env()
        finally:
            del os.environ["DYLD_INSERT_LIBRARIES"]
            del os.environ["DYLD_LIBRARY_PATH"]
        self.assertNotIn("DYLD_INSERT_LIBRARIES", env)
        self.assertNotIn("DYLD_LIBRARY_PATH", env)

    def test_flags_carry_the_deployment_floor(self) -> None:
        toolchain = self.locked.toolchain()
        self.assertIn(f"-mmacosx-version-min={self.locked.deployment_target}",
                      toolchain.cflags())
        self.assertIn(f"-mmacosx-version-min={self.locked.deployment_target}",
                      toolchain.ldflags(Path("/private")))
        self.assertIn(self.locked.cpu_baseline, toolchain.cflags())

    def test_no_elf_loader_flags_leak_into_macos_flags(self) -> None:
        toolchain = self.locked.toolchain()
        flags = toolchain.cflags() + toolchain.ldflags(Path("/private"))
        self.assertNotIn("noexecstack", flags)
        self.assertNotIn("build-id", flags)
        self.assertNotIn("FORTIFY", flags)


class LockAgainstMachineTests(unittest.TestCase):
    def test_repository_lock_matches_this_machine(self) -> None:
        locked = load_macos_toolchain(LOCK)
        found = problems(locked, host_floor=locked.deployment_target)
        self.assertEqual(found, [], f"toolchain lock disagrees with host: {found}")

    def test_wrong_compiler_version_is_reported(self) -> None:
        import dataclasses
        locked = load_macos_toolchain(LOCK)
        stale = dataclasses.replace(locked, llvm_version="0.0.1-nonexistent")
        self.assertTrue(any("0.0.1-nonexistent" in problem for problem in problems(stale)))

    def test_missing_sdk_is_reported(self) -> None:
        import dataclasses
        locked = load_macos_toolchain(LOCK)
        broken = dataclasses.replace(locked, sdkroot=Path("/nonexistent/SDK"))
        self.assertTrue(any("SDK not found" in problem for problem in problems(broken)))

    def test_host_below_floor_is_reported(self) -> None:
        locked = load_macos_toolchain(LOCK)
        found = problems(locked, host_floor="999.0")
        self.assertTrue(any("floor" in problem for problem in found))


class LtoSmokeGateTests(unittest.TestCase):
    """The gate plan Section 5.1 requires before any dependency build."""

    def test_locked_toolchain_builds_and_runs_thinlto(self) -> None:
        from buildsys.bootstrap import lto_smoke_test
        locked = load_macos_toolchain(LOCK)
        if problems(locked, host_floor=locked.deployment_target):
            self.skipTest("toolchain lock does not match this machine")
        with tempfile.TemporaryDirectory() as temporary:
            report = lto_smoke_test(locked.toolchain(), Path(temporary))
        self.assertEqual(report["arch"], "arm64")
        self.assertEqual(report["minos"], locked.deployment_target)
        self.assertTrue(report["runs"])


class ToolchainSelectionTests(unittest.TestCase):
    def test_linux_targets_keep_the_bare_name_toolchain(self) -> None:
        toolchain = toolchain_for(target_for_triple("x86_64-unknown-linux-musl"), LOCK)
        self.assertFalse(toolchain.is_macos)
        self.assertEqual(toolchain.cc, "clang")
        self.assertEqual(toolchain.ld, "ld.lld")
        self.assertEqual(toolchain.env()["LD"], "ld.lld")

    def test_macos_target_resolves_from_the_lock(self) -> None:
        toolchain = toolchain_for(target_for_triple("aarch64-apple-darwin"), LOCK)
        self.assertTrue(toolchain.is_macos)
        self.assertTrue(Path(toolchain.cc).is_absolute())


if __name__ == "__main__":
    unittest.main()
