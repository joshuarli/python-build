import socket
import ssl
import struct
import unittest


class PreHandshakeDataTests(unittest.TestCase):
    def connected_pair(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        client = socket.socket()
        client.connect(listener.getsockname())
        server, _ = listener.accept()
        listener.close()
        return client, server

    def reset_with_data(self, sock):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        sock.sendall(b"DELETE /data HTTP/1.0\r\n\r\n")
        sock.close()

    def assert_rejected(self, context, sock, **kwargs):
        with self.assertRaises(ssl.SSLError) as raised:
            context.wrap_socket(sock, **kwargs)
        error = raised.exception
        self.assertNotEqual(0, error.args[0])
        self.assertIn("before TLS handshake with data", error.args[1])
        self.assertIn("before TLS handshake with data", error.reason)
        self.assertIsNone(error.library)
        self.assertEqual(-1, sock.fileno())

    def test_client_rejects_reset_peer_data_before_tls(self):
        client, peer = self.connected_pair()
        self.reset_with_data(peer)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.assert_rejected(context, client, server_hostname="localhost")

    def test_server_rejects_reset_peer_data_before_tls(self):
        peer, server = self.connected_pair()
        self.reset_with_data(peer)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.assert_rejected(context, server, server_side=True)


if __name__ == "__main__":
    unittest.main()
