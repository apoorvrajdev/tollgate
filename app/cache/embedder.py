"""The embedder interface the semantic cache calls (ADR-0015).

`embed` returns a unit vector as `array("d")`. Every failure an embedder can classify raises
`EmbeddingError` with one of ADR-0010's failure kinds. Its message holds only the kind and the HTTP
status: never the text, which is the caller's prompt, never a reply body and never a URL.

`EmbeddingError` is not a `ProviderError`, so the router's fallback can never catch an embedder
failure.
"""

from array import array
from typing import Protocol

from app.providers.errors import ProviderErrorKind


class Embedder(Protocol):
    @property
    def identity(self) -> str: ...  # part of the cache partition key (ADR-0014)

    async def embed(self, text: str) -> array[float]: ...


class EmbeddingError(Exception):
    def __init__(self, kind: ProviderErrorKind, status_code: int | None) -> None:
        message = f"embedding failed: {kind}"
        if status_code is not None:
            message += f" (HTTP {status_code})"
        super().__init__(message)
        self.kind: ProviderErrorKind = kind
        self.status_code = status_code
