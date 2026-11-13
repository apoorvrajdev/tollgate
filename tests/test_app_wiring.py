import asyncio
from typing import Any

import fakeredis
import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from redis.asyncio.connection import AbstractConnection

import app.main
from app.clock import SystemClock
from app.limits.estimate import HeuristicEstimator
from app.limits.memory import InMemoryRateLimiter
from app.limits.redis_limiter import MAX_TOKENS, RedisRateLimiter
from app.main import _close_all, create_app
from app.settings import SettingsError
from tests.fakes import FakeClient, FakeClock, make_settings

PASSWORD_SENTINEL = "SENTINEL-redis-password"
# Loopback port 1 refuses connections; nothing in these tests connects to it.
REDIS_URL = f"redis://:{PASSWORD_SENTINEL}@127.0.0.1:1/3"
REDIS_BACKEND = {"TOLLGATE_LIMITER_BACKEND": "redis", "TOLLGATE_REDIS_URL": REDIS_URL}


def test_create_app_without_arguments_reads_os_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOLLGATE_API_KEYS", "env-key")
    monkeypatch.setenv("TOLLGATE_TOKENS_PER_MINUTE", "777")
    application = create_app()
    assert application.state.settings.tokens_per_minute == 777


def test_create_app_without_arguments_fails_naming_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "TOLLGATE_API_KEYS",
        "TOLLGATE_TOKENS_PER_MINUTE",
        "TOLLGATE_CAPACITY_TOKENS",
        "TOLLGATE_LIMITER_BACKEND",
        "TOLLGATE_REDIS_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SettingsError, match="TOLLGATE_API_KEYS"):
        create_app()


def test_create_app_uses_injected_settings_and_clock_ignoring_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TOLLGATE_API_KEYS", "")
    monkeypatch.setenv("TOLLGATE_TOKENS_PER_MINUTE", "not-a-number")
    settings = make_settings()
    clock = FakeClock()
    application = create_app(settings, clock)
    assert application.state.settings is settings
    assert application.state.clock is clock


def test_create_app_defaults_to_system_clock() -> None:
    assert isinstance(create_app(make_settings()).state.clock, SystemClock)


def test_app_main_has_no_module_level_app() -> None:
    assert not hasattr(app.main, "app")


def test_create_app_uses_the_heuristic_estimator() -> None:
    assert isinstance(create_app(make_settings()).state.estimator, HeuristicEstimator)


def test_memory_backend_builds_the_in_memory_limiter_and_ignores_a_redis_client() -> None:
    client = fakeredis.FakeAsyncRedis()
    application = create_app(make_settings(), FakeClock(), redis_client=client)
    assert isinstance(application.state.limiter, InMemoryRateLimiter)
    assert application.state.redis_client is None
    asyncio.run(client.aclose())


def test_redis_backend_uses_the_injected_client() -> None:
    client = fakeredis.FakeAsyncRedis()
    application = create_app(make_settings(**REDIS_BACKEND), FakeClock(), redis_client=client)
    assert isinstance(application.state.limiter, RedisRateLimiter)
    assert application.state.redis_client is client
    asyncio.run(client.aclose())


def test_redis_backend_without_a_client_builds_one_from_the_url() -> None:
    application = create_app(make_settings(**REDIS_BACKEND), FakeClock())
    assert isinstance(application.state.limiter, RedisRateLimiter)
    # from_url connects lazily; these are the parsed URL parts, and no connection is made.
    kwargs = application.state.redis_client.connection_pool.connection_kwargs
    assert (kwargs["host"], kwargs["port"], kwargs["db"]) == ("127.0.0.1", 1, 3)
    assert kwargs["password"] == PASSWORD_SENTINEL


@pytest.mark.parametrize(
    ("overrides", "variable"),
    [
        (
            {"TOLLGATE_TOKENS_PER_MINUTE": str(MAX_TOKENS + 1)},
            "TOLLGATE_TOKENS_PER_MINUTE",
        ),
        (
            {"TOLLGATE_TOKENS_PER_MINUTE": "600", "TOLLGATE_CAPACITY_TOKENS": str(MAX_TOKENS + 1)},
            "TOLLGATE_CAPACITY_TOKENS",
        ),
    ],
    ids=["tokens-per-minute", "capacity"],
)
def test_redis_range_error_at_startup_names_the_variable(
    overrides: dict[str, str], variable: str
) -> None:
    settings = make_settings(**REDIS_BACKEND, **overrides)
    with pytest.raises(SettingsError) as raised:
        create_app(settings, FakeClock())
    assert raised.value.variable == variable
    message = str(raised.value)
    assert message.startswith(f"{variable}: ")
    assert "75,059,993,789" in message
    assert PASSWORD_SENTINEL not in message
    assert str(MAX_TOKENS + 1) not in message


def test_redis_range_accepts_the_maximum_for_both_values() -> None:
    settings = make_settings(
        **REDIS_BACKEND,
        TOLLGATE_TOKENS_PER_MINUTE=str(MAX_TOKENS),
        TOLLGATE_CAPACITY_TOKENS=str(MAX_TOKENS),
    )
    assert isinstance(create_app(settings, FakeClock()).state.limiter, RedisRateLimiter)


