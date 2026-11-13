"""The Ollama adapter (ADR-0010, T-204): request and response translation and the failure kinds.

Every test runs the provider on an `httpx.MockTransport`: no network, no sleeping.
"""

import ast
import asyncio
import json
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.api.models import ChatMessage, ChatRequest, ChatResponse
from app.providers.errors import ProviderError
from app.providers.ollama import OllamaProvider
from tests.fakes import FakeClock, FixedIdSource

Handler = Callable[[httpx.Request], httpx.Response]
BODY_SENTINEL = "SENTINEL-body-4c1f"
PASSWORD_SENTINEL = "SENTINEL-password-8e2a"
FIXED_ID = "chatcmpl-fixed"
OK_BODY: dict[str, Any] = {
    "model": "llama3.2:latest",
    "created_at": "2026-01-01T00:00:00Z",
    "message": {"role": "assistant", "content": "hi there"},
    "done": True,
    "done_reason": "stop",
    "prompt_eval_count": 7,
    "eval_count": 5,
}


# A JSON document whose reply holds a lone surrogate escape, which cannot be sent back as UTF-8.
OK_SURROGATE_CONTENT = (
    b'{"model": "m", "message": {"role": "assistant", "content": "a\\ud800"},'
    b' "done_reason": "stop"}'
)


def ok_body(**overrides: Any) -> dict[str, Any]:
    """OK_BODY with fields replaced; a value of `...` removes the field."""
    body = {**OK_BODY, **overrides}
    return {key: value for key, value in body.items() if value is not ...}


def json_handler(body: Any, status: int = 200) -> Handler:
    return lambda request: httpx.Response(status, json=body)


def chat_request(**overrides: Any) -> ChatRequest:
    fields: dict[str, Any] = {
        "model": "llama3.2",
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
    base_url: str = "http://ollama.test",
    clock_seconds: float = 1000.9,
) -> tuple[ChatResponse | ProviderError, Calls]:
    """Run one call; return the response or the ProviderError, and the recorded requests."""
    calls = Calls(handler)
    client = httpx.AsyncClient(transport=httpx.MockTransport(calls), base_url=base_url)
    provider = OllamaProvider(client, FakeClock(clock_seconds), FixedIdSource(FIXED_ID))

    async def go() -> ChatResponse | ProviderError:
        try:
            return await provider.complete(request or chat_request())
        except ProviderError as error:
            return error
        finally:
            await client.aclose()

    return asyncio.run(go()), calls


def response_for(
    handler: Handler, request: ChatRequest | None = None, **kwargs: Any
) -> ChatResponse:
    result, _ = run(handler, request, **kwargs)
    assert isinstance(result, ChatResponse), result
    return result


def error_for(handler: Handler, request: ChatRequest | None = None, **kwargs: Any) -> ProviderError:
    result, _ = run(handler, request, **kwargs)
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


def test_request_is_a_post_to_api_chat_with_exactly_the_translated_body() -> None:
    request = sent(chat_request())
    assert request.method == "POST"
    assert request.url.path == "/api/chat"
    assert json.loads(request.content) == {
        "model": "llama3.2",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": False,
    }


@pytest.mark.parametrize("stream", [None, False])
def test_stream_false_is_always_sent(stream: bool | None) -> None:
    assert sent_body(chat_request(stream=stream))["stream"] is False


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
def test_num_predict_comes_from_max_completion_tokens_else_max_tokens(
    fields: dict[str, int], expected: int
) -> None:
    assert sent_body(chat_request(**fields))["options"] == {"num_predict": expected}


def test_options_are_left_out_when_nothing_is_given() -> None:
    assert "options" not in sent_body(chat_request())


@pytest.mark.parametrize("temperature", [0.0, 1.2, 2.0])
def test_temperature_is_sent_when_given_including_zero(temperature: float) -> None:
    assert sent_body(chat_request(temperature=temperature))["options"] == {
        "temperature": temperature
    }


def test_both_options_are_sent_together() -> None:
    body = sent_body(chat_request(max_tokens=5, temperature=0.5))
    assert body["options"] == {"num_predict": 5, "temperature": 0.5}


