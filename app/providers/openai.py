"""The OpenAI adapter (ADR-0010): `POST /v1/chat/completions` on plain httpx.

One attempt per call. Every failure it can classify is a `ProviderError` whose message holds only
the kind and the HTTP status, never the response body (which can echo the prompt or the key) or
the URL. The key is held as a `SecretStr` and put only into the `Authorization` header of each
request. The status is read before the body, and the body of a non-2xx answer is never read. A 2xx
body is read in decoded chunks up to `max_response_bytes`, and a larger one is a bad response
(ADR-0013).
"""

import json
from typing import Any, Literal

import httpx
from pydantic import SecretStr

from app.api.models import ChatMessage, ChatRequest, ChatResponse, Choice, ResponseMessage, Usage
from app.providers.errors import ProviderError
from app.providers.http_body import read_capped
from app.routing.config import DEFAULT_MAX_RESPONSE_BYTES

DEFAULT_BASE_URL = "https://api.openai.com"
CHAT_PATH = "/v1/chat/completions"
RATE_LIMITED_STATUS = 429

FinishReason = Literal["stop", "length", "content_filter"]
# OpenAI's `finish_reason` values that map as they are; any other value (tool_calls, function_call)
# is a bad response.
_FINISH_REASONS: dict[str, FinishReason] = {
    "stop": "stop",
    "length": "length",
    "content_filter": "content_filter",
}


def _message(message: ChatMessage) -> dict[str, str]:
    sent = {"role": message.role, "content": message.content}
    if message.name is not None:
        sent["name"] = message.name
    return sent


def _chat_body(request: ChatRequest) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": request.model,
        "messages": [_message(m) for m in request.messages],
    }
    max_completion_tokens = (
        request.max_completion_tokens
        if request.max_completion_tokens is not None
        else request.max_tokens
    )
    if max_completion_tokens is not None:
        body["max_completion_tokens"] = max_completion_tokens
    if request.temperature is not None:
        body["temperature"] = request.temperature
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


def _non_empty_text(value: object, status: int) -> str:
    text = _text(value, status)
    if not text:
        raise ProviderError("bad_response", status)
    return text


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


def _reply(message: dict[str, Any], reason: FinishReason, status: int) -> tuple[str, FinishReason]:
    """The reply text and the finish reason.

    Null or absent content with a non-empty refusal is an empty reply with `content_filter`.
    """
    content = message.get("content")
    if content is not None:
        return _text(content, status), reason
    refusal = message.get("refusal")
    # Only a non-empty refusal string explains null content (owner decision, T-205).
    if not isinstance(refusal, str) or not refusal:
        raise ProviderError("bad_response", status)
    return "", "content_filter"


def _translate(payload: object, status: int) -> ChatResponse:
    if not isinstance(payload, dict):
        raise ProviderError("bad_response", status)
    response_id = _non_empty_text(payload.get("id"), status)
    created = _whole_number(payload.get("created"), status)
    model = _non_empty_text(payload.get("model"), status)
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ProviderError("bad_response", status)
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ProviderError("bad_response", status)
    reason = choices[0].get("finish_reason")
    # isinstance first: an unhashable value (a list) must not reach the dict lookup.
    if not isinstance(reason, str) or reason not in _FINISH_REASONS:
        raise ProviderError("bad_response", status)
    content, finish_reason = _reply(message, _FINISH_REASONS[reason], status)
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        raise ProviderError("bad_response", status)
    prompt_tokens = _required_count(usage, "prompt_tokens", status)
    completion_tokens = _required_count(usage, "completion_tokens", status)
    return ChatResponse(
        id=response_id,
        object="chat.completion",
        created=created,
        model=model,
        choices=[
            Choice(
                index=0,
                message=ResponseMessage(role="assistant", content=content),
                finish_reason=finish_reason,
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


class OpenAIProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: SecretStr,
        *,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._max_response_bytes = max_response_bytes

    async def complete(self, request: ChatRequest) -> ChatResponse:
        status = 0
        # Built per request, so no attribute and no client default header holds the key.
        headers = {"Authorization": f"Bearer {self._api_key.get_secret_value()}"}
        # Each failure is raised after its `except` block, so the ProviderError has no
        # `__context__`: an httpx error can quote the Authorization header, and a body can echo it.
        failure: ProviderError | None = None
        content = b""
        try:
            async with self._client.stream(
                "POST", CHAT_PATH, json=_chat_body(request), headers=headers
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
        return _translate(payload, status)
