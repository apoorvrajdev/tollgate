from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]


def create_app() -> FastAPI:
    application = FastAPI(title="Tollgate")

    @application.get("/health", response_model=HealthResponse, status_code=200)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return application


# Entry point for `uvicorn app.main:app`.
app = create_app()
