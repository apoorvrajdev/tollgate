"""The behaviour every rate limiter must have: in memory, on fakeredis (T-106), on Redis (T-107).

Each case is an async function taking an Env. A limiter's test module passes a factory and runs
every case in BEHAVIOUR_CASES through run_behaviour_case. Pytest cannot run async tests without a
plugin, so each case is one asyncio.run; the factory is called inside the running loop, so a client
that is bound to its first event loop (fakeredis) works.

The factory contract: every call returns a limiter with its own empty state. A limiter that keeps
its state in a shared store (Redis) must use a fresh key prefix per call, because several cases
build two limiters with different rates and then use the same key on each. The case
case_two_limiters_from_the_factory_do_not_share_state checks this. A factory may also pass a
`cleanup` coroutine function to run_behaviour_case, which runs inside the loop after the case, to
close any client it created.

Notation: tpm is tokens per minute and cap is capacity in tokens. tpm 60 refills 1 token per second,
600 refills 10, 6000 refills 100, 60000 refills 1000, 100 refills 5/3, 90 refills 3/2, 7 refills
7/60, 11 refills 11/60 and 1 refills 1/60. Every expected value is worked out by hand from ADR-0007
and ADR-0008, never computed by the limiter. The clock only moves by multiples of 0.25 seconds,
which are exact in binary and whole milliseconds. A "drained" bucket has been reserved down to a
balance of 0. A "probe" is a reservation of 0 tokens, which takes nothing and shows the balance as
remaining_tokens.
"""

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

import pytest

from app.clock import Clock
from app.limits.limiter import Decision, RateLimiter
from tests.fakes import FakeClock

START_SECONDS = 1000.0  # not 0, so a bucket timestamp of 0 is a visible mistake

LimiterFactory = Callable[[Clock, int, int], RateLimiter]


@dataclass
class Env:
    clock: FakeClock
    make: Callable[[int, int], RateLimiter]  # (tokens_per_minute, capacity_tokens)


BehaviourCase = Callable[[Env], Coroutine[Any, Any, None]]
BEHAVIOUR_CASES: list[BehaviourCase] = []


def case(function: BehaviourCase) -> BehaviourCase:
    BEHAVIOUR_CASES.append(function)
    return function


def run_behaviour_case(
    behaviour_case: BehaviourCase,
    factory: LimiterFactory,
    cleanup: Callable[[], Coroutine[Any, Any, None]] | None = None,
) -> None:
    clock = FakeClock(START_SECONDS)
    env = Env(
        clock, lambda tokens_per_minute, capacity: factory(clock, tokens_per_minute, capacity)
    )

    async def run() -> None:
        try:
            await behaviour_case(env)
        finally:
            if cleanup is not None:
                await cleanup()

    asyncio.run(run())


async def probe(limiter: RateLimiter, key: str = "k") -> Decision:
    return await limiter.reserve(key, 0)


async def drain(limiter: RateLimiter, key: str, capacity: int) -> None:
    decision = await limiter.reserve(key, capacity)
    assert decision.allowed


# --- a new key, the boundary and the exact wait -------------------------------------------------


@case
async def case_new_key_starts_full(env: Env) -> None:
    limiter = env.make(60, 100)
    assert await probe(limiter) == Decision(True, 100, 100, None, 0)


@case
async def case_reservation_equal_to_balance_is_allowed(env: Env) -> None:
    limiter = env.make(60, 100)
    assert await limiter.reserve("k", 100) == Decision(True, 100, 0, None, 100)
    assert await limiter.reserve("k", 0) == Decision(True, 100, 0, None, 100)


@case
async def case_reservation_one_over_balance_is_refused_with_exact_wait(env: Env) -> None:
    limiter = env.make(60, 100)
    assert (await limiter.reserve("k", 60)).remaining_tokens == 40
    assert await limiter.reserve("k", 41) == Decision(False, 100, 40, 1, 60)
    # The refusal took nothing: the 40 that were there can still be reserved.
    assert await limiter.reserve("k", 40) == Decision(True, 100, 0, None, 100)


@case
async def case_wait_is_rounded_up_at_an_awkward_rate(env: Env) -> None:
    # 5/3 tokens per second: the wait for n tokens is ceil(3n / 5).
    limiter = env.make(100, 100)
    expected_waits = {1: 1, 2: 2, 3: 2, 4: 3, 5: 3, 6: 4, 10: 6, 100: 60}
    for amount, expected in expected_waits.items():
        key = f"key-{amount}"
        await drain(limiter, key, 100)
        decision = await limiter.reserve(key, amount)
        assert (decision.allowed, decision.retry_after_seconds) == (False, expected)


