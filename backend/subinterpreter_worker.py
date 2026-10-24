import gc
import ssl
from pathlib import Path


def run(certdata):
    root = Path(certdata)
    outputs = []
    for version in (ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3):
        for trusted in (True, False):
            client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            if trusted:
                client_context.load_verify_locations(root / "pycacert.pem")
            server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            server_context.load_cert_chain(str(root / "keycert3.pem"))
            for context in (client_context, server_context):
                context.minimum_version = version
                context.maximum_version = version
            client_in, client_out = ssl.MemoryBIO(), ssl.MemoryBIO()
            server_in, server_out = ssl.MemoryBIO(), ssl.MemoryBIO()
            client = client_context.wrap_bio(client_in, client_out, server_hostname="localhost")
            server = server_context.wrap_bio(server_in, server_out, server_side=True)
            finished = [False, False]
            rejected = False
            try:
                for _ in range(20):
                    for index, connection, outgoing, incoming in (
                        (0, client, client_out, server_in), (1, server, server_out, client_in)
                    ):
                        if not finished[index]:
                            try:
                                connection.do_handshake()
                            except ssl.SSLWantReadError:
                                pass
                            else:
                                finished[index] = True
                        data = outgoing.read()
                        if data:
                            incoming.write(data)
                    if all(finished):
                        break
            except ssl.SSLCertVerificationError:
                if trusted:
                    raise
                rejected = True
            if trusted:
                assert all(finished)
                assert client.version() == version.name.replace("_", ".")
                client.write(b"interpreter-owned payload")
                server_in.write(client_out.read())
                assert server.read(4096) == b"interpreter-owned payload"
                assert len(client.get_verified_chain()) == 2
                assert (("commonName", "localhost"),) in client.getpeercert()["subject"]
                payload = b"x" * 65553
                sent = 0
                received = bytearray()
                while sent < len(payload):
                    count = client.write(payload[sent:])
                    assert 0 < count <= len(payload) - sent
                    sent += count
                    server_in.write(client_out.read())
                    while len(received) < sent:
                        received.extend(server.read(sent - len(received)))
                assert bytes(received) == payload
                outputs.append(client.version())
            else:
                assert rejected
                outputs.append("rejected")
    del client, server, client_context, server_context
    gc.collect()
    return tuple(outputs)
