"""Rate limiting on POST /v1/chat/completions (T-108, ADR-0007, ADR-0008).

Every case uses a capacity of 1000 tokens refilled at 600 per minute (10 per second) and a fake
clock, so each header value below is computed by hand. Requests used (estimate from
`HeuristicEstimator`, usage from `MockProvider`, which counts whitespace-separated words):

- A: "hello there world" (17 characters): estimate ceil(17/4) + 3 + 3 = 11; usage 3 + 5 = 8.
- B: A with max_tokens 100: reserved 111; usage 8.
- C: "a b c d e f g h i j" (19 characters): estimate 11; usage 10 + 12 = 22.

A 200's headers come from the reserve decision, so the settled balance is checked through a
follow-up request (owner decision, T-108).
"""

import asyncio
import hashlib
from typing import Any

import fakeredis
import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.models import ChatRequest, ChatResponse
from app.limits.limiter import Decision, RateLimiter
from app.limits.redis_limiter import RedisRateLimiter
from app.main import create_app
from app.providers.mock import MockProvider
from tests.fakes import AUTH_HEADERS, TEST_API_KEY, FakeClock, FixedIdSource, make_settings

URL = "/v1/chat/completions"
START_SECONDS = 1000.0
CALLER_ID = hashlib.sha256(TEST_API_KEY.encode()).hexdigest()
OTHER_API_KEY = "other-key"
LIMIT_SETTINGS = {"TOLLGATE_TOKENS_PER_MINUTE": "600", "TOLLGATE_CAPACITY_TOKENS": "1000"}
HEADER_NAMES = (
    "x-ratelimit-limit-tokens",
    "x-ratelimit-remaining-tokens",
    "x-ratelimit-reset-tokens",
    "retry-after",
)
PROVIDER_SECRET = "SENTINEL-provider-internals"


def payload(content: str = "hello there world", **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"model": "mock-1", "messages": [{"role": "user", "content": content}]}
    body.update(overrides)
    return body


PAYLOAD_A = payload()
PAYLOAD_B = payload(max_tokens=100)
PAYLOAD_C = payload("a b c d e f g h i j")


def header_values(response: httpx.Response) -> tuple[str | None, ...]:
    return tuple(response.headers.get(name) for name in HEADER_NAMES)


class FailingProvider:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def complete(self, request: ChatRequest) -> ChatResponse:
        raise self._error


class RecordingLimiter:
    """Wraps a real limiter and records every call, so tests can assert the exact arguments."""

    def __init__(
        self,
        inner: RateLimiter,
        *,
        reserve_error: Exception | None = None,
        settle_error: Exception | None = None,
    ) -> None:
        self._inner = inner
        self._reserve_error = reserve_error
        self._settle_error = settle_error
        self.calls: list[tuple[Any, ...]] = []

    async def reserve(self, key: str, estimated_tokens: int) -> Decision:
        self.calls.append(("reserve", key, estimated_tokens))
        if self._reserve_error is not None:
            raise self._reserve_error
        return await self._inner.reserve(key, estimated_tokens)

    async def settle(self, key: str, reserved_tokens: int, actual_tokens: int) -> None:
        self.calls.append(("settle", key, reserved_tokens, actual_tokens))
        if self._settle_error is not None:
            raise self._settle_error
        await self._inner.settle(key, reserved_tokens, actual_tokens)


