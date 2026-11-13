"""Expected values below are worked out by hand from ADR-0007, never computed by the code."""

import itertools
from typing import Any

import pytest

from app.api.models import ChatRequest
from app.limits.estimate import HeuristicEstimator, TokenEstimator, reserved_tokens

ESTIMATOR = HeuristicEstimator()


def make_request(*contents: str, role: str = "user", **overrides: Any) -> ChatRequest:
    payload: dict[str, Any] = {
        "model": "mock-1",
        "messages": [{"role": role, "content": content} for content in contents],
    }
    payload.update(overrides)
    return ChatRequest.model_validate(payload)


def make_named_request(content: str, name: str | None) -> ChatRequest:
    message: dict[str, Any] = {"role": "user", "content": content, "name": name}
    return ChatRequest.model_validate({"model": "mock-1", "messages": [message]})


def estimate(request: ChatRequest) -> int:
    return ESTIMATOR.estimate_input_tokens(request)


def test_one_empty_message_estimates_6() -> None:
    # 0 characters -> 0 tokens, +3 for the message, +3 for the reply.
    assert estimate(make_request("")) == 6


@pytest.mark.parametrize(
    ("characters", "expected_tokens"),
    [(1, 7), (2, 7), (3, 7), (4, 7), (5, 8), (8, 8), (9, 9), (12, 9), (13, 10)],
)
def test_content_length_boundaries_at_the_divisor(characters: int, expected_tokens: int) -> None:
    assert estimate(make_request("a" * characters)) == expected_tokens


def test_name_adds_exactly_one_token() -> None:
    assert estimate(make_named_request("abcd", None)) == 7
    assert estimate(make_named_request("abcd", "bob")) == 8
    assert estimate(make_named_request("abcde", None)) == 8
    assert estimate(make_named_request("abcde", "bob")) == 9


def test_an_empty_string_name_still_counts_as_present() -> None:
    assert estimate(make_named_request("", None)) == 6
    assert estimate(make_named_request("", "")) == 7


@pytest.mark.parametrize("name", ["a", "a" * 40])
def test_the_length_of_the_name_does_not_change_the_estimate(name: str) -> None:
    assert estimate(make_named_request("abcd", name)) == 8


def test_each_extra_message_adds_its_own_share_plus_three() -> None:
    # reply 3; "" -> 0+3; "abcd" -> 1+3; "abcde" -> 2+3.
    assert estimate(make_request("")) == 6
    assert estimate(make_request("", "abcd")) == 10
    assert estimate(make_request("", "abcd", "abcde")) == 15


def test_the_reply_overhead_is_added_once_however_many_messages() -> None:
    assert estimate(make_request("", "", "")) == 12


@pytest.mark.parametrize("role", ["system", "user", "assistant"])
def test_every_role_counts_the_same(role: str) -> None:
    assert estimate(make_request("abcd", role=role)) == 7


def test_characters_are_python_string_length_not_bytes() -> None:
    two_byte = chr(0xE9)  # one character, two bytes in UTF-8
    outside_bmp = chr(0x1F600)  # one character, four bytes in UTF-8, two UTF-16 units
    assert estimate(make_request(two_byte * 4)) == 7
    assert estimate(make_request(two_byte * 5)) == 8
    assert estimate(make_request(outside_bmp * 4)) == 7
    assert estimate(make_request(outside_bmp * 5)) == 8


@pytest.mark.parametrize(
    ("content", "expected_tokens"),
    [
        ("    ", 7),  # 4 spaces -> 1 token
        ("     ", 8),  # 5 spaces -> 2 tokens
        (" a ", 7),  # 3 characters, leading and trailing spaces count
        ("\n\t\r\n", 7),  # 4 whitespace characters
        ("\n" * 9, 9),  # 9 characters -> 3 tokens
    ],
)
def test_whitespace_counts_as_characters(content: str, expected_tokens: int) -> None:
    assert estimate(make_request(content)) == expected_tokens


def test_combining_marks_count_as_separate_characters() -> None:
    accented = "e" + chr(0x301)  # two code points, one visible letter
    assert estimate(make_request(accented * 2)) == 7  # 4 characters
    assert estimate(make_request(accented + "e")) == 7  # 3 characters
    assert estimate(make_request(accented * 2 + "e")) == 8  # 5 characters


def test_the_estimate_never_decreases_when_content_grows_by_one_character() -> None:
    estimates = [estimate(make_request("a" * length)) for length in range(201)]
    assert estimates[0] == 6
    assert estimates[200] == 56  # 3 reply + 3 message + 50 content
    for shorter, longer in itertools.pairwise(estimates):
        assert longer - shorter in (0, 1)


def test_the_estimate_matches_a_hand_computed_full_example() -> None:
    # "You are helpful." is 16 characters: 4 + 3 = 7.  "Hello" is 5: 2 + 3, +1 for the name = 6.
    # Total with the reply overhead: 3 + 7 + 6 = 16.
    request = ChatRequest.model_validate(
        {
            "model": "mock-1",
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hello", "name": "bob"},
            ],
        }
    )
    assert estimate(request) == 16


def test_max_tokens_alone_is_added_to_the_estimate() -> None:
    assert reserved_tokens(make_request("abcd", max_tokens=100), ESTIMATOR) == 107


def test_max_completion_tokens_alone_is_added_to_the_estimate() -> None:
    assert reserved_tokens(make_request("abcd", max_completion_tokens=50), ESTIMATOR) == 57


def test_max_completion_tokens_wins_when_both_are_given() -> None:
    wins = make_request("abcd", max_completion_tokens=50, max_tokens=100)
    assert reserved_tokens(wins, ESTIMATOR) == 57
    reversed_values = make_request("abcd", max_completion_tokens=100, max_tokens=50)
    assert reserved_tokens(reversed_values, ESTIMATOR) == 107


def test_neither_max_field_gives_the_estimate_alone() -> None:
    assert reserved_tokens(make_request("abcd"), ESTIMATOR) == 7
    explicit = make_request("abcd", max_tokens=None, max_completion_tokens=None)
    assert reserved_tokens(explicit, ESTIMATOR) == 7


def test_the_given_estimator_is_the_one_used() -> None:
    class FixedEstimator:
        def estimate_input_tokens(self, request: ChatRequest) -> int:
            return 7

    assert reserved_tokens(make_request("a" * 1000, max_tokens=10), FixedEstimator()) == 17


def test_the_heuristic_estimator_satisfies_the_protocol() -> None:
    # The assignment is checked by mypy strict, which fails if the signature drifts from the
    # protocol; the call only makes the test do something at run time.
    estimator: TokenEstimator = HeuristicEstimator()
    assert estimator.estimate_input_tokens(make_request("")) == 6


def test_a_huge_max_tokens_is_added_exactly_with_no_cap() -> None:
    assert reserved_tokens(make_request("abcd", max_tokens=10**12), ESTIMATOR) == 10**12 + 7