def test_memory_backend_has_no_redis_range_limit() -> None:
    settings = make_settings(
        TOLLGATE_TOKENS_PER_MINUTE=str(MAX_TOKENS + 1),
        TOLLGATE_CAPACITY_TOKENS=str(MAX_TOKENS + 1),
    )
    assert isinstance(create_app(settings, FakeClock()).state.limiter, InMemoryRateLimiter)


# Shutdown closes the clients the app built (T-203).


def leaves(error: BaseException) -> list[BaseException]:
    """The exceptions inside nested exception groups, in order; the TestClient may add a group."""
    if isinstance(error, BaseExceptionGroup):
        return [leaf for inner in error.exceptions for leaf in leaves(inner)]
    return [error]


class ForbiddenRedis:
    """Stands in for `Redis` in app.main: building a client either way is a test failure."""

    def __new__(cls, *args: Any, **kwargs: Any) -> "ForbiddenRedis":
        raise AssertionError("a Redis client was built")

    @classmethod
    def from_url(cls, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("a Redis client was built from a URL")


class SpyRedis(fakeredis.FakeAsyncRedis):
    """A Redis client that counts the calls to aclose."""

    closes = 0

    async def aclose(self, *args: Any, **kwargs: Any) -> None:
        self.closes += 1
        await super().aclose(*args, **kwargs)


def test_redis_client_built_from_the_url_is_closed_at_shutdown_and_opens_no_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a connection was opened")

    closed: list[Redis] = []
    original = Redis.aclose

    async def record(self: Redis, *args: Any, **kwargs: Any) -> None:
        closed.append(self)
        await original(self, *args, **kwargs)

    monkeypatch.setattr(AbstractConnection, "connect", refuse)
    monkeypatch.setattr(Redis, "aclose", record)
    application = create_app(make_settings(**REDIS_BACKEND), FakeClock())
    client = application.state.redis_client
    assert application.state.owned_clients == [client]
    with TestClient(application):
        assert closed == []
    assert closed == [client]


def test_injected_redis_client_is_not_registered_or_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SpyRedis()
    monkeypatch.setattr(app.main, "Redis", ForbiddenRedis)
    application = create_app(make_settings(**REDIS_BACKEND), FakeClock(), redis_client=client)
    assert application.state.redis_client is client
    assert application.state.owned_clients == []
    with TestClient(application):
        pass
    assert client.closes == 0
    asyncio.run(client.aclose())


@pytest.mark.parametrize("injected", [False, True], ids=["no-client", "injected-client"])
def test_memory_backend_builds_nothing_and_closes_nothing(
    injected: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.main, "Redis", ForbiddenRedis)
    client = SpyRedis() if injected else None
    application = create_app(make_settings(), FakeClock(), redis_client=client)
    assert application.state.owned_clients == []
    with TestClient(application):
        pass
    assert application.state.owned_clients == []
    if client is not None:
        assert client.closes == 0
        asyncio.run(client.aclose())


def test_two_owned_clients_close_in_reverse_order_and_only_at_shutdown() -> None:
    log: list[str] = []
    first = FakeClient("first", log=log)
    second = FakeClient("second", log=log)
    application = create_app(make_settings(), FakeClock())
    # Appended after create_app, so the lifespan must read the live list.
    application.state.owned_clients.extend([first, second])
    with TestClient(application):
        assert log == []
    assert log == ["second", "first"]
    assert (first.closes, second.closes) == (1, 1)


def test_three_owned_clients_close_in_full_reverse_order() -> None:
    log: list[str] = []
    application = create_app(make_settings(), FakeClock())
    application.state.owned_clients.extend(FakeClient(name, log=log) for name in "abc")
    with TestClient(application):
        pass
    assert log == ["c", "b", "a"]


@pytest.mark.parametrize("failing", ["a", "b", "c"])
def test_a_close_that_raises_does_not_stop_the_others_and_is_raised_after(failing: str) -> None:
    log: list[str] = []
    boom = RuntimeError("close failed")
    application = create_app(make_settings(), FakeClock())
    application.state.owned_clients.extend(
        FakeClient(name, log=log, error=boom if name == failing else None) for name in "abc"
    )
    with pytest.raises(BaseExceptionGroup) as raised, TestClient(application):
        pass
    assert log == ["c", "b", "a"]
    assert leaves(raised.value) == [boom]


def test_every_failing_close_is_reported() -> None:
    log: list[str] = []
    first_error = RuntimeError("first failed")
    second_error = RuntimeError("second failed")
    application = create_app(make_settings(), FakeClock())
    application.state.owned_clients.extend(
        [
            FakeClient("first", log=log, error=first_error),
            FakeClient("second", log=log, error=second_error),
        ]
    )
    with pytest.raises(BaseExceptionGroup) as raised, TestClient(application):
        pass
    assert log == ["second", "first"]
    assert leaves(raised.value) == [second_error, first_error]


def test_a_close_that_raises_a_base_exception_propagates_unchanged() -> None:
    # KeyboardInterrupt and CancelledError must never be collected into the ExceptionGroup.
    log: list[str] = []
    interrupt = KeyboardInterrupt()
    clients = [FakeClient("ok", log=log), FakeClient("stop", log=log, error=interrupt)]

    async def close() -> None:
        await _close_all(clients)

    with pytest.raises(KeyboardInterrupt) as raised:
        asyncio.run(close())
    assert raised.value is interrupt
    assert log == ["stop"]