def test_messages_carry_only_role_and_content_in_order_and_never_a_name() -> None:
    messages = [
        ChatMessage(role="system", content="be brief", name="rules"),
        ChatMessage(role="user", content="hi", name="ann"),
        ChatMessage(role="assistant", content="hello"),
        ChatMessage(role="user", content="and you?"),
    ]
    body = sent_body(chat_request(messages=messages))
    assert body["messages"] == [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "and you?"},
    ]


def test_user_and_n_are_not_sent() -> None:
    body = sent_body(chat_request(user="SENTINEL-user", n=1))
    assert set(body) == {"model", "messages", "stream"}


def test_non_ascii_content_is_sent_as_utf_8() -> None:
    content = "café 你好 \U0001f600"
    messages = [ChatMessage(role="user", content=content)]
    assert sent_body(chat_request(messages=messages))["messages"][0]["content"] == content


def test_the_base_url_path_prefix_is_kept_and_the_default_host_is_ollamas() -> None:
    assert sent(chat_request(), base_url="http://h:1/prefix").url.path == "/prefix/api/chat"
    assert str(sent(chat_request(), base_url="http://localhost:11434").url) == (
        "http://localhost:11434/api/chat"
    )


# Criterion 2: response translation.


def test_a_stop_response_is_translated_in_full() -> None:
    response = response_for(json_handler(OK_BODY))
    assert response.model_dump() == {
        "id": FIXED_ID,
        "object": "chat.completion",
        "created": 1000,
        "model": "llama3.2:latest",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "hi there"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 7, "completion_tokens": 5, "total_tokens": 12},
    }


def test_a_length_response_maps_to_length() -> None:
    response = response_for(json_handler(ok_body(done_reason="length")))
    assert response.choices[0].finish_reason == "length"


def test_id_and_created_come_from_the_injected_sources_not_from_the_body() -> None:
    body = ok_body(id="SENTINEL-upstream-id", created=5, created_at="1999-01-01T00:00:00Z")
    response = response_for(json_handler(body), clock_seconds=2000.99)
    assert (response.id, response.created) == (FIXED_ID, 2000)


@pytest.mark.parametrize(
    ("overrides", "prompt", "completion"),
    [
        ({"prompt_eval_count": ...}, 0, 5),
        ({"eval_count": ...}, 7, 0),
        ({"prompt_eval_count": ..., "eval_count": ...}, 0, 0),
        ({"prompt_eval_count": 0, "eval_count": 0}, 0, 0),
        ({"prompt_eval_count": 1_000_000, "eval_count": 2_000_000}, 1_000_000, 2_000_000),
    ],
    ids=["no-prompt-count", "no-eval-count", "no-counts", "zero-counts", "large-counts"],
)
def test_an_absent_count_is_zero_and_the_total_is_the_sum(
    overrides: dict[str, Any], prompt: int, completion: int
) -> None:
    usage = response_for(json_handler(ok_body(**overrides))).usage
    assert (usage.prompt_tokens, usage.completion_tokens) == (prompt, completion)
    assert usage.total_tokens == prompt + completion


def test_an_empty_reply_is_valid() -> None:
    body = ok_body(message={"role": "assistant", "content": ""})
    assert response_for(json_handler(body)).choices[0].message.content == ""


def test_a_missing_role_is_not_checked_and_the_output_role_is_assistant() -> None:
    body = ok_body(message={"content": "x"})
    assert response_for(json_handler(body)).choices[0].message.role == "assistant"


# Criterion 3: errors.

