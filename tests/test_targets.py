"""Target description registry."""
from __future__ import annotations

import unittest

from buildsys.targets import (
    MACOS, TARGETS, UnsupportedTargetError, native_target, target_for_triple,
)

LINUX_TRIPLES = ("x86_64-unknown-linux-musl", "aarch64-unknown-linux-musl")
MACOS_TRIPLE = "aarch64-apple-darwin"


def _family(family: str):
    return [t for t in TARGETS.values() if t.family == family]


class TargetRegistryTests(unittest.TestCase):
    def test_both_linux_triples_are_described(self) -> None:
        self.assertIn("x86_64-unknown-linux-musl", TARGETS)
        self.assertIn("aarch64-unknown-linux-musl", TARGETS)

    def test_macos_arm64_is_described(self) -> None:
        target = target_for_triple(MACOS_TRIPLE)
        self.assertEqual(target.machine, "arm64")
        self.assertEqual(target.family, MACOS)
        self.assertTrue(target.is_macos)

    def test_macos_target_declares_a_deployment_floor_and_baseline(self) -> None:
        target = target_for_triple(MACOS_TRIPLE)
        self.assertEqual(target.deployment_target, "26.0")
        self.assertEqual(target.cpu_baseline_cflag, "-mcpu=apple-m1")
        # The PEP 425 tag prefix must agree with the declared floor, or the
        # build would advertise wheels for macOS releases its own
        # LC_BUILD_VERSION refuses to load on.
        self.assertEqual(target.platform_tag_prefix, "macosx_26_0")

    def test_each_linux_target_has_distinct_loader_and_openssl_name(self) -> None:
        linux = _family("linux-musl")
        self.assertEqual(len({t.musl_loader for t in linux}), len(linux))
        self.assertEqual(len({t.openssl_configure_target for t in linux}), len(linux))

    def test_openssl_names_are_distinct_across_every_target(self) -> None:
        names = {t.openssl_configure_target for t in TARGETS.values()}
        self.assertEqual(len(names), len(TARGETS))

    def test_family_specific_fields_are_not_populated_on_the_other_family(self) -> None:
        self.assertEqual(target_for_triple(MACOS_TRIPLE).musl_loader, "")
        self.assertEqual(target_for_triple(MACOS_TRIPLE).docker_platform, "")
        self.assertEqual(target_for_triple("x86_64-unknown-linux-musl").deployment_target, "")

    def test_incomplete_target_is_rejected_at_construction(self) -> None:
        from buildsys.targets import Target

        with self.assertRaises(UnsupportedTargetError):
            Target(triple="x", machine="x", family=MACOS, cpu_baseline_cflag="",
                   openssl_configure_target="")
        with self.assertRaises(UnsupportedTargetError):
            Target(triple="x", machine="x", family="linux-musl", cpu_baseline_cflag="",
                   openssl_configure_target="")
        with self.assertRaises(UnsupportedTargetError):
            Target(triple="x", machine="x", family="plan9", cpu_baseline_cflag="",
                   openssl_configure_target="")

    def test_unknown_triple_fails_closed(self) -> None:
        with self.assertRaises(UnsupportedTargetError):
            target_for_triple("riscv64-unknown-linux-musl")

    def test_target_for_triple_round_trips(self) -> None:
        target = target_for_triple("aarch64-unknown-linux-musl")
        self.assertEqual(target.machine, "aarch64")
        self.assertEqual(target.docker_platform, "linux/arm64")

    def test_native_target_matches_this_host(self) -> None:
        # Whatever this test runs on, native_target() must describe it —
        # otherwise every native-execution command fails closed.
        target = native_target()
        self.assertEqual(target, target_for_triple(target.triple))


if __name__ == "__main__":
    unittest.main()
