"""Disjoint phase and self-time diagnostic for the pinned email archive workload."""

import argparse
import cProfile
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pstats
import resource
import sys
import time

from email import policy
from email.parser import BytesParser

WORKLOAD_PATH = Path(__file__).with_name("email-workload-20260925.py")
EXPECTED_WORKLOAD_SHA256 = "9a0ab388d856435b29ab0fbdc0b73617de90ffc470e7ff4a746fc80d641a8792"
EXPECTED_INTERPRETER_SHA256 = "6eeeb64b9eb161d4d5edb9200e79146dabd8acc0f73fcdca48417d0e3c9531bd"
EXPECTED_SOURCE_LOCK_SHA256 = "7417c031b6ef4bc1a54963bad20455173c1be40bb51927bc523448dbacdcece9"
SOURCE_LOCK_PATH = Path(__file__).parents[1] / "sources.lock.json"
PHASES = ("original_parse", "original_index", "serialize", "serialized_reparse", "serialized_index")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _workload():
    spec = importlib.util.spec_from_file_location("pinned_email_workload", WORKLOAD_PATH)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load pinned workload")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _original_parse(parser, raw):
    return parser.parsebytes(raw)


def _original_index(workload, message, name):
    return workload._index(message, name)


def _serialize(message):
    return message.as_bytes(policy=policy.default)


def _serialized_reparse(parser, serialized):
    return parser.parsebytes(serialized)


def _serialized_index(workload, message, name):
    return workload._index(message, name)


def _phase_call(phases, profilers, index, function, *args):
    started = time.perf_counter()
    if profilers is None:
        result = function(*args)
    else:
        result = profilers[index].runcall(function, *args)
    phases[index] += time.perf_counter() - started
    return result


def _archive(phases, profilers, workload, fixtures):
    parser = BytesParser(policy=policy.default)
    records = []
    total_parts = 0
    serialized_bytes = 0
    for name, raw in fixtures:
        message = _phase_call(phases, profilers, 0, _original_parse, parser, raw)
        record = _phase_call(phases, profilers, 1, _original_index, workload, message, name)
        serialized = _phase_call(phases, profilers, 2, _serialize, message)
        reparsed_message = _phase_call(phases, profilers, 3, _serialized_reparse, parser, serialized)
        reparsed_record = _phase_call(phases, profilers, 4, _serialized_index,
                                      workload, reparsed_message, name)
        if reparsed_record != record:
            raise ValueError(f"serialization changed archive index: {name}")
        record["serialized_sha256"] = hashlib.sha256(serialized).hexdigest()
        total_parts += len(record["parts"])
        serialized_bytes += len(serialized)
        records.append(record)
    return workload._digest_json(records), total_parts, serialized_bytes


def _profile_stats(profiler):
    stats = pstats.Stats(profiler)
    rows = []
    groups = {}
    for (filename, line, function), (primitive, calls, self_time, cumulative, callers) in stats.stats.items():
        basename = Path(filename).name
        if basename in ("_header_value_parser.py", "headerregistry.py", "policy.py", "message.py",
                        "feedparser.py", "generator.py", "parser.py", "email-header-headroom-20260925.py",
                        "email-workload-20260925.py"):
            group = basename
        elif filename.startswith("~"):
            group = "builtins_and_c_calls"
        else:
            group = "other_python"
        groups[group] = groups.get(group, 0.0) + self_time
        rows.append({"file": basename, "line": line, "function": function,
                     "calls": calls, "self_seconds": self_time, "cumulative_seconds": cumulative})
    header_rows = sorted((row for row in rows if row["file"] == "_header_value_parser.py"),
                         key=lambda row: row["self_seconds"], reverse=True)
    lexical_helpers = {"_get_ptext_to_endchars", "get_fws", "get_ttext"}
    return {"total_calls": stats.total_calls, "total_self_seconds": stats.total_tt,
            "self_seconds_by_source": groups,
            "header_value_parser_top_self": header_rows[:15],
            "selected_lexical_helper_self_seconds": sum(
                row["self_seconds"] for row in header_rows if row["function"] in lexical_helpers),
            "top_self": sorted(rows, key=lambda row: row["self_seconds"], reverse=True)[:20]}


def main():
    argparser = argparse.ArgumentParser(description=__doc__)
    argparser.add_argument("--fixture-root", type=Path,
                           default=Path(sys.prefix) / "lib/python3.16/test/test_email/data")
    argparser.add_argument("--iterations", type=int, default=5)
    argparser.add_argument("--profile", action="store_true")
    args = argparser.parse_args()
    if args.iterations < 1:
        argparser.error("iterations must be positive")
    identity = {"interpreter_sha256": _sha256(Path(sys.executable)),
                "workload_sha256": _sha256(WORKLOAD_PATH),
                "source_lock_sha256": _sha256(SOURCE_LOCK_PATH)}
    expected = {"interpreter_sha256": EXPECTED_INTERPRETER_SHA256,
                "workload_sha256": EXPECTED_WORKLOAD_SHA256,
                "source_lock_sha256": EXPECTED_SOURCE_LOCK_SHA256}
    if identity != expected:
        argparser.error(f"pinned identity changed: {identity}")
    workload = _workload()
    fixtures = []
    for name, expected_digest in workload.FIXTURES:
        raw = (args.fixture_root / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_digest:
            argparser.error(f"fixture digest changed: {name}")
        fixtures.append((name, raw))
    fixtures = tuple(fixtures)
    phases = [0.0] * len(PHASES)
    profilers = [cProfile.Profile() for _ in PHASES] if args.profile else None
    before = resource.getrusage(resource.RUSAGE_SELF)
    load_before = os.getloadavg()
    started = time.perf_counter()
    for _ in range(args.iterations):
        digest, parts, serialized_bytes = _archive(phases, profilers, workload, fixtures)
        if digest != workload.EXPECTED_OUTPUT_SHA256:
            raise ValueError(f"archive index changed: {digest}")
    elapsed = time.perf_counter() - started
    after = resource.getrusage(resource.RUSAGE_SELF)
    result = {"identity": identity, "source_commit": workload.SOURCE_COMMIT,
              "source_archive_sha256": workload.SOURCE_ARCHIVE_SHA256,
              "fixture_sha256": dict(workload.FIXTURES), "output_digest": digest,
              "operation_count": args.iterations, "messages_per_operation": len(fixtures),
              "parts_per_operation": parts, "input_bytes_per_operation": sum(len(raw) for _, raw in fixtures),
              "serialized_bytes_per_operation": serialized_bytes,
              "mode": "per_phase_cprofile" if args.profile else "plain_phase_timer",
              "wall_seconds": elapsed, "user_cpu_seconds": after.ru_utime - before.ru_utime,
              "system_cpu_seconds": after.ru_stime - before.ru_stime,
              "peak_rss_bytes": after.ru_maxrss, "load_average_before": load_before,
              "phase_wall_seconds": dict(zip(PHASES, phases))}
    if profilers is not None:
        result["profile_by_phase"] = {phase: _profile_stats(profiler)
                                      for phase, profiler in zip(PHASES, profilers)}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
