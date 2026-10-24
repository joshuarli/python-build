import argparse
import json
import ssl
from pathlib import Path


CONTENT_HANDSHAKE = 22
CONTENT_CHANGE_CIPHER_SPEC = 20
CONTENT_HEADER = 0x100
CONTENT_INNER = 0x101
MESSAGE_CLIENT_HELLO = 1
MESSAGE_SERVER_HELLO = 2
MESSAGE_NEW_SESSION_TICKET = 4
MESSAGE_ENCRYPTED_EXTENSIONS = 8
MESSAGE_CERTIFICATE = 11
MESSAGE_SERVER_KEY_EXCHANGE = 12
MESSAGE_SERVER_HELLO_DONE = 14
MESSAGE_CERTIFICATE_VERIFY = 15
MESSAGE_CLIENT_KEY_EXCHANGE = 16
MESSAGE_FINISHED = 20
MESSAGE_CHANGE_CIPHER_SPEC = 0x101


def collect_handshake(certdata: Path, version: ssl.TLSVersion) -> dict:
    events = {"client": [], "server": []}
    client_context = ssl.create_default_context(cafile=str(certdata / "pycacert.pem"))
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(str(certdata / "allsans.pem"))
    for context in (client_context, server_context):
        context.minimum_version = version
        context.maximum_version = version

    def callback(side):
        def record(connection, direction, protocol_version, content_type, message_type, data):
            if not isinstance(connection, ssl.SSLObject):
                raise AssertionError(type(connection))
            if direction not in {"read", "write"}:
                raise AssertionError(direction)
            if type(data) is not bytes:
                raise AssertionError(type(data))
            events[side].append(
                (
                    direction,
                    int(protocol_version),
                    int(content_type),
                    int(message_type),
                    data,
                )
            )

        return record

    client_context._msg_callback = callback("client")
    server_context._msg_callback = callback("server")
    client_in, client_out = ssl.MemoryBIO(), ssl.MemoryBIO()
    server_in, server_out = ssl.MemoryBIO(), ssl.MemoryBIO()
    client = client_context.wrap_bio(
        client_in,
        client_out,
        server_hostname="www.example.org",
    )
    server = server_context.wrap_bio(server_in, server_out, server_side=True)
    complete = {"client": False, "server": False}
    endpoints = (
        ("client", client, client_out, server_in),
        ("server", server, server_out, client_in),
    )
    for _ in range(16):
        for side, endpoint, outgoing, incoming in endpoints:
            if not complete[side]:
                try:
                    endpoint.do_handshake()
                    complete[side] = True
                except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                    pass
            if outgoing.pending:
                incoming.write(outgoing.read())
        if all(complete.values()):
            break
    else:
        raise AssertionError("TLS handshake did not finish")
    verify_events(events)
    return events


def verify_events(events: dict[str, list[tuple]]) -> None:
    for records in events.values():
        for _, version, content_type, message_type, data in records:
            if content_type == CONTENT_HEADER:
                if len(data) != 5 or version != int.from_bytes(data[1:3], "big"):
                    raise AssertionError((version, message_type, data))
                if message_type != data[0]:
                    raise AssertionError((message_type, data))
            elif content_type == CONTENT_INNER:
                if len(data) != 1 or message_type != data[0]:
                    raise AssertionError((message_type, data))
            elif content_type == CONTENT_HANDSHAKE:
                if len(data) < 4 or message_type != data[0]:
                    raise AssertionError((message_type, data))
                if int.from_bytes(data[1:4], "big") + 4 != len(data):
                    raise AssertionError(data)
            elif content_type == CONTENT_CHANGE_CIPHER_SPEC:
                if data != b"\x01" or message_type != MESSAGE_CHANGE_CIPHER_SPEC:
                    raise AssertionError((message_type, data))
            elif content_type == 21:
                if len(data) < 2 or message_type != data[1]:
                    raise AssertionError((message_type, data))
            else:
                raise AssertionError((content_type, message_type, data))


def message_types(events: list[tuple], side: str, direction: str) -> list[int]:
    return [
        message_type
        for event_direction, _, content_type, message_type, _ in events[side]
        if event_direction == direction and content_type == CONTENT_HANDSHAKE
    ]


def require_messages(events: dict[str, list[tuple]], requirements: dict) -> None:
    for (side, direction), required in requirements.items():
        observed = message_types(events, side, direction)
        if observed != required:
            raise AssertionError((side, direction, required, observed))


