"""Exercise the public controller without invoking native compilation."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CLITests(unittest.TestCase):
    def invoke(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'build.py'), *args],
                              cwd=ROOT, text=True, capture_output=True)

    def test_unsupported_target_fails_before_building(self):
        result = self.invoke('build', '--target', 'aarch64-unknown-linux-musl', '--dev')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('not implemented', result.stderr)

    def test_sealed_requires_qualification_not_only_an_offline_flag(self):
        result = self.invoke('build', '--offline', '--sealed')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('qualification', result.stderr)

    def test_doctor_reports_container_and_target(self):
        result = self.invoke('doctor')
        self.assertEqual(result.returncode, 0, result.stderr)
        import json
        report = json.loads(result.stdout)
        self.assertEqual(report['target'], 'x86_64-unknown-linux-musl')
        self.assertIn('qualification', report)
