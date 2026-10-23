import _operator
import _hashlib_graviola
import _md5
import _sha1
import _sha2
import _sha3
import _blake2


_constructors = {
    "md5": _md5.md5,
    "sha1": _sha1.sha1,
    "sha224": _sha2.sha224,
    "sha256": _sha2.sha256,
    "sha384": _sha2.sha384,
    "sha512": _sha2.sha512,
    "blake2b": _blake2.blake2b,
    "blake2s": _blake2.blake2s,
    "sha3_224": _sha3.sha3_224,
    "sha3_256": _sha3.sha3_256,
    "sha3_384": _sha3.sha3_384,
    "sha3_512": _sha3.sha3_512,
    "shake_128": _sha3.shake_128,
    "shake_256": _sha3.shake_256,
}
_MISSING = object()

openssl_md_meth_names = frozenset(_constructors)
algorithms_available = openssl_md_meth_names
_GIL_MINSIZE = 2048
HMAC = _hashlib_graviola.HMAC
UnsupportedDigestmodError = _hashlib_graviola.UnsupportedDigestmodError
compare_digest = _operator._compare_digest
hmac_digest = _hashlib_graviola.hmac_digest
pbkdf2_hmac = _hashlib_graviola.pbkdf2_hmac
scrypt = _hashlib_graviola.scrypt

for _name, _constructor in _constructors.items():
    globals()["openssl_" + _name] = _constructor


def new(name, *args, **kwargs):
    if len(args) > 1:
        raise TypeError(f"new() takes at most 2 positional arguments but {len(args) + 1} were given")
    if "data" in kwargs and args:
        raise TypeError("new() got multiple values for argument given by name ('data') and position")
    if not isinstance(name, str):
        raise TypeError(f"new() argument 'name' must be str, not {type(name).__name__}")
    normalized_name = name.lower().replace("-", "_")
    try:
        constructor = _constructors[normalized_name]
    except KeyError:
        raise ValueError(f"unsupported hash type {name}") from None
    if args:
        return constructor(args[0], **kwargs)
    if "data" in kwargs:
        data = kwargs.pop("data")
        return constructor(data, **kwargs)
    return constructor(**kwargs)


def hmac_new(key, msg=b"", digestmod=_MISSING):
    if digestmod is _MISSING:
        raise TypeError("Missing required argument 'digestmod'.")
    return _hashlib_graviola.hmac_new(key, msg, digestmod)
