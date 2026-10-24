import re
import socket
import ssl
import threading
import time


EXPECTED = {
    40: (
        "SSLV3_ALERT_HANDSHAKE_FAILURE",
        "[SSL: SSLV3_ALERT_HANDSHAKE_FAILURE] ssl/tls alert handshake failure",
    ),
    42: (
        "SSLV3_ALERT_BAD_CERTIFICATE",
        "[SSL: SSLV3_ALERT_BAD_CERTIFICATE] ssl/tls alert bad certificate",
    ),
    49: (
        "TLSV1_ALERT_ACCESS_DENIED",
        "[SSL: TLSV1_ALERT_ACCESS_DENIED] tlsv1 alert access denied",
    ),
    80: (
        "TLSV1_ALERT_INTERNAL_ERROR",
        "[SSL: TLSV1_ALERT_INTERNAL_ERROR] tlsv1 alert internal error",
    ),
    116: (
        "TLSV13_ALERT_CERTIFICATE_REQUIRED",
        "[SSL: TLSV13_ALERT_CERTIFICATE_REQUIRED] tlsv13 alert certificate required",
    ),
    121: (None, "[SSL] unknown error (0xa000461)"),
}


def probe_alert(alert):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(2)
    address = listener.getsockname()

    def send_alert():
        try:
            peer, _ = listener.accept()
            with peer:
                peer.sendall(bytes((21, 3, 3, 0, 2, 2, alert)))
                time.sleep(0.05)
        finally:
            listener.close()

    worker = threading.Thread(target=send_alert, daemon=True)
    worker.start()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    raw = socket.create_connection(address, timeout=2)
    raw.settimeout(2)
    try:
        with context.wrap_socket(raw, server_hostname="example.test"):
            raise AssertionError(f"alert {alert} unexpectedly completed a handshake")
    except ssl.SSLError as error:
        reason, message = EXPECTED[alert]
        assert error.args[0] == 1, (alert, error.args)
        actual_message = re.sub(r" \(_ssl\.c:\d+\)$", "", error.args[1])
        assert actual_message == message, (alert, actual_message)
        assert error.library == "SSL", (alert, error.library)
        assert error.reason == reason, (alert, error.reason)
    finally:
        raw.close()
        worker.join(timeout=2)
        assert not worker.is_alive(), f"alert {alert} server thread did not stop"


for alert_code in EXPECTED:
    probe_alert(alert_code)

print(f"forced alert metadata: {len(EXPECTED)} passed")
