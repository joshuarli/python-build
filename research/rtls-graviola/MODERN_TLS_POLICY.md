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

## Private-key encryption

Encrypted PKCS#8 accepts PBES2 with AES-128/192/256-CBC and either
PBKDF2-HMAC-SHA224/256/384/512 or scrypt. The maintained PKCS#8 implementation
performs parsing, key derivation, and decryption. PBES1, PBKDF2-HMAC-SHA1,
DES/3DES encryption, and traditional Proc-Type/DEK-Info PEM are rejected.
Plaintext PKCS#8, RSA PKCS#1, and EC SEC1 containers remain supported.

Scrypt parameters are checked before derivation against the reference
key-loader's 32 MiB memory allowance, including its working buffers; invalid,
zero, and overflowing costs fail without allocating those buffers. PBKDF2
requires a positive iteration count no greater than the maintained library's
100,000,000-iteration ceiling. These limits have no configuration override.

The modern-key contract exercises the original CPython encrypted fixture,
all listed AES/SHA2 combinations, scrypt, password callbacks, and rejection
without changing a previously loaded identity, using both TLS 1.2 and TLS 1.3.
Its paired reference run
records the intentional rejection of retired formats. The original
82-case certificate acceptance corpus remains unchanged and passes.

## Retired capabilities

Do not add providers or compatibility paths for SSLv2, SSLv3, TLS 1.0,
TLS 1.1, finite-field DH/DHE, static RSA key exchange, CBC TLS suites,
RC4, DES/3DES, SHA-1 TLS signatures, unsafe legacy renegotiation, or
TLS compression, and security-level downgrades. Finite-field DH is excluded to keep the provider
surface small; this is not a claim that RFC 7919 groups are broken.

Traditional encrypted PEM using Proc-Type/DEK-Info and EVP_BytesToKey-style
MD5 derivation is retired. Its decryptors and dedicated dependencies must be
removed, rather than retained behind a disabled default. Unsupported requests
must fail explicitly; they must not select another algorithm or an unverified
connection. CPython entrypoints for compiled-out capabilities may raise
`NotImplementedError` without reading parameters or changing a context.

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

Hashlib and HMAC retain CPython API compatibility, including MD5 and SHA-1
for checksum and data-format uses, as explicitly confirmed by the owner.
Those digest APIs do not add algorithms to the TLS allowlist.
