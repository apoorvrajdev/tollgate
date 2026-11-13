"""A deterministic provider for development and tests (ADR-0004).

The reply and the usage depend only on the request. Time comes from the injected Clock and the
response id from the injected IdSource, so a fixed clock and id source give identical responses.
"""

from app.api.models import ChatRequest, ChatResponse, Choice, ResponseMessage, Usage
from app.clock import Clock
from app.providers.ids import IdSource

REPLY_PREFIX = "Mock reply: "


def count_words(text: str) -> int:
    """Whitespace-separated words: the mock's stand-in for tokens."""
    return len(text.split())


class MockProvider:
    def __init__(self, clock: Clock, id_source: IdSource) -> None:
        self._clock = clock
        self._id_source = id_source

    async def complete(self, request: ChatRequest) -> ChatResponse:
        reply = REPLY_PREFIX + request.messages[-1].content
        prompt_tokens = sum(count_words(message.content) for message in request.messages)
        completion_tokens = count_words(reply)
        return ChatResponse(
            id=self._id_source.next_id(),
            object="chat.completion",
            created=int(self._clock.now_seconds()),
            model=request.model,
            choices=[
                Choice(
                    index=0,
                    message=ResponseMessage(role="assistant", content=reply),
                    finish_reason="stop",
                )
            ],
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )
