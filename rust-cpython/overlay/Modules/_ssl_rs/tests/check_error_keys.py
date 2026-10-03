"""Check eager library-local error keys and public TLS failure metadata."""
import _ssl
import gc
import ssl


def error_maps():
    maps = [value for value in gc.get_referents(_ssl)
            if type(value) is dict and value and value is not _ssl.__dict__]
    groups = [value for value in maps
              if all(type(names) is dict for names in value.values())]
    libraries = [value for value in maps
                 if all(type(name) is str for name in value.values())]
    assert len(groups) == len(libraries) == 1, "eager library-local maps missing"
    return groups[0], libraries[0]


def check_error_keys():
    groups, libraries = error_maps()
    shared = {}
    for library, reasons in groups.items():
        assert type(library) is int and library in libraries
        assert reasons and all(type(name) is str for name in reasons.values())
        for reason in reasons:
            assert type(reason) is int
            if -5 <= reason <= 256:
                assert reason is int(str(reason)), "small reason owns a new integer"
                shared.setdefault(reason, set()).add(library)
    assert any(len(owners) > 1 for owners in shared.values()), "reason namespaces do not overlap"

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    def handshake():
        incoming = ssl.MemoryBIO()
        connection = context.wrap_bio(incoming, ssl.MemoryBIO(),
                                      server_hostname="example.test")
        incoming.write(b"GET / HTTP/1.0\r\n\r\n")
        connection.do_handshake()

    def malformed_pem():
        context.load_verify_locations(cadata=(
            "-----BEGIN CERTIFICATE-----\ninvalid\n-----END CERTIFICATE-----"))

    for operation, coded in ((handshake, True), (malformed_pem, False)):
        errors = []
        for _ in range(2):
            try:
                operation()
            except ssl.SSLError as error:
                errors.append(error)
            else:
                raise AssertionError("invalid TLS or certificate data did not raise")
        first, second = errors
        if not coded:
            assert first.library is None and first.reason is None
            assert second.library is None and second.reason is None
            assert first.errno == second.errno == 0
            assert "cadata does not contain a certificate" in str(first)
            continue
        assert first.reason and first.library
        assert first.reason is second.reason
        assert first.library is second.library
        library = next(code for code, name in libraries.items()
                       if name is first.library)
        assert any(name is first.reason for name in groups[library].values())
        assert first.reason in str(first) and first.library in str(first)
    assert all(before is after for before, after in zip((groups, libraries),
                                                      error_maps()))
    print("library-local SSL keys and canonical TLS metadata: PASS")


if __name__ == "__main__":
    check_error_keys()
