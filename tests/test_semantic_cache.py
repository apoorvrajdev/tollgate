"""The in-memory semantic cache: partition, lookup, store, expiry and eviction (ADR-0014, T-303).

Vectors come from `FakeEmbedder` and are dyadic where a similarity is compared, so every dot
product is exact. The clock starts at 100.0 and moves only by sums that are exact in binary.
"""

import asyncio
import hashlib
import math
from collections.abc import Coroutine, Mapping
from typing import Any

import pytest

from app.api.models import ChatMessage, ChatRequest, ChatResponse, Usage
from app.cache.embedder import EmbeddingError
from app.cache.semantic import (
    MAX_STORED_BYTES,
    Hit,
    InMemorySemanticCache,
    LookupResult,
    Miss,
    Skip,
    partition_key,
)
from tests.fakes import FakeClock, FakeEmbedder

LONE_SURROGATE = chr(0xD800)
CALLER = "caller-a"
OTHER_CALLER = "caller-b"
START_SECONDS = 100.0

# The canonical form of PINNED_REQUEST, written by hand from ADR-0014: sorted keys, no whitespace,
# non-ASCII escaped, the last message without its content. Its digest was computed from this text.
PINNED_CANONICAL = (
    '{"caller_id":"caller-1","embedder":"fake:v1","request":{"max_completion_tokens":10,'
    '"max_tokens":20,"messages":[{"content":"Be brief","name":"sys","role":"system"},'
    '{"content":"Caf\\u00e9?","name":"ann","role":"user"},{"name":"bob","role":"user"}],'
    '"model":"gpt-x","n":1,"stream":false,"temperature":0.5,"user":"u-1"}}'
)
PINNED_KEY = "fd76e9c003f5a43931a8c430f5f9de04478d79548f45343ad71a06ebb1465ef9"
PINNED_REQUEST = ChatRequest(
    model="gpt-x",
    messages=[
        ChatMessage(role="system", content="Be brief", name="sys"),
        ChatMessage(role="user", content="Café?", name="ann"),
        ChatMessage(role="user", content="Anything at all", name="bob"),
    ],
    max_completion_tokens=10,
    max_tokens=20,
    temperature=0.5,
    n=1,
    stream=False,
    user="u-1",
)


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


def chat(
    last: str = "q", *, earlier: list[ChatMessage] | None = None, **fields: Any
) -> ChatRequest:
    messages = [*(earlier or []), ChatMessage(role="user", content=last)]
    return ChatRequest(model=fields.pop("model", "m"), messages=messages, **fields)


def answer(content: str = "a", finish_reasons: tuple[str, ...] = ("stop",)) -> ChatResponse:
    return ChatResponse.model_validate(
        {
            "id": "chatcmpl-1",
            "object": "chat.completion",
            "created": 1,
            "model": "m",
            "choices": [
                {
                    "index": i,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": r,
                }
                for i, r in enumerate(finish_reasons)
            ],
            "usage": Usage(prompt_tokens=1, completion_tokens=2, total_tokens=3).model_dump(),
        }
    )


def make_cache(
    vectors: Mapping[str, tuple[float, ...]],
    *,
    threshold: float = 0.9,
    ttl_seconds: int = 60,
    max_entries: int = 10,
) -> tuple[InMemorySemanticCache, FakeClock, FakeEmbedder]:
    embedder = FakeEmbedder(vectors)
    clock = FakeClock(START_SECONDS)
    cache = InMemorySemanticCache(
        embedder,
        clock,
        similarity_threshold=threshold,
        ttl_seconds=ttl_seconds,
        max_entries=max_entries,
    )
    return cache, clock, embedder


def look(
    cache: InMemorySemanticCache, text: str, caller: str = CALLER, **fields: Any
) -> LookupResult:
    return run(cache.lookup(caller, chat(text, **fields)))


