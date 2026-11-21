"""A deterministic hashing embedder: the lexical baseline for tests and the eval harness (ADR-0015).

The text is lower-cased and padded with one space at each end. Each 3-character window is hashed
with BLAKE2b (8-byte digest, read big-endian) to an index modulo 512 and counted, and the counts
are L2-normalised. It gives the same vector in every process and needs no dependency. It measures
lexical overlap, not meaning, and no setting selects it at run time.
"""

import hashlib
import math
from array import array

from app.cache.embedder import EmbeddingError

IDENTITY = "hashing:v1"
DIMENSION = 512
WINDOW_CHARS = 3
DIGEST_BYTES = 8


def _hashed(text: str) -> array[float]:
    padded = " " + text.lower() + " "
    window_count = len(padded) - WINDOW_CHARS + 1
    if window_count <= 0:  # only the empty string: two spaces hold no window
        raise EmbeddingError("bad_response", None)
    counts = [0] * DIMENSION
    for start in range(window_count):
        window = padded[start : start + WINDOW_CHARS]
        # surrogatepass: a lone surrogate is hashed instead of raising; every valid string
        # gives the same bytes as strict UTF-8.
        digest = hashlib.blake2b(
            window.encode("utf-8", "surrogatepass"), digest_size=DIGEST_BYTES
        ).digest()
        counts[int.from_bytes(digest, "big") % DIMENSION] += 1
    norm = math.sqrt(math.sumprod(counts, counts))
    return array("d", (count / norm for count in counts))


class HashingEmbedder:
    @property
    def identity(self) -> str:
        return IDENTITY

    async def embed(self, text: str) -> array[float]:
        return _hashed(text)
