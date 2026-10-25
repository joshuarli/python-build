from __future__ import annotations

_CIPHER_ORDER = (
    "ECDHE-ECDSA-AES256-GCM-SHA384",
    "ECDHE-RSA-AES256-GCM-SHA384",
    "ECDHE-ECDSA-CHACHA20-POLY1305",
    "ECDHE-RSA-CHACHA20-POLY1305",
    "ECDHE-ECDSA-AES128-GCM-SHA256",
    "ECDHE-RSA-AES128-GCM-SHA256",
)

_OPENSSL_TO_IANA: dict[str, str] = {
    "ECDHE-ECDSA-AES256-GCM-SHA384": "TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384",
    "ECDHE-RSA-AES256-GCM-SHA384": "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384",
    "ECDHE-ECDSA-CHACHA20-POLY1305": "TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305_SHA256",
    "ECDHE-RSA-CHACHA20-POLY1305": "TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305_SHA256",
    "ECDHE-ECDSA-AES128-GCM-SHA256": "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256",
    "ECDHE-RSA-AES128-GCM-SHA256": "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256",
}

_TLS13_SUITES: dict[str, str] = {
    "TLS_AES_128_GCM_SHA256": "TLS13_AES_128_GCM_SHA256",
    "TLS_AES_256_GCM_SHA384": "TLS13_AES_256_GCM_SHA384",
    "TLS_CHACHA20_POLY1305_SHA256": "TLS13_CHACHA20_POLY1305_SHA256",
}

_IANA_TO_OPENSSL = {value: key for key, value in _OPENSSL_TO_IANA.items()}
_IANA_TO_OPENSSL.update({value: key for key, value in _TLS13_SUITES.items()})

_ALL_CIPHERS = frozenset(_CIPHER_ORDER)
_GROUP_ALIASES: dict[str, frozenset[str]] = {
    "HIGH": _ALL_CIPHERS,
    "ALL": _ALL_CIPHERS,
    "DEFAULT": _ALL_CIPHERS,
    "ECDH": frozenset(name for name in _CIPHER_ORDER if "ECDHE" in name),
    "ECDHE": frozenset(name for name in _CIPHER_ORDER if "ECDHE" in name),
    "kECDHE": frozenset(name for name in _CIPHER_ORDER if "ECDHE" in name),
    "aECDSA": frozenset(name for name in _CIPHER_ORDER if "ECDSA" in name),
    "aRSA": frozenset(name for name in _CIPHER_ORDER if "RSA" in name),
    "AESGCM": frozenset(
        name for name in _CIPHER_ORDER if "AES" in name and "GCM" in name
    ),
    "AES128": frozenset(name for name in _CIPHER_ORDER if "AES128" in name),
    "AES256": frozenset(name for name in _CIPHER_ORDER if "AES256" in name),
    "AES": frozenset(name for name in _CIPHER_ORDER if "AES" in name),
    "CHACHA20": frozenset(name for name in _CIPHER_ORDER if "CHACHA20" in name),
    "aNULL": frozenset(),
    "eNULL": frozenset(),
    "NULL": frozenset(),
    "MD5": frozenset(),
    "RC4": frozenset(),
    "3DES": frozenset(),
    "DES": frozenset(),
    "EXPORT": frozenset(),
    "LOW": frozenset(),
    "MEDIUM": frozenset(),
    "DH": frozenset(),
    "DHE": frozenset(),
    "kDHE": frozenset(),
    "aDSS": frozenset(),
    "DSS": frozenset(),
    "SEED": frozenset(),
    "IDEA": frozenset(),
    "CAMELLIA": frozenset(),
    "CAMELLIA128": frozenset(),
    "CAMELLIA256": frozenset(),
    "PSK": frozenset(),
    "SRP": frozenset(),
    "GOST": frozenset(),
    "ARIA": frozenset(),
    "ARIA128": frozenset(),
    "ARIA256": frozenset(),
    "CCM": frozenset(),
    "CCM8": frozenset(),
}

_CIPHER_METADATA: dict[str, tuple[str, str, str, str, int]] = {
    "ECDHE-ECDSA-AES256-GCM-SHA384": (
        "TLSv1.2", "ECDH", "ECDSA", "AESGCM(256)", 256
    ),
    "ECDHE-RSA-AES256-GCM-SHA384": (
        "TLSv1.2", "ECDH", "RSA", "AESGCM(256)", 256
    ),
    "ECDHE-ECDSA-CHACHA20-POLY1305": (
        "TLSv1.2", "ECDH", "ECDSA", "CHACHA20/POLY1305(256)", 256
    ),
    "ECDHE-RSA-CHACHA20-POLY1305": (
        "TLSv1.2", "ECDH", "RSA", "CHACHA20/POLY1305(256)", 256
    ),
    "ECDHE-ECDSA-AES128-GCM-SHA256": (
        "TLSv1.2", "ECDH", "ECDSA", "AESGCM(128)", 128
    ),
    "ECDHE-RSA-AES128-GCM-SHA256": (
        "TLSv1.2", "ECDH", "RSA", "AESGCM(128)", 128
    ),
    "TLS_AES_128_GCM_SHA256": ("TLSv1.3", "any", "any", "AESGCM(128)", 128),
    "TLS_AES_256_GCM_SHA384": ("TLSv1.3", "any", "any", "AESGCM(256)", 256),
    "TLS_CHACHA20_POLY1305_SHA256": (
        "TLSv1.3", "any", "any", "CHACHA20/POLY1305(256)", 256
    ),
}


