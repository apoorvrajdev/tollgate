"""The id source `create_app()` shares between the providers (T-305).

No test connects: the HTTP clients run on an `httpx.MockTransport`.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, ClassVar

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.models import ChatMessage, ChatRequest
from app.main import build_providers, create_app
from app.routing.config import RouteTable
from tests.fakes import AUTH_HEADERS, FakeClock, make_settings
from tests.test_app_anthropic import ANTHROPIC_BODY
from tests.test_app_ollama import OLLAMA_BODY, URL

TABLE: dict[str, Any] = {
    "providers": {
        "backup": {"type": "mock"},
        "local": {"type": "ollama", "base_url": "http://ollama.test:11434", "timeout_seconds": 12},
        "claude": {
            "type": "anthropic",
            "base_url": "https://anthropic.test",
            "api_key_env": "ANTHROPIC_TEST_KEY",
            "default_max_tokens": 77,
            "timeout_seconds": 12,
        },
    },
    "routes": {
        "mock": [{"provider": "backup"}],
        "ollama": [{"provider": "local", "model": "llama"}],
        "anthropic": [{"provider": "claude", "model": "claude-sonnet"}],
    },
}


class CountingIdSource:
    """Counts the instances built, so a test sees how many id sources the app made."""

    instances: ClassVar[list["CountingIdSource"]] = []

    def __init__(self) -> None:
        self.calls = 0
        CountingIdSource.instances.append(self)

    def next_id(self) -> str:
        self.calls += 1
        return f"chatcmpl-counted-{self.calls}"


def route_by_host(request: httpx.Request) -> httpx.Response:
    body = OLLAMA_BODY if request.url.host == "ollama.test" else ANTHROPIC_BODY
    return httpx.Response(200, json=body)


def table_file(tmp_path: Path) -> str:
    path = tmp_path / "routes.json"
    path.write_text(json.dumps(TABLE), encoding="utf-8")
    return str(path)


def test_the_mock_ollama_and_anthropic_providers_share_the_one_app_id_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    CountingIdSource.instances = []
    monkeypatch.setattr("app.main.UuidIdSource", CountingIdSource)
    settings = make_settings(
        TOLLGATE_ROUTES_FILE=table_file(tmp_path),
        TOLLGATE_CAPACITY_TOKENS="1000",
        ANTHROPIC_TEST_KEY="ant-key",
    )
    application = create_app(settings, http_transport=httpx.MockTransport(route_by_host))
    with TestClient(application) as client:
        ids = [
            client.post(
                URL,
                headers=AUTH_HEADERS,
                json={"model": alias, "messages": [{"role": "user", "content": "hi"}]},
            ).json()["id"]
            for alias in ("mock", "ollama", "anthropic", "mock")
        ]
    assert len(CountingIdSource.instances) == 1
    assert application.state.id_source is CountingIdSource.instances[0]
    assert ids == [f"chatcmpl-counted-{n}" for n in (1, 2, 3, 4)]


def mock_table() -> RouteTable:
    return make_settings().route_table


def test_build_providers_uses_the_source_it_is_given() -> None:
    table = mock_table()
    source = CountingIdSource()
    provider = build_providers(table, FakeClock(), id_source=source).providers["mock"]
    request = ChatRequest(model="m", messages=[ChatMessage(role="user", content="hi")])
    assert asyncio.run(provider.complete(request)).id == "chatcmpl-counted-1"


def test_build_providers_without_a_source_builds_it_inside_each_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    CountingIdSource.instances = []
    monkeypatch.setattr("app.main.UuidIdSource", CountingIdSource)
    table = mock_table()
    request = ChatRequest(model="m", messages=[ChatMessage(role="user", content="hi")])
    first = build_providers(table, FakeClock()).providers["mock"]
    second = build_providers(table, FakeClock()).providers["mock"]
    assert len(CountingIdSource.instances) == 2
    assert asyncio.run(first.complete(request)).id == "chatcmpl-counted-1"
    assert asyncio.run(second.complete(request)).id == "chatcmpl-counted-1"
