"""Time source. Code that depends on time takes a Clock; tests inject a fake."""

import time
from typing import Protocol


class Clock(Protocol):
    def now_seconds(self) -> float:
        """Seconds since the Unix epoch."""
        ...


class MonotonicClock(Protocol):
    def monotonic_seconds(self) -> float:
        """Seconds from an arbitrary start; only differences mean anything. Never goes back."""
        ...


class SystemMonotonicClock:
    """`time.perf_counter()`, the highest-resolution monotonic clock (ADR-0016)."""

    def monotonic_seconds(self) -> float:
        return time.perf_counter()


class SystemClock:
    """Wall-clock time, because several gateway instances share one Redis."""

    def now_seconds(self) -> float:
        return time.time()
