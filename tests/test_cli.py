"""Exercise the public controller without invoking native compilation."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from buildsys.targets import TARGETS, native_target  # noqa: E402


class CLITests(unittest.TestCase):
    def invoke(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'build.py'), *args],
                              cwd=ROOT, text=True, capture_output=True)

    def test_unsupported_target_fails_before_building(self):
        result = self.invoke('build', '--target', 'riscv64-unknown-linux-musl', '--dev')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('not implemented', result.stderr)

    def test_cross_arch_target_is_rejected_not_cross_compiled(self):
        # Every SUPPORTED target other than the one this test process is
        # actually running as (plan Section 12: never cross-compile) must
        # be rejected clearly rather than silently building/mislabeling the
        # wrong architecture. Picked dynamically so this test is correct
        # under QEMU-emulated aarch64 runs too, not just on an x86_64 host.
        host = native_target()
        foreign = next(
            triple for triple, target in TARGETS.items()
            if target.machine != host.machine or target.is_macos != host.is_macos
        )
        result = self.invoke('build', '--target', foreign, '--dev')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('does not match the running machine', result.stderr)

    def test_sealed_requires_qualification_not_only_an_offline_flag(self):
        result = self.invoke('build', '--offline', '--sealed')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('qualification', result.stderr)

    def test_doctor_reports_container_and_target(self):
        result = self.invoke('doctor')
        self.assertEqual(result.returncode, 0, result.stderr)
        import json
        report = json.loads(result.stdout)
        self.assertIn('native_target', report)
        self.assertIn('x86_64-unknown-linux-musl', report['supported_targets'])
        self.assertIn('aarch64-unknown-linux-musl', report['supported_targets'])
        self.assertIn('qualification', report)
