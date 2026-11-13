import pytest

from app.api.limit_headers import format_duration, limit_headers
from app.limits.limiter import Decision

HEADER_NAMES = (
    "x-ratelimit-limit-tokens",
    "x-ratelimit-remaining-tokens",
    "x-ratelimit-reset-tokens",
    "Retry-After",
)


def header_values(headers: dict[str, str]) -> tuple[str | None, ...]:
    return tuple(headers.get(name) for name in HEADER_NAMES)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "0s"),
        (1, "1s"),
        (45, "45s"),
        (59, "59s"),
        (60, "1m0s"),
        (61, "1m1s"),
        (119, "1m59s"),
        (120, "2m0s"),
        (360, "6m0s"),
        (3599, "59m59s"),
        (3600, "60m0s"),
    ],
)
def test_format_duration_writes_seconds_below_a_minute_and_minutes_from_one(
    seconds: int, expected: str
) -> None:
    assert format_duration(seconds) == expected


def test_format_duration_rejects_negative_seconds() -> None:
    with pytest.raises(ValueError, match="negative"):
        format_duration(-1)


def test_limit_headers_map_each_decision_field_to_its_own_header() -> None:
    # Every field has a distinct value, so a header built from the wrong field cannot pass.
    decision = Decision(
        allowed=False,
        limit_tokens=1000,
        remaining_tokens=7,
        retry_after_seconds=3,
        reset_seconds=100,
    )
    assert header_values(limit_headers(decision)) == ("1000", "7", "1m40s", "3")


def test_limit_headers_never_show_remaining_below_zero() -> None:
    decision = Decision(
        allowed=False,
        limit_tokens=1000,
        remaining_tokens=-5,
        retry_after_seconds=4,
        reset_seconds=200,
    )
    assert limit_headers(decision)["x-ratelimit-remaining-tokens"] == "0"


def test_limit_headers_keep_a_remaining_of_exactly_zero() -> None:
    decision = Decision(
        allowed=True, limit_tokens=10, remaining_tokens=0, retry_after_seconds=None, reset_seconds=1
    )
    assert limit_headers(decision)["x-ratelimit-remaining-tokens"] == "0"


def test_allowed_decision_gives_exactly_the_three_limit_headers() -> None:
    decision = Decision(
        allowed=True,
        limit_tokens=1000,
        remaining_tokens=989,
        retry_after_seconds=None,
        reset_seconds=2,
    )
    headers = limit_headers(decision)
    assert set(headers) == set(HEADER_NAMES[:3])
    assert header_values(headers) == ("1000", "989", "2s", None)


def test_oversized_refusal_gives_no_retry_after() -> None:
    # A refusal with no retry hint: waiting can never help, so Retry-After must not be sent.
    decision = Decision(
        allowed=False,
        limit_tokens=1000,
        remaining_tokens=1000,
        retry_after_seconds=None,
        reset_seconds=0,
    )
    headers = limit_headers(decision)
    assert set(headers) == set(HEADER_NAMES[:3])
    assert header_values(headers) == ("1000", "1000", "0s", None)
