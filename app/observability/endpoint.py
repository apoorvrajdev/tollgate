"""`GET /metrics` behind a token of its own (ADR-0016).

The route exists only when `TOLLGATE_METRICS_TOKEN` is set. The token is read and compared the way
API keys are (`app/api/auth.py`): raw header bytes as UTF-8, SHA-256 digests, `hmac.compare_digest`.
An API key never opens it, and the token never opens the chat route.
"""

import hmac
from collections.abc import Sequence

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import SecretStr

from app.api.auth import WWW_AUTHENTICATE_CHALLENGE, authorization_values, digest_of
from app.api.errors import INVALID_REQUEST_ERROR, ErrorBody, ErrorResponse
from app.observability.metrics import CONTENT_TYPE, MetricsRegistry
from app.observability.request_metrics import METRICS_PATH

INVALID_METRICS_TOKEN_CODE = "invalid_metrics_token"
INVALID_METRICS_TOKEN_MESSAGE = "Missing or invalid metrics token."


class MetricsTokenAuthenticator:
    def __init__(self, token: SecretStr) -> None:
        self._digest = digest_of(token.get_secret_value())

    def is_valid(self, values: Sequence[str]) -> bool:
        """True for exactly one `Authorization: Bearer <token>` value that carries the token."""
        if len(values) != 1:  # ambiguous: a proxy and this app could read different ones
            return False
        scheme, _, rest = values[0].partition(" ")
        if scheme.lower() != "bearer":
            return False
        submitted = rest.strip(" ")  # only spaces, as for API keys
        if not submitted:
            return False
        return hmac.compare_digest(self._digest, digest_of(submitted))


def unauthorized_response() -> JSONResponse:
    body = ErrorBody(
        message=INVALID_METRICS_TOKEN_MESSAGE,
        type=INVALID_REQUEST_ERROR,
        param=None,
        code=INVALID_METRICS_TOKEN_CODE,
    )
    return JSONResponse(
        status_code=401,
        content=ErrorResponse(error=body).model_dump(),
        headers={"WWW-Authenticate": WWW_AUTHENTICATE_CHALLENGE},
    )


def register_metrics_route(
    application: FastAPI, token: SecretStr, registry: MetricsRegistry
) -> None:
    """Add `GET /metrics`, left out of the OpenAPI document (the client contract)."""
    authenticator = MetricsTokenAuthenticator(token)

    # `async`, so it runs on the event loop: the registry has no lock and relies on that.
    async def metrics(request: Request) -> Response:
        if not authenticator.is_valid(authorization_values(request)):
            return unauthorized_response()
        return Response(registry.render(), media_type=CONTENT_TYPE)

    application.add_api_route(METRICS_PATH, metrics, methods=["GET"], include_in_schema=False)
