"""Diagnostic of pinned CPython 3.16 unified_diff dispatch and mutation timing.

Run with rust-cpython/stage/bin/python3.16. This deliberately changes only
module objects in this process and restores them before exit.
"""

import contextlib
import difflib
import sys


@contextlib.contextmanager
def replaced(owner, name, value):
    old = getattr(owner, name)
    setattr(owner, name, value)
    try:
        yield
    finally:
        setattr(owner, name, old)


def diff(a, b, **kwargs):
    return difflib.unified_diff(a, b, lineterm="", **kwargs)


def main():
    assert sys.version_info[:2] == (3, 16), sys.version
    assert difflib.__file__.endswith("/lib/python3.16/difflib.py")

    # A generator call does not inspect even invalid inputs or module globals.
    gen = diff([b"bad"], ["ok"])
    with replaced(difflib, "SequenceMatcher", lambda *args: None):
        try:
            next(gen)
        except TypeError as exc:
            assert "lines to compare must be str" in str(exc)
        else:
            raise AssertionError("_check_types did not run at first next")
    events = []
    original_matcher = difflib.SequenceMatcher

    def matcher_factory(*args, **kwargs):
        events.append(("constructor", args[0], kwargs))
        return original_matcher(*args, **kwargs)

    gen = diff(["old\n"], ["new\n"])
    assert not events
    with replaced(difflib, "SequenceMatcher", matcher_factory):
        assert next(gen).startswith("--- ")
    assert events == [("constructor", None, {})], events
    print("lazy_creation_and_global_lookup", events)

    # The global Match and each relevant method are independently patchable.
    original_find = original_matcher.find_longest_match
    for name in ("get_grouped_opcodes", "get_opcodes",
                 "get_matching_blocks", "find_longest_match"):
        original = getattr(original_matcher, name)
        events.clear()

        def spy(self, *args, **kwargs):
            events.append(name)
            return original(self, *args, **kwargs)

        with replaced(original_matcher, name, spy):
            list(diff(["old\n"], ["new\n"]))
        assert name in events, (name, events)
        print("method_lookup", events)

    def bad_match(*args):
        raise RuntimeError("patched Match")

    gen = diff(["old\n"], ["new\n"])
    with replaced(difflib, "Match", bad_match):
        try:
            next(gen)
        except RuntimeError as exc:
            assert str(exc) == "patched Match"
        else:
            raise AssertionError("patched Match was not called")
    print("patched_Match", "RuntimeError at first next")

    # First-element type checking is weaker than exact-str eligibility.
    for a in (["ok", b"later"], ["ok", []]):
        gen = diff(a, ["ok", "later"])
        try:
            next(gen)
        except (TypeError, ValueError) as exc:
            print("mixed_element", type(exc).__name__, str(exc)[:80])
        else:
            print("mixed_element", "accepted until later rendering")

    # Mutations before first next affect matching; later ones affect rendering.
    a, b = ["old\n"], ["new\n"]
    gen = diff(a, b)
    a[0] = "new\n"
    assert list(gen) == []
    a, b = ["old\n"], ["new\n"]
    gen = diff(a, b)
    assert next(gen).startswith("--- ")
    a[0] = "changed after header\n"
    remaining = list(gen)
    assert "-changed after header\n" in remaining, remaining
    print("input_mutation", "pre-next changes matching; post-header changes rendering")

    # Trace callback runs inside the Python matching loop. A snapshot made
    # before that loop would retain X, but the current loop sees B at i=1.
    a, b = ["A\n", "X\n"], ["A\n", "B\n"]
    assert list(diff(a, b))
    changed = False
    code = original_find.__code__

    def trace(frame, event, arg):
        nonlocal changed
        if (not changed and event == "line" and frame.f_code is code
                and frame.f_lineno == 380 and frame.f_locals.get("i") == 1):
            a[1] = "B\n"
            changed = True
        return trace

    sys.settrace(trace)
    try:
        rendered = list(diff(a, b))
    finally:
        sys.settrace(None)
    assert changed and rendered == [], (changed, rendered)
    print("reentrant_mutation", "trace changed a[1] during match; no diff emitted")

    # unified_diff uses default isjunk=None and autojunk=True. Constructor
    # replacement is visible at the first next, even for exact tuple[str].
    tuples = (("same\n", "old\n"), ("same\n", "new\n"))
    calls = []

    def factory(isjunk, left, right, autojunk=True):
        calls.append((isjunk, autojunk, left is tuples[0], right is tuples[1]))
        return original_matcher(isjunk, left, right, autojunk=autojunk)

    gen = diff(*tuples)
    with replaced(difflib, "SequenceMatcher", factory):
        list(gen)
    assert calls == [(None, True, True, True)], calls
    print("constructor_options", calls)


if __name__ == "__main__":
    main()
