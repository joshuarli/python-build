from __future__ import annotations

import socket
import threading
import unittest
from pathlib import Path
import sysconfig

import ssl


SERVER_CERT = Path(sysconfig.get_path("stdlib")) / "test" / "certdata" / "keycert3.pem"
EXPECTED_GROUP = "secp384r1"


def _contexts(
    version: ssl.TLSVersion,
    client_groups: str = EXPECTED_GROUP,
    server_groups: str = EXPECTED_GROUP,
):
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(SERVER_CERT)
    server.minimum_version = version
    server.maximum_version = version
    server.set_groups(server_groups)

    client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client.check_hostname = False
    client.verify_mode = ssl.CERT_NONE
    client.minimum_version = version
    client.maximum_version = version
    client.set_groups(client_groups)
    return client, server


def _memory_bio_groups(version: ssl.TLSVersion) -> tuple[str | None, str | None]:
    client_context, server_context = _contexts(version)
    return _memory_bio_groups_for_contexts(client_context, server_context)


def _memory_bio_groups_for_contexts(
    client_context: ssl.SSLContext,
    server_context: ssl.SSLContext,
) -> tuple[str | None, str | None]:
    client_incoming, client_outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
    server_incoming, server_outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
    client = client_context.wrap_bio(
        client_incoming, client_outgoing, server_hostname="localhost"
    )
    server = server_context.wrap_bio(
        server_incoming, server_outgoing, server_side=True
    )
    complete = {client: False, server: False}
    streams = (
        (client, client_outgoing, server_incoming),
        (server, server_outgoing, client_incoming),
    )
    for _ in range(128):
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
            return client.group(), server.group()
    raise AssertionError(f"MemoryBIO handshake did not finish for {version.name}")


def _socket_groups(version: ssl.TLSVersion) -> tuple[str | None, str | None]:
    client_context, server_context = _contexts(version)
    return _socket_groups_for_contexts(client_context, server_context)


def _socket_groups_for_contexts(
    client_context: ssl.SSLContext,
    server_context: ssl.SSLContext,
) -> tuple[str | None, str | None]:
    raw_client, raw_server = socket.socketpair()
    raw_client.settimeout(4)
    raw_server.settimeout(4)
    groups: dict[str, str | None] = {}
    server_errors: list[BaseException] = []
    server_socket: list[ssl.SSLSocket] = []
    server_done = threading.Event()

    def serve() -> None:
        try:
            wrapped = server_context.wrap_socket(
                raw_server, server_side=True, do_handshake_on_connect=False
            )
            server_socket.append(wrapped)
            with wrapped as server:
                server.do_handshake()
                groups["server"] = server.group()
                server_done.set()
        except BaseException as error:
            server_errors.append(error)

    thread = threading.Thread(target=serve)
    thread.start()
    client_error: BaseException | None = None
    client_group: str | None = None
    try:
        with client_context.wrap_socket(
            raw_client, server_hostname="localhost", do_handshake_on_connect=False
        ) as client:
            client.do_handshake()
            client_group = client.group()
            if not server_done.wait(4):
                raise TimeoutError("socketpair TLS server handshake did not finish")
    except BaseException as error:
        client_error = error
    finally:
        thread.join(6)
        cleanup_errors: list[BaseException] = []
        if thread.is_alive():
            if server_socket:
                try:
                    server_socket[0].close()
                except OSError as error:
                    cleanup_errors.append(error)
            thread.join(2)

    if thread.is_alive():
        raise RuntimeError("socketpair TLS server did not stop")
    if client_error is not None:
        for error in cleanup_errors:
            client_error.add_note(f"server socket cleanup failed: {error!r}")
        raise client_error
    if cleanup_errors:
        raise cleanup_errors[0]
    if server_errors:
        raise server_errors[0]
    return client_group, groups["server"]


class GroupContractTests(unittest.TestCase):
    def test_official_groups_and_aliases(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        groups = context.get_groups()
        groups_with_aliases = context.get_groups(include_aliases=True)
        self.assertIn("secp256r1", groups)
        self.assertNotIn("P-256", groups)
        self.assertIn("secp256r1", groups_with_aliases)
        self.assertIn("P-256", groups_with_aliases)

    def test_supported_signature_algorithms(self):
        self.assertIn("rsa_pss_rsae_sha256", ssl.get_sigalgs())

    def test_group_getters_before_handshake(self):
        client_context, _ = _contexts(ssl.TLSVersion.TLSv1_3)
        client = client_context.wrap_bio(
            ssl.MemoryBIO(), ssl.MemoryBIO(), server_hostname="localhost"
        )
        self.assertIsNone(client.group())

        raw_socket = socket.socket()
        raw_socket.settimeout(4)
        with client_context.wrap_socket(
            raw_socket,
            server_hostname="localhost",
            do_handshake_on_connect=False,
        ) as client_socket:
            self.assertIsNone(client_socket.group())

    def test_optional_unknown_groups_and_signature_algorithms(self):
        cases = (
            ("groups", "secp256r1:?future_group", "future_group"),
            (
                "client_sigalgs",
                "rsa_pss_rsae_sha256:?future_scheme",
                "future_scheme",
            ),
            (
                "server_sigalgs",
                "rsa_pss_rsae_sha256:?future_scheme",
                "future_scheme",
            ),
        )
        for setter, with_optional, only_unknown in cases:
            with self.subTest(setter=setter):
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                configure = getattr(context, f"set_{setter}")
                self.assertIsNone(configure(with_optional))

                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                configure = getattr(context, f"set_{setter}")
                with self.assertRaises(ssl.SSLError):
                    configure(only_unknown)
                if setter != "groups":
                    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                    configure = getattr(context, f"set_{setter}")
                    with self.assertRaises(ssl.SSLError):
                        configure("?future_scheme")

    def test_only_optional_unknown_group_leaves_no_negotiable_groups(self):
        with self.subTest(server_groups=EXPECTED_GROUP):
            client_context, server_context = _contexts(
                ssl.TLSVersion.TLSv1_3,
                client_groups=EXPECTED_GROUP,
                server_groups=EXPECTED_GROUP,
            )
            available_groups = client_context.get_groups()
            self.assertIsNone(client_context.set_groups("?future_group"))
            self.assertEqual(client_context.get_groups(), available_groups)
            with self.assertRaises(ssl.SSLError):
                _memory_bio_groups_for_contexts(client_context, server_context)

        with self.subTest(server_groups="x25519"):
            client_context, server_context = _contexts(
                ssl.TLSVersion.TLSv1_3,
                client_groups=EXPECTED_GROUP,
                server_groups="x25519",
            )
            available_groups = client_context.get_groups()
            self.assertIsNone(client_context.set_groups("?future_group"))
            self.assertEqual(client_context.get_groups(), available_groups)
            with self.assertRaises(ssl.SSLError):
                _memory_bio_groups_for_contexts(client_context, server_context)

    def test_negotiated_groups_on_memory_bio_and_socket(self):
        for version in (ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3):
            with self.subTest(version=version.name, carrier="MemoryBIO"):
                self.assertEqual(
                    _memory_bio_groups(version),
                    (EXPECTED_GROUP, EXPECTED_GROUP),
                )
            with self.subTest(version=version.name, carrier="SSLSocket"):
                self.assertEqual(
                    _socket_groups(version),
                    (EXPECTED_GROUP, EXPECTED_GROUP),
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
