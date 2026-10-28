from __future__ import annotations

import ssl
import sys
import unittest
from pathlib import Path

CERTDATA = Path(sys.argv.pop(1))
FIXTURES = Path(__file__).with_name("fixtures")


class ServerNameContract(unittest.TestCase):
    def contexts(self):
        client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        client.check_hostname = False
        client.load_verify_locations(CERTDATA / "pycacert.pem")
        server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server.load_cert_chain(str(CERTDATA / "keycert3.pem"))
        other = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        other.load_cert_chain(str(CERTDATA / "keycert4.pem"))
        return client, server, other

    def handshake(self, client_context, server_context, hostname):
        incoming = [ssl.MemoryBIO(), ssl.MemoryBIO()]
        outgoing = [ssl.MemoryBIO(), ssl.MemoryBIO()]
        client = client_context.wrap_bio(incoming[0], outgoing[0], server_hostname=hostname)
        server = server_context.wrap_bio(incoming[1], outgoing[1], server_side=True)
        completed = [False, False]
        for _ in range(20):
            for index, connection in enumerate((client, server)):
                if not completed[index]:
                    try:
                        connection.do_handshake()
                    except ssl.SSLWantReadError:
                        pass
                    else:
                        completed[index] = True
                data = outgoing[index].read()
                if data:
                    incoming[1 - index].write(data)
            if all(completed):
                return client, server
        self.fail("TLS handshake did not complete")

    def test_callback_waits_for_complete_client_hello(self):
        client_context, server_context, _ = self.contexts()
        calls = []
        server_context.sni_callback = lambda connection, hostname, context: calls.append(hostname)
        client_in, client_out = ssl.MemoryBIO(), ssl.MemoryBIO()
        server_in, server_out = ssl.MemoryBIO(), ssl.MemoryBIO()
        client = client_context.wrap_bio(client_in, client_out, server_hostname="example.test")
        server = server_context.wrap_bio(server_in, server_out, server_side=True)
        with self.assertRaises(ssl.SSLWantReadError):
            server.do_handshake()
        self.assertEqual(calls, [])
        with self.assertRaises(ssl.SSLWantReadError):
            client.do_handshake()
        hello = client_out.read()
        for byte in hello[:-1]:
            server_in.write(bytes([byte]))
            with self.assertRaises(ssl.SSLWantReadError):
                server.do_handshake()
            self.assertEqual(calls, [])
        server_in.write(hello[-1:])
        with self.assertRaises(ssl.SSLWantReadError):
            server.do_handshake()
        self.assertEqual(calls, ["example.test"])
        with self.assertRaises(ssl.SSLWantReadError):
            server.do_handshake()
        self.assertEqual(calls, ["example.test"])

    def test_callback_selects_certificate_and_receives_original_context(self):
        client, server, other = self.contexts()
        calls = []

        def callback(connection, hostname, context):
            calls.append((connection, hostname, context))
            connection.context = other

        server.sni_callback = callback
        client_connection, server_connection = self.handshake(client, server, "example.test")
        self.assertEqual(calls, [(server_connection, "example.test", server)])
        self.assertIs(server_connection.context, other)
        self.assertIn((("commonName", "fakehostname"),), client_connection.getpeercert()["subject"])

    def test_absent_sni_and_disabled_callback(self):
        client, server, _ = self.contexts()
        calls = []
        server.sni_callback = lambda connection, hostname, context: calls.append(hostname)
        self.handshake(client, server, None)
        self.assertEqual(calls, [None])
        server.sni_callback = None
        self.handshake(client, server, "example.test")
        self.assertEqual(calls, [None])

    def test_legacy_callback_receives_ascii_idna(self):
        client, server, _ = self.contexts()
        calls = []
        server.set_servername_callback(lambda connection, hostname, context: calls.append(hostname))
        self.handshake(client, server, "xn--pythn-mua.test")
        self.assertEqual(calls, ["xn--pythn-mua.test"])

    def test_context_switch_preserves_initial_client_authentication(self):
        modes = (ssl.CERT_NONE, ssl.CERT_OPTIONAL, ssl.CERT_REQUIRED)
        identities = (None, "keycert3.pem", "keycert.pem")
        for initial_mode in modes:
            for selected_mode in modes:
                for identity in identities:
                    with self.subTest(initial=initial_mode, selected=selected_mode, identity=identity):
                        client, initial, selected = self.contexts()
                        initial.verify_mode = initial_mode
                        selected.verify_mode = selected_mode
                        initial.load_verify_locations(CERTDATA / "pycacert.pem")
                        selected.load_verify_locations(CERTDATA / "pycacert.pem")
                        if identity is not None:
                            client.load_cert_chain(str(CERTDATA / identity))
                        initial.sni_callback = lambda connection, hostname, context, selected=selected: setattr(
                            connection, "context", selected
                        )
                        rejected = (
                            initial_mode == ssl.CERT_REQUIRED and identity is None
                        ) or (
                            initial_mode != ssl.CERT_NONE and identity == "keycert.pem"
                        )
                        if rejected:
                            with self.assertRaises(ssl.SSLError):
                                self.handshake(client, initial, "example.test")
                        else:
                            self.handshake(client, initial, "example.test")

    def test_context_switch_uses_selected_trust_roots(self):
        for initial_trust, selected_trust in ((True, False), (False, True)):
            with self.subTest(initial=initial_trust, selected=selected_trust):
                client, initial, selected = self.contexts()
                client.load_cert_chain(str(CERTDATA / "keycert3.pem"))
                for context, trusted in ((initial, initial_trust), (selected, selected_trust)):
                    context.verify_mode = ssl.CERT_REQUIRED
                    context.load_verify_locations(
                        CERTDATA / "pycacert.pem" if trusted else FIXTURES / "unrelated-root.pem"
                    )
                initial.sni_callback = lambda connection, hostname, context, selected=selected: setattr(
                    connection, "context", selected
                )
                if selected_trust:
                    self.handshake(client, initial, "example.test")
                else:
                    with self.assertRaises(ssl.SSLError):
                        self.handshake(client, initial, "example.test")

    def test_context_switch_uses_selected_client_signature_schemes(self):
        schemes = ("rsa_pss_rsae_sha256", "ecdsa_secp256r1_sha256")
        for version in (ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3):
            for initial_scheme in schemes:
                for selected_scheme in schemes:
                    with self.subTest(version=version, initial=initial_scheme, selected=selected_scheme):
                        client, initial, selected = self.contexts()
                        client.load_cert_chain(str(CERTDATA / "keycert3.pem"))
                        client.set_client_sigalgs(schemes[0])
                        for context in (client, initial, selected):
                            context.minimum_version = version
                            context.maximum_version = version
                        for context, scheme in ((initial, initial_scheme), (selected, selected_scheme)):
                            context.verify_mode = ssl.CERT_REQUIRED
                            context.load_verify_locations(CERTDATA / "pycacert.pem")
                            context.set_client_sigalgs(scheme)
                        initial.sni_callback = lambda connection, hostname, context, selected=selected: setattr(
                            connection, "context", selected
                        )
                        if selected_scheme == schemes[0]:
                            self.handshake(client, initial, "example.test")
                        else:
                            with self.assertRaises(ssl.SSLError):
                                self.handshake(client, initial, "example.test")

    def test_context_switch_uses_selected_capath(self):
        for selected_capath in (False, True):
            with self.subTest(selected_capath=selected_capath):
                client, initial, selected = self.contexts()
                client.load_cert_chain(str(CERTDATA / "keycert3.pem"))
                for context in (initial, selected):
                    context.verify_mode = ssl.CERT_REQUIRED
                trusted = selected if selected_capath else initial
                untrusted = initial if selected_capath else selected
                trusted.load_verify_locations(capath=str(CERTDATA / "capath"))
                untrusted.load_verify_locations(FIXTURES / "unrelated-root.pem")
                initial.sni_callback = lambda connection, hostname, context, selected=selected: setattr(
                    connection, "context", selected
                )
                if selected_capath:
                    self.handshake(client, initial, "example.test")
                else:
                    with self.assertRaises(ssl.SSLError):
                        self.handshake(client, initial, "example.test")

    def test_context_switch_preserves_initial_verify_flags(self):
        for initial_strict, selected_strict in ((True, False), (False, True), (False, False)):
            with self.subTest(initial=initial_strict, selected=selected_strict):
                client, initial, selected = self.contexts()
                client.load_cert_chain(str(FIXTURES / "client-no-aki.pem"))
                for context, strict in ((initial, initial_strict), (selected, selected_strict)):
                    context.verify_mode = ssl.CERT_REQUIRED
                    context.load_verify_locations(CERTDATA / "pycacert.pem")
                    context.verify_flags = ssl.VERIFY_X509_TRUSTED_FIRST
                    if strict:
                        context.verify_flags |= ssl.VERIFY_X509_STRICT
                initial.sni_callback = lambda connection, hostname, context, selected=selected: setattr(
                    connection, "context", selected
                )
                if initial_strict:
                    with self.assertRaises(ssl.SSLError):
                        self.handshake(client, initial, "example.test")
                else:
                    self.handshake(client, initial, "example.test")

    def test_context_switch_preserves_initial_protocol_bounds(self):
        versions = (ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3)
        for initial_version in versions:
            for client_version in versions:
                with self.subTest(initial=initial_version, client=client_version):
                    client, initial, selected = self.contexts()
                    selected_version = (
                        ssl.TLSVersion.TLSv1_3
                        if initial_version == ssl.TLSVersion.TLSv1_2
                        else ssl.TLSVersion.TLSv1_2
                    )
                    for context, version in (
                        (client, client_version), (initial, initial_version), (selected, selected_version)
                    ):
                        context.minimum_version = version
                        context.maximum_version = version
                    calls = []

                    def callback(connection, hostname, context, calls=calls, selected=selected):
                        calls.append(hostname)
                        connection.context = selected

                    initial.sni_callback = callback
                    if initial_version != client_version:
                        with self.assertRaises(ssl.SSLError):
                            self.handshake(client, initial, "example.test")
                        self.assertEqual(calls, [])
                    else:
                        connection, _ = self.handshake(client, initial, "example.test")
                        self.assertEqual(connection.version(), initial_version.name.replace("_", "."))
                        self.assertEqual(calls, ["example.test"])

    def test_context_switch_uses_selected_cipher_and_alpn(self):
        client, initial, selected = self.contexts()
        for context in (client, initial, selected):
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.maximum_version = ssl.TLSVersion.TLSv1_2
        client.set_ciphers("ECDHE-RSA-AES128-GCM-SHA256")
        initial.set_ciphers("ECDHE-RSA-AES256-GCM-SHA384")
        selected.set_ciphers("ECDHE-RSA-AES128-GCM-SHA256")
        client.set_alpn_protocols(["initial", "selected"])
        initial.set_alpn_protocols(["initial"])
        selected.set_alpn_protocols(["selected"])
        initial.sni_callback = lambda connection, hostname, context: setattr(
            connection, "context", selected
        )
        connection, _ = self.handshake(client, initial, "example.test")
        self.assertEqual(connection.cipher()[0], "ECDHE-RSA-AES128-GCM-SHA256")
        self.assertEqual(connection.selected_alpn_protocol(), "selected")

    def test_context_switch_preserves_client_trust(self):
        client, server, other = self.contexts()
        client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        client.check_hostname = False
        server.sni_callback = lambda connection, hostname, context: setattr(connection, "context", other)
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.handshake(client, server, "example.test")


if __name__ == "__main__":
    unittest.main(verbosity=2)
