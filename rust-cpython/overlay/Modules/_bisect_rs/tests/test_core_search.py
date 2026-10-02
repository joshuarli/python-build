"""Observe bisect callback, truth-result ownership, and integer boundaries."""

import bisect
import sys
import unittest
import weakref

import _bisect_rs


SEARCHES = (_bisect_rs.search_left, _bisect_rs.search_right)


class CoreSearchTests(unittest.TestCase):
    def test_midpoints_near_signed_index_limit(self):
        lo = sys.maxsize - 9
        hi = sys.maxsize
        boundary = sys.maxsize - 4
        for search in SEARCHES:
            with self.subTest(search=search.__name__):
                midpoints = []

                def probe(midpoint):
                    self.assertGreaterEqual(midpoint, lo)
                    self.assertLess(midpoint, hi)
                    midpoints.append(midpoint)
                    if search is _bisect_rs.search_left:
                        return midpoint < boundary
                    return midpoint >= boundary

                self.assertEqual(search(lo, hi, probe), boundary)
                self.assertTrue(midpoints)

    def test_callback_and_truth_exceptions_keep_identity(self):
        for search in SEARCHES:
            callback_error = LookupError('callback failed')

            def fail(midpoint):
                raise callback_error

            with self.assertRaises(LookupError) as caught:
                search(0, 8, fail)
            self.assertIs(caught.exception, callback_error)

            truth_error = ValueError('truth conversion failed')

            class Truth:
                def __bool__(self):
                    raise truth_error

            with self.assertRaises(ValueError) as caught:
                search(0, 8, lambda midpoint: Truth())
            self.assertIs(caught.exception, truth_error)

    def test_temporary_truth_results_are_released_between_callbacks(self):
        class Truth:
            def __bool__(self):
                return False

        for search, expected in zip(SEARCHES, (0, 16)):
            references = []

            def probe(midpoint):
                self.assertTrue(all(reference() is None for reference in references))
                result = Truth()
                references.append(weakref.ref(result))
                return result

            self.assertEqual(search(0, 16, probe), expected)
            self.assertTrue(references)
            self.assertTrue(all(reference() is None for reference in references))

    def test_invalid_arguments_do_not_invoke_callback(self):
        calls = []

        def probe(midpoint):
            calls.append(midpoint)
            return False

        for search in SEARCHES:
            for arguments in ((), (0, 8), (0, 8, probe, None)):
                with self.assertRaisesRegex(TypeError, 'search requires lo, hi, and a comparison callback'):
                    search(*arguments)
            for lo, hi in (('0', 8), (0, '8')):
                with self.assertRaises(TypeError):
                    search(lo, hi, probe)
            for lo, hi in ((sys.maxsize + 1, 8), (0, sys.maxsize + 1)):
                with self.assertRaises(OverflowError):
                    search(lo, hi, probe)
        self.assertEqual(calls, [])

    def test_public_key_search_and_insertion_reach_native_helpers(self):
        self.assertIs(bisect._rust_search_left, _bisect_rs.search_left)
        self.assertIs(bisect._rust_search_right, _bisect_rs.search_right)
        records = [(1, 'a'), (2, 'b'), (2, 'c'), (4, 'd')]
        key = lambda record: record[0]
        self.assertEqual(bisect.bisect_left(records, 2, key=key), 1)
        self.assertEqual(bisect.bisect_right(records, 2, key=key), 3)
        bisect.insort_left(records, (2, 'left'), key=key)
        bisect.insort_right(records, (2, 'right'), key=key)
        self.assertEqual(records, [(1, 'a'), (2, 'left'), (2, 'b'), (2, 'c'), (2, 'right'), (4, 'd')])


if __name__ == '__main__':
    unittest.main()