def remember(cache: InMemorySemanticCache, text: str, *, provider: str | None = None) -> None:
    result = look(cache, text)
    assert isinstance(result, Miss)
    assert cache.store(result.ticket, answer(f"answer to {text}"), provider or text) is True


def hit_provider(cache: InMemorySemanticCache, text: str) -> str | None:
    result = look(cache, text)
    return result.provider_name if isinstance(result, Hit) else None


# --- Partition (AC1) ---


def test_requests_differing_only_in_the_last_content_share_a_key() -> None:
    assert partition_key(CALLER, chat("one"), "fake:v1") == partition_key(
        CALLER, chat("two"), "fake:v1"
    )


def _earlier(
    role: str = "system", content: str = "s", name: str | None = None
) -> list[ChatMessage]:
    return [ChatMessage.model_validate({"role": role, "content": content, "name": name})]


@pytest.mark.parametrize(
    ("caller", "request_", "identity"),
    [
        pytest.param(OTHER_CALLER, chat(earlier=_earlier()), "fake:v1", id="caller-id"),
        pytest.param(CALLER, chat(earlier=_earlier(), model="other"), "fake:v1", id="model"),
        pytest.param(
            CALLER,
            chat(earlier=_earlier(), max_completion_tokens=5),
            "fake:v1",
            id="max-completion",
        ),
        pytest.param(CALLER, chat(earlier=_earlier(), max_tokens=5), "fake:v1", id="max-tokens"),
        pytest.param(
            CALLER, chat(earlier=_earlier(), temperature=0.5), "fake:v1", id="temperature"
        ),
        pytest.param(CALLER, chat(earlier=_earlier(), n=1), "fake:v1", id="n-1-vs-absent"),
        pytest.param(CALLER, chat(earlier=_earlier(), stream=False), "fake:v1", id="stream-false"),
        pytest.param(CALLER, chat(earlier=_earlier(), user="u"), "fake:v1", id="user"),
        pytest.param(
            CALLER, chat(earlier=_earlier(role="assistant")), "fake:v1", id="earlier-role"
        ),
        pytest.param(CALLER, chat(earlier=_earlier(content="t")), "fake:v1", id="earlier-content"),
        pytest.param(CALLER, chat(earlier=_earlier(name="x")), "fake:v1", id="earlier-name"),
        pytest.param(
            CALLER,
            ChatRequest(
                model="m", messages=[*_earlier(), ChatMessage(role="user", content="q", name="x")]
            ),
            "fake:v1",
            id="last-name",
        ),
        pytest.param(CALLER, chat(earlier=_earlier()), "fake:v2", id="embedder-identity"),
    ],
)
def test_a_change_in_one_field_gives_another_key(
    caller: str, request_: ChatRequest, identity: str
) -> None:
    base = partition_key(CALLER, chat(earlier=_earlier()), "fake:v1")
    assert partition_key(caller, request_, identity) != base


def test_one_fixed_request_gives_the_pinned_key() -> None:
    assert hashlib.sha256(PINNED_CANONICAL.encode("ascii")).hexdigest() == PINNED_KEY
    assert partition_key("caller-1", PINNED_REQUEST, "fake:v1") == PINNED_KEY


@pytest.mark.parametrize(
    "request_",
    [
        # The route accepts a lone surrogate in `user` and in a message's `name`.
        pytest.param(chat(earlier=_earlier(), user="u" + LONE_SURROGATE), id="user"),
        pytest.param(chat(earlier=_earlier(name="n" + LONE_SURROGATE)), id="earlier-name"),
        # Validation rejects one in `model` (its min_length decodes the text), so the route never
        # passes one; model_copy skips validation to prove the key would not raise.
        pytest.param(
            chat(earlier=_earlier()).model_copy(update={"model": "m" + LONE_SURROGATE}), id="model"
        ),
    ],
)
def test_a_lone_surrogate_gives_a_key_without_raising(request_: ChatRequest) -> None:
    key = partition_key(CALLER, request_, "fake:v1")
    assert len(key) == 64
    assert set(key) <= set("0123456789abcdef")


