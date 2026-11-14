"""The OpenAI adapter (ADR-0010, T-205): request and response translation, failures and the key.

Every test runs the provider on an `httpx.MockTransport`: no network, no sleeping. The response
bodies are written from the documented chat completion object, including fields the gateway
ignores (`system_fingerprint`, `logprobs`, `annotations`, the usage details).
"""

import ast
import asyncio
import json
import traceback
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.api.models import ChatMessage, ChatRequest, ChatResponse
from app.providers.errors import ProviderError
from app.providers.openai import OpenAIProvider

Handler = Callable[[httpx.Request], httpx.Response]
KEY = "sk-SENTINEL-key-5d2e"
BODY_SENTINEL = "SENTINEL-body-a83f"
UPSTREAM_ID = "chatcmpl-upstream-7Q2x"
UPSTREAM_CREATED = 1767225600
OK_MESSAGE: dict[str, Any] = {
    "role": "assistant",
    "content": "hi there",
    "refusal": None,
    "annotations": [],
}
OK_CHOICE: dict[str, Any] = {
    "index": 0,
    "message": OK_MESSAGE,
    "logprobs": None,
    "finish_reason": "stop",
}
OK_USAGE: dict[str, Any] = {
    "prompt_tokens": 9,
    "completion_tokens": 12,
    "total_tokens": 21,
    "prompt_tokens_details": {"cached_tokens": 0, "audio_tokens": 0},
    "completion_tokens_details": {"reasoning_tokens": 0, "audio_tokens": 0},
}
OK_BODY: dict[str, Any] = {
    "id": UPSTREAM_ID,
    "object": "chat.completion",
    "created": UPSTREAM_CREATED,
    "model": "gpt-4o-mini-2024-07-18",
    "choices": [OK_CHOICE],
    "usage": OK_USAGE,
    "service_tier": "default",
    "system_fingerprint": "fp_0123456789",
}


def _without_removed(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value is not ...}


def ok_body(**overrides: Any) -> dict[str, Any]:
    """OK_BODY with top-level fields replaced; a value of `...` removes the field."""
    return _without_removed({**OK_BODY, **overrides})


def with_choice(**overrides: Any) -> dict[str, Any]:
    """OK_BODY whose only choice has fields replaced; `...` removes one."""
    return ok_body(choices=[_without_removed({**OK_CHOICE, **overrides})])


def with_message(**overrides: Any) -> dict[str, Any]:
    """OK_BODY whose message has fields replaced; `...` removes one."""
    return with_choice(message=_without_removed({**OK_MESSAGE, **overrides}))


def with_usage(**overrides: Any) -> dict[str, Any]:
    """OK_BODY whose usage has fields replaced; `...` removes one."""
    return ok_body(usage=_without_removed({**OK_USAGE, **overrides}))


# JSON whose text holds a lone surrogate escape, which cannot be sent back as UTF-8.
SURROGATE_CONTENT = json.dumps(with_message(content="a" + chr(0xD800))).encode("ascii")
SURROGATE_MODEL = json.dumps(ok_body(model="m" + chr(0xD800))).encode("ascii")
SURROGATE_ID = json.dumps(ok_body(id="c" + chr(0xD800))).encode("ascii")


def raw_with_count(literal: str) -> bytes:
    """A valid reply whose completion_tokens is the given JSON literal (Python accepts NaN)."""
    template = json.dumps(with_usage(completion_tokens=0))
    return template.replace('"completion_tokens": 0', '"completion_tokens": ' + literal).encode()


def json_handler(body: Any, status: int = 200) -> Handler:
    return lambda request: httpx.Response(status, json=body)


def chat_request(**overrides: Any) -> ChatRequest:
    fields: dict[str, Any] = {
        "model": "gpt-4o-mini",
        "messages": [ChatMessage(role="user", content="hello")],
    }
    fields.update(overrides)
    return ChatRequest(**fields)


class Calls:
    """Wraps a handler and records every request it sees."""

    def __init__(self, handler: Handler) -> None:
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


