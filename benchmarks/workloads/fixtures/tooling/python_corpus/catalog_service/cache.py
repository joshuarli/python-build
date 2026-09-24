"""Bounded least-recently-used cache with expiration support."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Generic, Hashable, TypeVar


Key = TypeVar("Key", bound=Hashable)
Value = TypeVar("Value")


@dataclass(frozen=True, slots=True)
class CacheStats:
    """Snapshot counters for cache observability."""

    hits: int
    misses: int
    evictions: int
    size: int


class ExpiringLRU(Generic[Key, Value]):
    """A lock-protected LRU cache that expires entries by monotonic time."""

    def __init__(self, capacity: int, ttl_seconds: float, *, clock=time.monotonic) -> None:
        if capacity < 1 or ttl_seconds <= 0:
            raise ValueError("capacity and time to live must be positive")
        self._capacity = capacity
        self._ttl = ttl_seconds
        self._clock = clock
        self._items: OrderedDict[Key, tuple[float, Value]] = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, key: Key) -> Value | None:
        """Return a live value and promote it to most-recently-used."""
        with self._lock:
            item = self._items.get(key)
            if item is None:
                self._misses += 1
                return None
            deadline, value = item
            if deadline <= self._clock():
                del self._items[key]
                self._misses += 1
                return None
            self._items.move_to_end(key)
            self._hits += 1
            return value

    def put(self, key: Key, value: Value) -> None:
        """Insert a value, evicting the least recently used item if full."""
        with self._lock:
            self._items[key] = (self._clock() + self._ttl, value)
            self._items.move_to_end(key)
            if len(self._items) > self._capacity:
                self._items.popitem(last=False)
                self._evictions += 1

    def purge_expired(self) -> int:
        """Remove expired items and return the number that were removed."""
        now = self._clock()
        with self._lock:
            expired = [key for key, (deadline, _) in self._items.items() if deadline <= now]
            for key in expired:
                del self._items[key]
            return len(expired)

    def stats(self) -> CacheStats:
        """Return counters and the current number of cached items."""
        with self._lock:
            return CacheStats(self._hits, self._misses, self._evictions, len(self._items))
