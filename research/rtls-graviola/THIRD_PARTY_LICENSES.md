# Third-party licenses

The prototype patch does not vendor third-party source or add production
dependencies. Its `rust/Cargo.lock` delta adds or changes these packages:

| Package | Version | License expression |
| --- | --- | --- |
| `rustls-webpki` (locally adapted verified-path API) | 0.103.15 | ISC |
| `rustls` (session metadata accessors) | 0.23.45 | Apache-2.0 OR ISC OR MIT |
| RTLS source | 2026.10.3 | MIT |
| `rustls-graviola` | 0.4.0 | Apache-2.0 OR ISC OR MIT-0 |
| `graviola` | 0.4.1 | Apache-2.0 OR ISC OR MIT-0 |
| `getrandom` | 0.3.4 | MIT OR Apache-2.0 |
| `r-efi` | 5.3.0 | MIT OR Apache-2.0 OR LGPL-2.1-or-later |
| `wasip2` | 1.0.4+wasi-0.2.12 | Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT |
| `wit-bindgen` | 0.57.1 | Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT |
| `block-buffer` | 0.12.1 | MIT OR Apache-2.0 |
| `cpufeatures` | 0.3.1 | MIT OR Apache-2.0 |
| `crypto-common` | 0.2.2 | MIT OR Apache-2.0 |
| `digest` | 0.11.3 | MIT OR Apache-2.0 |
| `hybrid-array` | 0.4.15 | MIT OR Apache-2.0 |
| `sha1` | 0.11.0 | MIT OR Apache-2.0 |

The `getrandom`, `r-efi`, `wasip2`, and `wit-bindgen` entries are target
support dependencies recorded by Cargo. The lockfile also removes the AWS-LC
native build dependencies. Exact registry checksums remain in
[`rtls-graviola.patch`](rtls-graviola.patch).

The no-`_ssl` contract harness uses certificate and key fixtures from the
CPython 3.15.1 `Lib/test/certdata` directory, including its PSF-licensed test
CA key to generate a local expired leaf. These files are not copied into this
repository or the product.

`prepare_webpki.py` pins the original rustls-webpki 0.103.15 crate archive by
SHA-256. `webpki-policy.patch` adapts path-length counting and exposes existing
DNS validation to the policy layer. The extracted source retains its ISC
license notices. The CPython protocol-message enums in `ssl_metadata.py` are
covered by the Python Software Foundation license.