def run(
    handler: Handler,
    request: ChatRequest | None = None,
    *,
    base_url: str = "https://openai.test",
    max_response_bytes: int | None = None,
) -> tuple[ChatResponse | ProviderError, Calls]:
    """Run one call; return the response or the ProviderError, and the recorded requests."""
    calls = Calls(handler)
    client = httpx.AsyncClient(transport=httpx.MockTransport(calls), base_url=base_url)
    if max_response_bytes is None:
        provider = OpenAIProvider(client, SecretStr(KEY))
    else:
        provider = OpenAIProvider(client, SecretStr(KEY), max_response_bytes=max_response_bytes)

    async def go() -> ChatResponse | ProviderError:
        try:
            return await provider.complete(request or chat_request())
        except ProviderError as error:
            return error
        finally:
            await client.aclose()

    return asyncio.run(go()), calls


def response_for(handler: Handler, request: ChatRequest | None = None) -> ChatResponse:
    result, _ = run(handler, request)
    assert isinstance(result, ChatResponse), result
    return result


def error_for(handler: Handler, request: ChatRequest | None = None) -> ProviderError:
    result, _ = run(handler, request)
    assert isinstance(result, ProviderError), result
    return result


def sent(request: ChatRequest, **kwargs: Any) -> httpx.Request:
    _, calls = run(json_handler(OK_BODY), request, **kwargs)
    assert len(calls.requests) == 1
    return calls.requests[0]


def sent_body(request: ChatRequest) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(sent(request).content)
    return body


# Criterion 1: request translation.


def test_request_is_a_post_to_v1_chat_completions_with_exactly_the_translated_body() -> None:
    request = sent(chat_request())
    assert request.method == "POST"
    assert request.url.path == "/v1/chat/completions"
    assert request.headers["content-type"] == "application/json"
    assert json.loads(request.content) == {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "hello"}],
    }


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"max_tokens": 7}, 7),
        ({"max_completion_tokens": 9}, 9),
        ({"max_tokens": 7, "max_completion_tokens": 9}, 9),
        ({"max_tokens": 1}, 1),
    ],
    ids=["max-tokens", "max-completion-tokens", "completion-wins", "one"],
)
def test_max_completion_tokens_comes_from_max_completion_tokens_else_max_tokens(
    fields: dict[str, int], expected: int
) -> None:
    body = sent_body(chat_request(**fields))
    assert body["max_completion_tokens"] == expected
    assert "max_tokens" not in body


def test_no_max_field_sends_neither_max_key() -> None:
    body = sent_body(chat_request())
    assert "max_completion_tokens" not in body
    assert "max_tokens" not in body


@pytest.mark.parametrize("temperature", [0.0, 1.2, 2.0])
def test_temperature_is_forwarded_when_given_including_zero(temperature: float) -> None:
    body = sent_body(chat_request(temperature=temperature))
    assert body["temperature"] == temperature
    assert type(body["temperature"]) is float


def test_temperature_is_left_out_when_not_given() -> None:
    assert "temperature" not in sent_body(chat_request())


def test_name_is_forwarded_only_on_messages_that_have_one_in_order() -> None:
    messages = [
        ChatMessage(role="system", content="be brief", name="rules"),
        ChatMessage(role="user", content="hi", name="ann"),
        ChatMessage(role="assistant", content="hello"),
        ChatMessage(role="user", content="and you?"),
    ]
    assert sent_body(chat_request(messages=messages))["messages"] == [
        {"role": "system", "content": "be brief", "name": "rules"},
        {"role": "user", "content": "hi", "name": "ann"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "and you?"},
    ]


def test_user_n_and_stream_are_not_sent() -> None:
    request = sent(chat_request(user="SENTINEL-user-1d0e", n=1, stream=False))
    assert set(json.loads(request.content)) == {"model", "messages"}
    assert b"SENTINEL-user-1d0e" not in request.content


def test_all_fields_together_give_the_exact_body() -> None:
    request = chat_request(
        messages=[ChatMessage(role="user", content="hi", name="ann")],
        max_tokens=5,
        max_completion_tokens=6,
        temperature=0.5,
        user="u",
        n=1,
        stream=False,
    )
    assert sent_body(request) == {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "hi", "name": "ann"}],
        "max_completion_tokens": 6,
        "temperature": 0.5,
    }


