"""Heap ordering, callback failures and mutation stay at the Python boundary."""

import _heapq_rs as native
import heapq
import unittest


class HeapBoundaryTests(unittest.TestCase):
    def test_min_and_max_operations_reach_native(self):
        self.assertIs(heapq._rust_heapq, native)
        for suffix, reverse in (("", False), ("_max", True)):
            with self.subTest(suffix=suffix):
                values = [8, 3, 8, -4, 0, 11]
                getattr(native, "heapify" + suffix)(values)
                getattr(native, "heappush" + suffix)(values, 5)
                order = sorted([8, 3, 8, -4, 0, 11, 5], reverse=reverse)
                self.assertEqual([getattr(native, "heappop" + suffix)(values)
                                  for _ in range(len(values))], order)
                values = [3, 4, 5] if not reverse else [5, 4, 3]
                outside = -10 if not reverse else 10
                self.assertEqual(getattr(native, "heappushpop" + suffix)(values, outside), outside)
                self.assertEqual(len(values), 3)
                self.assertEqual(getattr(native, "heapreplace" + suffix)(values, 7),
                                 3 if not reverse else 5)

    def test_comparison_error_retains_exception_identity(self):
        error = LookupError("comparison sentinel")

        class Item:
            def __lt__(self, other):
                raise error

        with self.assertRaises(LookupError) as caught:
            native.heappush([Item()], Item())
        self.assertIs(caught.exception, error)

    def test_reentrant_comparison_detects_size_change(self):
        values = []

        class Item:
            def __lt__(self, other):
                values.clear()
                return False

        values.extend([Item(), Item()])
        with self.assertRaisesRegex(RuntimeError, "^list changed size during iteration$"):
            native.heapify(values)
        self.assertEqual(values, [])
        with self.assertRaisesRegex(IndexError, "^index out of range$"):
            native.heappop([])
        with self.assertRaisesRegex(TypeError, "^heap must be a list$"):
            native.heapify(())


if __name__ == '__main__':
    unittest.main()
