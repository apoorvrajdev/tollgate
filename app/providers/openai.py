"""The OpenAI adapter (ADR-0010): `POST /v1/chat/completions` on plain httpx.

One attempt per call. Every failure it can classify is a `ProviderError` whose message holds only
the kind and the HTTP status, never the response body (which can echo the prompt or the key) or
the URL. The key is held as a `SecretStr` and put only into the `Authorization` header of each
request. The request and the reply body are handled by `post_json` (`app/providers/http_body.py`):
the status is read first, a non-2xx body is never read, and a 2xx body is read up to
`max_response_bytes` (ADR-0013). This module only translates.
"""

from typing import Any, Literal

import httpx
from pydantic import SecretStr

from app.api.models import ChatMessage, ChatRequest, ChatResponse, Choice, ResponseMessage, Usage
from app.providers import fields
from app.providers.errors import ProviderError
from app.providers.http_body import post_json
from app.routing.config import DEFAULT_MAX_RESPONSE_BYTES

DEFAULT_BASE_URL = "https://api.openai.com"
CHAT_PATH = "/v1/chat/completions"

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


def _reply(message: dict[str, Any], reason: FinishReason, status: int) -> tuple[str, FinishReason]:
    """The reply text and the finish reason.

    Null or absent content with a non-empty refusal is an empty reply with `content_filter`.
    """
    content = message.get("content")
    if content is not None:
        return fields.text(content, status), reason
    refusal = message.get("refusal")
    # Only a non-empty refusal string explains null content (owner decision, T-205).
    if not isinstance(refusal, str) or not refusal:
        raise ProviderError("bad_response", status)
    return "", "content_filter"


def _translate(payload: object, status: int) -> ChatResponse:
    if not isinstance(payload, dict):
        raise ProviderError("bad_response", status)
    response_id = fields.non_empty_text(payload.get("id"), status)
    created = fields.whole_number(payload.get("created"), status)
    model = fields.non_empty_text(payload.get("model"), status)
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
    prompt_tokens = fields.required_count(usage, "prompt_tokens", status)
    completion_tokens = fields.required_count(usage, "completion_tokens", status)
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
        # Built per request, so no attribute and no client default header holds the key.
        headers = {"Authorization": f"Bearer {self._api_key.get_secret_value()}"}
        reply = await post_json(
            self._client,
            CHAT_PATH,
            body=_chat_body(request),
            headers=headers,
            max_response_bytes=self._max_response_bytes,
        )
        return _translate(reply.payload, reply.status_code)
