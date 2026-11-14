"""Anthropic through the whole app (T-206): serving, fallback, the balance, the key and the client.

The app is built on a route file in tmp_path and an `httpx.MockTransport`: no network, no sleeping.
"""

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import create_app
from tests.fakes import AUTH_HEADERS, TEST_API_KEY, FakeClock, make_settings
from tests.test_app_ollama import (
    BAD_GATEWAY_BODY,
    CAPACITY,
    LIMIT_SETTINGS,
    MOCK_TOTAL,
    RESERVED,
    URL,
    CountingTransport,
    Upstream,
    post,
    remaining,
)

KEY = "ant-SENTINEL-app-key-4e8f"
SECOND_KEY = "ant-SENTINEL-second-key-2a6b"
BODY_SENTINEL = "SENTINEL-anthropic-body-5c17"
ANTHROPIC_BODY: dict[str, Any] = {
    "id": "msg_upstream_app",
    "type": "message",
    "role": "assistant",
    "model": "claude-sonnet-5-5",
    "content": [{"type": "text", "text": "hi from anthropic"}],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {
        "input_tokens": 9,
        "cache_creation_input_tokens": 4,
        "cache_read_input_tokens": 30,
        "output_tokens": 12,
    },
}
ANTHROPIC_PROMPT = 43  # 9 input + 4 cache creation + 30 cache read
ANTHROPIC_TOTAL = 55
CLAUDE: dict[str, Any] = {
    "type": "anthropic",
    "base_url": "https://anthropic.test",
    "api_key_env": "ANTHROPIC_TEST_KEY",
    "default_max_tokens": 77,
    "timeout_seconds": 12,
}


def claude_table(claude: dict[str, Any] = CLAUDE) -> dict[str, Any]:
    return {
        "providers": {"claude": claude, "backup": {"type": "mock"}},
        "routes": {
            "solo": [{"provider": "claude", "model": "claude-sonnet"}],
            "fallback": [{"provider": "claude", "model": "claude-sonnet"}, {"provider": "backup"}],
        },
    }


def make_app(
    tmp_path: Path,
    handler: Callable[[httpx.Request], httpx.Response] | httpx.AsyncBaseTransport,
    table: dict[str, Any] | None = None,
) -> FastAPI:
    path = tmp_path / "routes.json"
    path.write_text(json.dumps(table or claude_table()), encoding="utf-8")
    settings = make_settings(
        **LIMIT_SETTINGS,
        TOLLGATE_ROUTES_FILE=str(path),
        ANTHROPIC_TEST_KEY=KEY,
        ANTHROPIC_SECOND_KEY=SECOND_KEY,
    )
    transport = (
        handler if isinstance(handler, httpx.AsyncBaseTransport) else httpx.MockTransport(handler)
    )
    return create_app(settings, FakeClock(1000.0), http_transport=transport)


def answering(status: int = 200, body: Any = None) -> Upstream:
    return Upstream(
        lambda request: httpx.Response(status, json=ANTHROPIC_BODY if body is None else body)
    )


def test_anthropic_serves_a_200_with_a_gateway_id_and_created_and_the_reported_model(
    tmp_path: Path,
) -> None:
    upstream = answering()
    with TestClient(make_app(tmp_path, upstream)) as client:
        response = post(client, "solo")
    assert response.status_code == 200
    body = response.json()
    assert body["choices"][0]["message"]["content"] == "hi from anthropic"
    assert body["choices"][0]["finish_reason"] == "stop"
    assert re.fullmatch(r"chatcmpl-[0-9a-f]{32}", body["id"])
    assert (body["created"], body["model"]) == (1000, "claude-sonnet-5-5")
    assert body["usage"] == {
        "prompt_tokens": ANTHROPIC_PROMPT,
        "completion_tokens": 12,
        "total_tokens": ANTHROPIC_TOTAL,
    }
    assert response.headers["x-tollgate-provider"] == "claude"
    assert response.headers["x-tollgate-fallbacks"] == "0"
    (request,) = upstream.requests
    assert str(request.url) == "https://anthropic.test/v1/messages"
    assert json.loads(request.content) == {
        "model": "claude-sonnet",
        "messages": [{"role": "user", "content": "hello there world"}],
        "max_tokens": 77,
    }
    # The provider's key, never the gateway client's own key.
    assert request.headers.get_list("x-api-key") == [KEY]
    assert request.headers.get_list("anthropic-version") == ["2026-10-21"]
    assert "authorization" not in request.headers
    assert TEST_API_KEY not in str(request.headers) + request.content.decode()