def test_non_ascii_content_is_sent_as_utf_8() -> None:
    content = "café 你好 \U0001f600"
    messages = [ChatMessage(role="user", content=content)]
    assert sent_body(chat_request(messages=messages))["messages"][0]["content"] == content


def test_the_key_is_sent_only_as_a_bearer_authorization_header() -> None:
    request = sent(chat_request())
    assert request.headers.get_list("authorization") == [f"Bearer {KEY}"]
    others = [value for name, value in request.headers.items() if name != "authorization"]
    assert all(KEY not in value for value in others)
    assert KEY not in str(request.url)
    assert KEY.encode() not in request.content


def test_the_key_is_never_a_default_header_of_the_client() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(json_handler(OK_BODY)), base_url="https://openai.test"
    )
    provider = OpenAIProvider(client, SecretStr(KEY))

    async def go() -> None:
        await provider.complete(chat_request())
        await client.aclose()

    asyncio.run(go())
    assert "authorization" not in client.headers


def test_the_base_url_path_prefix_is_kept() -> None:
    url = sent(chat_request(), base_url="https://gw.test/prefix").url
    assert str(url) == "https://gw.test/prefix/v1/chat/completions"


# Criterion 2: response translation.


def test_a_stop_response_is_translated_in_full() -> None:
    response = response_for(json_handler(with_usage(total_tokens=999)))
    assert response.model_dump() == {
        "id": UPSTREAM_ID,
        "object": "chat.completion",
        "created": UPSTREAM_CREATED,
        "model": "gpt-4o-mini-2024-07-18",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "hi there"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 9, "completion_tokens": 12, "total_tokens": 21},
    }


@pytest.mark.parametrize("reason", ["stop", "length", "content_filter"])
def test_each_documented_finish_reason_maps_as_it_is(reason: str) -> None:
    response = response_for(json_handler(with_choice(finish_reason=reason)))
    assert response.choices[0].finish_reason == reason
    assert response.choices[0].message.content == "hi there"


@pytest.mark.parametrize(
    ("content", "reason"),
    [(None, "stop"), (None, "length"), (None, "content_filter"), (..., "stop")],
    ids=["null-stop", "null-length", "null-content-filter", "absent-stop"],
)
def test_null_or_absent_content_with_a_refusal_is_an_empty_reply_with_content_filter(
    content: Any, reason: str
) -> None:
    message = {**OK_MESSAGE, "content": content, "refusal": "I can't help with that."}
    body = with_choice(message=_without_removed(message), finish_reason=reason)
    choice = response_for(json_handler(body)).choices[0]
    assert (choice.message.content, choice.finish_reason) == ("", "content_filter")


def test_a_refusal_alongside_string_content_keeps_the_content_and_the_finish_reason() -> None:
    body = with_message(content="partial", refusal="I can't help with that.")
    choice = response_for(json_handler(body)).choices[0]
    assert (choice.message.content, choice.finish_reason) == ("partial", "stop")


