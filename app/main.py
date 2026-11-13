import os
from typing import Any, Literal

from fastapi import FastAPI
from pydantic import BaseModel

from app.api import chat
from app.api.auth import ApiKeyAuthenticator, register_auth_error_handler
from app.api.errors import register_error_handlers, strip_validation_error_schemas
from app.clock import Clock, SystemClock
from app.providers.base import Provider
from app.providers.mock import MockProvider, UuidIdSource
from app.settings import Settings


class HealthResponse(BaseModel):
    status: Literal["ok"]


class TollgateApp(FastAPI):
    """FastAPI whose OpenAPI document omits the automatic 422, because the API answers 400."""

    def openapi(self) -> dict[str, Any]:
        return strip_validation_error_schemas(super().openapi())


def create_app(
    settings: Settings | None = None,
    clock: Clock | None = None,
    *,
    provider: Provider | None = None,
) -> FastAPI:
    """Build the app. With no settings it reads os.environ; start with `uvicorn --factory`."""
    application = TollgateApp(title="Tollgate")
    resolved_settings = settings if settings is not None else Settings.from_env(os.environ)
    application.state.settings = resolved_settings
    application.state.clock = clock if clock is not None else SystemClock()
    application.state.provider = (
        provider if provider is not None else MockProvider(application.state.clock, UuidIdSource())
    )
    application.state.authenticator = ApiKeyAuthenticator(resolved_settings.api_keys)
    register_error_handlers(application)
    register_auth_error_handler(application)
    application.include_router(chat.router)

    @application.get("/health", response_model=HealthResponse, status_code=200)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return application
