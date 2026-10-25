#.  Copyright (C) 2005-2010   Gregory P. Smith (greg@krypto.org)
#  Licensed to PSF under a Contributor Agreement.
#

__doc__ = r"""hashlib module - A common interface to many hash functions.

new(name, data=b'', **kwargs) - returns a new hash object implementing the
                                given hash function; initializing the hash
                                using the given binary data.

Named constructor functions are also available, these are faster
than using new(name):

md5(), sha1(), sha224(), sha256(), sha384(), sha512(), blake2b(), blake2s(),
sha3_224(), sha3_256(), sha3_384(), sha3_512(), shake_128(), and shake_256().

More algorithms may be available on your platform but the above are guaranteed
to exist.  See the algorithms_guaranteed and algorithms_available attributes
to find out what algorithm names can be passed to new().

NOTE: If you want the adler32 or crc32 hash functions they are available in
the zlib module.

Choose your hash function wisely.  Some have known collision weaknesses,
while others may be slower depending on the CPU architecture.

Hash objects have these methods:
 - update(data): Update the hash object with the bytes in data. Repeated calls
                 are equivalent to a single call with the concatenation of all
                 the arguments.
 - digest():     Return the digest of the bytes passed to the update() method
                 so far as a bytes object.
 - hexdigest():  Like digest() except the digest is returned as a string
                 of double length, containing only hexadecimal digits.
 - copy():       Return a copy (clone) of the hash object. This can be used to
                 efficiently compute the digests of data that share a common
                 initial substring.

Assuming that Python has been built with SHA-2 support, the SHA-256 digest
of the byte string b'Nobody inspects the spammish repetition' is computed
as follows:

    >>> import hashlib
    >>> m = hashlib.sha256()
    >>> m.update(b"Nobody inspects")
    >>> m.update(b" the spammish repetition")
    >>> m.digest()  # doctest: +ELLIPSIS
    b'\x03\x1e\xdd}Ae\x15\x93\xc5\xfe\\\x00o\xa5u+7...'

More condensed:

    >>> hashlib.sha256(b"Nobody inspects the spammish repetition").hexdigest()
    '031edd7d41651593c5fe5c006fa5752b37fddff7bc4e843aa6af0c950f4b9406'
"""

# This tuple and __get_builtin_constructor() must be modified if a new
# always available algorithm is added.
__always_supported = ('md5', 'sha1', 'sha224', 'sha256', 'sha384', 'sha512',
                      'blake2b', 'blake2s',
                      'sha3_224', 'sha3_256', 'sha3_384', 'sha3_512',
                      'shake_128', 'shake_256')


algorithms_guaranteed = set(__always_supported)
algorithms_available = set(__always_supported)

__all__ = __always_supported + ('new', 'algorithms_guaranteed',
                                'algorithms_available', 'file_digest')


__builtin_constructor_cache = {}

# Prefer our blake2 implementation
# OpenSSL 1.1.0 comes with a limited implementation of blake2b/s. The OpenSSL
# implementations neither support keyed blake2 (blake2 MAC) nor advanced
# features like salt, personalization, or tree hashing. OpenSSL hash-only
# variants are available as 'blake2b512' and 'blake2s256', though.
__block_openssl_constructor = {
    'blake2b', 'blake2s',
}

_rust_hash_algorithms = frozenset({'md5', 'sha1', 'sha224', 'sha256',
                                  'sha384', 'sha512', 'sha512_224',
                                  'sha512_256', 'ripemd160', 'sm3'})
_rust_only_algorithms = frozenset({'sha512_224', 'sha512_256',
                                   'ripemd160', 'sm3'})
_rust_extra_algorithms = frozenset({'sha512_224', 'sha512_256',
                                    'ripemd160', 'sm3', 'md5-sha1'})
_rust_hash_module = None


