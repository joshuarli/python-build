import _hashlib
import hashlib
import inspect
import warnings


def check_readonly(value, type_name):
    original = {
        name: getattr(value, name)
        for name in ("name", "digest_size", "block_size")
    }
    for name, current in original.items():
        message = f"attribute '{name}' of '_hashlib.{type_name}' objects is not writable"
        try:
            setattr(value, name, "changed")
        except AttributeError as error:
            if str(error) != message:
                raise AssertionError((name, "set", str(error))) from None
        else:
            raise AssertionError((name, "set", "accepted"))
        try:
            delattr(value, name)
        except AttributeError as error:
            if str(error) != message:
                raise AssertionError((name, "delete", str(error))) from None
        else:
            raise AssertionError((name, "delete", "accepted"))
        if getattr(value, name) != current:
            raise AssertionError((name, "metadata changed"))


for algorithm in ("sm3", "sha512_256"):
    original = _hashlib.new(algorithm, b"prefix")
    check_readonly(original, "HASH")
    copied = original.copy()
    if copied.name != original.name or copied.digest() != original.digest():
        raise AssertionError((algorithm, "copy did not preserve state"))
    copied.update(b"-copy")
    if copied.digest() == original.digest():
        raise AssertionError((algorithm, "copy shared mutable state"))

hmac = _hashlib.hmac_new(b"key", b"prefix", "sha256")
check_readonly(hmac, "HMAC")
hmac_copy = hmac.copy()
if hmac_copy.name != hmac.name or hmac_copy.digest() != hmac.digest():
    raise AssertionError("HMAC copy did not preserve state")
hmac_copy.update(b"-copy")
if hmac_copy.digest() == hmac.digest():
    raise AssertionError("HMAC copy shared mutable state")

import copy
import pickle

for algorithm in ("ripemd160", "sm3"):
    rust_hash = _hashlib.new(algorithm, b"a")
    for refuse in (copy.copy, copy.deepcopy, pickle.dumps):
        try:
            refuse(rust_hash)
        except TypeError:
            pass
        else:
            raise AssertionError((algorithm, refuse.__name__, "accepted"))
for refuse in (copy.copy, copy.deepcopy, pickle.dumps):
    try:
        refuse(hmac)
    except TypeError:
        pass
    else:
        raise AssertionError(("HMAC", refuse.__name__, "accepted"))

def lookalike_sha256(*args):
    raise RuntimeError("must not be called")

for impostor in (lookalike_sha256, hashlib.sha256(), hashlib.new("sha256")):
    try:
        _hashlib.hmac_new(b"key", b"msg", impostor)
    except _hashlib.UnsupportedDigestmodError:
        pass
    else:
        raise AssertionError(("digestmod identity", "accepted", repr(impostor)))
if _hashlib.hmac_new(b"key", b"msg", _hashlib.openssl_sha256).digest() != _hashlib.hmac_new(
    b"key", b"msg", "sha256"
).digest():
    raise AssertionError("openssl_sha256 digestmod disagrees with its name")

with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    keyword = _hashlib.new("ripemd160", string=b"x")
if keyword.digest() != _hashlib.new("ripemd160", b"x").digest() or not any(
    issubclass(item.category, DeprecationWarning) for item in caught
):
    raise AssertionError("string= keyword not honored with a DeprecationWarning")
try:
    _hashlib.new("ripemd160", b"a", string=b"b")
except TypeError:
    pass
else:
    raise AssertionError("data and string accepted together")

expected_signature = inspect.Signature(
    (
        inspect.Parameter("data", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=b""),
        inspect.Parameter("usedforsecurity", inspect.Parameter.KEYWORD_ONLY, default=True),
        inspect.Parameter("string", inspect.Parameter.KEYWORD_ONLY, default=None),
    )
)
for name in (
    "md5",
    "sha1",
    "sha224",
    "sha256",
    "sha384",
    "sha512",
    "sha3_224",
    "sha3_256",
    "sha3_384",
    "sha3_512",
    "shake_128",
    "shake_256",
):
    constructor = getattr(_hashlib, "openssl_" + name)
    if inspect.signature(constructor) != expected_signature:
        raise AssertionError((name, inspect.signature(constructor)))
    for keyword, value in (
        ("data", b"data"),
        ("usedforsecurity", False),
        ("string", b"string"),
    ):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            constructor(**{keyword: value})
    try:
        constructor(unaccepted_keyword=True)
    except TypeError:
        pass
    else:
        raise AssertionError((name, "accepted an undeclared keyword"))


class TruthValue:
    def __init__(self, raises=False):
        self.calls = 0
        self.raises = raises

    def __bool__(self):
        self.calls += 1
        if self.raises:
            raise RuntimeError("truth-value called")
        return False


for api in (_hashlib.new, hashlib.new):
    for algorithm in ("sha512_224", "sha512_256", "ripemd160", "sm3", "md5-sha1"):
        value = TruthValue()
        api(algorithm, usedforsecurity=value)
        if value.calls != 1:
            raise AssertionError((api.__module__, algorithm, value.calls))

        value = TruthValue(raises=True)
        try:
            api(algorithm, usedforsecurity=value)
        except RuntimeError as error:
            if str(error) != "truth-value called":
                raise AssertionError((api.__module__, algorithm, str(error))) from None
        else:
            raise AssertionError((api.__module__, algorithm, "accepted raising truth value"))
        if value.calls != 1:
            raise AssertionError((api.__module__, algorithm, value.calls))

    value = TruthValue()
    try:
        api("unsupported-hash-name", usedforsecurity=value)
    except ValueError:
        pass
    else:
        raise AssertionError((api.__module__, "accepted an unsupported hash name"))
    if value.calls != 1:
        raise AssertionError((api.__module__, "unsupported name", value.calls))

    value = TruthValue(raises=True)
    try:
        api("unsupported-hash-name", usedforsecurity=value)
    except RuntimeError as error:
        if str(error) != "truth-value called":
            raise AssertionError((api.__module__, "unsupported name", str(error))) from None
    else:
        raise AssertionError((api.__module__, "unsupported name", "truth value was ignored"))
    if value.calls != 1:
        raise AssertionError((api.__module__, "unsupported name", value.calls))

print("hash constructors preserve readonly metadata, copy state, signatures, and security coercion")
