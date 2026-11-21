"""The Ollama embedder (ADR-0015, T-301): the request, the reply checks and the failure kinds.

Every test runs the embedder on an `httpx.MockTransport`: no network, no sleeping.
"""

import asyncio
import json
import traceback
from array import array
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any

import httpx
import pytest

from app.cache.embedder import Embedder, EmbeddingError
from app.cache.ollama_embedder import OllamaEmbedder
from app.providers.errors import ProviderErrorKind

Handler = Callable[[httpx.Request], httpx.Response]
MODEL = "all-minilm"
BODY_SENTINEL = "SENTINEL-body-71d3"
TEXT_SENTINEL = "SENTINEL-text-0b9e"
PASSWORD_SENTINEL = "SENTINEL-password-5a42"
HOST_SENTINEL = "sentinel-host-c8f1.test"
HUGE_INTEGER = "1" + "0" * 399  # 400 digits: float() raises OverflowError
DEFAULT_CAP_BYTES = 1_048_576


def reply(vectors: Any) -> dict[str, Any]:
    """An /api/embed reply with Ollama's extra fields."""
    return {
        "model": MODEL,
        "embeddings": vectors,
        "total_duration": 14143917,
        "load_duration": 1019500,
        "prompt_eval_count": 8,
    }


def json_handler(body: Any, status: int = 200) -> Handler:
    return lambda request: httpx.Response(status, json=body)


def raw_handler(content: bytes, status: int = 200) -> Handler:
    return lambda request: httpx.Response(status, content=content)


def raw_vector(literals: str) -> bytes:
    """A reply whose one vector is the given JSON text (Python's parser accepts NaN, Infinity)."""
    return b'{"embeddings": [[' + literals.encode("ascii") + b"]]}"


def padded(size_bytes: int) -> bytes:
    """The valid reply `[[3, 4]]` padded with JSON whitespace to exactly `size_bytes`."""
    body = json.dumps(reply([[3, 4]])).encode("utf-8")
    assert len(body) <= size_bytes
    return body + b" " * (size_bytes - len(body))


def raises(exception: Exception) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exception

    return handler


def failing_mid_body(exception: Exception) -> Handler:
    async def body() -> AsyncIterator[bytes]:
        yield b'{"embeddings": '
        raise exception

    return lambda request: httpx.Response(200, content=body())


class Calls:
    """Serves the handlers in turn (the last one repeats) and records every request."""

    def __init__(self, handlers: Sequence[Handler]) -> None:
        self.handlers = list(handlers)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        handler = self.handlers[min(len(self.requests), len(self.handlers) - 1)]
        self.requests.append(request)
        return handler(request)


def run(
    handlers: Handler | Sequence[Handler],
    texts: Sequence[str] = ("hello",),
    *,
    base_url: str = "http://ollama.test",
    max_response_bytes: int | None = None,
) -> tuple[list[array[float] | EmbeddingError], Calls]:
    """Embed each text in turn on one embedder; the vectors or errors, and the requests."""
    calls = Calls([handlers] if callable(handlers) else handlers)
    client = httpx.AsyncClient(transport=httpx.MockTransport(calls), base_url=base_url)
    if max_response_bytes is None:
        embedder = OllamaEmbedder(client, MODEL)
    else:
        embedder = OllamaEmbedder(client, MODEL, max_response_bytes=max_response_bytes)

    async def go() -> list[array[float] | EmbeddingError]:
        results: list[array[float] | EmbeddingError] = []
        try:
            for text in texts:
                try:
                    results.append(await embedder.embed(text))
                except EmbeddingError as error:
                    results.append(error)
        finally:
            await client.aclose()
        return results

    return asyncio.run(go()), calls


def vector_for(handler: Handler, **kwargs: Any) -> array[float]:
    (result,), _ = run(handler, **kwargs)
    assert isinstance(result, array), result
    return result


def error_for(handler: Handler, **kwargs: Any) -> EmbeddingError:
    (result,), _ = run(handler, **kwargs)
    assert isinstance(result, EmbeddingError), result
    return result


# Identity and criterion 2: the request.


def test_identity_is_ollama_and_the_model() -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(json_handler(reply([[1]]))))
    embedder: Embedder = OllamaEmbedder(client, "bge-m3")
    assert embedder.identity == "ollama:bge-m3"
    asyncio.run(client.aclose())


def test_each_call_is_one_post_to_api_embed_with_exactly_model_input_and_truncate_false() -> None:
    results, calls = run(json_handler(reply([[3, 4]])), texts=["héllo", "second text"])
    assert all(isinstance(result, array) for result in results)
    assert len(calls.requests) == 2
    for request, text in zip(calls.requests, ["héllo", "second text"], strict=True):
        assert request.method == "POST"
        assert request.url.path == "/api/embed"
        body = json.loads(request.content)
        assert body == {"model": MODEL, "input": text, "truncate": False}
        assert body["truncate"] is False


