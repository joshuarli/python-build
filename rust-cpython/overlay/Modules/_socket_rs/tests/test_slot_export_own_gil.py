"""Interpreter-owned helper methods under separately admitted native startup."""
import unittest

import _socket_rs as native
import _interpreters


class OwnGilSlotExportTests(unittest.TestCase):
    def test_isolated_interpreter_methods_public_route_and_outer_survival(self):
        method = native.parse_address
        interpreter = _interpreters.create("isolated")
        try:
            self.assertEqual(_interpreters.get_config(interpreter).gil, "own")
            result = _interpreters.run_string(interpreter, r"""
import importlib
import socket
import _socket
import _socket_rs as native
assert native.parse_address.__self__ is native
assert native.parse_address(4, '192.0.2.1') == b'\xc0\x00\x02\x01'
assert native.format_address(6, bytes.fromhex('20010db8000000000000000000000001')) == '2001:db8::1'
for method, value in ((native.send, b'x'), (native.recv, 1)):
    try:
        method(-1, value)
    except ValueError:
        pass
    else:
        raise AssertionError('negative descriptor unexpectedly accepted')
assert issubclass(socket.socket, _socket.socket)
assert type(_socket.CAPI).__name__ == 'PyCapsule'
left, right = socket.socketpair()
try:
    count = native.send(left.fileno(), b'own-gil')
    assert count > 0
    assert native.recv(right.fileno(), count) == b'own-gil'[:count]
    assert left.fileno() >= 0 and right.fileno() >= 0
finally:
    left.close()
    right.close()
held = native.parse_address
assert importlib.reload(native) is native
assert native.parse_address is held
original = native.parse_address
try:
    native.parse_address = lambda version, text: b'own-gil'
    assert socket.inet_pton(socket.AF_INET, '127.0.0.1') == b'own-gil'
finally:
    native.parse_address = original
assert socket.inet_pton(socket.AF_INET, '127.0.0.1') == b'\x7f\x00\x00\x01'
""")
            self.assertIsNone(result)
        except BaseException as primary:
            try:
                _interpreters.destroy(interpreter)
            except BaseException as cleanup:
                primary.add_note(f"interpreter destruction also failed: {cleanup!r}")
            raise
        else:
            _interpreters.destroy(interpreter)
        self.assertIs(native.parse_address, method)
        self.assertIs(method.__self__, native)
        self.assertEqual(method(4, "192.0.2.1"), b"\xc0\x00\x02\x01")


if __name__ == "__main__":
    unittest.main()