# --- Eligibility (AC2) ---


@pytest.mark.parametrize("last_role", ["assistant", "system"])
def test_a_request_not_ending_with_a_user_message_skips_without_embedding(last_role: str) -> None:
    cache, _, embedder = make_cache({"q": (1.0, 0.0)})
    request = ChatRequest.model_validate(
        {
            "model": "m",
            "messages": [{"role": "user", "content": "q"}, {"role": last_role, "content": "q"}],
        }
    )
    assert run(cache.lookup(CALLER, request)) == Skip("not_eligible")
    assert embedder.calls == []


@pytest.mark.parametrize("first_role", ["system", "assistant"])
def test_a_request_ending_with_a_user_message_is_looked_up(first_role: str) -> None:
    cache, _, embedder = make_cache({"q": (1.0, 0.0)})
    assert isinstance(look(cache, "q", earlier=_earlier(role=first_role, content="first")), Miss)
    assert embedder.calls == ["q"]


# --- Threshold and choice (AC3, AC4) ---


def test_a_similarity_equal_to_the_threshold_hits_and_reports_it() -> None:
    cache, _, _ = make_cache(
        {"stored": (0.75, math.sqrt(0.4375)), "query": (1.0, 0.0)}, threshold=0.75
    )
    remember(cache, "stored")
    result = look(cache, "query")
    assert isinstance(result, Hit)
    assert result.similarity == 0.75
    assert result.provider_name == "stored"
    assert result.response == answer("answer to stored")


def test_a_similarity_just_below_the_threshold_misses() -> None:
    below = 0.7499999999999999
    assert below == math.nextafter(0.75, 0.0)
    cache, _, _ = make_cache({"stored": (below, 0.5), "query": (1.0, 0.0)}, threshold=0.75)
    remember(cache, "stored")
    assert isinstance(look(cache, "query"), Miss)


@pytest.mark.parametrize(
    "order", [("a", "b"), ("b", "a")], ids=["more-similar-last", "more-similar-first"]
)
def test_the_more_similar_of_two_passing_entries_wins(order: tuple[str, str]) -> None:
    # a scores 0.75, b 0.875 against the query; a and b score 0.40625 against each other.
    cache, _, _ = make_cache(
        {"a": (0.75, 0.5), "b": (0.875, -0.5), "query": (1.0, 0.0)}, threshold=0.5
    )
    for text in order:
        remember(cache, text)
    result = look(cache, "query")
    assert isinstance(result, Hit)
    assert (result.provider_name, result.similarity) == ("b", 0.875)


def test_at_equal_similarity_the_more_recently_stored_entry_wins() -> None:
    # Both score 0.75 against "x"; "y" hits only a, so a is the more recently used of the two.
    cache, _, _ = make_cache(
        {"a": (0.75, 0.625), "b": (0.75, -0.625), "x": (1.0, 0.0), "y": (0.0, 1.0)}, threshold=0.5
    )
    remember(cache, "a")
    remember(cache, "b")
    assert hit_provider(cache, "y") == "a"
    result = look(cache, "x")
    assert isinstance(result, Hit)
    assert (result.provider_name, result.similarity) == ("b", 0.75)


@pytest.mark.parametrize(
    ("caller", "fields"),
    [(OTHER_CALLER, {}), (CALLER, {"model": "other"})],
    ids=["caller", "model"],
)
def test_an_identical_vector_in_another_partition_never_hits(
    caller: str, fields: dict[str, Any]
) -> None:
    cache, _, _ = make_cache({"q": (1.0, 0.0)})
    remember(cache, "q")
    assert isinstance(look(cache, "q", caller, **fields), Miss)
    assert isinstance(look(cache, "q"), Hit)


def test_a_miss_ticket_holds_the_partition_key_and_the_vector() -> None:
    cache, _, _ = make_cache({"q": (0.5, 0.25)})
    result = look(cache, "q", user="u")
    assert isinstance(result, Miss)
    assert result.ticket.partition_key == partition_key(CALLER, chat("q", user="u"), "fake:v1")
    assert result.ticket.vector.typecode == "d"
    assert list(result.ticket.vector) == [0.5, 0.25]


