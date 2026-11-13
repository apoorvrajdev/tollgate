import os
from collections.abc import Mapping
from typing import Any, Literal

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
from app.providers.mock import MockProvider, UuidIdSource
from app.routing.config import ROUTES_FILE_VAR, MockProviderConfig, RouteTable, format_path
from app.routing.router import TableRouter
from app.settings import (
    CAPACITY_TOKENS_VAR,
    REDIS_URL_VAR,
    TOKENS_PER_MINUTE_VAR,
    Settings,
    SettingsError,
)

# Provider types this build can serve. Each adapter task adds its type (T-204 to T-206).
BUILT_PROVIDER_TYPES = ("mock",)


class HealthResponse(BaseModel):
    status: Literal["ok"]


class TollgateApp(FastAPI):
    """FastAPI whose OpenAPI document omits the automatic 422, because the API answers 400."""

    def openapi(self) -> dict[str, Any]:
        return strip_validation_error_schemas(super().openapi())


def _check_redis_range(settings: Settings) -> None:
    """Turn the Redis limiter's range limit into a startup error that names the variable."""
    reason = f"must be at most {MAX_TOKENS:,} when the limiter backend is 'redis'"
    if settings.tokens_per_minute > MAX_TOKENS:
        raise SettingsError(TOKENS_PER_MINUTE_VAR, reason)
    if settings.capacity_tokens > MAX_TOKENS:
        raise SettingsError(CAPACITY_TOKENS_VAR, reason)


def build_limiter(
    settings: Settings, clock: Clock, redis_client: Redis | None
) -> tuple[RateLimiter, Redis | None]:
    """The limiter chosen by `settings.limiter_backend`, and the Redis client it uses, if any.

    With the redis backend an injected client is used (tests pass a fakeredis client); otherwise
    one is built from the URL, which connects lazily. The memory backend ignores the client.
    """
    if settings.limiter_backend == "memory":
        limiter = InMemoryRateLimiter(clock, settings.tokens_per_minute, settings.capacity_tokens)
        return limiter, None
    _check_redis_range(settings)
    if redis_client is None:
        if settings.redis_url is None:  # Settings guarantees a URL for this backend.
            raise SettingsError(REDIS_URL_VAR, "is required when the limiter backend is 'redis'")
        redis_client = Redis.from_url(settings.redis_url.get_secret_value())
    redis_limiter = RedisRateLimiter(
        redis_client, clock, settings.tokens_per_minute, settings.capacity_tokens
    )
    return redis_limiter, redis_client


def build_providers(table: RouteTable, clock: Clock) -> dict[str, Provider]:
    """One provider per entry in the route table, by name.

    A type that is not built yet stops startup; the message names the field, never a value.
    """
    providers: dict[str, Provider] = {}
    id_source = UuidIdSource()
    for name, config in table.providers.items():
        if not isinstance(config, MockProviderConfig):
            field = format_path(["providers", name, "type"])
            built = ", ".join(BUILT_PROVIDER_TYPES)
            raise SettingsError(ROUTES_FILE_VAR, f"{field}: is not built yet; built types: {built}")
        providers[name] = MockProvider(clock, id_source)
    return providers


def create_app(
    settings: Settings | None = None,
    clock: Clock | None = None,
    *,
    provider: Provider | None = None,
    providers: Mapping[str, Provider] | None = None,
    redis_client: Redis | None = None,
) -> FastAPI:
    """Build the app. With no settings it reads os.environ; start with `uvicorn --factory`.

    `provider` sets the registry entry named `mock`; `providers` then sets entries by name, so
    tests can supply several. An entry the route table does not name is never routed to. Neither
    skips the check for types not built yet.
    """
    application = TollgateApp(title="Tollgate")
    resolved_settings = settings if settings is not None else Settings.from_env(os.environ)
    resolved_clock = clock if clock is not None else SystemClock()
    application.state.settings = resolved_settings
    application.state.clock = resolved_clock
    # Built before the limiter, so a startup error never leaves a Redis client behind.
    registry = build_providers(resolved_settings.route_table, resolved_clock)
    if provider is not None:
        registry["mock"] = provider
    if providers is not None:
        registry.update(providers)
    application.state.providers = registry
    application.state.router = TableRouter(resolved_settings.route_table)
    application.state.authenticator = ApiKeyAuthenticator(resolved_settings.api_keys)
    application.state.estimator = HeuristicEstimator()
    application.state.limiter, application.state.redis_client = build_limiter(
        resolved_settings, resolved_clock, redis_client
    )
    register_error_handlers(application)
    register_auth_error_handler(application)
    application.include_router(chat.router)

    @application.get("/health", response_model=HealthResponse, status_code=200)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return application
