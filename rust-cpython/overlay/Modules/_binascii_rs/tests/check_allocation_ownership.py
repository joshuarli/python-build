"""Check native temporary and output ownership on bounded allocation failures."""
import importlib.util
import sys
import unittest
import _binascii_rs as native

spec = importlib.util.spec_from_file_location('_binascii_allocation_test', sys.argv.pop(1))
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


class BinasciiAllocationOwnership(unittest.TestCase):
    def assert_clean(self, failure):
        counts = observer.counts()
        attempts, successes, frees, live, failed, foreign, overflow, backend, calloc, realloc = counts
        self.assertEqual((successes, live, failed, foreign, overflow, backend, calloc),
                         (frees, 0, failure, 0, 0, 0, 0))
        return attempts

    def check_failures(self, method, arguments, domain):
        expected = method(*arguments)
        self.assertIs(type(expected), bytes)
        sink = bytearray(len(expected))
        references = tuple(sys.getrefcount(argument) for argument in arguments)
        self.assertIsNone(observer.drive(method, arguments, sink, 0, domain))
        self.assertEqual(sink, expected)
        attempts = self.assert_clean(0)
        self.assertGreater(attempts, 0)
        self.assertLessEqual(attempts, 8)
        for ordinal in range(1, attempts + 1):
            with self.subTest(method=method.__name__, domain=domain, failure=ordinal):
                with self.assertRaises(MemoryError):
                    observer.drive(method, arguments, sink, ordinal, domain)
                self.assert_clean(1)
                self.assertEqual(tuple(sys.getrefcount(argument) for argument in arguments), references)
                self.assertIsNone(observer.drive(method, arguments, sink, 0, domain))
                self.assertEqual(sink, expected)
                self.assertEqual(self.assert_clean(0), attempts)

    def test_mem_snapshot_and_filtered_decode_failures_release_and_retry(self):
        data = b'abcdefgh' * 257
        cases = [(native.b64decode, (native.standard_b64encode(data) + b'\n!\t', False, True)),
                 (native.b85encode, (data, False)),
                 (native.b85decode, (native.b85encode(data, False),)),
                 (native.z85encode, (data, False)),
                 (native.z85decode, (native.z85encode(data, False),)),
                 (native.a85encode, (data,)),
                 (native.a85decode, (native.a85encode(data),))]
        for method, arguments in cases:
            self.check_failures(method, arguments, 1)

    def test_object_output_failures_release_and_retry(self):
        data = b'abcdefgh' * 257 + b'q'
        aligned = data[:-1]
        cases = [(native.b2a_hex, (data,)), (native.hexlify, (data,)),
                 (native.a2b_hex, (native.hexlify(data),)),
                 (native.unhexlify, (native.hexlify(data),)),
                 (native.standard_b64encode, (data,)), (native.urlsafe_b64encode, (data,)),
                 (native.b64decode, (native.standard_b64encode(data), True, True)),
                 (native.b16encode, (data,)), (native.b16decode, (native.b16encode(data),)),
                 (native.b32encode, (data, True)), (native.b32decode, (native.b32encode(data, True), True)),
                 (native.b32hexencode, (data, True)), (native.b32hexdecode, (native.b32hexencode(data, True), True)),
                 (native.b85encode, (data, False)), (native.b85decode, (native.b85encode(data, False),)),
                 (native.z85encode, (aligned, False)), (native.z85decode, (native.z85encode(aligned, False),)),
                 (native.a85encode, (data,)), (native.a85decode, (native.a85encode(data),))]
        for method, arguments in cases:
            self.check_failures(method, arguments, 2)

    def test_clean_decode_and_direct_encode_need_no_mem_snapshot(self):
        data = b'abcdefgh' * 257
        for method, arguments in ((native.standard_b64encode, (data,)),
                                  (native.b64decode, (native.standard_b64encode(data), True, True)),
                                  (native.b16encode, (data,)), (native.b32encode, (data, True)),
                                  (native.hexlify, (data,))):
            expected = method(*arguments)
            sink = bytearray(len(expected))
            self.assertIsNone(observer.drive(method, arguments, sink, 1, 1))
            self.assertEqual(sink, expected)
            self.assertEqual(observer.counts(), (0,) * 10)


if __name__ == '__main__':
    unittest.main()
