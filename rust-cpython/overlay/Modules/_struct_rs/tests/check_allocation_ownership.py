"""Observe exact plan ownership and retain public binary-record providers."""
import importlib.util
import sys
import unittest
import _struct
import _struct_rs
import struct

spec = importlib.util.spec_from_file_location("_struct_allocation_test", sys.argv.pop(1))
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


class StructPlanOwnership(unittest.TestCase):
    def check_counts(self, attempts, successes, failed):
        self.assertEqual(observer.counts(),
                         (attempts, successes, successes, 0, failed, 0, 0, 0, 0, 0))

    def test_plan_success_and_allocation_failure_release_storage(self):
        observer.module_contract(_struct_rs)
        format = '<' + 'x0s0iB' * 1024
        values = tuple(item for index in range(1024) for item in (b'', index & 255))
        expected = _struct.pack(format, *values)
        for method, right, result in ((_struct_rs.pack, values, expected),
                                     (_struct_rs.unpack, expected, _struct.unpack(format, expected))):
            self.assertEqual(observer.drive(method, format, right, 0), result)
            self.check_counts(1, 1, 0)
            with self.assertRaises(MemoryError):
                observer.drive(method, format, right, 1)
            self.check_counts(1, 0, 1)
            self.assertEqual(observer.drive(method, format, right, 0), result)
            self.check_counts(1, 1, 0)

    def test_full_validation_and_rejected_values_release_storage(self):
        for method, format, right, attempts in (
            (_struct_rs.pack, '<999999999999999999999I', (), 0),
            (_struct_rs.pack, '<I?', (17, object()), 1),
            (_struct_rs.pack, '<I', (-1,), 1),
            (_struct_rs.unpack, '<I', b'wrong length', 1),
        ):
            self.assertIs(observer.drive(method, format, right, 0), False)
            self.check_counts(attempts, attempts, 0)
        self.assertEqual(observer.drive(_struct_rs.pack, '<', (), 1), b'')
        self.check_counts(0, 0, 0)
        source = bytearray(b'abcd')
        self.assertEqual(observer.drive(_struct_rs.pack, '<4s', (source,), 0), b'abcd')
        self.check_counts(1, 1, 0)
        source.extend(b'!')
        self.assertIs(observer.drive(_struct_rs.pack, '<4sI', (source, -1), 0), False)
        self.check_counts(1, 1, 0)
        source.extend(b'?')

    def test_public_calls_retain_helper_and_native_type_identity(self):
        self.assertIs(struct.Struct, _struct.Struct)
        self.assertIs(struct.error, _struct.error)
        calls = []
        originals = {name: getattr(_struct_rs, name) for name in ('pack', 'unpack', 'unpack_from')}
        def traced(name):
            def invoke(*args):
                calls.append(name)
                return originals[name](*args)
            return invoke
        try:
            for name in originals:
                setattr(_struct_rs, name, traced(name))
            packed = struct.pack('<I', 17)
            self.assertEqual(packed, _struct.pack('<I', 17))
            self.assertEqual(struct.unpack('<I', packed), (17,))
            self.assertEqual(struct.unpack_from('<I', b'x' + packed, 1), (17,))
            target = bytearray(4)
            self.assertIsNone(struct.pack_into('<I', target, 0, 17))
            self.assertEqual(target, packed)
            self.assertEqual(calls, ['pack', 'unpack', 'unpack_from', 'pack'])
        finally:
            for name, method in originals.items():
                setattr(_struct_rs, name, method)


if __name__ == '__main__':
    unittest.main()
