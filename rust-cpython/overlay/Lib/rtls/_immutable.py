from __future__ import annotations


class ImmutableType(type):
    """Metaclass emulating CPython's immutable static extension types.

    Assigning (or deleting) an attribute on the class raises the same shape
    of TypeError CPython raises for immutable types, so the ``ssl`` surface
    observes built-in-like behavior. Instance attribute behavior is
    unchanged. Internal class-level wiring must go through
    ``type.__setattr__``.
    """

    def __setattr__(cls, name, value):
        raise TypeError(
            f"cannot set {name!r} attribute of immutable type {cls.__name__!r}"
        )

    def __delattr__(cls, name):
        raise TypeError(
            f"cannot delete {name!r} attribute of immutable type {cls.__name__!r}"
        )
