import os
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from app.clock import Clock, SystemClock
from app.settings import Settings


class HealthResponse(BaseModel):
    status: Literal["ok"]


def create_app(settings: Settings | None = None, clock: Clock | None = None) -> FastAPI:
    """Build the app. With no settings it reads os.environ; start with `uvicorn --factory`."""
    application = FastAPI(title="Tollgate")
    application.state.settings = settings if settings is not None else Settings.from_env(os.environ)
    application.state.clock = clock if clock is not None else SystemClock()

    @application.get("/health", response_model=HealthResponse, status_code=200)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return application
