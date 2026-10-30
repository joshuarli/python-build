"""Locale-ignorecase negated-set differential: lane vs pristine.

U8 acceptance probe. Upstream python/cpython commit 6671d27327dd
(GH-156445, fixing gh-156444) rewrote SRE(charset_loc_ignore) in
Modules/_sre/sre_lib.h: the old code tested the whole set once per
locale case and took the disjunction, which complements a set before
closing it under case instead of after, so both [bc] and [^bc]
matched b'B'. The backported overlay shadows only that function; this
probe asserts the fixed behavior matches pristine 3.16.0a1+ case for
case. Run:

    python3 rust-cpython/tests/parity_re_locale.py \
        --lane <lane stage python> --pristine <pristine python>

Exit 0 when every case agrees, 1 otherwise.
"""

from __future__ import annotations

import argparse
import os
import subprocess


def build_cases():
    import re

    IL = re.LOCALE | re.IGNORECASE
    return [
        # (pattern, subject, flags, expected_match)
        (rb"[bc]", b"B", IL, True),
        (rb"[^bc]", b"B", IL, False),
        (rb"[^b-c]", b"C", IL, False),
        (rb"[^bc]", b"c", IL, False),
        (rb"[^bc]", b"a", IL, True),
        (rb"[^b]", b"B", IL, False),
        (rb"[^b]", b"a", IL, True),
        (rb"[^\wq]", b"Q", IL, False),
        (rb"[ace]", b"C", IL, True),
        (rb"[^ace]", b"C", IL, False),
        (rb"[^ace]", b"b", IL, True),
        (rb"(?:a|[^bc])", b"B", IL, False),
        (rb"(?:a|[^bc])", b"A", IL, True),
        (rb"\w(?<!b)", b"B", IL, False),
        (rb"\w(?<!b)", b"A", IL, True),
    ]


def emit():
    import re

    lines = []
    for pattern, subject, flags, _ in build_cases():
        try:
            hit = re.fullmatch(pattern, subject, flags) is not None
        except Exception as exc:  # noqa: BLE001
            lines.append(f"{pattern!r} ERROR:{type(exc).__name__}")
        else:
            lines.append(f"{pattern!r} {subject!r} {hit}")
    for line in lines:
        print(line)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emit", action="store_true")
    parser.add_argument("--lane")
    parser.add_argument("--pristine")
    args = parser.parse_args(argv)
    if args.emit:
        emit()
        return 0
    if not args.lane or not args.pristine:
        parser.error("--lane and --pristine are required (or --emit)")
    env = {**os.environ, "PYTHONHASHSEED": "0"}
    outs = {}
    for label, python in (("lane", args.lane), ("pristine", args.pristine)):
        result = subprocess.run(
            [python, __file__, "--emit"],
            capture_output=True,
            text=True,
            env=env,
            timeout=600,
            check=False,
        )
        if result.returncode != 0:
            print(f"{label} emit failed:\n{result.stderr}")
            return 1
        outs[label] = result.stdout.splitlines()
    lane_lines, pristine_lines = outs["lane"], outs["pristine"]
    if len(lane_lines) != len(pristine_lines):
        print("line count differs")
        return 1
    failures = 0
    for lane_line, pristine_line in zip(lane_lines, pristine_lines):
        if lane_line != pristine_line:
            failures += 1
            print(f"MISMATCH:\n  lane:     {lane_line}\n  pristine:  {pristine_line}")
    expected = {(f"{p!r} {s!r} {e}") for p, s, _, e in build_cases()}
    for line in lane_lines:
        if line not in expected and "ERROR" not in line:
            failures += 1
            print(f"UNEXPECTED lane result (differs from fixed behavior): {line}")
    if failures:
        print(f"{failures} mismatches")
        return 1
    print(f"OK {len(lane_lines)} cases identical to pristine, all fixed behavior")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