@case
async def case_wait_is_rounded_up_at_fast_rates(env: Env) -> None:
    hundred_per_second = env.make(6000, 1000)
    await drain(hundred_per_second, "k", 1000)
    for amount, expected in {1: 1, 100: 1, 101: 2, 250: 3}.items():
        assert (await hundred_per_second.reserve("k", amount)).retry_after_seconds == expected
    thousand_per_second = env.make(60000, 1000)
    await drain(thousand_per_second, "k", 1000)
    for amount in (1, 1000):
        assert (await thousand_per_second.reserve("k", amount)).retry_after_seconds == 1


@case
async def case_wait_counts_from_the_current_balance(env: Env) -> None:
    limiter = env.make(100, 100)
    await drain(limiter, "k", 100)
    env.clock.advance(1)  # 5/3 tokens
    assert (await limiter.reserve("k", 2)).retry_after_seconds == 1  # short by 1/3
    assert (await limiter.reserve("k", 3)).retry_after_seconds == 1  # short by 4/3
    assert (await limiter.reserve("k", 4)).retry_after_seconds == 2  # short by 7/3


@case
async def case_retry_after_is_both_sufficient_and_minimal(env: Env) -> None:
    for tokens_per_minute in (60, 100, 90, 7):
        limiter = env.make(tokens_per_minute, 100)
        for amount in range(1, 101):
            key = f"key-{amount}"
            await drain(limiter, key, 100)
            retry = (await limiter.reserve(key, amount)).retry_after_seconds
            assert retry is not None
            assert retry >= 1
            env.clock.advance(retry - 1)
            assert not (await limiter.reserve(key, amount)).allowed
            env.clock.advance(1)
            assert (await limiter.reserve(key, amount)).allowed


# --- the refill ---------------------------------------------------------------------------------


@case
async def case_refill_rate_is_tokens_per_minute_over_sixty(env: Env) -> None:
    limiter = env.make(600, 1000)
    await drain(limiter, "k", 1000)
    env.clock.advance(5)
    assert (await probe(limiter)).remaining_tokens == 50
    env.clock.advance(2.5)
    assert (await probe(limiter)).remaining_tokens == 75


@case
async def case_refill_is_linear_in_elapsed_time(env: Env) -> None:
    limiter = env.make(600, 1000)
    await drain(limiter, "k", 1000)
    for seconds, expected in ((1, 10), (1, 20), (2, 40), (4, 80)):
        env.clock.advance(seconds)
        assert (await probe(limiter)).remaining_tokens == expected


@case
async def case_refill_accumulates_across_calls(env: Env) -> None:
    limiter = env.make(600, 1000)
    await drain(limiter, "k", 1000)
    env.clock.advance(10)
    assert (await probe(limiter)).remaining_tokens == 100
    env.clock.advance(10)
    assert (await probe(limiter)).remaining_tokens == 200


@case
async def case_refill_is_capped_at_capacity(env: Env) -> None:
    limiter = env.make(60, 100)
    assert (await limiter.reserve("k", 30)).remaining_tokens == 70
    env.clock.advance(29)
    assert (await probe(limiter)).remaining_tokens == 99
    env.clock.advance(1)
    assert (await probe(limiter)).remaining_tokens == 100
    env.clock.advance(1000)
    assert await probe(limiter) == Decision(True, 100, 100, None, 0)


@case
async def case_refill_is_exact_at_an_awkward_rate(env: Env) -> None:
    limiter = env.make(100, 100)
    await drain(limiter, "k", 100)
    for expected in (1, 3, 5):  # 5/3, 10/3 and 5 tokens after 1, 2 and 3 seconds
        env.clock.advance(1)
        assert (await probe(limiter)).remaining_tokens == expected
    assert await limiter.reserve("k", 5) == Decision(True, 100, 0, None, 60)
    # Sixty steps of one second refill exactly 100 tokens, with no drift.
    for _ in range(60):
        env.clock.advance(1)
        await probe(limiter)
    assert (await limiter.reserve("k", 100)).allowed