class Gateway:
    """The app on the memory backend, a client with the test key, and the fake clock."""

    def __init__(self, *, provider: Any = None, **settings: str) -> None:
        self.clock = FakeClock(START_SECONDS)
        self.app: FastAPI = create_app(
            make_settings(**{**LIMIT_SETTINGS, **settings}),
            self.clock,
            provider=provider or MockProvider(self.clock, FixedIdSource()),
        )
        self.client = TestClient(self.app, headers=AUTH_HEADERS)

    def post(self, body: dict[str, Any]) -> httpx.Response:
        response: httpx.Response = self.client.post(URL, json=body)
        return response

    def reserve(self, tokens: int) -> Decision:
        result: Decision = asyncio.run(self.app.state.limiter.reserve(CALLER_ID, tokens))
        return result

    def settle(self, reserved_tokens: int, actual_tokens: int) -> None:
        asyncio.run(self.app.state.limiter.settle(CALLER_ID, reserved_tokens, actual_tokens))

    def record(
        self,
        *,
        reserve_error: Exception | None = None,
        settle_error: Exception | None = None,
    ) -> RecordingLimiter:
        recorder = RecordingLimiter(
            self.app.state.limiter, reserve_error=reserve_error, settle_error=settle_error
        )
        self.app.state.limiter = recorder
        return recorder


# Criterion 1: under the limit.


def test_200_carries_the_headers_of_the_reserve_decision() -> None:
    response = Gateway().post(PAYLOAD_A)
    assert response.status_code == 200
    # 1000 - 11 = 989; 11 missing at 10 per second is 1.1 s, rounded up to 2 s.
    assert header_values(response) == ("1000", "989", "2s", None)


def test_reservation_equal_to_the_balance_is_allowed() -> None:
    gateway = Gateway()
    gateway.reserve(989)
    response = gateway.post(PAYLOAD_A)
    assert response.status_code == 200
    assert header_values(response) == ("1000", "0", "1m40s", None)


def test_request_equal_to_the_capacity_is_allowed() -> None:
    response = Gateway().post(payload(max_tokens=989))  # 11 + 989 = 1000
    assert response.status_code == 200
    assert header_values(response) == ("1000", "0", "1m40s", None)


# Criterion 2: the settled balance reflects the provider's usage, not the estimate.


def test_follow_up_request_shows_the_balance_settled_with_the_mock_usage() -> None:
    gateway = Gateway()
    first = gateway.post(PAYLOAD_B)
    # The 200 shows the balance after reserving 111: 889, with 111 missing (11.1 s, so 12 s).
    assert header_values(first) == ("1000", "889", "12s", None)
    # Settled with usage 8: 889 + 111 - 8 = 992. The follow-up reserves 11: 981, 19 missing.
    follow_up = gateway.post(PAYLOAD_A)
    assert header_values(follow_up) == ("1000", "981", "2s", None)


def test_usage_above_the_reservation_is_charged() -> None:
    gateway = Gateway()
    assert header_values(gateway.post(PAYLOAD_C)) == ("1000", "989", "2s", None)
    # Settled with usage 22: 989 - 11 = 978. The follow-up reserves 11: 967, 33 missing (3.3 s).
    assert header_values(gateway.post(PAYLOAD_A)) == ("1000", "967", "4s", None)


def test_route_reserves_and_settles_with_the_caller_id_and_exact_amounts() -> None:
    gateway = Gateway()
    recorder = gateway.record()
    # A `user` and another model in the body must not change the key.
    response = gateway.post({**PAYLOAD_B, "user": "someone-else", "model": "mock-2"})
    assert response.status_code == 200
    assert recorder.calls == [("reserve", CALLER_ID, 111), ("settle", CALLER_ID, 111, 8)]


# Criterion 1: over the limit.


def test_refusal_returns_429_with_the_adr_body_and_retry_after_rounded_up() -> None:
    gateway = Gateway()
    gateway.reserve(990)  # balance 10
    recorder = gateway.record()
    response = gateway.post(payload(max_tokens=24))  # 11 + 24 = 35
    assert response.status_code == 429
    # 25 missing at 10 per second is 2.5 s, rounded up to 3. The bucket misses 990: 99 s.
    assert header_values(response) == ("1000", "10", "1m39s", "3")
    assert response.json() == {
        "error": {
            "message": "Rate limit reached for tokens: limit 1000, requested 35. Try again in 3s.",
            "type": "tokens",
            "param": None,
            "code": "rate_limit_exceeded",
        }
    }
    # No provider call means no settle; a refusal is never settled.
    assert recorder.calls == [("reserve", CALLER_ID, 35)]


