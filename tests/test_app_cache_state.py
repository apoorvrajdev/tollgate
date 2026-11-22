"""The id source and the semantic cache `create_app()` keeps on the app state (ADR-0014, T-305).

No test connects: the HTTP clients run on an `httpx.MockTransport`, and vectors come from
`FakeEmbedder` and are dyadic, so every similarity is exact.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, ClassVar

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.models import ChatMessage, ChatRequest, ChatResponse, Usage
from app.cache.semantic import Hit, InMemorySemanticCache, Miss
from app.main import build_providers, create_app
from app.routing.config import RouteTable
from tests.fakes import AUTH_HEADERS, FakeClock, FakeEmbedder, make_settings
from tests.test_app_anthropic import ANTHROPIC_BODY
from tests.test_app_ollama import OLLAMA_BODY, URL

START_SECONDS = 100.0
CALLER = "caller"
CACHE_ENV = {
    "TOLLGATE_CACHE_EMBEDDER": "ollama",
    "TOLLGATE_CACHE_EMBEDDER_MODEL": "m",
    "TOLLGATE_CACHE_SIMILARITY_THRESHOLD": "0.5",
    "TOLLGATE_CACHE_TTL_SECONDS": "60",
    "TOLLGATE_CACHE_MAX_ENTRIES": "2",
}
# Dot products with STORED are exact: 1.0, 0.5, 0.5 - 2**-10 and 0.
VECTORS: dict[str, tuple[float, ...]] = {
    "stored": (1.0, 0.0),
    "same": (1.0, 0.0),
    "at-threshold": (0.5, 0.5),
    "below-threshold": (0.5 - 2**-10, 0.5),
    "other-1": (0.0, 1.0),
    "other-2": (0.0, 1.0),
    "far-a": (-1.0, 0.0),
    "far-b": (0.0, -1.0),
}
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


def test_cache_off_leaves_the_state_cache_none() -> None:
    assert create_app(make_settings()).state.cache is None


def answer() -> ChatResponse:
    return ChatResponse.model_validate(
        {
            "id": "chatcmpl-1",
            "object": "chat.completion",
            "created": 1,
            "model": "m",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "a"},
                    "finish_reason": "stop",
                }
            ],
            "usage": Usage(prompt_tokens=1, completion_tokens=2, total_tokens=3).model_dump(),
        }
    )


def cache_app(**env: str) -> tuple[InMemorySemanticCache, FakeClock]:
    clock = FakeClock(START_SECONDS)
    application = create_app(
        make_settings(**{**CACHE_ENV, **env}),
        clock,
        embedder=FakeEmbedder(VECTORS),
    )
    cache = application.state.cache
    assert isinstance(cache, InMemorySemanticCache)
    return cache, clock


def chat(text: str) -> ChatRequest:
    return ChatRequest(model="m", messages=[ChatMessage(role="user", content=text)])


def look_up(cache: InMemorySemanticCache, text: str) -> Hit | Miss:
    result = asyncio.run(cache.lookup(CALLER, chat(text)))
    assert isinstance(result, Hit | Miss)
    return result


def store(cache: InMemorySemanticCache, text: str) -> None:
    miss = look_up(cache, text)
    assert isinstance(miss, Miss)
    assert cache.store(miss.ticket, answer(), "backup")


def test_the_cache_embeds_with_the_app_embedder() -> None:
    embedder = FakeEmbedder(VECTORS)
    application = create_app(make_settings(**CACHE_ENV), FakeClock(), embedder=embedder)
    look_up(application.state.cache, "stored")
    assert embedder.calls == ["stored"]


def test_an_entry_hits_just_before_the_ttl_and_misses_at_it() -> None:
    cache, clock = cache_app()
    store(cache, "stored")
    clock.advance(59.5)
    assert isinstance(look_up(cache, "same"), Hit)
    clock.advance(0.5)  # 60 seconds after the store
    assert isinstance(look_up(cache, "same"), Miss)


def test_the_ttl_comes_from_the_settings() -> None:
    cache, clock = cache_app(TOLLGATE_CACHE_TTL_SECONDS="120")
    store(cache, "stored")
    clock.advance(119.5)
    assert isinstance(look_up(cache, "same"), Hit)
    clock.advance(0.5)
    assert isinstance(look_up(cache, "same"), Miss)


def test_a_similarity_at_the_threshold_hits_and_just_below_it_misses() -> None:
    cache, _ = cache_app()
    store(cache, "stored")
    at = look_up(cache, "at-threshold")
    assert isinstance(at, Hit)
    assert at.similarity == 0.5
    assert isinstance(look_up(cache, "below-threshold"), Miss)


def test_the_threshold_comes_from_the_settings() -> None:
    cache, _ = cache_app(TOLLGATE_CACHE_SIMILARITY_THRESHOLD="0.75")
    store(cache, "stored")
    assert isinstance(look_up(cache, "at-threshold"), Miss)  # passes at 0.5, not at 0.75
    assert isinstance(look_up(cache, "same"), Hit)


def test_storing_exactly_the_maximum_evicts_nothing_and_one_more_evicts() -> None:
    cache, _ = cache_app()
    store(cache, "stored")
    store(cache, "other-1")
    assert len(cache) == 2
    assert isinstance(look_up(cache, "same"), Hit)  # the first entry is still there
    store(cache, "far-a")  # a third entry; the least recently used one goes
    assert len(cache) == 2
    assert isinstance(look_up(cache, "other-2"), Miss)  # "other-1" was evicted
    assert isinstance(look_up(cache, "same"), Hit)


def test_the_maximum_comes_from_the_settings() -> None:
    cache, _ = cache_app(TOLLGATE_CACHE_MAX_ENTRIES="3")
    for text in ("stored", "other-1", "far-a"):
        store(cache, text)
    assert len(cache) == 3
    store(cache, "far-b")
    assert len(cache) == 3


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


def test_the_cache_embeds_with_the_embedder_the_app_built() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"embeddings": [[1.0, 0.0]]})

    application = create_app(
        make_settings(**CACHE_ENV), FakeClock(), http_transport=httpx.MockTransport(handler)
    )
    assert isinstance(look_up(application.state.cache, "stored"), Miss)
    assert len(requests) == 1