BAD_RESPONSES: list[tuple[str, Handler]] = [
    ("invalid-json", lambda request: httpx.Response(200, content=b"{not json")),
    ("empty-body", lambda request: httpx.Response(200, content=b"")),
    ("no-content-204", lambda request: httpx.Response(204)),
    ("invalid-utf-8", lambda request: httpx.Response(200, content=b'{"a": "\xff"}')),
    (
        "utf-16-body",
        lambda request: httpx.Response(200, content=json.dumps(OK_BODY).encode("utf-16")),
    ),
    ("deeply-nested", lambda request: httpx.Response(200, content=b"[" * 100_000)),
    ("top-level-list", json_handler([OK_BODY])),
    ("top-level-string", json_handler("text")),
    ("top-level-number", json_handler(5)),
    ("top-level-null", json_handler(None)),
    ("no-message", json_handler(ok_body(message=...))),
    ("message-null", json_handler(ok_body(message=None))),
    ("message-list", json_handler(ok_body(message=["x"]))),
    ("message-string", json_handler(ok_body(message="x"))),
    ("no-content", json_handler(ok_body(message={"role": "assistant"}))),
    ("content-null", json_handler(ok_body(message={"content": None}))),
    ("content-int", json_handler(ok_body(message={"content": 5}))),
    ("content-list", json_handler(ok_body(message={"content": ["x"]}))),
    ("content-dict", json_handler(ok_body(message={"content": {"a": 1}}))),
    ("content-lone-surrogate", lambda r: httpx.Response(200, content=OK_SURROGATE_CONTENT)),
    ("no-done-reason", json_handler(ok_body(done_reason=...))),
    ("done-reason-null", json_handler(ok_body(done_reason=None))),
    ("done-reason-empty", json_handler(ok_body(done_reason=""))),
    ("done-reason-upper", json_handler(ok_body(done_reason="STOP"))),
    ("done-reason-padded", json_handler(ok_body(done_reason="stop "))),
    ("done-reason-load", json_handler(ok_body(done_reason="load"))),
    ("done-reason-unload", json_handler(ok_body(done_reason="unload"))),
    ("done-reason-content-filter", json_handler(ok_body(done_reason="content_filter"))),
    ("done-reason-tool-calls", json_handler(ok_body(done_reason="tool_calls"))),
    ("done-reason-int", json_handler(ok_body(done_reason=1))),
    ("done-reason-list", json_handler(ok_body(done_reason=["stop"]))),
    ("done-reason-dict", json_handler(ok_body(done_reason={"a": 1}))),
    ("prompt-count-negative", json_handler(ok_body(prompt_eval_count=-1))),
    ("prompt-count-bool", json_handler(ok_body(prompt_eval_count=True))),
    ("prompt-count-float", json_handler(ok_body(prompt_eval_count=1.5))),
    ("prompt-count-whole-float", json_handler(ok_body(prompt_eval_count=5.0))),
    ("prompt-count-string", json_handler(ok_body(prompt_eval_count="7"))),
    ("prompt-count-null", json_handler(ok_body(prompt_eval_count=None))),
    ("prompt-count-list", json_handler(ok_body(prompt_eval_count=[7]))),
    ("eval-count-negative", json_handler(ok_body(eval_count=-1))),
    ("eval-count-bool", json_handler(ok_body(eval_count=False))),
    ("eval-count-float", json_handler(ok_body(eval_count=1.5))),
    ("eval-count-string", json_handler(ok_body(eval_count="5"))),
    ("eval-count-null", json_handler(ok_body(eval_count=None))),
    ("no-model", json_handler(ok_body(model=...))),
    ("model-null", json_handler(ok_body(model=None))),
    ("model-int", json_handler(ok_body(model=5))),
    ("model-empty", json_handler(ok_body(model=""))),
    (
        "corrupt-gzip",
        lambda request: httpx.Response(
            200, headers={"content-encoding": "gzip"}, stream=httpx.ByteStream(b"not gzip")
        ),
    ),
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


def test_a_bad_response_carries_the_status_it_arrived_with() -> None:
    assert error_for(lambda request: httpx.Response(201, content=b"nope")).status_code == 201
    assert error_for(lambda request: httpx.Response(204)).status_code == 204


@pytest.mark.parametrize("status", [200, 201, 299])
def test_any_2xx_with_a_valid_body_succeeds(status: int) -> None:
    assert response_for(json_handler(OK_BODY, status)).usage.total_tokens == 12


@pytest.mark.parametrize("status", [300, 301, 399])
def test_a_redirect_is_a_non_retryable_upstream_status(status: int) -> None:
    error = error_for(json_handler(OK_BODY, status))
    assert (error.kind, error.status_code, error.retryable) == ("upstream_status", status, False)


def test_a_404_for_a_missing_model_is_a_non_retryable_upstream_status() -> None:
    body = {"error": "model 'x' not found"}
    error = error_for(json_handler(body, 404))
    assert (error.kind, error.status_code, error.retryable) == ("upstream_status", 404, False)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 408, 418, 422, 499])
