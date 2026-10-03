"""Check named tuple method binding ownership and observable capture behavior."""

import builtins
import collections
import inspect
import unittest


class NamedTupleMethodBindingsTests(unittest.TestCase):
    def test_generated_methods_share_four_retained_cells(self):
        record = collections.namedtuple('Record', 'left right')
        methods = (
            record._make.__func__, record._replace, record.__repr__,
            record._asdict, record.__getnewargs__,
        )
        cells = {id(cell) for method in methods for cell in method.__closure__}
        self.assertEqual(len(cells), 4)
        bindings = [
            cell for cell in record._make.__func__.__closure__
            if isinstance(cell.cell_contents, tuple)
        ]
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0].cell_contents,
                         (tuple.__new__, dict, tuple, len, map, zip))
        for method in (record._replace, record._asdict, record.__getnewargs__):
            self.assertTrue(any(cell is bindings[0] for cell in method.__closure__))

    def test_methods_keep_factory_time_builtin_bindings(self):
        record = collections.namedtuple('Record', 'left right', defaults=(9,))
        original = {name: getattr(builtins, name)
                    for name in ('dict', 'tuple', 'len', 'map', 'zip')}

        def unavailable(*args, **kwargs):
            raise AssertionError('generated method looked up a replacement builtin')

        try:
            for name in original:
                setattr(builtins, name, unavailable)
            instance = record._make((1, 2))
            replaced = instance._replace(right=3)
            mapping = replaced._asdict()
            arguments = replaced.__getnewargs__()
        finally:
            for name, value in original.items():
                setattr(builtins, name, value)
        self.assertEqual(instance, (1, 2))
        self.assertEqual(replaced, (1, 3))
        self.assertEqual(mapping, {'left': 1, 'right': 3})
        self.assertEqual(arguments, (1, 3))

    def test_generated_metadata_defaults_and_replace_contract(self):
        record = collections.namedtuple('Record', 'left right', defaults=(9,))
        self.assertEqual(record.__module__, __name__)
        self.assertEqual(record.__new__.__defaults__, (9,))
        self.assertEqual(record._fields, ('left', 'right'))
        self.assertEqual(record._field_defaults, {'right': 9})
        self.assertEqual(str(inspect.signature(record._asdict)), '(self)')
        self.assertEqual(str(inspect.signature(record.__getnewargs__)), '(self)')
        instance = record(1)
        self.assertEqual(repr(instance), 'Record(left=1, right=9)')
        self.assertEqual(instance.__replace__(right=4), (1, 4))
        with self.assertRaisesRegex(TypeError, 'Expected 2 arguments, got 1'):
            record._make((1,))
        with self.assertRaisesRegex(TypeError, 'Got unexpected field names'):
            instance._replace(extra=3)
        record._fields = ('changed',)
        self.assertEqual(record._make((1, 2)), (1, 2))
        self.assertEqual(instance._replace(right=4), (1, 4))


if __name__ == '__main__':
    unittest.main()
