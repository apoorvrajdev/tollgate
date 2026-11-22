"""The cache eval harness: hit rate and wrong-hit rate at every threshold (ADR-0014, T-304).

Each pair runs through its own new `InMemorySemanticCache` with a threshold of 0.5 and one entry:
an answer is stored for `first`, then `second` is looked up. The similarity of a hit places the
pair: under the cache's own `>=` rule it hits at every threshold up to that similarity, and a miss
at 0.5 misses at every threshold. The thresholds are `i / 100`, the same doubles that parsing the
setting gives. A `Skip` stops the run with `SkippedLookupError`, so an embedder outage can never
look like zero wrong hits. The recommended threshold is the lowest below 1.00 with no wrong hit.
"""

import hashlib
import json
from array import array
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Final, Literal

from app.api.models import ChatMessage, ChatRequest, ChatResponse
from app.cache.embedder import Embedder, EmbeddingError
from app.cache.semantic import Hit, InMemorySemanticCache, Skip
from app.clock import Clock

DIFFERENT_CATEGORIES: Final = (
    "unrelated_topic",
    "negation",
    "changed_number",
    "swapped_order",
    "changed_entity",
)
SAME_CATEGORIES: Final = (
    "synonym",
    "word_order",
    "register",
    "question_vs_request",
    "concise_vs_verbose",
)
THRESHOLDS: Final[tuple[float, ...]] = tuple(i / 100 for i in range(50, 101))
PAIR_KEYS: Final = frozenset({"id", "label", "category", "first", "second"})

