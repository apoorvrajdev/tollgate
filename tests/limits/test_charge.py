"""The capped settle charge (T-208, ADR-0012)."""

import random

import pytest

from app.limits.charge import charged_tokens

LIMIT = 60
PROPERTY_SEED = 20261114
PROPERTY_PAIRS = 1000
MIN_DRAWS_PER_STRATUM = 200


@pytest.mark.parametrize("reported", [0, LIMIT - 1, LIMIT])
def test_a_count_at_most_the_limit_is_charged_as_reported(reported: int) -> None:
    assert charged_tokens(reported, LIMIT) == reported


@pytest.mark.parametrize("reported", [LIMIT + 1, 10**30])
def test_a_count_above_the_limit_is_charged_at_the_limit(reported: int) -> None:
    assert charged_tokens(reported, LIMIT) == LIMIT


@pytest.mark.parametrize("reported", [-1, -(10**30)])
def test_a_negative_count_is_returned_unchanged_so_settle_still_rejects_it(reported: int) -> None:
    assert charged_tokens(reported, LIMIT) == reported


def test_the_charge_is_never_above_the_limit_and_equals_any_count_within_it() -> None:
    source = random.Random(PROPERTY_SEED)
    draws = {"negative": 0, "within": 0, "above": 0}
    for _ in range(PROPERTY_PAIRS):
        limit_tokens = source.randint(1, 2**63)
        stratum = source.choice(sorted(draws))
        if stratum == "negative":
            reported_tokens = source.randint(-(2**63), -1)
        elif stratum == "within":
            reported_tokens = source.randint(0, limit_tokens)
        else:
            reported_tokens = source.randint(limit_tokens + 1, 2**64 + 1)
        draws[stratum] += 1
        charge = charged_tokens(reported_tokens, limit_tokens)
        assert charge <= limit_tokens, (reported_tokens, limit_tokens)
        if reported_tokens <= limit_tokens:
            assert charge == reported_tokens, (reported_tokens, limit_tokens)
        else:
            assert charge == limit_tokens, (reported_tokens, limit_tokens)
    # Every stratum is drawn often enough that the property is not vacuous for any of them.
    assert min(draws.values()) >= MIN_DRAWS_PER_STRATUM, draws
