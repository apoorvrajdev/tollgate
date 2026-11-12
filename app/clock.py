"""Time source. Code that depends on time takes a Clock; tests inject a fake."""

import time
from typing import Protocol


class Clock(Protocol):
    def now_seconds(self) -> float:
        """Seconds since the Unix epoch."""
        ...


class SystemClock:
    """Wall-clock time, because several gateway instances share one Redis."""

    def now_seconds(self) -> float:
        return time.time()
