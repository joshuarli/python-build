# Cipher support

The Graviola build exposes three TLS 1.3 suites:

- `TLS_AES_128_GCM_SHA256`
- `TLS_AES_256_GCM_SHA384`
- `TLS_CHACHA20_POLY1305_SHA256`

It exposes six TLS 1.2 suites: ECDHE with AES-128-GCM, AES-256-GCM, or
ChaCha20-Poly1305, each with RSA or ECDSA authentication.

`SSLContext.set_ciphers()` selects TLS 1.2 suites. It leaves the TLS 1.3 suites
enabled. `SSLContext.get_ciphers()` reports the builder's enabled suites with
OpenSSL-style names, IDs, protocols, descriptions, and strength fields.

`HIGH`, `ALL`, and `DEFAULT` select the supported TLS 1.2 suites. The provider
does not offer static RSA, DHE, PSK, CCM, ARIA, or CBC suites. Unsupported
suite names contribute no selection. `set_ciphers()` raises `ssl.SSLError`
when no supported TLS 1.2 suite remains.

The parser supports `@STRENGTH`, `+` reordering, `-` temporary removal, and `!`
permanent exclusion. It raises `NotImplementedError` for other `@` directives.
In particular, it rejects `@SECLEVEL=N` because the provider has no matching
security-level control.
