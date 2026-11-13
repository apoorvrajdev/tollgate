"""The ADR-0008 rate-limit headers, built from a limiter Decision.

Every response to an authenticated chat completion that reached the limiter carries the three
`x-ratelimit-*-tokens` headers. `Retry-After` is added only to a refusal that can succeed later.
"""

from typing import Any

from app.limits.limiter import Decision

LIMIT_TOKENS_HEADER = "x-ratelimit-limit-tokens"
REMAINING_TOKENS_HEADER = "x-ratelimit-remaining-tokens"
RESET_TOKENS_HEADER = "x-ratelimit-reset-tokens"
RETRY_AFTER_HEADER = "Retry-After"

SECONDS_PER_MINUTE = 60


def format_duration(seconds: int) -> str:
    """`<s>s` below a minute, `<m>m<s>s` otherwise: 0s, 45s, 1m0s, 6m0s.

    An hour or more is written in minutes (3600 is `60m0s`, not `1h0m0s`). That is ADR-0008's
    grammar taken literally and accepted as is; reset times of an hour are unlikely in practice.
    """
    if seconds < 0:
        raise ValueError("seconds must not be negative")
    if seconds < SECONDS_PER_MINUTE:
        return f"{seconds}s"
    minutes, rest_seconds = divmod(seconds, SECONDS_PER_MINUTE)
    return f"{minutes}m{rest_seconds}s"


def limit_headers(decision: Decision) -> dict[str, str]:
    """The headers for a response built after `decision`.

    Remaining is clamped at 0 here as well, because a Decision does not validate its fields.
    """
    headers = {
        LIMIT_TOKENS_HEADER: str(decision.limit_tokens),
        REMAINING_TOKENS_HEADER: str(max(0, decision.remaining_tokens)),
        RESET_TOKENS_HEADER: format_duration(decision.reset_seconds),
    }
    if decision.retry_after_seconds is not None:
        headers[RETRY_AFTER_HEADER] = str(decision.retry_after_seconds)
    return headers


# The headers as documented in the OpenAPI document (ADR-0008).
LIMIT_HEADERS_OPENAPI: dict[str, dict[str, Any]] = {
    LIMIT_TOKENS_HEADER: {
        "description": "The bucket capacity in tokens",
        "schema": {"type": "integer"},
    },
    REMAINING_TOKENS_HEADER: {
        "description": "Tokens left after this request's reservation, rounded down, never below 0",
        "schema": {"type": "integer"},
    },
    RESET_TOKENS_HEADER: {
        "description": (
            "Time until the bucket is full again, rounded up to whole seconds: '<s>s' below a "
            "minute, '<m>m<s>s' otherwise (0s, 45s, 6m0s)"
        ),
        "schema": {"type": "string"},
    },
}

RETRY_AFTER_OPENAPI: dict[str, dict[str, Any]] = {
    RETRY_AFTER_HEADER: {
        "description": (
            "Whole seconds, rounded up, until the same request can succeed. Absent when the "
            "request is larger than the limit"
        ),
        "schema": {"type": "integer"},
    }
}
