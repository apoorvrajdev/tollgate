import os
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Any, Literal, NamedTuple, Protocol, assert_never

import httpx
from fastapi import FastAPI
from fastapi.telemetry import TelemetryConfig
from pydantic import BaseModel
from redis.asyncio import Redis

from app.api import chat
from app.api.auth import ApiKeyAuthenticator, register_auth_error_handler
from app.api.errors import register_error_handlers, strip_validation_error_schemas
from app.cache.embedder import Embedder
from app.cache.ollama_embedder import OllamaEmbedder
from app.cache.semantic import InMemorySemanticCache, SemanticCache
from app.clock import Clock, MonotonicClock, SystemClock, SystemMonotonicClock
from app.limits.estimate import HeuristicEstimator
from app.limits.limiter import RateLimiter
from app.limits.memory import InMemoryRateLimiter
from app.limits.redis_limiter import MAX_TOKENS, RedisRateLimiter
from app.observability.logs import log_request
from app.observability.middleware import RequestMiddleware
from app.providers.anthropic import DEFAULT_BASE_URL as ANTHROPIC_DEFAULT_BASE_URL
from app.providers.anthropic import AnthropicProvider
from app.providers.base import Provider
from app.providers.ids import IdSource, UuidIdSource
from app.providers.mock import MockProvider
from app.providers.ollama import DEFAULT_BASE_URL as OLLAMA_DEFAULT_BASE_URL
from app.providers.ollama import OllamaProvider
from app.providers.openai import DEFAULT_BASE_URL as OPENAI_DEFAULT_BASE_URL
from app.providers.openai import OpenAIProvider
from app.routing.config import (
    MIN_TIMEOUT_SECONDS,
    AnthropicProviderConfig,
    MockProviderConfig,
    OllamaProviderConfig,
    OpenAIProviderConfig,
    RouteTable,
)
from app.routing.router import TableRouter
from app.settings import (
    CACHE_EMBEDDER_URL_VAR,
    CAPACITY_TOKENS_VAR,
    REDIS_URL_VAR,
    TOKENS_PER_MINUTE_VAR,
    CacheSettings,
    Settings,
    SettingsError,
)

# The connect timeout is fixed; `timeout_seconds` covers reads, writes and the pool (ADR-0010).
CONNECT_TIMEOUT_SECONDS = MIN_TIMEOUT_SECONDS
# The embedder's timeouts are fixed too (ADR-0015): 5 seconds to connect, 10 for the rest.
EMBEDDER_CONNECT_TIMEOUT_SECONDS = 5
EMBEDDER_TIMEOUT_SECONDS = 10
# FastAPI's own spans, metrics and logs stay off, so an OpenTelemetry SDK installed later starts no
# second, unreviewed set of them (ADR-0016). `auto_configure` is set explicitly because its default
# reads an environment variable.
NATIVE_TELEMETRY_OFF: TelemetryConfig = {
    "tracing": False,
    "metrics": False,
    "logs": False,
    "operation_spans": False,
    "auto_configure": False,
}


class AsyncCloseable(Protocol):
    """A client the app closes at shutdown: a Redis client or an httpx.AsyncClient."""

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
    config: OllamaProviderConfig | OpenAIProviderConfig | AnthropicProviderConfig,
    transport: httpx.AsyncBaseTransport | None,
    *,
    default_base_url: str,
) -> httpx.AsyncClient:
    """One client for one HTTP provider. Tests pass an `httpx.MockTransport`; none connects here.

    An absent or empty `base_url` means the provider's `default_base_url`.
    """
    seconds = config.timeout_seconds
    timeout = httpx.Timeout(
        connect=CONNECT_TIMEOUT_SECONDS, read=seconds, write=seconds, pool=seconds
    )
    base_url = config.base_url or default_base_url
    return httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport)


def build_embedder(
    cache: CacheSettings, transport: httpx.AsyncBaseTransport | None
) -> tuple[httpx.AsyncClient, OllamaEmbedder]:
    """The Ollama embedder on its own client. Nothing connects here; tests pass a MockTransport."""
    timeout = httpx.Timeout(
        connect=EMBEDDER_CONNECT_TIMEOUT_SECONDS,
        read=EMBEDDER_TIMEOUT_SECONDS,
        write=EMBEDDER_TIMEOUT_SECONDS,
        pool=EMBEDDER_TIMEOUT_SECONDS,
    )
    failed = False
    try:
        client = httpx.AsyncClient(
            base_url=cache.embedder_url.get_secret_value(), timeout=timeout, transport=transport
        )
    except httpx.InvalidURL:  # its message can echo part of the URL, which can hold credentials
        failed = True
    if failed:
        raise SettingsError(CACHE_EMBEDDER_URL_VAR, "is not a valid URL")
    return client, OllamaEmbedder(client, cache.embedder_model)


