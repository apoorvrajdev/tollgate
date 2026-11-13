import os
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Any, Literal, NamedTuple, Protocol

import httpx
from fastapi import FastAPI
from pydantic import BaseModel
from redis.asyncio import Redis

from app.api import chat
from app.api.auth import ApiKeyAuthenticator, register_auth_error_handler
from app.api.errors import register_error_handlers, strip_validation_error_schemas
from app.clock import Clock, SystemClock
from app.limits.estimate import HeuristicEstimator
from app.limits.limiter import RateLimiter
from app.limits.memory import InMemoryRateLimiter
from app.limits.redis_limiter import MAX_TOKENS, RedisRateLimiter
from app.providers.base import Provider
from app.providers.ids import UuidIdSource
from app.providers.mock import MockProvider
from app.providers.ollama import DEFAULT_BASE_URL, OllamaProvider
from app.routing.config import (
    MIN_TIMEOUT_SECONDS,
    ROUTES_FILE_VAR,
    MockProviderConfig,
    OllamaProviderConfig,
    RouteTable,
    format_path,
)
from app.routing.router import TableRouter
from app.settings import (
    CAPACITY_TOKENS_VAR,
    REDIS_URL_VAR,
    TOKENS_PER_MINUTE_VAR,
    Settings,
    SettingsError,
)

# Provider types this build can serve. Each adapter task adds its type (T-204 to T-206).
BUILT_PROVIDER_TYPES = ("mock", "ollama")
# The connect timeout is fixed; `timeout_seconds` covers reads, writes and the pool (ADR-0010).
CONNECT_TIMEOUT_SECONDS = MIN_TIMEOUT_SECONDS


class AsyncCloseable(Protocol):
    """A client the app closes at shutdown: a Redis client, and later an httpx.AsyncClient."""

    async def aclose(self) -> None: ...


class LimiterBuild(NamedTuple):
    """The limiter, the Redis client it uses (if any), and the clients this build created."""

    limiter: RateLimiter
    redis_client: Redis | None
    built_clients: tuple[AsyncCloseable, ...]


class ProvidersBuild(NamedTuple):
    """The provider registry and the HTTP clients this build created."""

    providers: dict[str, Provider]
    built_clients: tuple[AsyncCloseable, ...]


class HealthResponse(BaseModel):
    status: Literal["ok"]


class TollgateApp(FastAPI):
    """FastAPI whose OpenAPI document omits the automatic 422, because the API answers 400."""

    def openapi(self) -> dict[str, Any]:
        return strip_validation_error_schemas(super().openapi())


async def _close_all(clients: Sequence[AsyncCloseable]) -> None:
    """Close every client, last built first. A close that raises does not stop the others.

    The errors are raised together once all clients have been tried, so a failure is never hidden.
    """
    errors: list[Exception] = []
    for client in reversed(clients):
        try:
            await client.aclose()
        except Exception as error:
            errors.append(error)
    if errors:
        raise ExceptionGroup("clients failed to close", errors)


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await _close_all(application.state.owned_clients)


def _check_redis_range(settings: Settings) -> None:
    """Turn the Redis limiter's range limit into a startup error that names the variable."""
    reason = f"must be at most {MAX_TOKENS:,} when the limiter backend is 'redis'"
    if settings.tokens_per_minute > MAX_TOKENS:
        raise SettingsError(TOKENS_PER_MINUTE_VAR, reason)
    if settings.capacity_tokens > MAX_TOKENS:
        raise SettingsError(CAPACITY_TOKENS_VAR, reason)


def build_limiter(settings: Settings, clock: Clock, redis_client: Redis | None) -> LimiterBuild:
    """The limiter chosen by `settings.limiter_backend`, and the Redis client it uses, if any.

    With the redis backend an injected client is used (tests pass a fakeredis client); otherwise
    one is built from the URL, which connects lazily. The memory backend ignores the client.
    Only a client built here is in `built_clients`; the caller owns it and closes it at shutdown.
    """
    if settings.limiter_backend == "memory":
        limiter = InMemoryRateLimiter(clock, settings.tokens_per_minute, settings.capacity_tokens)
        return LimiterBuild(limiter, None, ())
    _check_redis_range(settings)
    built: tuple[AsyncCloseable, ...] = ()
    if redis_client is None:
        if settings.redis_url is None:  # Settings guarantees a URL for this backend.
            raise SettingsError(REDIS_URL_VAR, "is required when the limiter backend is 'redis'")
        redis_client = Redis.from_url(settings.redis_url.get_secret_value())
        built = (redis_client,)
    redis_limiter = RedisRateLimiter(
        redis_client, clock, settings.tokens_per_minute, settings.capacity_tokens
    )
    return LimiterBuild(redis_limiter, redis_client, built)