@pytest.mark.parametrize(
    ("overrides", "prompt", "completion"),
    [
        ({"total_tokens": ...}, 9, 12),
        ({"total_tokens": None}, 9, 12),
        ({"total_tokens": -5}, 9, 12),
        ({"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, 0, 0),
        ({"prompt_tokens": 0}, 0, 12),
        ({"completion_tokens": 0}, 9, 0),
        ({"prompt_tokens": 1_000_000, "completion_tokens": 2_000_000}, 1_000_000, 2_000_000),
    ],
    ids=[
        "no-total",
        "null-total",
        "wrong-total",
        "zero-counts",
        "zero-prompt",
        "zero-completion",
        "large-counts",
    ],
)
def test_the_total_is_prompt_plus_completion_whatever_upstream_reports(
    overrides: dict[str, Any], prompt: int, completion: int
) -> None:
    usage = response_for(json_handler(with_usage(**overrides))).usage
    assert (usage.prompt_tokens, usage.completion_tokens) == (prompt, completion)
    assert usage.total_tokens == prompt + completion


def test_an_empty_reply_is_valid() -> None:
    assert response_for(json_handler(with_message(content=""))).choices[0].message.content == ""


@pytest.mark.parametrize("role", [..., "user", "tool", ""], ids=["absent", "user", "tool", "empty"])
def test_the_output_role_is_assistant_whatever_role_the_reply_names(role: Any) -> None:
    response = response_for(json_handler(with_message(role=role)))
    assert response.choices[0].message.role == "assistant"


def test_only_the_first_choice_is_used_and_its_index_is_zero() -> None:
    second = {**OK_CHOICE, "index": 1, "message": {**OK_MESSAGE, "content": "second"}}
    first = {**OK_CHOICE, "index": 3}
    choices = response_for(json_handler(ok_body(choices=[first, second]))).choices
    assert len(choices) == 1
    assert (choices[0].index, choices[0].message.content) == (0, "hi there")


@pytest.mark.parametrize("status", [200, 201, 299])
def test_any_2xx_with_a_valid_body_succeeds(status: int) -> None:
    assert response_for(json_handler(OK_BODY, status)).usage.total_tokens == 21


# Criterion 3: errors.

BAD_RESPONSES: list[tuple[str, Handler]] = [
    ("invalid-json", lambda request: httpx.Response(200, content=b"{not json")),
    ("empty-body", lambda request: httpx.Response(200, content=b"")),
    ("no-content-204", lambda request: httpx.Response(204)),
    ("invalid-utf-8", lambda request: httpx.Response(200, content=b'{"a": "\xff"}')),
    ("deeply-nested", lambda request: httpx.Response(200, content=b"[" * 100_000)),
    ("top-level-list", json_handler([OK_BODY])),
    ("top-level-null", json_handler(None)),
    (
        "corrupt-gzip",
        lambda request: httpx.Response(
            200, headers={"content-encoding": "gzip"}, stream=httpx.ByteStream(b"not gzip")
        ),
    ),
    ("no-id", json_handler(ok_body(id=...))),
    ("id-null", json_handler(ok_body(id=None))),
    ("id-int", json_handler(ok_body(id=5))),
    ("id-empty", json_handler(ok_body(id=""))),
    ("id-lone-surrogate", lambda request: httpx.Response(200, content=SURROGATE_ID)),
    ("no-created", json_handler(ok_body(created=...))),
    ("created-null", json_handler(ok_body(created=None))),
    ("created-bool", json_handler(ok_body(created=True))),
    ("created-float", json_handler(ok_body(created=1.5))),
    ("created-whole-float", json_handler(ok_body(created=1767225600.0))),
    ("created-string", json_handler(ok_body(created="1767225600"))),
    ("created-negative", json_handler(ok_body(created=-1))),
    ("no-model", json_handler(ok_body(model=...))),
    ("model-null", json_handler(ok_body(model=None))),
    ("model-empty", json_handler(ok_body(model=""))),
    ("model-int", json_handler(ok_body(model=5))),
    ("model-lone-surrogate", lambda request: httpx.Response(200, content=SURROGATE_MODEL)),
    ("no-choices", json_handler(ok_body(choices=...))),
    ("choices-null", json_handler(ok_body(choices=None))),
    ("choices-empty", json_handler(ok_body(choices=[]))),
    ("choices-dict", json_handler(ok_body(choices=OK_CHOICE))),
    ("choice-string", json_handler(ok_body(choices=["x"]))),
    ("no-message", json_handler(with_choice(message=...))),
    ("message-null", json_handler(with_choice(message=None))),
    ("message-string", json_handler(with_choice(message="hi"))),
    ("content-null-no-refusal", json_handler(with_message(content=None, refusal=...))),
    ("content-absent-no-refusal", json_handler(with_message(content=..., refusal=...))),
    ("content-null-refusal-null", json_handler(with_message(content=None, refusal=None))),
    ("content-null-refusal-empty", json_handler(with_message(content=None, refusal=""))),
    ("content-null-refusal-int", json_handler(with_message(content=None, refusal=5))),
    ("content-null-refusal-list", json_handler(with_message(content=None, refusal=["no"]))),
    ("content-int", json_handler(with_message(content=5))),
    ("content-list", json_handler(with_message(content=[{"type": "text", "text": "x"}]))),
    ("content-lone-surrogate", lambda request: httpx.Response(200, content=SURROGATE_CONTENT)),
    ("no-finish-reason", json_handler(with_choice(finish_reason=...))),
    ("finish-reason-null", json_handler(with_choice(finish_reason=None))),
    ("finish-reason-tool-calls", json_handler(with_choice(finish_reason="tool_calls"))),
    ("finish-reason-function-call", json_handler(with_choice(finish_reason="function_call"))),
    (
        "finish-reason-tool-calls-with-refusal",
        json_handler(
            with_choice(
                message={**OK_MESSAGE, "content": None, "refusal": "no"},
                finish_reason="tool_calls",
            )
        ),
    ),
    ("finish-reason-upper", json_handler(with_choice(finish_reason="STOP"))),
    ("finish-reason-empty", json_handler(with_choice(finish_reason=""))),
    ("finish-reason-int", json_handler(with_choice(finish_reason=1))),
    ("finish-reason-list", json_handler(with_choice(finish_reason=["stop"]))),
    ("no-usage", json_handler(ok_body(usage=...))),
    ("usage-null", json_handler(ok_body(usage=None))),
    ("usage-list", json_handler(ok_body(usage=[9, 12]))),
    ("no-prompt-tokens", json_handler(with_usage(prompt_tokens=...))),
    ("prompt-tokens-negative", json_handler(with_usage(prompt_tokens=-1))),
    ("prompt-tokens-bool", json_handler(with_usage(prompt_tokens=True))),
    ("prompt-tokens-float", json_handler(with_usage(prompt_tokens=1.5))),
    ("prompt-tokens-whole-float", json_handler(with_usage(prompt_tokens=5.0))),
    ("prompt-tokens-string", json_handler(with_usage(prompt_tokens="7"))),
    ("prompt-tokens-null", json_handler(with_usage(prompt_tokens=None))),
    ("no-completion-tokens", json_handler(with_usage(completion_tokens=...))),
    ("completion-tokens-negative", json_handler(with_usage(completion_tokens=-1))),
    ("completion-tokens-bool", json_handler(with_usage(completion_tokens=False))),
    ("completion-tokens-float", json_handler(with_usage(completion_tokens=1.5))),
    ("completion-tokens-null", json_handler(with_usage(completion_tokens=None))),
    ("count-nan", lambda request: httpx.Response(200, content=raw_with_count("NaN"))),
    ("count-infinity", lambda request: httpx.Response(200, content=raw_with_count("Infinity"))),
]


@pytest.mark.parametrize(
    "handler", [case[1] for case in BAD_RESPONSES], ids=[case[0] for case in BAD_RESPONSES]
)
def test_a_2xx_that_cannot_be_translated_is_a_bad_response_and_not_retryable(
    handler: Handler,
) -> None:
    error = error_for(handler)
    assert error.kind == "bad_response"
    assert not error.retryable
    assert str(error) == f"provider failed: bad_response (HTTP {error.status_code})"
    assert error.status_code in (200, 204)
    # No context either: a decoding, JSON or Unicode error can hold a body that echoes the key.
    assert error.__context__ is None


def test_a_bad_response_carries_the_status_it_arrived_with() -> None:
    assert error_for(lambda request: httpx.Response(201, content=b"nope")).status_code == 201


def test_a_429_is_a_retryable_rate_limited_error() -> None:
    error = error_for(json_handler({"error": {"message": "x"}}, 429))
    assert (error.kind, error.status_code, error.retryable) == ("rate_limited", 429, True)


@pytest.mark.parametrize("status", [500, 502, 503, 504, 599])
def test_a_5xx_status_is_a_retryable_upstream_status(status: int) -> None:
    error = error_for(json_handler({"error": {"message": "x"}}, status))
    assert (error.kind, error.status_code, error.retryable) == ("upstream_status", status, True)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 408, 409, 422, 499])
