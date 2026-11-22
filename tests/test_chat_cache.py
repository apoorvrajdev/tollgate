"""The semantic cache on POST /v1/chat/completions (T-306, ADR-0014, ADR-0015).

Limits as in test_chat_routing.py: capacity 1000 tokens, refilled at 600 per minute (10 per
second), on a fake clock. Every prompt below is 17 to 20 characters, so each reserves 11 tokens
(no `max_tokens`), and a scripted provider reports 20 + 17 = 37 tokens.

The cache runs on `FakeEmbedder` with dyadic vectors, so every similarity is exact: the two
"hello" prompts score 1.0 against each other and 0 against "unrelated words here".
Route `pair` tries `first`, then `second`; there is no default route.
"""

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.cache.embedder import EmbeddingError
from app.main import create_app
from app.providers.errors import ProviderError
from tests.fakes import (
    AUTH_HEADERS,
    TEST_API_KEY,
    FakeClock,
    FakeEmbedder,
    ScriptedProvider,
    make_settings,
)
from tests.test_app_cache_state import CountingIdSource
from tests.test_app_ollama import OLLAMA_BODY
from tests.test_chat_rate_limits import CALLER_ID, OTHER_API_KEY, RecordingLimiter
from tests.test_chat_routing import (
    LIMIT_SETTINGS,
    START_SECONDS,
    URL,
    limit_values,
    route_file,
    routing_values,
)

CACHE_HEADER = "x-tollgate-cache"
PROMPT = "hello there world"
SIMILAR = "hello there, world"
UNRELATED = "unrelated words here"
VECTORS: dict[str, tuple[float, ...]] = {
    PROMPT: (1.0, 0.0),
    SIMILAR: (1.0, 0.0),
    UNRELATED: (0.0, 1.0),
}
CACHE_ENV = {
    "TOLLGATE_CACHE_EMBEDDER": "ollama",
    "TOLLGATE_CACHE_EMBEDDER_MODEL": "m",
    "TOLLGATE_CACHE_SIMILARITY_THRESHOLD": "0.5",
    "TOLLGATE_CACHE_TTL_SECONDS": "60",
    "TOLLGATE_CACHE_MAX_ENTRIES": "100",
}
OTHER_HEADERS = {"Authorization": f"Bearer {OTHER_API_KEY}"}


class SequenceIdSource:
    """Numbered ids, so a test sees exactly which call to the source made an id."""

    def __init__(self) -> None:
        self.calls = 0

    def next_id(self) -> str:
        self.calls += 1
        return f"chatcmpl-hit-{self.calls}"


def payload(content: str, model: str = "pair", **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"model": model, "messages": [{"role": "user", "content": content}]}
    body.update(overrides)
    return body


class CacheGateway:
    """The app on a route file in tmp_path, with scripted providers, a recording limiter, a
    numbered id source and, with `cache`, a `FakeEmbedder`. Unnamed providers stay mocks.
    """

    def __init__(
        self,
        tmp_path: Path,
        providers: dict[str, ScriptedProvider],
        *,
        cache: bool = True,
        embedder: FakeEmbedder | None = None,
    ) -> None:
        path = tmp_path / "routes.json"
        path.write_text(json.dumps(route_file(default=False)), encoding="utf-8")
        env = {
            **LIMIT_SETTINGS,
            "TOLLGATE_ROUTES_FILE": str(path),
            "TOLLGATE_API_KEYS": f"{TEST_API_KEY},{OTHER_API_KEY}",
        }
        if cache:
            env.update(CACHE_ENV)
            self.embedder: FakeEmbedder | None = embedder or FakeEmbedder(VECTORS)
        else:
            self.embedder = None
        self.clock = FakeClock(START_SECONDS)
        self.app: FastAPI = create_app(
            make_settings(**env), self.clock, providers=providers, embedder=self.embedder
        )
        self.recorder = RecordingLimiter(self.app.state.limiter)
        self.app.state.limiter = self.recorder
        self.ids = SequenceIdSource()
        self.app.state.id_source = self.ids
        self.client = TestClient(self.app, headers=AUTH_HEADERS)

    def post(self, content: str, **overrides: Any) -> httpx.Response:
        response: httpx.Response = self.client.post(URL, json=payload(content, **overrides))
        return response

    @property
    def embedded(self) -> list[str]:
        assert self.embedder is not None
        return self.embedder.calls

    def stored(self) -> int:
        return len(self.app.state.cache)


def scripted() -> dict[str, ScriptedProvider]:
    return {"first": ScriptedProvider("first"), "second": ScriptedProvider("second")}


