"""The Ollama embedder (ADR-0015): `POST /api/embed` on plain httpx, through `post_json`.

One request per call, no retry. `"truncate": false` is always sent, so a prompt longer than the
model's context is a 400 (an `EmbeddingError`, so the cache skips it), never cut down to a prefix it
shares with other prompts. The reply is read up to `max_response_bytes` (ADR-0013's helper) and
must hold exactly one non-empty vector of finite numbers. It is normalised again by its norm, and
every vector must have the length of the first one this embedder returned.

Every failure is an `EmbeddingError` with the kind and status of the `ProviderError` that
`post_json` raised, or `bad_response` with the reply's status. Each is raised outside any `except`
block, so it has no `__context__`: a caught error can hold the reply, which can echo the text.
"""

import math
from array import array

import httpx

from app.cache.embedder import EmbeddingError
from app.providers.errors import ProviderError
from app.providers.http_body import post_json

EMBED_PATH = "/api/embed"
DEFAULT_MAX_RESPONSE_BYTES = 1_048_576


def _as_float(value: object) -> float | None:
    """A JSON number as a float (not a bool), or None; an integer too large for a float is None."""
    if type(value) is float:
        return value
    if type(value) is not int:
        return None
    try:
        return float(value)
    except OverflowError:  # an integer of more than about 308 digits
        return None


class OllamaEmbedder:
    def __init__(
        self,
        client: httpx.AsyncClient,
        model: str,
        *,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ) -> None:
        self._client = client
        self._model = model
        self._max_response_bytes = max_response_bytes
        self._dimension: int | None = None  # the length of the first vector returned

    @property
    def identity(self) -> str:
        return f"ollama:{self._model}"

    async def embed(self, text: str) -> array[float]:
        failure: EmbeddingError | None = None
        try:
            reply = await post_json(
                self._client,
                EMBED_PATH,
                body={"model": self._model, "input": text, "truncate": False},
                headers=None,
                max_response_bytes=self._max_response_bytes,
            )
        except ProviderError as error:
            failure = EmbeddingError(error.kind, error.status_code)
        else:
            return self._checked(reply.payload, reply.status_code)
        raise failure

    def _checked(self, payload: object, status: int) -> array[float]:
        if not isinstance(payload, dict):
            raise EmbeddingError("bad_response", status)
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != 1:
            raise EmbeddingError("bad_response", status)
        raw = embeddings[0]
        if not isinstance(raw, list):
            raise EmbeddingError("bad_response", status)
        values: list[float] = []
        for item in raw:
            value = _as_float(item)
            if value is None:
                raise EmbeddingError("bad_response", status)
            values.append(value)
        # The norm check also covers ADR-0015's other two rules: an empty vector has norm 0, and a
        # NaN or infinite element makes the norm NaN or infinite, so a finite norm means every
        # element is finite. `math.sumprod` overflows to infinity where `math.hypot` would not.
        norm = math.sqrt(math.sumprod(values, values))
        if norm == 0.0 or not math.isfinite(norm):
            raise EmbeddingError("bad_response", status)
        if self._dimension is not None and len(values) != self._dimension:
            raise EmbeddingError("bad_response", status)
        if self._dimension is None:  # set only once every check has passed
            self._dimension = len(values)
        return array("d", (value / norm for value in values))