def test_a_client_error_status_is_not_retryable(status: int) -> None:
    error = error_for(json_handler({"error": {"message": "x"}}, status))
    assert (error.kind, error.status_code, error.retryable) == ("upstream_status", status, False)


def test_a_redirect_is_not_followed_and_not_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://elsewhere.test/v1/x"})

    result, calls = run(handler)
    assert isinstance(result, ProviderError)
    assert (result.kind, result.status_code, result.retryable) == ("upstream_status", 302, False)
    assert len(calls.requests) == 1


@pytest.mark.parametrize("status", [503, 429, 401])
def test_the_body_of_an_error_status_is_never_read(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # Reading this body would raise a DecodingError, which is a bad response on a 2xx.
        return httpx.Response(
            status, headers={"content-encoding": "gzip"}, stream=httpx.ByteStream(b"not gzip")
        )

    error = error_for(handler)
    assert error.status_code == status
    assert error.kind != "bad_response"


def raises(exception: Exception) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exception

    return handler


@pytest.mark.parametrize(
    "exception",
    [
        httpx.ConnectTimeout("c"),
        httpx.ReadTimeout("r"),
        httpx.WriteTimeout("w"),
        httpx.PoolTimeout("p"),
    ],
    ids=["connect", "read", "write", "pool"],
)
def test_every_timeout_is_a_retryable_timeout_error(exception: Exception) -> None:
    error = error_for(raises(exception))
    assert (error.kind, error.status_code, error.retryable) == ("timeout", None, True)
    assert str(error) == "provider failed: timeout"


@pytest.mark.parametrize(
    "exception",
    [
        httpx.ConnectError("c"),
        httpx.ReadError("r"),
        httpx.RemoteProtocolError("p"),
        httpx.LocalProtocolError("l"),
    ],
    ids=["connect", "read", "remote-protocol", "local-protocol"],
)
def test_other_transport_errors_are_retryable_connection_errors(exception: Exception) -> None:
    error = error_for(raises(exception))
    assert (error.kind, error.status_code, error.retryable) == ("connection", None, True)
    assert str(error) == "provider failed: connection"


def test_one_attempt_is_made_on_a_server_error_on_a_429_and_on_a_timeout() -> None:
    for handler in (
        json_handler({"error": {}}, 500),
        json_handler({"error": {}}, 429),
        raises(httpx.ReadTimeout("r")),
    ):
        _, calls = run(handler)
        assert len(calls.requests) == 1


def test_an_error_that_is_not_an_httpx_error_propagates_unchanged() -> None:
    boom = RuntimeError("boom")
    with pytest.raises(RuntimeError) as raised:
        run(raises(boom))
    assert raised.value is boom


# Criterion 4: the key never shows.


def echo_key_in_header_error(request: httpx.Request) -> httpx.Response:
    # What h11 raises for a header value it rejects: the message holds the whole value.
    raise httpx.LocalProtocolError(f"Illegal header value {request.headers['authorization']!r}")


def echo_key_in_timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout(f"timed out sending {request.headers['authorization']}")


ECHOED = f"Incorrect API key provided: {KEY}. {BODY_SENTINEL}"


@pytest.mark.parametrize(
    "handler",
    [
        json_handler({"error": {"message": ECHOED, "code": "invalid_api_key"}}, 401),
        json_handler({"error": {"message": ECHOED}}, 403),
        json_handler({"error": {"message": ECHOED}}, 429),
        json_handler({"error": {"message": ECHOED}}, 500),
        lambda request: httpx.Response(200, content=f"{{{ECHOED}".encode()),
        json_handler(with_choice(finish_reason=ECHOED)),
        json_handler(with_usage(prompt_tokens=ECHOED)),
        json_handler(ok_body(id=..., echo=ECHOED)),
        echo_key_in_header_error,
        echo_key_in_timeout,
        raises(httpx.ConnectError(ECHOED)),
    ],
    ids=[
        "401",
        "403",
        "429",
        "500",
        "invalid-json",
        "finish-reason",
        "count",
        "missing-id",
        "header-error",
        "timeout",
        "connect",
    ],
)
def test_no_error_shows_the_key_or_the_body(handler: Handler) -> None:
    error = error_for(handler)
    text = str(error) + repr(error) + "".join(traceback.format_exception(error))
    assert KEY not in text
    assert BODY_SENTINEL not in text
    assert "openai.test" not in text
    assert error.__cause__ is None
    # Not even a suppressed context: an error reporter may read `__context__` directly.
    assert error.__context__ is None
    assert str(error) in (
        f"provider failed: {error.kind}",
        f"provider failed: {error.kind} (HTTP {error.status_code})",
    )


def test_the_provider_repr_never_shows_the_key() -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(json_handler(OK_BODY)))
    provider = OpenAIProvider(client, SecretStr(KEY))
    for text in (repr(provider), str(provider), repr(vars(provider))):
        assert KEY not in text
    asyncio.run(client.aclose())