def parse_cipher_string(cipher_string: str) -> list[str]:
    if not isinstance(cipher_string, str):
        raise TypeError("cipher string must be str")
    if not cipher_string:
        _raise_no_ciphers(cipher_string)

    selected: list[str] = []
    permanently_excluded: set[str] = set()
    for token in cipher_string.replace(" ", ":").split(":"):
        token = token.strip()
        if not token:
            continue
        if token.startswith("@"):
            if token == "@STRENGTH":
                selected.sort(key=_get_strength_bits, reverse=True)
                continue
            raise NotImplementedError(
                f"cipher directive {token!r} is not supported by RTLS"
            )
        if token[0] in "!-":
            matches = set(_resolve_cipher_expression(token[1:]))
            if token[0] == "!":
                permanently_excluded.update(matches)
            selected = [cipher for cipher in selected if cipher not in matches]
            continue
        if token.startswith("+"):
            matches = set(_resolve_cipher_expression(token[1:]))
            selected = [cipher for cipher in selected if cipher not in matches] + [
                cipher for cipher in selected if cipher in matches
            ]
            continue
        for cipher in _resolve_cipher_expression(token):
            if cipher not in permanently_excluded and cipher not in selected:
                selected.append(cipher)

    if not selected:
        _raise_no_ciphers(cipher_string)
    return [_OPENSSL_TO_IANA[cipher] for cipher in selected]


def parse_tls13_cipher_suites(cipher_suites: str) -> list[str]:
    if not cipher_suites:
        return []
    selected = [
        _TLS13_SUITES[name]
        for name in cipher_suites.split(":")
        if name in _TLS13_SUITES
    ]
    if not selected:
        from ._exceptions import SSLError

        raise SSLError(0, "No cipher suite can be selected.")
    return selected


def _resolve_cipher_expression(expression: str) -> tuple[str, ...]:
    if "+" in expression:
        groups = [_resolve_cipher_group(name) for name in expression.split("+")]
        if not groups or any(not group for group in groups):
            return ()
        matching = set.intersection(*groups)
    else:
        matching = _resolve_cipher_group(expression)
    return tuple(name for name in _CIPHER_ORDER if name in matching)


def _resolve_cipher_group(name: str) -> set[str]:
    if name in _GROUP_ALIASES:
        return set(_GROUP_ALIASES[name])
    if name in _OPENSSL_TO_IANA:
        return {name}
    name_upper = name.upper()
    for group_name, members in _GROUP_ALIASES.items():
        if group_name.upper() == name_upper:
            return set(members)
    return set()


def get_cipher_descriptions(
    enabled_cipher_suites: list[tuple[str, int]],
) -> list[dict[str, object]]:
    descriptions = []
    for iana_name, suite_id in enabled_cipher_suites:
        openssl_name = _IANA_TO_OPENSSL.get(iana_name)
        if openssl_name is None:
            raise RuntimeError(
                f"missing OpenSSL metadata for Rustls suite {iana_name!r}"
            )
        try:
            protocol, key_exchange, authentication, encryption, bits = _CIPHER_METADATA[
                openssl_name
            ]
        except KeyError as error:
            raise RuntimeError(
                f"missing cipher metadata for suite {openssl_name!r}"
            ) from error
        description = (
            f"{openssl_name:<31}{protocol} Kx={key_exchange:<8} "
            f"Au={authentication:<5} Enc={encryption:<22} Mac=AEAD"
        )
        descriptions.append(
            {
                "name": openssl_name,
                "id": 0x03000000 | suite_id,
                "protocol": protocol,
                "description": description,
                "strength_bits": bits,
                "alg_bits": bits,
            }
        )
    return descriptions


def _get_strength_bits(cipher_name: str) -> int:
    metadata = _CIPHER_METADATA.get(cipher_name)
    return metadata[4] if metadata is not None else 0


def _raise_no_ciphers(cipher_string: str) -> None:
    from ._exceptions import SSLError

    raise SSLError(1, f"[SSL] No cipher can be selected from '{cipher_string}'")
