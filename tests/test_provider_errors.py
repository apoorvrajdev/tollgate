from typing import get_args

import pytest

from app.providers.errors import ProviderError, ProviderErrorKind


@pytest.mark.parametrize(
    ("kind", "status_code", "retryable"),
    [
        ("connection", None, True),
        ("timeout", None, True),
        ("rate_limited", 429, True),
        ("rate_limited", None, True),
        ("upstream_status", 404, False),
        ("upstream_status", 499, False),
        ("upstream_status", 500, True),
        ("upstream_status", 501, True),
        ("upstream_status", 529, True),
        ("upstream_status", 599, True),
        ("upstream_status", None, False),
        ("bad_response", None, False),
        ("bad_response", 200, False),
    ],
)
def test_retryable_is_exact_for_every_kind_and_status(
    kind: ProviderErrorKind, status_code: int | None, retryable: bool
) -> None:
    assert ProviderError(kind, status_code).retryable is retryable


def test_message_holds_only_the_kind_and_the_status() -> None:
    with_status = ProviderError("upstream_status", 503)
    assert str(with_status) == "provider failed: upstream_status (HTTP 503)"
    assert (with_status.kind, with_status.status_code) == ("upstream_status", 503)
    without_status = ProviderError("timeout")
    assert str(without_status) == "provider failed: timeout"
    assert (without_status.kind, without_status.status_code) == ("timeout", None)


def test_the_kinds_are_exactly_the_five_in_adr_0010() -> None:
    assert get_args(ProviderErrorKind) == (
        "connection",
        "timeout",
        "rate_limited",
        "upstream_status",
        "bad_response",
    )


def test_provider_error_is_an_exception() -> None:
    with pytest.raises(ProviderError, match=r"^provider failed: connection$"):
        raise ProviderError("connection")