def build_providers(
    table: RouteTable,
    clock: Clock,
    http_transport: httpx.AsyncBaseTransport | None = None,
    *,
    id_source: IdSource | None = None,
) -> ProvidersBuild:
    """One provider per entry in the route table, by name, and the HTTP clients it built.

    Every provider that makes ids uses `id_source`; with None a new `UuidIdSource` is built here.
    Every type in the route table is built; mypy checks that each has a branch.
    """
    providers: dict[str, Provider] = {}
    clients: list[AsyncCloseable] = []
    if id_source is None:
        id_source = UuidIdSource()
    for name, config in table.providers.items():
        if isinstance(config, MockProviderConfig):
            providers[name] = MockProvider(clock, id_source)
        elif isinstance(config, OllamaProviderConfig):
            client = build_http_client(
                config, http_transport, default_base_url=OLLAMA_DEFAULT_BASE_URL
            )
            clients.append(client)
            providers[name] = OllamaProvider(
                client, clock, id_source, max_response_bytes=config.max_response_bytes
            )
        elif isinstance(config, OpenAIProviderConfig):
            client = build_http_client(
                config, http_transport, default_base_url=OPENAI_DEFAULT_BASE_URL
            )
            clients.append(client)
            providers[name] = OpenAIProvider(
                client, table.api_keys[name], max_response_bytes=config.max_response_bytes
            )
        elif isinstance(config, AnthropicProviderConfig):
            client = build_http_client(
                config, http_transport, default_base_url=ANTHROPIC_DEFAULT_BASE_URL
            )
            clients.append(client)
            providers[name] = AnthropicProvider(
                client,
                table.api_keys[name],
                config.default_max_tokens,
                clock,
                id_source,
                max_response_bytes=config.max_response_bytes,
            )
        else:
            assert_never(config)
    return ProvidersBuild(providers, tuple(clients))


def create_app(
    settings: Settings | None = None,
    clock: Clock | None = None,
    *,
    provider: Provider | None = None,
    providers: Mapping[str, Provider] | None = None,
    redis_client: Redis | None = None,
    http_transport: httpx.AsyncBaseTransport | None = None,
    embedder: Embedder | None = None,
    monotonic_clock: MonotonicClock | None = None,
) -> FastAPI:
    """Build the app. With no settings it reads os.environ; start with `uvicorn --factory`.

    `provider` sets the registry entry named `mock`; `providers` then sets entries by name, so
    tests can supply several. An entry the route table does not name is never routed to; one it
    names replaces the provider built for that name. `http_transport` is used by every HTTP client
    the app builds (tests pass an `httpx.MockTransport`).

    A client the app builds is appended to `app.state.owned_clients`; the lifespan closes them at
    shutdown, last built first. A client passed in is the caller's to close.

    With the cache on the app builds an `OllamaEmbedder` on its own client, kept on
    `app.state.embedder`; `embedder` replaces it (and no client is built). Passing one while the
    cache is off raises ValueError, so a test cannot believe it exercises a cache that is not there.
    The cache is an `InMemorySemanticCache` on that embedder and the clock, kept on
    `app.state.cache` (None when the cache is off). One `UuidIdSource`, on `app.state.id_source`,
    serves every provider. A `MonotonicClock` (`monotonic_clock`, else a `SystemMonotonicClock`),
    on `app.state.monotonic_clock`, times each provider call and each HTTP request.

    `RequestMiddleware` writes one JSON line per request to the logger `tollgate.request`
    (ADR-0016). The app installs no handler; `deploy/logging.json` does, for uvicorn.
    """
    application = TollgateApp(title="Tollgate", lifespan=_lifespan, telemetry=NATIVE_TELEMETRY_OFF)
    application.state.owned_clients = []
    resolved_settings = settings if settings is not None else Settings.from_env(os.environ)
    resolved_clock = clock if clock is not None else SystemClock()
    if embedder is not None and resolved_settings.cache is None:
        raise ValueError("embedder was passed but the cache is off")
    application.state.settings = resolved_settings
    application.state.clock = resolved_clock
    application.state.monotonic_clock = (
        monotonic_clock if monotonic_clock is not None else SystemMonotonicClock()
    )
    # The providers are built before the limiter, so a limiter error never leaves a Redis client
    # behind; an HTTP client built by then is unopened, and nothing needs to close it.
    id_source = UuidIdSource()
    application.state.id_source = id_source
    providers_build = build_providers(
        resolved_settings.route_table, resolved_clock, http_transport, id_source=id_source
    )
    registry = providers_build.providers
    application.state.owned_clients.extend(providers_build.built_clients)
    application.state.embedder = embedder
    if embedder is None and resolved_settings.cache is not None:
        embedder_client, application.state.embedder = build_embedder(
            resolved_settings.cache, http_transport
        )
        application.state.owned_clients.append(embedder_client)
    cache: SemanticCache | None = None  # typed, so mypy checks the Protocol is satisfied
    if resolved_settings.cache is not None:
        cache = InMemorySemanticCache(
            application.state.embedder,
            resolved_clock,
            similarity_threshold=resolved_settings.cache.similarity_threshold,
            ttl_seconds=resolved_settings.cache.ttl_seconds,
            max_entries=resolved_settings.cache.max_entries,
        )
    application.state.cache = cache
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
    application.add_middleware(RequestMiddleware, observers=(log_request,))
    application.include_router(chat.router)

    @application.get("/health", response_model=HealthResponse, status_code=200)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return application