def test_refused_request_never_calls_the_provider() -> None:
    gateway = Gateway(provider=FailingProvider(RuntimeError("must not be called")))
    gateway.reserve(1000)
    response = gateway.post(PAYLOAD_A)
    assert response.status_code == 429


def test_waiting_retry_after_seconds_lets_the_request_through() -> None:
    gateway = Gateway()
    gateway.reserve(990)  # balance 10
    body = payload(max_tokens=24)  # 35
    assert gateway.post(body).headers["retry-after"] == "3"
    gateway.clock.advance(2)  # balance 30: 5 missing is 0.5 s, so 1
    second = gateway.post(body)
    assert second.status_code == 429
    assert header_values(second) == ("1000", "30", "1m37s", "1")
    gateway.clock.advance(1)  # balance 40
    third = gateway.post(body)
    assert third.status_code == 200
    # 40 - 35 = 5; 995 missing is 99.5 s, so 100 s.
    assert header_values(third) == ("1000", "5", "1m40s", None)


def test_refusal_during_a_debt_shows_remaining_zero_and_the_full_wait() -> None:
    gateway = Gateway()
    gateway.reserve(1000)
    gateway.settle(0, 500)  # balance -500
    response = gateway.post(PAYLOAD_A)
    assert response.status_code == 429
    # 511 missing is 51.1 s, so 52; the bucket misses 1500: 150 s.
    assert header_values(response) == ("1000", "0", "2m30s", "52")


def test_request_larger_than_the_capacity_gets_429_without_retry_after() -> None:
    gateway = Gateway()
    recorder = gateway.record()
    response = gateway.post(payload(max_tokens=990))  # 11 + 990 = 1001
    assert response.status_code == 429
    assert header_values(response) == ("1000", "1000", "0s", None)
    assert response.json() == {
        "error": {
            "message": (
                "Request too large for tokens: limit 1000, requested 1001. The request is larger "
                "than the limit and can never succeed."
            ),
            "type": "tokens",
            "param": None,
            "code": "rate_limit_exceeded",
        }
    }
    assert recorder.calls == [("reserve", CALLER_ID, 1001)]


# Criterion 3: a failing provider.


@pytest.mark.parametrize(
    "error",
    [RuntimeError(PROVIDER_SECRET), HTTPException(status_code=503, detail=PROVIDER_SECRET)],
    ids=["runtime-error", "http-exception"],
)
def test_provider_failure_returns_502_and_refunds_the_whole_reservation(error: Exception) -> None:
    gateway = Gateway(provider=FailingProvider(error))
    recorder = gateway.record()
    response = gateway.post(PAYLOAD_B)
    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "message": "The upstream provider failed to complete the request.",
            "type": "api_error",
            "param": None,
            "code": "provider_error",
        }
    }
    assert PROVIDER_SECRET not in response.text
    # The headers come from the reserve decision, before the refund (owner decision, T-108).
    assert header_values(response) == ("1000", "889", "12s", None)
    assert recorder.calls == [("reserve", CALLER_ID, 111), ("settle", CALLER_ID, 111, 0)]
    # Refunded in full: back to 1000, so the follow-up leaves 989.
    gateway.app.state.provider = MockProvider(gateway.clock, FixedIdSource())
    assert header_values(gateway.post(PAYLOAD_A)) == ("1000", "989", "2s", None)


def test_limiter_errors_are_not_turned_into_502_or_refunded() -> None:
    gateway = Gateway()
    recorder = gateway.record(reserve_error=RuntimeError("limiter down"))
    with pytest.raises(RuntimeError, match="limiter down"):
        gateway.post(PAYLOAD_A)
    assert recorder.calls == [("reserve", CALLER_ID, 11)]