def _get_rust_hash_module():
    """Load the optional digest extension only in interpreters that support it."""
    global _rust_hash_module
    if _rust_hash_module is False:
        return None
    if _rust_hash_module is None:
        try:
            import _hashlib_rs
        except ImportError:
            _rust_hash_module = False
            return None
        else:
            _rust_hash_module = _hashlib_rs
    return _rust_hash_module


def _rust_hash_constructor(name, builtin_constructor):
    """Route fixed-output public constructors through Rust when available."""
    def constructor(*args, **kwargs):
        backend_hash = builtin_constructor(*args, **kwargs)
        rust_module = _get_rust_hash_module()
        if rust_module is None:
            return backend_hash
        if args:
            data = args[0]
        else:
            data = kwargs.get('data', kwargs.get('string', b''))
        return rust_module.new(name, data)

    constructor.__name__ = builtin_constructor.__name__
    constructor.__qualname__ = builtin_constructor.__qualname__
    constructor.__module__ = builtin_constructor.__module__
    constructor.__doc__ = builtin_constructor.__doc__
    constructor.__wrapped__ = builtin_constructor
    return constructor


def _get_rust_constructor(name):
    """Prefer the Rust digest object for fixed-output algorithms it covers."""
    if name in _rust_hash_algorithms and name not in _rust_only_algorithms:
        return _rust_hash_constructor(name, __get_builtin_constructor(name))
    return __get_builtin_constructor(name)


def _normalize_digest_name(name):
    normalized = name.lower()
    aliases = {
        'sha-1': 'sha1',
        'sha-224': 'sha224',
        'sha-256': 'sha256',
        'sha-384': 'sha384',
        'sha-512': 'sha512',
        'sha512-224': 'sha512_224',
        'sha512-256': 'sha512_256',
        'blake2b512': 'blake2b',
        'blake2b-512': 'blake2b',
        'blake2s256': 'blake2s',
        'blake2s-256': 'blake2s',
        'sha3-224': 'sha3_224',
        'sha3-256': 'sha3_256',
        'sha3-384': 'sha3_384',
        'sha3-512': 'sha3_512',
        'shake-128': 'shake_128',
        'shake-256': 'shake_256',
        'ripemd-160': 'ripemd160',
    }
    return aliases.get(normalized, normalized)


class _MD5SHA1:
    name = 'md5-sha1'
    digest_size = 36
    block_size = 64
    __slots__ = ('_md5', '_sha1')

    def __init__(self, data=b'', *, usedforsecurity=True):
        import _md5
        import _sha1
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


def _md5_sha1(data=b'', *, usedforsecurity=True):
    return _MD5SHA1(data, usedforsecurity=usedforsecurity)

def __get_builtin_constructor(name):
    if not isinstance(name, str):
        # Since this function is only used by new(), we use the same
        # exception as _hashlib.new() when 'name' is of incorrect type.
        err = f"new() argument 'name' must be str, not {type(name).__name__}"
        raise TypeError(err)
    cache = __builtin_constructor_cache
    constructor = cache.get(name)
    if constructor is not None:
        return constructor
    try:
        if name in {'SHA1', 'sha1'}:
            import _sha1
            cache['SHA1'] = cache['sha1'] = _sha1.sha1
        elif name in {'MD5', 'md5'}:
            import _md5
            cache['MD5'] = cache['md5'] = _md5.md5
        elif name in {'SHA256', 'sha256', 'SHA224', 'sha224'}:
            import _sha2
            cache['SHA224'] = cache['sha224'] = _sha2.sha224
            cache['SHA256'] = cache['sha256'] = _sha2.sha256
        elif name in {'SHA512', 'sha512', 'SHA384', 'sha384'}:
            import _sha2
            cache['SHA384'] = cache['sha384'] = _sha2.sha384
            cache['SHA512'] = cache['sha512'] = _sha2.sha512
        elif name in {'blake2b', 'blake2s'}:
            import _blake2
            cache['blake2b'] = _blake2.blake2b
            cache['blake2s'] = _blake2.blake2s
        elif name in {'sha3_224', 'sha3_256', 'sha3_384', 'sha3_512'}:
            import _sha3
            cache['sha3_224'] = _sha3.sha3_224
            cache['sha3_256'] = _sha3.sha3_256
            cache['sha3_384'] = _sha3.sha3_384
            cache['sha3_512'] = _sha3.sha3_512
        elif name in {'shake_128', 'shake_256'}:
            import _sha3
            cache['shake_128'] = _sha3.shake_128
            cache['shake_256'] = _sha3.shake_256
    except ImportError:
        pass  # no extension module, this hash is unsupported.

    constructor = cache.get(name)
    if constructor is not None:
        return constructor

    # Keep the message in sync with hashlib.h::HASHLIB_UNSUPPORTED_ALGORITHM.
    raise ValueError(f'unsupported hash algorithm {name}')


