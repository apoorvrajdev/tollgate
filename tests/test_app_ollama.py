"""Ollama through the whole app (T-204): serving, fallback, the balance and the clients' lifetime.

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
from tests.fakes import AUTH_HEADERS, FakeClock, make_settings

URL = "/v1/chat/completions"
LIMIT_SETTINGS = {"TOLLGATE_TOKENS_PER_MINUTE": "600", "TOLLGATE_CAPACITY_TOKENS": "1000"}
BODY_SENTINEL = "SENTINEL-upstream-body-71c9"
PASSWORD_SENTINEL = "SENTINEL-password-3b0e"
OLLAMA_BODY: dict[str, Any] = {
    "model": "llama3.2:latest",
    "message": {"role": "assistant", "content": "hi from ollama"},
    "done_reason": "stop",
    "prompt_eval_count": 7,
    "eval_count": 5,
}
# "hello there world" reserves 11 tokens: ceil(17 / 4) + 3 for the message, and 3 for the reply.
RESERVED = 11
CAPACITY = 1000
MOCK_TOTAL = 8  # 3 words in, "Mock reply: hello there world" (5 words) out


def payload(model: str) -> dict[str, Any]:
    return {"model": model, "messages": [{"role": "user", "content": "hello there world"}]}


def providers_table(**providers: dict[str, Any]) -> dict[str, Any]:
    return {
        "providers": {**providers, "backup": {"type": "mock"}},
        "routes": {
            "solo": [{"provider": "local", "model": "llama3.2"}],
            "fallback": [{"provider": "local", "model": "llama3.2"}, {"provider": "backup"}],
        },
    }


LOCAL = {"type": "ollama", "base_url": "http://ollama.test:11434", "timeout_seconds": 12}


def make_app(
    tmp_path: Path,
    handler: Callable[[httpx.Request], httpx.Response] | httpx.AsyncBaseTransport,
    table: dict[str, Any] | None = None,
    *,
    transport: bool = True,
) -> FastAPI:
    path = tmp_path / "routes.json"
    path.write_text(json.dumps(table or providers_table(local=LOCAL)), encoding="utf-8")
    settings = make_settings(**LIMIT_SETTINGS, TOLLGATE_ROUTES_FILE=str(path))
    resolved = (
        handler if isinstance(handler, httpx.AsyncBaseTransport) else httpx.MockTransport(handler)
    )
    return create_app(settings, FakeClock(1000.0), http_transport=resolved if transport else None)


class Upstream:
    """A scripted Ollama: answers with `respond` and records every request."""

    def __init__(self, respond: Callable[[httpx.Request], httpx.Response]) -> None:
        self.respond = respond
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.respond(request)


def answering(status: int = 200, body: Any = None) -> Upstream:
    return Upstream(
        lambda request: httpx.Response(status, json=OLLAMA_BODY if body is None else body)
    )


def remaining(response: httpx.Response) -> str:
    value: str = response.headers["x-ratelimit-remaining-tokens"]
    return value


def post(client: TestClient, model: str) -> httpx.Response:
    response: httpx.Response = client.post(URL, json=payload(model), headers=AUTH_HEADERS)
    return response


# Criterion 5: Ollama serves a 200, and the balance is settled with its usage.


def test_ollama_serves_a_200_with_its_reply_model_and_the_routing_headers(tmp_path: Path) -> None:
    upstream = answering()
    with TestClient(make_app(tmp_path, upstream)) as client:
        response = post(client, "solo")
    assert response.status_code == 200
    body = response.json()
    assert body["choices"][0]["message"]["content"] == "hi from ollama"
    assert body["model"] == "llama3.2:latest"
    assert re.fullmatch(r"chatcmpl-[0-9a-f]{32}", body["id"])
    assert body["created"] == 1000
    assert response.headers["x-tollgate-provider"] == "local"
    assert response.headers["x-tollgate-fallbacks"] == "0"
    (request,) = upstream.requests
    assert str(request.url) == "http://ollama.test:11434/api/chat"
    assert json.loads(request.content)["model"] == "llama3.2"


def test_a_follow_up_shows_the_balance_settled_with_ollamas_usage(tmp_path: Path) -> None:
    with TestClient(make_app(tmp_path, answering())) as client:
        post(client, "solo")
        follow_up = post(client, "solo")
    # 1000 - 12 (7 + 5 from Ollama) - 11 reserved by the follow-up.
    assert remaining(follow_up) == str(CAPACITY - 12 - RESERVED)


# Criterion 5 and 3: fallback, and what each failure costs.


def test_a_route_of_ollama_then_mock_falls_back_on_an_ollama_503(tmp_path: Path) -> None:
    upstream = answering(503, {"error": BODY_SENTINEL})
    with TestClient(make_app(tmp_path, upstream)) as client:
        response = post(client, "fallback")
        follow_up = post(client, "fallback")
    assert response.status_code == 200
    assert response.headers["x-tollgate-provider"] == "backup"
    assert response.headers["x-tollgate-fallbacks"] == "1"
    assert len(upstream.requests) == 2  # one per request, none retried
    assert BODY_SENTINEL not in response.text
    # The balance after the mock's usage (8), not Ollama's, then the follow-up's reservation.
    assert remaining(follow_up) == str(CAPACITY - MOCK_TOTAL - RESERVED)


@pytest.mark.parametrize(
    "exception",
    [httpx.ReadTimeout("slow"), httpx.ConnectTimeout("slow"), httpx.ConnectError("refused")],
    ids=["read-timeout", "connect-timeout", "connection-error"],
)
def test_a_timeout_or_a_connection_error_falls_back_to_the_next_target(
    tmp_path: Path, exception: Exception
) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise exception

    with TestClient(make_app(tmp_path, fail)) as client:
        response = post(client, "fallback")
    assert response.status_code == 200
    assert response.headers["x-tollgate-provider"] == "backup"
    assert response.headers["x-tollgate-fallbacks"] == "1"


def test_an_ollama_404_does_not_fall_back_and_is_refunded_in_full(tmp_path: Path) -> None:
    upstream = answering(404, {"error": "model 'x' not found"})
    with TestClient(make_app(tmp_path, upstream)) as client:
        response = post(client, "fallback")
        follow_up = post(client, "solo")
    assert response.status_code == 502
    assert "x-tollgate-provider" not in response.headers
    assert len(upstream.requests) == 2  # the first request stopped at Ollama; so did the second
    assert remaining(follow_up) == str(CAPACITY - RESERVED)


def test_a_200_that_is_not_valid_json_is_a_502_charged_as_reserved(tmp_path: Path) -> None:
    upstream = Upstream(lambda request: httpx.Response(200, content=b"{not json"))
    with TestClient(make_app(tmp_path, upstream)) as client:
        response = post(client, "solo")
        follow_up = post(client, "solo")
    assert response.status_code == 502
    assert remaining(follow_up) == str(CAPACITY - RESERVED - RESERVED)


def test_a_502_shows_nothing_from_the_upstream_body_or_the_base_url(tmp_path: Path) -> None:
    local = {**LOCAL, "base_url": f"http://user:{PASSWORD_SENTINEL}@ollama.test:11434"}
    upstream = answering(503, {"error": BODY_SENTINEL})
    app = make_app(tmp_path, upstream, providers_table(local=local))
    with TestClient(app) as client:
        response = post(client, "solo")
    assert response.status_code == 502
    text = response.text + str(dict(response.headers))
    assert BODY_SENTINEL not in text
    assert PASSWORD_SENTINEL not in text


# The clients the app builds.


def test_each_http_provider_gets_its_own_client_with_its_timeouts_and_base_url(
    tmp_path: Path,
) -> None:
    second = {"type": "ollama", "base_url": "http://other.test:9", "timeout_seconds": 30}
    third = {"type": "ollama"}
    upstream = answering()
    app = make_app(
        tmp_path,
        upstream,
        {
            "providers": {"local": LOCAL, "second": second, "third": third},
            "routes": {name: [{"provider": name}] for name in ("local", "second", "third")},
        },
    )
    clients = app.state.owned_clients
    assert len(clients) == 3
    assert len({id(client) for client in clients}) == 3
    assert [client.timeout for client in clients] == [
        httpx.Timeout(connect=5, read=12, write=12, pool=12),
        httpx.Timeout(connect=5, read=30, write=30, pool=30),
        httpx.Timeout(connect=5, read=60, write=60, pool=60),
    ]
    assert [client.base_url for client in clients] == [
        httpx.URL("http://ollama.test:11434"),
        httpx.URL("http://other.test:9"),
        httpx.URL("http://localhost:11434"),
    ]
    with TestClient(app) as client:
        for name in ("local", "second", "third"):
            assert post(client, name).status_code == 200
    # Every client uses the transport the app was given.
    assert [request.url.host for request in upstream.requests] == [
        "ollama.test",
        "other.test",
        "localhost",
    ]


def test_an_empty_base_url_is_treated_as_not_given_and_uses_the_default_host(
    tmp_path: Path,
) -> None:
    upstream = answering()
    table = providers_table(local={"type": "ollama", "base_url": ""})
    with TestClient(make_app(tmp_path, upstream, table)) as client:
        assert post(client, "solo").status_code == 200
    assert [str(request.url) for request in upstream.requests] == [
        "http://localhost:11434/api/chat"
    ]


class CountingTransport(httpx.MockTransport):
    """A MockTransport that counts how often it is closed."""

    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        super().__init__(handler)
        self.closes = 0

    async def aclose(self) -> None:
        self.closes += 1
        await super().aclose()


def test_the_http_clients_are_closed_at_shutdown_and_not_before(tmp_path: Path) -> None:
    transport = CountingTransport(answering())
    table = {
        "providers": {"local": LOCAL, "second": {"type": "ollama"}, "mock": {"type": "mock"}},
        "routes": {"solo": [{"provider": "local"}]},
    }
    app = make_app(tmp_path, transport, table)
    clients = app.state.owned_clients
    assert len(clients) == 2
    with TestClient(app) as client:
        assert post(client, "solo").status_code == 200
        assert transport.closes == 0
        assert [c.is_closed for c in clients] == [False, False]
    assert transport.closes == 2
    assert [c.is_closed for c in clients] == [True, True]


def test_a_mock_only_app_builds_no_http_client(tmp_path: Path) -> None:
    app = make_app(tmp_path, answering(), {"providers": {"backup": {"type": "mock"}}, "routes": {}})
    assert app.state.owned_clients == []


def test_without_a_transport_the_app_builds_real_clients_and_closes_them(tmp_path: Path) -> None:
    app = make_app(tmp_path, answering(), transport=False)
    (http_client,) = app.state.owned_clients
    assert isinstance(http_client, httpx.AsyncClient)
    with TestClient(app):  # nothing is sent, so no connection is made
        assert not http_client.is_closed
    assert http_client.is_closed