@case
async def case_the_wait_is_exact_when_the_rate_is_not_a_whole_number(env: Env) -> None:
    # 11 tokens per minute: 11 tokens take exactly 60 seconds, which float division can miss.
    limiter = env.make(11, 100)
    await drain(limiter, "k", 100)
    assert (await limiter.reserve("k", 11)).retry_after_seconds == 60


@case
async def case_many_small_refills_add_up_exactly(env: Env) -> None:
    # 1 token per minute: 120 one-second steps give exactly 2 tokens, with no accumulated drift.
    limiter = env.make(1, 100)
    await drain(limiter, "k", 100)
    for _ in range(120):
        env.clock.advance(1)
        await probe(limiter)
    assert (await probe(limiter)).remaining_tokens == 2


@case
async def case_refill_is_applied_once_per_call(env: Env) -> None:
    limiter = env.make(60, 100)
    await drain(limiter, "k", 100)
    env.clock.advance(10)
    assert (await probe(limiter)).remaining_tokens == 10
    assert (await probe(limiter)).remaining_tokens == 10


@case
async def case_refill_is_applied_before_a_reservation(env: Env) -> None:
    limiter = env.make(60, 100)
    await drain(limiter, "a", 100)
    await drain(limiter, "b", 100)
    env.clock.advance(10)
    assert await limiter.reserve("a", 11) == Decision(False, 100, 10, 1, 90)
    assert await limiter.reserve("b", 10) == Decision(True, 100, 0, None, 100)


# --- a reservation larger than the capacity -----------------------------------------------------


@case
async def case_oversized_reservation_is_refused_without_a_retry_hint(env: Env) -> None:
    limiter = env.make(60, 100)
    assert await limiter.reserve("k", 101) == Decision(False, 100, 100, None, 0)
    assert await limiter.reserve("k", 10**9) == Decision(False, 100, 100, None, 0)


@case
async def case_oversized_reservation_leaves_the_balance_unchanged(env: Env) -> None:
    limiter = env.make(60, 100)
    await limiter.reserve("k", 60)
    assert await limiter.reserve("k", 101) == Decision(False, 100, 40, None, 60)
    assert (await probe(limiter)).remaining_tokens == 40


@case
async def case_a_capacity_sized_reservation_is_allowed_when_full(env: Env) -> None:
    limiter = env.make(60, 100)
    assert await limiter.reserve("k", 100) == Decision(True, 100, 0, None, 100)


@case
async def case_a_capacity_sized_reservation_waits_when_not_full(env: Env) -> None:
    limiter = env.make(60, 100)
    await limiter.reserve("k", 1)
    assert await limiter.reserve("k", 100) == Decision(False, 100, 99, 1, 1)


@case
async def case_capacity_is_independent_of_the_rate(env: Env) -> None:
    limiter = env.make(60, 500)
    assert await limiter.reserve("a", 500) == Decision(True, 500, 0, None, 500)
    assert await limiter.reserve("b", 501) == Decision(False, 500, 500, None, 0)


@case
async def case_the_limit_is_the_capacity_on_every_kind_of_decision(env: Env) -> None:
    limiter = env.make(60, 100)
    allowed = await limiter.reserve("k", 10)
    refused = await limiter.reserve("k", 100)
    oversized = await limiter.reserve("k", 101)
    assert (allowed.allowed, refused.allowed, oversized.allowed) == (True, False, False)
    assert (allowed.limit_tokens, refused.limit_tokens, oversized.limit_tokens) == (100, 100, 100)


# --- what a reservation does to the balance -----------------------------------------------------


@case
async def case_an_allowed_reservation_takes_its_tokens(env: Env) -> None:
    limiter = env.make(60, 100)
    remaining = [(await limiter.reserve("k", 30)).remaining_tokens for _ in range(3)]
    assert remaining == [70, 40, 10]


@case
async def case_a_refused_reservation_takes_nothing(env: Env) -> None:
    limiter = env.make(60, 100)
    await limiter.reserve("k", 60)
    for amount in range(41, 101):
        decision = await limiter.reserve("k", amount)
        assert (decision.allowed, decision.remaining_tokens) == (False, 40)
    assert (await probe(limiter)).remaining_tokens == 40


# --- settling -----------------------------------------------------------------------------------


@case
async def case_settle_charges_the_difference(env: Env) -> None:
    limiter = env.make(60, 100)
    await limiter.reserve("k", 40)
    await limiter.settle("k", 40, 70)
    assert (await probe(limiter)).remaining_tokens == 30


