"""Test doubles shared across tests."""


class FakeClock:
    """A clock that moves only when advance() is called."""

    def __init__(self, start_seconds: float = 0.0) -> None:
        self._now_seconds = start_seconds

    def now_seconds(self) -> float:
        return self._now_seconds

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("advance seconds must not be negative")
        self._now_seconds += seconds
