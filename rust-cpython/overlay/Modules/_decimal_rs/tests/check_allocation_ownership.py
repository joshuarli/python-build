"""Count coefficient ownership on every allocation failure and parser exit."""
import importlib.util
import sys
import unittest
import _decimal_rs

spec = importlib.util.spec_from_file_location("_decimal_allocation_test", sys.argv.pop(1))
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


class CoefficientOwnership(unittest.TestCase):
    def check_counts(self, attempts, successes, failed):
        self.assertEqual(observer.counts(),
                         (attempts, successes, successes, 0, failed, 0, 0, 0, 0, 0))

    def test_allocations_and_each_failure_release_all_coefficients(self):
        observer.module_contract(_decimal_rs)
        left, right = "9" * 1001, "8" * 1003
        for method, expected in (
            (_decimal_rs.add_exact_integers, str(int(left) + int(right))),
            (_decimal_rs.multiply_exact_integers, str(int(left) * int(right))),
        ):
            self.assertEqual(observer.drive(method, left, right, 0), expected)
            self.check_counts(4, 4, 0)
            for failure in range(1, 5):
                with self.subTest(method=method.__name__, failure=failure):
                    with self.assertRaises(MemoryError):
                        observer.drive(method, left, right, failure)
                    self.check_counts(failure, failure - 1, 1)
                    self.assertEqual(observer.drive(method, left, right, 0), expected)
                    self.check_counts(4, 4, 0)

    def test_invalid_second_operand_releases_first_coefficient(self):
        left = "9" * 1001
        for method in (_decimal_rs.add_exact_integers, _decimal_rs.multiply_exact_integers):
            for right, error in (("_1", ValueError), ("1.0", ValueError), (object(), TypeError)):
                with self.subTest(method=method.__name__, error=error):
                    with self.assertRaises(error):
                        observer.drive(method, left, right, 0)
                    self.check_counts(1, 1, 0)
            observer.drive(method, left, "1", 0)
            self.check_counts(3, 3, 0)

    def test_public_bound_coefficients_need_no_mem_buffer(self):
        text = "9" * 128
        for method, expected in (
            (_decimal_rs.add_exact_integers, str(2 * int(text))),
            (_decimal_rs.multiply_exact_integers, str(int(text) ** 2)),
        ):
            self.assertEqual(observer.drive(method, text, text, 1), expected)
            self.check_counts(0, 0, 0)


if __name__ == "__main__":
    unittest.main()