@case
async def case_settle_refunds_the_difference(env: Env) -> None:
    limiter = env.make(60, 100)
    await limiter.reserve("k", 40)
    await limiter.settle("k", 40, 10)
    assert (await probe(limiter)).remaining_tokens == 90


@case
async def case_settle_with_equal_amounts_changes_nothing(env: Env) -> None:
    limiter = env.make(60, 100)
    await limiter.reserve("k", 40)
    await limiter.settle("k", 40, 40)
    assert (await probe(limiter)).remaining_tokens == 60


@case
async def case_settle_with_zero_actual_refunds_the_whole_reservation(env: Env) -> None:
    limiter = env.make(60, 100)
    await limiter.reserve("k", 40)
    await limiter.settle("k", 40, 0)
    assert await probe(limiter) == Decision(True, 100, 100, None, 0)


@case
async def case_a_charge_can_take_the_balance_below_zero(env: Env) -> None:
    limiter = env.make(60, 100)
    await limiter.reserve("k", 100)
    await limiter.settle("k", 100, 160)  # balance -60
    # Remaining is never shown below 0; the wait and the reset still count the debt.
    assert await probe(limiter) == Decision(False, 100, 0, 60, 160)
    assert await limiter.reserve("k", 1) == Decision(False, 100, 0, 61, 160)
    env.clock.advance(60)
    assert await probe(limiter) == Decision(True, 100, 0, None, 100)
    env.clock.advance(1)
    assert await limiter.reserve("k", 1) == Decision(True, 100, 0, None, 100)


@case
async def case_a_refund_never_lifts_the_balance_above_capacity(env: Env) -> None:
    limiter = env.make(60, 100)
    await limiter.reserve("k", 10)  # balance 90
    await limiter.settle("k", 50, 0)  # a refund of 50
    assert await probe(limiter) == Decision(True, 100, 100, None, 0)
    assert (await limiter.reserve("k", 100)).remaining_tokens == 0


@case
async def case_settle_refills_before_it_charges(env: Env) -> None:
    limiter = env.make(60, 100)
    await drain(limiter, "k", 100)
    env.clock.advance(150)  # refilled to capacity
    await limiter.settle("k", 0, 30)
    assert (await probe(limiter)).remaining_tokens == 70


@case
async def case_settling_an_unknown_key_acts_on_a_full_bucket(env: Env) -> None:
    limiter = env.make(60, 100)
    await limiter.settle("x", 50, 0)
    assert (await probe(limiter, "x")).remaining_tokens == 100
    await limiter.settle("y", 0, 30)
    assert (await probe(limiter, "y")).remaining_tokens == 70


@case
async def case_settle_touches_only_its_own_key(env: Env) -> None:
    limiter = env.make(60, 100)
    await limiter.reserve("a", 40)
    await limiter.settle("a", 40, 70)
    assert (await probe(limiter, "a")).remaining_tokens == 30
    assert (await probe(limiter, "b")).remaining_tokens == 100


# --- keys ---------------------------------------------------------------------------------------


@case
async def case_keys_are_independent(env: Env) -> None:
    limiter = env.make(60, 100)
    await drain(limiter, "a", 100)
    assert (await probe(limiter, "b")).remaining_tokens == 100
    assert not (await limiter.reserve("a", 1)).allowed
    assert (await limiter.reserve("b", 100)).allowed


@case
async def case_lookalike_keys_are_distinct(env: Env) -> None:
    limiter = env.make(60, 100)
    for key in ("key", "KEY", "key ", "", "default"):
        assert (await limiter.reserve(key, 100)).allowed, repr(key)


@case
async def case_two_limiters_from_the_factory_do_not_share_state(env: Env) -> None:
    first, second = env.make(60, 100), env.make(60, 100)
    await drain(first, "k", 100)
    assert await probe(second) == Decision(True, 100, 100, None, 0)
    assert not (await first.reserve("k", 1)).allowed


# --- concurrency --------------------------------------------------------------------------------


@case
async def case_fifty_concurrent_reservations_never_overspend(env: Env) -> None:
    limiter = env.make(60, 100)
    decisions = await asyncio.gather(*[limiter.reserve("k", 3) for _ in range(50)])
    allowed = [decision for decision in decisions if decision.allowed]
    refused = [decision for decision in decisions if not decision.allowed]
    # 33 reservations of 3 take 99 of the 100 tokens; a 34th would need 102.
    assert (len(allowed), len(refused)) == (33, 17)
    assert {decision.remaining_tokens for decision in allowed} == set(range(1, 100, 3))
    assert all(decision.remaining_tokens == 1 for decision in refused)
    assert all(decision.retry_after_seconds == 2 for decision in refused)
    assert (await probe(limiter)).remaining_tokens == 1