def test_a_client_error_status_is_not_retryable(status: int) -> None:
    error = error_for(json_handler({"error": "x"}, status))
    assert (error.kind, error.status_code, error.retryable) == ("upstream_status", status, False)


@pytest.mark.parametrize("status", [500, 502, 503, 504, 529, 599])
def test_a_5xx_status_is_a_retryable_upstream_status(status: int) -> None:
    error = error_for(json_handler({"error": "x"}, status))
    assert (error.kind, error.status_code, error.retryable) == ("upstream_status", status, True)


def test_a_429_is_a_retryable_rate_limited_error() -> None:
    error = error_for(json_handler({"error": "x"}, 429))
    assert (error.kind, error.status_code, error.retryable) == ("rate_limited", 429, True)


def test_the_body_of_an_error_status_is_never_read() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # Reading this body would raise a DecodingError, which is a bad response on a 2xx.
        return httpx.Response(
            503, headers={"content-encoding": "gzip"}, stream=httpx.ByteStream(b"not gzip")
        )

    error = error_for(handler)
    assert (error.kind, error.status_code) == ("upstream_status", 503)


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
        httpx.WriteError("w"),
        httpx.RemoteProtocolError("p"),
        httpx.UnsupportedProtocol("u"),
    ],
    ids=["connect", "read", "write", "protocol", "unsupported"],
)
def test_other_transport_errors_are_retryable_connection_errors(exception: Exception) -> None:
    error = error_for(raises(exception))
    assert (error.kind, error.status_code, error.retryable) == ("connection", None, True)
    assert str(error) == "provider failed: connection"


def test_one_attempt_is_made_on_a_server_error_and_on_a_timeout() -> None:
    _, calls = run(json_handler({"error": "x"}, 500))
    assert len(calls.requests) == 1
    _, calls = run(raises(httpx.ReadTimeout("r")))
    assert len(calls.requests) == 1


def test_an_error_that_is_not_an_httpx_error_propagates_unchanged() -> None:
    boom = RuntimeError("boom")
    with pytest.raises(RuntimeError) as raised:
        run(raises(boom))
    assert raised.value is boom


@pytest.mark.parametrize(
    "handler",
    [
        json_handler({"error": BODY_SENTINEL, "echo": "hello"}, 503),
        json_handler({"error": BODY_SENTINEL}, 404),
        json_handler({"error": BODY_SENTINEL}, 429),
        lambda request: httpx.Response(200, content=f"{{{BODY_SENTINEL}".encode()),
        json_handler(ok_body(done_reason=BODY_SENTINEL)),
        json_handler(ok_body(prompt_eval_count=BODY_SENTINEL)),
        raises(httpx.ReadTimeout(BODY_SENTINEL)),
        raises(httpx.ConnectError(BODY_SENTINEL)),
    ],
    ids=["503", "404", "429", "invalid-json", "done-reason", "count", "timeout", "connect"],
)
def test_no_error_shows_the_response_body_or_the_url(handler: Handler) -> None:
    base_url = f"http://user:{PASSWORD_SENTINEL}@ollama.test:11434"
    error = error_for(handler, base_url=base_url)
    text = str(error) + repr(error) + "".join(traceback.format_exception(error))
    for sentinel in (BODY_SENTINEL, PASSWORD_SENTINEL, "ollama.test"):
        assert sentinel not in text
    assert error.__cause__ is None
    assert str(error) in (
        f"provider failed: {error.kind}",
        f"provider failed: {error.kind} (HTTP {error.status_code})",
    )


def test_the_adapter_does_not_import_the_mock() -> None:
    source = Path("app/providers/ollama.py").read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert "app.providers.mock" not in imported
    assert "app.providers.ids" in imported
