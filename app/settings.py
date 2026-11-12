"""Gateway configuration, read from environment variables and validated at startup.

Error messages name the variable and a fixed reason. They never include a value, because values
can be API keys or a Redis URL with a password.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from pydantic import SecretStr

API_KEYS_VAR = "TOLLGATE_API_KEYS"
TOKENS_PER_MINUTE_VAR = "TOLLGATE_TOKENS_PER_MINUTE"
CAPACITY_TOKENS_VAR = "TOLLGATE_CAPACITY_TOKENS"
LIMITER_BACKEND_VAR = "TOLLGATE_LIMITER_BACKEND"
REDIS_URL_VAR = "TOLLGATE_REDIS_URL"

LimiterBackend = Literal["memory", "redis"]

# At most 18 digits: bounded, so int() cannot hit Python's digit limit and escape as a ValueError.
_ASCII_DIGITS = re.compile(r"[0-9]{1,18}")


class SettingsError(ValueError):
    """Invalid configuration. The message is '<VARIABLE>: <reason>' and never shows a value."""

    def __init__(self, variable: str, reason: str) -> None:
        super().__init__(f"{variable}: {reason}")
        self.variable = variable


@dataclass(frozen=True, slots=True)
class Settings:
    api_keys: tuple[SecretStr, ...]
    tokens_per_minute: int
    capacity_tokens: int
    limiter_backend: LimiterBackend
    redis_url: SecretStr | None

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> "Settings":
        api_keys = _parse_api_keys(environ.get(API_KEYS_VAR))
        tokens_per_minute = _parse_positive_int(
            TOKENS_PER_MINUTE_VAR, environ.get(TOKENS_PER_MINUTE_VAR)
        )
        capacity_raw = environ.get(CAPACITY_TOKENS_VAR)
        capacity_tokens = (
            tokens_per_minute
            if capacity_raw is None
            else _parse_positive_int(CAPACITY_TOKENS_VAR, capacity_raw)
        )
        limiter_backend = _parse_backend(environ.get(LIMITER_BACKEND_VAR))
        redis_url = _parse_redis_url(limiter_backend, environ.get(REDIS_URL_VAR))
        return cls(
            api_keys=api_keys,
            tokens_per_minute=tokens_per_minute,
            capacity_tokens=capacity_tokens,
            limiter_backend=limiter_backend,
            redis_url=redis_url,
        )


def _parse_api_keys(raw: str | None) -> tuple[SecretStr, ...]:
    if raw is None or not raw.strip():
        raise SettingsError(API_KEYS_VAR, "is required and must contain at least one key")
    pieces = [piece.strip() for piece in raw.split(",")]
    if any(not piece for piece in pieces):
        raise SettingsError(API_KEYS_VAR, "contains an empty key")
    return tuple(SecretStr(piece) for piece in pieces)


def _parse_positive_int(variable: str, raw: str | None) -> int:
    if raw is None:
        raise SettingsError(variable, "is required")
    text = raw.strip()
    if _ASCII_DIGITS.fullmatch(text) is None:
        raise SettingsError(variable, "must be a positive integer")
    value = int(text)
    if value <= 0:
        raise SettingsError(variable, "must be greater than zero")
    return value


def _parse_backend(raw: str | None) -> LimiterBackend:
    if raw is None or raw == "memory":
        return "memory"
    if raw == "redis":
        return "redis"
    raise SettingsError(LIMITER_BACKEND_VAR, "must be 'memory' or 'redis'")


def _parse_redis_url(backend: LimiterBackend, raw: str | None) -> SecretStr | None:
    if backend != "redis":
        return None
    if raw is None or not raw.strip():
        raise SettingsError(REDIS_URL_VAR, "is required when the limiter backend is 'redis'")
    return SecretStr(raw.strip())
