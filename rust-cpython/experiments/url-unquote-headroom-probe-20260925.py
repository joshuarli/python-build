"""Profile complete catalog URL tasks and classify their public unquote inputs."""

from __future__ import annotations

import argparse
import cProfile
import hashlib
import json
import pstats
import sys
from collections import Counter
from pathlib import Path
from urllib import parse
from urllib import request

from benchmarks.workloads.catalog_url import catalog_url_normalize
from benchmarks.workloads.catalog_url_breadth import catalog_search_form


TASKS = {"catalog_url_normalize": catalog_url_normalize,
         "catalog_search_form": catalog_search_form}
EXPECTED = {"catalog_url_normalize": "a6fedf33e0fd5e72b79af8d77499b9a7bb8e8d53491955f2e554570679e04941",
            "catalog_search_form": "a56d64f19accb1be3bb302cc60f406928d15182828c2b7e975e957d503dc1f22"}
INPUT = "7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f"


def identity() -> dict[str, str]:
    extension = Path(parse._rust_url_quote.__file__)
    parser = Path(parse.__file__)
    binary = Path(sys.executable)
    return {"executable": str(binary), "executable_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            "parser": str(parser), "parser_sha256": hashlib.sha256(parser.read_bytes()).hexdigest(),
            "extension": str(extension), "extension_sha256": hashlib.sha256(extension.read_bytes()).hexdigest()}


def checked(task: str, iterations: int) -> dict[str, int | float | str]:
    result = TASKS[task](iterations)
    if result["operation_count"] != iterations or result["input_digest"] != INPUT or result["digest"] != EXPECTED[task]:
        raise AssertionError(result)
    return result


def profile(task: str, iterations: int) -> dict[str, object]:
    profiler = cProfile.Profile()
    profiler.enable()
    result = checked(task, iterations)
    profiler.disable()
    stats = pstats.Stats(profiler)
    rows = [{"file": file, "line": line, "name": name, "primitive_calls": primitive,
             "calls": calls, "self_seconds": own, "cumulative_seconds": cumulative}
            for (file, line, name), (primitive, calls, own, cumulative, _) in stats.stats.items()]
    return {"mode": "profile", "task": task, "iterations": iterations, "identity": identity(),
            "result": result, "total_calls": stats.total_calls, "total_seconds": stats.total_tt,
            "rows": sorted(rows, key=lambda row: (row["file"], row["line"], row["name"]))}


def count(task: str) -> dict[str, object]:
    original = parse.unquote
    categories: Counter[str] = Counter()
    lengths: Counter[int] = Counter()
    escapes: Counter[int] = Counter()
    invalid: Counter[int] = Counter()

    def observed(string: str | bytes, encoding: str = "utf-8", errors: str = "replace") -> str:
        categories["all_public_calls"] += 1
        if type(string) is str:
            categories["exact_str"] += 1
            if type(encoding) is str and encoding == "utf-8" and type(errors) is str and errors == "replace":
                categories["default_codec_errors"] += 1
                if string.isascii():
                    categories["ascii"] += 1
                    if "%" in string:
                        categories["eligible"] += 1
                        lengths[len(string)] += 1
                        indices = [index for index, char in enumerate(string) if char == "%"]
                        escapes[len(indices)] += 1
                        bad = sum(index + 2 >= len(string) or
                                  string[index + 1] not in "0123456789ABCDEFabcdef" or
                                  string[index + 2] not in "0123456789ABCDEFabcdef"
                                  for index in indices)
                        invalid[bad] += 1
                    else:
                        categories["no_percent_fast_exit"] += 1
                else:
                    categories["non_ascii"] += 1
        return original(string, encoding, errors)

    request_original = request.unquote
    def observed_request(string: str | bytes, encoding: str = "utf-8", errors: str = "replace") -> str:
        categories["request_alias_calls"] += 1
        return observed(string, encoding, errors)

    parse.unquote = observed
    request.unquote = observed_request
    try:
        result = checked(task, 1)
    finally:
        parse.unquote = original
        request.unquote = request_original
    return {"mode": "count", "task": task, "iterations": 1, "identity": identity(),
            "result": result, "categories": dict(categories),
            "eligible_lengths": sorted(lengths.items()), "eligible_percent_counts": sorted(escapes.items()),
            "eligible_invalid_percent_counts": sorted(invalid.items())}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("profile", "count"))
    parser.add_argument("task", choices=tuple(TASKS))
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args()
    if args.iterations < 1 or (args.mode == "count" and args.iterations != 1):
        parser.error("count uses exactly one complete batch")
    report = profile(args.task, args.iterations) if args.mode == "profile" else count(args.task)
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
