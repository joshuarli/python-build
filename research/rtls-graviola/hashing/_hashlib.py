import _operator
import _hashlib_graviola
import _md5
import _sha1
import _sha2
import _sha3
import _blake2


def _md5_sha1(data=b"", *, usedforsecurity=True):
    return _MD5SHA1(data, usedforsecurity=usedforsecurity)


class _MD5SHA1:
    name = "md5-sha1"
    digest_size = 36
    block_size = 64
    __slots__ = ("_md5", "_sha1")

    def __init__(self, data=b"", *, usedforsecurity=True):
        self._md5 = _md5.md5(data, usedforsecurity=usedforsecurity)
        self._sha1 = _sha1.sha1(data, usedforsecurity=usedforsecurity)

    def update(self, data):
        self._md5.update(data)
        self._sha1.update(data)

    def digest(self):
        return self._md5.digest() + self._sha1.digest()

    def hexdigest(self):
        return self._md5.hexdigest() + self._sha1.hexdigest()

    def copy(self):
        result = object.__new__(type(self))
        result._md5 = self._md5.copy()
        result._sha1 = self._sha1.copy()
        return result


def _rust_constructor(algorithm):
    def constructor(data=b"", *, usedforsecurity=True):
        return _hashlib_graviola.hash_new(algorithm, data)

    constructor.__name__ = "openssl_" + algorithm
    constructor.__module__ = __name__
    return constructor


_constructors = {
    "md5": _md5.md5,
    "md5-sha1": _md5_sha1,
    "sha1": _sha1.sha1,
    "sha224": _sha2.sha224,
    "sha256": _sha2.sha256,
    "sha384": _sha2.sha384,
    "sha512": _sha2.sha512,
    "sha512_224": _rust_constructor("sha512_224"),
    "sha512_256": _rust_constructor("sha512_256"),
    "blake2b": _blake2.blake2b,
    "blake2s": _blake2.blake2s,
    "sha3_224": _sha3.sha3_224,
    "sha3_256": _sha3.sha3_256,
    "sha3_384": _sha3.sha3_384,
    "sha3_512": _sha3.sha3_512,
    "shake_128": _sha3.shake_128,
    "shake_256": _sha3.shake_256,
    "ripemd160": _rust_constructor("ripemd160"),
    "sm3": _rust_constructor("sm3"),
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
    normalized_name = _normalize_digest_name(name)
    try:
        constructor = _constructors[normalized_name]
    except KeyError:
        raise UnsupportedDigestmodError(
            f"[digital envelope routines] unsupported hash algorithm {name}"
        ) from None
    if args:
        return constructor(args[0], **kwargs)
    if "data" in kwargs:
        data = kwargs.pop("data")
        return constructor(data, **kwargs)
    return constructor(**kwargs)


def _normalize_digest_name(name):
    normalized = name.lower()
    aliases = {
        "sha-1": "sha1",
        "sha-224": "sha224",
        "sha-256": "sha256",
        "sha-384": "sha384",
        "sha-512": "sha512",
        "sha512-224": "sha512_224",
        "sha512-256": "sha512_256",
        "sha3-224": "sha3_224",
        "sha3-256": "sha3_256",
        "sha3-384": "sha3_384",
        "sha3-512": "sha3_512",
        "shake-128": "shake_128",
        "shake-256": "shake_256",
        "ripemd-160": "ripemd160",
    }
    return aliases.get(normalized, normalized)


def hmac_new(key, msg=b"", digestmod=_MISSING):
    if digestmod is _MISSING:
        raise TypeError("Missing required argument 'digestmod'.")
    return _hashlib_graviola.hmac_new(key, msg, digestmod)
