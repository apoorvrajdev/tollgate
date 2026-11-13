"""POST /v1/chat/completions. It requires an API key (T-103); limits (T-108) are added later."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.auth import UNAUTHORIZED_RESPONSE, AuthenticatedRoute, require_api_key
from app.api.errors import ErrorResponse
from app.api.models import ChatRequest, ChatResponse
from app.providers.base import Provider

router = APIRouter(route_class=AuthenticatedRoute)


def get_provider(request: Request) -> Provider:
    provider: Provider = request.app.state.provider
    return provider


@router.post(
    "/v1/chat/completions",
    response_model=ChatResponse,
    status_code=200,
    dependencies=[Depends(require_api_key)],
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        **UNAUTHORIZED_RESPONSE,
    },
)
async def create_chat_completion(
    body: ChatRequest, provider: Annotated[Provider, Depends(get_provider)]
) -> ChatResponse:
    return await provider.complete(body)
