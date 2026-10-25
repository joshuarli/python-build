import _operator
import inspect
import warnings
import _hashlib_rs
import _hmac_rs
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
        usedforsecurity = bool(usedforsecurity)
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


_RUST_ALGORITHMS = frozenset({
    "md5",
    "sha1",
    "sha224",
    "sha256",
    "sha384",
    "sha512",
    "sha512_224",
    "sha512_256",
    "sha3_224",
    "sha3_256",
    "sha3_384",
    "sha3_512",
    "ripemd160",
    "sm3",
})

_CONFLICT_MESSAGE = (
    "'data' and 'string' are mutually exclusive and support for 'string' "
    "keyword parameter is slated for removal in a future version."
)
_DEPRECATED_STRING_MESSAGE = (
    "the 'string' keyword parameter is deprecated since Python 3.15 and slated "
    "for removal in Python 3.19; use the 'data' keyword parameter or pass the "
    "data to hash as a positional argument instead"
)
_ALLOWED_KEYWORDS = frozenset({"data", "string", "usedforsecurity"})


def _clinic_parse(qualname, args, kwargs, *, positional_count):
    """Mirror CPython's clinic argument handling for hash constructors.

    Returns (data, usedforsecurity). Raises TypeError with the exact
    messages CPython's Argument Clinic emits, including the deprecated
    `string` keyword path with its DeprecationWarning.
    """
    if len(args) > 1:
        raise TypeError(
            f"{qualname}() takes at most 1 positional argument ({len(args)} given)"
        )
    if args and "data" in kwargs:
        raise TypeError(
            f"argument for {qualname}() given by name ('data') and position ({positional_count})"
        )
    for keyword in kwargs:
        if keyword not in _ALLOWED_KEYWORDS:
            raise TypeError(
                f"{qualname}() got an unexpected keyword argument '{keyword}'"
            )
    if "string" in kwargs and (args or "data" in kwargs):
        raise TypeError(_CONFLICT_MESSAGE)
    if "string" in kwargs:
        warnings.warn(
            _DEPRECATED_STRING_MESSAGE, DeprecationWarning, stacklevel=4
        )
        data = kwargs["string"]
    elif args:
        data = args[0]
    else:
        data = kwargs.get("data", b"")
    usedforsecurity = kwargs.get("usedforsecurity", True)
    bool(usedforsecurity)
    return data, usedforsecurity


def _rust_backend(algorithm):
    def backend(data=b"", usedforsecurity=True):
        bool(usedforsecurity)
        return _hashlib_rs.new(algorithm, data)

    return backend


_constructors = {
    "md5": _rust_backend("md5"),
    "md5-sha1": _md5_sha1,
    "sha1": _rust_backend("sha1"),
    "sha224": _rust_backend("sha224"),
    "sha256": _rust_backend("sha256"),
    "sha384": _rust_backend("sha384"),
    "sha512": _rust_backend("sha512"),
    "sha512_224": _rust_backend("sha512_224"),
    "sha512_256": _rust_backend("sha512_256"),
    "blake2b": _blake2.blake2b,
    "blake2s": _blake2.blake2s,
    "sha3_224": _sha3.sha3_224,
    "sha3_256": _sha3.sha3_256,
    "sha3_384": _sha3.sha3_384,
    "sha3_512": _sha3.sha3_512,
    "shake_128": _sha3.shake_128,
    "shake_256": _sha3.shake_256,
    "ripemd160": _rust_backend("ripemd160"),
    "sm3": _rust_backend("sm3"),
}
_MISSING = object()

openssl_md_meth_names = frozenset(_constructors)
algorithms_available = openssl_md_meth_names
_GIL_MINSIZE = 2048
_STATIC_HMAC_SIZES = {
    "sha3_224": (28, 144),
    "sha3_256": (32, 136),
    "sha3_384": (48, 104),
    "sha3_512": (64, 72),
}


class UnsupportedDigestmodError(ValueError):
    pass


compare_digest = _operator._compare_digest


class _HMACMeta(type):
    def __call__(cls, *args, **kwargs):
        raise TypeError("cannot create '_hashlib.HMAC' instances")

    def __setattr__(cls, name, value):
        raise TypeError("cannot set attributes of immutable type '_hashlib.HMAC'")

    def __delattr__(cls, name, value):
        raise TypeError("cannot delete attributes of immutable type '_hashlib.HMAC'")


def _hmac_sizes(algorithm):
    if algorithm in _STATIC_HMAC_SIZES:
        return _STATIC_HMAC_SIZES[algorithm]
    probe = _hashlib_rs.new(algorithm, b"")
    return probe.digest_size, probe.block_size


