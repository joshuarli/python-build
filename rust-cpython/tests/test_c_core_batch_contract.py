"""Original C modules retain native APIs and lifetimes across core placement."""
import array
import fcntl
import heapq
import importlib
import json
import math
import os
import random
import select
import struct
import sys
import unittest
import _heapq
import _json
import _math_integer
import _queue
import _random
import _statistics
import _struct


MODULES = ('_struct', '_heapq', '_math_integer', 'math', 'fcntl', 'select',
           '_json', '_queue', '_random', '_statistics', 'array')


class OriginalCCoreBatchContractTests(unittest.TestCase):
    def test_numeric_native_apis_and_errors(self):
        self.assertEqual(_math_integer.comb(8, 3), 56)
        self.assertEqual(_math_integer.gcd(18, 24), 6)
        self.assertEqual(math.sqrt(81), 9)
        self.assertEqual(_statistics._normal_dist_inv_cdf(0.5, 7, 2), 7)
        with self.assertRaises(ValueError):
            math.sqrt(-1)
        with self.assertRaises(TypeError):
            _math_integer.comb(2.5, 1)

    def test_heap_queue_random_and_array_native_ownership(self):
        values = [4, 1, 3, 2]
        _heapq.heapify(values)
        self.assertEqual([_heapq.heappop(values) for _ in range(4)], [1, 2, 3, 4])
        with self.assertRaises(IndexError):
            _heapq.heappop(values)
        queue = _queue.SimpleQueue()
        owner = object()
        queue.put(owner)
        self.assertIs(queue.get_nowait(), owner)
        with self.assertRaises(_queue.Empty):
            queue.get_nowait()
        first, second = _random.Random(1234), _random.Random(1234)
        self.assertEqual([first.getrandbits(24) for _ in range(8)],
                         [second.getrandbits(24) for _ in range(8)])
        numbers = array.array('i', [2, 4, 6])
        copied = array.array('i')
        copied.frombytes(numbers.tobytes())
        self.assertEqual(copied.tolist(), [2, 4, 6])
        with self.assertRaises(BufferError):
            with memoryview(numbers):
                numbers.append(8)
        numbers.append(8)

    def test_posix_descriptors_restore_flags_and_close(self):
        read_fd, write_fd = os.pipe()
        try:
            flags = fcntl.fcntl(read_fd, fcntl.F_GETFL)
            try:
                fcntl.fcntl(read_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                self.assertTrue(fcntl.fcntl(read_fd, fcntl.F_GETFL) & os.O_NONBLOCK)
                os.write(write_fd, b'x')
                self.assertEqual(select.select([read_fd], [], [], 0), ([read_fd], [], []))
                self.assertEqual(os.read(read_fd, 1), b'x')
            finally:
                fcntl.fcntl(read_fd, fcntl.F_SETFL, flags)
            self.assertEqual(fcntl.fcntl(read_fd, fcntl.F_GETFL), flags)
        finally:
            os.close(read_fd)
            os.close(write_fd)

    def test_native_json_codec_and_errors(self):
        self.assertEqual(_json.encode_basestring_ascii('a\u00e9'), '"a\\u00e9"')
        self.assertEqual(_json.scanstring('"a\\n"', 1, True), ('a\n', 5))
        with self.assertRaises(TypeError):
            _json.encode_basestring_ascii(b'bytes')
        with self.assertRaises(ValueError):
            _json.scanstring('"unterminated', 1, True)

    def test_held_native_modules_and_methods_survive_mapping_changes_and_reload(self):
        owners = {name: sys.modules[name] for name in MODULES}
        held = (math.sqrt, _json.encode_basestring_ascii,
                fcntl.fcntl, select.select, _statistics._normal_dist_inv_cdf)
        try:
            for name in MODULES:
                sys.modules[name] = None
            self.assertEqual(held[0](16), 4)
            self.assertEqual(held[1]('owner'), '"owner"')
            for method in held:
                self.assertIs(method.__self__, owners[method.__module__])
        finally:
            sys.modules.update(owners)
        for name, owner in owners.items():
            with self.subTest(module=name):
                self.assertIs(importlib.reload(owner), owner)
        self.assertEqual(held[0](16), 4)

    def test_public_rust_neighbors_receive_real_calls(self):
        import _heapq_rs
        import _json_rs
        import _random_rs
        owners = ((_heapq_rs, 'heappush'),
                  (_json_rs, 'dumps'), (_random_rs, 'choice'))
        original = {(module, name): getattr(module, name) for module, name in owners}
        calls = set()
        def recording(module, name):
            def call(*args):
                calls.add((module.__name__, name))
                return original[module, name](*args)
            return call
        try:
            for module, name in owners:
                setattr(module, name, recording(module, name))
            heap = []
            heapq.heappush(heap, 3)
            self.assertEqual(heap, [3])
            self.assertEqual(json.dumps({'a': 1}), '{"a": 1}')
            self.assertEqual(random.Random(1234).choice(['only']), 'only')
            self.assertEqual(calls, {(module.__name__, name) for module, name in owners})
        finally:
            for (module, name), method in original.items():
                setattr(module, name, method)

    def test_original_c_modules_keep_own_gil_admission(self):
        import _interpreters
        interpreter = _interpreters.create(_interpreters.new_config('isolated', gil='own'))
        try:
            result = _interpreters.run_string(interpreter, """
import array, fcntl, math, select, _heapq, _json, _math_integer, _queue, _random, _statistics, _struct
assert _struct.unpack('>H', _struct.pack('>H', 258)) == (258,)
assert math.sqrt(81) == 9
assert _math_integer.comb(8, 3) == 56
assert _statistics._normal_dist_inv_cdf(0.5, 7, 2) == 7
assert _json.encode_basestring_ascii('owner') == '"owner"'
assert array.array('i', [2, 4]).tolist() == [2, 4]
queue = _queue.SimpleQueue()
queue.put(3)
assert queue.get_nowait() == 3
heap = [3, 1, 2]
_heapq.heapify(heap)
assert _heapq.heappop(heap) == 1
assert select.select([], [], [], 0) == ([], [], [])
first, second = _random.Random(1234), _random.Random(1234)
assert first.getrandbits(24) == second.getrandbits(24)
""")
            self.assertIsNone(result)
        finally:
            _interpreters.destroy(interpreter)


if __name__ == '__main__':
    unittest.main()
