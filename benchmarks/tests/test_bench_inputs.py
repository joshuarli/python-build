"""Selected workload input requirements for the benchmark controller."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from benchmarks import bench
from benchmarks.workloads.registry import select_workloads


class SelectedInputTests(unittest.TestCase):
    def test_unused_lock_inputs_are_not_claimed_as_installed(self):
        lock = Mock()
        self.assertEqual(bench._used_input_provenance(lock, set()), [])
        lock.provenance.assert_not_called()
        lock.provenance.return_value = [{"name": "example"}]
        self.assertEqual(bench._used_input_provenance(lock, {"macros"}),
                         [{"name": "example"}])
        lock.provenance.assert_called_once_with({"macros"})

    def test_stdlib_only_selection_needs_no_wheelhouse(self):
        workloads = select_workloads("realworld", "standard", "zlib_decode_1m", None)
        self.assertFalse(bench._requires_macro_inputs(workloads))

    def test_package_and_pip_workloads_need_wheelhouse(self):
        for name in ("django_wsgi_request", "pip_install_wheelhouse"):
            with self.subTest(name=name):
                workloads = select_workloads("realworld", "standard", name, None)
                self.assertTrue(bench._requires_macro_inputs(workloads))


if __name__ == "__main__":
    unittest.main()
