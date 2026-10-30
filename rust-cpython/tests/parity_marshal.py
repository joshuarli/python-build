"""Byte-identity differential for marshal output: lane vs pristine.

U1 acceptance probe. Every corpus case must serialize to identical bytes
under the lane interpreter and the pristine 3.16.0a1+ interpreter, because
upstream 3.16 reference tagging depends only on the object graph, never on
ambient reference counts. Run:

    python3 rust-cpython/tests/parity_marshal.py \
        --lane <lane stage python> --pristine <pristine python>

Both children run with PYTHONHASHSEED=0 so mapping order cannot differ.
Exit 0 when every case matches byte for byte, 1 otherwise.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys


def build_cases():
    cases = {}

    shared_list = [1, 2, 3]
    cases["shared-list-twice"] = (shared_list, shared_list)

    shared_dict = {"a": 1, "b": [2]}
    cases["shared-dict-twice"] = {"x": shared_dict, "y": shared_dict}

    cases["small-int-thrice"] = (7, 7, 7)

    # High ambient refcount, single occurrence: must NOT be flagged.
    anchor = [7] * 100
    cases["ambient-int-single"] = ((7,), len(anchor))

    interned = sys.intern("shared_name")
    cases["interned-twice"] = (interned, interned)
    cases["interned-single"] = ("unique_string_xyz",)

    code = compile("def f():\n    return (1, 'a')", "<t>", "exec")
    cases["code-twice"] = (code, code)
    cases["code-single"] = (compile("x = 1", "<t>", "exec"),)

    probe = [1.5, complex(1.0, 2.0), b"xy", None, True]
    cases["scalars"] = (probe, probe)

    big = 2**100 + 12345
    cases["big-int-twice"] = (big, big)

    uni = "héllo wörld \U0001f600"
    cases["unicode-twice"] = (uni, uni)

    sub = ("a", 1)
    cases["frozenset-shared"] = (
        frozenset([sub, (2, 3)]),
        frozenset([(2, 3), sub]),
    )

    nested = {"k": [shared_list, shared_dict, (sub, sub)]}
    cases["nested"] = (nested, nested)

    return cases


def emit():
    import marshal

    assert marshal.version >= 6, marshal.version
    lines = []
    for name in sorted(build_cases()):
        graph = build_cases()[name]
        try:
            blob = marshal.dumps(graph)
        except Exception as exc:  # noqa: BLE001
            lines.append(f"{name} ERROR:{type(exc).__name__}")
        else:
            lines.append(f"{name} {blob.hex()}")
    # Stability: re-dump after churning ambient references; bytes must not
    # move when unrelated objects are created and dropped.
    junk = [{"i": i} for i in range(5000)]
    del junk
    again = []
    for name in sorted(build_cases()):
        graph = build_cases()[name]
        try:
            blob = marshal.dumps(graph)
        except Exception as exc:  # noqa: BLE001
            again.append(f"{name} ERROR:{type(exc).__name__}")
        else:
            again.append(f"{name} {blob.hex()}")
    if again != lines:
        print("UNSTABLE")
    for line in lines:
        print(line)


def cycle_probe(python):
    code = (
        "import marshal; t = ([],); t[0].append(t); "
        "marshal.dumps(t)"
    )
    result = subprocess.run(
        [python, "-c", code],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONHASHSEED": "0"},
        timeout=120,
        check=False,
    )
    return result.returncode, result.stderr.strip().splitlines()[-1] if result.stderr else ""


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
    if "UNSTABLE" in lane_lines:
        print("lane output is not self-stable across ambient churn")
        return 1
    if "UNSTABLE" in pristine_lines:
        print("pristine output is not self-stable across ambient churn")
        return 1
    failures = 0
    for lane_line, pristine_line in zip(lane_lines, pristine_lines):
        if lane_line != pristine_line:
            failures += 1
            name = lane_line.split(" ", 1)[0]
            print(f"MISMATCH {name}:")
            print(f"  lane:     {lane_line.split(' ', 1)[1][:120]}")
            print(f"  pristine:  {pristine_line.split(' ', 1)[1][:120]}")
    if len(lane_lines) != len(pristine_lines):
        print("line count differs")
        return 1
    lane_cycles = cycle_probe(args.lane)
    pristine_cycles = cycle_probe(args.pristine)
    # Known fork-vs-a1 divergence (U1 follow-up): pristine raises ValueError
    # on tuple cycles; the lane round-trips them through the C fallback
    # writer, matching the fork's test_reference_loop_tuple. Recorded here,
    # resolved by the source rebase, not by U1.
    if "ValueError" not in pristine_cycles[1]:
        print(f"pristine must raise ValueError: pristine={pristine_cycles}")
        return 1
    if lane_cycles[0] == 0:
        print(f"NOTE cycle-divergence: lane round-trips tuple cycle "
              f"(fork behavior); pristine raises "
              f"({pristine_cycles[1].strip()})")
    elif "ValueError" not in lane_cycles[1]:
        print(f"lane cycle probe failed unexpectedly: lane={lane_cycles}")
        return 1
    if failures:
        print(f"{failures} byte mismatches")
        return 1
    print(f"OK {len(lane_lines)} cases byte-identical (cycle behavior noted above)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
