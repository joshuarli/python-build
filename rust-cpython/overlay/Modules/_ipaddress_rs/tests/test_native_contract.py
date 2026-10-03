"""Ownership and parsing contracts for the native address operations."""
import importlib
import ipaddress
import sys
import threading
import unittest

import _ipaddress_rs as native


class NativeAddressContract(unittest.TestCase):
    def test_parse_boundaries_and_public_errors(self):
        for text in ('0.0.0.0', '255.255.255.255', '127.0.0.1'):
            self.assertEqual(native.parse_ipv4(text), ipaddress.IPv4Address(text).packed)
        for text in ('::', 'ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff',
                     '::ffff:192.0.2.1', '2001:db8::1'):
            self.assertEqual(native.parse_ipv6(text), ipaddress.IPv6Address(text).packed)
        for cls, method, text in ((ipaddress.IPv4Address, native.parse_ipv4, '01.2.3.4'),
                                  (ipaddress.IPv6Address, native.parse_ipv6, '1::2::3')):
            with self.assertRaises(ValueError):
                method(text)
            with self.assertRaises(ipaddress.AddressValueError):
                cls(text)
        with self.assertRaises(TypeError):
            native.parse_ipv4(123)
        with self.assertRaises(UnicodeEncodeError):
            native.parse_ipv6('\ud800')

    def test_bounds_and_exporter_release(self):
        for width in (4, 16):
            packed = bytearray(range(width))
            value = int.from_bytes(packed, 'big')
            for prefix in (0, 1, width * 8 - 1, width * 8):
                mask = ((1 << (width * 8)) - 1) ^ ((1 << (width * 8 - prefix)) - 1)
                expected = ((value & mask).to_bytes(width, 'big') +
                            (value | (((1 << (width * 8)) - 1) ^ mask)).to_bytes(width, 'big'))
                self.assertEqual(native.network_bounds(packed, prefix), expected)
            packed.extend(b'x')
        for prefix in (-1, 129, object()):
            packed = bytearray(16)
            with self.assertRaises((ValueError, TypeError)):
                native.network_bounds(packed, prefix)
            packed.extend(b'x')
        packed = bytearray(3)
        with self.assertRaises(ValueError):
            native.network_bounds(packed, 0)
        packed.extend(b'x')

    def test_index_callback_and_noncontiguous_buffer(self):
        packed = bytearray(4)
        failure = RuntimeError('index callback')
        class Prefix:
            def __index__(self):
                raise failure
        with self.assertRaises(RuntimeError) as caught:
            native.network_bounds(packed, Prefix())
        self.assertIs(caught.exception, failure)
        packed.extend(b'x')
        with self.assertRaises(BufferError):
            native.network_bounds(memoryview(bytearray(8))[::2], 0)

    def test_held_functions_reload_and_helper_replacement(self):
        held = native.parse_ipv4
        self.assertIs(held.__self__, native)
        module = sys.modules.pop('_ipaddress_rs')
        try:
            again = importlib.import_module('_ipaddress_rs')
            self.assertEqual(held('10.0.0.1'), again.parse_ipv4('10.0.0.1'))
            self.assertIs(held.__self__, module)
            self.assertEqual(importlib.reload(again).network_bounds(b'\xff' * 4, 0),
                             b'\0' * 4 + b'\xff' * 4)
        finally:
            sys.modules['_ipaddress_rs'] = module

    def test_parallel_result_ownership(self):
        results, errors = [], []
        def worker():
            try:
                for _ in range(128):
                    result = native.parse_ipv6('2001:db8::1')
                    self.assertEqual(len(result), 16)
                    results.append(result)
            except BaseException as error:
                errors.append(error)
        workers = [threading.Thread(target=worker, daemon=True) for _ in range(2)]
        for worker_thread in workers:
            worker_thread.start()
        for worker_thread in workers:
            worker_thread.join(10)
        self.assertFalse(any(worker_thread.is_alive() for worker_thread in workers))
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 256)
        self.assertTrue(all(value == results[0] for value in results))


if __name__ == '__main__':
    unittest.main()