def test_the_adapter_imports_neither_the_mock_nor_the_ollama_adapter() -> None:
    source = (Path(__file__).parent.parent / "app" / "providers" / "openai.py").read_text(
        encoding="utf-8"
    )
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert "app.providers.mock" not in imported
    assert "app.providers.ollama" not in imported
    assert "app.providers.http_body" in imported


# The reply size cap (ADR-0013).

CAP_BYTES = 1_024


def padded(size_bytes: int, body: dict[str, Any] | None = None) -> bytes:
    """A valid reply padded with JSON whitespace to exactly `size_bytes`."""
    data = json.dumps(OK_BODY if body is None else body).encode("utf-8")
    assert len(data) <= size_bytes
    return data + b" " * (size_bytes - len(data))


def chunked(status: int, data: bytes, served: list[int], chunk_bytes: int = 256) -> Handler:
    """A handler that streams `data` in chunks and records each chunk asked for in `served`."""

    async def body() -> AsyncIterator[bytes]:
        for index in range(0, len(data), chunk_bytes):
            served.append(index // chunk_bytes)
            yield data[index : index + chunk_bytes]

    return lambda request: httpx.Response(status, content=body())


def test_a_2xx_body_above_max_response_bytes_is_a_non_retryable_bad_response() -> None:
    data = padded(CAP_BYTES + 1, with_message(content=f"{KEY} {BODY_SENTINEL}"))
    result, _ = run(lambda request: httpx.Response(200, content=data), max_response_bytes=CAP_BYTES)
    assert isinstance(result, ProviderError), result
    assert (result.kind, result.status_code, result.retryable) == ("bad_response", 200, False)
    text = str(result) + repr(result) + "".join(traceback.format_exception(result))
    assert KEY not in text
    assert BODY_SENTINEL not in text
    assert result.__context__ is None


def test_a_valid_body_padded_to_exactly_max_response_bytes_is_served() -> None:
    data = padded(CAP_BYTES)
    result, _ = run(lambda request: httpx.Response(200, content=data), max_response_bytes=CAP_BYTES)
    assert isinstance(result, ChatResponse), result
    assert result.choices[0].message.content == "hi there"


@pytest.mark.parametrize(
    ("status", "kind", "retryable"),
    [(503, "upstream_status", True), (429, "rate_limited", True), (401, "upstream_status", False)],
)
def test_an_error_status_with_an_oversized_body_is_classified_by_status_and_never_read(
    status: int, kind: str, retryable: bool
) -> None:
    served: list[int] = []
    result, _ = run(chunked(status, b"x" * 2_000, served), max_response_bytes=CAP_BYTES)
    assert isinstance(result, ProviderError), result
    assert (result.kind, result.status_code, result.retryable) == (kind, status, retryable)
    assert served == []


@pytest.mark.parametrize(
    ("size_bytes", "served_ok"),
    [(8_388_608, True), (8_388_609, False)],
    ids=["8-mib", "8-mib-plus-1"],
)
def test_the_adapter_default_cap_is_8_mib(size_bytes: int, served_ok: bool) -> None:
    data = padded(size_bytes)
    result, _ = run(lambda request: httpx.Response(200, content=data))
    if served_ok:
        assert isinstance(result, ChatResponse), result
    else:
        assert isinstance(result, ProviderError), result
        assert (result.kind, result.status_code) == ("bad_response", 200)
