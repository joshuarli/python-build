# Experimental TLS support policy

This policy defines qualification for the isolated OpenSSL-free macOS arm64
candidate. It follows the owner's decision to support modern cryptography
with a small maintained surface. Production defaults and release qualification
remain unchanged until a separate adoption decision.

[Oxish's cryptographic allowlist](https://github.com/djc/oxish#supported-cryptographic-algorithms)
is a useful model for keeping scope small. Oxish implements SSH; the TLS
requirements here follow the actual rustls/Graviola interfaces.

## Required transport and credential support

| Area | Required support |
| --- | --- |
| Protocols | TLS 1.2 and TLS 1.3 |
| Encryption | AES-128-GCM, AES-256-GCM, ChaCha20-Poly1305 |
| Key exchange | X25519MLKEM768 hybrid, X25519, P-256, P-384 |
| TLS 1.2 suites | ECDHE with RSA or ECDSA authentication and the AEAD algorithms above |
| Authentication | Supported RSA/SHA-2, ECDSA/SHA-2, and Ed25519 signatures; TLS 1.3 RSA uses RSA-PSS |
| Certificate paths | Full selected-path verification, strict checks, hostname validation, constraints, and the product CA-source policy |
| Private keys | Plaintext PKCS#8, PKCS#1, and SEC1 containers; modern encrypted PKCS#8 |
| Python integration | Normal ssl imports, sockets, MemoryBIO, asyncio, HTTPS, client authentication, SNI, ALPN, sessions, and supported algorithm controls |

A format name does not determine a key's security. A plaintext PKCS#1 RSA
container can hold a supported modern key. AES-CBC inside encrypted PKCS#8
is separate from a CBC TLS cipher suite. Credential-loading qualification must
identify its actual encryption and key-derivation algorithms.

## Retired capabilities

Do not add providers or compatibility paths for SSLv2, SSLv3, TLS 1.0,
TLS 1.1, finite-field DH/DHE, static RSA key exchange, CBC TLS suites,
RC4, DES/3DES, SHA-1 TLS signatures, unsafe legacy renegotiation, or
security-level downgrades. Finite-field DH is excluded to keep the provider
surface small; this is not a claim that RFC 7919 groups are broken.

Traditional encrypted PEM using Proc-Type/DEK-Info and EVP_BytesToKey-style
MD5 derivation is retired. Its decryptors and dedicated dependencies must be
removed, rather than retained behind a disabled default. Unsupported requests
must fail explicitly; they must not select another algorithm or an unverified
connection.

Trusted roots are supplied by the existing CA-source contract. A trusted
root's historical self-signature is distinct from an untrusted certificate-path
signature or a negotiated TLS signature. Do not silently remove roots from the
pinned Mozilla bundle or relax path verification as part of this policy.

## Qualification accounting

Run upstream suites unchanged and preserve their complete results. Classify
failures against this policy after inspecting the actual assertions. Retired
capability tests are outside the candidate contract; failures in required
modern behavior remain implementation defects. OpenSSL version guards and
private C object-layout assumptions need explicit accounting and direct tests
for modern behavior that would otherwise be skipped.

The original missing-AKI and malformed-chain regressions remain mandatory.
Nothing in this policy permits weaker certificate acceptance, permissive
fallbacks, fabricated backend identities, or ignored setters.

Hashlib compatibility is a separate API contract. This TLS policy does not
remove digest APIs used for file checksums or data formats.
