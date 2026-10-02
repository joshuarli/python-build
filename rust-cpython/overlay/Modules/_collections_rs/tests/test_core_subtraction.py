"""Observe iterable subtraction, callback errors, ownership and reentry."""

import _collections
import _collections_rs
import collections
import unittest
import weakref


class CoreSubtractionTests(unittest.TestCase):
    def test_counts_match_c_tally_oracle_and_public_calls_reach_rust(self):
        words = ('a', 'b', 'a', '日本語', 'b', 'a')
        counts = {}
        _collections._count_elements(counts, iter(words))
        expected = {key: -value for key, value in counts.items()}
        original = _collections_rs.subtract_iterable
        calls = []

        def observed(mapping, iterable, mapping_get):
            calls.append(mapping)
            return original(mapping, iterable, mapping_get)

        _collections_rs.subtract_iterable = observed
        try:
            counter = collections.Counter()
            result = counter.subtract(iter(words))
        finally:
            _collections_rs.subtract_iterable = original
        self.assertIsNone(result)
        self.assertEqual(counter, expected)
        self.assertEqual(list(counter), list(counts))
        self.assertEqual(calls, [counter])

    def test_callback_failures_keep_exception_identity(self):
        for stage in ('iterate', 'get', 'subtract', 'set'):
            with self.subTest(stage=stage):
                failure = LookupError(stage)

                class Iterator:
                    def __iter__(self):
                        return self

                    def __next__(self):
                        raise failure

                class Count:
                    def __sub__(self, other):
                        raise failure

                class Mapping(dict):
                    def __setitem__(self, key, value):
                        raise failure

                def get(key, default):
                    if stage == 'get':
                        raise failure
                    return Count() if stage == 'subtract' else 3

                mapping = Mapping() if stage == 'set' else {}
                iterable = Iterator() if stage == 'iterate' else ('a',)
                with self.assertRaises(LookupError) as caught:
                    _collections_rs.subtract_iterable(mapping, iterable, get)
                self.assertIs(caught.exception, failure)

    def test_temporary_counts_and_results_release_between_get_calls(self):
        references = []
        stored = []

        class Value:
            pass

        class Count:
            def __sub__(self, other):
                if other != 1:
                    raise AssertionError('subtraction operand changed')
                value = Value()
                references.append(weakref.ref(value))
                return value

        class Mapping:
            def get(self, key, default):
                if not all(reference() is None for reference in references):
                    raise AssertionError('previous count or result retained')
                count = Count()
                references.append(weakref.ref(count))
                return count

            def __setitem__(self, key, value):
                stored.append(key)

        mapping = Mapping()
        self.assertIsNone(_collections_rs.subtract_iterable(
            mapping, ('a', 'b', 'a'), mapping.get,
        ))
        self.assertEqual(stored, ['a', 'b', 'a'])
        self.assertTrue(references)
        self.assertTrue(all(reference() is None for reference in references))

    def test_get_callback_can_reenter_subtraction_without_shared_state(self):
        outer = {'a': 3}
        inner = {'b': 5}
        calls = []

        def get(key, default):
            calls.append(key)
            _collections_rs.subtract_iterable(inner, ('b',), inner.get)
            return outer.get(key, default)

        self.assertIsNone(_collections_rs.subtract_iterable(outer, 'aa', get))
        self.assertEqual(outer, {'a': 1})
        self.assertEqual(inner, {'b': 3})
        self.assertEqual(calls, ['a', 'a'])
        with self.assertRaisesRegex(TypeError, 'requires a mapping, iterable, and bound get method'):
            _collections_rs.subtract_iterable(outer, 'a')


if __name__ == '__main__':
    unittest.main()
