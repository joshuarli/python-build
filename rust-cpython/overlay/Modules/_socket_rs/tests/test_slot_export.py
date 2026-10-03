"""Address, borrowed descriptor, and interpreter-owned method contracts."""
import importlib
import socket
import sys
import threading
import unittest

import _socket
import _socket_rs as native


DOCS = {
    "parse_address": "Parse an IPv4 or IPv6 address into network-order bytes",
    "format_address": "Format network-order IPv4 or IPv6 bytes",
    "send": "Send bytes through a borrowed blocking socket descriptor",
    "recv": "Receive bytes through a borrowed blocking socket descriptor",
}


class SlotExportTests(unittest.TestCase):
    def test_four_methods_metadata_addresses_errors_and_buffer_release(self):
        self.assertEqual(native.__doc__, "Rust address conversion and blocking socket I/O")
        for name, doc in DOCS.items():
            method = getattr(native, name)
            self.assertEqual(method.__name__, name)
            self.assertEqual(method.__module__, "_socket_rs")
            self.assertIs(method.__self__, native)
            self.assertEqual(method.__doc__, doc)
            with self.assertRaises(TypeError):
                method()
            with self.assertRaises(TypeError):
                method(unexpected=1)
        self.assertEqual(native.parse_address(4, "192.0.2.1"), b"\xc0\x00\x02\x01")
        packed = bytes.fromhex("20010db8000000000000000000000001")
        self.assertEqual(native.parse_address(6, "2001:db8::1"), packed)
        self.assertEqual(native.format_address(6, packed), "2001:db8::1")
        self.assertEqual(native.format_address(6, b"\0" * 12 + b"\xc0\0\2\1"), "::c000:201")
        for version, text in ((4, "01.2.3.4"), (6, "1::2::3"), (3, "127.0.0.1")):
            with self.assertRaises(ValueError):
                native.parse_address(version, text)
        with self.assertRaises(UnicodeEncodeError):
            native.parse_address(6, "\ud800")
        for packed in (bytearray(b"\x7f\0\0\1"), bytearray(b"bad")):
            if len(packed) == 4:
                self.assertEqual(native.format_address(4, packed), "127.0.0.1")
            else:
                with self.assertRaises(ValueError):
                    native.format_address(4, packed)
            packed.extend(b"x")
        with self.assertRaises(BufferError):
            native.format_address(4, memoryview(bytearray(8))[::2])

    def test_exception_identity_and_reentrant_integer_conversion(self):
        marker = RuntimeError("socket integer conversion sentinel")

        class BadIndex:
            def __index__(self):
                raise marker

        for method, value in ((native.parse_address, "127.0.0.1"),
                              (native.format_address, b"\0" * 4),
                              (native.send, b"x"), (native.recv, 1)):
            with self.assertRaises(RuntimeError) as raised:
                method(BadIndex(), value)
            self.assertIs(raised.exception, marker)

        class ReentrantIndex:
            def __index__(self):
                self.packed = native.parse_address(4, "127.0.0.1")
                return 4

        version = ReentrantIndex()
        self.assertEqual(native.format_address(version, b"\x7f\0\0\1"), "127.0.0.1")
        self.assertEqual(version.packed, b"\x7f\0\0\1")
        with self.assertRaises(OverflowError):
            native.parse_address(2**100, "127.0.0.1")
        with self.assertRaises(ValueError):
            native.send(-1, b"x")
        with self.assertRaises(ValueError):
            native.recv(-1, 1)

    def test_public_dispatch_monkeypatch_fallback_and_native_capsule(self):
        self.assertTrue(issubclass(socket.socket, _socket.socket))
        capsule = _socket.CAPI
        self.assertEqual(type(capsule).__name__, "PyCapsule")
        original = {name: getattr(native, name) for name in DOCS}
        calls = []

        def wrap(name):
            def call(*args):
                calls.append(name)
                return original[name](*args)
            return call

        try:
            for name in DOCS:
                setattr(native, name, wrap(name))
            self.assertEqual(socket.inet_pton(socket.AF_INET, "127.0.0.1"), b"\x7f\0\0\1")
            self.assertEqual(socket.inet_ntop(socket.AF_INET, b"\x7f\0\0\1"), "127.0.0.1")
            left, right = socket.socketpair()
            try:
                payload = bytearray(b"socket")
                count = left.send(payload)
                self.assertGreater(count, 0)
                self.assertEqual(right.recv(count), bytes(payload[:count]))
                payload.extend(b"x")
                count = native.send(right.fileno(), b"reply")
                self.assertGreater(count, 0)
                self.assertEqual(native.recv(left.fileno(), count), b"reply"[:count])
                self.assertGreaterEqual(left.fileno(), 0)
                self.assertGreaterEqual(right.fileno(), 0)
            finally:
                left.close()
                right.close()
            self.assertEqual(set(calls), set(DOCS))
            compatible = b"\0" * 12 + b"\xc0\0\2\1"
            before = len(calls)
            self.assertEqual(socket.inet_ntop(socket.AF_INET6, compatible),
                             socket._native_inet_ntop(socket.AF_INET6, compatible))
            self.assertEqual(len(calls), before)
        finally:
            for name, method in original.items():
                setattr(native, name, method)
        helper = socket._socket_rs
        try:
            socket._socket_rs = None
            sys.modules["_socket_rs"] = None
            self.assertEqual(socket.inet_pton(socket.AF_INET, "127.0.0.1"), b"\x7f\0\0\1")
            left, right = socket.socketpair()
            try:
                count = left.send(b"fallback")
                self.assertGreater(count, 0)
                self.assertEqual(right.recv(count), b"fallback"[:count])
            finally:
                left.close()
                right.close()
        finally:
            socket._socket_rs = helper
            sys.modules["_socket_rs"] = native
        self.assertIs(_socket.CAPI, capsule)

    def test_reload_reimport_and_thread_transfer_keep_held_methods_live(self):
        methods = tuple(getattr(native, name) for name in DOCS)
        self.assertIs(importlib.reload(native), native)
        self.assertEqual(tuple(getattr(native, name) for name in DOCS), methods)
        module = sys.modules.pop("_socket_rs")
        try:
            replacement = importlib.import_module("_socket_rs")
            self.assertIs(methods[0].__self__, module)
            self.assertIs(replacement.parse_address.__self__, replacement)
            self.assertEqual(methods[0](4, "127.0.0.1"), replacement.parse_address(4, "127.0.0.1"))
        finally:
            sys.modules["_socket_rs"] = module
        failures = []

        def worker():
            try:
                self.assertEqual(methods[0](4, "127.0.0.1"), b"\x7f\0\0\1")
                self.assertEqual(methods[1](4, b"\x7f\0\0\1"), "127.0.0.1")
                self.assertTrue(all(method.__self__ is native for method in methods))
            except BaseException as error:
                failures.append((type(error).__name__, str(error)))

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(10)
        self.assertFalse(thread.is_alive(), "socket method worker did not finish")
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
