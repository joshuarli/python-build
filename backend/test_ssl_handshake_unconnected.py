import errno
import socket
import unittest

import ssl


class UnconnectedHandshakeTests(unittest.TestCase):
    def test_do_handshake_reports_not_connected(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        with context.wrap_socket(
            socket.socket(),
            do_handshake_on_connect=False,
        ) as sock:
            with self.assertRaises(OSError) as caught:
                sock.do_handshake()
            self.assertEqual(caught.exception.errno, errno.ENOTCONN)
            self.assertGreaterEqual(sock.fileno(), 0)


if __name__ == "__main__":
    unittest.main()
