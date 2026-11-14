"""The Ollama adapter (ADR-0010): `POST /api/chat` on plain httpx.

One attempt per call. Every failure it can classify is a `ProviderError` whose message holds only
the kind and the HTTP status, never the response body (which can echo the prompt) or the URL. The
request and the reply body are handled by `post_json` (`app/providers/http_body.py`): the status is
read first, a non-2xx body is never read, and a 2xx body is read up to `max_response_bytes`
(ADR-0013). This module only translates.
"""

from typing import Any, Literal

import httpx

from app.api.models import ChatRequest, ChatResponse, Choice, ResponseMessage, Usage
from app.clock import Clock
from app.providers import fields
from app.providers.errors import ProviderError
from app.providers.http_body import post_json
from app.providers.ids import IdSource
from app.routing.config import DEFAULT_MAX_RESPONSE_BYTES

DEFAULT_BASE_URL = "http://localhost:11434"
CHAT_PATH = "/api/chat"

FinishReason = Literal["stop", "length"]
# Ollama's `done_reason` values that map as they are; any other value is a bad response.
_FINISH_REASONS: dict[str, FinishReason] = {"stop": "stop", "length": "length"}


def _chat_body(request: ChatRequest) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": request.model,
        "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        "stream": False,
    }
    options: dict[str, Any] = {}
    num_predict = (
        request.max_completion_tokens
        if request.max_completion_tokens is not None
        else request.max_tokens
    )
    if num_predict is not None:
        options["num_predict"] = num_predict
    if request.temperature is not None:
        options["temperature"] = request.temperature
    if options:
        body["options"] = options
    return body


def _count(payload: dict[str, Any], key: str, status: int) -> int:
    """A token count: absent is 0; present must be a whole number of at least 0 (not a bool)."""
    if key not in payload:
        return 0
    return fields.whole_number(payload[key], status)


def _translate(payload: object, status: int, clock: Clock, id_source: IdSource) -> ChatResponse:
    if not isinstance(payload, dict):
        raise ProviderError("bad_response", status)
    message = payload.get("message")
    if not isinstance(message, dict):
        raise ProviderError("bad_response", status)
    content = fields.text(message.get("content"), status)
    model = fields.text(payload.get("model"), status)
    if not model:
        raise ProviderError("bad_response", status)
    reason = payload.get("done_reason")
    # isinstance first: an unhashable value (a list) must not reach the dict lookup.
    if not isinstance(reason, str) or reason not in _FINISH_REASONS:
        raise ProviderError("bad_response", status)
    prompt_tokens = _count(payload, "prompt_eval_count", status)
    completion_tokens = _count(payload, "eval_count", status)
    return ChatResponse(
        id=id_source.next_id(),
        object="chat.completion",
        created=int(clock.now_seconds()),
        model=model,
        choices=[
            Choice(
                index=0,
                message=ResponseMessage(role="assistant", content=content),
                finish_reason=_FINISH_REASONS[reason],
            )
        ],
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


class OllamaProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        clock: Clock,
        id_source: IdSource,
        *,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ) -> None:
        self._client = client
        self._clock = clock
        self._id_source = id_source
        self._max_response_bytes = max_response_bytes

    async def complete(self, request: ChatRequest) -> ChatResponse:
        reply = await post_json(
            self._client,
            CHAT_PATH,
            body=_chat_body(request),
            headers=None,
            max_response_bytes=self._max_response_bytes,
        )
        return _translate(reply.payload, reply.status_code, self._clock, self._id_source)
