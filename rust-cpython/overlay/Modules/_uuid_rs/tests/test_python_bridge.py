"""Python error and buffer ownership contracts of the Rust UUID bridge."""

import unittest
import uuid
import _uuid_rs


class UUIDParsingCompatibilityTests(unittest.TestCase):
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
