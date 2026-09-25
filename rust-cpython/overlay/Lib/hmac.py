"""HMAC (Keyed-Hashing for Message Authentication) module.

Implements the HMAC algorithm as described by RFC 2104.
"""

try:
    import _hashlib as _hashopenssl
except ImportError:
    _hashopenssl = None
    _functype = None
    from _operator import _compare_digest as compare_digest
else:
    compare_digest = _hashopenssl.compare_digest
    _functype = type(_hashopenssl.openssl_sha256)  # builtin type

try:
    import _hmac
except ImportError:
    _hmac = None

trans_5C = bytes((x ^ 0x5C) for x in range(256))
trans_36 = bytes((x ^ 0x36) for x in range(256))

# The size of the digests returned by HMAC depends on the underlying
# hashing module used.  Use digest_size from the instance of HMAC instead.
digest_size = None


def _is_shake_constructor(digest_like):
    if isinstance(digest_like, str):
        name = digest_like
    else:
        h = digest_like() if callable(digest_like) else digest_like.new()
        if not isinstance(name := getattr(h, "name", None), str):
            return False
    return name.startswith(("shake", "SHAKE"))


def _get_digest_constructor(digest_like):
    if callable(digest_like):
        return digest_like
    if isinstance(digest_like, str):
        def digest_wrapper(d=b''):
            import hashlib
            return hashlib.new(digest_like, d)
    else:
        def digest_wrapper(d=b''):
            return digest_like.new(d)
    return digest_wrapper


_RUST_HMAC_SPECS = {
    "md5": ("md5", 16, 64),
    "sha1": ("sha1", 20, 64),
    "sha224": ("sha224", 28, 64),
    "sha256": ("sha256", 32, 64),
    "sha384": ("sha384", 48, 128),
    "sha512": ("sha512", 64, 128),
    "sha512224": ("sha512_224", 28, 128),
    "sha512256": ("sha512_256", 32, 128),
    "sha3224": ("sha3_224", 28, 144),
    "sha3256": ("sha3_256", 32, 136),
    "sha3384": ("sha3_384", 48, 104),
    "sha3512": ("sha3_512", 64, 72),
}


def _rust_hmac_spec(digestmod):
    if not isinstance(digestmod, str):
        return None
    normalized = digestmod.lower().replace("-", "").replace("_", "")
    return _RUST_HMAC_SPECS.get(normalized)


def _get_rust_hmac():
    try:
        import _hmac_rs
    except ImportError:
        return None
    return _hmac_rs


class _RustHMACState:
    __slots__ = ("_module", "_state", "_digest_name", "name", "digest_size", "block_size")

    def __init__(self, module, state, digest_name, digest_size, block_size):
        self._module = module
        self._state = state
        self._digest_name = digest_name
        self.name = f"hmac-{digest_name}"
        self.digest_size = digest_size
        self.block_size = block_size

    def update(self, msg):
        self._module.update(self._state, msg)

    def copy(self):
        return type(self)(
            self._module,
            self._module.copy(self._state),
            self._digest_name,
            self.digest_size,
            self.block_size,
        )

    def digest(self):
        return self._module.digest(self._state)

    def hexdigest(self):
        return self._module.hexdigest(self._state)


