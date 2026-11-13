"""The Ollama adapter (ADR-0010): `POST /api/chat` on plain httpx.

One attempt per call. Every failure it can classify is a `ProviderError` whose message holds only
the kind and the HTTP status, never the response body (which can echo the prompt) or the URL. The
status is read before the body, and the body of a non-2xx answer is never read.
"""

import json
from typing import Any, Literal

import httpx

from app.api.models import ChatRequest, ChatResponse, Choice, ResponseMessage, Usage
from app.clock import Clock
from app.providers.errors import ProviderError
from app.providers.ids import IdSource

DEFAULT_BASE_URL = "http://localhost:11434"
CHAT_PATH = "/api/chat"
RATE_LIMITED_STATUS = 429

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


def _text(value: object, status: int) -> str:
    """A string that can be sent back as UTF-8 (empty is allowed), else a bad response."""
    if not isinstance(value, str):
        raise ProviderError("bad_response", status)
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:  # a lone surrogate from a JSON escape
        raise ProviderError("bad_response", status) from None
    return value


def _count(payload: dict[str, Any], key: str, status: int) -> int:
    """A token count: absent is 0; present must be a whole number of at least 0 (not a bool)."""
    if key not in payload:
        return 0
    value = payload[key]
    if type(value) is not int or value < 0:
        raise ProviderError("bad_response", status)
    return value


def _translate(payload: object, status: int, clock: Clock, id_source: IdSource) -> ChatResponse:
    if not isinstance(payload, dict):
        raise ProviderError("bad_response", status)
    message = payload.get("message")
    if not isinstance(message, dict):
        raise ProviderError("bad_response", status)
    content = _text(message.get("content"), status)
    model = _text(payload.get("model"), status)
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


def _status_error(status: int) -> ProviderError:
    if status == RATE_LIMITED_STATUS:
        return ProviderError("rate_limited", status)
    return ProviderError("upstream_status", status)


class OllamaProvider:
    def __init__(self, client: httpx.AsyncClient, clock: Clock, id_source: IdSource) -> None:
        self._client = client
        self._clock = clock
        self._id_source = id_source

    async def complete(self, request: ChatRequest) -> ChatResponse:
        status = 0
        try:
            async with self._client.stream("POST", CHAT_PATH, json=_chat_body(request)) as response:
                status = response.status_code
                if not response.is_success:
                    raise _status_error(status)
                content = await response.aread()
        # httpx.TimeoutException is a subclass of httpx.TransportError, so it is checked first.
        except httpx.TimeoutException:
            raise ProviderError("timeout") from None
        except httpx.TransportError:
            raise ProviderError("connection") from None
        except httpx.DecodingError:
            raise ProviderError("bad_response", status) from None
        try:
            payload = json.loads(content.decode("utf-8"))
        except (
            ValueError,
            RecursionError,
        ):  # invalid UTF-8, invalid JSON, empty body, deep nesting
            raise ProviderError("bad_response", status) from None
        return _translate(payload, status, self._clock, self._id_source)
