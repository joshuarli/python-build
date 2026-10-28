from __future__ import annotations

import socket
import ssl
import sysconfig
import threading
import unittest
from pathlib import Path

from rtls._ciphers import parse_cipher_string

TEST_CERT = Path(sysconfig.get_path("stdlib")) / "test" / "certdata" / "keycert3.pem"
TLS12_NAMES = {
    "ECDHE-ECDSA-AES128-GCM-SHA256": 0x0300C02B,
    "ECDHE-RSA-AES128-GCM-SHA256": 0x0300C02F,
    "ECDHE-ECDSA-AES256-GCM-SHA384": 0x0300C02C,
    "ECDHE-RSA-AES256-GCM-SHA384": 0x0300C030,
    "ECDHE-ECDSA-CHACHA20-POLY1305": 0x0300CCA9,
    "ECDHE-RSA-CHACHA20-POLY1305": 0x0300CCA8,
}
TLS13_NAMES = {
    "TLS_AES_128_GCM_SHA256": 0x03001301,
    "TLS_AES_256_GCM_SHA384": 0x03001302,
    "TLS_CHACHA20_POLY1305_SHA256": 0x03001303,
}


def _handshake(client_selector: str, server_selector: str):
    client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client_context.check_hostname = False
    client_context.verify_mode = ssl.CERT_NONE
    client_context.minimum_version = ssl.TLSVersion.TLSv1_2
    client_context.maximum_version = ssl.TLSVersion.TLSv1_2
    client_context.set_ciphers(client_selector)

    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.minimum_version = ssl.TLSVersion.TLSv1_2
    server_context.maximum_version = ssl.TLSVersion.TLSv1_2
    server_context.load_cert_chain(str(TEST_CERT))
    server_context.set_ciphers(server_selector)

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    server_result = []

    def serve() -> None:
        try:
            connection, _ = listener.accept()
            with server_context.wrap_socket(connection, server_side=True) as tls:
                server_result.append(("ok", tls.cipher()))
                server_result.append(tls.recv(1))
        except Exception as error:  # noqa: BLE001
            server_result.append(("error", type(error).__name__, str(error)))
        finally:
            listener.close()

    server = threading.Thread(target=serve, daemon=True)
    server.start()
    try:
        raw_socket = socket.create_connection(listener.getsockname(), timeout=5)
        with client_context.wrap_socket(raw_socket, server_hostname="localhost") as tls:
            result = ("ok", tls.cipher())
            tls.sendall(b"x")
    except Exception as error:  # noqa: BLE001
        result = ("error", type(error).__name__, str(error))
    server.join(5)
    if server.is_alive():
        raise RuntimeError("cipher negotiation thread did not finish")
    return result, server_result


class CipherControlRegressionTests(unittest.TestCase):
    def test_failed_selectors_leave_context_unchanged(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.set_ciphers("AES128")
        selected = context.get_ciphers()
        with self.assertRaises(ssl.SSLError):
            context.set_ciphers("")
        self.assertEqual(context.get_ciphers(), selected)
        with self.assertRaises(NotImplementedError):
            context.set_ciphers("DEFAULT:@SECLEVEL=5")
        self.assertEqual(context.get_ciphers(), selected)

    def test_reported_suites_have_actual_ids_and_selection(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        rows = context.get_ciphers()
        self.assertEqual(
            {row["name"]: row["id"] for row in rows},
            TLS12_NAMES | TLS13_NAMES,
        )
        for row in rows:
            expected_protocol = (
                "TLSv1.3" if row["name"].startswith("TLS_") else "TLSv1.2"
            )
            expected_bits = 128 if "128" in row["name"] else 256
            self.assertEqual(row["protocol"], expected_protocol)
            self.assertEqual(row["strength_bits"], expected_bits)
            self.assertEqual(row["alg_bits"], expected_bits)
        context.set_ciphers("AES128")
        rows = context.get_ciphers()
        self.assertEqual(
            {row["name"]: row["id"] for row in rows},
            {
                "ECDHE-ECDSA-AES128-GCM-SHA256": 0x0300C02B,
                "ECDHE-RSA-AES128-GCM-SHA256": 0x0300C02F,
                **TLS13_NAMES,
            },
        )
        rsa = next(row for row in rows if row["name"] == "ECDHE-RSA-AES128-GCM-SHA256")
        expected_description = (
            "ECDHE-RSA-AES128-GCM-SHA256    TLSv1.2 Kx=ECDH     Au=RSA   "
            "Enc=AESGCM(128)            Mac=AEAD"
        )
        self.assertEqual(
            rsa["description"],
            expected_description,
        )

    def test_selector_order_and_exclusion_semantics(self):
        expected = [
            "TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384",
            "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384",
            "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256",
            "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256",
        ]
        self.assertEqual(parse_cipher_string("ECDHE+AESGCM"), expected)
        cipher = "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256"
        self.assertEqual(
            parse_cipher_string(
                "AESGCM:-ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256"
            )[-1],
            cipher,
        )
        self.assertNotIn(
            cipher,
            parse_cipher_string(
                "AESGCM:!ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256"
            ),
        )
        self.assertEqual(
            parse_cipher_string("AESGCM:+ECDHE-RSA-AES128-GCM-SHA256")[-1],
            cipher,
        )
        self.assertEqual(
            parse_cipher_string("ALL:@STRENGTH")[0],
            "TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384",
        )

    def test_selected_suites_control_real_negotiation(self):
        name = "ECDHE-RSA-AES128-GCM-SHA256"
        client, server = _handshake(name, name)
        self.assertEqual(client[0], "ok")
        self.assertEqual(server[0][0], "ok")
        self.assertEqual(client[1][0], name)
        self.assertEqual(server[0][1][0], name)
        self.assertEqual(server[1], b"x")

        client, server = _handshake("AES128", "AES256")
        self.assertEqual(client[0], "error")
        self.assertEqual(server[0][0], "error")


if __name__ == "__main__":
    unittest.main(verbosity=2)
