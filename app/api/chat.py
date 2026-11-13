"""POST /v1/chat/completions: authenticate, select a route, reserve tokens, try the route, settle.

The order is authentication, validation, route selection, estimate, reservation, then each target
of the route in turn (ADR-0007, ADR-0011). A model that no route serves gets the ADR-0011 404
before any estimate or reservation, so it carries no limit headers.

The limiter key is always the authenticated caller id (the SHA-256 digest of the API key, T-103),
never a value taken from the request, because buckets are never evicted.

There is one reservation and one settle per request. A 200 settles with the usage of the target
that served it and names that target in `x-tollgate-provider`, with the failed attempts before it
in `x-tollgate-fallbacks`. A route that ends without an answer gives the ADR-0008 502: a provider
failure is refunded in full, but an answer that could not be translated (`bad_response`) stays
charged as reserved, because the provider has probably billed it (ADR-0010).

The limit headers come from the Decision that `reserve` returned, so a 200 shows the balance after
the reservation (made from the estimate) and a 502 shows the balance before the settle; the next
request sees the settled balance (owner decision, T-108). A 400 is rejected before any reservation
and carries no limit headers.
"""

from collections.abc import Mapping
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from app.api.auth import UNAUTHORIZED_RESPONSE, AuthenticatedRoute, CallerIdentity, require_api_key
from app.api.errors import INVALID_REQUEST_ERROR, ErrorBody, ErrorResponse
from app.api.limit_headers import LIMIT_HEADERS_OPENAPI, RETRY_AFTER_OPENAPI, limit_headers
from app.api.models import ChatRequest, ChatResponse
from app.limits.estimate import TokenEstimator, reserved_tokens
from app.limits.limiter import Decision, RateLimiter
from app.providers.base import Provider
from app.routing.router import RouteFailed, Router, UnknownModelError, run_route

RATE_LIMIT_ERROR_TYPE = "tokens"
RATE_LIMIT_ERROR_CODE = "rate_limit_exceeded"
PROVIDER_ERROR_TYPE = "api_error"
PROVIDER_ERROR_CODE = "provider_error"
PROVIDER_ERROR_MESSAGE = "The upstream provider failed to complete the request."
MODEL_NOT_FOUND_CODE = "model_not_found"
MODEL_NOT_FOUND_MESSAGE = "The requested model is not available on this gateway."
PROVIDER_HEADER = "x-tollgate-provider"
FALLBACKS_HEADER = "x-tollgate-fallbacks"

ROUTING_HEADERS_OPENAPI: dict[str, dict[str, Any]] = {
    PROVIDER_HEADER: {
        "description": "The configured name of the provider that served the request",
        "schema": {"type": "string"},
    },
    FALLBACKS_HEADER: {
        "description": "The number of failed attempts before the one that served the request",
        "schema": {"type": "integer"},
    },
}

router = APIRouter(route_class=AuthenticatedRoute)


def get_providers(request: Request) -> Mapping[str, Provider]:
    providers: Mapping[str, Provider] = request.app.state.providers
    return providers


def get_router(request: Request) -> Router:
    route_selector: Router = request.app.state.router
    return route_selector


def get_limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.limiter
    return limiter


def get_estimator(request: Request) -> TokenEstimator:
    estimator: TokenEstimator = request.app.state.estimator
    return estimator


def rate_limit_message(decision: Decision, requested_tokens: int) -> str:
    """The 429 message: the limit, the requested amount and the wait (ADR-0008)."""
    if decision.retry_after_seconds is None:
        return (
            f"Request too large for tokens: limit {decision.limit_tokens}, requested "
            f"{requested_tokens}. The request is larger than the limit and can never succeed."
        )
    return (
        f"Rate limit reached for tokens: limit {decision.limit_tokens}, requested "
        f"{requested_tokens}. Try again in {decision.retry_after_seconds}s."
    )


def error_response(status_code: int, body: ErrorBody, headers: dict[str, str]) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content=ErrorResponse(error=body).model_dump(), headers=headers
    )


@router.post(
    "/v1/chat/completions",
    response_model=ChatResponse,
    status_code=200,
    responses={
        200: {"headers": {**LIMIT_HEADERS_OPENAPI, **ROUTING_HEADERS_OPENAPI}},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        **UNAUTHORIZED_RESPONSE,
        404: {
            "model": ErrorResponse,
            "description": "No route serves the requested model; nothing was reserved",
        },
        429: {
            "model": ErrorResponse,
            "description": "Token rate limit exceeded, or the request is larger than the limit",
            "headers": {**LIMIT_HEADERS_OPENAPI, **RETRY_AFTER_OPENAPI},
        },
        502: {
            "model": ErrorResponse,
            "description": (
                "The route ended without an answer: a provider failure is refunded in full, and "
                "an answer that could not be translated is charged as reserved"
            ),
            "headers": LIMIT_HEADERS_OPENAPI,
        },
    },
)
async def create_chat_completion(
    body: ChatRequest,
    response: Response,
    caller: Annotated[CallerIdentity, Depends(require_api_key)],
    providers: Annotated[Mapping[str, Provider], Depends(get_providers)],
    route_selector: Annotated[Router, Depends(get_router)],
    limiter: Annotated[RateLimiter, Depends(get_limiter)],
    estimator: Annotated[TokenEstimator, Depends(get_estimator)],
) -> ChatResponse | JSONResponse:
    try:
        route = route_selector.select(body)
    except UnknownModelError:
        not_found = ErrorBody(
            message=MODEL_NOT_FOUND_MESSAGE,
            type=INVALID_REQUEST_ERROR,
            param="model",
            code=MODEL_NOT_FOUND_CODE,
        )
        return error_response(404, not_found, {})
    key = caller.caller_id
    requested_tokens = reserved_tokens(body, estimator)
    decision = await limiter.reserve(key, requested_tokens)
    headers = limit_headers(decision)
    if not decision.allowed:
        refusal = ErrorBody(
            message=rate_limit_message(decision, requested_tokens),
            type=RATE_LIMIT_ERROR_TYPE,
            param=None,
            code=RATE_LIMIT_ERROR_CODE,
        )
        return error_response(429, refusal, headers)
    # run_route guards only the provider calls, so a limiter error is never refunded, and the
    # exception text is never sent, because it can hold provider internals.
    outcome = await run_route(route, providers, body)
    if isinstance(outcome, RouteFailed):
        actual_tokens = requested_tokens if outcome.charged else 0
        await limiter.settle(key, requested_tokens, actual_tokens)
        failure = ErrorBody(
            message=PROVIDER_ERROR_MESSAGE,
            type=PROVIDER_ERROR_TYPE,
            param=None,
            code=PROVIDER_ERROR_CODE,
        )
        return error_response(502, failure, headers)
    await limiter.settle(key, requested_tokens, outcome.completion.usage.total_tokens)
    response.headers.update(headers)
    response.headers[PROVIDER_HEADER] = outcome.provider_name
    response.headers[FALLBACKS_HEADER] = str(outcome.fallbacks)
    return outcome.completion
