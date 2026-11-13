"""The shared limiter suite on a real Redis server (ADR-0006). Run only in CI or by hand.

These tests carry the `redis_server` marker, which the default pytest options deselect, so
`scripts/check.py` and local runs never reach the network. Select them with
`python -m pytest -m redis_server` and set TOLLGATE_TEST_REDIS_URL (for example
redis://localhost:6379/0). With the marker selected and the variable missing, the tests fail;
they never skip.

Every limiter gets its own key prefix (a run id plus a counter), because the shared suite builds
several limiters per case and uses the same key on each. Cleanup deletes the keys under the
prefixes the case created and closes the clients.
"""

import itertools
import os
import uuid

import pytest
from redis.asyncio import Redis

from app.clock import Clock
from app.limits.limiter import RateLimiter
from app.limits.redis_limiter import RedisRateLimiter
from tests.limits.behaviour import BEHAVIOUR_CASES, BehaviourCase, run_behaviour_case

URL_VARIABLE = "TOLLGATE_TEST_REDIS_URL"

pytestmark = pytest.mark.redis_server


def redis_url() -> str:
    url = os.environ.get(URL_VARIABLE, "")
    if not url:
        pytest.fail(f"{URL_VARIABLE} must be set to run the redis_server tests", pytrace=False)
    return url


class RealRedisHarness:
    def __init__(self, url: str) -> None:
        self._url = url
        self._run_id = uuid.uuid4().hex
        self._numbers = itertools.count()
        self._clients: list[Redis] = []
        self._prefixes: list[str] = []

    def make(self, clock: Clock, tokens_per_minute: int, capacity_tokens: int) -> RateLimiter:
        client = Redis.from_url(self._url)
        self._clients.append(client)
        prefix = f"tollgate-test:{self._run_id}:{next(self._numbers)}:"
        self._prefixes.append(prefix)
        return RedisRateLimiter(
            client, clock, tokens_per_minute, capacity_tokens, key_prefix=prefix
        )

    async def cleanup(self) -> None:
        try:
            if self._clients:
                for prefix in self._prefixes:
                    async for key in self._clients[0].scan_iter(match=f"{prefix}*"):
                        await self._clients[0].delete(key)
        finally:
            for client in self._clients:
                await client.aclose()


@pytest.mark.parametrize(
    "behaviour_case", BEHAVIOUR_CASES, ids=[case.__name__ for case in BEHAVIOUR_CASES]
)
def test_redis_server_limiter_behaviour(behaviour_case: BehaviourCase) -> None:
    harness = RealRedisHarness(redis_url())
    run_behaviour_case(behaviour_case, harness.make, harness.cleanup)
