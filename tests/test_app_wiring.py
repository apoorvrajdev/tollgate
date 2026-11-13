import asyncio

import fakeredis
import pytest

import app.main
from app.clock import SystemClock
from app.limits.estimate import HeuristicEstimator
from app.limits.memory import InMemoryRateLimiter
from app.limits.redis_limiter import MAX_TOKENS, RedisRateLimiter
from app.main import create_app
from app.settings import SettingsError
from tests.fakes import FakeClock, make_settings

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
