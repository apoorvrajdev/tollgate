"""The Redis token bucket on fakeredis, running the real Lua script.

fakeredis reads the real time for key expiry, so TTL checks assert the PTTL that was set, within a
tolerance, and never wait for a key to expire. Clock values are multiples of 1/1024 second, which
are exact in binary.
"""

import asyncio
import hashlib
import itertools
import re
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

import fakeredis
import pytest

from app.clock import Clock
from app.limits.limiter import Decision, RateLimiter
from app.limits.redis_limiter import (
    DEFAULT_KEY_PREFIX,
    MAX_TOKENS,
    RedisRateLimiter,
    ScriptResult,
    milliseconds_from_seconds,
    parse_script_result,
)
from tests.fakes import FakeClock
from tests.limits.behaviour import BEHAVIOUR_CASES, BehaviourCase, run_behaviour_case

SCRIPT_PATH = Path(__file__).parents[2] / "app" / "limits" / "token_bucket.lua"
PTTL_TOLERANCE_MILLISECONDS = 1000


class FakeRedisHarness:
    """One fake server per test; every limiter gets its own client and its own key prefix."""

    def __init__(self) -> None:
        self.server = fakeredis.FakeServer()
        self._clients: list[fakeredis.FakeAsyncRedis] = []
        self._prefix_numbers = itertools.count()

    def client(self) -> fakeredis.FakeAsyncRedis:
        client = fakeredis.FakeAsyncRedis(server=self.server)
        self._clients.append(client)
        return client

    def make(
        self, clock: Clock, tokens_per_minute: int, capacity_tokens: int, **options: str
    ) -> RedisRateLimiter:
        options.setdefault("key_prefix", f"test:{next(self._prefix_numbers)}:")
        return RedisRateLimiter(self.client(), clock, tokens_per_minute, capacity_tokens, **options)

    async def close(self) -> None:
        for client in self._clients:
            await client.aclose()


def run(scenario: Callable[[FakeRedisHarness], Coroutine[Any, Any, None]]) -> None:
    harness = FakeRedisHarness()

    async def main() -> None:
        try:
            await scenario(harness)
        finally:
            await harness.close()

    asyncio.run(main())


