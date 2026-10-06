"""Additional original C modules retain APIs, capsules and interpreter ownership."""
import codecs
import ctypes
import datetime
import hashlib
import importlib
import io
import os
import struct
import subprocess
import sys
import unittest
import _blake2
import _interpreters
import _posixsubprocess
import _socket
import _zoneinfo
import termios
import unicodedata


MODULES = ('_socket', '_posixsubprocess', 'termios', '_zoneinfo',
           '_interpreters', 'unicodedata', '_blake2')


def capsule_valid(capsule, name):
    valid = ctypes.pythonapi.PyCapsule_IsValid
    original = valid.argtypes, valid.restype
    try:
        valid.argtypes = [ctypes.py_object, ctypes.c_char_p]
        valid.restype = ctypes.c_int
        return valid(capsule, name)
    finally:
        valid.argtypes, valid.restype = original


def fixed_zone():
    header = b'TZif' + bytes(16) + struct.pack('>6I', 0, 0, 0, 0, 1, 4)
    return _zoneinfo.ZoneInfo.from_file(io.BytesIO(header + struct.pack('>lbb', 0, 0, 0) + b'UTC\0'), key='fixture-UTC')


class ExtendedOriginalCContractTests(unittest.TestCase):
    def test_socket_capsule_and_owned_pair_survive_module_replacement(self):
        capsule = _socket.CAPI
        self.assertEqual(capsule_valid(capsule, b'_socket.CAPI'), 1)
        import _ssl
        self.assertEqual(_ssl._SSLSocket.__module__, '_ssl')
        owner = sys.modules['_socket']
        first, second = _socket.socketpair()
        held_send, held_recv = first.sendall, second.recv
        try:
            sys.modules['_socket'] = None
            held_send(b'owner')
            self.assertEqual(held_recv(5), b'owner')
            self.assertEqual(capsule_valid(capsule, b'_socket.CAPI'), 1)
            self.assertIs(held_send.__self__, first)
            with self.assertRaises(TypeError):
                held_recv('invalid size')
        finally:
            sys.modules['_socket'] = owner
            first.close()
            second.close()
        self.assertEqual(first.fileno(), -1)
        self.assertEqual(second.fileno(), -1)

    def test_original_fork_exec_remains_the_public_subprocess_owner(self):
        self.assertIs(subprocess._fork_exec, _posixsubprocess.fork_exec)
        with self.assertRaises(TypeError):
            _posixsubprocess.fork_exec()
        original = subprocess._fork_exec
        spawn = subprocess._USE_POSIX_SPAWN
        calls = []
        def forwarding(*args):
            calls.append(True)
            return original(*args)
        child = None
        try:
            subprocess._USE_POSIX_SPAWN = False
            subprocess._fork_exec = forwarding
            child = subprocess.Popen([sys.executable, '-I', '-S', '-B', '-c', 'print("child-contract")'],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = child.communicate(timeout=15)
            self.assertEqual(child.returncode, 0)
            self.assertEqual((stdout, stderr), (b'child-contract\n', b''))
            self.assertEqual(calls, [True])
        finally:
            subprocess._fork_exec = original
            subprocess._USE_POSIX_SPAWN = spawn
            if child is not None:
                if child.poll() is None:
                    child.kill()
                child.wait()
                if child.stdout is not None:
                    child.stdout.close()
                if child.stderr is not None:
                    child.stderr.close()

    def test_termios_error_identity_and_fixed_zone_state(self):
        read_fd, write_fd = os.pipe()
        try:
            with self.assertRaises(termios.error):
                termios.tcgetattr(read_fd)
        finally:
            os.close(read_fd)
            os.close(write_fd)
        with self.assertRaises(TypeError):
            termios.tcgetattr(object())
        zone = fixed_zone()
        held = zone.utcoffset
        self.assertEqual(zone.key, 'fixture-UTC')
        self.assertEqual(held(None), datetime.timedelta(0))
        self.assertEqual(zone.tzname(None), 'UTC')
        with self.assertRaises(ValueError):
            _zoneinfo.ZoneInfo.from_file(io.BytesIO(b'not a TZif header'))
        self.assertEqual(held(None), datetime.timedelta(0))

    def test_unicode_capsule_and_original_lookup_survive_reimport(self):
        original = unicodedata
        capsule = original._ucnhash_CAPI
        self.assertEqual(capsule_valid(capsule, b'unicodedata._ucnhash_CAPI'), 1)
        held = original.lookup
        try:
            sys.modules.pop('unicodedata')
            fresh = importlib.import_module('unicodedata')
            self.assertIsNot(fresh, original)
            self.assertEqual(held('LATIN CAPITAL LETTER A'), 'A')
            self.assertEqual(fresh.normalize('NFC', 'e\u0301'), '\u00e9')
            self.assertEqual(codecs.decode(b'\\N{LATIN CAPITAL LETTER A}', 'unicode_escape'), 'A')
            self.assertEqual(capsule_valid(capsule, b'unicodedata._ucnhash_CAPI'), 1)
            with self.assertRaises(KeyError):
                held('NO SUCH UNICODE CHARACTER')
        finally:
            sys.modules['unicodedata'] = original

    def test_original_blake2_state_copy_and_hashlib_owner(self):
        self.assertIs(hashlib.blake2b, _blake2.blake2b)
        self.assertIs(hashlib.blake2s, _blake2.blake2s)
        for constructor in (_blake2.blake2b, _blake2.blake2s):
            digest = constructor(b'prefix', key=b'key', digest_size=16)
            copied = digest.copy()
            digest.update(b'one')
            copied.update(b'two')
            self.assertEqual(digest.digest(), constructor(b'prefixone', key=b'key', digest_size=16).digest())
            self.assertEqual(copied.digest(), constructor(b'prefixtwo', key=b'key', digest_size=16).digest())
            self.assertNotEqual(digest.digest(), copied.digest())
            with self.assertRaises(ValueError):
                constructor(digest_size=0)

    def test_original_modules_reload_and_hold_native_owners(self):
        held = (_socket.htons, termios.tcgetattr, unicodedata.lookup, _posixsubprocess.fork_exec)
        for name in MODULES:
            owner = sys.modules[name]
            self.assertIs(importlib.reload(owner), owner)
        for method in held:
            self.assertIs(method.__self__, sys.modules[method.__module__])
        self.assertEqual(held[0](1), 256)
        self.assertEqual(held[2]('LATIN CAPITAL LETTER A'), 'A')

    def test_original_interpreters_own_gil_and_outer_survival(self):
        outer = _interpreters.get_current()[0]
        for _ in range(2):
            interpreter = _interpreters.create(_interpreters.new_config('isolated', gil='own'))
            try:
                result = _interpreters.run_string(interpreter, """
import _socket, _posixsubprocess, termios, _zoneinfo, _interpreters, unicodedata, _blake2
assert _interpreters.get_current()[0] != _interpreters.get_main()[0]
assert _socket.htons(1) == 256
assert unicodedata.lookup('LATIN CAPITAL LETTER A') == 'A'
assert _blake2.blake2s(b'abc').digest() == _blake2.blake2s(b'abc').digest()
try:
    termios.tcgetattr(object())
except TypeError:
    pass
else:
    raise AssertionError('non-descriptor accepted')
""")
                self.assertIsNone(result, result)
            finally:
                _interpreters.destroy(interpreter)
        self.assertEqual(_interpreters.get_current()[0], outer)
        self.assertIn(outer, [row[0] for row in _interpreters.list_all()])


if __name__ == '__main__':
    unittest.main()