@pytest.mark.parametrize(
    ("fields", "expected"),
    [({}, 77), ({"max_tokens": 5}, 5), ({"max_completion_tokens": 6, "max_tokens": 5}, 6)],
    ids=["default", "max-tokens", "max-completion-tokens"],
)
def test_anthropic_max_tokens_comes_from_the_configured_default_unless_the_client_gives_one(
    tmp_path: Path, fields: dict[str, int], expected: int
) -> None:
    upstream = answering()
    payload = {"model": "solo", "messages": [{"role": "user", "content": "hi"}], **fields}
    with TestClient(make_app(tmp_path, upstream)) as client:
        assert client.post(URL, json=payload, headers=AUTH_HEADERS).status_code == 200
    (request,) = upstream.requests
    assert json.loads(request.content)["max_tokens"] == expected


def test_each_anthropic_provider_sends_its_own_key_and_default(tmp_path: Path) -> None:
    second = {
        **CLAUDE,
        "base_url": "https://second.test",
        "api_key_env": "ANTHROPIC_SECOND_KEY",
        "default_max_tokens": 88,
    }
    table = {
        "providers": {"claude": CLAUDE, "second": second},
        "routes": {"one": [{"provider": "claude"}], "two": [{"provider": "second"}]},
    }
    upstream = answering()
    with TestClient(make_app(tmp_path, upstream, table)) as client:
        for alias in ("two", "one", "two"):
            assert post(client, alias).status_code == 200
    assert [
        (
            request.url.host,
            request.headers["x-api-key"],
            json.loads(request.content)["max_tokens"],
        )
        for request in upstream.requests
    ] == [
        ("second.test", SECOND_KEY, 88),
        ("anthropic.test", KEY, 77),
        ("second.test", SECOND_KEY, 88),
    ]


def test_a_follow_up_shows_the_balance_settled_with_anthropics_usage_including_cache(
    tmp_path: Path,
) -> None:
    with TestClient(make_app(tmp_path, answering())) as client:
        post(client, "solo")
        follow_up = post(client, "solo")
    assert remaining(follow_up) == str(CAPACITY - ANTHROPIC_TOTAL - RESERVED)


# Criterion 5.


def test_a_route_of_anthropic_then_mock_falls_back_on_a_529_and_settles_with_the_mocks_usage(
    tmp_path: Path,
) -> None:
    overloaded = {
        "type": "error",
        "error": {"type": "overloaded_error", "message": f"{BODY_SENTINEL} {KEY}"},
    }
    upstream = answering(529, overloaded)
    with TestClient(make_app(tmp_path, upstream)) as client:
        response = post(client, "fallback")
        follow_up = post(client, "fallback")
    assert response.status_code == 200
    assert response.headers["x-tollgate-provider"] == "backup"
    assert response.headers["x-tollgate-fallbacks"] == "1"
    assert len(upstream.requests) == 2  # one per request, none retried
    text = response.text + str(dict(response.headers))
    assert BODY_SENTINEL not in text
    assert KEY not in text
    # The balance after the mock's usage (8), not Anthropic's, then the follow-up's reservation.
    assert remaining(follow_up) == str(CAPACITY - MOCK_TOTAL - RESERVED)