class HMAC:
    """RFC 2104 HMAC class.  Also complies with RFC 4231.

    This supports the API for Cryptographic Hash Functions (PEP 247).
    """

    # Note: self.blocksize is the default blocksize; self.block_size
    # is effective block size as well as the public API attribute.
    blocksize = 64  # 512-bit HMAC; can be changed in subclasses.

    __slots__ = (
        "_hmac", "_inner", "_outer", "block_size", "digest_size"
    )

    def __init__(self, key, msg=None, digestmod=''):
        """Create a new HMAC object.

        key: bytes or buffer, key for the keyed hash object.
        msg: bytes or buffer, Initial input for the hash or None.
        digestmod: A hash name suitable for hashlib.new(). *OR*
                   A hashlib constructor returning a new hash object. *OR*
                   A module supporting PEP 247.

                   Required as of 3.8, despite its position after the optional
                   msg argument.  Passing it as a keyword argument is
                   recommended, though not required for legacy API reasons.
        """

        if not isinstance(key, (bytes, bytearray)):
            raise TypeError(f"key: expected bytes or bytearray, "
                            f"but got {type(key).__name__!r}")

        if not digestmod:
            raise TypeError("Missing required argument 'digestmod'.")

        self.__init(key, msg, digestmod)

    def __init(self, key, msg, digestmod):
        if _hashopenssl and isinstance(digestmod, (str, _functype)):
            if isinstance(digestmod, str) and self._init_rust_hmac(
                    key, msg, digestmod):
                return
            try:
                self._init_openssl_hmac(key, msg, digestmod)
                return
            except _hashopenssl.UnsupportedDigestmodError:  # pragma: no cover
                pass
        if _hmac and isinstance(digestmod, str):
            try:
                self._init_builtin_hmac(key, msg, digestmod)
                return
            except _hmac.UnknownHashError:  # pragma: no cover
                pass
        self._init_old(key, msg, digestmod)

    def _init_rust_hmac(self, key, msg, digestmod):
        spec = _rust_hmac_spec(digestmod)
        if spec is None:
            return False
        rust_hmac = _get_rust_hmac()
        if rust_hmac is None:
            return False
        try:
            _hashopenssl.hmac_new(key, None, digestmod=digestmod)
        except _hashopenssl.UnsupportedDigestmodError:
            return False
        name, digest_size, block_size = spec
        state = _RustHMACState(
            rust_hmac, rust_hmac.new(key, name), name, digest_size, block_size
        )
        if msg is not None:
            state.update(msg)
        self._hmac = state
        self._inner = self._outer = None
        self.digest_size = digest_size
        self.block_size = block_size
        return True

    def _init_openssl_hmac(self, key, msg, digestmod):
        self._hmac = _hashopenssl.hmac_new(key, msg, digestmod=digestmod)
        self._inner = self._outer = None  # because the slots are defined
        self.digest_size = self._hmac.digest_size
        self.block_size = self._hmac.block_size

    _init_hmac = _init_openssl_hmac  # for backward compatibility (if any)

    def _init_builtin_hmac(self, key, msg, digestmod):
        self._hmac = _hmac.new(key, msg, digestmod=digestmod)
        self._inner = self._outer = None  # because the slots are defined
        self.digest_size = self._hmac.digest_size
        self.block_size = self._hmac.block_size

    def _init_old(self, key, msg, digestmod):
        import warnings

        digest_cons = _get_digest_constructor(digestmod)
        if _is_shake_constructor(digest_cons):
            raise ValueError(f"unsupported hash algorithm {digestmod}")

        self._hmac = None
        self._outer = digest_cons()
        self._inner = digest_cons()
        self.digest_size = self._inner.digest_size

        if hasattr(self._inner, 'block_size'):
            blocksize = self._inner.block_size
            if blocksize < 16:
                warnings.warn(f"block_size of {blocksize} seems too small; "
                              f"using our default of {self.blocksize}.",
                              RuntimeWarning, 2)
                blocksize = self.blocksize  # pragma: no cover
        else:
            warnings.warn("No block_size attribute on given digest object; "
                          f"Assuming {self.blocksize}.",
                          RuntimeWarning, 2)
            blocksize = self.blocksize  # pragma: no cover

        if len(key) > blocksize:
            key = digest_cons(key).digest()

        self.block_size = blocksize

        key = key.ljust(blocksize, b'\0')
        self._outer.update(key.translate(trans_5C))
        self._inner.update(key.translate(trans_36))
        if msg is not None:
            self.update(msg)

    @property
    def name(self):
        if self._hmac:
            return self._hmac.name
        else:
            return f"hmac-{self._inner.name}"

    def update(self, msg):
        """Feed data from msg into this hashing object."""
        inst = self._hmac or self._inner
        inst.update(msg)

    def copy(self):
        """Return a separate copy of this hashing object.

        An update to this copy won't affect the original object.
        """
        # Call __new__ directly to avoid the expensive __init__.
        other = self.__class__.__new__(self.__class__)
        other.digest_size = self.digest_size
        other.block_size = self.block_size
        if self._hmac:
            other._hmac = self._hmac.copy()
            other._inner = other._outer = None
        else:
            other._hmac = None
            other._inner = self._inner.copy()
            other._outer = self._outer.copy()
        return other

    def _current(self):
        """Return a hash object for the current state.

        To be used only internally with digest() and hexdigest().
        """
        if self._hmac:
            return self._hmac
        else:
            h = self._outer.copy()
            h.update(self._inner.digest())
            return h

    def digest(self):
        """Return the hash value of this hashing object.

        This returns the hmac value as bytes.  The object is
        not altered in any way by this function; you can continue
        updating the object after calling this function.
        """
        h = self._current()
        return h.digest()

    def hexdigest(self):
        """Like digest(), but returns a string of hexadecimal digits instead.
        """
        h = self._current()
        return h.hexdigest()