EVAL_CALLER_ID = "eval"
EVAL_MODEL = "eval-model"
EVAL_PROVIDER = "eval"
EVAL_TTL_SECONDS = 3_600
EVAL_MAX_ENTRIES = 1
_ANSWER = ChatResponse.model_validate(
    {
        "id": "chatcmpl-eval",
        "object": "chat.completion",
        "created": 0,
        "model": EVAL_MODEL,
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": "a"}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
)

type PairLabel = Literal["same", "different"]


@dataclass(frozen=True, slots=True)
class Pair:
    id: str
    label: PairLabel
    category: str
    first: str
    second: str


class DatasetError(ValueError):
    """The dataset is malformed. The message names the pair and the field, never its text."""


class EvaluationError(Exception):
    """The run stopped; no report or recommendation exists."""


class SkippedLookupError(EvaluationError):
    def __init__(self, pair_id: str, lookup: Literal["first", "second"], cause: str | None) -> None:
        message = f"pair {pair_id}: the {lookup} lookup was skipped"
        if cause is not None:
            message += f" ({cause})"  # an EmbeddingError's message: the kind and status only
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ThresholdRow:
    threshold: float
    same_hits: int
    same_hit_rate: float
    wrong_hits: int
    wrong_hit_rate: float
    wrong_hits_by_category: dict[str, int]  # every DIFFERENT_CATEGORIES key, in that order


@dataclass(frozen=True, slots=True)
class EvalReport:
    run_date: str  # UTC, from the injected clock
    embedder_identity: str
    same_pairs: int
    different_pairs: int
    rows: tuple[ThresholdRow, ...]
    recommended_threshold: float | None


def load_pairs(data: bytes) -> tuple[Pair, ...]:
    """Parse and check the pairs. Counts are not checked here, so tests can use small sets."""
    try:
        items = json.loads(data)
    except ValueError:
        items = None
    if not isinstance(items, list):
        raise DatasetError("the dataset must be a JSON array of pairs")
    pairs: list[Pair] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(items):
        where = f"pair {index}"
        if not isinstance(item, dict) or set(item) != PAIR_KEYS:
            raise DatasetError(f"{where}: must be an object with exactly {sorted(PAIR_KEYS)}")
        for key in sorted(PAIR_KEYS):
            if not isinstance(item[key], str):
                raise DatasetError(f"{where}: {key} must be a string")
        label, category = item["label"], item["category"]
        if label == "same":
            allowed: tuple[str, ...] = SAME_CATEGORIES
        elif label == "different":
            allowed = DIFFERENT_CATEGORIES
        else:
            raise DatasetError(f"{where}: label must be same or different")
        if category not in allowed:
            raise DatasetError(f"{where}: category is not a {label} category")
        if item["id"] in seen_ids:
            raise DatasetError(f"{where}: duplicate id")
        seen_ids.add(item["id"])
        for key in ("first", "second"):
            if not item[key].strip():
                raise DatasetError(f"{where}: {key} is blank")
        pairs.append(Pair(item["id"], label, category, item["first"], item["second"]))
    return tuple(pairs)


def dataset_sha256(data: bytes) -> str:
    """The SHA-256 of the file with LF line endings, so a CRLF checkout gives the same digest."""
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


class _CauseRecorder:
    """Passes calls through and remembers the last `EmbeddingError`, which the cache swallows."""

    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder
        self.last_error: EmbeddingError | None = None

    @property
    def identity(self) -> str:
        return self._embedder.identity

    async def embed(self, text: str) -> array[float]:
        try:
            return await self._embedder.embed(text)
        except EmbeddingError as error:
            self.last_error = error
            raise


def _request(text: str) -> ChatRequest:
    return ChatRequest(model=EVAL_MODEL, messages=[ChatMessage(role="user", content=text)])


async def _similarity(pair: Pair, embedder: _CauseRecorder, clock: Clock) -> float | None:
    """The second lookup's hit similarity in a new cache holding only `first`; None on a miss."""
    cache = InMemorySemanticCache(
        embedder,
        clock,
        similarity_threshold=THRESHOLDS[0],
        ttl_seconds=EVAL_TTL_SECONDS,
        max_entries=EVAL_MAX_ENTRIES,
    )
    embedder.last_error = None
    first = await cache.lookup(EVAL_CALLER_ID, _request(pair.first))
    if isinstance(first, Skip):
        raise SkippedLookupError(pair.id, "first", _cause(embedder))
    if isinstance(first, Hit):  # only possible if caches were shared between pairs
        raise EvaluationError(f"pair {pair.id}: the first lookup hit a cache that should be empty")
    if not cache.store(first.ticket, _ANSWER, EVAL_PROVIDER):
        raise EvaluationError(f"pair {pair.id}: the answer was not stored")
    second = await cache.lookup(EVAL_CALLER_ID, _request(pair.second))
    if isinstance(second, Skip):
        raise SkippedLookupError(pair.id, "second", _cause(embedder))
    return second.similarity if isinstance(second, Hit) else None


def _cause(embedder: _CauseRecorder) -> str | None:
    return None if embedder.last_error is None else str(embedder.last_error)


def _hits_at(threshold: float, similarity: float | None) -> bool:
    return similarity is not None and similarity >= threshold


async def evaluate(pairs: Sequence[Pair], embedder: Embedder, clock: Clock) -> EvalReport:
    same = [pair for pair in pairs if pair.label == "same"]
    different = [pair for pair in pairs if pair.label == "different"]
    if not same or not different:
        raise ValueError("the dataset needs at least one same and one different pair")
    run_date = datetime.fromtimestamp(clock.now_seconds(), UTC).date().isoformat()
    recorder = _CauseRecorder(embedder)
    similarities = {pair.id: await _similarity(pair, recorder, clock) for pair in pairs}
    rows: list[ThresholdRow] = []
    for threshold in THRESHOLDS:
        same_hits = sum(_hits_at(threshold, similarities[pair.id]) for pair in same)
        by_category = dict.fromkeys(DIFFERENT_CATEGORIES, 0)
        for pair in different:
            if _hits_at(threshold, similarities[pair.id]):
                by_category[pair.category] += 1
        wrong_hits = sum(by_category.values())
        rows.append(
            ThresholdRow(
                threshold=threshold,
                same_hits=same_hits,
                same_hit_rate=same_hits / len(same),
                wrong_hits=wrong_hits,
                wrong_hit_rate=wrong_hits / len(different),
                wrong_hits_by_category=by_category,
            )
        )
    return EvalReport(
        run_date=run_date,
        embedder_identity=embedder.identity,
        same_pairs=len(same),
        different_pairs=len(different),
        rows=tuple(rows),
        recommended_threshold=recommended_threshold(rows),
    )


def recommended_threshold(rows: Sequence[ThresholdRow]) -> float | None:
    """The lowest threshold below 1.00 with no wrong hit, or None (ADR-0014)."""
    return next((row.threshold for row in rows if row.threshold < 1 and row.wrong_hits == 0), None)


def report_as_json(
    report: EvalReport, *, dataset_sha256: str, ollama_version: str | None
) -> dict[str, object]:
    return {
        "settings": {
            "date": report.run_date,
            "embedder": report.embedder_identity,
            "dataset_sha256": dataset_sha256,
            "same_pairs": report.same_pairs,
            "different_pairs": report.different_pairs,
            "ollama_version": ollama_version,
        },
        "rows": [asdict(row) for row in report.rows],
        "recommended_threshold": report.recommended_threshold,
    }


def render_markdown(report: EvalReport, *, dataset_sha256: str, ollama_version: str | None) -> str:
    """The report as ASCII Markdown: settings, one row per threshold, the recommendation."""
    embedder = report.embedder_identity
    if embedder.startswith("hashing:"):
        embedder += " (lexical baseline, not semantic)"
    lines = [
        "# Cache eval report",
        "",
        f"- Date (UTC): {report.run_date}",
        f"- Embedder: {embedder}",
        f"- Dataset SHA-256 (LF line endings): {dataset_sha256}",
        f"- Pairs: {report.same_pairs} same, {report.different_pairs} different",
        f"- Ollama version: {ollama_version or 'n/a'}",
        "",
        "| Threshold | Same hits | Wrong hits | " + " | ".join(DIFFERENT_CATEGORIES) + " |",
        "| --- " * (3 + len(DIFFERENT_CATEGORIES)) + "|",
    ]
    for row in report.rows:
        cells = [
            f"{row.threshold:.2f}",
            f"{row.same_hits}/{report.same_pairs} ({row.same_hit_rate:.1%})",
            f"{row.wrong_hits}/{report.different_pairs} ({row.wrong_hit_rate:.1%})",
            *(str(row.wrong_hits_by_category[c]) for c in DIFFERENT_CATEGORIES),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    if report.recommended_threshold is None:
        lines.append(
            "Recommended threshold: none. No threshold below 1.00 has zero wrong hits on this"
            " dataset, so do not use the cache with this embedder."
        )
    else:
        lines.append(
            f"Recommended threshold: {report.recommended_threshold:.2f}, the lowest below 1.00"
            " with zero wrong hits on this dataset. That is not a guarantee of zero wrong hits."
        )
    return "\n".join(lines) + "\n"