def test_the_base_url_path_prefix_is_kept() -> None:
    _, calls = run(json_handler(reply([[1]])), base_url="http://h:1/prefix")
    assert calls.requests[0].url.path == "/prefix/api/embed"


# Criterion 3: the reply.


@pytest.mark.parametrize("status", [200, 201])
def test_a_reply_is_normalised_again(status: int) -> None:
    vector = vector_for(json_handler(reply([[3, 4]]), status))
    assert vector.typecode == "d"
    assert list(vector) == [0.6, 0.8]


def test_an_already_normalised_reply_keeps_its_values_and_floats_are_accepted() -> None:
    assert list(vector_for(json_handler(reply([[0.6, -0.8]])))) == [0.6, -0.8]


BAD_REPLIES: dict[str, bytes] = {
    "top-level-list": json.dumps([[3, 4]]).encode(),
    "top-level-string": json.dumps("x").encode(),
    "top-level-null": b"null",
    "top-level-number": b"5",
    "no-embeddings": json.dumps({"model": MODEL}).encode(),
    "embeddings-null": json.dumps(reply(None)).encode(),
    "embeddings-dict": json.dumps(reply({"0": [3, 4]})).encode(),
    "embeddings-string": json.dumps(reply("3,4")).encode(),
    "embeddings-empty": json.dumps(reply([])).encode(),
    "two-vectors": json.dumps(reply([[3, 4], [3, 4]])).encode(),
    "vector-a-number": json.dumps(reply([3])).encode(),
    "empty-vector": json.dumps(reply([[]])).encode(),
    "element-true": json.dumps(reply([[3, True]])).encode(),
    "element-false": json.dumps(reply([[3, False]])).encode(),
    "element-string": json.dumps(reply([[3, "4"]])).encode(),
    "element-null": json.dumps(reply([[3, None]])).encode(),
    "element-list": json.dumps(reply([[3, [4]]])).encode(),
    "nan": raw_vector("3, NaN"),
    "infinity": raw_vector("3, Infinity"),
    "negative-infinity": raw_vector("-Infinity, 3"),
    "float-overflow-literal": raw_vector("3, 1e400"),
    "huge-integer": raw_vector("3, " + HUGE_INTEGER),
    "huge-negative-integer": raw_vector("-" + HUGE_INTEGER + ", 3"),
    "zero-vector": json.dumps(reply([[0, 0]])).encode(),
    "signed-zero-vector": json.dumps(reply([[0.0, -0.0]])).encode(),
    "norm-overflows": json.dumps(reply([[1e308, 1e308]])).encode(),
    "invalid-json": b"{not json",
    "empty-body": b"",
}


@pytest.mark.parametrize("status", [200, 201])
@pytest.mark.parametrize("name", list(BAD_REPLIES))
def test_a_reply_that_breaks_the_rules_is_a_bad_response_with_its_status(
    name: str, status: int
) -> None:
    error = error_for(raw_handler(BAD_REPLIES[name], status))
    assert type(error) is EmbeddingError
    assert (error.kind, error.status_code) == ("bad_response", status)
    assert str(error) == f"embedding failed: bad_response (HTTP {status})"


def test_a_later_reply_must_have_the_length_of_the_first() -> None:
    handlers = [
        json_handler(reply([[1, 2, 2]])),
        json_handler(reply([[3, 4]])),
        json_handler(reply([[3, 4]])),
        json_handler(reply([[2, 1, 2]])),
        json_handler(reply([[1, 1, 1, 1]])),
    ]
    results, _ = run(handlers, texts=["a", "b", "c", "d", "e"])
    assert [isinstance(result, array) for result in results] == [True, False, False, True, False]
    for result in results[1:3] + results[4:]:
        assert isinstance(result, EmbeddingError)
        assert (result.kind, result.status_code) == ("bad_response", 200)


def test_a_rejected_first_reply_does_not_set_the_length() -> None:
    handlers = [
        json_handler(reply([[0, 0]])),
        json_handler(reply([[1, 2, 2]])),
        json_handler(reply([[2, 2, 1]])),
        json_handler(reply([[3, 4]])),
    ]
    results, _ = run(handlers, texts=["a", "b", "c", "d"])
    assert [isinstance(result, array) for result in results] == [False, True, True, False]


