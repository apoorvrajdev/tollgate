"""The reply checks the HTTP adapters share (ADR-0010, T-210).

Every check is called with status 201, so a check that raises with a fixed 200 fails. Every
rejection is a `bad_response` that holds only the kind and the status and has no `__context__`.
"""

from collections.abc import Callable

import pytest

from app.providers import fields
from app.providers.errors import ProviderError

STATUS = 201
LONE_SURROGATE = "\ud800"
HUGE_INT = 10**30


def rejection(check: Callable[[], object]) -> ProviderError:
    with pytest.raises(ProviderError) as caught:
        check()
    error = caught.value
    assert (error.kind, error.status_code, error.retryable) == ("bad_response", STATUS, False)
    assert str(error) == f"provider failed: bad_response (HTTP {STATUS})"
    assert error.__context__ is None
    assert error.__cause__ is None
    return error


# text


@pytest.mark.parametrize(
    "value",
    ["", "hi", " ", "héllo", "日本語", "\U0001f600", "a\u0000b"],
    ids=["empty", "ascii", "space", "latin", "cjk", "emoji", "nul"],
)
def test_text_returns_a_string_that_encodes_as_utf8_unchanged(value: str) -> None:
    assert fields.text(value, STATUS) == value


@pytest.mark.parametrize(
    "value",
    [None, 0, 1, 1.5, True, [], ["a"], {}, b"x"],
    ids=["none", "zero", "one", "float", "bool", "list", "list-of-str", "dict", "bytes"],
)
def test_text_rejects_a_non_string(value: object) -> None:
    rejection(lambda: fields.text(value, STATUS))


@pytest.mark.parametrize(
    "value",
    [LONE_SURROGATE, "a\udfffb", "\udbff", "ok" + LONE_SURROGATE],
    ids=["high", "low-in-text", "last-high", "trailing"],
)
def test_text_rejects_a_lone_surrogate_without_a_context(value: str) -> None:
    rejection(lambda: fields.text(value, STATUS))


# non_empty_text


@pytest.mark.parametrize("value", ["a", " ", "héllo"], ids=["char", "space", "latin"])
def test_non_empty_text_accepts_any_non_empty_string_unchanged(value: str) -> None:
    assert fields.non_empty_text(value, STATUS) == value


def test_non_empty_text_rejects_the_empty_string() -> None:
    rejection(lambda: fields.non_empty_text("", STATUS))


@pytest.mark.parametrize(
    "value", [None, 1, [], LONE_SURROGATE], ids=["none", "int", "list", "surrogate"]
)
def test_non_empty_text_keeps_the_checks_of_text(value: object) -> None:
    rejection(lambda: fields.non_empty_text(value, STATUS))


# whole_number


@pytest.mark.parametrize("value", [0, 1, 2**63, HUGE_INT], ids=["zero", "one", "2^63", "huge"])
def test_whole_number_accepts_zero_and_large_ints_unchanged(value: int) -> None:
    result = fields.whole_number(value, STATUS)
    assert result == value
    assert type(result) is int


@pytest.mark.parametrize(
    "value",
    [-1, -(2**70), True, False, 1.0, 0.0, 1.5, float("nan"), "1", None, [], {}],
    ids=[
        "minus-1",
        "minus-huge",
        "true",
        "false",
        "float-1",
        "float-0",
        "float-1.5",
        "nan",
        "string",
        "none",
        "list",
        "dict",
    ],
)
def test_whole_number_rejects_what_is_not_an_int_of_at_least_0(value: object) -> None:
    rejection(lambda: fields.whole_number(value, STATUS))


# required_count


@pytest.mark.parametrize(
    "mapping",
    [{}, {"other": 3}, {"Key": 3}],
    ids=["empty", "other-key", "other-case"],
)
def test_required_count_rejects_an_absent_key(mapping: dict[str, object]) -> None:
    rejection(lambda: fields.required_count(mapping, "key", STATUS))


@pytest.mark.parametrize(
    "value",
    [-1, True, False, 1.5, 1.0, "1", None],
    ids=["minus-1", "true", "false", "float", "float-1", "string", "none"],
)
def test_required_count_rejects_a_present_invalid_value(value: object) -> None:
    rejection(lambda: fields.required_count({"key": value}, "key", STATUS))


@pytest.mark.parametrize("value", [0, 7, 2**40], ids=["zero", "seven", "2^40"])
def test_required_count_returns_a_present_valid_count(value: int) -> None:
    assert fields.required_count({"key": value, "other": -1}, "key", STATUS) == value
