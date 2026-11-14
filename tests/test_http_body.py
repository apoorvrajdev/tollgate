"""The HTTP body helpers (ADR-0013, T-209, T-210): the capped reader and `post_json`.

The capped reader: the limit, where reading stops, and decoded counting. `post_json`: the request,
the status mapping, the failure mapping and the errors' contents. Every body is streamed through an
`httpx.MockTransport` from an async generator, so the test can see which chunks were asked for.
No network, no sleeping.
"""

import asyncio
import gzip
import json
import traceback
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any

import httpx
import pytest

from app.providers.errors import ProviderError
from app.providers.http_body import JsonReply, post_json, read_capped

Handler = Callable[[httpx.Request], httpx.Response]
LIMIT_BYTES = 1_024
BODY_SENTINEL = b"SENTINEL-body-5d2e"


def pattern(size_bytes: int, start: int = 0) -> bytes:
    """Bytes that differ along their length, so a dropped or reordered chunk changes the result."""
    return bytes((start + index) % 251 for index in range(size_bytes))


def split(data: bytes, chunk_bytes: int) -> list[bytes]:
    return [data[index : index + chunk_bytes] for index in range(0, len(data), chunk_bytes)]


def streamed(
    parts: Sequence[bytes],
    served: list[int],
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> Handler:
    """A handler whose body is `parts`, one chunk each; `served` records each chunk asked for."""

    async def body() -> AsyncIterator[bytes]:
        for index, part in enumerate(parts):
            served.append(index)
            yield part

    return lambda request: httpx.Response(status, headers=headers, content=body())


def read(handler: Handler, max_response_bytes: int = LIMIT_BYTES) -> bytes | ProviderError:
    async def go() -> bytes | ProviderError:
        transport = httpx.MockTransport(handler)
        async with (
            httpx.AsyncClient(transport=transport) as client,
            client.stream("POST", "http://provider.test/") as response,
        ):
            try:
                return await read_capped(response, max_response_bytes)
            except ProviderError as error:
                return error

    return asyncio.run(go())


def body_of(handler: Handler, max_response_bytes: int = LIMIT_BYTES) -> bytes:
    result = read(handler, max_response_bytes)
    assert isinstance(result, bytes), result
    return result


def error_of(handler: Handler, max_response_bytes: int = LIMIT_BYTES) -> ProviderError:
    result = read(handler, max_response_bytes)
    assert isinstance(result, ProviderError), result
    return result


# Criterion 1: the limit, and where reading stops.


@pytest.mark.parametrize(
    "parts",
    [
        pytest.param([pattern(400), pattern(400, 400), pattern(224, 800)], id="exactly-the-limit"),
        pytest.param([pattern(400), pattern(400, 400), pattern(223, 800)], id="the-limit-minus-1"),
        pytest.param([], id="zero-bytes"),
    ],
)
def test_a_body_up_to_the_limit_is_returned_unchanged(parts: list[bytes]) -> None:
    served: list[int] = []
    assert body_of(streamed(parts, served)) == b"".join(parts)
    assert served == list(range(len(parts)))


def test_a_body_one_byte_over_the_limit_is_a_bad_response_with_its_status() -> None:
    parts = [pattern(400), pattern(400, 400), pattern(225, 800)]
    error = error_of(streamed(parts, [], status=201))
    assert (error.kind, error.status_code, error.retryable) == ("bad_response", 201, False)
    assert str(error) == "provider failed: bad_response (HTTP 201)"


def test_the_total_spans_chunks_and_reading_stops_at_the_chunk_that_passes_it() -> None:
    # Every chunk is below the limit; the running total passes it in the third (1,200 bytes).
    parts = [pattern(400, 400 * index) for index in range(5)]
    served: list[int] = []
    error = error_of(streamed(parts, served))
    assert (error.kind, error.status_code) == ("bad_response", 200)
    assert served == [0, 1, 2]


def test_the_same_chunks_under_a_higher_limit_are_read_in_full() -> None:
    parts = [pattern(400, 400 * index) for index in range(5)]
    served: list[int] = []
    assert body_of(streamed(parts, served), max_response_bytes=2_000) == b"".join(parts)
    assert served == [0, 1, 2, 3, 4]


# Criterion 2: the count is of decoded bytes.

GZIP = {"content-encoding": "gzip"}


@pytest.mark.parametrize("chunk_bytes", [None, 16], ids=["one-chunk", "16-byte-chunks"])
def test_a_gzip_body_decoding_to_the_limit_plus_1_is_a_bad_response(
    chunk_bytes: int | None,
) -> None:
    compressed = gzip.compress(b"a" * (LIMIT_BYTES + 1))
    assert len(compressed) < LIMIT_BYTES
    parts = [compressed] if chunk_bytes is None else split(compressed, chunk_bytes)
    error = error_of(streamed(parts, [], headers=GZIP))
    assert (error.kind, error.status_code) == ("bad_response", 200)


@pytest.mark.parametrize("chunk_bytes", [None, 16], ids=["one-chunk", "16-byte-chunks"])
def test_a_gzip_body_decoding_to_exactly_the_limit_is_returned_decoded(
    chunk_bytes: int | None,
) -> None:
    decoded = b"a" * LIMIT_BYTES
    compressed = gzip.compress(decoded)
    assert len(compressed) < LIMIT_BYTES
    parts = [compressed] if chunk_bytes is None else split(compressed, chunk_bytes)
    assert body_of(streamed(parts, [], headers=GZIP)) == decoded


# The error never holds the body.


def test_an_oversized_body_error_holds_no_part_of_the_body() -> None:
    body = BODY_SENTINEL * (LIMIT_BYTES // len(BODY_SENTINEL) + 1)
    error = error_of(streamed([body], []))
    text = str(error) + repr(error) + "".join(traceback.format_exception(error))
    assert BODY_SENTINEL.decode("ascii") not in text
    assert error.__cause__ is None
    assert error.__context__ is None


# post_json (T-210). Failure groups run on a 201 reply as well as a 200, so a branch that raises
# with a fixed 200 is caught.

PATH = "/v1/chat"
REQUEST_BODY = {"model": "m", "messages": [{"role": "user", "content": "héllo"}]}
URL_SENTINEL = "SENTINEL-host-91ab"
HEADER_SENTINEL = "SENTINEL-header-77cd"
ERROR_SENTINEL = "SENTINEL-error-3f10"
REPLY_STATUSES = [200, 201]


def json_reply(status: int, content: bytes = b'{"ok": true}') -> Handler:
    return lambda request: httpx.Response(status, content=content)


def raising(error: Exception) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    return handler


def failing_mid_body(error: Exception, status: int = 200) -> Handler:
    """A reply whose status arrives and whose body fails after one chunk."""

    async def body() -> AsyncIterator[bytes]:
        yield b"{"
        raise error

    return lambda request: httpx.Response(status, content=body())


def post(
    handler: Handler,
    *,
    headers: dict[str, str] | None = None,
    path: str = PATH,
    max_response_bytes: int = LIMIT_BYTES,
    requests: list[httpx.Request] | None = None,
) -> JsonReply | ProviderError:
    seen = requests if requests is not None else []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    async def go() -> JsonReply | ProviderError:
        transport = httpx.MockTransport(recording)
        async with httpx.AsyncClient(
            transport=transport, base_url=f"http://{URL_SENTINEL}.test"
        ) as client:
            try:
                return await post_json(
                    client,
                    path,
                    body=REQUEST_BODY,
                    headers=headers,
                    max_response_bytes=max_response_bytes,
                )
            except ProviderError as error:
                return error

    return asyncio.run(go())


def reply_of(handler: Handler, **options: Any) -> JsonReply:
    result = post(handler, **options)
    assert isinstance(result, JsonReply), result
    return result


def failure_of(handler: Handler, **options: Any) -> ProviderError:
    result = post(handler, **options)
    assert isinstance(result, ProviderError), result
    return result


def test_post_json_sends_one_post_with_exactly_the_json_body_path_and_headers() -> None:
    requests: list[httpx.Request] = []
    sent = {"x-api-key": "k-123", "anthropic-version": "v9"}
    reply_of(json_reply(200), headers=sent, requests=requests)
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert request.url.path == PATH
    assert json.loads(request.content) == REQUEST_BODY
    assert request.headers["content-type"] == "application/json"
    for name, value in sent.items():
        assert request.headers[name] == value


def test_post_json_with_headers_none_sends_only_the_default_headers() -> None:
    requests: list[httpx.Request] = []
    reply_of(json_reply(200), headers=None, requests=requests)

    async def baseline() -> httpx.Request:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, content=b"{}")

        async with (
            httpx.AsyncClient(
                transport=httpx.MockTransport(handler), base_url=f"http://{URL_SENTINEL}.test"
            ) as client,
            client.stream("POST", PATH, json=REQUEST_BODY),
        ):
            pass
        return seen[0]

    expected = asyncio.run(baseline())
    assert dict(requests[0].headers) == dict(expected.headers)


@pytest.mark.parametrize("status", [200, 201, 299])
@pytest.mark.parametrize(
    ("content", "payload"),
    [
        (b'{"a": [1, 2, {"b": null}]}', {"a": [1, 2, {"b": None}]}),
        (b"[1, 2]", [1, 2]),
        (b"null", None),
        (b"7", 7),
        (b'{"s": "\\ud800"}', {"s": "\ud800"}),  # a lone surrogate is the adapter's check
    ],
    ids=["object", "list", "null", "number", "lone-surrogate-escape"],
)
def test_post_json_returns_the_parsed_payload_with_the_reply_status(
    status: int, content: bytes, payload: object
) -> None:
    reply = reply_of(json_reply(status, content))
    assert reply.payload == payload
    assert reply.status_code == status
    assert JsonReply._fields == ("payload", "status_code")


@pytest.mark.parametrize(
    ("status", "kind", "retryable"),
    [
        (429, "rate_limited", True),
        (500, "upstream_status", True),
        (529, "upstream_status", True),
        (400, "upstream_status", False),
        (404, "upstream_status", False),
        (302, "upstream_status", False),
    ],
)
def test_post_json_maps_a_non_2xx_status_without_reading_the_body(
    status: int, kind: str, retryable: bool
) -> None:
    served: list[int] = []
    error = failure_of(streamed([b"body"], served, status=status))
    assert (error.kind, error.status_code, error.retryable) == (kind, status, retryable)
    assert served == []


@pytest.mark.parametrize("status", [404, 429, 500, 503])
def test_post_json_does_not_turn_a_corrupt_non_2xx_body_into_a_bad_response(status: int) -> None:
    corrupt = streamed([b"not gzip at all"], [], status=status, headers=GZIP)
    error = failure_of(corrupt)
    assert error.kind in {"rate_limited", "upstream_status"}
    assert error.status_code == status


def test_post_json_does_not_follow_a_redirect() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/elsewhere":
            return httpx.Response(200, content=b'{"followed": true}')
        return httpx.Response(302, headers={"location": "/elsewhere"})

    error = failure_of(handler, requests=requests)
    assert (error.kind, error.status_code, error.retryable) == ("upstream_status", 302, False)
    assert [request.url.path for request in requests] == [PATH]


TIMEOUTS = [httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout]
TRANSPORT_ERRORS = [
    httpx.ConnectError,
    httpx.ReadError,
    httpx.WriteError,
    httpx.RemoteProtocolError,
    httpx.NetworkError,
]


@pytest.mark.parametrize("when", ["on-send", "mid-body"])
@pytest.mark.parametrize("error_type", TIMEOUTS, ids=lambda t: t.__name__)
def test_post_json_maps_each_timeout_type_to_timeout(
    error_type: type[httpx.TimeoutException], when: str
) -> None:
    error = error_type(ERROR_SENTINEL)
    handler = raising(error) if when == "on-send" else failing_mid_body(error)
    result = failure_of(handler)
    assert (result.kind, result.status_code, result.retryable) == ("timeout", None, True)


@pytest.mark.parametrize("when", ["on-send", "mid-body"])
@pytest.mark.parametrize("error_type", TRANSPORT_ERRORS, ids=lambda t: t.__name__)
def test_post_json_maps_other_transport_errors_to_connection(
    error_type: type[httpx.TransportError], when: str
) -> None:
    error = error_type(ERROR_SENTINEL)
    handler = raising(error) if when == "on-send" else failing_mid_body(error)
    result = failure_of(handler)
    assert (result.kind, result.status_code, result.retryable) == ("connection", None, True)


def test_post_json_does_not_catch_an_error_that_is_not_an_httpx_error() -> None:
    with pytest.raises(RuntimeError, match="not httpx"):
        post(raising(RuntimeError("not httpx")))


@pytest.mark.parametrize("status", REPLY_STATUSES)
def test_post_json_maps_a_corrupt_gzip_2xx_to_a_bad_response_with_its_status(status: int) -> None:
    error = failure_of(streamed([b"not gzip at all"], [], status=status, headers=GZIP))
    assert (error.kind, error.status_code, error.retryable) == ("bad_response", status, False)


# The limit is above the deep-nesting body (100,000 bytes), so that body reaches the JSON parser
# and its RecursionError, not the size cap.
PARSER_LIMIT_BYTES = 200_000
UNREADABLE = [
    pytest.param(b"\xff\xfe{}", id="invalid-utf8"),
    pytest.param(b"{nope", id="invalid-json"),
    pytest.param(b"", id="empty"),
    pytest.param(b"  \n", id="whitespace-only"),
    pytest.param(b"[" * 100_000, id="deep-nesting"),
]


@pytest.mark.parametrize("status", REPLY_STATUSES)
@pytest.mark.parametrize("content", UNREADABLE)
def test_post_json_maps_an_unreadable_2xx_body_to_a_bad_response_with_its_status(
    status: int, content: bytes
) -> None:
    error = failure_of(json_reply(status, content), max_response_bytes=PARSER_LIMIT_BYTES)
    assert (error.kind, error.status_code, error.retryable) == ("bad_response", status, False)


def padded(size_bytes: int) -> bytes:
    """Valid JSON of exactly `size_bytes` bytes."""
    return b"[" + b" " * (size_bytes - 2) + b"]"


@pytest.mark.parametrize("status", REPLY_STATUSES)
def test_post_json_accepts_a_body_of_exactly_the_limit_and_rejects_one_byte_more(
    status: int,
) -> None:
    assert reply_of(json_reply(status, padded(LIMIT_BYTES))).payload == []
    error = failure_of(json_reply(status, padded(LIMIT_BYTES + 1)))
    assert (error.kind, error.status_code) == ("bad_response", status)


def test_post_json_counts_a_gzip_body_at_its_decoded_size() -> None:
    over = gzip.compress(padded(LIMIT_BYTES + 1))
    assert len(over) < LIMIT_BYTES
    error = failure_of(streamed([over], [], status=201, headers=GZIP))
    assert (error.kind, error.status_code) == ("bad_response", 201)
    exact = gzip.compress(padded(LIMIT_BYTES))
    assert reply_of(streamed([exact], [], status=201, headers=GZIP)).payload == []


def test_post_json_uses_the_max_response_bytes_it_is_given() -> None:
    handler = json_reply(200, padded(1_500))
    assert isinstance(post(handler, max_response_bytes=1_024), ProviderError)
    assert reply_of(handler, max_response_bytes=2_048).payload == []


LEAKY_LIMITS_BYTES = {"deep-nesting": PARSER_LIMIT_BYTES}
LEAKY_FAILURES = {
    "429": streamed([ERROR_SENTINEL.encode()], [], status=429),
    "500": streamed([ERROR_SENTINEL.encode()], [], status=500),
    "404": streamed([ERROR_SENTINEL.encode()], [], status=404),
    "timeout-on-send": raising(httpx.ConnectTimeout(ERROR_SENTINEL)),
    "timeout-mid-body": failing_mid_body(httpx.ReadTimeout(ERROR_SENTINEL)),
    "connection-on-send": raising(httpx.ConnectError(ERROR_SENTINEL)),
    "connection-mid-body": failing_mid_body(httpx.ReadError(ERROR_SENTINEL)),
    "corrupt-gzip": streamed([ERROR_SENTINEL.encode()], [], headers=GZIP),
    "invalid-json": json_reply(200, ERROR_SENTINEL.encode()),
    "invalid-utf8": json_reply(200, b"\xff" + ERROR_SENTINEL.encode()),
    "deep-nesting": json_reply(200, b"[" * 100_000 + ERROR_SENTINEL.encode()),
    "oversize": json_reply(200, b'"' + ERROR_SENTINEL.encode() * LIMIT_BYTES + b'"'),
}


@pytest.mark.parametrize("name", list(LEAKY_FAILURES))
def test_post_json_errors_have_no_context_and_hold_no_body_url_or_header_value(name: str) -> None:
    error = failure_of(
        LEAKY_FAILURES[name],
        headers={"x-api-key": HEADER_SENTINEL},
        max_response_bytes=LEAKY_LIMITS_BYTES.get(name, LIMIT_BYTES),
    )
    text = str(error) + repr(error) + "".join(traceback.format_exception(error))
    for sentinel in (ERROR_SENTINEL, URL_SENTINEL, HEADER_SENTINEL):
        assert sentinel not in text
    expected = f"provider failed: {error.kind}"
    if error.status_code is not None:
        expected += f" (HTTP {error.status_code})"
    assert str(error) == expected
    assert error.__cause__ is None
    assert error.__context__ is None
