"""Observable snapshot validation, including callbacks on changed sequences."""
import hashlib
import gc
import importlib
import builtins
import weakref
import difflib
import unittest
from types import SimpleNamespace, ModuleType, BuiltinFunctionType

class SnapshotBehaviorTests(unittest.TestCase):
    def assert_matches_reference(self, a, b):
        actual = difflib.SequenceMatcher(None, a, b).get_matching_blocks()
        backend = difflib._difflib_rs
        try:
            difflib._difflib_rs = None
            expected = difflib.SequenceMatcher(None, a, b).get_matching_blocks()
        finally:
            difflib._difflib_rs = backend
        self.assertEqual(actual, expected)

    def test_changed_list_declines_stale_snapshot(self):
        matcher = difflib.SequenceMatcher(None, ['a', 'b'], ['a', 'b'])
        matcher.b[1] = 'c'
        self.assertIsNone(matcher._rust_find_longest_match(0, 2, 0, 2))
        matcher.set_seq2(['a', 'c'])
        self.assertEqual(matcher.find_longest_match(), difflib.Match(0, 0, 1))

    def test_equal_strings_with_different_identity(self):
        text = 'same dynamically constructed string ' * 3
        first = text.encode().decode()
        second = text.encode().decode()
        self.assertIsNot(first, second)
        matcher = difflib.SequenceMatcher(None, [first], [first])
        matcher.b[0] = second
        self.assertEqual(matcher.find_longest_match(), difflib.Match(0, 0, 1))

    def test_mixed_builtin_values_and_earliest_ties(self):
        self.assert_matches_reference([1, 'x', 2, 'x', 1], ['x', 1, 'x', 2, 'x'])
        self.assert_matches_reference(['a', 'b', 'a', 'b'], ['b', 'a', 'b', 'a'])

    def test_custom_equality_preserves_mutation_and_reentry(self):
        events = []
        matcher = difflib.SequenceMatcher(None, ['token'], ['token'])
        class Value:
            def __eq__(self, other):
                events.append(('eq', other))
                nested = difflib.SequenceMatcher(None, ['a'], ['a']).find_longest_match()
                events.append(('nested', nested.size))
                matcher.b.clear()
                return False
        matcher.b[0] = Value()
        self.assertIsNone(matcher._rust_find_longest_match(0, 1, 0, 1))
        self.assertEqual(events, [('eq', 'token'), ('nested', 1)])
        self.assertEqual(matcher.b, [])

    def test_custom_equality_error_identity(self):
        marker = RuntimeError('comparison marker')
        matcher = difflib.SequenceMatcher(None, ['token'], ['token'])
        class Value:
            def __eq__(self, other):
                raise marker
        matcher.b[0] = Value()
        with self.assertRaises(RuntimeError) as caught:
            matcher._rust_find_longest_match(0, 1, 0, 1)
        self.assertIs(caught.exception, marker)

    def test_custom_equality_true_uses_historical_values(self):
        calls = []
        matcher = difflib.SequenceMatcher(None, ['token'], ['token'])
        class Value:
            def __eq__(self, other):
                calls.append(other)
                return True
        matcher.b[0] = Value()
        self.assertEqual(matcher.find_longest_match(), difflib.Match(0, 0, 1))
        self.assertEqual(calls, ['token'])

    def test_live_tuple_override_keeps_call_order(self):
        matcher = difflib.SequenceMatcher(None, ['a'], ['a'])
        calls = []
        original = difflib.__dict__.get('tuple')
        def factory(sequence):
            calls.append(sequence)
            return tuple(sequence)
        difflib.tuple = factory
        try:
            self.assertEqual(matcher.find_longest_match(), difflib.Match(0, 0, 1))
            self.assertEqual([id(x) for x in calls], [id(matcher.b), id(matcher.a)])
        finally:
            if original is None:
                del difflib.tuple
            else:
                difflib.tuple = original

    def test_replaced_backend_needs_only_original_method(self):
        backend = difflib._difflib_rs
        calls = []
        def find(*args):
            calls.append(args)
            return backend.find_longest_match_index(*args)
        def unexpected(*args):
            raise AssertionError('replacement backend must retain the original boundary')
        difflib._difflib_rs = SimpleNamespace(find_longest_match_index=find, snapshot_matches=unexpected)
        try:
            matcher = difflib.SequenceMatcher(None, ['a'], ['a'])
            self.assertEqual(matcher.find_longest_match(), difflib.Match(0, 0, 1))
            self.assertEqual(len(calls), 1)
        finally:
            difflib._difflib_rs = backend

    def test_evicted_replaced_module_is_not_kept_alive(self):
        import sys
        reference = weakref.ref(difflib._difflib_rs)
        difflib._difflib_rs = SimpleNamespace()
        sys.modules.pop('_difflib_rs')
        try:
            gc.collect()
            self.assertIsNone(reference())
        finally:
            difflib._difflib_rs = importlib.import_module('_difflib_rs')
            importlib.reload(difflib)

    def test_initial_opaque_backend_has_no_new_getter_calls(self):
        class Opaque:
            __slots__ = ()
            def __getattr__(self, name):
                raise AssertionError('opaque backend attribute read: ' + name)
        backend = Opaque()
        original_import = builtins.__import__
        def importer(name, *args, **kwargs):
            return backend if name == '_difflib_rs' else original_import(name, *args, **kwargs)
        fresh = ModuleType('snapshot_opaque_facade')
        fresh.__dict__['__builtins__'] = {**vars(builtins), '__import__': importer}
        with open(difflib.__file__) as stream:
            source = stream.read()
        exec(compile(source, difflib.__file__, 'exec'), fresh.__dict__)
        self.assertIs(fresh._difflib_rs, backend)

    def test_initial_custom_module_uses_original_matching_interface(self):
        original_import = builtins.__import__
        native = difflib._difflib_rs
        for with_poison in (False, True):
            calls = []
            backend = ModuleType('custom_matching_backend')
            def find(*args):
                calls.append('match')
                return native.find_longest_match_index(*args)
            def poison(*args):
                raise AssertionError('custom module snapshot attribute invoked')
            def missing(name):
                raise AssertionError('custom module attribute getter: ' + name)
            backend.find_longest_match_index = find
            backend.__getattr__ = missing
            if with_poison:
                backend.snapshot_matches = poison
            def importer(name, *args, **kwargs):
                return backend if name == '_difflib_rs' else original_import(name, *args, **kwargs)
            fresh = ModuleType('snapshot_custom_facade')
            fresh.__dict__['__builtins__'] = {**vars(builtins), '__import__': importer}
            with open(difflib.__file__) as stream:
                source = stream.read()
            exec(compile(source, difflib.__file__, 'exec'), fresh.__dict__)
            matcher = fresh.SequenceMatcher(None, ['a'], ['a'])
            self.assertEqual(matcher.find_longest_match(), fresh.Match(0, 0, 1))
            self.assertEqual(calls, ['match'])

    def test_ranges_and_direct_boundary_errors(self):
        matcher = difflib.SequenceMatcher(None, ['a', 'b'], ['a', 'b'])
        self.assertEqual(matcher.find_longest_match(1, 2, 1, 2), difflib.Match(1, 1, 1))
        self.assertIsNone(matcher._rust_find_longest_match(-1, 2, 0, 2))
        self.assertIsNone(matcher._rust_find_longest_match(0, 3, 0, 2))
        with self.assertRaisesRegex(ValueError, 'ascending'):
            difflib._difflib_rs.find_longest_match_index(('a',), ('a', 'a'), {'a': [1, 0]}, 0, 1, 0, 2)

    def test_fixed_reordered_digest_and_native_dispatch(self):
        blocks = [[f'def section_{section:02d}(item):\n']
                  + [f'    value = step_{index % 7}(item)\n' for index in range(31)]
                  + [f'    return value + {section}\n'] for section in range(12)]
        before = [line for block in blocks for line in block]
        after = [line for section in (0, 1, 5, 6, 2, 3, 4, 9, 10, 7, 8, 11) for line in blocks[section]]
        after[120] = '    value = step_3(item + 1)\n'
        backend = difflib._difflib_rs
        original = backend.find_longest_match_index
        self.assertIs(type(original), BuiltinFunctionType)
        self.assertIs(original.__self__, backend)
        calls = []
        def find(*args):
            calls.append(1)
            return original(*args)
        backend.find_longest_match_index = find
        try:
            patch = ''.join(difflib.unified_diff(before, after, fromfile='before.py', tofile='after.py', lineterm='\n'))
            self.assertEqual(hashlib.sha256(patch.encode()).hexdigest(), '26585b44b4a4ced0dbb5f717454d1cbc7fd290ad798a767f0de0ecd41497f7c8')
            self.assertGreater(len(calls), 0)
        finally:
            backend.find_longest_match_index = original

class SnapshotOptimizationTests(unittest.TestCase):
    def test_precise_callback_free_comparison(self):
        compare = difflib._difflib_rs.snapshot_matches
        self.assertEqual(compare(['a', 2], ('a', 2), tuple), 1)
        self.assertEqual(compare(['a', 3], ('a', 2), tuple), 0)
        self.assertEqual(compare(['a'], ('a', 2), tuple), 0)
        class Value:
            def __eq__(self, other):
                raise AssertionError('eligibility must not compare custom values')
        self.assertEqual(compare([Value()], ('a',), tuple), -1)
        self.assertEqual(compare(['a'], ('a',), lambda x: tuple(x)), -1)
        with self.assertRaises(TypeError):
            compare([], ())
        calls = []
        def live(*args):
            calls.append(args)
            return compare(*args)
        difflib._difflib_rs.snapshot_matches = live
        try:
            matcher = difflib.SequenceMatcher(None, ['a'], ['a'])
            self.assertEqual(matcher.find_longest_match(), difflib.Match(0, 0, 1))
            self.assertEqual(len(calls), 1)
        finally:
            difflib._difflib_rs.snapshot_matches = compare

if __name__ == '__main__':
    unittest.main()
