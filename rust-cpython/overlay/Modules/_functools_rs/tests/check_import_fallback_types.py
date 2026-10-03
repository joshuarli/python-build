"""Check native imports avoid fallback types while blocked imports remain usable."""

import builtins
from pathlib import Path
import sys
from types import ModuleType
import unittest


class ImportFallbackTypes(unittest.TestCase):
    def import_functools(self, *, blocked):
        classes = []
        self.partial_import_namespaces = []
        build_class = builtins.__build_class__
        import_module = builtins.__import__
        source_path = Path(sys.base_prefix) / 'lib/python3.16/functools.py'
        source = source_path.read_bytes()
        module = ModuleType('functools')
        module.__file__ = str(source_path)
        previous = sys.modules.get('functools')

        def selected_import(name, *args, **kwargs):
            fromlist = args[2] if len(args) > 2 else kwargs.get('fromlist', ())
            if name == '_functools' and fromlist and 'partial' in fromlist:
                self.partial_import_namespaces.append(tuple(module.__dict__))
            if blocked and name == '_functools':
                raise ImportError('accelerator blocked for fallback check')
            return import_module(name, *args, **kwargs)

        def record_class(function, name, *bases, **kwargs):
            if function.__globals__.get('__name__') == 'functools':
                classes.append(name)
            return build_class(function, name, *bases, **kwargs)

        builtins.__build_class__ = record_class
        builtins.__import__ = selected_import
        sys.modules['functools'] = module
        try:
            exec(compile(source, str(source_path), 'exec'), module.__dict__)
        finally:
            builtins.__build_class__ = build_class
            builtins.__import__ = import_module
            if previous is None:
                sys.modules.pop('functools', None)
            else:
                sys.modules['functools'] = previous
        self.assertIsNotNone(module)
        return module, classes

    def exercise_partial(self, module):
        def arguments(*args, **kwargs):
            return args, kwargs

        call = module.partial(arguments, module.Placeholder, 2, mode='held')
        self.assertEqual(call(1, 3), ((1, 2, 3), {'mode': 'held'}))
        with self.assertRaises(TypeError):
            call()

        class Methods:
            method = module.partialmethod(arguments, module.Placeholder, 2)

        instance = Methods()
        self.assertEqual(instance.method(1), ((instance, 1, 2), {}))
        key = module.cmp_to_key(lambda left, right: (left > right) - (left < right))
        self.assertEqual(sorted([3, 1, 2], key=key), [1, 2, 3])

    def test_accelerator_import_does_not_construct_fallback_types(self):
        module, classes = self.import_functools(blocked=False)
        self.assertNotIn('_PlaceholderType', classes)
        self.assertNotIn('partial', classes)
        import _functools
        self.assertIs(module.partial, _functools.partial)
        self.assertIs(module.Placeholder, _functools.Placeholder)
        self.exercise_partial(module)

    def test_native_type_selection_follows_shared_helper_definitions(self):
        self.import_functools(blocked=False)
        self.assertEqual(len(self.partial_import_namespaces), 1)
        namespace, = self.partial_import_namespaces
        for helper in ('_partial_prepare_merger', '_partial_new', '_partial_repr'):
            self.assertIn(helper, namespace)
        self.assertNotIn('_partial_accelerated', namespace)

    def test_fallback_metadata_state_and_error_contract(self):
        module, _ = self.import_functools(blocked=True)
        self.assertEqual(module._PlaceholderType.__doc__,
                         'The type of the Placeholder singleton.\n\n'
                         'Used as a placeholder for partial arguments.\n')
        self.assertEqual(module.partial.__doc__,
                         'New function with partial application of the given arguments\n'
                         'and keywords.\n')
        for name in ('_PlaceholderType', 'partial'):
            cls = getattr(module, name)
            self.assertEqual(cls.__module__, 'functools')
            self.assertEqual(cls.__name__, name)
            self.assertEqual(cls.__qualname__, name)
        self.assertIs(module.partial.__new__, module._partial_new)
        self.assertIs(module.partial.__repr__.__wrapped__, module._partial_repr)
        self.assertEqual(module.Placeholder.__reduce__(), 'Placeholder')
        call = module.partial(pow, 2)
        call.tag = 'state'
        self.assertEqual(call.__reduce__(),
                         (module.partial, (pow,), (pow, (2,), None, {'tag': 'state'})))
        with self.assertRaisesRegex(TypeError, 'argument to __setstate__ must be a tuple'):
            call.__setstate__(None)
        with self.assertRaisesRegex(TypeError, 'expected 4 items in state, got 1'):
            call.__setstate__((pow,))
        self.assertEqual(call(3), 8)
        self.assertEqual(call.tag, 'state')

    def test_fallback_pickle_protocols_restore_types_and_state(self):
        import pickle
        module, _ = self.import_functools(blocked=True)
        previous = sys.modules.get('functools')
        sys.modules['functools'] = module
        try:
            call = module.partial(pow, 2)
            call.tag = 'state'
            for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
                with self.subTest(protocol=protocol):
                    restored = pickle.loads(pickle.dumps(call, protocol))
                    self.assertIs(type(restored), module.partial)
                    self.assertEqual(restored(3), 8)
                    self.assertEqual(restored.tag, 'state')
                    singleton = pickle.loads(pickle.dumps(module.Placeholder, protocol))
                    self.assertIs(singleton, module.Placeholder)
        finally:
            if previous is None:
                sys.modules.pop('functools', None)
            else:
                sys.modules['functools'] = previous

    def test_missing_partial_preserves_python_placeholder_selection(self):
        import _functools
        partial = _functools.partial
        del _functools.partial
        try:
            module, _ = self.import_functools(blocked=False)
        finally:
            _functools.partial = partial
        self.assertIsNotNone(module)
        self.assertIsNot(module.Placeholder, _functools.Placeholder)
        self.assertIs(module._PlaceholderType(), module.Placeholder)
        self.exercise_partial(module)

    def test_missing_placeholder_attributes_preserve_import_binding_order(self):
        import _functools
        for missing in ('Placeholder', '_PlaceholderType'):
            with self.subTest(missing=missing):
                original = getattr(_functools, missing)
                delattr(_functools, missing)
                try:
                    module, _ = self.import_functools(blocked=False)
                finally:
                    setattr(_functools, missing, original)
                self.assertIsNotNone(module)
                self.assertIs(module.partial, _functools.partial)
                self.assertIsNot(module._PlaceholderType, _functools._PlaceholderType)
                if missing == 'Placeholder':
                    self.assertIsNot(module.Placeholder, _functools.Placeholder)
                    self.assertEqual(module.partial(pow, 2)(3), 8)
                else:
                    self.assertIs(module.Placeholder, _functools.Placeholder)
                    self.exercise_partial(module)

    def test_blocked_accelerator_constructs_working_fallback_types(self):
        module, classes = self.import_functools(blocked=True)
        self.assertEqual(classes.count('_PlaceholderType'), 1)
        self.assertEqual(classes.count('partial'), 1)
        self.assertIs(module._PlaceholderType(), module.Placeholder)
        self.exercise_partial(module)


if __name__ == '__main__':
    unittest.main()