def test_settle_error_after_a_successful_provider_call_is_not_turned_into_502_or_refunded() -> None:
    # Known gap (logged in T-108): the completion is lost and the caller gets the error, but the
    # settle error must never be mistaken for a provider failure and refunded.
    gateway = Gateway()
    recorder = gateway.record(settle_error=RuntimeError("settle failed"))
    with pytest.raises(RuntimeError, match="settle failed"):
        gateway.post(PAYLOAD_B)
    assert recorder.calls == [("reserve", CALLER_ID, 111), ("settle", CALLER_ID, 111, 8)]


# Buckets are per authenticated key.


def test_each_api_key_has_its_own_bucket() -> None:
    gateway = Gateway(TOLLGATE_API_KEYS=f"{TEST_API_KEY},{OTHER_API_KEY}")
    gateway.reserve(1000)
    assert gateway.post(PAYLOAD_A).status_code == 429
    other = gateway.client.post(
        URL, json=PAYLOAD_A, headers={"Authorization": f"Bearer {OTHER_API_KEY}"}
    )
    assert other.status_code == 200
    assert header_values(other) == ("1000", "989", "2s", None)


# Criterion 5: no limit headers where the limiter was not reached.


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer wrong-key"}, {"Authorization": f"Basic {TEST_API_KEY}"}],
    ids=["missing", "wrong-key", "wrong-scheme"],
)
def test_401_carries_no_limit_headers(headers: dict[str, str]) -> None:
    gateway = Gateway()
    recorder = gateway.record()
    response = TestClient(gateway.app).post(URL, json=PAYLOAD_A, headers=headers)
    assert response.status_code == 401
    assert header_values(response) == (None, None, None, None)
    assert recorder.calls == []


def test_health_carries_no_limit_headers() -> None:
    response = Gateway().client.get("/health")
    assert response.status_code == 200
    assert header_values(response) == (None, None, None, None)


def test_authenticated_400_makes_no_reservation_and_carries_no_limit_headers() -> None:
    gateway = Gateway()
    recorder = gateway.record()
    response = gateway.post({**PAYLOAD_A, "stream": True})
    assert response.status_code == 400
    assert header_values(response) == (None, None, None, None)
    assert recorder.calls == []


# Criterion 6: the redis backend.


def test_redis_backend_serves_requests_from_redis() -> None:
    async def scenario() -> None:
        server = fakeredis.FakeServer()
        redis_client = fakeredis.FakeAsyncRedis(server=server)
        clock = FakeClock(START_SECONDS)
        settings = make_settings(
            **LIMIT_SETTINGS,
            # Loopback port 1 refuses connections, so an ignored injected client fails loudly
            # and never reaches a real server.
            TOLLGATE_LIMITER_BACKEND="redis",
            TOLLGATE_REDIS_URL="redis://127.0.0.1:1/0",
        )
        application = create_app(
            settings,
            clock,
            provider=MockProvider(clock, FixedIdSource()),
            redis_client=redis_client,
        )
        assert isinstance(application.state.limiter, RedisRateLimiter)
        assert application.state.redis_client is redis_client
        transport = httpx.ASGITransport(app=application)
        try:
            async with httpx.AsyncClient(
                transport=transport, base_url="http://gateway", headers=AUTH_HEADERS
            ) as client:
                first = await client.post(URL, json=PAYLOAD_A)
                assert first.status_code == 200
                assert header_values(first) == ("1000", "989", "2s", None)
                # Settled with usage 8 in Redis: 992. Half a second on the injected clock refills
                # 5 (997); the follow-up reserves 11: 986, 14 missing (1.4 s). A limiter on the
                # system clock would refill nothing in the few milliseconds and show 981.
                clock.advance(0.5)
                follow_up = await client.post(URL, json=PAYLOAD_A)
                assert header_values(follow_up) == ("1000", "986", "2s", None)
            bucket = "tollgate:bucket:" + hashlib.sha256(CALLER_ID.encode()).hexdigest()
            assert await redis_client.keys("*") == [bucket.encode()]
        finally:
            await redis_client.aclose()

    asyncio.run(scenario())