def __py_new(name, *args, **kwargs):
    """new(name, data=b'', **kwargs) - Return a new hashing object using the
    named algorithm; optionally initialized with data (which must be
    a bytes-like object).
    """
    return __get_builtin_constructor(name)(*args, **kwargs)


def _rust_extra_new(name, normalized, args, kwargs):
    # Names without a builtin constructor share new()'s argument errors.
    if len(args) > 1:
        raise TypeError(
            f"new() takes at most 2 positional arguments ({len(args) + 1} given)")
    if args and 'data' in kwargs:
        raise TypeError(
            "new() got multiple values for argument "
            "given by name ('data') and position")
    for keyword in kwargs:
        if keyword not in ('data', 'string', 'usedforsecurity'):
            raise TypeError(
                f"new() got an unexpected keyword argument '{keyword}'")
    if 'string' in kwargs:
        if args or 'data' in kwargs:
            raise TypeError(
                "'data' and 'string' are mutually exclusive "
                "and support for 'string' keyword parameter "
                "is slated for removal in a future version.")
        import warnings
        warnings.warn(
            "the 'string' keyword parameter is deprecated since "
            "Python 3.15 and slated for removal in Python 3.19; "
            "use the 'data' keyword parameter or pass the data "
            "to hash as a positional argument instead",
            DeprecationWarning, stacklevel=3)
        data = kwargs['string']
    elif args:
        data = args[0]
    else:
        data = kwargs.get('data', b'')
    usedforsecurity = kwargs.get('usedforsecurity', True)
    bool(usedforsecurity)
    rust_module = _get_rust_hash_module()
    if rust_module is None:
        raise ValueError(f"unsupported hash algorithm {name}")
    if normalized == 'md5-sha1':
        return _md5_sha1(data, usedforsecurity=usedforsecurity)
    return rust_module.new(normalized, data)


def __rust_new(name, *args, **kwargs):
    """new(name, data=b'') - Return a new hashing object using the named algorithm;
    optionally initialized with data (which must be a bytes-like object).
    """
    if not isinstance(name, str):
        raise TypeError(
            f"new() argument 'name' must be str, not {type(name).__name__}")
    if name in __block_openssl_constructor:
        # __block_openssl_constructor is expected to contain strings only
        assert isinstance(name, str), f"unexpected name: {name}"
        # Prefer our builtin blake2 implementation.
        return __get_builtin_constructor(name)(*args, **kwargs)
    normalized = _normalize_digest_name(name)
    if normalized not in _rust_extra_algorithms:
        try:
            constructor = __get_builtin_constructor(normalized)
        except ValueError:
            if 'usedforsecurity' in kwargs:
                bool(kwargs['usedforsecurity'])
            raise ValueError(f"unsupported hash algorithm {name}") from None
        backend_hash = constructor(*args, **kwargs)
        if backend_hash.name in _rust_hash_algorithms:
            rust_module = _get_rust_hash_module()
            if rust_module is not None:
                if args:
                    data = args[0]
                else:
                    data = kwargs.get('data', kwargs.get('string', b''))
                return rust_module.new(backend_hash.name, data)
        return backend_hash
    return _rust_extra_new(name, normalized, args, kwargs)


