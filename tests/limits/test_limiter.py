import dataclasses

import pytest

from app.limits.limiter import Decision


def test_decision_is_frozen() -> None:
    decision = Decision(True, 100, 50, None, 10)
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.allowed = False  # type: ignore[misc]


def test_decisions_compare_by_value() -> None:
    assert Decision(True, 100, 50, None, 10) == Decision(True, 100, 50, None, 10)
    assert Decision(True, 100, 50, None, 10) != Decision(True, 100, 50, None, 11)
    assert Decision(False, 100, 50, 1, 10) != Decision(False, 100, 50, None, 10)


def test_decision_has_exactly_the_five_documented_fields() -> None:
    names = [field.name for field in dataclasses.fields(Decision)]
    assert names == [
        "allowed",
        "limit_tokens",
        "remaining_tokens",
        "retry_after_seconds",
        "reset_seconds",
    ]
