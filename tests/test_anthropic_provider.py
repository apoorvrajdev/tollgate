"""The Anthropic adapter (ADR-0010, T-206): request and response translation, failures and the key.

Every test runs the provider on an `httpx.MockTransport`: no network, no sleeping. The response
bodies are written from the documented Messages API response, including fields the gateway
ignores (the upstream `id`, `type`, `role`, `stop_sequence`, `service_tier`).
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
from app.providers.anthropic import AnthropicProvider
from app.providers.errors import ProviderError
from tests.fakes import FakeClock, FixedIdSource

Handler = Callable[[httpx.Request], httpx.Response]
KEY = "ant-SENTINEL-key-7b3c"
BODY_SENTINEL = "SENTINEL-body-c41e"
THINKING_SENTINEL = "SENTINEL-thinking-9a0d"
UPSTREAM_ID = "msg_upstream_SENTINEL_01"
FIXED_ID = "chatcmpl-fixed-anthropic"
CLOCK_SECONDS = 2000.99
DEFAULT_MAX_TOKENS = 321
OK_USAGE: dict[str, Any] = {
    "input_tokens": 10,
    "cache_creation_input_tokens": 20,
    "cache_read_input_tokens": 300,
    "output_tokens": 12,
    "service_tier": "standard",
}
OK_BODY: dict[str, Any] = {
    "id": UPSTREAM_ID,
    "type": "message",
    "role": "assistant",
    "model": "claude-sonnet-5-5",
    "content": [{"type": "text", "text": "hi there"}],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": OK_USAGE,
}


def _without_removed(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value is not ...}


def ok_body(**overrides: Any) -> dict[str, Any]:
    """OK_BODY with top-level fields replaced; a value of `...` removes the field."""
    return _without_removed({**OK_BODY, **overrides})


def with_usage(**overrides: Any) -> dict[str, Any]:
    """OK_BODY whose usage has fields replaced; `...` removes one."""
    return ok_body(usage=_without_removed({**OK_USAGE, **overrides}))


def text_block(text: Any) -> dict[str, Any]:
    return {"type": "text", "text": text}


def thinking_block(thinking: str = THINKING_SENTINEL) -> dict[str, Any]:
    return {"type": "thinking", "thinking": thinking, "signature": "sig"}


# JSON whose text holds a lone surrogate escape, which cannot be sent back as UTF-8.
SURROGATE_TEXT = json.dumps(ok_body(content=[text_block("a" + chr(0xD800))])).encode("ascii")
SURROGATE_MODEL = json.dumps(ok_body(model="m" + chr(0xD800))).encode("ascii")


def raw_with_count(literal: str) -> bytes:
    """A valid reply whose output_tokens is the given JSON literal (Python accepts NaN)."""
    template = json.dumps(with_usage(output_tokens=0))
    return template.replace('"output_tokens": 0', '"output_tokens": ' + literal).encode()


def json_handler(body: Any, status: int = 200) -> Handler:
    return lambda request: httpx.Response(status, json=body)


def chat_request(**overrides: Any) -> ChatRequest:
    fields: dict[str, Any] = {
        "model": "claude-alias",
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


def make_provider(
    client: httpx.AsyncClient, *, max_response_bytes: int | None = None
) -> AnthropicProvider:
    clock = FakeClock(CLOCK_SECONDS)
    ids = FixedIdSource(FIXED_ID)
    if max_response_bytes is None:
        return AnthropicProvider(client, SecretStr(KEY), DEFAULT_MAX_TOKENS, clock, ids)
    return AnthropicProvider(
        client,
        SecretStr(KEY),
        DEFAULT_MAX_TOKENS,
        clock,
        ids,
        max_response_bytes=max_response_bytes,
    )


def run(
    handler: Handler,
    request: ChatRequest | None = None,
    *,
    base_url: str = "https://anthropic.test",
    max_response_bytes: int | None = None,
) -> tuple[ChatResponse | ProviderError, Calls]:
    """Run one call; return the response or the ProviderError, and the recorded requests."""
    calls = Calls(handler)
    client = httpx.AsyncClient(transport=httpx.MockTransport(calls), base_url=base_url)
    provider = make_provider(client, max_response_bytes=max_response_bytes)

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


def reply_for(body: dict[str, Any]) -> tuple[str, str]:
    choice = response_for(json_handler(body)).choices[0]
    return choice.message.content, choice.finish_reason


def sent(request: ChatRequest, **kwargs: Any) -> httpx.Request:
    _, calls = run(json_handler(OK_BODY), request, **kwargs)
    assert len(calls.requests) == 1
    return calls.requests[0]


def sent_body(request: ChatRequest) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(sent(request).content)
    return body


# Criterion 1: request translation.


def test_request_is_a_post_to_v1_messages_with_exactly_the_translated_body() -> None:
    request = sent(chat_request())
    assert request.method == "POST"
    assert request.url.path == "/v1/messages"
    assert request.headers.get_list("content-type") == ["application/json"]
    assert json.loads(request.content) == {
        "model": "claude-alias",
        "messages": [{"role": "user", "content": "hello"}],
        "max_tokens": DEFAULT_MAX_TOKENS,
    }


def test_system_messages_are_joined_with_newline_in_order_into_system() -> None:
    messages = [
        ChatMessage(role="system", content="first rule"),
        ChatMessage(role="user", content="hi"),
        ChatMessage(role="system", content="second rule"),
        ChatMessage(role="assistant", content="hello"),
        ChatMessage(role="system", content="third rule"),
        ChatMessage(role="user", content="and you?"),
    ]
    assert sent_body(chat_request(messages=messages)) == {
        "model": "claude-alias",
        "system": "first rule\nsecond rule\nthird rule",
        "messages": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "and you?"},
        ],
        "max_tokens": DEFAULT_MAX_TOKENS,
    }


def test_one_system_message_is_sent_as_it_is() -> None:
    messages = [
        ChatMessage(role="system", content="be brief"),
        ChatMessage(role="user", content="hi"),
    ]
    body = sent_body(chat_request(messages=messages))
    assert body["system"] == "be brief"
    assert body["messages"] == [{"role": "user", "content": "hi"}]


def test_system_is_absent_when_there_are_no_system_messages() -> None:
    messages = [
        ChatMessage(role="user", content="hi"),
        ChatMessage(role="assistant", content="hello"),
        ChatMessage(role="user", content="bye"),
    ]
    body = sent_body(chat_request(messages=messages))
    assert "system" not in body
    assert body["messages"] == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "bye"},
    ]


def test_empty_system_messages_still_give_a_system_field() -> None:
    messages = [
        ChatMessage(role="system", content=""),
        ChatMessage(role="system", content=""),
        ChatMessage(role="user", content="hi"),
    ]
    assert sent_body(chat_request(messages=messages))["system"] == "\n"


def test_a_request_of_only_system_messages_is_sent_with_empty_messages() -> None:
    # Anthropic's answer to this is unknown; the adapter forwards it (owner decision, T-206).
    messages = [ChatMessage(role="system", content="only rules")]
    body = sent_body(chat_request(messages=messages))
    assert (body["system"], body["messages"]) == ("only rules", [])


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"max_tokens": 7}, 7),
        ({"max_completion_tokens": 9}, 9),
        ({"max_tokens": 7, "max_completion_tokens": 9}, 9),
        ({"max_tokens": 1}, 1),
        ({}, DEFAULT_MAX_TOKENS),
    ],
    ids=["max-tokens", "max-completion-tokens", "completion-wins", "one", "default"],
)
def test_max_tokens_comes_from_max_completion_tokens_else_max_tokens_else_the_default(
    fields: dict[str, int], expected: int
) -> None:
    body = sent_body(chat_request(**fields))
    assert body["max_tokens"] == expected
    assert "max_completion_tokens" not in body


@pytest.mark.parametrize("temperature", [0.0, 1.0, 2.0])
def test_temperature_is_never_sent(temperature: float) -> None:
    assert "temperature" not in sent_body(chat_request(temperature=temperature))


def test_name_user_n_and_stream_are_not_sent() -> None:
    messages = [
        ChatMessage(role="system", content="be brief", name="SENTINEL-name-sys"),
        ChatMessage(role="user", content="hi", name="SENTINEL-name-user"),
        ChatMessage(role="assistant", content="hello", name="SENTINEL-name-bot"),
    ]
    request = sent(chat_request(messages=messages, user="SENTINEL-user-1d0e", n=1, stream=False))
    body = json.loads(request.content)
    assert set(body) == {"model", "system", "messages", "max_tokens"}
    assert all(set(message) == {"role", "content"} for message in body["messages"])
    assert b"SENTINEL" not in request.content


def test_all_fields_together_give_the_exact_body() -> None:
    request = chat_request(
        messages=[
            ChatMessage(role="system", content="rules", name="r"),
            ChatMessage(role="user", content="hi", name="ann"),
        ],
        max_tokens=5,
        max_completion_tokens=6,
        temperature=0.5,
        user="u",
        n=1,
        stream=False,
    )
    assert sent_body(request) == {
        "model": "claude-alias",
        "system": "rules",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 6,
    }


def test_non_ascii_content_is_sent_as_utf_8() -> None:
    content = "café 你好 \U0001f600"
    messages = [
        ChatMessage(role="system", content=content),
        ChatMessage(role="user", content=content),
    ]
    body = sent_body(chat_request(messages=messages))
    assert (body["system"], body["messages"][0]["content"]) == (content, content)


def test_whitespace_in_system_and_message_content_is_sent_unchanged() -> None:
    messages = [
        ChatMessage(role="system", content="  first rule \n"),
        ChatMessage(role="system", content="\tsecond rule  "),
        ChatMessage(role="user", content="  padded \n"),
        ChatMessage(role="assistant", content=" "),
    ]
    body = sent_body(chat_request(messages=messages))
    assert body["system"] == "  first rule \n\n\tsecond rule  "
    assert body["messages"] == [
        {"role": "user", "content": "  padded \n"},
        {"role": "assistant", "content": " "},
    ]


def test_the_key_is_sent_only_in_the_x_api_key_header() -> None:
    request = sent(chat_request())
    assert request.headers.get_list("x-api-key") == [KEY]
    assert "authorization" not in request.headers
    others = [value for name, value in request.headers.items() if name != "x-api-key"]
    assert all(KEY not in value for value in others)
    assert KEY not in str(request.url)
    assert KEY.encode() not in request.content


def test_the_version_header_is_2026_10_21() -> None:
    assert sent(chat_request()).headers.get_list("anthropic-version") == ["2026-10-21"]


def test_the_key_and_the_version_are_never_default_headers_of_the_client() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(json_handler(OK_BODY)), base_url="https://anthropic.test"
    )
    provider = make_provider(client)

    async def go() -> None:
        await provider.complete(chat_request())
        await client.aclose()

    asyncio.run(go())
    assert "x-api-key" not in client.headers
    assert "anthropic-version" not in client.headers


def test_the_base_url_path_prefix_is_kept() -> None:
    url = sent(chat_request(), base_url="https://gw.test/prefix").url
    assert str(url) == "https://gw.test/prefix/v1/messages"


# Criterion 2: response translation.


def test_an_end_turn_response_is_translated_in_full() -> None:
    response = response_for(json_handler(OK_BODY))
    assert response.model_dump() == {
        "id": FIXED_ID,
        "object": "chat.completion",
        "created": 2000,  # the clock's 2000.99, truncated
        "model": "claude-sonnet-5-5",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "hi there"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 330, "completion_tokens": 12, "total_tokens": 342},
    }


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("end_turn", "stop"),
        ("stop_sequence", "stop"),
        ("max_tokens", "length"),
        ("model_context_window_exceeded", "length"),
        ("refusal", "content_filter"),
    ],
)
def test_each_stop_reason_maps(reason: str, expected: str) -> None:
    assert reply_for(ok_body(stop_reason=reason)) == ("hi there", expected)


@pytest.mark.parametrize(
    ("blocks", "expected"),
    [
        ([text_block("Hel"), text_block("lo")], "Hello"),
        ([text_block("a"), thinking_block(), text_block("b"), text_block("c")], "abc"),
        ([thinking_block(), text_block("only")], "only"),
        ([text_block(""), text_block("x"), text_block("")], "x"),
        ([text_block("line\n"), text_block("next")], "line\nnext"),
    ],
    ids=["two", "around-thinking", "after-thinking", "empty-blocks", "newline-kept"],
)
def test_text_blocks_are_joined_in_order_with_no_separator(
    blocks: list[dict[str, Any]], expected: str
) -> None:
    assert reply_for(ok_body(content=blocks)) == (expected, "stop")


@pytest.mark.parametrize(
    "block",
    [
        thinking_block(),
        {"type": "redacted_thinking", "data": THINKING_SENTINEL},
        {"type": "tool_use", "id": "t1", "name": "f", "input": {"q": THINKING_SENTINEL}},
        {"type": "server_tool_use", "id": "t2", "name": "web_search", "input": {}},
        {"type": "unknown_future_block", "text": THINKING_SENTINEL},
        {"text": THINKING_SENTINEL},
        {"type": None, "text": THINKING_SENTINEL},
        {**thinking_block(), "text": THINKING_SENTINEL},
        {"type": "Text", "text": THINKING_SENTINEL},
        {"type": "TEXT", "text": THINKING_SENTINEL},
        {"type": " text", "text": THINKING_SENTINEL},
        {},
    ],
    ids=[
        "thinking",
        "redacted-thinking",
        "tool-use",
        "server-tool-use",
        "unknown-type-with-text",
        "no-type-with-text",
        "type-null-with-text",
        "thinking-with-text",
        "type-capitalised",
        "type-upper",
        "type-leading-space",
        "empty-block",
    ],
)
def test_blocks_that_are_not_text_are_ignored(block: dict[str, Any]) -> None:
    content, reason = reply_for(ok_body(content=[text_block("kept"), block]))
    assert (content, reason) == ("kept", "stop")


@pytest.mark.parametrize("reason", ["end_turn", "max_tokens", "model_context_window_exceeded"])
@pytest.mark.parametrize("blocks", [[], [thinking_block()]], ids=["no-blocks", "thinking-only"])
def test_no_text_block_gives_an_empty_reply(blocks: list[dict[str, Any]], reason: str) -> None:
    content, _ = reply_for(ok_body(content=blocks, stop_reason=reason))
    assert content == ""


@pytest.mark.parametrize("blocks", [[], [thinking_block()]], ids=["no-blocks", "thinking-only"])
def test_a_refusal_with_no_text_block_is_an_empty_reply_with_content_filter(
    blocks: list[dict[str, Any]],
) -> None:
    assert reply_for(ok_body(content=blocks, stop_reason="refusal")) == ("", "content_filter")


def test_a_refusal_with_text_keeps_the_text_and_gives_content_filter() -> None:
    body = ok_body(content=[text_block("I can't help with that.")], stop_reason="refusal")
    assert reply_for(body) == ("I can't help with that.", "content_filter")


@pytest.mark.parametrize(
    ("overrides", "prompt", "completion"),
    [
        ({}, 330, 12),
        ({"cache_creation_input_tokens": 0}, 310, 12),
        ({"cache_read_input_tokens": 0}, 30, 12),
        ({"input_tokens": 0}, 320, 12),
        ({"output_tokens": 0}, 330, 0),
        ({"input_tokens": 4000, "cache_creation_input_tokens": 50_000}, 50_300 + 4000, 12),
    ],
    ids=["all", "no-creation", "no-read", "no-input", "no-output", "large"],
)
def test_prompt_tokens_are_input_plus_both_cache_fields(
    overrides: dict[str, Any], prompt: int, completion: int
) -> None:
    usage = response_for(json_handler(with_usage(**overrides))).usage
    assert (usage.prompt_tokens, usage.completion_tokens) == (prompt, completion)
    assert usage.total_tokens == prompt + completion


@pytest.mark.parametrize(
    ("overrides", "prompt"),
    [
        ({"cache_creation_input_tokens": ...}, 310),
        ({"cache_read_input_tokens": ...}, 30),
        ({"cache_creation_input_tokens": None}, 310),
        ({"cache_read_input_tokens": None}, 30),
        ({"cache_creation_input_tokens": ..., "cache_read_input_tokens": ...}, 10),
        ({"cache_creation_input_tokens": None, "cache_read_input_tokens": None}, 10),
        ({"cache_creation_input_tokens": None, "cache_read_input_tokens": ...}, 10),
    ],
    ids=[
        "creation-absent",
        "read-absent",
        "creation-null",
        "read-null",
        "both-absent",
        "both-null",
        "null-and-absent",
    ],
)
def test_an_absent_or_null_cache_field_counts_zero(overrides: dict[str, Any], prompt: int) -> None:
    usage = response_for(json_handler(with_usage(**overrides))).usage
    assert (usage.prompt_tokens, usage.completion_tokens, usage.total_tokens) == (
        prompt,
        12,
        prompt + 12,
    )


@pytest.mark.parametrize(
    ("overrides", "prompt", "completion"),
    [
        (
            {
                "input_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "output_tokens": 0,
            },
            0,
            0,
        ),
        ({"input_tokens": 1_000_000, "output_tokens": 2_000_000}, 1_000_320, 2_000_000),
    ],
    ids=["zero-counts", "large-counts"],
)
def test_the_total_is_prompt_plus_completion(
    overrides: dict[str, Any], prompt: int, completion: int
) -> None:
    usage = response_for(json_handler(with_usage(**overrides))).usage
    assert (usage.prompt_tokens, usage.completion_tokens) == (prompt, completion)
    assert usage.total_tokens == prompt + completion


@pytest.mark.parametrize(
    "upstream_id",
    [UPSTREAM_ID, ..., None, 5, ""],
    ids=["sentinel", "absent", "null", "int", "empty"],
)
def test_id_and_created_come_from_the_injected_sources_not_the_body(upstream_id: Any) -> None:
    response = response_for(json_handler(ok_body(id=upstream_id, created=1767225600)))
    assert (response.id, response.created) == (FIXED_ID, 2000)


class CountingIdSource:
    def __init__(self) -> None:
        self.calls = 0

    def next_id(self) -> str:
        self.calls += 1
        return f"chatcmpl-{self.calls}"


def test_each_call_takes_a_new_id_and_the_current_time() -> None:
    clock = FakeClock(1000.0)
    ids = CountingIdSource()
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(json_handler(OK_BODY)), base_url="https://anthropic.test"
    )
    provider = AnthropicProvider(client, SecretStr(KEY), DEFAULT_MAX_TOKENS, clock, ids)

    async def go() -> list[ChatResponse]:
        first = await provider.complete(chat_request())
        clock.advance(5.5)
        second = await provider.complete(chat_request())
        await client.aclose()
        return [first, second]

    responses = asyncio.run(go())
    assert [(r.id, r.created) for r in responses] == [("chatcmpl-1", 1000), ("chatcmpl-2", 1005)]


def test_an_empty_text_reply_is_valid() -> None:
    assert reply_for(ok_body(content=[text_block("")])) == ("", "stop")


@pytest.mark.parametrize("role", [..., "user", ""], ids=["absent", "user", "empty"])
def test_the_output_role_is_assistant_whatever_role_the_reply_names(role: Any) -> None:
    response = response_for(json_handler(ok_body(role=role, type=...)))
    assert response.choices[0].message.role == "assistant"


@pytest.mark.parametrize("status", [200, 201, 299])
def test_any_2xx_with_a_valid_body_succeeds(status: int) -> None:
    assert response_for(json_handler(OK_BODY, status)).usage.total_tokens == 342


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
    ("no-model", json_handler(ok_body(model=...))),
    ("model-null", json_handler(ok_body(model=None))),
    ("model-empty", json_handler(ok_body(model=""))),
    ("model-int", json_handler(ok_body(model=5))),
    ("model-lone-surrogate", lambda request: httpx.Response(200, content=SURROGATE_MODEL)),
    ("no-stop-reason", json_handler(ok_body(stop_reason=...))),
    ("stop-reason-null", json_handler(ok_body(stop_reason=None))),
    ("stop-reason-tool-use", json_handler(ok_body(stop_reason="tool_use"))),
    ("stop-reason-pause-turn", json_handler(ok_body(stop_reason="pause_turn"))),
    ("stop-reason-unknown", json_handler(ok_body(stop_reason="future_reason"))),
    ("stop-reason-upper", json_handler(ok_body(stop_reason="END_TURN"))),
    ("stop-reason-empty", json_handler(ok_body(stop_reason=""))),
    ("stop-reason-int", json_handler(ok_body(stop_reason=1))),
    ("stop-reason-list", json_handler(ok_body(stop_reason=["end_turn"]))),
    ("stop-reason-openai-stop", json_handler(ok_body(stop_reason="stop"))),
    ("stop-reason-openai-length", json_handler(ok_body(stop_reason="length"))),
    ("stop-reason-openai-content-filter", json_handler(ok_body(stop_reason="content_filter"))),
    (
        "stop-reason-tool-use-no-text",
        json_handler(ok_body(stop_reason="tool_use", content=[thinking_block()])),
    ),
    ("no-content", json_handler(ok_body(content=...))),
    ("content-null", json_handler(ok_body(content=None))),
    ("content-dict", json_handler(ok_body(content=text_block("x")))),
    ("content-string", json_handler(ok_body(content="hi there"))),
    ("block-string", json_handler(ok_body(content=["hi there"]))),
    ("block-null", json_handler(ok_body(content=[text_block("a"), None]))),
    ("block-list", json_handler(ok_body(content=[[text_block("a")]]))),
    ("text-absent", json_handler(ok_body(content=[{"type": "text"}]))),
    ("text-null", json_handler(ok_body(content=[text_block(None)]))),
    ("text-int", json_handler(ok_body(content=[text_block(5)]))),
    ("text-list", json_handler(ok_body(content=[text_block(["a"])]))),
    ("text-after-good-block-int", json_handler(ok_body(content=[text_block("a"), text_block(1)]))),
    ("text-lone-surrogate", lambda request: httpx.Response(200, content=SURROGATE_TEXT)),
    ("no-usage", json_handler(ok_body(usage=...))),
    ("usage-null", json_handler(ok_body(usage=None))),
    ("usage-list", json_handler(ok_body(usage=[10, 12]))),
    ("no-input-tokens", json_handler(with_usage(input_tokens=...))),
    ("input-tokens-negative", json_handler(with_usage(input_tokens=-1))),
    ("input-tokens-bool", json_handler(with_usage(input_tokens=True))),
    ("input-tokens-float", json_handler(with_usage(input_tokens=1.5))),
    ("input-tokens-whole-float", json_handler(with_usage(input_tokens=5.0))),
    ("input-tokens-string", json_handler(with_usage(input_tokens="7"))),
    ("input-tokens-null", json_handler(with_usage(input_tokens=None))),
    ("no-output-tokens", json_handler(with_usage(output_tokens=...))),
    ("output-tokens-negative", json_handler(with_usage(output_tokens=-1))),
    ("output-tokens-bool", json_handler(with_usage(output_tokens=False))),
    ("output-tokens-float", json_handler(with_usage(output_tokens=1.5))),
    ("output-tokens-string", json_handler(with_usage(output_tokens="12"))),
    ("output-tokens-null", json_handler(with_usage(output_tokens=None))),
    ("creation-negative", json_handler(with_usage(cache_creation_input_tokens=-1))),
    ("creation-bool", json_handler(with_usage(cache_creation_input_tokens=True))),
    ("creation-false", json_handler(with_usage(cache_creation_input_tokens=False))),
    ("creation-float", json_handler(with_usage(cache_creation_input_tokens=1.5))),
    ("creation-whole-float", json_handler(with_usage(cache_creation_input_tokens=20.0))),
    ("creation-string", json_handler(with_usage(cache_creation_input_tokens="20"))),
    ("creation-zero-string", json_handler(with_usage(cache_creation_input_tokens="0"))),
    ("read-negative", json_handler(with_usage(cache_read_input_tokens=-1))),
    ("read-bool", json_handler(with_usage(cache_read_input_tokens=True))),
    ("read-false", json_handler(with_usage(cache_read_input_tokens=False))),
    ("read-float", json_handler(with_usage(cache_read_input_tokens=1.5))),
    ("read-whole-float", json_handler(with_usage(cache_read_input_tokens=300.0))),
    ("read-string", json_handler(with_usage(cache_read_input_tokens="300"))),
    ("read-empty-string", json_handler(with_usage(cache_read_input_tokens=""))),
    ("read-empty-list", json_handler(with_usage(cache_read_input_tokens=[]))),
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


@pytest.mark.parametrize(
    "body",
    [b"nope", json.dumps({}).encode(), json.dumps(ok_body(stop_reason="tool_use")).encode()],
    ids=["invalid-json", "empty-object", "untranslatable"],
)
@pytest.mark.parametrize("status", [201, 202])
def test_a_bad_response_carries_the_status_it_arrived_with(body: bytes, status: int) -> None:
    error = error_for(lambda request: httpx.Response(status, content=body))
    assert (error.kind, error.status_code) == ("bad_response", status)


ERROR_BODY: dict[str, Any] = {"type": "error", "error": {"type": "api_error", "message": "x"}}


def test_a_429_is_a_retryable_rate_limited_error() -> None:
    error = error_for(json_handler(ERROR_BODY, 429))
    assert (error.kind, error.status_code, error.retryable) == ("rate_limited", 429, True)


@pytest.mark.parametrize("status", [500, 502, 503, 504, 529, 599])
def test_a_5xx_including_529_is_a_retryable_upstream_status(status: int) -> None:
    error = error_for(json_handler(ERROR_BODY, status))
    assert (error.kind, error.status_code, error.retryable) == ("upstream_status", status, True)


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 408, 409, 413, 422, 499])
def test_a_client_error_status_is_not_retryable(status: int) -> None:
    error = error_for(json_handler(ERROR_BODY, status))
    assert (error.kind, error.status_code, error.retryable) == ("upstream_status", status, False)


def test_a_redirect_is_not_followed_and_not_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://elsewhere.test/v1/x"})

    result, calls = run(handler)
    assert isinstance(result, ProviderError)
    assert (result.kind, result.status_code, result.retryable) == ("upstream_status", 302, False)
    assert len(calls.requests) == 1


@pytest.mark.parametrize("status", [529, 429, 401])
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


def test_one_attempt_is_made_on_a_529_on_a_429_and_on_a_timeout() -> None:
    for handler in (
        json_handler(ERROR_BODY, 529),
        json_handler(ERROR_BODY, 429),
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
    raise httpx.LocalProtocolError(f"Illegal header value {request.headers['x-api-key']!r}")


def echo_key_in_timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout(f"timed out sending {request.headers['x-api-key']}")


ECHOED = f"invalid x-api-key: {KEY}. {BODY_SENTINEL}"


def echo_error(status: int) -> Handler:
    body = {"type": "error", "error": {"type": "authentication_error", "message": ECHOED}}
    return json_handler(body, status)


@pytest.mark.parametrize(
    "handler",
    [
        echo_error(401),
        echo_error(403),
        echo_error(429),
        echo_error(500),
        echo_error(529),
        lambda request: httpx.Response(200, content=f"{{{ECHOED}".encode()),
        json_handler(ok_body(stop_reason=ECHOED)),
        json_handler(with_usage(input_tokens=ECHOED)),
        json_handler(with_usage(cache_read_input_tokens=ECHOED)),
        json_handler(ok_body(content=[text_block(ECHOED), text_block(5)])),
        json_handler(ok_body(model=..., echo=ECHOED)),
        echo_key_in_header_error,
        echo_key_in_timeout,
        raises(httpx.ConnectError(ECHOED)),
    ],
    ids=[
        "401",
        "403",
        "429",
        "500",
        "529",
        "invalid-json",
        "stop-reason",
        "count",
        "cache-count",
        "text-block",
        "missing-model",
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
    assert "anthropic.test" not in text
    assert error.__cause__ is None
    # Not even a suppressed context: an error reporter may read `__context__` directly.
    assert error.__context__ is None
    assert str(error) in (
        f"provider failed: {error.kind}",
        f"provider failed: {error.kind} (HTTP {error.status_code})",
    )


def test_the_provider_repr_never_shows_the_key() -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(json_handler(OK_BODY)))
    provider = make_provider(client)
    for text in (repr(provider), str(provider), repr(vars(provider))):
        assert KEY not in text
    asyncio.run(client.aclose())


def test_the_adapter_imports_neither_the_mock_nor_another_adapter() -> None:
    source = (Path(__file__).parent.parent / "app" / "providers" / "anthropic.py").read_text(
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
    assert "app.providers.openai" not in imported
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
    data = padded(CAP_BYTES + 1, ok_body(content=[text_block(f"{KEY} {BODY_SENTINEL}")]))
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
    [(529, "upstream_status", True), (429, "rate_limited", True), (401, "upstream_status", False)],
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