# --- Expiry (AC6) ---


def test_an_entry_hits_just_before_its_expiry() -> None:
    cache, clock, _ = make_cache({"q": (1.0, 0.0)})
    remember(cache, "q")
    clock.advance(59.999)
    assert isinstance(look(cache, "q"), Hit)


def test_an_entry_misses_at_exactly_its_expiry() -> None:
    cache, clock, _ = make_cache({"q": (1.0, 0.0)})
    remember(cache, "q")
    clock.advance(60)
    assert clock.now_seconds() == 160.0
    assert isinstance(look(cache, "q"), Miss)


def test_a_hit_does_not_extend_the_entry_life() -> None:
    cache, clock, _ = make_cache({"q": (1.0, 0.0)})
    remember(cache, "q")
    clock.advance(30)
    assert isinstance(look(cache, "q"), Hit)
    clock.advance(30)
    assert isinstance(look(cache, "q"), Miss)


# --- Eviction (AC7) ---

AXES = {"a": (1.0, 0.0, 0.0), "b": (0.0, 1.0, 0.0), "c": (0.0, 0.0, 1.0)}


def test_when_full_an_expired_entry_is_evicted_before_a_more_recently_used_live_one() -> None:
    cache, clock, _ = make_cache(AXES, max_entries=2)
    remember(cache, "a")  # expires at 160
    clock.advance(10)
    remember(cache, "b")  # expires at 170
    clock.advance(10)
    assert hit_provider(cache, "a") == "a"  # a is now the most recently used
    clock.advance(40)
    assert clock.now_seconds() == 160.0
    remember(cache, "c")
    assert len(cache) == 2
    assert hit_provider(cache, "b") == "b"
    assert hit_provider(cache, "c") == "c"


def test_when_full_the_least_recently_used_entry_is_evicted() -> None:
    cache, _, _ = make_cache(AXES, ttl_seconds=3600, max_entries=2)
    remember(cache, "a")
    remember(cache, "b")
    assert hit_provider(cache, "a") == "a"
    remember(cache, "c")
    assert len(cache) == 2
    assert hit_provider(cache, "b") is None
    assert hit_provider(cache, "a") == "a"
    assert hit_provider(cache, "c") == "c"


def test_the_entry_count_never_passes_the_maximum() -> None:
    texts = [f"t{i}" for i in range(6)]
    vectors = {
        text: tuple(1.0 if j == i else 0.0 for j in range(6)) for i, text in enumerate(texts)
    }
    cache, _, _ = make_cache(vectors, ttl_seconds=3600, max_entries=3)
    for stored, text in enumerate(texts, start=1):
        remember(cache, text)
        assert len(cache) == min(stored, 3)
    assert [hit_provider(cache, text) for text in texts] == [None, None, None, "t3", "t4", "t5"]


def test_evicting_the_last_entry_of_a_partition_drops_the_partition() -> None:
    cache, _, _ = make_cache({"q": (1.0, 0.0)}, max_entries=1)
    remember(cache, "q")
    other = look(cache, "q", OTHER_CALLER)
    assert isinstance(other, Miss)
    assert cache.store(other.ticket, answer(), "p") is True
    # Private access on purpose: an empty partition is invisible through the public API, but
    # keeping it would leak one key per abandoned partition.
    assert list(cache._partitions) == [other.ticket.partition_key]


def test_a_stored_vector_is_a_copy_not_the_ticket_vector() -> None:
    cache, _, _ = make_cache({"q": (1.0, 0.0)})
    miss = look(cache, "q")
    assert isinstance(miss, Miss)
    assert cache.store(miss.ticket, answer(), "p") is True
    miss.ticket.vector[0] = 0.0
    hit = look(cache, "q")
    assert isinstance(hit, Hit)
    assert hit.similarity == 1.0