@case
async def case_concurrent_reservations_on_two_keys_do_not_interfere(env: Env) -> None:
    limiter = env.make(60, 100)
    calls = [limiter.reserve(key, 3) for _ in range(50) for key in ("a", "b")]
    decisions = await asyncio.gather(*calls)
    assert sum(decision.allowed for decision in decisions) == 66
    assert (await probe(limiter, "a")).remaining_tokens == 1
    assert (await probe(limiter, "b")).remaining_tokens == 1


@case
async def case_concurrent_settles_do_not_lose_updates(env: Env) -> None:
    limiter = env.make(60, 100)
    await asyncio.gather(*[limiter.settle("k", 0, 10) for _ in range(10)])
    assert (await probe(limiter)).remaining_tokens == 0


# --- the numbers in a decision ------------------------------------------------------------------


@case
async def case_decision_numbers_are_plain_integers(env: Env) -> None:
    limiter = env.make(100, 100)
    await limiter.reserve("k", 60)
    decisions = [
        await limiter.reserve("k", 10),  # allowed
        await limiter.reserve("k", 50),  # refused, can succeed later
        await limiter.reserve("k", 101),  # larger than the capacity
    ]
    for decision in decisions:
        assert type(decision.allowed) is bool
        assert type(decision.limit_tokens) is int
        assert type(decision.remaining_tokens) is int
        assert type(decision.reset_seconds) is int
        assert decision.retry_after_seconds is None or type(decision.retry_after_seconds) is int


@case
async def case_remaining_is_rounded_down(env: Env) -> None:
    five_thirds = env.make(100, 100)
    await drain(five_thirds, "k", 100)
    for expected in (1, 3, 5):  # 5/3, 10/3 and 5
        env.clock.advance(1)
        assert (await probe(five_thirds)).remaining_tokens == expected
    one_and_a_half = env.make(90, 100)
    await drain(one_and_a_half, "k", 100)
    env.clock.advance(1)
    assert (await probe(one_and_a_half)).remaining_tokens == 1
    one_per_second = env.make(60, 100)
    await drain(one_per_second, "k", 100)
    env.clock.advance(0.75)
    assert (await probe(one_per_second)).remaining_tokens == 0


@case
async def case_reset_is_rounded_up(env: Env) -> None:
    limiter = env.make(100, 100)
    for amount, expected in {1: 1, 2: 2, 3: 2, 4: 3, 5: 3, 10: 6, 100: 60}.items():
        decision = await limiter.reserve(f"key-{amount}", amount)
        assert (decision.allowed, decision.reset_seconds) == (True, expected)


@case
async def case_reset_counts_from_the_current_balance(env: Env) -> None:
    limiter = env.make(60, 100)
    await limiter.reserve("k", 100)
    env.clock.advance(40)
    assert (await probe(limiter)).reset_seconds == 60


@case
async def case_the_same_operations_give_equal_decisions(env: Env) -> None:
    first, second = env.make(100, 100), env.make(100, 100)
    first_decisions: list[Decision] = []
    second_decisions: list[Decision] = []
    for amount in (70, 40, 90):
        first_decisions.append(await first.reserve("k", amount))
        second_decisions.append(await second.reserve("k", amount))
        await first.settle("k", amount, 20)
        await second.settle("k", amount, 20)
        env.clock.advance(3)
    first_decisions.append(await probe(first))
    second_decisions.append(await probe(second))
    assert first_decisions == second_decisions
    assert len(first_decisions) == 4
    # 70 of 100 taken: 30 left, and 70 tokens at 5/3 per second take 42 seconds to come back.
    assert first_decisions[0] == Decision(True, 100, 30, None, 42)


@case
async def case_negative_amounts_are_rejected_and_change_nothing(env: Env) -> None:
    limiter = env.make(60, 100)
    with pytest.raises(ValueError, match="negative"):
        await limiter.reserve("k", -1)
    with pytest.raises(ValueError, match="negative"):
        await limiter.settle("k", -1, 0)
    with pytest.raises(ValueError, match="negative"):
        await limiter.settle("k", 0, -1)
    assert await probe(limiter) == Decision(True, 100, 100, None, 0)
