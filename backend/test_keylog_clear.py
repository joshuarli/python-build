from pathlib import Path
import socket
import tempfile
import unittest

from test.test_ssl import HOST, ThreadedEchoServer, testing_context


def handshake(client_context, server_context, server_hostname):
    server = ThreadedEchoServer(context=server_context, chatty=False)
    with server:
        with client_context.wrap_socket(
            socket.socket(), server_hostname=server_hostname
        ) as client:
            client.connect((HOST, server.port))


class KeyLogClearTests(unittest.TestCase):
    def test_clearing_stops_logging_for_new_handshakes(self):
        work_root = Path(__file__).resolve().parents[1] / ".work" / "tmp"
        work_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="rtls-keylog-", dir=work_root) as directory:
            path = Path(directory) / "secrets.log"
            client_context, server_context, hostname = testing_context()
            client_context.keylog_filename = path

            handshake(client_context, server_context, hostname)
            before_clear = path.read_bytes()
            self.assertIn(b"CLIENT_HANDSHAKE_TRAFFIC_SECRET", before_clear)

            client_context.keylog_filename = None
            self.assertIsNone(client_context.keylog_filename)
            handshake(client_context, server_context, hostname)

            self.assertEqual(path.read_bytes(), before_clear)


if __name__ == "__main__":
    unittest.main()
