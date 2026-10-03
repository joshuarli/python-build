import gc
import unittest
import weakref

import _hashlib
import _hmac_rs


NAMES = (
    "md5", "sha1", "sha224", "sha256", "sha384", "sha512",
    "sha512_224", "sha512_256", "sha3_224", "sha3_256",
    "sha3_384", "sha3_512",
)


class HmacCoreOutputsTests(unittest.TestCase):
    def test_all_outputs_and_key_block_boundaries_match_c_provider(self):
        for name in NAMES:
            for size in (0, 63, 64, 65, 71, 72, 73, 103, 104, 105,
                         127, 128, 129, 135, 136, 137, 143, 144, 145, 257):
                with self.subTest(name=name, size=size):
                    key = bytes(index % 256 for index in range(size))
                    data = bytes(index % 251 for index in range(size))
                    expected = _hashlib.hmac_digest(key, data, name)
                    state = _hmac_rs.new(key, name)
                    self.assertIs(_hmac_rs.update(state, memoryview(data)), state)
                    self.assertEqual(_hmac_rs.digest(state), expected)
                    self.assertEqual(_hmac_rs.hexdigest(state), expected.hex())
                    self.assertEqual(_hmac_rs.compute_digest(key, data, name), expected)
                    copied = _hmac_rs.copy(state)
                    _hmac_rs.update(copied, b"suffix")
                    self.assertEqual(_hmac_rs.digest(copied),
                                     _hashlib.hmac_digest(key, data + b"suffix", name))
                    self.assertEqual(_hmac_rs.digest(state), expected)
                    del copied, state
        gc.collect()

    def test_name_survives_buffer_callbacks_and_capsule_copy_outlives_inputs(self):
        class Name(str):
            pass

        name = Name("sha512")
        name_ref = weakref.ref(name)
        events = []

        class Buffer:
            def __init__(self, label, data):
                self.label = label
                self.data = bytearray(data)

            def __buffer__(self, flags):
                gc.collect()
                self_test.assertIsNotNone(name_ref())
                events.append((self.label, "acquire"))
                return memoryview(self.data)

            def __release_buffer__(self, view):
                events.append((self.label, "release"))

        self_test = self
        key = Buffer("key", b"key")
        data = Buffer("data", b"message")
        expected = _hashlib.hmac_digest(b"key", b"message", "sha512")
        state = _hmac_rs.new(key, name)
        self.assertEqual(events, [("key", "acquire"), ("key", "release")])
        events.clear()
        self.assertEqual(_hmac_rs.compute_digest(key, data, name), expected)
        self.assertEqual(events, [("key", "acquire"), ("data", "acquire"),
                                  ("data", "release"), ("key", "release")])
        _hmac_rs.update(state, data)
        digest = _hmac_rs.digest(state)
        text = _hmac_rs.hexdigest(state)
        copied = _hmac_rs.copy(state)
        key.data[:] = b"changed"
        data.data[:] = b"changed"
        del state, key, data, name
        gc.collect()
        self.assertIsNone(name_ref())
        self.assertEqual(_hmac_rs.digest(copied), expected)
        self.assertEqual(digest, expected)
        self.assertEqual(text, expected.hex())
        _hmac_rs.update(copied, b"suffix")
        self.assertEqual(_hmac_rs.digest(copied),
                         _hashlib.hmac_digest(b"key", b"messagesuffix", "sha512"))
        del copied
        gc.collect()

    def test_validation_order_and_native_capsule_errors(self):
        for call, args in (
            (_hmac_rs.new, (b"key",)),
            (_hmac_rs.compute_digest, (b"key", b"data")),
            (_hmac_rs.update, (object(),)),
        ):
            with self.assertRaisesRegex(TypeError, "invalid number of arguments"):
                call(*args)
        for name in ("unsupported", "sha256\0", "SHA256"):
            with self.assertRaisesRegex(ValueError, "unsupported HMAC digest"):
                _hmac_rs.new(b"key", name)
            with self.assertRaises(TypeError):
                _hmac_rs.new(object(), name)
            with self.assertRaises(TypeError):
                _hmac_rs.compute_digest(b"key", object(), name)
        with self.assertRaises(TypeError):
            _hmac_rs.new(object(), object())
        for call in (_hmac_rs.copy, _hmac_rs.digest, _hmac_rs.hexdigest):
            with self.assertRaises(ValueError):
                call(object())


if __name__ == "__main__":
    unittest.main()