def ceil_div(numerator: int, denominator: int) -> int:
    return -(-numerator // denominator)


@pytest.mark.parametrize(
    "behaviour_case", BEHAVIOUR_CASES, ids=[case.__name__ for case in BEHAVIOUR_CASES]
)
def test_redis_limiter_behaviour(behaviour_case: BehaviourCase) -> None:
    harness = FakeRedisHarness()

    def factory(clock: Clock, tokens_per_minute: int, capacity_tokens: int) -> RateLimiter:
        return harness.make(clock, tokens_per_minute, capacity_tokens)

    run_behaviour_case(behaviour_case, factory, harness.close)


# --- keys and expiry ----------------------------------------------------------------------------


async def key_names(harness: FakeRedisHarness) -> list[str]:
    """Every key on the fake server, decoded and sorted."""
    raw_keys = await harness.client().keys("*")
    return sorted(key.decode() if isinstance(key, bytes) else key for key in raw_keys)


def test_the_bucket_key_is_the_prefix_and_sha256_of_the_key_never_the_key_itself() -> None:
    secret = "fixture-api-key-0001"
    digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()

    async def scenario(harness: FakeRedisHarness) -> None:
        clock = FakeClock(1000.0)
        limiter = harness.make(clock, 60, 100, key_prefix="pfx:")
        await limiter.reserve(secret, 10)
        await limiter.settle(secret, 10, 20)
        keys = await key_names(harness)
        assert keys == [f"pfx:{digest}"]
        assert limiter.bucket_key(secret) == f"pfx:{digest}"
        assert all(secret not in key for key in keys)

        default = RedisRateLimiter(harness.client(), clock, 60, 100)
        await default.reserve(secret, 10)
        keys = await key_names(harness)
        assert keys == [f"pfx:{digest}", f"{DEFAULT_KEY_PREFIX}{digest}"]
        assert DEFAULT_KEY_PREFIX == "tollgate:bucket:"

    run(scenario)


async def pttl(harness: FakeRedisHarness, limiter: RedisRateLimiter, key: str = "k") -> int:
    value = await harness.client().pttl(limiter.bucket_key(key))
    assert isinstance(value, int)
    return value


def assert_pttl(actual: int, expected: int) -> None:
    assert expected - PTTL_TOLERANCE_MILLISECONDS < actual <= expected, (actual, expected)


def test_every_call_sets_a_ttl_until_full_plus_the_margin() -> None:
    async def scenario(harness: FakeRedisHarness) -> None:
        clock = FakeClock(1000.0)
        limiter = harness.make(clock, 60, 100)  # 1 token per second
        await limiter.reserve("k", 0)
        assert_pttl(await pttl(harness, limiter), 60_001)  # full: the margin and 1 ms
        await limiter.reserve("k", 100)
        assert_pttl(await pttl(harness, limiter), 160_001)  # 100 s to refill
        clock.advance(40)
        await limiter.reserve("k", 0)
        assert_pttl(await pttl(harness, limiter), 120_001)  # refreshed: 60 s to go
        await limiter.settle("k", 0, 100)  # 40 - 100 = -60
        assert_pttl(await pttl(harness, limiter), 220_001)  # the debt counts too

    run(scenario)


class SteppableClock:
    def __init__(self, now_seconds: float) -> None:
        self.now = now_seconds

    def now_seconds(self) -> float:
        return self.now


def test_a_clock_that_steps_back_gives_no_refill_and_no_second_refill() -> None:
    async def scenario(harness: FakeRedisHarness) -> None:
        clock = SteppableClock(1000.0)
        limiter = harness.make(clock, 60, 100)
        assert (await limiter.reserve("k", 100)).allowed  # drained at t=1000
        clock.now = 990.0  # a time correction ten seconds back
        stepped_back = await limiter.reserve("k", 1)
        assert (stepped_back.allowed, stepped_back.retry_after_seconds) == (False, 1)
        # The key outlives the ten seconds until the clock is back at the stored timestamp.
        assert_pttl(await pttl(harness, limiter), 170_001)
        clock.now = 1000.0  # back at the old timestamp: still nothing to refill
        assert not (await limiter.reserve("k", 1)).allowed
        clock.now = 1001.0
        assert (await limiter.reserve("k", 1)).allowed

    run(scenario)


def test_a_full_bucket_never_holds_more_than_its_capacity() -> None:
    # At 1 token per millisecond, a refill that skipped the cap would add a whole token per call.
    # A refund that skipped the cap would only show in the stored hash, because the next call
    # caps the balance before anything reads it.
    async def scenario(harness: FakeRedisHarness) -> None:
        clock = SteppableClock(1000.0)
        limiter = harness.make(clock, 60000, 100)
        bucket_key = limiter.bucket_key("k")
        for now_seconds in (1000.0, 1001.0, 1002.0, 1003.0):
            clock.now = now_seconds
            assert await limiter.reserve("k", 0) == Decision(True, 100, 100, None, 0)
        assert await harness.client().hget(bucket_key, "balance_units") == b"6000000"
        await limiter.settle("k", 50, 0)  # a refund of 50 on a full bucket
        assert await harness.client().hget(bucket_key, "balance_units") == b"6000000"
        assert (await limiter.reserve("k", 100)).remaining_tokens == 0
        assert not (await limiter.reserve("k", 1)).allowed

    run(scenario)


# --- milliseconds -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("seconds", "expected_milliseconds"),
    [
        (1000.0, 1_000_000),
        (1000 + 1 / 1024, 1_000_000),
        (1000 + 1023 / 1024, 1_000_999),
        (0.25, 250),
        (2.5, 2500),
    ],
)
def test_milliseconds_are_the_floor_of_the_exact_clock_value(
    seconds: float, expected_milliseconds: int
) -> None:
    assert milliseconds_from_seconds(seconds) == expected_milliseconds


def test_sub_millisecond_moves_refill_nothing_until_the_millisecond_ticks() -> None:
    async def scenario(harness: FakeRedisHarness) -> None:
        clock = SteppableClock(1000.0)
        limiter = harness.make(clock, 60000, 1000)  # 1 token per millisecond
        assert (await limiter.reserve("k", 1000)).allowed
        clock.now = 1000 + 1 / 1024  # 0.98 ms
        assert (await limiter.reserve("k", 0)).remaining_tokens == 0
        clock.now = 1000 + 2 / 1024  # 1.95 ms: one whole millisecond, one token
        assert (await limiter.reserve("k", 0)).remaining_tokens == 1
        clock.now = 1000 + 1023 / 1024  # 999.02 ms
        assert (await limiter.reserve("k", 0)).remaining_tokens == 999
        clock.now = 1001.0
        assert await limiter.reserve("k", 0) == Decision(True, 1000, 1000, None, 0)

    run(scenario)


# --- the constructor and the exact range --------------------------------------------------------


@pytest.mark.parametrize(
    ("tokens_per_minute", "capacity_tokens"), [(0, 100), (-1, 100), (60, 0), (60, -1)]
)
def test_the_constructor_rejects_a_non_positive_rate_or_capacity(
    tokens_per_minute: int, capacity_tokens: int
) -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        RedisRateLimiter(
            fakeredis.FakeAsyncRedis(), FakeClock(), tokens_per_minute, capacity_tokens
        )


def test_the_largest_exact_rate_and_capacity_are_accepted_and_one_more_is_rejected() -> None:
    assert MAX_TOKENS == 75_059_993_789 == 2**52 // 60_000
    client = fakeredis.FakeAsyncRedis()
    RedisRateLimiter(client, FakeClock(), MAX_TOKENS, 100)
    RedisRateLimiter(client, FakeClock(), 60, MAX_TOKENS)
    for tokens_per_minute, capacity_tokens in ((MAX_TOKENS + 1, 100), (60, MAX_TOKENS + 1)):
        with pytest.raises(ValueError, match="at most 75,059,993,789"):
            RedisRateLimiter(client, FakeClock(), tokens_per_minute, capacity_tokens)


