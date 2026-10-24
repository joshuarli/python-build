from __future__ import annotations

import ssl
import unittest

import sni_contract


class AlpnContract(unittest.TestCase):
    contexts = sni_contract.ServerNameContract.contexts
    handshake = sni_contract.ServerNameContract.handshake

    def test_server_preference_and_no_overlap(self):
        versions = (ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3)
        offers = ((["first", "second"], "second"), (["unknown"], None), ([], None))
        for version in versions:
            for switch_context in (False, True):
                for client_protocols, expected in offers:
                    with self.subTest(version=version, switch=switch_context, offers=client_protocols):
                        client, initial, selected = self.contexts()
                        for context in (client, initial, selected):
                            context.minimum_version = version
                            context.maximum_version = version
                        client.set_alpn_protocols(client_protocols)
                        initial.set_alpn_protocols(["first"] if switch_context else ["second", "first"])
                        selected.set_alpn_protocols(["second", "first"])
                        if switch_context:
                            initial.sni_callback = lambda connection, hostname, context: setattr(
                                connection, "context", selected
                            )
                        client_connection, server_connection = self.handshake(
                            client, initial, "example.test"
                        )
                        self.assertEqual(client_connection.selected_alpn_protocol(), expected)
                        self.assertEqual(server_connection.selected_alpn_protocol(), expected)
                        if client_protocols == ["unknown"]:
                            client.set_alpn_protocols(["first", "second"])
                            client_connection, server_connection = self.handshake(
                                client, initial, "example.test"
                            )
                            self.assertEqual(client_connection.selected_alpn_protocol(), "second")
                            self.assertEqual(server_connection.selected_alpn_protocol(), "second")


if __name__ == "__main__":
    unittest.main(verbosity=2)
