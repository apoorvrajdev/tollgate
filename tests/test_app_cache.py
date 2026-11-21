"""The embedder `create_app()` builds when the cache is on (ADR-0015, T-302).

No test connects: every client runs on an `httpx.MockTransport`.
"""

import asyncio
import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

import app.main
from app.cache.embedder import Embedder
from app.cache.hashing import HashingEmbedder
from app.main import create_app
from app.settings import SettingsError
from tests.fakes import make_settings

CACHE_ENV = {
    "TOLLGATE_CACHE_EMBEDDER": "ollama",
    "TOLLGATE_CACHE_EMBEDDER_MODEL": "all-minilm",
    "TOLLGATE_CACHE_SIMILARITY_THRESHOLD": "0.9",
}
URL_PASSWORD = "url-pw-sentinel-2c7d"


class Handler:
    """A MockTransport handler that records requests and answers with one vector."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, json={"embeddings": [[3, 4]]})


def cache_app(handler: Handler, **env: str) -> Any:
    settings = make_settings(**{**CACHE_ENV, **env})
    return create_app(settings, http_transport=httpx.MockTransport(handler))


def test_cache_off_has_no_embedder_and_no_embedder_client() -> None:
    application = create_app(make_settings())
    assert application.state.settings.cache is None
    assert application.state.embedder is None
    assert application.state.owned_clients == []


def test_cache_on_builds_a_client_with_the_url_and_the_timeouts() -> None:
    application = cache_app(Handler())
    (client,) = application.state.owned_clients
    assert str(client.base_url) == "http://localhost:11434"
    assert client.timeout == httpx.Timeout(connect=5, read=10, write=10, pool=10)
    custom = cache_app(Handler(), TOLLGATE_CACHE_EMBEDDER_URL="http://ollama.test:9")
    assert str(custom.state.owned_clients[0].base_url) == "http://ollama.test:9"


def test_cache_on_opens_no_connection_until_the_embedder_is_used() -> None:
    handler = Handler()
    cache_app(handler)
    assert handler.requests == []


def test_the_client_is_registered_and_closed_at_shutdown_and_not_before() -> None:
    application = cache_app(Handler())
    (client,) = application.state.owned_clients
    with TestClient(application):
        assert not client.is_closed
    assert client.is_closed


def test_the_embedder_uses_the_model_and_the_injected_transport() -> None:
    handler = Handler()
    application = cache_app(handler)
    embedder: Embedder = application.state.embedder
    assert embedder.identity == "ollama:all-minilm"
    vector = asyncio.run(embedder.embed("hello"))
    assert list(vector) == [0.6, 0.8]
    (request,) = handler.requests
    assert request.url.path == "/api/embed"
    assert json.loads(request.content)["model"] == "all-minilm"
    asyncio.run(application.state.owned_clients[0].aclose())


def test_an_injected_embedder_builds_no_client() -> None:
    handler = Handler()
    injected = HashingEmbedder()
    settings = make_settings(**CACHE_ENV)
    application = create_app(
        settings, http_transport=httpx.MockTransport(handler), embedder=injected
    )
    assert application.state.embedder is injected
    assert application.state.owned_clients == []
    assert handler.requests == []


def test_an_embedder_with_the_cache_off_raises_value_error() -> None:
    with pytest.raises(ValueError, match="cache is off"):
        create_app(make_settings(), embedder=HashingEmbedder())


class CountingRedis:
    calls = 0

    @classmethod
    def from_url(cls, url: str) -> Any:
        cls.calls += 1
        raise AssertionError("the Redis client must not be built")


def test_an_invalid_embedder_url_is_a_settings_error_without_the_value_and_before_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app.main, "Redis", CountingRedis)
    CountingRedis.calls = 0
    settings = make_settings(
        TOLLGATE_LIMITER_BACKEND="redis",
        TOLLGATE_REDIS_URL="redis://127.0.0.1:1/0",
        TOLLGATE_CACHE_EMBEDDER_URL=f"http://user:{URL_PASSWORD}@[::1",
        **CACHE_ENV,
    )
    with pytest.raises(SettingsError) as raised:
        create_app(settings)
    error = raised.value
    assert error.variable == "TOLLGATE_CACHE_EMBEDDER_URL"
    assert URL_PASSWORD not in str(error) + repr(error)
    assert error.__context__ is None
    assert CountingRedis.calls == 0
