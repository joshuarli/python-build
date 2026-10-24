from __future__ import annotations

import socket
import threading
import unittest
from pathlib import Path
import sysconfig

import ssl


CERTDATA = Path(sysconfig.get_path("stdlib")) / "test" / "certdata"
SERVER_CA = CERTDATA / "pycacert.pem"
RSA_CERT = CERTDATA / "keycert3.pem"
ECDSA_CERT = CERTDATA / "keycertecc.pem"


def _contexts(version: ssl.TLSVersion, server_cert: Path = RSA_CERT, client_cert: Path | None = None, client_auth: bool = False):
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(server_cert)
    server_context.minimum_version = version
    server_context.maximum_version = version
    if client_auth:
        server_context.load_verify_locations(cafile=SERVER_CA)
        server_context.verify_mode = ssl.CERT_REQUIRED

    client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client_context.check_hostname = False
    client_context.verify_mode = ssl.CERT_NONE
    client_context.minimum_version = version
    client_context.maximum_version = version
    if client_cert is not None:
        client_context.load_cert_chain(client_cert)
    return client_context, server_context


def _signature_values(connection):
    return connection.client_sigalg(), connection.server_sigalg()


def _run_sockets(client_context, server_context, server_hostname="localhost", session=None, install_sni=False):
    if install_sni:
        selected_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        selected_context.load_cert_chain(ECDSA_CERT)
        selected_context.minimum_version = server_context.minimum_version
        selected_context.maximum_version = server_context.maximum_version

        def select_context(connection, name, initial_context):
            if name == "localhost-ecc":
                connection.context = selected_context

        server_context.sni_callback = select_context

    raw_client, raw_server = socket.socketpair()
    result = {}
    server_errors = []

    def serve():
        try:
            with server_context.wrap_socket(
                raw_server, server_side=True, do_handshake_on_connect=False
            ) as server:
                result["server_pre"] = _signature_values(server)
                server.do_handshake()
                result["server"] = (
                    server.client_sigalg(),
                    server.server_sigalg(),
                    server.session_reused,
                )
                server.sendall(b"x")
        except BaseException as error:
            server_errors.append(error)

    thread = threading.Thread(target=serve)
    thread.start()
    try:
        with client_context.wrap_socket(
            raw_client,
            server_hostname=server_hostname,
            do_handshake_on_connect=False,
            session=session,
        ) as client:
            result["client_pre"] = _signature_values(client)
            client.do_handshake()
            result["client"] = (
                client.client_sigalg(),
                client.server_sigalg(),
                client.session_reused,
            )
            client.recv(1)
            result["session"] = client.session
    finally:
        thread.join(5)
    if thread.is_alive():
        raise RuntimeError("signature metadata handshake did not finish")
    if server_errors:
        raise server_errors[0]
    return result


def _run_sslobject(version: ssl.TLSVersion):
    client_context, server_context = _contexts(version)
    client_incoming, client_outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
    server_incoming, server_outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
    client = client_context.wrap_bio(
        client_incoming, client_outgoing, server_hostname="localhost"
    )
    server = server_context.wrap_bio(
        server_incoming, server_outgoing, server_side=True
    )
    before = (_signature_values(client), _signature_values(server))
    complete = {client: False, server: False}
    streams = (
        (client, client_outgoing, server_incoming),
        (server, server_outgoing, client_incoming),
    )
    for _ in range(64):
        for connection, outgoing, peer_incoming in streams:
            if not complete[connection]:
                try:
                    connection.do_handshake()
                    complete[connection] = True
                except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                    pass
            data = outgoing.read()
            if data:
                peer_incoming.write(data)
        if all(complete.values()):
            break
    if not all(complete.values()):
        raise RuntimeError("SSLObject handshake did not finish")
    after = (_signature_values(client), _signature_values(server))
    return before, after


class SignatureMetadataTests(unittest.TestCase):
    def test_sslobject_signature_getters(self):
        before, after = _run_sslobject(ssl.TLSVersion.TLSv1_3)
        self.assertEqual(before, ((None, None), (None, None)))
        client, server = after
        self.assertIsNone(client[0])
        self.assertTrue(client[1].startswith("rsa_"))
        self.assertIsNone(server[0])
        self.assertEqual(server[1], client[1])

    def test_sslsocket_signature_getters_before_handshake(self):
        client_context, server_context = _contexts(ssl.TLSVersion.TLSv1_3)
        raw_client, raw_server = socket.socketpair()
        client = client_context.wrap_socket(
            raw_client, server_hostname="localhost", do_handshake_on_connect=False
        )
        server = server_context.wrap_socket(
            raw_server, server_side=True, do_handshake_on_connect=False
        )
        try:
            self.assertEqual(_signature_values(client), (None, None))
            self.assertEqual(_signature_values(server), (None, None))
        finally:
            client.close()
            server.close()

    def test_server_auth_signature_tracks_rsa_and_ecdsa(self):
        for version in (ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3):
            for server_cert, prefix in ((RSA_CERT, "rsa_"), (ECDSA_CERT, "ecdsa_")):
                with self.subTest(version=version.name, server_cert=server_cert.name):
                    client_context, server_context = _contexts(version, server_cert)
                    result = _run_sockets(client_context, server_context)
                    client = result["client"]
                    server = result["server"]
                    self.assertEqual(result["client_pre"], (None, None))
                    self.assertEqual(result["server_pre"], (None, None))
                    self.assertIsNone(client[0])
                    self.assertTrue(client[1].startswith(prefix))
                    self.assertIsNone(server[0])
                    self.assertEqual(server[1], client[1])
                    self.assertFalse(client[2])
                    self.assertFalse(server[2])

    def test_mutual_authentication_signature_tracks_rsa_and_ecdsa(self):
        for version in (ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3):
            for client_cert, prefix in ((RSA_CERT, "rsa_"), (ECDSA_CERT, "ecdsa_")):
                with self.subTest(version=version.name, client_cert=client_cert.name):
                    client_context, server_context = _contexts(
                        version, RSA_CERT, client_cert, client_auth=True
                    )
                    result = _run_sockets(client_context, server_context)
                    client = result["client"]
                    server = result["server"]
                    self.assertTrue(client[0].startswith(prefix))
                    self.assertTrue(client[1].startswith("rsa_"))
                    self.assertEqual(server[:2], client[:2])
                    self.assertFalse(client[2])
                    self.assertFalse(server[2])

    def test_sni_selects_the_signature_from_the_selected_context(self):
        client_context, server_context = _contexts(ssl.TLSVersion.TLSv1_3)
        result = _run_sockets(
            client_context,
            server_context,
            server_hostname="localhost-ecc",
            install_sni=True,
        )
        self.assertTrue(result["client"][1].startswith("ecdsa_"))
        self.assertEqual(result["server"][1], result["client"][1])

    def test_resumed_handshakes_have_no_signature_metadata(self):
        for version in (ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3):
            with self.subTest(version=version.name):
                client_context, server_context = _contexts(version)
                first = _run_sockets(client_context, server_context)
                self.assertFalse(first["client"][2])
                resumed = _run_sockets(
                    client_context,
                    server_context,
                    session=first["session"],
                )
                self.assertTrue(resumed["client"][2])
                self.assertTrue(resumed["server"][2])
                self.assertEqual(resumed["client"][:2], (None, None))
                self.assertEqual(resumed["server"][:2], (None, None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
