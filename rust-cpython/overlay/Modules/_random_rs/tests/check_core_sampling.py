"""Observe callback ordering, owned results, errors and public native sampling."""
import gc
import random
import weakref
import _random_rs as native


def main():
    bounds = []
    def first(upper):
        bounds.append(upper)
        return 0
    pool = list("abcd")
    result = [None] * 3
    assert native.sample_pool(pool, result, range(3), 4, first) is result
    assert result == list("adc") and bounds == [4, 3, 2]
    selected = set()
    draws = iter([0, 0, 2])
    result = [None] * 2
    assert native.sample_selected(list("abcd"), selected, selected.add,
                                  result, range(2), 4, lambda upper: next(draws)) is result
    assert result == list("ac") and selected == {0, 2}
    class Item:
        pass
    item = Item()
    owner = weakref.ref(item)
    sequence = [item]
    held = native.choice(sequence, lambda upper: 0)
    del item, sequence
    gc.collect()
    assert owner() is held
    del held
    gc.collect()
    assert owner() is None
    failure = RuntimeError("callback failure")
    def fails(upper):
        raise failure
    try:
        native.choice([1], fails)
    except RuntimeError as error:
        assert error is failure
    else:
        raise AssertionError("callback error lost")
    def reenters(upper):
        assert native.choice([7], lambda size: 0) == 7
        return 0
    assert native.choice([9], reenters) == 9
    try:
        native.choice([], first)
    except IndexError as error:
        assert str(error) == "Cannot choose from an empty sequence"
    else:
        raise AssertionError("empty choice accepted")
    original = {name: getattr(native, name) for name in
                ("choice", "sample_pool", "sample_selected")}
    calls = []
    for name, method in original.items():
        def trace(*args, _name=name, _method=method):
            calls.append(_name)
            return _method(*args)
        setattr(native, name, trace)
    try:
        generator = random.Random(12345)
        state = generator.getstate()
        assert generator.choice([11]) == 11
        assert len(generator.sample(list(range(4)), 3)) == 3
        assert len(generator.sample(range(10000), 2)) == 2
        assert calls == ["choice", "sample_pool", "sample_selected"]
        generator.setstate(state)
        assert generator.choice([11]) == 11
    finally:
        for name, method in original.items():
            setattr(native, name, method)
    print("OK core sampling callback order, ownership, errors, reentry and public Rust routes")


if __name__ == "__main__":
    main()