@pytest.mark.parametrize(
    ("size_bytes", "served"),
    [(DEFAULT_CAP_BYTES, True), (DEFAULT_CAP_BYTES + 1, False)],
    ids=["exactly-the-cap", "the-cap-plus-1"],
)
def test_the_default_cap_reads_exactly_1_048_576_bytes_and_rejects_one_more(
    size_bytes: int, served: bool
) -> None:
    (result,), _ = run(raw_handler(padded(size_bytes)))
    if served:
        assert isinstance(result, array), result
        assert list(result) == [0.6, 0.8]
    else:
        assert isinstance(result, EmbeddingError), result
        assert (result.kind, result.status_code) == ("bad_response", 200)


@pytest.mark.parametrize(
    ("size_bytes", "served"), [(1_024, True), (1_025, False)], ids=["limit", "limit-plus-1"]
)
def test_a_configured_max_response_bytes_is_used(size_bytes: int, served: bool) -> None:
    (result,), _ = run(raw_handler(padded(size_bytes)), max_response_bytes=1_024)
    assert isinstance(result, array) is served, result


# Criterion 4: failures.


@pytest.mark.parametrize(
    ("handler", "kind", "status"),
    [
        (raises(httpx.ConnectError("c")), "connection", None),
        (raises(httpx.ConnectTimeout("c")), "timeout", None),
        (raises(httpx.ReadTimeout("r")), "timeout", None),
        (json_handler({"error": "x"}, 429), "rate_limited", 429),
        (
            json_handler({"error": "the input length exceeds the context length"}, 400),
            "upstream_status",
            400,
        ),
        (json_handler({"error": "model 'x' not found"}, 404), "upstream_status", 404),
        (json_handler({"error": "x"}, 500), "upstream_status", 500),
    ],
    ids=["connect-error", "connect-timeout", "read-timeout", "429", "400", "404", "500"],
)
def test_failures_map_to_their_kind_and_status(
    handler: Handler, kind: ProviderErrorKind, status: int | None
) -> None:
    (result,), calls = run(handler)
    assert type(result) is EmbeddingError, result
    assert (result.kind, result.status_code) == (kind, status)
    expected = f"embedding failed: {kind}"
    assert str(result) == (expected if status is None else f"{expected} (HTTP {status})")
    assert len(calls.requests) == 1


OVERSIZE_LIMIT_BYTES = 256

LEAKY_FAILURES: dict[str, tuple[Handler, int | None]] = {
    "connect-error": (raises(httpx.ConnectError(BODY_SENTINEL)), None),
    "read-timeout-mid-body": (failing_mid_body(httpx.ReadTimeout(BODY_SENTINEL)), None),
    "429": (raw_handler(BODY_SENTINEL.encode(), 429), None),
    "400": (raw_handler(BODY_SENTINEL.encode(), 400), None),
    "404": (raw_handler(BODY_SENTINEL.encode(), 404), None),
    "500": (raw_handler(BODY_SENTINEL.encode(), 500), None),
    "invalid-json": (raw_handler(b"{" + BODY_SENTINEL.encode()), None),
    "error-object": (json_handler({"error": BODY_SENTINEL}), None),
    "string-element": (json_handler(reply([[BODY_SENTINEL]])), None),
    "huge-integer": (raw_handler(raw_vector(HUGE_INTEGER)), None),
    "nan": (raw_handler(raw_vector("NaN, 1")), None),
    "zero-vector": (json_handler(reply([[0, 0]])), None),
    "body-above-the-limit": (
        raw_handler(b'"' + BODY_SENTINEL.encode() * OVERSIZE_LIMIT_BYTES + b'"'),
        OVERSIZE_LIMIT_BYTES,
    ),
}


@pytest.mark.parametrize("name", list(LEAKY_FAILURES))
def test_no_embedding_error_holds_the_body_the_text_or_the_url_or_has_a_context(
    name: str,
) -> None:
    handler, limit = LEAKY_FAILURES[name]
    error = error_for(
        handler,
        texts=[TEXT_SENTINEL],
        base_url=f"http://user:{PASSWORD_SENTINEL}@{HOST_SENTINEL}:11434",
        max_response_bytes=limit,
    )
    text = str(error) + repr(error) + "".join(traceback.format_exception(error))
    for sentinel in (BODY_SENTINEL, TEXT_SENTINEL, PASSWORD_SENTINEL, HOST_SENTINEL):
        assert sentinel not in text
    assert error.__context__ is None
    assert error.__cause__ is None


def test_an_error_that_is_not_an_httpx_error_propagates_unchanged() -> None:
    boom = RuntimeError("boom")
    with pytest.raises(RuntimeError) as raised:
        run(raises(boom))
    assert raised.value is boom
