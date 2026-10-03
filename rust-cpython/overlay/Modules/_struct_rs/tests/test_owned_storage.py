"""Boundary and ownership checks for standard binary-record storage."""
import _struct
import _struct_rs
import _testcapi
import struct
import sys
import unittest


def outcome(call, *args):
    try:
        return (True, call(*args))
    except Exception as error:
        return (False, type(error), error.args)


def one_allocation_fault(call, args, fail_at):
    result = None
    error = None
    remove = _testcapi.remove_mem_hooks
    _testcapi.set_nomemory(fail_at, fail_at + 1)
    try:
        result = call(*args)
    except BaseException as caught:
        error = caught
    finally:
        remove()
    return result, error


class StructOwnedStorageTests(unittest.TestCase):
    def test_supported_field_boundaries_match_native_bytes(self):
        fields = {
            'b': (-128, 127), 'B': (0, 255),
            'h': (-32768, 32767), 'H': (0, 65535),
            'i': (-(1 << 31), (1 << 31) - 1), 'I': (0, (1 << 32) - 1),
            'l': (-(1 << 31), (1 << 31) - 1), 'L': (0, (1 << 32) - 1),
            'q': (-(1 << 63), (1 << 63) - 1), 'Q': (0, (1 << 64) - 1),
            'f': (-0.0, 1.5), 'd': (-0.0, 1.5), '?': (False, True),
            'c': (b'\x00', b'\xff'),
        }
        self.assertIs(struct.Struct, _struct.Struct)
        self.assertIs(struct.error, _struct.error)
        for prefix in ('<', '>', '!', '='):
            for code, values in fields.items():
                format = prefix + '2' + code
                expected = _struct.pack(format, *values)
                self.assertEqual(_struct_rs.pack(format, values), expected)
                self.assertEqual(struct.pack(format, *values), expected)
                self.assertEqual(_struct_rs.unpack(format, expected), _struct.unpack(format, expected))
            for format, values in ((prefix, ()), (prefix + '0x0i0c', ()),
                                   (prefix + '0s', (b'ignored',)),
                                   (prefix + '4s2x3c', (b'abcdef', b'A', b'B', b'C'))):
                expected = _struct.pack(format, *values)
                self.assertEqual(_struct_rs.pack(format, values), expected)
                self.assertEqual(_struct_rs.unpack(format, expected), _struct.unpack(format, expected))

    def test_many_operations_and_zero_fields_preserve_offsets(self):
        format = '<' + 'x0s0iB' * 1024
        values = tuple(item for index in range(1024) for item in (b'', index & 255))
        expected = _struct.pack(format, *values)
        self.assertEqual(_struct_rs.pack(format, values), expected)
        self.assertEqual(_struct_rs.unpack(format, expected), _struct.unpack(format, expected))
        self.assertEqual(_struct_rs.unpack_from(format, b'prefix' + expected + b'tail', 6),
                         _struct.unpack_from(format, b'prefix' + expected + b'tail', 6))

    def test_unsupported_formats_and_values_keep_native_oracle(self):
        for format, values in (('@n', (17,)), ('<e', (1.5,)), ('<p', (b'abc',)),
                               ('<0', ()), ('<1s?', (b'x', object())),
                               ('<I', (-1,)), ('<c', (b'long',)), ('<s', ('text',)),
                               ('<999999999999999999999I', ())):
            self.assertIs(_struct_rs.pack(format, values), False)
            self.assertEqual(outcome(struct.pack, format, *values),
                             outcome(_struct.pack, format, *values))
        for format in ('@n', '<e', '<p', '< 2I'):
            self.assertIs(_struct_rs.unpack(format, b''), False)
            self.assertEqual(outcome(struct.unpack, format, b''),
                             outcome(_struct.unpack, format, b''))

    def test_exact_buffers_release_after_success_and_rejection(self):
        source = bytearray(b'abcdef')
        self.assertEqual(_struct_rs.pack('<4s', (source,)), b'abcd')
        source.extend(b'!')
        self.assertIs(_struct_rs.pack('<4sI', (source, -1)), False)
        source.extend(b'?')
        record = bytearray(_struct.pack('<I', 17))
        self.assertEqual(_struct_rs.unpack('<I', record), (17,))
        self.assertIs(_struct_rs.unpack_from('<I', record, -1), False)
        record.extend(b'!')
        self.assertIs(_struct_rs.unpack('<I', record), False)
        record.extend(b'?')
        target = bytearray(b'unchanged')
        oracle_target = bytearray(target)
        self.assertEqual(outcome(struct.pack_into, '<I', target, 0, -1),
                         outcome(_struct.pack_into, '<I', oracle_target, 0, -1))
        self.assertEqual(target, oracle_target)

    def test_exporter_reentry_and_format_references_are_scoped(self):
        class Exporter:
            def __init__(self):
                self.storage = bytearray(_struct.pack('<I', 29))
                self.acquired = 0
                self.released = 0

            def __buffer__(self, flags):
                self.assert_nested = struct.pack('<I', 17)
                self.acquired += 1
                return memoryview(self.storage)

            def __release_buffer__(self, view):
                self.released += 1

        exporter = Exporter()
        self.assertIs(_struct_rs.unpack('<I', exporter), False)
        self.assertEqual(exporter.acquired, 0)
        self.assertEqual(struct.unpack('<I', exporter), (29,))
        self.assertEqual(exporter.assert_nested, _struct.pack('<I', 17))
        self.assertEqual((exporter.acquired, exporter.released), (1, 1))
        exporter.storage.extend(b'!')
        self.assertEqual(outcome(struct.unpack, '<I', exporter),
                         outcome(_struct.unpack, '<I', bytearray(exporter.storage)))
        self.assertEqual((exporter.acquired, exporter.released), (2, 2))
        exporter.storage.extend(b'?')
        format = ''.join(('<', '4s', 'I'))
        expected = _struct.pack(format, b'word', 31)
        count = sys.getrefcount(format)
        for _ in range(16):
            self.assertEqual(_struct_rs.pack(format, (b'word', 31)), expected)
        self.assertEqual(sys.getrefcount(format), count)

    def test_fallible_plan_and_output_leave_no_buffer_export(self):
        source = bytearray(b'abcdefgh')
        format = '<8sI8s'
        values = (source, 0x12345678, source)
        expected = _struct.pack(format, bytes(source), 0x12345678, bytes(source))
        record = bytearray(expected)
        operations = ((_struct_rs.pack, (format, values), expected),
                      (_struct_rs.unpack, (format, record), _struct.unpack(format, expected)))
        failures = 0
        for call, args, oracle in operations:
            for fail_at in range(64):
                value, error = one_allocation_fault(call, args, fail_at)
                if error is not None:
                    self.assertIsInstance(error, MemoryError)
                    failures += 1
                else:
                    self.assertEqual(value, oracle)
                source.append(0)
                source.pop()
                record.append(0)
                record.pop()
                self.assertEqual(_struct_rs.pack(format, values), expected)
        self.assertGreater(failures, 0)


if __name__ == '__main__':
    unittest.main()