def run_version(certdata: Path, version: ssl.TLSVersion) -> dict:
    events = collect_handshake(certdata, version)
    client_hello_versions = {
        (side, direction): {
            protocol_version
            for event_direction, protocol_version, content_type, message_type, _ in events[side]
            if event_direction == direction
            and content_type == CONTENT_HANDSHAKE
            and message_type == MESSAGE_CLIENT_HELLO
        }
        for side, direction in (("client", "write"), ("server", "read"))
    }
    if client_hello_versions[("client", "write")] != {int(version)}:
        raise AssertionError(client_hello_versions)
    if client_hello_versions[("server", "read")] != {0x0304}:
        raise AssertionError(client_hello_versions)
    if version == ssl.TLSVersion.TLSv1_2:
        require_messages(
            events,
            {
                ("client", "write"): [
                    MESSAGE_CLIENT_HELLO,
                    MESSAGE_CLIENT_KEY_EXCHANGE,
                    MESSAGE_FINISHED,
                ],
                ("client", "read"): [
                    MESSAGE_SERVER_HELLO,
                    MESSAGE_CERTIFICATE,
                    MESSAGE_SERVER_KEY_EXCHANGE,
                    MESSAGE_SERVER_HELLO_DONE,
                    MESSAGE_NEW_SESSION_TICKET,
                    MESSAGE_FINISHED,
                ],
                ("server", "read"): [
                    MESSAGE_CLIENT_HELLO,
                    MESSAGE_CLIENT_KEY_EXCHANGE,
                    MESSAGE_FINISHED,
                ],
                ("server", "write"): [
                    MESSAGE_SERVER_HELLO,
                    MESSAGE_CERTIFICATE,
                    MESSAGE_SERVER_KEY_EXCHANGE,
                    MESSAGE_SERVER_HELLO_DONE,
                    MESSAGE_NEW_SESSION_TICKET,
                    MESSAGE_FINISHED,
                ],
            },
        )
    else:
        require_messages(
            events,
            {
                ("client", "write"): [MESSAGE_CLIENT_HELLO, MESSAGE_FINISHED],
                ("client", "read"): [
                    MESSAGE_SERVER_HELLO,
                    MESSAGE_ENCRYPTED_EXTENSIONS,
                    MESSAGE_CERTIFICATE,
                    MESSAGE_CERTIFICATE_VERIFY,
                    MESSAGE_FINISHED,
                ],
                ("server", "read"): [MESSAGE_CLIENT_HELLO, MESSAGE_FINISHED],
                ("server", "write"): [
                    MESSAGE_SERVER_HELLO,
                    MESSAGE_ENCRYPTED_EXTENSIONS,
                    MESSAGE_CERTIFICATE,
                    MESSAGE_CERTIFICATE_VERIFY,
                    MESSAGE_FINISHED,
                    MESSAGE_NEW_SESSION_TICKET,
                    MESSAGE_NEW_SESSION_TICKET,
                ],
            },
        )
    if not any(event[2] == CONTENT_HEADER for records in events.values() for event in records):
        raise AssertionError("record headers were not captured")
    if not all(
        any(event[2] == CONTENT_CHANGE_CIPHER_SPEC for event in events[side])
        for side in ("client", "server")
    ):
        raise AssertionError("ChangeCipherSpec events were not captured")
    if version == ssl.TLSVersion.TLSv1_3 and not any(
        event[2] == CONTENT_INNER for records in events.values() for event in records
    ):
        raise AssertionError("TLS 1.3 inner content types were not captured")
    if version == ssl.TLSVersion.TLSv1_3:
        for side in ("client", "server"):
            for direction in ("read", "write"):
                if not any(
                    event[0] == direction
                    and event[2] == CONTENT_INNER
                    and event[3] == CONTENT_HANDSHAKE
                    and event[4] == bytes((CONTENT_HANDSHAKE,))
                    for event in events[side]
                ):
                    raise AssertionError((side, direction, "missing inner handshake type"))
    return events


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--certdata", type=Path, required=True)
    args = parser.parse_args()
    result = {}
    for name, version in (
        ("tls12", ssl.TLSVersion.TLSv1_2),
        ("tls13", ssl.TLSVersion.TLSv1_3),
    ):
        events = run_version(args.certdata, version)
        result[name] = {
            side: [
                [direction, protocol_version, content_type, message_type, len(data)]
                for direction, protocol_version, content_type, message_type, data in records
            ]
            for side, records in events.items()
        }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