class HMAC(metaclass=_HMACMeta):
    __slots__ = ("_state", "_digest_size", "_block_size", "_algorithm")

    def __new__(cls, *args, **kwargs):
        raise TypeError("cannot create '_hashlib.HMAC' instances")

    def __init__(self, key, msg=None, digestmod=None):
        if digestmod is None:
            raise TypeError("Missing required argument 'digestmod'.")
        algorithm = _digest_name(digestmod)
        if algorithm in ("shake_128", "shake_256") or algorithm not in _RUST_ALGORITHMS:
            raise UnsupportedDigestmodError(
                "[digital envelope routines] unsupported hash algorithm "
            )
        self._state = _hmac_rs.new(key, algorithm)
        self._digest_size, self._block_size = _hmac_sizes(algorithm)
        self._algorithm = algorithm
        if msg is not None:
            _hmac_rs.update(self._state, msg)

    @property
    def name(self):
        return "hmac-" + self._algorithm

    @property
    def digest_size(self):
        return self._digest_size

    @property
    def block_size(self):
        return self._block_size

    def __setattr__(self, name, value):
        if name in ("name", "digest_size", "block_size"):
            raise AttributeError(
                f"attribute '{name}' of '_hashlib.HMAC' objects is not writable"
            )
        object.__setattr__(self, name, value)

    def __delattr__(self, name, value):
        if name in ("name", "digest_size", "block_size"):
            raise AttributeError(
                f"attribute '{name}' of '_hashlib.HMAC' objects is not writable"
            )
        object.__delattr__(self, name)

    def update(self, msg):
        _hmac_rs.update(self._state, msg)

    def digest(self):
        return _hmac_rs.digest(self._state)

    def hexdigest(self):
        return self.digest().hex()

    def copy(self):
        result = object.__new__(type(self))
        result._state = _hmac_rs.copy(self._state)
        result._digest_size = self._digest_size
        result._block_size = self._block_size
        result._algorithm = self._algorithm
        return result

    def __repr__(self):
        return f"<{self._algorithm} HMAC object @ {id(self):#x}>"


def _digest_name(digestmod):
    if isinstance(digestmod, str):
        name = digestmod
    else:
        name = getattr(digestmod, "__name__", None)
        if name is None:
            name = getattr(digestmod, "name", None)
        if not isinstance(name, str):
            raise UnsupportedDigestmodError(
                "[digital envelope routines] unsupported hash algorithm "
            )
        name = name.removeprefix("openssl_")
    return _normalize_digest_name(name)


def hmac_new(key, msg=b"", digestmod=_MISSING):
    if digestmod is _MISSING:
        raise TypeError("Missing required argument 'digestmod'.")
    result = object.__new__(HMAC)
    HMAC.__init__(result, key, msg, digestmod)
    return result


def hmac_digest(key, msg, digest):
    algorithm = _digest_name(digest)
    if algorithm in ("shake_128", "shake_256") or algorithm not in _RUST_ALGORITHMS:
        raise UnsupportedDigestmodError(
            "[digital envelope routines] unsupported hash algorithm "
        )
    return _hmac_rs.compute_digest(key, msg, algorithm)


def pbkdf2_hmac(hash_name, password, salt, iterations, dklen=None):
    return _hashlib_rs.pbkdf2_hmac(hash_name, password, salt, iterations, dklen)


def scrypt(password, *, salt, n, r, p, maxmem=0, dklen=64):
    return _hashlib_rs.scrypt(password, salt, n, r, p, maxmem, dklen)


def get_fips_mode():
    return 0


_openssl_names = (
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
    "ripemd160",
    "sm3",
)
_openssl_fallback_signature = inspect.Signature(
    (
        inspect.Parameter("data", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=b""),
        inspect.Parameter("usedforsecurity", inspect.Parameter.KEYWORD_ONLY, default=True),
        inspect.Parameter("string", inspect.Parameter.KEYWORD_ONLY, default=None),
    )
)


def _openssl_constructor(name):
    builtin = _constructors[name]
    qualname = "openssl_" + name

    def constructor(*args, **kwargs):
        data, usedforsecurity = _clinic_parse(qualname, args, kwargs, positional_count=1)
        return builtin(data, usedforsecurity=usedforsecurity)

    constructor.__name__ = qualname
    constructor.__qualname__ = constructor.__name__
    constructor.__module__ = __name__
    try:
        constructor.__signature__ = inspect.signature(builtin)
    except (TypeError, ValueError):
        constructor.__signature__ = _openssl_fallback_signature
    return constructor


for _name in _openssl_names:
    globals()["openssl_" + _name] = _openssl_constructor(_name)


def new(name, *args, **kwargs):
    if not isinstance(name, str):
        raise TypeError(f"new() argument 'name' must be str, not {type(name).__name__}")
    if len(args) > 1:
        raise TypeError(f"new() takes at most 2 positional arguments ({len(args) + 1} given)")
    if args and "data" in kwargs:
        raise TypeError("argument for new() given by name ('data') and position (2)")
    for keyword in kwargs:
        if keyword not in _ALLOWED_KEYWORDS:
            raise TypeError(f"new() got an unexpected keyword argument '{keyword}'")
    if "string" in kwargs and (args or "data" in kwargs):
        raise TypeError(_CONFLICT_MESSAGE)
    normalized_name = _normalize_digest_name(name)
    try:
        constructor = _constructors[normalized_name]
    except KeyError:
        if "usedforsecurity" in kwargs:
            bool(kwargs["usedforsecurity"])
        raise UnsupportedDigestmodError(
            f"[digital envelope routines] unsupported hash algorithm {name}"
        ) from None
    if "string" in kwargs:
        import warnings

        warnings.warn(_DEPRECATED_STRING_MESSAGE, DeprecationWarning, stacklevel=2)
        return constructor(kwargs["string"], usedforsecurity=kwargs.get("usedforsecurity", True))
    if args:
        data = args[0]
    else:
        data = kwargs.get("data", b"")
    usedforsecurity = kwargs.get("usedforsecurity", True)
    bool(usedforsecurity)
    return constructor(data, usedforsecurity=usedforsecurity)


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
        "blake2b512": "blake2b",
        "blake2b-512": "blake2b",
        "blake2s256": "blake2s",
        "blake2s-256": "blake2s",
        "sha3-224": "sha3_224",
        "sha3-256": "sha3_256",
        "sha3-384": "sha3_384",
        "sha3-512": "sha3_512",
        "shake-128": "shake_128",
        "shake-256": "shake_256",
        "ripemd-160": "ripemd160",
    }
    return aliases.get(normalized, normalized)
