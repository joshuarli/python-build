"""Ingest a pinned, mixed MIME mail archive with public stdlib email APIs.

One operation parses all selected source messages, indexes searchable headers and
parts, serializes each message, and checks the index after reparsing. Fixture
bytes come from the pinned Rust-for-CPython CPython 3.16 source test corpus.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from pathlib import Path


SOURCE_COMMIT = "b812b4a7b9efaca46b98544a8633b7d7e454166b"
SOURCE_ARCHIVE_SHA256 = "965dbc9c847b0ed779a16134495b8690c9fc957996d8bcbb83c47089d4e81467"
EXPECTED_OUTPUT_SHA256 = "e5faf8d7b11d84b98aef05bb543b77eecb8ae5324b13467bf0d6136b37572534"
FIXTURES = (
    ("msg_01.txt", "c15a3a17f6b65e9c51c58ed3a79d12bc517f867321ed118e5dc7b5c3a1ed7d4b"),
    ("msg_02.txt", "05d5e533f5e590d9ee2c7692d26dc87ccbf381f4831cca3362baf596691a55bb"),
    ("msg_05.txt", "845bca9a59de1959c1501cbc1f2c90fa9ab73a38653175fe94073c012fa555b1"),
    ("msg_06.txt", "0c4e8456a424135a4dda4829050de77b05c7fb56ef716841bdfe1371af2eb695"),
    ("msg_07.txt", "8358092b45c8631df6466a2e4dc23278263b2dd2ba5765e99caba47c304dd3b5"),
    ("msg_16.txt", "fbb4ae9e31ddd26e43b7c051041bb3d9d6bebd418a858da67268920bc672afb9"),
    ("msg_33.txt", "cc35e6cc84c00eb7d5e2bdf9ceb8977eb94c2bcc1630ea93c6c4b82381406dad"),
    ("msg_40.txt", "d59f6e422b9ad6163924bc1fb70ae8b697a11282d5b32b02708b40cb9a7d82ee"),
    ("msg_43.txt", "045797ff45987136a2a5712f8f8310710e0944e4b4547bab2dc99933edd1bc9a"),
    ("msg_45.txt", "b98e4e0c90037146f2b5d3cbb9e43cb419f36385cfd7a4567fd509ef00ec53cb"),
    ("msg_46.txt", "d92e941be30507b7dd5976f4223f9d01998f1e73262e900e0ed002b0f53dc4b7"),
)


def _digest_json(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     separators=(",", ":")).encode("ascii")).hexdigest()


def _index(message, name: str) -> dict[str, object]:
    parts = []
    for part in message.walk():
        payload = part.get_payload(decode=True)
        parts.append({
            "type": part.get_content_type(),
            "disposition": part.get_content_disposition(),
            "filename": part.get_filename(),
            "charset": part.get_content_charset(),
            "bytes": len(payload) if payload is not None else None,
            "content_sha256": hashlib.sha256(payload).hexdigest() if payload is not None else None,
            "defects": [type(defect).__name__ for defect in part.defects],
        })
    return {
        "file": name,
        "subject": str(message.get("subject", "")),
        "from": getaddresses(message.get_all("from", [])),
        "to": getaddresses(message.get_all("to", [])),
        "date": str(message.get("date", "")),
        "message_id": str(message.get("message-id", "")),
        "parts": parts,
    }


def _archive_digest(fixtures: tuple[tuple[str, bytes], ...]) -> tuple[str, int, int]:
    parser = BytesParser(policy=policy.default)
    records = []
    total_parts = 0
    serialized_bytes = 0
    for name, raw in fixtures:
        message = parser.parsebytes(raw)
        record = _index(message, name)
        serialized = message.as_bytes(policy=policy.default)
        if _index(parser.parsebytes(serialized), name) != record:
            raise ValueError(f"serialization changed archive index: {name}")
        record["serialized_sha256"] = hashlib.sha256(serialized).hexdigest()
        total_parts += len(record["parts"])
        serialized_bytes += len(serialized)
        records.append(record)
    return _digest_json(records), total_parts, serialized_bytes


def run(fixture_root: Path, iterations: int) -> dict[str, object]:
    if iterations < 1:
        raise ValueError("iterations must be positive")
    fixtures = []
    for name, expected in FIXTURES:
        raw = (fixture_root / name).read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected:
            raise ValueError(f"fixture {name} SHA-256 {actual} != {expected}")
        fixtures.append((name, raw))
    frozen = tuple(fixtures)
    started = time.perf_counter()
    for _ in range(iterations):
        output_digest, parts, serialized_bytes = _archive_digest(frozen)
        if output_digest != EXPECTED_OUTPUT_SHA256:
            raise ValueError(f"archive index changed: {output_digest}")
    elapsed = time.perf_counter() - started
    return {
        "operation_count": iterations,
        "digest": output_digest,
        "elapsed_seconds": elapsed,
        "messages_per_operation": len(frozen),
        "parts_per_operation": parts,
        "input_bytes_per_operation": sum(len(raw) for _, raw in frozen),
        "serialized_bytes_per_operation": serialized_bytes,
        "source_commit": SOURCE_COMMIT,
        "source_archive_sha256": SOURCE_ARCHIVE_SHA256,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-root", type=Path, default=Path(sys.prefix) /
                        "lib/python3.16/test/test_email/data")
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--profile", action="store_true",
                        help="include one process CPU, peak RSS, and cProfile diagnostic")
    args = parser.parse_args(argv)
    try:
        if args.profile:
            import cProfile
            import os
            import pstats
            import resource

            profiler = cProfile.Profile()
            before = resource.getrusage(resource.RUSAGE_SELF)
            load = os.getloadavg()
            started = time.perf_counter()
            profiler.enable()
            result = run(args.fixture_root, args.iterations)
            profiler.disable()
            after = resource.getrusage(resource.RUSAGE_SELF)
            stats = pstats.Stats(profiler)
            hot = sorted(stats.stats.items(), key=lambda row: row[1][3], reverse=True)[:12]
            result["diagnostic"] = {
                "process_wall_seconds": time.perf_counter() - started,
                "user_cpu_seconds": after.ru_utime - before.ru_utime,
                "system_cpu_seconds": after.ru_stime - before.ru_stime,
                "peak_rss_bytes": after.ru_maxrss,
                "load_average_before": load,
                "profile_calls": stats.total_calls,
                "top_cumulative": [
                    {"file": Path(key[0]).name, "function": key[2],
                     "calls": value[0], "self_seconds": value[2],
                     "cumulative_seconds": value[3]}
                    for key, value in hot
                ],
            }
        else:
            result = run(args.fixture_root, args.iterations)
    except (OSError, ValueError) as error:
        parser.exit(2, f"email archive workload: {error}\n")
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