_rust_hash_module_available = _get_rust_hash_module() is not None
if _rust_hash_module_available:
    algorithms_available = algorithms_available.union(_rust_extra_algorithms)

new = __rust_new
__get_hash = _get_rust_constructor

try:
    from _hashlib_rs import pbkdf2_hmac as _rust_pbkdf2_hmac
except ImportError:
    _rust_pbkdf2_hmac = None

try:
    from _hashlib_rs import scrypt as _rust_scrypt
except ImportError:
    _rust_scrypt = None

if _rust_pbkdf2_hmac is not None:
    def pbkdf2_hmac(hash_name, password, salt, iterations, dklen=None):
        return _rust_pbkdf2_hmac(hash_name, password, salt, iterations, dklen)
    __all__ += ('pbkdf2_hmac',)

if _rust_scrypt is not None:
    def scrypt(password, *, salt, n, r, p, maxmem=0, dklen=64):
        return _rust_scrypt(password, salt, n, r, p, maxmem, dklen)
    __all__ += ('scrypt',)


def file_digest(fileobj, digest, /, *, _bufsize=2**18):
    """Hash the contents of a file-like object. Returns a digest object.

    *fileobj* must be a file-like object opened for reading in binary mode.
    It accepts file objects from open(), io.BytesIO(), and SocketIO objects.
    The function may bypass Python's I/O and use the file descriptor *fileno*
    directly.

    *digest* must either be a hash algorithm name as a *str*, a hash
    constructor, or a callable that returns a hash object.
    """
    # On Linux we could use AF_ALG sockets and sendfile() to achieve zero-copy
    # hashing with hardware acceleration.
    if isinstance(digest, str):
        digestobj = new(digest)
    else:
        digestobj = digest()

    if hasattr(fileobj, "getbuffer"):
        # io.BytesIO object, use zero-copy buffer
        digestobj.update(fileobj.getbuffer())
        return digestobj

    # Only binary files implement readinto().
    if not (
        hasattr(fileobj, "readinto")
        and hasattr(fileobj, "readable")
        and fileobj.readable()
    ):
        raise ValueError(
            f"'{fileobj!r}' is not a file-like object in binary reading mode."
        )

    # binary file, socket.SocketIO object
    # Note: socket I/O uses different syscalls than file I/O.
    buf = bytearray(_bufsize)  # Reusable buffer to reduce allocations.
    view = memoryview(buf)
    while True:
        size = fileobj.readinto(buf)
        if size is None:
            raise BlockingIOError("I/O operation would block.")
        if size == 0:
            break  # EOF
        digestobj.update(view[:size])

    return digestobj


for __func_name in __always_supported:
    # try them all, some may not work due to the OpenSSL
    # version not supporting that algorithm.
    try:
        globals()[__func_name] = __get_hash(__func_name)
    except ValueError:
        # Don't log here: logging at import time has global side effects and
        # would tell the wrong audience; code that uses a missing algorithm
        # gets a ValueError from the stub installed below.
        # The following code can be simplified in Python 3.19
        # once "string" is removed from the signature.
        __code = f'''\
def {__func_name}(data=__UNSET, *, usedforsecurity=True, string=__UNSET):
    if data is __UNSET and string is not __UNSET:
        import warnings
        warnings.warn(
            "the 'string' keyword parameter is deprecated since "
            "Python 3.15 and slated for removal in Python 3.19; "
            "use the 'data' keyword parameter or pass the data "
            "to hash as a positional argument instead",
            DeprecationWarning, stacklevel=2)
    if data is not __UNSET and string is not __UNSET:
        raise TypeError("'data' and 'string' are mutually exclusive "
                        "and support for 'string' keyword parameter "
                        "is slated for removal in a future version.")
    raise ValueError("unsupported hash algorithm {__func_name}")
'''
        exec(__code, {"__UNSET": object()}, __locals := {})
        globals()[__func_name] = __locals[__func_name]
        del __code, __locals

# Cleanup locals()
del __always_supported, __func_name, __get_hash
del __py_new, _get_rust_constructor
