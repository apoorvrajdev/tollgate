"""OpenAI through the whole app (T-205): serving, fallback, the balance, the key and the client.

The app is built on a route file in tmp_path and an `httpx.MockTransport`: no network, no sleeping.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import create_app
from tests.fakes import TEST_API_KEY, FakeClock, make_settings
from tests.test_app_ollama import (
    BAD_GATEWAY_BODY,
    CAPACITY,
    LIMIT_SETTINGS,
    MOCK_TOTAL,
    RESERVED,
    CountingTransport,
    Upstream,
    post,
    remaining,
)

KEY = "sk-SENTINEL-app-key-0c4b"
BODY_SENTINEL = "SENTINEL-openai-body-e21d"
UPSTREAM_CREATED = 1767225600
OPENAI_BODY: dict[str, Any] = {
    "id": "chatcmpl-upstream-app",
    "object": "chat.completion",
    "created": UPSTREAM_CREATED,
    "model": "gpt-4o-mini-2024-07-18",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "hi from openai", "refusal": None},
            "logprobs": None,
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 9, "completion_tokens": 12, "total_tokens": 21},
}
OPENAI_TOTAL = 21
CLOUD: dict[str, Any] = {
    "type": "openai",
    "base_url": "https://openai.test",
    "api_key_env": "OPENAI_TEST_KEY",
    "timeout_seconds": 12,
}


def cloud_table(cloud: dict[str, Any] = CLOUD) -> dict[str, Any]:
    return {
        "providers": {"cloud": cloud, "backup": {"type": "mock"}},
        "routes": {
            "solo": [{"provider": "cloud", "model": "gpt-4o-mini"}],
            "fallback": [{"provider": "cloud", "model": "gpt-4o-mini"}, {"provider": "backup"}],
        },
    }


def make_app(
    tmp_path: Path,
    handler: Callable[[httpx.Request], httpx.Response] | httpx.AsyncBaseTransport,
    table: dict[str, Any] | None = None,
) -> FastAPI:
    path = tmp_path / "routes.json"
    path.write_text(json.dumps(table or cloud_table()), encoding="utf-8")
    settings = make_settings(**LIMIT_SETTINGS, TOLLGATE_ROUTES_FILE=str(path), OPENAI_TEST_KEY=KEY)
    transport = (
        handler if isinstance(handler, httpx.AsyncBaseTransport) else httpx.MockTransport(handler)
    )
    return create_app(settings, FakeClock(1000.0), http_transport=transport)


def answering(status: int = 200, body: Any = None) -> Upstream:
    return Upstream(
        lambda request: httpx.Response(status, json=OPENAI_BODY if body is None else body)
    )


def test_openai_serves_a_200_keeping_its_id_created_and_model(tmp_path: Path) -> None:
    upstream = answering()
    with TestClient(make_app(tmp_path, upstream)) as client:
        response = post(client, "solo")
    assert response.status_code == 200
    body = response.json()
    assert body["choices"][0]["message"]["content"] == "hi from openai"
    assert (body["id"], body["created"], body["model"]) == (
        "chatcmpl-upstream-app",
        UPSTREAM_CREATED,
        "gpt-4o-mini-2024-07-18",
    )
    assert body["usage"] == {"prompt_tokens": 9, "completion_tokens": 12, "total_tokens": 21}
    assert response.headers["x-tollgate-provider"] == "cloud"
    assert response.headers["x-tollgate-fallbacks"] == "0"
    (request,) = upstream.requests
    assert str(request.url) == "https://openai.test/v1/chat/completions"
    assert json.loads(request.content)["model"] == "gpt-4o-mini"
    # The provider's key, never the gateway client's own key.
    assert request.headers.get_list("authorization") == [f"Bearer {KEY}"]
    assert TEST_API_KEY not in str(request.headers) + request.content.decode()


def test_each_openai_provider_sends_its_own_key(tmp_path: Path) -> None:
    path = tmp_path / "routes.json"
    second = {**CLOUD, "base_url": "https://second.test", "api_key_env": "OPENAI_SECOND_KEY"}
    table = {
        "providers": {"cloud": CLOUD, "second": second},
        "routes": {"one": [{"provider": "cloud"}], "two": [{"provider": "second"}]},
    }
    path.write_text(json.dumps(table), encoding="utf-8")
    settings = make_settings(
        **LIMIT_SETTINGS,
        TOLLGATE_ROUTES_FILE=str(path),
        OPENAI_TEST_KEY=KEY,
        OPENAI_SECOND_KEY="sk-SENTINEL-second-key-9f1a",
    )
    upstream = answering()
    app = create_app(settings, FakeClock(1000.0), http_transport=httpx.MockTransport(upstream))
    with TestClient(app) as client:
        for alias in ("two", "one", "two"):
            assert post(client, alias).status_code == 200
    assert [
        (request.url.host, request.headers["authorization"]) for request in upstream.requests
    ] == [
        ("second.test", "Bearer sk-SENTINEL-second-key-9f1a"),
        ("openai.test", f"Bearer {KEY}"),
        ("second.test", "Bearer sk-SENTINEL-second-key-9f1a"),
    ]


def test_a_follow_up_shows_the_balance_settled_with_openais_usage(tmp_path: Path) -> None:
    with TestClient(make_app(tmp_path, answering())) as client:
        post(client, "solo")
        follow_up = post(client, "solo")
    assert remaining(follow_up) == str(CAPACITY - OPENAI_TOTAL - RESERVED)


# Criterion 5.


def test_a_route_of_openai_then_mock_falls_back_on_an_openai_429_and_settles_with_the_mocks_usage(
    tmp_path: Path,
) -> None:
    upstream = answering(429, {"error": {"message": f"{BODY_SENTINEL} {KEY}"}})
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
    # The balance after the mock's usage (8), not OpenAI's, then the follow-up's reservation.
    assert remaining(follow_up) == str(CAPACITY - MOCK_TOTAL - RESERVED)


def test_an_openai_401_does_not_fall_back_and_is_refunded_in_full(tmp_path: Path) -> None:
    upstream = answering(401, {"error": {"message": f"Incorrect API key provided: {KEY}"}})
    with TestClient(make_app(tmp_path, upstream)) as client:
        response = post(client, "fallback")
        follow_up = post(client, "solo")
    assert response.status_code == 502
    assert response.json() == BAD_GATEWAY_BODY
    assert "x-tollgate-provider" not in response.headers
    assert KEY not in response.text + str(dict(response.headers))
    assert len(upstream.requests) == 2  # the first request stopped at OpenAI; so did the second
    assert remaining(follow_up) == str(CAPACITY - RESERVED)


@pytest.mark.parametrize("base_url", [..., ""], ids=["absent", "empty"])
def test_without_a_base_url_openai_is_reached_at_api_openai_com(
    tmp_path: Path, base_url: Any
) -> None:
    cloud = {
        key: value for key, value in {**CLOUD, "base_url": base_url}.items() if value is not ...
    }
    upstream = answering()
    with TestClient(make_app(tmp_path, upstream, cloud_table(cloud))) as client:
        assert post(client, "solo").status_code == 200
    assert [str(request.url) for request in upstream.requests] == [
        "https://api.openai.com/v1/chat/completions"
    ]


def test_the_openai_client_has_its_timeouts_and_is_closed_at_shutdown(tmp_path: Path) -> None:
    transport = CountingTransport(answering())
    app = make_app(tmp_path, transport)
    (http_client,) = app.state.owned_clients
    assert http_client.timeout == httpx.Timeout(connect=5, read=12, write=12, pool=12)
    assert http_client.base_url == httpx.URL("https://openai.test")
    assert "authorization" not in http_client.headers
    with TestClient(app) as client:
        assert post(client, "solo").status_code == 200
        assert not http_client.is_closed
    assert transport.closes == 1
    assert http_client.is_closed


CAP_BYTES = 1_024


def padded_reply(size_bytes: int) -> bytes:
    body = {**OPENAI_BODY, "choices": [{**OPENAI_BODY["choices"][0]}]}
    body["choices"][0]["message"] = {"role": "assistant", "content": BODY_SENTINEL}
    data = json.dumps(body).encode("utf-8")
    assert len(data) <= size_bytes
    return data + b" " * (size_bytes - len(data))


def test_openai_max_response_bytes_is_passed_through(tmp_path: Path) -> None:
    table = cloud_table({**CLOUD, "max_response_bytes": CAP_BYTES})
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
    assert response.headers["x-tollgate-provider"] == "cloud"
