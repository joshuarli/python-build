"""Command-line parsing for offline catalog maintenance tasks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from catalog_service.adapters.filesystem import scan
from catalog_service.export import export_json
from catalog_service.index import InvertedIndex
from catalog_service.query import parse_query
from catalog_service.repository import CatalogRepository
from catalog_service.search import search


def build_parser() -> argparse.ArgumentParser:
    """Build CLI options with explicit subcommand requirements."""
    parser = argparse.ArgumentParser(prog="catalog-service")
    subcommands = parser.add_subparsers(dest="command", required=True)
    index_parser = subcommands.add_parser("index")
    index_parser.add_argument("root", type=Path)
    index_parser.add_argument("output", type=Path)
    search_parser = subcommands.add_parser("search")
    search_parser.add_argument("snapshot", type=Path)
    search_parser.add_argument("query")
    search_parser.add_argument("--limit", type=int, default=25)
    return parser


def run(arguments: Sequence[str] | None = None) -> int:
    """Execute one CLI command and return a process status code."""
    options = build_parser().parse_args(arguments)
    if options.command == "index":
        entries = scan(options.root)
        payload = export_json(entries)
        options.output.write_bytes(payload)
        return 0
    if options.command == "search":
        document = json.loads(options.snapshot.read_bytes())
        repository = CatalogRepository()
        with repository.transaction() as values:
            for item in document["entries"]:
                entry = __import__("catalog_service.codec", fromlist=["decode_entry"]).decode_entry(item)
                values[entry.identifier] = entry
        index = InvertedIndex()
        index.rebuild(repository.snapshot())
        page = search(repository, index, parse_query(options.query), limit=options.limit)
        sys.stdout.buffer.write(json.dumps({"total": page.total}).encode() + b"\n")
        return 0
    raise AssertionError(f"unhandled command: {options.command}")
