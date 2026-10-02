"""Exercise capsule-backed context policy, TLS steps, and coded TLS errors."""
import _ssl_rs
import os
import ssl
import sys


def client_context():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def transfer(source, destination):
    data = source.read()
    if data:
        destination.write(data)


def check_round_trip():
    certificate = os.path.join(
        sys.prefix, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}",
        "test", "certdata", "keycert.pem")
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(certificate)
    client = client_context()
    client_in, client_out = ssl.MemoryBIO(), ssl.MemoryBIO()
    server_in, server_out = ssl.MemoryBIO(), ssl.MemoryBIO()
    peers = (
        client.wrap_bio(client_in, client_out, server_hostname="localhost"),
        server_context.wrap_bio(server_in, server_out, server_side=True),
    )
    completed = [False, False]
    for _ in range(100):
        for index, peer in enumerate(peers):
            if not completed[index]:
                try:
                    peer.do_handshake()
                except ssl.SSLWantReadError:
                    pass
                else:
                    completed[index] = True
        transfer(client_out, server_in)
        transfer(server_out, client_in)
        if all(completed):
            break
    assert all(completed), "in-memory TLS handshake did not complete"
    assert peers[0].version() == peers[1].version()

    for sender, output, receiver, incoming, payload in (
        (peers[0], client_out, peers[1], server_in, b"client to server"),
        (peers[1], server_out, peers[0], client_in, b"server to client"),
    ):
        assert sender.write(payload) == len(payload)
        transfer(output, incoming)
        assert receiver.read(len(payload)) == payload


def check_error_steps():
    context = client_context()
    incoming, outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
    connection = context.wrap_bio(incoming, outgoing, server_hostname="localhost")
    try:
        connection.do_handshake()
    except ssl.SSLWantReadError as error:
        assert error.errno == ssl.SSL_ERROR_WANT_READ
    else:
        raise AssertionError("empty input did not request a TLS read")

    errors = []
    for _ in range(2):
        incoming = ssl.MemoryBIO()
        connection = context.wrap_bio(incoming, ssl.MemoryBIO(),
                                      server_hostname="localhost")
        incoming.write(b"GET / HTTP/1.0\r\n\r\n")
        try:
            connection.do_handshake()
        except ssl.SSLError as error:
            errors.append(error)
        else:
            raise AssertionError("plaintext input did not raise a TLS error")
    first, second = errors
    assert first.errno == second.errno == ssl.SSL_ERROR_SSL
    assert first.library and first.reason
    assert first.library is second.library
    assert first.reason is second.reason


def main():
    capsule = _ssl_rs._C_API
    assert type(capsule).__name__ == "PyCapsule"
    assert repr(capsule).startswith('<capsule object "_ssl_rs._C_API" at ')
    check_round_trip()
    check_error_steps()
    assert _ssl_rs._C_API is capsule
    print("capsule-backed TLS context, round trips, and error steps: PASS")


if __name__ == "__main__":
    main()