def new(key, msg=None, digestmod=''):
    """Create a new hashing object and return it.

    key: bytes or buffer, The starting key for the hash.
    msg: bytes or buffer, Initial input for the hash, or None.
    digestmod: A hash name suitable for hashlib.new(). *OR*
               A hashlib constructor returning a new hash object. *OR*
               A module supporting PEP 247.

               Required as of 3.8, despite its position after the optional
               msg argument.  Passing it as a keyword argument is
               recommended, though not required for legacy API reasons.

    You can now feed arbitrary bytes into the object using its update()
    method, and can ask for the hash value at any time by calling its digest()
    or hexdigest() methods.
    """
    return HMAC(key, msg, digestmod)


def digest(key, msg, digest):
    """Fast inline implementation of HMAC.

    key: bytes or buffer, The key for the keyed hash object.
    msg: bytes or buffer, Input message.
    digest: A hash name suitable for hashlib.new() for best performance. *OR*
            A hashlib constructor returning a new hash object. *OR*
            A module supporting PEP 247.
    """
    if _hashopenssl and isinstance(digest, (str, _functype)):
        if isinstance(digest, str):
            spec = _rust_hmac_spec(digest)
            rust_hmac = _get_rust_hmac() if spec is not None else None
            if rust_hmac is not None:
                try:
                    _hashopenssl.hmac_digest(key, b"", digest)
                except (OverflowError, _hashopenssl.UnsupportedDigestmodError):
                    pass
                else:
                    return rust_hmac.compute_digest(key, msg, spec[0])
        try:
            return _hashopenssl.hmac_digest(key, msg, digest)
        except OverflowError:
            # OpenSSL's HMAC limits the size of the key to INT_MAX.
            # Instead of falling back to HACL* implementation which
            # may still not be supported due to a too large key, we
            # directly switch to the pure Python fallback instead
            # even if we could have used streaming HMAC for small keys
            # but large messages.
            return _compute_digest_fallback(key, msg, digest)
        except _hashopenssl.UnsupportedDigestmodError:
            pass

    if _hmac and isinstance(digest, str):
        try:
            return _hmac.compute_digest(key, msg, digest)
        except (OverflowError, _hmac.UnknownHashError):
            # HACL* HMAC limits the size of the key to UINT32_MAX
            # so we fallback to the pure Python implementation even
            # if streaming HMAC may have been used for small keys
            # and large messages.
            pass

    return _compute_digest_fallback(key, msg, digest)


def _compute_digest_fallback(key, msg, digest):
    digest_cons = _get_digest_constructor(digest)
    if _is_shake_constructor(digest_cons):
        raise ValueError(f"unsupported hash algorithm {digest}")
    inner = digest_cons()
    outer = digest_cons()
    blocksize = getattr(inner, 'block_size', 64)
    if len(key) > blocksize:
        key = digest_cons(key).digest()
    key = key.ljust(blocksize, b'\0')
    inner.update(key.translate(trans_36))
    outer.update(key.translate(trans_5C))
    inner.update(msg)
    outer.update(inner.digest())
    return outer.digest()
