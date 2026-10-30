import argparse
import errno
import json
import select
import socket
import ssl
import threading
import unittest
from pathlib import Path


class HandshakeErrorCleanupTests(unittest.TestCase):
    certificate_file: Path

    def test_empty_open_peer_does_not_block_cleanup(self):
        receiver, peer = socket.socketpair()
        receiver.settimeout(0.5)
        with receiver, peer:
            from rtls._socket import _discard_pending_handshake_data

            self.assertEqual(_discard_pending_handshake_data(receiver), 0)
            self.assertEqual(receiver.gettimeout(), 0.5)

    def test_global_default_timeout_does_not_change_socket_mode(self):
        receiver, peer = socket.socketpair()
        default_timeout = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(0.5)
            from rtls._socket import _discard_pending_handshake_data

            self.assertEqual(_discard_pending_handshake_data(receiver), 0)
            self.assertIsNone(receiver.gettimeout())
            self.assertTrue(receiver.getblocking())
        finally:
            socket.setdefaulttimeout(default_timeout)
            receiver.close()
            peer.close()

    def test_closed_socket_reports_bad_descriptor(self):
        receiver, peer = socket.socketpair()
        receiver.close()
        peer.close()

        from rtls._socket import _discard_pending_handshake_data

        with self.assertRaises(OSError) as caught:
            _discard_pending_handshake_data(receiver)
        self.assertEqual(caught.exception.errno, errno.EBADF)

    def test_unending_peer_cannot_block_or_exceed_one_socket_buffer(self):
        receiver, peer = socket.socketpair()
        peer.setblocking(False)
        stop = threading.Event()
        sent = threading.Event()

        def flood():
            payload = b"x" * 16384
            while not stop.is_set():
                try:
                    peer.send(payload)
                    sent.set()
                except BlockingIOError:
                    select.select([], [peer], [], 0.01)
                except OSError:
                    return

        writer = threading.Thread(target=flood)
        writer.start()
        try:
            from rtls._socket import _discard_pending_handshake_data

            self.assertTrue(sent.wait(1))
            received = _discard_pending_handshake_data(receiver)
            self.assertGreater(received, 0)
            self.assertLessEqual(received, 65536)
        finally:
            stop.set()
            writer.join(1)
            receiver.close()
            peer.close()
        self.assertFalse(writer.is_alive())

    def _assert_certificate_rejection_reaches_server_as_tls_alert(
        self, do_handshake_on_connect
    ):
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(self.certificate_file)
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(3)
        server_errors = []

        def serve():
            try:
                accepted, _ = listener.accept()
                accepted.settimeout(3)
                with server_context.wrap_socket(accepted, server_side=True):
                    pass
            except BaseException as error:  # noqa: BLE001
                server_errors.append(error)
            finally:
                listener.close()

        thread = threading.Thread(target=serve)
        thread.start()
        client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        client_context.check_hostname = False
        client = socket.create_connection(listener.getsockname(), timeout=3)
        client.settimeout(3)
        wrapped = None
        try:
            if do_handshake_on_connect:
                with self.assertRaises(ssl.SSLCertVerificationError):
                    wrapped = client_context.wrap_socket(
                        client, server_hostname="localhost"
                    )
            else:
                wrapped = client_context.wrap_socket(
                    client,
                    server_hostname="localhost",
                    do_handshake_on_connect=False,
                )
                with self.assertRaises(ssl.SSLCertVerificationError):
                    wrapped.do_handshake()
        finally:
            if wrapped is None:
                client.close()
            else:
                wrapped.close()
        thread.join(4)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(server_errors), 1)
        self.assertIsInstance(server_errors[0], ssl.SSLError)

    def test_automatic_handshake_rejection_reaches_server_as_tls_alert(self):
        self._assert_certificate_rejection_reaches_server_as_tls_alert(True)

    def test_manual_handshake_rejection_reaches_server_as_tls_alert(self):
        self._assert_certificate_rejection_reaches_server_as_tls_alert(False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--certdata", required=True, type=Path)
    args = parser.parse_args()
    HandshakeErrorCleanupTests.certificate_file = args.certdata / "keycert3.pem"
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(HandshakeErrorCleanupTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = result.wasSuccessful() and result.testsRun == 6 and not result.skipped
    print(json.dumps({"ok": passed, "tests_run": result.testsRun, "skipped": len(result.skipped)}))
    raise SystemExit(0 if passed else 1)
