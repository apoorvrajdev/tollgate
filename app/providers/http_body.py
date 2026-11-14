"""The HTTP providers' one request and its reply body (ADR-0010, ADR-0013).

`post_json` makes the request, reads the status first, never reads the body of a non-2xx answer,
and reads a 2xx body with `read_capped`. The count of `read_capped` is of decoded bytes:
`aiter_bytes()` runs each raw chunk through the Content-Encoding decoder, so a compressed body
counts at its decompressed size. Reading stops at the chunk that takes the total above the limit,
and leaving the caller's `client.stream` block closes the response without reading the rest. Memory
can pass the limit by one decoded chunk, and a compressed chunk of up to 64 KiB can expand far
beyond its size (ADR-0013).

Every `ProviderError` that `post_json` classifies holds only the kind and the status, never the
reply body (which can echo the prompt or a key), the URL or a header value. Each one built from a
caught httpx or decoding error is raised after its `except` block, so it has no `__context__`.
"""

import json
from collections.abc import Mapping
from typing import Any, NamedTuple

import httpx

from app.providers.errors import ProviderError

RATE_LIMITED_STATUS = 429


class JsonReply(NamedTuple):
    payload: object
    status_code: int


async def read_capped(response: httpx.Response, max_response_bytes: int) -> bytes:
    """The decoded body; a body of exactly `max_response_bytes` is returned.

    Raises ProviderError("bad_response", response.status_code) as soon as the total passes the
    limit. The error holds only the kind and the status, never any of the body.
    """
    chunks: list[bytes] = []
    total_bytes = 0
    async for chunk in response.aiter_bytes():
        total_bytes += len(chunk)
        if total_bytes > max_response_bytes:
            raise ProviderError("bad_response", response.status_code)
        chunks.append(chunk)
    return b"".join(chunks)


def _status_error(status: int) -> ProviderError:
    if status == RATE_LIMITED_STATUS:
        return ProviderError("rate_limited", status)
    return ProviderError("upstream_status", status)


async def post_json(
    client: httpx.AsyncClient,
    path: str,
    *,
    body: Mapping[str, Any],
    headers: Mapping[str, str] | None,
    max_response_bytes: int,
) -> JsonReply:
    """POST `body` as JSON; the parsed 2xx reply and its status, or a ProviderError."""
    status = 0
    failure: ProviderError | None = None
    content = b""
    try:
        async with client.stream("POST", path, json=body, headers=headers) as response:
            status = response.status_code
            if not response.is_success:
                raise _status_error(status)
            content = await read_capped(response, max_response_bytes)
    # httpx.TimeoutException is a subclass of httpx.TransportError, so it is checked first.
    except httpx.TimeoutException:
        failure = ProviderError("timeout")
    except httpx.TransportError:
        failure = ProviderError("connection")
    except httpx.DecodingError:
        failure = ProviderError("bad_response", status)
    if failure is not None:
        raise failure
    try:
        payload = json.loads(content.decode("utf-8"))
    except (
        ValueError,
        RecursionError,
    ):  # invalid UTF-8, invalid JSON, empty body, deep nesting
        failure = ProviderError("bad_response", status)
    if failure is not None:
        raise failure
    return JsonReply(payload, status)
