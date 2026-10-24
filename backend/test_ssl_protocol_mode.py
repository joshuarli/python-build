import os
import socket
import unittest

import ssl


class TLSProtocolModeTests(unittest.TestCase):
    def make_context(self, protocol):
        context = ssl.SSLContext(protocol)
        if protocol == ssl.PROTOCOL_TLS_CLIENT:
            context.check_hostname = False
        return context

    def assert_mode_error(self, error, message):
        self.assertIsInstance(error, ssl.SSLError)
        self.assertEqual(error.args[0], 0)
        self.assertEqual(error.args[1].split(" (_ssl.c:", 1)[0], message)
        self.assertIsNone(error.reason)
        self.assertIsNone(error.library)

    def test_wrap_bio_rejects_server_role_with_client_context(self):
        context = self.make_context(ssl.PROTOCOL_TLS_CLIENT)
        with self.assertRaises(ssl.SSLError) as caught:
            context.wrap_bio(
                ssl.MemoryBIO(), ssl.MemoryBIO(), server_side=True
            )
        self.assert_mode_error(
            caught.exception,
            "Cannot create a server socket with a PROTOCOL_TLS_CLIENT context",
        )

    def test_wrap_bio_rejects_client_role_with_server_context(self):
        context = self.make_context(ssl.PROTOCOL_TLS_SERVER)
        with self.assertRaises(ssl.SSLError) as caught:
            context.wrap_bio(
                ssl.MemoryBIO(), ssl.MemoryBIO(), server_side=False
            )
        self.assert_mode_error(
            caught.exception,
            "Cannot create a client socket with a PROTOCOL_TLS_SERVER context",
        )

    def assert_connected_socket_mode_error(
        self, context, server_side, message, socket_class=None
    ):
        if socket_class is not None:
            context.sslsocket_class = socket_class
        sock, peer = socket.socketpair()
        self.addCleanup(sock.close)
        self.addCleanup(peer.close)
        descriptor = sock.fileno()
        peer.settimeout(1)
        with self.assertRaises(ssl.SSLError) as caught:
            context.wrap_socket(
                sock,
                server_side=server_side,
                do_handshake_on_connect=False,
            )
        self.assert_mode_error(caught.exception, message)
        self.assertEqual(sock.fileno(), -1)
        with self.assertRaises(OSError):
            os.fstat(descriptor)
        self.assertEqual(peer.recv(1), b"")
        peer.close()

    def test_wrap_socket_rejects_server_role_with_client_context(self):
        self.assert_connected_socket_mode_error(
            self.make_context(ssl.PROTOCOL_TLS_CLIENT),
            True,
            "Cannot create a server socket with a PROTOCOL_TLS_CLIENT context",
        )

    def test_wrap_socket_rejects_client_role_with_server_context(self):
        self.assert_connected_socket_mode_error(
            self.make_context(ssl.PROTOCOL_TLS_SERVER),
            False,
            "Cannot create a client socket with a PROTOCOL_TLS_SERVER context",
        )

    def test_custom_socket_class_uses_context_role_guard(self):
        class CustomSSLSocket(ssl.SSLSocket):
            pass

        self.assert_connected_socket_mode_error(
            self.make_context(ssl.PROTOCOL_TLS_SERVER),
            False,
            "Cannot create a client socket with a PROTOCOL_TLS_SERVER context",
            socket_class=CustomSSLSocket,
        )

    def test_unconnected_wrap_defers_role_error_until_connect(self):
        context = self.make_context(ssl.PROTOCOL_TLS_SERVER)
        sock = socket.socket()
        original_descriptor = sock.fileno()
        wrapped = context.wrap_socket(
            sock,
            server_side=False,
            do_handshake_on_connect=False,
        )
        self.addCleanup(wrapped.close)
        self.assertEqual(sock.fileno(), -1)
        self.assertGreaterEqual(wrapped.fileno(), 0)
        with self.assertRaises(ssl.SSLError) as caught:
            wrapped.connect(("127.0.0.1", 1))
        self.assert_mode_error(
            caught.exception,
            "Cannot create a client socket with a PROTOCOL_TLS_SERVER context",
        )
        self.assertGreaterEqual(wrapped.fileno(), 0)
        wrapped.close()
        with self.assertRaises(OSError):
            os.fstat(original_descriptor)


if __name__ == "__main__":
    unittest.main()
