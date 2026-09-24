"""Complete public difflib tasks over deterministic source-like revisions.

The digests pin both revisions and the complete emitted patch. Fixture setup
is outside the timed interval; each iteration formats and checks a full diff.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import sys
import time
from collections.abc import Callable


class WorkloadError(RuntimeError):
    """A difflib task changed its fixed input or emitted patch."""


def _digest(parts: tuple[tuple[str, bytes], ...]) -> str:
    digest = hashlib.sha256()
    for name, data in parts:
        encoded_name = name.encode("utf-8")
        digest.update(len(encoded_name).to_bytes(4, "big"))
        digest.update(encoded_name)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def _mostly_equal() -> tuple[list[str], list[str]]:
    before = [f"def handler_{index:04d}(value):\n" if index % 16 == 0
              else f"    return transform_{index % 17}(value, {index})\n"
              for index in range(512)]
    after = before.copy()
    for index in range(29, len(after), 53):
        after[index] = f"    return transform_{index % 17}(value + 1, {index})\n"
    after[177:177] = ["    # validate input before dispatch\n",
                       "    assert value is not None\n"]
    del after[361:364]
    return before, after


def _reordered_repetitive() -> tuple[list[str], list[str]]:
    # Repeated lines give SequenceMatcher many plausible anchors. Whole blocks
    # move, so this covers a different matching shape than isolated edits.
    blocks = [[f"def section_{section:02d}(item):\n"]
              + [f"    value = step_{index % 7}(item)\n" for index in range(31)]
              + [f"    return value + {section}\n"]
              for section in range(12)]
    before = [line for block in blocks for line in block]
    order = (0, 1, 5, 6, 2, 3, 4, 9, 10, 7, 8, 11)
    after = [line for section in order for line in blocks[section]]
    after[120] = "    value = step_3(item + 1)\n"
    return before, after


def _run(iterations: int, revisions: tuple[list[str], list[str]],
         expected_input: str, expected_output: str) -> dict[str, int | float | str]:
    before, after = revisions
    input_digest = _digest((("before", "".join(before).encode("utf-8")),
                            ("after", "".join(after).encode("utf-8"))))
    if input_digest != expected_input:
        raise WorkloadError(f"difflib fixture changed: {input_digest}")

    started = time.perf_counter()
    for _ in range(iterations):
        patch = "".join(difflib.unified_diff(
            before, after, fromfile="before.py", tofile="after.py", lineterm="\n"))
        output_digest = hashlib.sha256(patch.encode("utf-8")).hexdigest()
        if output_digest != expected_output:
            raise WorkloadError(f"unified_diff output changed: {output_digest}")
    elapsed = time.perf_counter() - started
    return {"operation_count": iterations, "digest": expected_output,
            "elapsed_seconds": elapsed, "input_digest": input_digest}


def difflib_unified_mostly_equal(iterations: int) -> dict[str, int | float | str]:
    """Produce a whole patch for sparse changes in a 512-line source file."""
    return _run(iterations, _mostly_equal(),
                "25b83537c564e95a74f38ae2a79a710f92c832660a7c7e9f660b4a3dee2fe842",
                "b5e86d88c7cad40f06a1ca79c7c2869a223315fdb30bdc7cd8940849414af2a3")


def difflib_unified_reordered(iterations: int) -> dict[str, int | float | str]:
    """Produce a whole patch for moved blocks with repeated source lines."""
    return _run(iterations, _reordered_repetitive(),
                "4534585365055d7f64ab4c2582f9dd14ae83bdd90055f920bdb7a35a7f0e20f3",
                "26585b44b4a4ced0dbb5f717454d1cbc7fd290ad798a767f0de0ecd41497f7c8")


_SCENARIOS: dict[str, Callable[[int], dict[str, int | float | str]]] = {
    "difflib_unified_mostly_equal": difflib_unified_mostly_equal,
    "difflib_unified_reordered": difflib_unified_reordered,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=sorted(_SCENARIOS))
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args(argv)
    if args.iterations < 1:
        parser.error("--iterations must be positive")
    try:
        result = _SCENARIOS[args.scenario](args.iterations)
    except WorkloadError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