def test_a_capacity_at_the_limit_stays_exact() -> None:
    async def scenario(harness: FakeRedisHarness) -> None:
        clock = FakeClock(1000.0)
        limiter = harness.make(clock, 7, MAX_TOKENS)  # 7 units per millisecond
        await limiter.reserve("k", 1)  # capacity - 60,000 units
        clock.advance(0.25)  # 250 ms refill 1,750 units: 58,250 still missing
        stored = await harness.client().hget(limiter.bucket_key("k"), "balance_units")
        assert stored == b"4503599627280000"  # capacity units 4,503,599,627,340,000 minus 60,000
        decision = await limiter.reserve("k", MAX_TOKENS)
        # 58,250 units missing at 7,000 units per second: 8.32 seconds, rounded up.
        assert decision == Decision(False, MAX_TOKENS, MAX_TOKENS - 1, 9, 9)
        stored = await harness.client().hget(limiter.bucket_key("k"), "balance_units")
        assert stored == b"4503599627281750"

    run(scenario)


def test_charges_stop_at_the_debt_floor_exactly() -> None:
    floor_units = MAX_TOKENS * 60_000  # 4,503,599,627,340,000

    async def scenario(harness: FakeRedisHarness) -> None:
        clock = FakeClock(1000.0)
        limiter = harness.make(clock, 1, 100)  # 1,000 units per second
        at_floor = Decision(
            False, 100, 0, ceil_div(floor_units, 1000), ceil_div(floor_units + 6_000_000, 1000)
        )
        assert at_floor.retry_after_seconds == 4_503_599_627_340
        await limiter.settle("k", 0, 10**30)
        assert await limiter.reserve("k", 0) == at_floor
        await limiter.settle("k", 0, 10**30)  # already at the floor: no deeper
        assert await limiter.reserve("k", 0) == at_floor
        assert_pttl(await pttl(harness, limiter), floor_units + 6_000_000 + 60_001)
        await limiter.settle("k", 10**30, 0)  # a huge refund fills the bucket
        assert await limiter.reserve("k", 0) == Decision(True, 100, 100, None, 0)
        # One token above the floor: a charge of MAX_TOKENS + 99 from a full bucket of 100.
        await limiter.settle("j", 0, MAX_TOKENS + 99)
        probe = await limiter.reserve("j", 0)
        assert probe.retry_after_seconds == ceil_div(floor_units - 60_000, 1000)

    run(scenario)


# --- the script and its reply -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ([1, b"3600000/60000"], ScriptResult(True, 3_600_000)),
        ([0, b"-60/60000"], ScriptResult(False, -60)),
        ([0, "0/60000"], ScriptResult(False, 0)),
        ([1, b"4503599627340000/60000"], ScriptResult(True, 4_503_599_627_340_000)),
    ],
)
def test_the_script_result_parser_accepts_exact_fractions(
    raw: object, expected: ScriptResult
) -> None:
    assert parse_script_result(raw) == expected


@pytest.mark.parametrize(
    ("raw", "error"),
    [
        ([1, 3600000], ValueError),  # the balance as a number
        ([1, b"3.6e+06/60000"], ValueError),
        ([1, b"1e+15/60000"], ValueError),
        ([1, b"60/60001"], ValueError),
        ([1, b"60"], ValueError),
        ([1, b" 60/60000"], ValueError),
        ([1, b"60/60000\n"], ValueError),
        ([1, "\uff16\uff10/60000"], ValueError),  # fullwidth digits
        ([1, b"\xff/60000"], ValueError),
        ([2, b"60/60000"], ValueError),
        ([True, b"60/60000"], ValueError),
        ([b"1", b"60/60000"], ValueError),
        ([1], TypeError),
        ([1, b"60/60000", 0], TypeError),
        ((1, b"60/60000"), TypeError),
        (None, TypeError),
    ],
)
def test_the_script_result_parser_rejects_everything_else(
    raw: object, error: type[Exception]
) -> None:
    with pytest.raises(error):
        parse_script_result(raw)


def test_the_script_never_reads_the_server_clock() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "redis.call" in source  # the right file
    assert re.search(r"""(?i)["']\s*time\s*["']""", source) is None


def test_a_negative_amount_raises_before_anything_reaches_redis() -> None:
    async def scenario(harness: FakeRedisHarness) -> None:
        limiter = harness.make(FakeClock(1000.0), 60, 100)
        with pytest.raises(ValueError, match="negative"):
            await limiter.reserve("k", -1)
        with pytest.raises(ValueError, match="negative"):
            await limiter.settle("k", -1, 0)
        with pytest.raises(ValueError, match="negative"):
            await limiter.settle("k", 0, -1)
        assert await key_names(harness) == []

    run(scenario)
