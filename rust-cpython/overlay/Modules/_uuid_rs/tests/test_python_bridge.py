"""Python error and buffer ownership contracts of the Rust UUID bridge."""

import unittest
import uuid
import _uuid_rs


class UUIDParsingCompatibilityTests(unittest.TestCase):
    def test_rust_backend_with_own_interpreter_gil(self):
        import _interpreters

        interpreter = _interpreters.create()
        try:
            result = _interpreters.run_string(interpreter, """
import _uuid_rs
text = '0123456789abcdef0123456789abcdef'
data = _uuid_rs.parse_hex(text)
assert _uuid_rs.format(data) == '01234567-89ab-cdef-0123-456789abcdef'
assert _uuid_rs.format_hex(data) == text
import uuid
assert uuid._uuid_rs is _uuid_rs
assert uuid.UUID(text).hex == text
assert uuid.uuid4().version == 4
assert uuid.uuid3(uuid.NAMESPACE_DNS, 'python.org').version == 3
assert uuid.uuid5(uuid.NAMESPACE_DNS, 'python.org').version == 5
""")
            self.assertIsNone(result)
        finally:
            _interpreters.destroy(interpreter)

    def test_nonascii_failure_keeps_ascii_encoding_context(self):
        for invalid in ('\u2603', '\ud800'):
            with self.subTest(invalid=repr(invalid)):
                with self.assertRaises(ValueError) as caught:
                    uuid.UUID('f' * 31 + invalid)
                context = caught.exception.__context__
                self.assertIsInstance(context, UnicodeEncodeError)
                self.assertEqual(context.encoding, 'ascii')

    def test_buffer_parse_releases_export_and_copies_result(self):
        text = '0123456789abcdef0123456789abcdef'
        data = bytearray(text, 'ascii')
        parsed = _uuid_rs.parse_hex(data)
        data[:] = b'f' * 32
        data.append(0)
        self.assertEqual(parsed, bytes.fromhex(text))


if __name__ == '__main__':
    unittest.main()
