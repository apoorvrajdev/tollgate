"""The capped body reader (ADR-0013, T-209): the limit, where reading stops, and decoded counting.

Every body is streamed through an `httpx.MockTransport` from an async generator, so the test can see
which chunks were asked for. No network, no sleeping.
"""

import asyncio
import gzip
import traceback
from collections.abc import AsyncIterator, Callable, Sequence

import httpx
import pytest

from app.providers.errors import ProviderError
from app.providers.http_body import read_capped

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
