"""Gateway configuration, read from environment variables and validated at startup.

Error messages name the variable and a fixed reason. They never include a value, because values
can be API keys or a Redis URL with a password.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from pydantic import SecretStr

from app.routing.config import RouteTable, RouteTableError, load_route_table

API_KEYS_VAR = "TOLLGATE_API_KEYS"
TOKENS_PER_MINUTE_VAR = "TOLLGATE_TOKENS_PER_MINUTE"
CAPACITY_TOKENS_VAR = "TOLLGATE_CAPACITY_TOKENS"
LIMITER_BACKEND_VAR = "TOLLGATE_LIMITER_BACKEND"
REDIS_URL_VAR = "TOLLGATE_REDIS_URL"

CACHE_EMBEDDER_VAR = "TOLLGATE_CACHE_EMBEDDER"
CACHE_EMBEDDER_MODEL_VAR = "TOLLGATE_CACHE_EMBEDDER_MODEL"
CACHE_EMBEDDER_URL_VAR = "TOLLGATE_CACHE_EMBEDDER_URL"
CACHE_SIMILARITY_THRESHOLD_VAR = "TOLLGATE_CACHE_SIMILARITY_THRESHOLD"
CACHE_TTL_SECONDS_VAR = "TOLLGATE_CACHE_TTL_SECONDS"
CACHE_MAX_ENTRIES_VAR = "TOLLGATE_CACHE_MAX_ENTRIES"
# The variables that need TOLLGATE_CACHE_EMBEDDER, in the order errors are reported.
_CACHE_DEPENDENT_VARS = (
    CACHE_EMBEDDER_MODEL_VAR,
    CACHE_EMBEDDER_URL_VAR,
    CACHE_SIMILARITY_THRESHOLD_VAR,
    CACHE_TTL_SECONDS_VAR,
    CACHE_MAX_ENTRIES_VAR,
)

DEFAULT_CACHE_EMBEDDER_URL = "http://localhost:11434"
MIN_SIMILARITY_THRESHOLD = 0.5
MIN_TTL_SECONDS = 60
MAX_TTL_SECONDS = 604_800
DEFAULT_TTL_SECONDS = 3_600
MIN_CACHE_ENTRIES = 1
MAX_CACHE_ENTRIES = 100_000
DEFAULT_CACHE_ENTRIES = 1_000

LimiterBackend = Literal["memory", "redis"]

# At most 18 digits: bounded, so int() cannot hit Python's digit limit and escape as a ValueError.
_ASCII_DIGITS = re.compile(r"[0-9]{1,18}")
# A decimal of at most 4 places, or 1 or 1.0 to 1.0000. The pattern is also the upper bound: it
# matches nothing above 1. `[0-9]` is ASCII only.
_THRESHOLD = re.compile(r"0\.[0-9]{1,4}|1|1\.0{1,4}")


class SettingsError(ValueError):
    """Invalid configuration. The message is '<VARIABLE>: <reason>' and never shows a value."""

    def __init__(self, variable: str, reason: str) -> None:
        super().__init__(f"{variable}: {reason}")
        self.variable = variable


@dataclass(frozen=True, slots=True)
class CacheSettings:
    embedder: Literal["ollama"]
    embedder_model: str
    embedder_url: SecretStr
    similarity_threshold: float
    ttl_seconds: int
    max_entries: int


@dataclass(frozen=True, slots=True)
class Settings:
    api_keys: tuple[SecretStr, ...]
    tokens_per_minute: int
    capacity_tokens: int
    limiter_backend: LimiterBackend
    redis_url: SecretStr | None
    route_table: RouteTable
    cache: CacheSettings | None

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
        try:
            route_table = load_route_table(environ)
        except RouteTableError as error:
            raise SettingsError(error.variable, error.reason) from None
        cache = _parse_cache(environ)
        return cls(
            api_keys=api_keys,
            tokens_per_minute=tokens_per_minute,
            capacity_tokens=capacity_tokens,
            limiter_backend=limiter_backend,
            redis_url=redis_url,
            route_table=route_table,
            cache=cache,
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


def _parse_cache(environ: Mapping[str, str]) -> CacheSettings | None:
    """The cache settings, or None when TOLLGATE_CACHE_EMBEDDER is unset (ADR-0014, ADR-0015).

    A cache variable set while the embedder is unset (even blank) is an error, so a half-configured
    cache never starts silently off. The first error in declaration order is reported.
    """
    embedder = environ.get(CACHE_EMBEDDER_VAR)
    if embedder is None:
        for name in _CACHE_DEPENDENT_VARS:
            if name in environ:
                raise SettingsError(name, f"is set but {CACHE_EMBEDDER_VAR} is not")
        return None
    if embedder != "ollama":
        raise SettingsError(CACHE_EMBEDDER_VAR, "must be 'ollama'")
    return CacheSettings(
        embedder="ollama",
        embedder_model=_parse_cache_model(environ.get(CACHE_EMBEDDER_MODEL_VAR)),
        embedder_url=_parse_cache_url(environ.get(CACHE_EMBEDDER_URL_VAR)),
        similarity_threshold=_parse_threshold(environ.get(CACHE_SIMILARITY_THRESHOLD_VAR)),
        ttl_seconds=_parse_bounded_int(
            CACHE_TTL_SECONDS_VAR,
            environ.get(CACHE_TTL_SECONDS_VAR),
            DEFAULT_TTL_SECONDS,
            MIN_TTL_SECONDS,
            MAX_TTL_SECONDS,
        ),
        max_entries=_parse_bounded_int(
            CACHE_MAX_ENTRIES_VAR,
            environ.get(CACHE_MAX_ENTRIES_VAR),
            DEFAULT_CACHE_ENTRIES,
            MIN_CACHE_ENTRIES,
            MAX_CACHE_ENTRIES,
        ),
    )


def _parse_cache_model(raw: str | None) -> str:
    if raw is None:
        raise SettingsError(CACHE_EMBEDDER_MODEL_VAR, "is required when the cache is on")
    text = raw.strip()
    if not text:
        raise SettingsError(CACHE_EMBEDDER_MODEL_VAR, "must not be blank")
    return text


def _parse_cache_url(raw: str | None) -> SecretStr:
    if raw is None:
        return SecretStr(DEFAULT_CACHE_EMBEDDER_URL)
    text = raw.strip()
    if not text:  # set but blank is an error, never the default
        raise SettingsError(CACHE_EMBEDDER_URL_VAR, "must not be blank")
    return SecretStr(text)


def _parse_threshold(raw: str | None) -> float:
    if raw is None:
        raise SettingsError(CACHE_SIMILARITY_THRESHOLD_VAR, "is required when the cache is on")
    text = raw.strip()
    reason = "must be a decimal from 0.5 to 1 with at most 4 decimal places"
    if _THRESHOLD.fullmatch(text) is None:
        raise SettingsError(CACHE_SIMILARITY_THRESHOLD_VAR, reason)
    value = float(text)
    if value < MIN_SIMILARITY_THRESHOLD:
        raise SettingsError(CACHE_SIMILARITY_THRESHOLD_VAR, reason)
    return value


def _parse_bounded_int(
    variable: str, raw: str | None, default: int, minimum: int, maximum: int
) -> int:
    """A whole number from `minimum` to `maximum`; unset is `default`, set but blank is an error."""
    if raw is None:
        return default
    text = raw.strip()
    reason = f"must be a whole number from {minimum:,} to {maximum:,}"
    if _ASCII_DIGITS.fullmatch(text) is None:
        raise SettingsError(variable, reason)
    value = int(text)
    if not minimum <= value <= maximum:
        raise SettingsError(variable, reason)
    return value
