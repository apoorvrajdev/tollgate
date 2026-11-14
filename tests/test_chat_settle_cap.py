"""The settle charge of a 200 is capped at the bucket capacity (T-208, ADR-0012).

Every case runs through the whole app on both limiters, with a capacity of 60 tokens refilled at 60
per minute (1 per second), so one token of balance moves every header. The limiter is the real one
the app builds, never a wrapper. Each request is "hello there world", which reserves
ceil(17 / 4) + 3 + 3 = 11 tokens, so after the first request settles a count N the balance is
60 - min(N, 60).
"""

import asyncio
import hashlib
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

import fakeredis
import httpx
import pytest

from app.main import create_app
from tests.fakes import AUTH_HEADERS, FakeClock, ScriptedProvider, make_settings
from tests.limits.test_redis_limiter import assert_pttl
from tests.test_chat_rate_limits import CALLER_ID, START_SECONDS, URL, header_values, payload

CAPACITY = 60
RESERVED = 11
FULL_REFILL_SECONDS = 60
CAP_SETTINGS = {"TOLLGATE_TOKENS_PER_MINUTE": "60", "TOLLGATE_CAPACITY_TOKENS": str(CAPACITY)}
BACKENDS = ("memory", "redis")
BUCKET_KEY = "tollgate:bucket:" + hashlib.sha256(CALLER_ID.encode()).hexdigest()
UNITS_PER_TOKEN = 60_000  # the Redis limiter's fixed-point scale (milliseconds per minute)
# The script's expiry from a balance of 0: one full refill, 1 ms, and the 60-second margin (T-106).
EMPTY_BUCKET_PTTL_MILLISECONDS = FULL_REFILL_SECONDS * 1000 + 1 + 60_000


@dataclass
class CappedApp:
    client: httpx.AsyncClient
    clock: FakeClock
    redis_client: fakeredis.FakeAsyncRedis | None

    async def post(self) -> httpx.Response:
        return await self.client.post(URL, json=payload())

    async def stored_balance_units(self) -> bytes | str | None:
        assert self.redis_client is not None
        value: bytes | str | None = await self.redis_client.hget(BUCKET_KEY, "balance_units")
        return value


@asynccontextmanager
async def capped_app(backend: str, provider: ScriptedProvider) -> AsyncIterator[CappedApp]:
    clock = FakeClock(START_SECONDS)
    redis_client = fakeredis.FakeAsyncRedis(server=fakeredis.FakeServer())
    if backend == "redis":
        # Loopback port 1 refuses connections, so an ignored injected client fails loudly.
        settings = make_settings(
            **CAP_SETTINGS,
            TOLLGATE_LIMITER_BACKEND="redis",
            TOLLGATE_REDIS_URL="redis://127.0.0.1:1/0",
        )
        application = create_app(settings, clock, provider=provider, redis_client=redis_client)
    else:
        application = create_app(make_settings(**CAP_SETTINGS), clock, provider=provider)
    transport = httpx.ASGITransport(app=application)
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://gateway", headers=AUTH_HEADERS
        ) as client:
            yield CappedApp(client, clock, redis_client if backend == "redis" else None)
    finally:
        await redis_client.aclose()


def run(
    backend: str, provider: ScriptedProvider, scenario: Callable[[CappedApp], Awaitable[None]]
) -> None:
    async def main() -> None:
        async with capped_app(backend, provider) as app:
            await scenario(app)

    asyncio.run(main())


def reporting(total_tokens: int) -> ScriptedProvider:
    # Injected as the registry entry `mock`, which the built-in route table serves.
    return ScriptedProvider("mock", prompt_tokens=total_tokens, completion_tokens=0)


# Criteria 2 and 3: an absurd count is returned in `usage` and charges one full bucket.


@pytest.mark.parametrize("backend", BACKENDS)
def test_an_absurd_count_is_returned_in_usage_and_charges_one_full_bucket(backend: str) -> None:
    async def scenario(app: CappedApp) -> None:
        first = await app.post()
        assert first.status_code == 200
        assert first.json()["usage"] == {
            "prompt_tokens": 10**30,
            "completion_tokens": 0,
            "total_tokens": 10**30,
        }
        assert header_values(first) == ("60", "49", "11s", None)
        if app.redis_client is not None:
            assert await app.stored_balance_units() == b"0"
            pttl = await app.redis_client.pttl(BUCKET_KEY)
            assert_pttl(pttl, EMPTY_BUCKET_PTTL_MILLISECONDS)
        # A balance of exactly 0 on the same frozen clock: the follow-up waits its own 11 tokens.
        refused = await app.post()
        assert refused.status_code == 429
        assert header_values(refused) == ("60", "0", "1m0s", str(RESERVED))
        assert refused.json()["error"]["message"] == (
            "Rate limit reached for tokens: limit 60, requested 11. Try again in 11s."
        )
        app.clock.advance(FULL_REFILL_SECONDS)
        refilled = await app.post()
        assert refilled.status_code == 200
        assert header_values(refilled) == ("60", "49", "11s", None)

    run(backend, reporting(10**30), scenario)


# Criterion 4: counts at and around the capacity leave the exact balance.


@pytest.mark.parametrize(
    ("reported_tokens", "balance_tokens", "reset"),
    [(CAPACITY - 1, 1, "59s"), (CAPACITY, 0, "1m0s"), (CAPACITY + 1, 0, "1m0s")],
)
@pytest.mark.parametrize("backend", BACKENDS)
def test_counts_at_and_around_the_capacity_leave_the_exact_balance(
    backend: str, reported_tokens: int, balance_tokens: int, reset: str
) -> None:
    async def scenario(app: CappedApp) -> None:
        first = await app.post()
        assert first.status_code == 200
        assert first.json()["usage"]["total_tokens"] == reported_tokens
        if app.redis_client is not None:
            expected_units = str(balance_tokens * UNITS_PER_TOKEN).encode()
            assert await app.stored_balance_units() == expected_units
        # Exactly the follow-up's reservation refills, so it is served with the settled balance
        # left over; an uncapped CAPACITY + 1 would leave -1 and the follow-up would be a 429.
        app.clock.advance(RESERVED)
        follow_up = await app.post()
        assert follow_up.status_code == 200
        assert header_values(follow_up) == ("60", str(balance_tokens), reset, None)

    run(backend, reporting(reported_tokens), scenario)


# Criterion 5: a count above the reservation and below the capacity is charged in full.


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_count_between_the_reservation_and_the_capacity_is_charged_in_full(backend: str) -> None:
    provider = ScriptedProvider("mock", prompt_tokens=20, completion_tokens=10)

    async def scenario(app: CappedApp) -> None:
        first = await app.post()
        assert first.status_code == 200
        assert first.json()["usage"]["total_tokens"] == 30
        if app.redis_client is not None:
            assert await app.stored_balance_units() == str(30 * UNITS_PER_TOKEN).encode()
        # Settled 30 of 60: the follow-up reserves 11 and leaves 19, 41 s from full.
        follow_up = await app.post()
        assert follow_up.status_code == 200
        assert header_values(follow_up) == ("60", "19", "41s", None)

    run(backend, provider, scenario)
