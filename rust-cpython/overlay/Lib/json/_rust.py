"""Internal dispatch for complete JSON documents handled by the Rust codec."""

try:
    import _json_rs
except ImportError:
    _json_rs = None


def _supported(value):
    """Check the exact built-in values accepted by the Rust conversion."""
    if _json_rs is None:
        return False
    pending = [value]
    seen = set()
    while pending:
        current = pending.pop()
        value_type = type(current)
        if value_type in (str, int, float, bool, type(None)):
            continue
        if value_type in (list, tuple):
            marker = id(current)
            if marker in seen:
                return False
            seen.add(marker)
            pending.extend(current)
            continue
        if value_type is dict:
            marker = id(current)
            if marker in seen or any(type(key) is not str for key in current):
                return False
            seen.add(marker)
            pending.extend(current.values())
            continue
        return False
    return True


def dumps(value):
    if _supported(value):
        return _json_rs.dumps(value)
    return None


def loads(document):
    if _json_rs is None:
        return False, None
    return _json_rs.loads(document)
