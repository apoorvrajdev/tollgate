"""The Anthropic adapter (ADR-0010): `POST /v1/messages` on plain httpx.

One attempt per call. Every failure it can classify is a `ProviderError` whose message holds only
the kind and the HTTP status, never the response body (which can echo the prompt or the key) or
the URL. The key is held as a `SecretStr` and put only into the `x-api-key` header of each request.
The status is read before the body, and the body of a non-2xx answer is never read. A 2xx body is
read in decoded chunks up to `max_response_bytes`, and a larger one is a bad response (ADR-0013).
"""

import json
from typing import Any, Literal

import httpx
from pydantic import SecretStr

from app.api.models import ChatRequest, ChatResponse, Choice, ResponseMessage, Usage
from app.clock import Clock
from app.providers.errors import ProviderError
from app.providers.http_body import read_capped
from app.providers.ids import IdSource
from app.routing.config import DEFAULT_MAX_RESPONSE_BYTES

DEFAULT_BASE_URL = "https://api.anthropic.com"
MESSAGES_PATH = "/v1/messages"
# This version answers 400 to any temperature, so the client's temperature is never sent (ADR-0010).
ANTHROPIC_VERSION = "2026-10-21"
RATE_LIMITED_STATUS = 429
SYSTEM_SEPARATOR = "\n"

FinishReason = Literal["stop", "length", "content_filter"]
# Anthropic's `stop_reason` values the gateway maps; any other value (tool_use, pause_turn) is a
# bad response.
_STOP_REASONS: dict[str, FinishReason] = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "model_context_window_exceeded": "length",
    "refusal": "content_filter",
}


def _messages_body(request: ChatRequest, default_max_tokens: int) -> dict[str, Any]:
    system = [m.content for m in request.messages if m.role == "system"]
    body: dict[str, Any] = {
        "model": request.model,
        # No `name`: Anthropic messages have none.
        "messages": [
            {"role": m.role, "content": m.content} for m in request.messages if m.role != "system"
        ],
    }
    if system:
        body["system"] = SYSTEM_SEPARATOR.join(system)
    if request.max_completion_tokens is not None:
        body["max_tokens"] = request.max_completion_tokens
    elif request.max_tokens is not None:
        body["max_tokens"] = request.max_tokens
    else:
        body["max_tokens"] = default_max_tokens
    return body


def _text(value: object, status: int) -> str:
    """A string that can be sent back as UTF-8 (empty is allowed), else a bad response."""
    if not isinstance(value, str):
        raise ProviderError("bad_response", status)
    encodable = True
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:  # a lone surrogate from a JSON escape
        encodable = False
    # Raised after the block: the UnicodeEncodeError holds the whole string, which can echo the key.
    if not encodable:
        raise ProviderError("bad_response", status)
    return value


def _whole_number(value: object, status: int) -> int:
    """A whole number of at least 0 (not a bool), else a bad response."""
    if type(value) is not int or value < 0:
        raise ProviderError("bad_response", status)
    return value


def _required_count(usage: dict[str, Any], key: str, status: int) -> int:
    """A token count that must be present (ADR-0010: a missing count is a bad response)."""
    if key not in usage:
        raise ProviderError("bad_response", status)
    return _whole_number(usage[key], status)


def _cache_count(usage: dict[str, Any], key: str, status: int) -> int:
    """A cache token count: absent or null is 0 (ADR-0010)."""
    value = usage.get(key)
    if value is None:
        return 0
    return _whole_number(value, status)


def _reply(content: object, status: int) -> str:
    """The `text` blocks joined in order with no separator; other block types are ignored.

    A response with no text block (a refusal, or a limit spent on thinking) is an empty reply.
    """
    if not isinstance(content, list):
        raise ProviderError("bad_response", status)
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            raise ProviderError("bad_response", status)
        if block.get("type") == "text":
            parts.append(_text(block.get("text"), status))
    return "".join(parts)


def _translate(payload: object, status: int, clock: Clock, id_source: IdSource) -> ChatResponse:
    if not isinstance(payload, dict):
        raise ProviderError("bad_response", status)
    model = _text(payload.get("model"), status)
    if not model:
        raise ProviderError("bad_response", status)
    reason = payload.get("stop_reason")
    # isinstance first: an unhashable value (a list) must not reach the dict lookup.
    if not isinstance(reason, str) or reason not in _STOP_REASONS:
        raise ProviderError("bad_response", status)
    content = _reply(payload.get("content"), status)
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        raise ProviderError("bad_response", status)
    prompt_tokens = (
        _required_count(usage, "input_tokens", status)
        + _cache_count(usage, "cache_creation_input_tokens", status)
        + _cache_count(usage, "cache_read_input_tokens", status)
    )
    completion_tokens = _required_count(usage, "output_tokens", status)
    return ChatResponse(
        id=id_source.next_id(),
        object="chat.completion",
        created=int(clock.now_seconds()),
        model=model,
        choices=[
            Choice(
                index=0,
                message=ResponseMessage(role="assistant", content=content),
                finish_reason=_STOP_REASONS[reason],
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


class AnthropicProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: SecretStr,
        default_max_tokens: int,
        clock: Clock,
        id_source: IdSource,
        *,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._default_max_tokens = default_max_tokens
        self._clock = clock
        self._id_source = id_source
        self._max_response_bytes = max_response_bytes

    async def complete(self, request: ChatRequest) -> ChatResponse:
        status = 0
        # Built per request, so no attribute and no client default header holds the key.
        headers = {
            "x-api-key": self._api_key.get_secret_value(),
            "anthropic-version": ANTHROPIC_VERSION,
        }
        body = _messages_body(request, self._default_max_tokens)
        # Each failure is raised after its `except` block, so the ProviderError has no
        # `__context__`: an httpx error can quote the x-api-key header, and a body can echo it.
        failure: ProviderError | None = None
        content = b""
        try:
            async with self._client.stream(
                "POST", MESSAGES_PATH, json=body, headers=headers
            ) as response:
                status = response.status_code
                if not response.is_success:
                    raise _status_error(status)
                content = await read_capped(response, self._max_response_bytes)
        # httpx.TimeoutException is a subclass of httpx.TransportError, so it is checked first.
        except httpx.TimeoutException:
            failure = ProviderError("timeout")
        except httpx.TransportError:
            failure = ProviderError("connection")
        except httpx.DecodingError:
            failure = ProviderError("bad_response", status)
        if failure is not None:
            raise failure
        try:
            payload = json.loads(content.decode("utf-8"))
        except (
            ValueError,
            RecursionError,
        ):  # invalid UTF-8, invalid JSON, empty body, deep nesting
            failure = ProviderError("bad_response", status)
        if failure is not None:
            raise failure
        return _translate(payload, status, self._clock, self._id_source)