def ollama_app(
    tmp_path: Path, handler: Callable[[httpx.Request], httpx.Response], *, cache: bool
) -> tuple[FastAPI, FakeClock]:
    table = {
        "providers": {
            "local": {"type": "ollama", "base_url": "http://ollama.test:11434"},
        },
        "routes": {"solo": [{"provider": "local", "model": "llama3.2"}]},
    }
    path = tmp_path / "routes.json"
    path.write_text(json.dumps(table), encoding="utf-8")
    env = {**LIMIT_SETTINGS, "TOLLGATE_ROUTES_FILE": str(path)}
    if cache:
        env.update(CACHE_ENV, TOLLGATE_CACHE_EMBEDDER_URL="http://embed.test:11434")
    clock = FakeClock(START_SECONDS)
    application = create_app(
        make_settings(**env), clock, http_transport=httpx.MockTransport(handler)
    )
    return application, clock


class OllamaUpstream:
    """Answers `/api/embed` with one fixed vector and `/api/chat` with OLLAMA_BODY; records each
    request as (host, path, JSON body).
    """

    def __init__(self) -> None:
        self.seen: list[tuple[str, str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append((request.url.host, request.url.path, json.loads(request.content)))
        if request.url.path == "/api/embed":
            return httpx.Response(200, json={"embeddings": [[3.0, 4.0]]})
        return httpx.Response(200, json=OLLAMA_BODY)

    def paths(self) -> list[tuple[str, str]]:
        return [(host, path) for host, path, _ in self.seen]


# Criterion 1: the cache off.


def test_cache_off_each_200_says_skip_including_after_a_fallback(tmp_path: Path) -> None:
    first = ScriptedProvider("first", error=ProviderError("timeout"))
    gateway = CacheGateway(tmp_path, {"first": first}, cache=False)
    assert (gateway.app.state.cache, gateway.app.state.embedder) == (None, None)
    for content in (PROMPT, SIMILAR):
        response = gateway.post(content)
        assert response.status_code == 200
        assert response.headers[CACHE_HEADER] == "skip"
        assert routing_values(response) == ("second", "1")


def test_cache_off_on_the_built_in_mock_route_says_skip() -> None:
    application = create_app(make_settings(), FakeClock())
    response = TestClient(application, headers=AUTH_HEADERS).post(
        URL, json=payload(PROMPT, "mock-1")
    )
    assert response.status_code == 200
    assert response.headers[CACHE_HEADER] == "skip"


def test_cache_off_an_ollama_route_never_calls_the_embed_endpoint(tmp_path: Path) -> None:
    upstream = OllamaUpstream()
    application, _ = ollama_app(tmp_path, upstream, cache=False)
    with TestClient(application, headers=AUTH_HEADERS) as client:
        responses = [client.post(URL, json=payload(PROMPT, "solo")) for _ in range(2)]
    assert [r.headers[CACHE_HEADER] for r in responses] == ["skip", "skip"]
    assert upstream.paths() == [("ollama.test", "/api/chat")] * 2


# Criterion 2: a miss served after a fallback, then a hit.


def test_a_miss_served_after_a_fallback_then_a_hit_from_the_cache(tmp_path: Path) -> None:
    first = ScriptedProvider("first", error=ProviderError("timeout"))
    second = ScriptedProvider("second", reported_model="reported-2")
    gateway = CacheGateway(tmp_path, {"first": first, "second": second})
    miss = gateway.post(PROMPT)
    assert miss.status_code == 200
    assert miss.headers[CACHE_HEADER] == "miss"
    assert routing_values(miss) == ("second", "1")
    stored = miss.json()
    assert (stored["id"], stored["created"], stored["model"]) == (
        "chatcmpl-second",
        0,
        "reported-2",
    )
    gateway.clock.advance(42.5)
    hit = gateway.post(SIMILAR)
    assert hit.status_code == 200
    assert hit.headers[CACHE_HEADER] == "hit"
    assert routing_values(hit) == ("second", "0")
    assert hit.json() == {**stored, "id": "chatcmpl-hit-1", "created": 1042}
    assert gateway.ids.calls == 1
    assert (len(first.requests), len(second.requests)) == (1, 1)
    assert gateway.embedded == [PROMPT, SIMILAR]


# Criterion 3: a hit settles 0.


def test_a_hit_reserves_once_settles_zero_once_and_leaves_the_balance_unchanged(
    tmp_path: Path,
) -> None:
    gateway = CacheGateway(tmp_path, scripted())
    miss = gateway.post(PROMPT)
    # 1000 - 11 = 989; 11 missing at 10 per second is 1.1 s, so 2 s. The settle leaves 963.
    assert limit_values(miss) == ("1000", "989", "2s", None)
    hit = gateway.post(SIMILAR)
    assert hit.headers[CACHE_HEADER] == "hit"
    # 963 - 11 = 952; 48 missing is 4.8 s, so 5 s.
    assert limit_values(hit) == ("1000", "952", "5s", None)
    assert gateway.recorder.calls[2:] == [("reserve", CALLER_ID, 11), ("settle", CALLER_ID, 11, 0)]
    follow_up = gateway.post(UNRELATED)
    assert follow_up.headers[CACHE_HEADER] == "miss"
    # The hit gave back all 11, so the balance is 963 again: 963 - 11 = 952. Settling the stored
    # usage would show 915, and keeping the reservation 941.
    assert limit_values(follow_up) == ("1000", "952", "5s", None)


# Criterion 4: no embedding before the reservation.


def test_a_429_for_a_cached_prompt_never_calls_the_embedder(tmp_path: Path) -> None:
    gateway = CacheGateway(tmp_path, scripted())
    assert gateway.post(PROMPT).headers[CACHE_HEADER] == "miss"
    drained = asyncio.run(gateway.app.state.limiter.reserve(CALLER_ID, 960))
    assert drained.allowed  # 963 - 960 leaves 3, less than the 11 the next request needs
    refused = gateway.post(SIMILAR)
    assert refused.status_code == 429
    assert gateway.embedded == [PROMPT]


def test_a_404_and_a_400_never_call_the_embedder(tmp_path: Path) -> None:
    gateway = CacheGateway(tmp_path, scripted())
    assert gateway.post(PROMPT, model="no-such-model").status_code == 404
    bad = gateway.client.post(URL, json={"model": "pair", "messages": []})
    assert bad.status_code == 400
    assert gateway.embedded == []


# Criterion 5: what is not stored.


def test_after_a_length_answer_the_next_similar_request_is_a_miss_again(tmp_path: Path) -> None:
    first = ScriptedProvider("first", finish_reason="length")
    gateway = CacheGateway(tmp_path, {"first": first})
    assert gateway.post(PROMPT).headers[CACHE_HEADER] == "miss"
    again = gateway.post(SIMILAR)
    assert again.headers[CACHE_HEADER] == "miss"
    assert len(first.requests) == 2
    assert gateway.stored() == 0


def test_a_502_stores_nothing(tmp_path: Path) -> None:
    first = ScriptedProvider("first", error=ProviderError("upstream_status", 400))
    gateway = CacheGateway(tmp_path, {"first": first})
    assert gateway.post(PROMPT).status_code == 502
    assert gateway.stored() == 0
    working = ScriptedProvider("first")
    gateway.app.state.providers["first"] = working
    again = gateway.post(SIMILAR)
    assert (again.status_code, again.headers[CACHE_HEADER]) == (200, "miss")
    assert len(working.requests) == 1


# Criterion 6: an embedder failure.


def test_an_embedder_failure_is_a_skip_served_by_the_provider_and_stores_nothing(
    tmp_path: Path,
) -> None:
    embedder = FakeEmbedder(VECTORS, error=EmbeddingError("connection", None))
    providers = scripted()
    gateway = CacheGateway(tmp_path, providers, embedder=embedder)
    skipped = gateway.post(PROMPT)
    assert (skipped.status_code, skipped.headers[CACHE_HEADER]) == (200, "skip")
    assert routing_values(skipped) == ("first", "0")
    assert gateway.stored() == 0
    embedder.error = None
    assert gateway.post(SIMILAR).headers[CACHE_HEADER] == "miss"
    assert len(providers["first"].requests) == 2
    hit = gateway.post(PROMPT)
    assert hit.headers[CACHE_HEADER] == "hit"
    # `first` is not the route's last target, so the stored provider is not a route position.
    assert routing_values(hit) == ("first", "0")
    assert len(providers["first"].requests) == 2


# Criterion 7: the header only on 200.


def bad_request(gateway: CacheGateway) -> httpx.Response:
    response: httpx.Response = gateway.client.post(URL, json={"model": "pair", "messages": []})
    return response


def unauthorized(gateway: CacheGateway) -> httpx.Response:
    response: httpx.Response = TestClient(gateway.app).post(URL, json=payload(PROMPT))
    return response


def not_found(gateway: CacheGateway) -> httpx.Response:
    return gateway.post(PROMPT, model="no-such-model")


def rate_limited_cached(gateway: CacheGateway) -> httpx.Response:
    gateway.post(PROMPT)
    asyncio.run(gateway.app.state.limiter.reserve(CALLER_ID, 960))
    return gateway.post(SIMILAR)


def bad_gateway(gateway: CacheGateway) -> httpx.Response:
    gateway.app.state.providers["first"] = ScriptedProvider(
        "first", error=ProviderError("upstream_status", 400)
    )
    return gateway.post(PROMPT)


@pytest.mark.parametrize("cache", [True, False], ids=["cache-on", "cache-off"])
@pytest.mark.parametrize(
    ("status", "send"),
    [
        (400, bad_request),
        (401, unauthorized),
        (404, not_found),
        (429, rate_limited_cached),
        (502, bad_gateway),
    ],
    ids=["400", "401", "404", "429", "502"],
)
def test_the_cache_header_is_absent_on_every_status_but_200(
    tmp_path: Path, cache: bool, status: int, send: Callable[[CacheGateway], httpx.Response]
) -> None:
    gateway = CacheGateway(tmp_path, scripted(), cache=cache)
    response = send(gateway)
    assert response.status_code == status
    assert CACHE_HEADER not in response.headers


# Criterion 8: entries are per caller.


def test_another_caller_sending_the_same_prompt_gets_a_miss(tmp_path: Path) -> None:
    providers = scripted()
    gateway = CacheGateway(tmp_path, providers)
    assert gateway.post(PROMPT).headers[CACHE_HEADER] == "miss"
    other = gateway.client.post(URL, json=payload(PROMPT), headers=OTHER_HEADERS)
    assert (other.status_code, other.headers[CACHE_HEADER]) == (200, "miss")
    assert len(providers["first"].requests) == 2
    assert gateway.post(SIMILAR).headers[CACHE_HEADER] == "hit"
    assert len(providers["first"].requests) == 2


# Criterion 9: the whole app with the Ollama embedder.


def test_an_ollama_route_with_the_ollama_embedder_serves_a_miss_then_a_hit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    CountingIdSource.instances = []
    monkeypatch.setattr("app.main.UuidIdSource", CountingIdSource)
    upstream = OllamaUpstream()
    application, clock = ollama_app(tmp_path, upstream, cache=True)
    with TestClient(application, headers=AUTH_HEADERS) as client:
        miss = client.post(URL, json=payload(PROMPT, "solo"))
        clock.advance(7.5)
        hit = client.post(URL, json=payload(SIMILAR, "solo"))
    assert [miss.headers[CACHE_HEADER], hit.headers[CACHE_HEADER]] == ["miss", "hit"]
    assert routing_values(miss) == routing_values(hit) == ("local", "0")
    assert upstream.paths() == [
        ("embed.test", "/api/embed"),
        ("ollama.test", "/api/chat"),
        ("embed.test", "/api/embed"),
    ]
    embeds = [body for _, path, body in upstream.seen if path == "/api/embed"]
    assert embeds == [
        {"model": "m", "input": PROMPT, "truncate": False},
        {"model": "m", "input": SIMILAR, "truncate": False},
    ]
    stored = miss.json()
    assert (stored["id"], stored["created"]) == ("chatcmpl-counted-1", 1000)
    assert hit.json() == {**stored, "id": "chatcmpl-counted-2", "created": 1007}


# Beyond the criteria.


def test_a_request_not_ending_in_a_user_message_is_a_skip_with_the_cache_on(
    tmp_path: Path,
) -> None:
    gateway = CacheGateway(tmp_path, scripted())
    messages = [
        {"role": "user", "content": PROMPT},
        {"role": "assistant", "content": "earlier reply"},
    ]
    response = gateway.client.post(URL, json={"model": "pair", "messages": messages})
    assert (response.status_code, response.headers[CACHE_HEADER]) == (200, "skip")
    assert gateway.embedded == []


def test_a_lookup_error_other_than_an_embedding_error_is_a_500_charged_as_reserved(
    tmp_path: Path,
) -> None:
    providers = scripted()
    embedder = FakeEmbedder(VECTORS, error=RuntimeError("embedder bug"))
    gateway = CacheGateway(tmp_path, providers, embedder=embedder)
    with pytest.raises(RuntimeError, match="embedder bug"):
        gateway.post(PROMPT)
    assert gateway.recorder.calls == [("reserve", CALLER_ID, 11)]
    assert all(provider.requests == [] for provider in providers.values())


def test_a_settle_error_after_a_miss_stores_nothing(tmp_path: Path) -> None:
    providers = scripted()
    gateway = CacheGateway(tmp_path, providers)
    inner = gateway.app.state.limiter
    gateway.app.state.limiter = RecordingLimiter(inner, settle_error=RuntimeError("settle failed"))
    with pytest.raises(RuntimeError, match="settle failed"):
        gateway.post(PROMPT)
    gateway.app.state.limiter = inner
    assert gateway.stored() == 0
    assert gateway.post(SIMILAR).headers[CACHE_HEADER] == "miss"
    assert len(providers["first"].requests) == 2
