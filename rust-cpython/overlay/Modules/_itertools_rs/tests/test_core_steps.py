"""Iterator steps retain native dispatch, values and Python exception identity."""
import importlib
import sys
import unittest
import _itertools_rs as native


NAMES = ('_chain_next', '_compress_next', '_dropwhile_next', '_filterfalse_next',
         '_islice_next', '_starmap_next', '_takewhile_next')


class ItertoolsCoreTests(unittest.TestCase):
    def test_native_step_state_and_exhaustion(self):
        source = iter([[10]])
        status, active = native._chain_next(source, None)
        self.assertEqual(status, 1)
        self.assertEqual(native._chain_next(source, active), (0, 10))
        self.assertEqual(native._chain_next(source, active), (2, None))
        self.assertEqual(native._chain_next(source, None), (3, None))
        self.assertEqual(native._compress_next(iter([1, 2]), iter([False, True])), 2)
        values = iter([1, 2, 3])
        self.assertEqual(native._dropwhile_next(lambda v: v < 2, values, False), (True, 2))
        self.assertEqual(native._dropwhile_next(lambda v: v < 2, values, True), (True, 3))
        self.assertEqual(native._filterfalse_next(lambda v: v % 2, iter([1, 2])), 2)
        values = iter(range(10))
        self.assertEqual(native._islice_next(values, 2, 7, 3, 0), (2, 5, 3))
        self.assertEqual(native._islice_next(values, 5, 7, 3, 3), (5, 7, 6))
        self.assertEqual(native._starmap_next(pow, iter([(2, 3)])), 8)
        self.assertEqual(native._takewhile_next(bool, iter([4]), False), (True, 4))
        self.assertEqual(native._takewhile_next(bool, iter([0]), False), (False, None))
        cases = ((native._compress_next, (iter(()), iter(()))),
                 (native._dropwhile_next, (bool, iter(()), False)),
                 (native._filterfalse_next, (None, iter(()))),
                 (native._islice_next, (iter(()), 0, -1, 1, 0)),
                 (native._starmap_next, (pow, iter(()))),
                 (native._takewhile_next, (bool, iter([1]), True)))
        for method, args in cases:
            with self.subTest(method=method.__name__):
                with self.assertRaises(StopIteration):
                    method(*args)

    def test_callback_exception_identity_and_argument_errors(self):
        error = ValueError('predicate failed')
        def fail(*args):
            raise error
        for method, args in ((native._dropwhile_next, (fail, iter([1]), False)),
                             (native._filterfalse_next, (fail, iter([1]))),
                             (native._starmap_next, (fail, iter([(1,)]))),
                             (native._takewhile_next, (fail, iter([1]), False))):
            with self.subTest(method=method.__name__):
                with self.assertRaises(ValueError) as caught:
                    method(*args)
                self.assertIs(caught.exception, error)
        for name in NAMES:
            with self.subTest(method=name):
                with self.assertRaises(TypeError):
                    getattr(native, name)()

    def test_fresh_public_module_keeps_all_seven_native_routes(self):
        originals = {name: getattr(native, name) for name in NAMES}
        calls = {name: 0 for name in NAMES}
        old_module = sys.modules.get('itertools')
        def forwarding(name):
            def call(*args):
                calls[name] += 1
                return originals[name](*args)
            return call
        try:
            for name in NAMES:
                setattr(native, name, forwarding(name))
            sys.modules.pop('itertools', None)
            public = importlib.import_module('itertools')
            self.assertEqual(list(public.chain([1], [], [2])), [1, 2])
            self.assertEqual(list(public.compress('abc', [1, 0, 1])), ['a', 'c'])
            self.assertEqual(list(public.dropwhile(lambda v: v < 2, [1, 2, 3])), [2, 3])
            self.assertEqual(list(public.filterfalse(lambda v: v % 2, [1, 2, 3, 4])), [2, 4])
            self.assertEqual(list(public.islice(range(10), 2, 7, 3)), [2, 5])
            self.assertEqual(list(public.starmap(pow, [(2, 3), (3, 2)])), [8, 9])
            self.assertEqual(list(public.takewhile(lambda v: v < 3, [1, 2, 3, 4])), [1, 2])
            self.assertTrue(all(count > 0 for count in calls.values()), calls)
        finally:
            for name, method in originals.items():
                setattr(native, name, method)
            if old_module is None:
                sys.modules.pop('itertools', None)
            else:
                sys.modules['itertools'] = old_module


if __name__ == '__main__':
    unittest.main()