# --- What is stored (AC8) ---


@pytest.mark.parametrize("reason", ["length", "content_filter"])
def test_a_length_or_content_filter_answer_is_not_stored(reason: str) -> None:
    cache, _, _ = make_cache({"q": (1.0, 0.0)})
    miss = look(cache, "q")
    assert isinstance(miss, Miss)
    assert cache.store(miss.ticket, answer(finish_reasons=(reason,)), "p") is False
    assert isinstance(look(cache, "q"), Miss)
    assert len(cache) == 0


@pytest.mark.parametrize("reasons", [(), ("stop", "stop")], ids=["zero", "two"])
def test_an_answer_without_exactly_one_choice_is_not_stored(reasons: tuple[str, ...]) -> None:
    cache, _, _ = make_cache({"q": (1.0, 0.0)})
    miss = look(cache, "q")
    assert isinstance(miss, Miss)
    assert cache.store(miss.ticket, answer(finish_reasons=reasons), "p") is False
    assert isinstance(look(cache, "q"), Miss)


def response_of_bytes(size_bytes: int) -> ChatResponse:
    base_bytes = len(answer("").model_dump_json().encode("utf-8"))
    pairs, odd = divmod(size_bytes - base_bytes, 2)
    response = answer("é" * pairs + "a" * odd)  # "é" is 2 bytes in UTF-8, 1 character
    body = response.model_dump_json()
    assert len(body.encode("utf-8")) == size_bytes
    assert len(body) <= MAX_STORED_BYTES  # counted in characters, it would always fit
    return response


def test_a_body_of_exactly_65536_utf8_bytes_is_stored() -> None:
    assert MAX_STORED_BYTES == 65_536
    cache, _, _ = make_cache({"q": (1.0, 0.0)})
    response = response_of_bytes(65_536)
    miss = look(cache, "q")
    assert isinstance(miss, Miss)
    assert cache.store(miss.ticket, response, "p") is True
    hit = look(cache, "q")
    assert isinstance(hit, Hit)
    assert hit.response == response


def test_a_body_of_65537_utf8_bytes_is_not_stored() -> None:
    cache, _, _ = make_cache({"q": (1.0, 0.0)})
    miss = look(cache, "q")
    assert isinstance(miss, Miss)
    assert cache.store(miss.ticket, response_of_bytes(65_537), "p") is False
    assert isinstance(look(cache, "q"), Miss)


def test_a_hit_returns_the_stored_bytes_not_a_later_change_to_the_model() -> None:
    cache, _, _ = make_cache({"q": (1.0, 0.0)})
    response = answer("original")
    miss = look(cache, "q")
    assert isinstance(miss, Miss)
    assert cache.store(miss.ticket, response, "p") is True
    response.choices[0].message.content = "changed"
    hit = look(cache, "q")
    assert isinstance(hit, Hit)
    assert hit.response == answer("original")
    assert hit.response is not response


# --- Embedder failures (AC9) ---


def test_an_embedding_error_gives_a_skip() -> None:
    cache, _, embedder = make_cache({})
    embedder.error = EmbeddingError("timeout", None)
    assert look(cache, "q") == Skip("embedder_failed")
    assert embedder.calls == ["q"]


def test_each_skip_reason_is_distinct_and_a_lookup_that_embeds_never_skips_as_not_eligible() -> (
    None
):
    assert Skip("not_eligible") != Skip("embedder_failed")
    assert Skip("embedder_failed").reason == "embedder_failed"
    cache, _, embedder = make_cache({})
    embedder.error = EmbeddingError("timeout", None)
    skipped = look(cache, "q")
    assert isinstance(skipped, Skip)
    assert skipped.reason != "not_eligible"


def test_any_other_embedder_exception_propagates() -> None:
    cache, _, embedder = make_cache({})
    embedder.error = RuntimeError("bug")
    with pytest.raises(RuntimeError, match="bug"):
        look(cache, "q")
