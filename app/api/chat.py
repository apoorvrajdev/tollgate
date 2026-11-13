"""POST /v1/chat/completions: authenticate, reserve tokens, call the provider, settle (ADR-0007).

The limiter key is always the authenticated caller id (the SHA-256 digest of the API key, T-103),
never a value taken from the request, because buckets are never evicted.

The limit headers come from the Decision that `reserve` returned, so a 200 shows the balance after
the reservation (made from the estimate) and a 502 shows the balance before the refund; the next
request sees the settled balance (owner decision, T-108). A 400 is rejected before any reservation
and carries no limit headers.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from app.api.auth import UNAUTHORIZED_RESPONSE, AuthenticatedRoute, CallerIdentity, require_api_key
from app.api.errors import ErrorBody, ErrorResponse
from app.api.limit_headers import LIMIT_HEADERS_OPENAPI, RETRY_AFTER_OPENAPI, limit_headers
from app.api.models import ChatRequest, ChatResponse
from app.limits.estimate import TokenEstimator, reserved_tokens
from app.limits.limiter import Decision, RateLimiter
from app.providers.base import Provider

RATE_LIMIT_ERROR_TYPE = "tokens"
RATE_LIMIT_ERROR_CODE = "rate_limit_exceeded"
PROVIDER_ERROR_TYPE = "api_error"
PROVIDER_ERROR_CODE = "provider_error"
PROVIDER_ERROR_MESSAGE = "The upstream provider failed to complete the request."

router = APIRouter(route_class=AuthenticatedRoute)


def get_provider(request: Request) -> Provider:
    provider: Provider = request.app.state.provider
    return provider


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
        200: {"headers": LIMIT_HEADERS_OPENAPI},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        **UNAUTHORIZED_RESPONSE,
        429: {
            "model": ErrorResponse,
            "description": "Token rate limit exceeded, or the request is larger than the limit",
            "headers": {**LIMIT_HEADERS_OPENAPI, **RETRY_AFTER_OPENAPI},
        },
        502: {
            "model": ErrorResponse,
            "description": "The provider failed; the reservation was refunded",
            "headers": LIMIT_HEADERS_OPENAPI,
        },
    },
)
async def create_chat_completion(
    body: ChatRequest,
    response: Response,
    caller: Annotated[CallerIdentity, Depends(require_api_key)],
    provider: Annotated[Provider, Depends(get_provider)],
    limiter: Annotated[RateLimiter, Depends(get_limiter)],
    estimator: Annotated[TokenEstimator, Depends(get_estimator)],
) -> ChatResponse | JSONResponse:
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
    # Only the provider call is guarded: a limiter error must not refund a reservation that was
    # never made. The exception text is never sent, because it can hold provider internals.
    try:
        completion = await provider.complete(body)
    except Exception:
        await limiter.settle(key, requested_tokens, 0)
        failure = ErrorBody(
            message=PROVIDER_ERROR_MESSAGE,
            type=PROVIDER_ERROR_TYPE,
            param=None,
            code=PROVIDER_ERROR_CODE,
        )
        return error_response(502, failure, headers)
    await limiter.settle(key, requested_tokens, completion.usage.total_tokens)
    response.headers.update(headers)
    return completion
