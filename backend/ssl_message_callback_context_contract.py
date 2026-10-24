import argparse
import concurrent.futures
from collections.abc import Callable
import json
import socket
import ssl
from pathlib import Path

CONTENT_HANDSHAKE = 22
MESSAGE_CLIENT_HELLO = 1
MESSAGE_SERVER_HELLO = 2
MESSAGE_NEW_SESSION_TICKET = 4


def make_server_context(certdata: Path, version: ssl.TLSVersion) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = version
    context.maximum_version = version
    context.load_cert_chain(str(certdata / "allsans.pem"))
    return context


def handshake(client: ssl.SSLSocket, server: ssl.SSLSocket) -> None:
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        client_handshake = executor.submit(client.do_handshake)
        server_handshake = executor.submit(server.do_handshake)
        client_handshake.result(timeout=15)
        server_handshake.result(timeout=15)


def open_socket_pair(
    client_context: ssl.SSLContext,
    server_context: ssl.SSLContext,
) -> tuple[ssl.SSLSocket, ssl.SSLSocket]:
    client_raw, server_raw = socket.socketpair()
    client_raw.settimeout(10)
    server_raw.settimeout(10)
    client = client_context.wrap_socket(
        client_raw,
        server_hostname="www.example.org",
        do_handshake_on_connect=False,
    )
    server = server_context.wrap_socket(
        server_raw,
        server_side=True,
        do_handshake_on_connect=False,
    )
    return client, server


def callback_for(
    events: list[tuple],
    owner: dict[str, ssl.SSLSocket],
    label: str,
) -> Callable:
    def callback(connection, direction, version, content_type, message_type, data):
        if not isinstance(connection, ssl.SSLSocket):
            raise AssertionError((label, type(connection)))
        if direction not in {"read", "write"} or type(data) is not bytes:
            raise AssertionError((label, direction, type(data)))
        events.append(
            (
                direction,
                int(version),
                int(content_type),
                int(message_type),
                connection is owner.get("socket"),
            )
        )

    return callback


def run_sni_case(
    certdata: Path,
    initial_enabled: bool,
    selected_enabled: bool,
) -> dict:
    owner: dict[str, ssl.SSLSocket] = {}
    events = {"initial": [], "selected": []}
    client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client_context.check_hostname = False
    client_context.verify_mode = ssl.CERT_NONE
    client_context.minimum_version = ssl.TLSVersion.TLSv1_2
    client_context.maximum_version = ssl.TLSVersion.TLSv1_2
    contexts = {}
    for label, enabled in (
        ("initial", initial_enabled),
        ("selected", selected_enabled),
    ):
        context = make_server_context(certdata, ssl.TLSVersion.TLSv1_2)
        if enabled:
            context._msg_callback = callback_for(events[label], owner, label)
        contexts[label] = context
    initial = contexts["initial"]
    selected = contexts["selected"]
    sni_observations = []

    def select_context(connection, server_name, context):
        sni_observations.append(
            (connection is owner.get("socket"), server_name)
        )
        connection.context = selected

    initial.sni_callback = select_context
    client, server = open_socket_pair(client_context, initial)
    owner["socket"] = server
    try:
        handshake(client, server)
        client_hello = [
            event
            for event in events["initial"]
            if event[0] == "read"
            and event[2] == CONTENT_HANDSHAKE
            and event[3] == MESSAGE_CLIENT_HELLO
        ]
        selected_client_hello = [
            event
            for event in events["selected"]
            if event[2] == CONTENT_HANDSHAKE
            and event[3] == MESSAGE_CLIENT_HELLO
        ]
        selected_server_hello = [
            event
            for event in events["selected"]
            if event[0] == "write"
            and event[2] == CONTENT_HANDSHAKE
            and event[3] == MESSAGE_SERVER_HELLO
        ]
        if sni_observations != [(True, "www.example.org")]:
            raise AssertionError((initial_enabled, selected_enabled, sni_observations))
        if initial_enabled != bool(client_hello):
            raise AssertionError((initial_enabled, client_hello, events["initial"]))
        if selected_client_hello:
            raise AssertionError((selected_enabled, selected_client_hello))
        if selected_enabled != bool(selected_server_hello):
            raise AssertionError(
                (selected_enabled, selected_server_hello, events["selected"])
            )
        if any(not event[4] for label in events for event in events[label]):
            raise AssertionError((initial_enabled, selected_enabled, events))
        return {
            "initial_enabled": initial_enabled,
            "selected_enabled": selected_enabled,
            "initial_client_hello": len(client_hello),
            "selected_server_hello": len(selected_server_hello),
            "initial_event_count": len(events["initial"]),
            "selected_event_count": len(events["selected"]),
            "server_name": sni_observations[0][1],
        }
    finally:
        client.close()
        server.close()


def make_client_context(
    enabled: bool,
    owner: dict[str, ssl.SSLSocket],
    events: list[tuple],
    label: str,
) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    if enabled:
        context._msg_callback = callback_for(events, owner, label)
    return context


def run_reassignment_case(
    certdata: Path,
    initial_enabled: bool,
    selected_enabled: bool,
) -> dict:
    owner: dict[str, ssl.SSLSocket] = {}
    initial_events: list[tuple] = []
    selected_events: list[tuple] = []
    initial = make_client_context(
        initial_enabled, owner, initial_events, "initial"
    )
    selected = make_client_context(
        selected_enabled, owner, selected_events, "selected"
    )
    server_context = make_server_context(certdata, ssl.TLSVersion.TLSv1_3)
    server_context.num_tickets = 2
    client, server = open_socket_pair(initial, server_context)
    owner["socket"] = client
    try:
        handshake(client, server)
        client.context = selected
        initial_count_after_switch = len(initial_events)
        server.sendall(b"x")
        if client.recv(1) != b"x":
            raise AssertionError("TLS application data changed")
        ticket_events = [
            event
            for event in selected_events
            if event[0] == "read"
            and event[2] == CONTENT_HANDSHAKE
            and event[3] == MESSAGE_NEW_SESSION_TICKET
        ]
        if selected_enabled and not ticket_events:
            raise AssertionError((selected_enabled, selected_events))
        if not selected_enabled and len(initial_events) != initial_count_after_switch:
            raise AssertionError((initial_events, initial_count_after_switch))
        if any(not event[4] for event in (*initial_events, *selected_events)):
            raise AssertionError((initial_events, selected_events))
        return {
            "initial_enabled": initial_enabled,
            "selected_enabled": selected_enabled,
            "handshake_event_count": initial_count_after_switch,
            "selected_ticket_count": len(ticket_events),
        }
    finally:
        client.close()
        server.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--certdata", type=Path, required=True)
    args = parser.parse_args()
    result = {
        "sni": [
            run_sni_case(args.certdata, bool(initial), bool(selected))
            for initial in (0, 1)
            for selected in (0, 1)
        ],
        "reassignment": [
            run_reassignment_case(args.certdata, bool(initial), bool(selected))
            for initial in (0, 1)
            for selected in (0, 1)
        ],
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
