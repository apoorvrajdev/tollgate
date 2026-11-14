"""Read an HTTP provider's 2xx reply with a size cap (ADR-0013).

The count is of decoded bytes: `aiter_bytes()` runs each raw chunk through the Content-Encoding
decoder, so a compressed body counts at its decompressed size. Reading stops at the chunk that takes
the total above the limit, and leaving the caller's `client.stream` block closes the response
without reading the rest. Memory can pass the limit by one decoded chunk, and a compressed chunk of
up to 64 KiB can expand far beyond its size (ADR-0013).
"""

import httpx

from app.providers.errors import ProviderError


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
