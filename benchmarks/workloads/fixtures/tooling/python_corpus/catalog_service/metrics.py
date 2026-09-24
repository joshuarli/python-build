"""Small in-process counters and latency aggregation helpers."""

from __future__ import annotations

import math
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class Distribution:
    """Descriptive summary of a sequence of nonnegative measurements."""

    count: int
    total: float
    minimum: float
    maximum: float
    mean: float
    variance: float


class Counters:
    """Thread-safe named integer counters with deterministic snapshots."""

    def __init__(self) -> None:
        self._values: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def increment(self, name: str, amount: int = 1) -> int:
        """Increment a counter and return its new value."""
        if amount < 0:
            raise ValueError("counter increments must be nonnegative")
        with self._lock:
            self._values[name] += amount
            return self._values[name]

    def snapshot(self) -> dict[str, int]:
        """Return an alphabetically ordered copy of counter state."""
        with self._lock:
            return {key: self._values[key] for key in sorted(self._values)}


def summarize(values: Iterable[float]) -> Distribution:
    """Calculate a population variance without retaining input values."""
    count = 0
    total = 0.0
    squares = 0.0
    minimum = math.inf
    maximum = -math.inf
    for value in values:
        if value < 0 or not math.isfinite(value):
            raise ValueError("measurements must be finite and nonnegative")
        count += 1
        total += value
        squares += value * value
        minimum = min(minimum, value)
        maximum = max(maximum, value)
    if not count:
        return Distribution(0, 0.0, 0.0, 0.0, 0.0, 0.0)
    mean = total / count
    variance = max(0.0, squares / count - mean * mean)
    return Distribution(count, total, minimum, maximum, mean, variance)
