"""Test doubles shared across tests."""

from app.settings import Settings


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


def make_settings(**overrides: str) -> Settings:
    """Settings built from an explicit mapping, so tests never depend on the process environment."""
    environ = {"TOLLGATE_API_KEYS": "test-key", "TOLLGATE_TOKENS_PER_MINUTE": "1000"}
    environ.update(overrides)
    return Settings.from_env(environ)
