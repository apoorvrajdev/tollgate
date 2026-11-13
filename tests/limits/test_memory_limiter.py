import asyncio

import pytest

from app.clock import Clock
from app.limits.limiter import RateLimiter
from app.limits.memory import InMemoryRateLimiter
from tests.fakes import FakeClock
from tests.limits.behaviour import BEHAVIOUR_CASES, BehaviourCase, run_behaviour_case


def make_memory_limiter(clock: Clock, tokens_per_minute: int, capacity_tokens: int) -> RateLimiter:
    return InMemoryRateLimiter(clock, tokens_per_minute, capacity_tokens)


@pytest.mark.parametrize(
    "behaviour_case", BEHAVIOUR_CASES, ids=[case.__name__ for case in BEHAVIOUR_CASES]
)
def test_in_memory_limiter_behaviour(behaviour_case: BehaviourCase) -> None:
    run_behaviour_case(behaviour_case, make_memory_limiter)


def test_the_shared_suite_has_not_shrunk_and_its_names_are_unique() -> None:
    # Raise the floor when cases are added; lowering it means a case was dropped and needs review.
    names = [case.__name__ for case in BEHAVIOUR_CASES]
    assert len(names) >= 45
    assert len(set(names)) == len(names)


@pytest.mark.parametrize(
    ("tokens_per_minute", "capacity_tokens"), [(0, 100), (-1, 100), (60, 0), (60, -1)]
)
def test_the_constructor_rejects_a_non_positive_rate_or_capacity(
    tokens_per_minute: int, capacity_tokens: int
) -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        InMemoryRateLimiter(FakeClock(), tokens_per_minute, capacity_tokens)


class CountingClock(FakeClock):
    """Counts reads, and records whether a watched lock is held at each read."""

    def __init__(self) -> None:
        super().__init__(1000.0)
        self.reads = 0
        self.watched_lock: asyncio.Lock | None = None
        self.lock_held_at_read: list[bool] = []

    def now_seconds(self) -> float:
        self.reads += 1
        if self.watched_lock is not None:
            self.lock_held_at_read.append(self.watched_lock.locked())
        return super().now_seconds()


def test_each_call_reads_the_clock_exactly_once_and_while_holding_the_lock() -> None:
    clock = CountingClock()
    limiter = InMemoryRateLimiter(clock, 60, 100)
    clock.watched_lock = limiter._lock

    async def calls() -> list[int]:
        reads_after_each_call: list[int] = []
        await limiter.reserve("k", 10)  # allowed
        reads_after_each_call.append(clock.reads)
        await limiter.reserve("k", 100)  # refused, can succeed later
        reads_after_each_call.append(clock.reads)
        await limiter.reserve("k", 101)  # larger than the capacity
        reads_after_each_call.append(clock.reads)
        await limiter.settle("k", 10, 5)
        reads_after_each_call.append(clock.reads)
        return reads_after_each_call

    assert asyncio.run(calls()) == [1, 2, 3, 4]
    assert clock.lock_held_at_read == [True, True, True, True]


class SteppableClock:
    def __init__(self, now_seconds: float) -> None:
        self.now = now_seconds

    def now_seconds(self) -> float:
        return self.now


def test_a_clock_that_steps_back_gives_no_refill_and_no_second_refill() -> None:
    clock = SteppableClock(1000.0)
    limiter = InMemoryRateLimiter(clock, 60, 100)

    async def scenario() -> None:
        assert (await limiter.reserve("k", 100)).allowed  # drained at t=1000
        clock.now = 990.0  # a time correction ten seconds back
        stepped_back = await limiter.reserve("k", 1)
        assert (stepped_back.allowed, stepped_back.retry_after_seconds) == (False, 1)
        clock.now = 1000.0  # back at the old timestamp: still nothing to refill
        assert not (await limiter.reserve("k", 1)).allowed
        clock.now = 1001.0
        assert (await limiter.reserve("k", 1)).allowed

    asyncio.run(scenario())
