"""POST /v1/chat/completions. Authentication (T-103) and limits (T-108) are added later."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.errors import ErrorResponse
from app.api.models import ChatRequest, ChatResponse
from app.providers.base import Provider

router = APIRouter()


def get_provider(request: Request) -> Provider:
    provider: Provider = request.app.state.provider
    return provider


@router.post(
    "/v1/chat/completions",
    response_model=ChatResponse,
    status_code=200,
    responses={400: {"model": ErrorResponse, "description": "Invalid request"}},
)
async def create_chat_completion(
    body: ChatRequest, provider: Annotated[Provider, Depends(get_provider)]
) -> ChatResponse:
    return await provider.complete(body)
