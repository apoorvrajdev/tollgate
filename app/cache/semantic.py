"""The in-memory semantic cache: partition, lookup, store, expiry and eviction (ADR-0014, ADR-0015).

A request is eligible only when its last message has role `user`. Everything else in the request,
with the caller id and the embedder identity, must match exactly: it is hashed into a partition
key, and a lookup scans only that partition. The last message's content is the only text that is
embedded. A hit needs a cosine similarity (a dot product of unit vectors) at least equal to the
threshold; the most similar entry wins, and a tie goes to the most recently stored.

An entry holds the vector, the answer as its UTF-8 JSON bytes and the provider's name: never the
API key or the prompt. It expires `ttl_seconds` after it was stored, and a hit does not extend it.
When the cache is full, a store evicts one entry: the oldest stored one if it has expired, else the
least recently used, where a store and a hit both count as a use. With a fixed lifetime the oldest
stored entry expires first, so checking it finds an expired entry whenever one exists, provided the
clock does not step backwards; if it does, a live entry may be evicted early, and the count still
never passes `max_entries`. Expired entries are never returned and are evicted first.
"""

import hashlib
import json
import math
from array import array
from collections import OrderedDict
from dataclasses import dataclass

from app.api.models import ChatRequest, ChatResponse
from app.cache.embedder import Embedder, EmbeddingError
from app.clock import Clock

MAX_STORED_BYTES = 65_536


@dataclass(frozen=True, slots=True)
class Ticket:
    """What a later store needs from a miss: the partition key and the embedded vector."""

    partition_key: str
    vector: array[float]


@dataclass(frozen=True, slots=True)
class Hit:
    response: ChatResponse
    provider_name: str
    similarity: float


@dataclass(frozen=True, slots=True)
class Miss:
    ticket: Ticket


@dataclass(frozen=True, slots=True)
class Skip:
    """Not looked up: the request is not eligible or the embedder failed."""


type LookupResult = Hit | Miss | Skip


def partition_key(caller_id: str, request: ChatRequest, embedder_identity: str) -> str:
    """The SHA-256 hex digest of the canonical JSON of everything a hit must match exactly.

    `ensure_ascii=True` escapes every non-ASCII character, so a lone surrogate, which validation
    lets through in `user` and `name`, still encodes as ASCII instead of raising.
    """
    fields = request.model_dump(mode="json")
    del fields["messages"][-1]["content"]
    canonical = json.dumps(
        {"caller_id": caller_id, "embedder": embedder_identity, "request": fields},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True)
class _Entry:
    sequence: int  # store order; breaks ties between equal similarities
    partition_key: str
    vector: array[float]
    body: bytes  # the answer's UTF-8 JSON, so MAX_STORED_BYTES bounds the entry
    provider_name: str
    expires_at_seconds: float


class InMemorySemanticCache:
    def __init__(
        self,
        embedder: Embedder,
        clock: Clock,
        *,
        similarity_threshold: float,
        ttl_seconds: int,
        max_entries: int,
    ) -> None:
        self._embedder = embedder
        self._clock = clock
        self._similarity_threshold = similarity_threshold
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._next_sequence = 0
        self._by_use: OrderedDict[int, _Entry] = OrderedDict()  # least recently used first
        # Oldest stored first. An OrderedDict finds its first entry in O(1); a plain dict would
        # step over the slots that evictions from its front leave behind.
        self._by_store: OrderedDict[int, _Entry] = OrderedDict()
        self._partitions: dict[str, dict[int, _Entry]] = {}

    def __len__(self) -> int:
        return len(self._by_store)

    async def lookup(self, caller_id: str, request: ChatRequest) -> LookupResult:
        last = request.messages[-1]
        if last.role != "user":
            return Skip()
        key = partition_key(caller_id, request, self._embedder.identity)
        try:
            vector = await self._embedder.embed(last.content)
        except EmbeddingError:
            return Skip()  # fail open; any other exception is a bug and propagates
        now_seconds = self._clock.now_seconds()
        best: _Entry | None = None
        best_similarity = 0.0
        for entry in self._partitions.get(key, {}).values():
            if now_seconds >= entry.expires_at_seconds:
                continue
            similarity = math.sumprod(vector, entry.vector)
            if similarity < self._similarity_threshold:
                continue
            if (
                best is None
                or similarity > best_similarity
                or (similarity == best_similarity and entry.sequence > best.sequence)
            ):
                best, best_similarity = entry, similarity
        if best is None:
            return Miss(Ticket(key, vector))
        self._by_use.move_to_end(best.sequence)
        return Hit(ChatResponse.model_validate_json(best.body), best.provider_name, best_similarity)

    def store(self, ticket: Ticket, response: ChatResponse, provider_name: str) -> bool:
        """Store the answer to a miss; return whether it was stored."""
        if len(response.choices) != 1 or response.choices[0].finish_reason != "stop":
            return False
        body = response.model_dump_json().encode("utf-8")
        if len(body) > MAX_STORED_BYTES:
            return False
        now_seconds = self._clock.now_seconds()
        if len(self._by_store) >= self._max_entries:
            self._remove(self._eviction_victim(now_seconds))
        entry = _Entry(
            sequence=self._next_sequence,
            partition_key=ticket.partition_key,
            vector=array("d", ticket.vector),
            body=body,
            provider_name=provider_name,
            expires_at_seconds=now_seconds + self._ttl_seconds,
        )
        self._next_sequence += 1
        self._by_use[entry.sequence] = entry
        self._by_store[entry.sequence] = entry
        self._partitions.setdefault(entry.partition_key, {})[entry.sequence] = entry
        return True

    def _eviction_victim(self, now_seconds: float) -> _Entry:
        oldest_stored = next(iter(self._by_store.values()))
        if now_seconds >= oldest_stored.expires_at_seconds:
            return oldest_stored
        return next(iter(self._by_use.values()))

    def _remove(self, entry: _Entry) -> None:
        del self._by_use[entry.sequence]
        del self._by_store[entry.sequence]
        partition = self._partitions[entry.partition_key]
        del partition[entry.sequence]
        if not partition:
            del self._partitions[entry.partition_key]  # an empty partition would leak its key
