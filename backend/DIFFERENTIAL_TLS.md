# Differential TLS checks

`differential_tls.py` runs one generated corpus under two interpreters and
diffs the outcomes: 14 leaf certificates (exact, upper case, trailing dot,
wildcards including partial, TLD and double, IDNA, IPv4, IPv6, an IP written as
a DNS name, CN-only, CN with a different SAN, several SANs) against 17 hostnames
in an in-memory handshake; 17 chain and policy cases (expired, not yet valid,
client-only and any EKU, missing or key-agreement-only key usage, missing
basicConstraints, a leaf marked CA, missing AKI, ECDSA and 1024-bit RSA keys,
an intermediate sent and not sent, a path-length violation, a self-signed leaf
used as its own anchor); 4 CRL cases (leaf revoked, clean CRL, expired CRL, no CRL
loaded) with leaf checking on; and 59 mutated PEM variants of the CA (truncations, bit
flips, wrong labels, CRLF, blank lines, text around the block) loaded as a trust
anchor and converted with `PEM_cert_to_DER_cert`.

```sh
python3 backend/differential_tls.py corpus .work/tmp/dtls/corpus
<openssl-reference-python> -I backend/differential_tls.py run .work/tmp/dtls/corpus ref.json
<product-python> -I backend/differential_tls.py run .work/tmp/dtls/corpus prod.json
python3 backend/differential_tls.py diff ref.json prod.json
```

## Result, 2026-10-30

Reference OpenSSL 3.5.7 against the macOS product build at `38faf1d`: 377 cases,
325 agree, 52 differ.

Handshakes: 195 of 238 agree, including every wildcard, IDNA, IP SAN, CN-only,
CN-fallback, and multi-SAN case. The 43 differences:

- 39 are rejections by both with a different `verify_code`: an IP address
  mismatch is reported as 62 (hostname mismatch) instead of OpenSSL's 64.
- 4 are trailing-dot handling. The product treats `example.com.` as
  `example.com` (3 cases accept where OpenSSL rejects) and does not match a
  certificate whose SAN itself ends in a dot (1 case rejects where OpenSSL
  accepts). Both are the same host name; neither admits a different host.

No hostname or IP case is accepted by the product that names a different host.

Chain and policy cases: 16 of 17 agree, including the verify codes (expired 10,
not yet valid 9, wrong EKU 26, missing AKI 85, unknown issuer 20, path length
25). The one difference is stricter in the product: a leaf with
`basicConstraints=CA:TRUE` is rejected (code 1) where OpenSSL accepts it. A
1024-bit RSA server key is refused at load by both. All four CRL cases agree,
including codes (revoked 23, expired CRL 12, CRL missing 3).

PEM and DER loading, 8 differences (7 unresolved, 1 since fixed), none a verification
bypass, since a trust anchor contributes only its subject and key:

- Blank lines inside the base64 body load in the product and fail in OpenSSL.
- Five single-bit flips of the CA DER load in OpenSSL and fail in the product:
  three inside the trailing signature value (bytes 506 to 508) and two near the
  validity period (bytes 99 and 103). One flip, inside the commonName OID
  (byte 56), loads in the product and fails in OpenSSL. The product's cause for
  rejecting the five has not been traced.
- Loading an empty `cadata` raised `SSLError` in the product where OpenSSL
  raises `ValueError`; the facade now raises `ValueError("empty cadata")`.
