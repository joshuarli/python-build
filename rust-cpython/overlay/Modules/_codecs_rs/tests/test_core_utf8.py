"""Check UTF-8 conversion, fallback boundaries and public Rust reachability."""

import _codecs_rs
import codecs
import unittest


class CoreUtf8Tests(unittest.TestCase):
    def test_encoding_preserves_native_output_and_fallback(self):
        for text in ('', 'ASCII', 'a\0b', '日本語', '€𐀀'):
            with self.subTest(text=text):
                self.assertEqual(_codecs_rs.encode_utf8(text),
                                 codecs.utf_8_encode(text)[0])
        self.assertIsNone(_codecs_rs.encode_utf8('\ud800'))
        self.assertIsNone(_codecs_rs.encode_utf8(b'not text'))
        with self.assertRaises(UnicodeEncodeError):
            codecs.getincrementalencoder('utf-8')().encode('\ud800')

    def test_every_chunk_boundary_matches_native_decoder(self):
        data = 'A€𐀀\0日本語B'.encode('utf-8')
        for end in range(len(data) + 1):
            prefix = data[:end]
            for final in (False, True):
                with self.subTest(end=end, final=final):
                    try:
                        expected = codecs.utf_8_decode(prefix, 'strict', final)
                    except UnicodeDecodeError:
                        expected = None
                    self.assertEqual(_codecs_rs.decode_utf8(prefix, final), expected)

    def test_invalid_sequences_and_truth_conversion(self):
        for data in (b'\xff', b'\xc0\x80', b'\xed\xa0\x80', b'\xf4\x90\x80\x80',
                     b'A\xe2x', b'\x80'):
            for final in (False, True):
                with self.subTest(data=data, final=final):
                    self.assertIsNone(_codecs_rs.decode_utf8(data, final))
        self.assertEqual(_codecs_rs.decode_utf8(b'A\xe2\x82', []), ('A', 1))
        self.assertIsNone(_codecs_rs.decode_utf8(b'A\xe2\x82', [1]))

        class InvalidTruth:
            def __bool__(self):
                raise RuntimeError('final truth failed')

        with self.assertRaisesRegex(RuntimeError, 'final truth failed'):
            _codecs_rs.decode_utf8(b'A', InvalidTruth())
        with self.assertRaises(TypeError):
            _codecs_rs.decode_utf8(bytearray(b'A'), True)
        with self.assertRaisesRegex(TypeError, 'decode_utf8 expects data and final'):
            _codecs_rs.decode_utf8(b'A')

    def test_public_incremental_conversion_reaches_rust(self):
        encode = _codecs_rs.encode_utf8
        decode = _codecs_rs.decode_utf8
        calls = []

        def observed_encode(text):
            calls.append('encode')
            return encode(text)

        def observed_decode(data, final):
            calls.append('decode')
            return decode(data, final)

        _codecs_rs.encode_utf8 = observed_encode
        _codecs_rs.decode_utf8 = observed_decode
        try:
            encoded = codecs.getincrementalencoder('utf-8')().encode('A€')
            decoder = codecs.getincrementaldecoder('utf-8')()
            first = decoder.decode(b'A\xe2', False)
            second = decoder.decode(b'\x82\xac', True)
        finally:
            _codecs_rs.encode_utf8 = encode
            _codecs_rs.decode_utf8 = decode
        self.assertEqual(encoded, b'A\xe2\x82\xac')
        self.assertEqual((first, second), ('A', '€'))
        self.assertEqual(calls, ['encode', 'decode', 'decode'])


if __name__ == '__main__':
    unittest.main()
