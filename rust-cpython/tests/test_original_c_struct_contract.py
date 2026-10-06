"""Original C struct behavior remains independent of extension placement."""
import importlib
import sys
import types
import unittest

import _struct
import struct


class OriginalStructTests(unittest.TestCase):
    def test_wire_types_errors_and_held_cache_objects(self):
        self.assertIs(struct.Struct, _struct.Struct)
        self.assertIs(struct.error, _struct.error)
        self.assertEqual(_struct.Struct.__module__, '_struct')
        self.assertEqual(_struct.error.__module__, 'struct')
        self.assertTrue(issubclass(_struct.error, Exception))
        for name in ('pack', 'unpack', 'pack_into', 'unpack_from', 'iter_unpack', 'calcsize', '_clearcache'):
            method = getattr(_struct, name)
            self.assertIsInstance(method, types.BuiltinFunctionType)
            self.assertIs(method.__self__, _struct)
        wire = b'\xff\xfe\x01\x02\x03\x04OK\x3f\x80\x00\x00'
        values = (-2, 0x01020304, b'OK', 1.0)
        held = _struct.Struct('>hI2sf')
        held_pack = held.pack
        self.assertEqual(held.size, 12)
        self.assertEqual(held.format, '>hI2sf')
        self.assertEqual(held_pack(*values), wire)
        self.assertEqual(_struct.unpack('>hI2sf', wire), values)
        self.assertEqual(_struct.calcsize('>hI2sf'), 12)
        for _ in range(3):
            self.assertIsNone(_struct._clearcache())
            self.assertEqual(held_pack(*values), wire)
            self.assertEqual(held.unpack(wire), values)
            self.assertEqual(_struct.pack('>hI2sf', *values), wire)
        self.assertEqual(list(_struct.iter_unpack('>h', b'\x00\x01\xff\xfe')), [(1,), (-2,)])
        for callback, args, error_type in ((_struct.pack, ('>i',), struct.error),
                                          (_struct.unpack, ('>i', b'x'), struct.error),
                                          (_struct.calcsize, ('!', 'extra'), TypeError),
                                          (_struct.pack, ('>B', 256), struct.error)):
            with self.assertRaises(error_type):
                callback(*args)

    def test_buffers_and_index_callback_identity(self):
        target = bytearray(b'.' * 12)
        self.assertIsNone(_struct.pack_into('>I', target, 3, 0x01020304))
        self.assertEqual(target, b'...\x01\x02\x03\x04.....')
        self.assertEqual(_struct.unpack_from('>I', memoryview(target), 3), (0x01020304,))
        with self.assertRaises(TypeError):
            _struct.pack_into('>I', b'xxxx', 0, 1)
        calls = []
        class Index:
            def __index__(self):
                calls.append('index')
                self_test.assertEqual(_struct.unpack('>i', b'\x00\x00\x00\x07'), (7,))
                return 7
        self_test = self
        self.assertEqual(_struct.pack('>i', Index()), b'\x00\x00\x00\x07')
        self.assertEqual(calls, ['index'])
        error = RuntimeError('struct index identity')
        class Broken:
            def __index__(self):
                raise error
        with self.assertRaises(RuntimeError) as caught:
            _struct.pack('>i', Broken())
        self.assertIs(caught.exception, error)
        self.assertEqual(_struct.pack('>i', 8), b'\x00\x00\x00\x08')

    def test_reload_reimport_and_held_original_methods(self):
        original = _struct
        held_pack = original.pack
        held_struct = original.Struct('>i')
        self.assertIs(importlib.reload(original), original)
        self.assertEqual(held_pack('>i', 9), b'\x00\x00\x00\x09')
        try:
            del sys.modules['_struct']
            fresh = importlib.import_module('_struct')
            self.assertIsNot(fresh, original)
            self.assertIs(fresh.pack.__self__, fresh)
            self.assertIs(held_pack.__self__, original)
            self.assertEqual(fresh.pack('>i', 10), b'\x00\x00\x00\x0a')
            self.assertEqual(held_struct.pack(11), b'\x00\x00\x00\x0b')
            self.assertIsNone(fresh._clearcache())
            self.assertEqual(held_struct.unpack(b'\x00\x00\x00\x0c'), (12,))
        finally:
            sys.modules['_struct'] = original

    def test_public_facade_still_activates_rust(self):
        import _struct_rs as helper
        original_cache = struct._rust_struct
        originals = {name: getattr(helper, name) for name in ('pack', 'unpack', 'unpack_from')}
        counts = dict.fromkeys(originals, 0)
        def wrapper(name):
            def invoke(*args):
                counts[name] += 1
                return originals[name](*args)
            return invoke
        try:
            struct._rust_struct = struct._RUST_STRUCT_NOT_LOADED
            for name in originals:
                setattr(helper, name, wrapper(name))
            wire = b'\x00\x00\x00\x07'
            self.assertEqual(struct.pack('>i', 7), wire)
            self.assertIs(struct._rust_struct, helper)
            self.assertEqual(struct.unpack('>i', wire), (7,))
            target = bytearray(8)
            self.assertIsNone(struct.pack_into('>i', target, 2, 7))
            self.assertEqual(struct.unpack_from('>i', target, 2), (7,))
            self.assertEqual(counts, {'pack': 2, 'unpack': 1, 'unpack_from': 1})
            error = RuntimeError('Rust facade delegate identity')
            def failing(*args):
                raise error
            helper.pack = failing
            with self.assertRaises(RuntimeError) as caught:
                struct.pack('>i', 7)
            self.assertIs(caught.exception, error)
        finally:
            for name, original in originals.items():
                setattr(helper, name, original)
            struct._rust_struct = original_cache

    def test_own_gil_cycles_and_outer_survival(self):
        import _interpreters
        held_pack = _struct.pack
        for _ in range(3):
            interpreter = _interpreters.create('isolated')
            try:
                result = _interpreters.run_string(interpreter, '''
import importlib, sys
import _struct, struct
assert _struct.pack.__self__ is _struct
assert struct.Struct is _struct.Struct and struct.error is _struct.error
held = _struct.Struct('>i')
assert held.pack(13) == b'\\x00\\x00\\x00\\x0d'
assert _struct._clearcache() is None
assert held.unpack(b'\\x00\\x00\\x00\\x0e') == (14,)
try:
    import _struct_rs
except ImportError:
    pass
else:
    raise AssertionError('Rust struct own-GIL capability changed')
assert '_struct_rs' not in sys.modules
assert struct.pack('>i', 15) == b'\\x00\\x00\\x00\\x0f'
assert struct._rust_struct is None
assert importlib.reload(_struct).pack('>i', 16) == b'\\x00\\x00\\x00\\x10'
''')
                self.assertIsNone(result, result)
            finally:
                _interpreters.destroy(interpreter)
            self.assertEqual(held_pack('>i', 17), b'\x00\x00\x00\x11')
            self.assertIs(held_pack.__self__, _struct)


if __name__ == '__main__':
    unittest.main()
