"""Check UUID helper outputs, buffer release, errors and public RFC bits."""
import unittest
import uuid
import _uuid_rs as native


class UUIDCoreContractTests(unittest.TestCase):
    def test_method_metadata_and_arity_diagnostics(self):
        for name in ('parse_hex', 'normalize', 'set_version', 'uuid3', 'uuid4',
                     'uuid5', 'format', 'format_hex'):
            method = getattr(native, name)
            self.assertEqual(method.__name__, name)
            self.assertEqual(method.__module__, '_uuid_rs')
            self.assertIs(method.__self__, native)
        for method, arguments, message in (
                (native.parse_hex, (), 'parse_hex() takes exactly one argument'),
                (native.normalize, (), 'normalize() takes exactly one argument'),
                (native.set_version, (), 'set_version() takes exactly two arguments'),
                (native.uuid3, (), 'name UUID generator takes exactly one argument'),
                (native.uuid5, (), 'name UUID generator takes exactly one argument'),
                (native.uuid4, (b'',), 'uuid4() takes no arguments'),
                (native.format, (), 'format() takes exactly one argument'),
                (native.format_hex, (), 'format() takes exactly one argument')):
            with self.assertRaises(TypeError) as caught:
                method(*arguments)
            self.assertEqual(str(caught.exception), message)

    def test_parse_format_and_exports_release_on_success_and_error(self):
        raw = bytes.fromhex('12345678123456781234567812345678')
        for spelling in (b'12345678123456781234567812345678',
                         b'12345678-1234-5678-1234-567812345678',
                         b'{12345678-1234-5678-1234-567812345678}',
                         b'urn:uuid:12345678-1234-5678-1234-567812345678'):
            data = bytearray(spelling)
            self.assertEqual(native.parse_hex(data), raw)
            data.extend(b'x')
        for spelling in (b'z' * 32, b'\xff' * 32, b''):
            data = bytearray(spelling)
            with self.assertRaisesRegex(ValueError, '^invalid UUID hexadecimal data$'):
                native.parse_hex(data)
            data.extend(b'x')
        for method, expected in ((native.normalize, raw),
                                 (native.format, b'12345678-1234-5678-1234-567812345678'),
                                 (native.format_hex, b'12345678123456781234567812345678')):
            data = bytearray(raw)
            self.assertEqual(method(data), expected)
            data.extend(b'x')
            with self.assertRaisesRegex(ValueError, '^UUID data must contain exactly 16 bytes$'):
                method(data)
            data.extend(b'x')
        with self.assertRaises(TypeError):
            native.parse_hex('12345678123456781234567812345678')
        with self.assertRaises(BufferError):
            native.normalize(memoryview(bytearray(32))[::2])

    def test_versions_name_vectors_random_bits_and_public_route(self):
        raw = bytes.fromhex('12345678123456781234567812345678')
        for version in range(1, 9):
            result = native.set_version(raw, bytes([version]))
            expected = bytearray(raw)
            expected[6] = (expected[6] & 15) | (version << 4)
            expected[8] = (expected[8] & 63) | 128
            self.assertEqual(result, expected)
            self.assertEqual(uuid.UUID(bytes=raw, version=version).bytes, result)
        for version in (b'', b'\0', b'\x09', b'\x01\x02'):
            with self.assertRaisesRegex(ValueError, '^illegal UUID version number$'):
                native.set_version(raw, version)
        payload = uuid.NAMESPACE_DNS.bytes + b'python.org'
        self.assertEqual(native.uuid3(payload).hex(), '6fa459eaee8a3ca4894edb77e160355e')
        self.assertEqual(native.uuid5(payload).hex(), '886313e13b8a53729b900c9aee199e5d')
        self.assertEqual(uuid.uuid3(uuid.NAMESPACE_DNS, 'python.org').bytes, native.uuid3(payload))
        self.assertEqual(uuid.uuid5(uuid.NAMESPACE_DNS, 'python.org').bytes, native.uuid5(payload))
        for method in (native.uuid3, native.uuid5):
            with self.assertRaisesRegex(ValueError, '^namespace UUID data must contain 16 bytes$'):
                method(b'')
        random = native.uuid4()
        self.assertEqual(len(random), 16)
        self.assertEqual(random[6] >> 4, 4)
        self.assertEqual(random[8] & 192, 128)
        public = uuid.UUID(bytes=random)
        self.assertEqual(public.version, 4)
        self.assertEqual(public.hex.encode(), native.format_hex(random))
        self.assertEqual(str(public).encode(), native.format(random))


if __name__ == '__main__':
    unittest.main()
