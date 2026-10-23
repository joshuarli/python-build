import inspect
import warnings

import _hashlib


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
        raise AssertionError((name, "accepted an unsigned signature parameter"))

print("hash and HMAC metadata is read-only; copies and constructor signatures match")
