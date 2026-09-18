"""Target description registry (plan Section 12)."""
from __future__ import annotations

import unittest

from buildsys.targets import TARGETS, UnsupportedTargetError, target_for_triple


class TargetRegistryTests(unittest.TestCase):
    def test_x86_64_and_aarch64_are_both_described(self) -> None:
        self.assertIn("x86_64-unknown-linux-musl", TARGETS)
        self.assertIn("aarch64-unknown-linux-musl", TARGETS)

    def test_each_target_has_distinct_musl_loader_and_openssl_name(self) -> None:
        loaders = {t.musl_loader for t in TARGETS.values()}
        openssl_targets = {t.openssl_configure_target for t in TARGETS.values()}
        self.assertEqual(len(loaders), len(TARGETS))
        self.assertEqual(len(openssl_targets), len(TARGETS))

    def test_unknown_triple_fails_closed(self) -> None:
        with self.assertRaises(UnsupportedTargetError):
            target_for_triple("riscv64-unknown-linux-musl")

    def test_target_for_triple_round_trips(self) -> None:
        target = target_for_triple("aarch64-unknown-linux-musl")
        self.assertEqual(target.machine, "aarch64")
        self.assertEqual(target.docker_platform, "linux/arm64")


if __name__ == "__main__":
    unittest.main()
