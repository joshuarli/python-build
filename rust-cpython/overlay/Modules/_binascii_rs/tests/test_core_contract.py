"""Observable contracts for the core-only binascii and Base64 engines."""

import inspect
import binascii
import importlib.machinery
import importlib.util
import unittest
import _base64 as original
import _binascii_rs as native


class CoreBinasciiContractTests(unittest.TestCase):
    def test_dynamic_hex_error_class_and_method_metadata(self):
        previous = binascii.Error
        class ReplacementError(Exception):
            pass
        try:
            binascii.Error = ReplacementError
            for name in ("a2b_hex", "unhexlify"):
                for data, message in ((b"g0", "Non-hexadecimal digit found"),
                                      (b"0", "Odd number of hexadecimal digits")):
                    with self.assertRaises(ReplacementError) as caught:
                        getattr(native, name)(data)
                    self.assertEqual(str(caught.exception), message)
        finally:
            binascii.Error = previous
        for name in ("b2a_hex", "hexlify", "a2b_hex", "unhexlify", "crc32", "crc_hqx"):
            function = getattr(native, name)
            self.assertEqual(function.__name__, name)
            self.assertEqual(function.__module__, "binascii")
            self.assertIs(function.__self__, native)
            self.assertIs(getattr(binascii, name), function)
        with self.assertRaises(OverflowError):
            native.hexlify(b"abc", bytes_per_sep=1 << 100)
        self.assertEqual(native.hexlify(b"\0\1", sep="\xff"), b"00\xff01")

    def test_existing_base64_initializer_export(self):
        loader = importlib.machinery.ExtensionFileLoader("_base64", native.__file__)
        spec = importlib.util.spec_from_file_location("_base64", native.__file__, loader=loader)
        alias = importlib.util.module_from_spec(spec)
        loader.exec_module(alias)
        self.assertEqual(alias.__name__, "_base64")
        self.assertEqual(alias.__doc__, original.__doc__)
        for name in ("standard_b64encode", "urlsafe_b64encode", "b64decode",
                     "b16encode", "b16decode", "b32encode", "b32decode",
                     "b32hexencode", "b32hexdecode", "b85encode", "b85decode",
                     "z85encode", "z85decode", "a85encode", "a85decode"):
            self.assertEqual(getattr(alias, name).__module__, "_base64")
            self.assertEqual(getattr(alias, name).__doc__, getattr(original, name).__doc__)
        self.assertEqual(alias.standard_b64encode(b"abc"), original.standard_b64encode(b"abc"))

    def test_all_original_engine_bytes_and_rejections(self):
        payloads = [b"", b"f", b"fo", b"foo", b"foob", b"fooba", b"foobar",
                    b"\0" * 16, bytes(range(256)), b"record=value\n" * 73]
        for name in ("standard_b64encode", "urlsafe_b64encode", "b32encode",
                     "b32hexencode", "b85encode", "z85encode"):
            for data in payloads:
                for padded in (False, True):
                    with self.subTest(name=name, size=len(data), padded=padded):
                        self.assertEqual(getattr(native, name)(data, padded),
                                         getattr(original, name)(data, padded))
        for name in ("b16encode", "a85encode"):
            for data in payloads:
                self.assertEqual(getattr(native, name)(data), getattr(original, name)(data))
        for name in ("b16decode", "b85decode", "z85decode", "a85decode"):
            encoder = name.replace("decode", "encode")
            for data in payloads:
                encoded = getattr(original, encoder)(data) if name in ("b16decode", "a85decode") else getattr(original, encoder)(data, False)
                self.assertEqual(getattr(native, name)(encoded), getattr(original, name)(encoded))
            for invalid in (b"?", b"\xff", b"uuuuu", b"~~~~~", b"!z", b"z z", b"!!\v!!!"):
                self.assertEqual(getattr(native, name)(invalid), getattr(original, name)(invalid))
        for name in ("b32decode", "b32hexdecode"):
            encoder = name.replace("decode", "encode")
            for data in payloads:
                for padded in (False, True):
                    encoded = getattr(original, encoder)(data, padded)
                    self.assertEqual(getattr(native, name)(encoded, padded),
                                     getattr(original, name)(encoded, padded))
            for invalid in (b"A", b"ABC", b"AB======", b"ab======", b"\xff"):
                for padded in (False, True):
                    self.assertEqual(getattr(native, name)(invalid, padded),
                                     getattr(original, name)(invalid, padded))
        for data in (b"", b"Zg==", b"Zh==", b"Z g==", b"Zg", b"Zg=", b"Zg===", b"AA=A", b"Zg==x", b"\xffZg=="):
            for validate in (False, True):
                for padded in (False, True):
                    self.assertEqual(native.b64decode(data, validate, padded),
                                     original.b64decode(data, validate, padded))

    def test_keyword_parser_spelling_and_signature(self):
        self.assertEqual(str(inspect.signature(native.hexlify)),
                         "(data, /, sep=None, bytes_per_sep=1)")
        cases = [
            (native.hexlify, (), {}, "hexlify() missing required argument 'data' (pos 1)"),
            (native.hexlify, (b"x",), {"data": b"x"}, "hexlify() got some positional-only arguments passed as keyword arguments: 'data'"),
            (native.hexlify, (b"x", b":"), {"sep": b":"}, "hexlify() got multiple values for argument 'sep'"),
            (native.hexlify, (b"x",), {"bad\0key": 1}, "hexlify() got an unexpected keyword argument 'bad\\x00key'"),
            (native.crc32, (), {"data": b"x"}, "crc32() got some positional-only arguments passed as keyword arguments: 'data'"),
            (native.crc_hqx, (b"x",), {}, "crc_hqx() missing required argument 'crc' (pos 2)"),
            (native.unhexlify, (b"aa", b""), {}, "unhexlify() takes at most 1 positional arguments (2 given)"),
        ]
        for function, args, kwargs, message in cases:
            with self.subTest(function=function.__name__, message=message):
                with self.assertRaises(TypeError) as caught:
                    function(*args, **kwargs)
                self.assertEqual(str(caught.exception), message)
        with self.assertRaises(UnicodeEncodeError):
            native.hexlify(b"x", **{"bad\ud800": 1})
        self.assertEqual(native.hexlify(b"\x01\x23\x45\x67\x89", sep=b":", bytes_per_sep=2), b"01:2345:6789")
        self.assertEqual(native.hexlify(b"\x01\x23\x45\x67\x89", sep=b":", bytes_per_sep=-2), b"0123:4567:89")
        self.assertEqual(native.unhexlify("a: a", ignorechars=b": "), b"\xaa")

    def test_checksums_seed_masking_and_index_errors(self):
        self.assertEqual(native.crc32(b"123456789"), 0xcbf43926)
        self.assertEqual(native.crc_hqx(b"123456789", 0), 0x31c3)
        self.assertEqual(native.crc32(b"second", native.crc32(b"first")), native.crc32(b"firstsecond"))
        self.assertEqual(native.crc32(b"abc", -1), native.crc32(b"abc", (1 << 64) - 1))
        class IndexFailure:
            def __index__(self):
                raise RuntimeError("index failure")
        with self.assertRaisesRegex(RuntimeError, "index failure"):
            native.crc32(b"abc", IndexFailure())

    def test_truth_callback_and_noncontiguous_buffer_errors(self):
        class TruthFailure:
            def __bool__(self):
                raise RuntimeError("truth failure")
        for name in ("standard_b64encode", "urlsafe_b64encode", "b32encode",
                     "b32hexencode", "b85encode", "z85encode"):
            with self.assertRaisesRegex(RuntimeError, "truth failure"):
                getattr(native, name)(b"x", TruthFailure())
        for name in ("b32decode", "b32hexdecode"):
            with self.assertRaisesRegex(RuntimeError, "truth failure"):
                getattr(native, name)(b"", TruthFailure())
        with self.assertRaisesRegex(RuntimeError, "truth failure"):
            native.b64decode(b"", TruthFailure(), True)
        for name in ("b16encode", "a85encode", "standard_b64encode"):
            with self.assertRaises(BufferError):
                getattr(native, name)(memoryview(b"abcdef")[::2])
        with self.assertRaises(TypeError):
            native.b16encode("abc")

    def test_base85_exporter_release_preserves_snapshot(self):
        class Exporter:
            def __init__(self, data):
                self.data = bytearray(data)
                self.events = []
            def __buffer__(self, flags):
                self.events.append("borrow")
                return memoryview(self.data)
            def __release_buffer__(self, view):
                self.events.append("release")
                self.data[:] = b"x" * len(self.data)
        for name in ("b85encode", "z85encode", "a85encode"):
            for data in (b"", b"\0" * 9, b"abcdefgh"):
                exporter = Exporter(data)
                expected = getattr(original, name)(data) if name == "a85encode" else getattr(original, name)(data, False)
                actual = getattr(native, name)(exporter) if name == "a85encode" else getattr(native, name)(exporter, False)
                self.assertEqual(actual, expected)
                self.assertEqual(exporter.events, ["borrow", "release"])
        for name in ("b85decode", "z85decode", "a85decode"):
            data = getattr(original, name.replace("decode", "encode"))(b"abcdefgh") if name == "a85decode" else getattr(original, name.replace("decode", "encode"))(b"abcdefgh", False)
            exporter = Exporter(data)
            self.assertEqual(getattr(native, name)(exporter), b"abcdefgh")
            self.assertEqual(exporter.events, ["borrow", "release"])


if __name__ == "__main__":
    unittest.main()
