"""Run one complete catalog task with installed import and cache checks."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

from benchmarks.workloads.catalog_url import catalog_url_normalize
from benchmarks.workloads.catalog_url_breadth import catalog_search_form
import urllib.parse


EXPECTED = {
    "catalog_search_form": "a56d64f19accb1be3bb302cc60f406928d15182828c2b7e975e957d503dc1f22",
    "catalog_url_normalize": "a6fedf33e0fd5e72b79af8d77499b9a7bb8e8d53491955f2e554570679e04941",
}


def identity(side: str) -> dict[str, object]:
    prefix = Path(sys.prefix).resolve()
    if prefix.name != side:
        raise RuntimeError(f"unexpected prefix: {prefix}")
    parser = prefix / "lib/python3.16/urllib/parse.py"
    cache = prefix / "lib/python3.16/urllib/__pycache__/parse.cpython-316.pyc"
    extension = prefix / "lib/python3.16/lib-dynload/_rust_url_quote.cpython-316-darwin.so"
    if Path(urllib.parse.__file__).resolve() != parser or Path(urllib.parse.__spec__.cached).resolve() != cache:
        raise RuntimeError("parser import escaped staged tree")
    if Path(urllib.parse._rust_url_quote.__file__).resolve() != extension:
        raise RuntimeError("extension import escaped staged tree")
    source = parser.read_bytes()
    bytecode = cache.read_bytes()
    if bytecode[:4] != importlib.util.MAGIC_NUMBER or int.from_bytes(bytecode[4:8], "little") != 3:
        raise RuntimeError("parser cache magic or checked-hash flags differ")
    if bytecode[8:16] != importlib.util.source_hash(source):
        raise RuntimeError("parser cache source hash is stale")
    return {
        "prefix": str(prefix),
        "parser_sha256": hashlib.sha256(source).hexdigest(),
        "cache_sha256": hashlib.sha256(bytecode).hexdigest(),
        "cache_source_hash": bytecode[8:16].hex(),
        "extension_sha256": hashlib.sha256(extension.read_bytes()).hexdigest(),
        "extension_bytes": extension.stat().st_size,
        "parser_bytes": parser.stat().st_size,
        "unquote_helper": hasattr(urllib.parse._rust_url_quote, "unquote_ascii"),
    }


def main() -> None:
    side, task, iterations_text = sys.argv[1:]
    iterations = int(iterations_text)
    details = identity(side)
    if details["unquote_helper"] != (side == "candidate"):
        raise RuntimeError("candidate helper presence mismatch")
    result = {"catalog_search_form": catalog_search_form,
              "catalog_url_normalize": catalog_url_normalize}[task](iterations)
    if result["digest"] != EXPECTED[task]:
        raise RuntimeError(f"public task digest changed: {result['digest']}")
    print(json.dumps({"side": side, "task": task, "identity": details, "result": result}, sort_keys=True))


if __name__ == "__main__":
    main()