def build_http_client(
    config: OllamaProviderConfig, transport: httpx.AsyncBaseTransport | None
) -> httpx.AsyncClient:
    """One client for one HTTP provider. Tests pass an `httpx.MockTransport`; none connects here."""
    seconds = config.timeout_seconds
    timeout = httpx.Timeout(
        connect=CONNECT_TIMEOUT_SECONDS, read=seconds, write=seconds, pool=seconds
    )
    base_url = config.base_url or DEFAULT_BASE_URL
    return httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport)


def build_providers(
    table: RouteTable, clock: Clock, http_transport: httpx.AsyncBaseTransport | None = None
) -> ProvidersBuild:
    """One provider per entry in the route table, by name, and the HTTP clients it built.

    A type that is not built yet stops startup; the message names the field, never a value.
    """
    providers: dict[str, Provider] = {}
    clients: list[AsyncCloseable] = []
    id_source = UuidIdSource()
    for name, config in table.providers.items():
        if isinstance(config, MockProviderConfig):
            providers[name] = MockProvider(clock, id_source)
        elif isinstance(config, OllamaProviderConfig):
            client = build_http_client(config, http_transport)
            clients.append(client)
            providers[name] = OllamaProvider(client, clock, id_source)
        else:
            field = format_path(["providers", name, "type"])
            built = ", ".join(BUILT_PROVIDER_TYPES)
            raise SettingsError(ROUTES_FILE_VAR, f"{field}: is not built yet; built types: {built}")
    return ProvidersBuild(providers, tuple(clients))


def create_app(
    settings: Settings | None = None,
    clock: Clock | None = None,
    *,
    provider: Provider | None = None,
    providers: Mapping[str, Provider] | None = None,
    redis_client: Redis | None = None,
    http_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    """Build the app. With no settings it reads os.environ; start with `uvicorn --factory`.

    `provider` sets the registry entry named `mock`; `providers` then sets entries by name, so
    tests can supply several. An entry the route table does not name is never routed to. Neither
    skips the check for types not built yet. `http_transport` is used by every HTTP client the app
    builds (tests pass an `httpx.MockTransport`).

    A client the app builds is appended to `app.state.owned_clients`; the lifespan closes them at
    shutdown, last built first. A client passed in is the caller's to close.
    """
    application = TollgateApp(title="Tollgate", lifespan=_lifespan)
    application.state.owned_clients = []
    resolved_settings = settings if settings is not None else Settings.from_env(os.environ)
    resolved_clock = clock if clock is not None else SystemClock()
    application.state.settings = resolved_settings
    application.state.clock = resolved_clock
    # Built before the limiter, so a startup error never leaves a Redis client behind.
    providers_build = build_providers(resolved_settings.route_table, resolved_clock, http_transport)
    registry = providers_build.providers
    application.state.owned_clients.extend(providers_build.built_clients)
    if provider is not None:
        registry["mock"] = provider
    if providers is not None:
        registry.update(providers)
    application.state.providers = registry
    application.state.router = TableRouter(resolved_settings.route_table)
    application.state.authenticator = ApiKeyAuthenticator(resolved_settings.api_keys)
    application.state.estimator = HeuristicEstimator()
    limiter_build = build_limiter(resolved_settings, resolved_clock, redis_client)
    application.state.limiter = limiter_build.limiter
    application.state.redis_client = limiter_build.redis_client
    application.state.owned_clients.extend(limiter_build.built_clients)
    register_error_handlers(application)
    register_auth_error_handler(application)
    application.include_router(chat.router)

    @application.get("/health", response_model=HealthResponse, status_code=200)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return application
