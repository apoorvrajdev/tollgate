"""The provider interface (ARCHITECTURE section 3). Adapters implement it; the router calls it."""

from typing import Protocol

from app.api.models import ChatRequest, ChatResponse


class Provider(Protocol):
    async def complete(self, request: ChatRequest) -> ChatResponse:
        """Answer one chat request. Raises if the provider fails."""
        ...
