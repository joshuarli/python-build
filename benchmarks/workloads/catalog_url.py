"""Complete URL normalization and stable-key batches using the catalog fixture.

One operation processes the entire fixed batch. Fixture creation and loading
are outside the timed interval; normalization, key creation, and hashing of
every output are inside it.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path
from types import ModuleType


class WorkloadError(RuntimeError):
    """The fixed catalog batch or its complete output changed."""


_FIXTURE = (Path(__file__).resolve().parent / "fixtures" / "tooling" /
            "python_corpus" / "catalog_service" / "normalize.py")
_EXPECTED_INPUT = "7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f"
_EXPECTED_OUTPUT = "a6fedf33e0fd5e72b79af8d77499b9a7bb8e8d53491955f2e554570679e04941"


def _catalog_normalize() -> ModuleType:
    # Loading this standalone fixture by its file avoids cwd and sys.path
    # assumptions when the runner invokes this module with python -m.
    spec = importlib.util.spec_from_file_location("benchmark_catalog_normalize", _FIXTURE)
    if spec is None or spec.loader is None:
        raise WorkloadError(f"catalog normalizer is missing: {_FIXTURE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _batch() -> tuple[tuple[str, tuple[str, ...]], ...]:
    cases = (
        (" HTTPS://Example.COM/a/b/?q=one#Top ", ("Catalog", "Plain title", "1")),
        ("https://shop.example/caf%C3%A9/%E2%82%AC?q=%2F#résumé", ("Café", "€ price", "a/b")),
        ("https://user%20name:p%40ss@host.example:8443/a/../b?x=1&x=2#frag", ("User Name", "p@ss", "a?b#c")),
        ("http://192.0.2.17:8080/a//b/?a=%26&b=2", ("IPv4", "192.0.2.17", "a:b")),
        ("https://reader:secret@[2001:db8::1]:443/docs?q=ok#part", ("IPv6", "reader", "[2001:db8::1]")),
        ("https://example.org/%2f/%ZZ/%?bad=%G1#%", ("Malformed %", "already%20escaped", "x/y")),
        ("https://example.org/a%20b/%252F?q=a+b#h%23i", ("Escapes", "a%20b", "one+two")),
        ("https://example.org/日本語/naïve?tag=é#東京", ("日本語", "NAÏVE", "東京")),
        ("https://example.org/short", ("x", "y", "z")),
        ("https://example.org/" + "p" * 2048 + "/end?q=" + "%20" * 128,
         ("Long", "é" * 512, "a/b?c#d" * 64)),
        ("https://example.org/a/./b/../c///", ("Path", "a/./b/../c", "")),
        ("http://EXAMPLE.net:80/?empty=&reserved=%3F%23%2F#section", ("Reserved", "?/#&=", "  multi   space  ")),
    )
    unique = tuple((f"https://items.example/{index:03d}/café%20item?ref={index}&kind=%2F#part{index}",
                    ("Item", f"Café {index:03d}", f"kind/{index % 5}"))
                   for index in range(24))
    return cases + unique + cases


def _digest(records: tuple[tuple[str, ...], ...]) -> str:
    digest = hashlib.sha256()
    for record in records:
        digest.update(len(record).to_bytes(4, "big"))
        for value in record:
            encoded = value.encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
    return digest.hexdigest()


def catalog_url_normalize(iterations: int) -> dict[str, int | float | str]:
    """Normalize 48 URLs and create 48 keys per complete batch."""
    if iterations < 1:
        raise ValueError("iterations must be positive")
    batch = _batch()
    catalog = _catalog_normalize()
    input_digest = _digest(tuple((url, *parts) for url, parts in batch))
    if input_digest != _EXPECTED_INPUT:
        raise WorkloadError(f"catalog URL input changed: {input_digest}")

    started = time.perf_counter()
    for _ in range(iterations):
        outputs = tuple((catalog.normalize_url(url), catalog.stable_key(parts))
                        for url, parts in batch)
        output_digest = _digest(outputs)
        if output_digest != _EXPECTED_OUTPUT:
            raise WorkloadError(f"catalog URL output changed: {output_digest}")
    elapsed = time.perf_counter() - started
    return {"operation_count": iterations, "digest": output_digest,
            "input_digest": input_digest, "elapsed_seconds": elapsed,
            "urls_per_operation": len(batch), "keys_per_operation": len(batch)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=("catalog_url_normalize",))
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args(argv)
    if args.iterations < 1:
        parser.error("--iterations must be positive")
    try:
        result = catalog_url_normalize(args.iterations)
    except WorkloadError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