def test_an_anthropic_401_does_not_fall_back_and_is_refunded_in_full(tmp_path: Path) -> None:
    unauthorized = {
        "type": "error",
        "error": {"type": "authentication_error", "message": f"invalid x-api-key {KEY}"},
    }
    upstream = answering(401, unauthorized)
    with TestClient(make_app(tmp_path, upstream)) as client:
        response = post(client, "fallback")
        follow_up = post(client, "solo")
    assert response.status_code == 502
    assert response.json() == BAD_GATEWAY_BODY
    assert "x-tollgate-provider" not in response.headers
    assert KEY not in response.text + str(dict(response.headers))
    assert len(upstream.requests) == 2  # the first request stopped at Anthropic; so did the second
    assert remaining(follow_up) == str(CAPACITY - RESERVED)


@pytest.mark.parametrize("base_url", [..., ""], ids=["absent", "empty"])
def test_without_a_base_url_anthropic_is_reached_at_api_anthropic_com(
    tmp_path: Path, base_url: Any
) -> None:
    claude = {
        key: value for key, value in {**CLAUDE, "base_url": base_url}.items() if value is not ...
    }
    upstream = answering()
    with TestClient(make_app(tmp_path, upstream, claude_table(claude))) as client:
        assert post(client, "solo").status_code == 200
    assert [str(request.url) for request in upstream.requests] == [
        "https://api.anthropic.com/v1/messages"
    ]


def test_the_anthropic_client_has_its_timeouts_and_is_closed_at_shutdown(tmp_path: Path) -> None:
    transport = CountingTransport(answering())
    app = make_app(tmp_path, transport)
    (http_client,) = app.state.owned_clients
    assert http_client.timeout == httpx.Timeout(connect=5, read=12, write=12, pool=12)
    assert http_client.base_url == httpx.URL("https://anthropic.test")
    assert "x-api-key" not in http_client.headers
    assert "anthropic-version" not in http_client.headers
    with TestClient(app) as client:
        assert post(client, "solo").status_code == 200
        assert not http_client.is_closed
    assert transport.closes == 1
    assert http_client.is_closed


CAP_BYTES = 1_024


def padded_reply(size_bytes: int) -> bytes:
    body = {**ANTHROPIC_BODY, "content": [{"type": "text", "text": BODY_SENTINEL}]}
    data = json.dumps(body).encode("utf-8")
    assert len(data) <= size_bytes
    return data + b" " * (size_bytes - len(data))


def test_anthropic_max_response_bytes_is_passed_through(tmp_path: Path) -> None:
    table = claude_table({**CLAUDE, "max_response_bytes": CAP_BYTES})
    over = Upstream(lambda request: httpx.Response(200, content=padded_reply(CAP_BYTES + 1)))
    with TestClient(make_app(tmp_path, over, table)) as client:
        response = post(client, "fallback")
        follow_up = post(client, "solo")
    assert response.status_code == 502
    assert BODY_SENTINEL not in response.text
    assert len(over.requests) == 2  # no fallback to the mock
    assert remaining(follow_up) == str(CAPACITY - RESERVED - RESERVED)  # charged as reserved
    exact = Upstream(lambda request: httpx.Response(200, content=padded_reply(CAP_BYTES)))
    with TestClient(make_app(tmp_path, exact, table)) as client:
        response = post(client, "fallback")
    assert response.status_code == 200
    assert response.headers["x-tollgate-provider"] == "claude"


class CountingIdSource:
    def __init__(self) -> None:
        self.calls = 0

    def next_id(self) -> str:
        self.calls += 1
        return f"chatcmpl-counted-{self.calls}"


def test_anthropic_and_the_mock_share_the_registry_id_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.main.UuidIdSource", CountingIdSource)
    table = claude_table()
    table["routes"]["plain"] = [{"provider": "backup"}]
    with TestClient(make_app(tmp_path, answering(), table)) as client:
        ids = [post(client, alias).json()["id"] for alias in ("solo", "plain", "solo")]
    assert ids == ["chatcmpl-counted-1", "chatcmpl-counted-2", "chatcmpl-counted-3"]
