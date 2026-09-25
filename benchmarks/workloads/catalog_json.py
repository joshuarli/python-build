"""Export a complete, deterministic catalog through its public JSON API.

One operation exports every record as one JSON array. Record construction and
the fixed input check precede timing; output hashing follows timing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path


_CORPUS = Path(__file__).resolve().parent / "fixtures" / "tooling" / "python_corpus"
_EXPECTED_INPUT = "9c3c7d7b1dd6d58e72b446ce4684ee93edc031aca5bdd6b8c6d852bc079b8bc4"
_EXPECTED_OUTPUT = "e73d3916e9d6984dacef72251336a1582a4d64814c244595aeb566af4d9146d3"
_RECORD_COUNT = 512


class WorkloadError(RuntimeError):
    """The fixed catalog input or its complete exported bytes changed."""


def _catalog_modules():
    # The checked-in fixture is an ordinary package with absolute imports.
    # Make its parent visible for direct `python -m` and harness invocation.
    corpus = str(_CORPUS)
    if corpus not in sys.path:
        sys.path.insert(0, corpus)
    from catalog_service.codec import encode_entry
    from catalog_service.export import export_json
    from catalog_service.model import CatalogEntry, EntryKind
    return CatalogEntry, EntryKind, encode_entry, export_json


def _entries(CatalogEntry, EntryKind):
    """Create varied records in non-identifier order, as a repository may."""
    kinds = tuple(EntryKind)
    titles = (
        "Release notes: Python & JSON", "Café inventory / été",
        "画像の説明と検索", 'Quoted "title" \\ path',
        "Package manifest — arm64", "Source map: Δ changes",
        "Security advisory <2026>", "Documentation: naïve approach",
    )
    bodies = (
        "A compact record with ordinary English words and punctuation.",
        "Unicode text: résumé, 東京, emoji 🐍, and € prices. " * 3,
        'Escapes: quote " slash \\ tab\t and newline\n in a field.',
        "Long description with repeated searchable detail. " * 12,
    )
    return tuple(
        CatalogEntry(
            identifier=f"item-{(index * 73) % _RECORD_COUNT:04d}",
            title=f"{titles[index % len(titles)]} #{index:04d}",
            kind=kinds[index % len(kinds)],
            body=bodies[index % len(bodies)],
            labels=("Public", f"Group-{index % 17}", "été" if index % 7 == 0 else "stable"),
            attributes={
                "uri": f"https://catalog.example/items/{index}?view=full&lang=ja",
                "owner": ("Alice", "Bjørn", "Team Δ")[index % 3],
                "mime": ("application/json", "image/png", "text/plain")[index % 3],
            },
            revision=1 + index % 9,
        )
        for index in range(_RECORD_COUNT)
    )


def _input_digest(entries, encode_entry) -> str:
    digest = hashlib.sha256()
    for entry in entries:
        encoded = encode_entry(entry)
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def catalog_json_export(iterations: int) -> dict[str, int | float | str]:
    """Time one complete 512-record JSON export per iteration."""
    if iterations < 1:
        raise ValueError("iterations must be positive")
    CatalogEntry, EntryKind, encode_entry, export_json = _catalog_modules()
    entries = _entries(CatalogEntry, EntryKind)
    input_digest = _input_digest(entries, encode_entry)
    if input_digest != _EXPECTED_INPUT:
        raise WorkloadError(f"catalog JSON input changed: {input_digest}")

    elapsed = 0.0
    for _ in range(iterations):
        started = time.perf_counter()
        payload = export_json(entries)
        elapsed += time.perf_counter() - started
        output_digest = hashlib.sha256(payload).hexdigest()
        if output_digest != _EXPECTED_OUTPUT:
            raise WorkloadError(f"catalog JSON output changed: {output_digest}")
    return {
        "operation_count": iterations,
        "digest": output_digest,
        "input_digest": input_digest,
        "elapsed_seconds": elapsed,
        "records_per_operation": len(entries),
        "bytes_per_operation": len(payload),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=("catalog_json_export",))
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args(argv)
    if args.iterations < 1:
        parser.error("--iterations must be positive")
    try:
        result = catalog_json_export(args.iterations)
    except WorkloadError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
