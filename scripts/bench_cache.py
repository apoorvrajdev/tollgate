"""Measure the cache scan's cost and the embedding call's latency (T-408, ADR-0015, ADR-0018).

Usage:
  python scripts/bench_cache.py scan [--entries N [N ...]] [--dimensions D [D ...]]
      [--repeats R] [--seed S] [--max-vector-bytes B] [--output report.json]
  python scripts/bench_cache.py embed --model M [--url URL] [--calls N] [--output report.json]

`scan` fills one partition of an `InMemorySemanticCache` with N seeded unit vectors of D
dimensions for each combination of the given N and D, and times `lookup` with `timeit`, one
lookup per repeat, at a threshold no entry can reach, so every lookup scans every entry. A
combination whose vectors would take more than --max-vector-bytes is skipped and reported as
skipped.

Each timed lookup runs to completion without the event loop stepping in, so its time holds the
lookup's own work (the scan, plus the fixed cost of the partition key and the result) with no
waiting. If a lookup ever pauses on an await, the run stops with an error and reports nothing:
its time would include waiting. Only one combination's cache is held at a time.

`embed` calls GET /api/version once, makes one discarded embedding call, then times N sequential
calls through `OllamaEmbedder`. Any `EmbeddingError` stops the run, and no figure is reported.
The URL can hold credentials, so it is never printed or written.

Exit codes: 0 on success (skipped combinations included), 1 when no report is produced, 2 on bad
usage.
"""

import argparse
import asyncio
import json
import math
import random
import statistics
import sys
import time
import timeit
from array import array
from collections.abc import Callable, Coroutine, Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from pydantic import SecretStr

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
for _path in (ROOT, SCRIPTS):  # running a script puts scripts/ first; tests load it by path
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from bench_load import (  # noqa: E402
    EXIT_FAILED,
    EXIT_OK,
    MILLISECONDS_PER_SECOND,
    HostFacts,
    Parser,
    collect_host_facts,
    positive_int,
)
from eval_cache import ScriptError, fetch_ollama_version  # noqa: E402

from app.api.models import (  # noqa: E402
    ChatMessage,
    ChatRequest,
    ChatResponse,
    Choice,
    ResponseMessage,
    Usage,
)
from app.cache.embedder import Embedder, EmbeddingError  # noqa: E402
from app.cache.semantic import InMemorySemanticCache, Miss, Ticket, partition_key  # noqa: E402
from app.main import build_embedder  # noqa: E402
from app.settings import (  # noqa: E402
    DEFAULT_CACHE_EMBEDDER_URL,
    DEFAULT_TTL_SECONDS,
    CacheSettings,
    SettingsError,
)

type Timer = Callable[[], float]

VECTOR_ITEM_BYTES = array("d").itemsize  # 8: the cache keeps vectors as array("d")
# A dot product of unit vectors is at most 1 plus a few units of rounding, so no entry reaches
# 2.0. A finite value, unlike math.inf, is written as standard JSON.
UNREACHABLE_THRESHOLD = 2.0
CALLER_ID = "bench"
LOOKUP_TEXT = "bench lookup"
REQUEST = ChatRequest(model="bench", messages=[ChatMessage(role="user", content=LOOKUP_TEXT)])
RESPONSE = ChatResponse(
    id="chatcmpl-bench",
    object="chat.completion",
    created=0,
    model="bench",
    choices=[
        Choice(
            index=0,
            message=ResponseMessage(role="assistant", content="bench"),
            finish_reason="stop",
        )
    ],
    usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
)
PROVIDER_NAME = "bench"
FIXED_EMBEDDER_IDENTITY = "bench:fixed"
EMBED_TEXT = "How do I reset my password?"  # fixed, ASCII, far below any model's context

DEFAULT_ENTRIES = (1_000, 10_000, 100_000)  # ADR-0018
DEFAULT_DIMENSIONS = (384, 1_024)  # ADR-0018
DEFAULT_REPEATS = 20  # chosen, not measured
DEFAULT_SEED = 0
# 1 GiB, chosen: the largest combination in the default grid (100,000 x 1,024) holds 819,200,000
# bytes of vectors, and only one combination is held at a time.
DEFAULT_MAX_VECTOR_BYTES = 1_073_741_824
DEFAULT_CALLS = 100  # ADR-0018
DISCARDED_CALLS = 1

SKIPPED_REASON = "vectors above --max-vector-bytes"
LOOKUP_PAUSED = (
    "a timed lookup paused on an await, so its time would include waiting, not only the scan;"
    " the run stopped and reports no figure"
)
LOOKUP_HIT = "a timed lookup was not a miss, so it did not scan every entry"
VECTOR_BYTES_FORMULA = (
    "entries x dimensions x 8 (array('d'); vectors only, not Python's overhead per entry)"
)
SCAN_TIMING_METHOD = (
    "timeit.Timer(lookup, timer=time.perf_counter).repeat(repeat=<repeats>, number=1):"
    " one lookup per repeat, garbage collection off while timing; minimum and"
    " statistics.median of the repeats"
)
EMBED_TIMING_METHOD = (
    "time.perf_counter around each sequential OllamaEmbedder.embed call, after one discarded call"
)
SCAN_EMBEDDER = "fixed query vector, no embedding call"


class FixedEmbedder:
    """Returns the query vector for every text, without pausing."""

    def __init__(self, query: array[float]) -> None:
        self._query = query

    @property
    def identity(self) -> str:
        return FIXED_EMBEDDER_IDENTITY

    async def embed(self, text: str) -> array[float]:
        return self._query


class _FrozenClock:
    """Time never moves, so no entry expires during a run."""

    def now_seconds(self) -> float:
        return 0.0


@dataclass(frozen=True, slots=True)
class Timing:
    min_seconds: float
    median_seconds: float
    max_seconds: float
    samples_seconds: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class ScanRow:
    """One combination; `timing` is None when it was skipped."""

    entries: int
    dimensions: int
    vector_bytes: int
    timing: Timing | None


def unit_vector(rng: random.Random, dimensions: int) -> array[float]:
    """Coordinates from `random()`, whose output Python keeps the same across versions."""
    values = [2.0 * rng.random() - 1.0 for _ in range(dimensions)]
    norm = math.sqrt(math.sumprod(values, values))
    return array("d", (value / norm for value in values))


def seeded_vectors(
    seed: int, entries: int, dimensions: int
) -> tuple[array[float], Iterator[array[float]]]:
    """The query, then the entries lazily: the cache copies each one, so none is held twice."""
    rng = random.Random(seed)
    query = unit_vector(rng, dimensions)
    return query, (unit_vector(rng, dimensions) for _ in range(entries))


def vector_bytes(entries: int, dimensions: int) -> int:
    return entries * dimensions * VECTOR_ITEM_BYTES


def build_scan_cache(
    embedder: Embedder,
    vectors: Iterable[array[float]],
    *,
    entries: int,
    similarity_threshold: float,
) -> InMemorySemanticCache:
    """Store every vector in the one partition that REQUEST from CALLER_ID looks up.

    Stored through tickets, not lookup then store: a lookup per entry would scan the partition
    each time, which is quadratic in its size.
    """
    cache = InMemorySemanticCache(
        embedder,
        _FrozenClock(),
        similarity_threshold=similarity_threshold,
        ttl_seconds=DEFAULT_TTL_SECONDS,
        max_entries=entries,
    )
    key = partition_key(CALLER_ID, REQUEST, embedder.identity)
    for vector in vectors:
        cache.store(Ticket(key, vector), RESPONSE, PROVIDER_NAME)
    if len(cache) != entries:
        raise ScriptError(f"the partition holds {len(cache)} entries, not {entries}")
    return cache


def run_to_completion[T](coroutine: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine that must finish without pausing; a pause stops the run (LOOKUP_PAUSED).

    Called inside a running event loop, so an await that needs the loop yields here instead of
    failing for want of one.
    """
    try:
        coroutine.send(None)
    except StopIteration as stop:
        result: T = stop.value
        return result
    coroutine.close()
    raise ScriptError(LOOKUP_PAUSED)


def time_lookups(cache: InMemorySemanticCache, *, repeats: int, timer: Timer) -> list[float]:
    """The time of each of `repeats` lookups; every one must be a miss."""
    misses: list[bool] = []

    def one() -> None:
        result = run_to_completion(cache.lookup(CALLER_ID, REQUEST))
        misses.append(isinstance(result, Miss))

    samples = timeit.Timer(stmt=one, timer=timer).repeat(repeat=repeats, number=1)
    if not all(misses):
        raise ScriptError(LOOKUP_HIT)
    return samples


def summarize_times(samples: Sequence[float]) -> Timing:
    return Timing(
        min_seconds=min(samples),
        median_seconds=statistics.median(samples),
        max_seconds=max(samples),
        samples_seconds=tuple(samples),
    )


async def run_scan(
    *,
    entries: Sequence[int],
    dimensions: Sequence[int],
    repeats: int,
    seed: int,
    max_vector_bytes: int,
    timer: Timer,
) -> list[ScanRow]:
    """Every combination, entries outer and dimensions inner. Async only so that the timed
    lookups run inside an event loop (see `run_to_completion`); nothing here awaits.
    """
    rows: list[ScanRow] = []
    for entry_count in entries:
        for dimension_count in dimensions:
            size_bytes = vector_bytes(entry_count, dimension_count)
            if size_bytes > max_vector_bytes:
                rows.append(ScanRow(entry_count, dimension_count, size_bytes, None))
                continue
            samples = _measure(
                entry_count, dimension_count, seed=seed, repeats=repeats, timer=timer
            )
            rows.append(ScanRow(entry_count, dimension_count, size_bytes, summarize_times(samples)))
    return rows


def _measure(
    entries: int, dimensions: int, *, seed: int, repeats: int, timer: Timer
) -> list[float]:
    """Fill and time one combination. The cache is freed on return, so the next fill never runs
    while it is alive: peak vector memory is one combination's, which --max-vector-bytes bounds.
    """
    query, vectors = seeded_vectors(seed, entries, dimensions)
    cache = build_scan_cache(
        FixedEmbedder(query),
        vectors,
        entries=entries,
        similarity_threshold=UNREACHABLE_THRESHOLD,
    )
    return time_lookups(cache, repeats=repeats, timer=timer)


async def time_embeddings(embedder: Embedder, *, calls: int, timer: Timer) -> list[float]:
    """One discarded call (it may load the model), then `calls` timed sequential calls.

    An `EmbeddingError` propagates, so a failed run reports no figure.
    """
    for _ in range(DISCARDED_CALLS):
        await embedder.embed(EMBED_TEXT)
    samples: list[float] = []
    for _ in range(calls):
        start_seconds = timer()
        await embedder.embed(EMBED_TEXT)
        samples.append(timer() - start_seconds)
    return samples


def _host_settings(host: HostFacts) -> dict[str, object]:
    return {
        "git_commit": host.git_commit,
        "python_version": host.python_version,
        "os": host.os,
        "cpu_count": host.cpu_count,
    }


def _timing_json(timing: Timing) -> dict[str, float]:
    return {"min": timing.min_seconds, "median": timing.median_seconds, "max": timing.max_seconds}


def scan_report_as_json(
    rows: Sequence[ScanRow],
    *,
    entries: Sequence[int],
    dimensions: Sequence[int],
    repeats: int,
    seed: int,
    max_vector_bytes: int,
    host: HostFacts,
) -> dict[str, object]:
    return {
        "mode": "scan",
        "rows": [
            {
                "entries": row.entries,
                "dimensions": row.dimensions,
                "vector_bytes": row.vector_bytes,
                "status": "skipped" if row.timing is None else "measured",
                "skipped_reason": SKIPPED_REASON if row.timing is None else None,
                "per_lookup_seconds": None if row.timing is None else _timing_json(row.timing),
                "samples_seconds": None if row.timing is None else list(row.timing.samples_seconds),
            }
            for row in rows
        ],
        "timing_method": SCAN_TIMING_METHOD,
        "settings": {
            "entries": list(entries),
            "dimensions": list(dimensions),
            "repeats": repeats,
            "seed": seed,
            "max_vector_bytes": max_vector_bytes,
            "vector_bytes_formula": VECTOR_BYTES_FORMULA,
            "similarity_threshold": UNREACHABLE_THRESHOLD,
            "embedder": SCAN_EMBEDDER,
            **_host_settings(host),
        },
    }


def _ms(seconds: float) -> str:
    return f"{seconds * MILLISECONDS_PER_SECOND:.4f}"


def _host_lines(host: HostFacts) -> list[str]:
    cpus = "n/a" if host.cpu_count is None else str(host.cpu_count)
    return [
        f"- Git commit: {host.git_commit or 'unknown'}",
        f"- Python {host.python_version} on {host.os}, {cpus} CPUs",
    ]


def render_scan_markdown(
    rows: Sequence[ScanRow],
    *,
    entries: Sequence[int],
    dimensions: Sequence[int],
    repeats: int,
    seed: int,
    max_vector_bytes: int,
    host: HostFacts,
) -> str:
    lines = [
        "# Cache scan: time per lookup over one full partition",
        "",
        "| Entries | Dimensions | Vector bytes | Min (ms) | Median (ms) | Max (ms) |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        if row.timing is None:
            figures = f"skipped: {SKIPPED_REASON} | n/a | n/a"
        else:
            timing = row.timing
            figures = (
                f"{_ms(timing.min_seconds)} | {_ms(timing.median_seconds)}"
                f" | {_ms(timing.max_seconds)}"
            )
        lines.append(f"| {row.entries:,} | {row.dimensions:,} | {row.vector_bytes:,} | {figures} |")
    lines += [
        "",
        f"Timing: {SCAN_TIMING_METHOD}.",
        "",
        "## Settings",
        "",
        f"- Entries: {', '.join(f'{n:,}' for n in entries)}; dimensions:"
        f" {', '.join(f'{d:,}' for d in dimensions)}",
        f"- Repeats: {repeats}; seed: {seed}",
        f"- Vector memory limit: {max_vector_bytes:,} bytes ({VECTOR_BYTES_FORMULA})",
        f"- Similarity threshold: {UNREACHABLE_THRESHOLD} (no entry reaches it, so every lookup"
        " scans every entry and misses)",
        f"- Embedder: {SCAN_EMBEDDER}",
        *_host_lines(host),
    ]
    return "\n".join(lines) + "\n"


def embed_report_as_json(
    timing: Timing, *, model: str, ollama_version: str, host: HostFacts
) -> dict[str, object]:
    return {
        "mode": "embed",
        "calls": len(timing.samples_seconds),
        "discarded_calls": DISCARDED_CALLS,
        "per_call_seconds": _timing_json(timing),
        "samples_seconds": list(timing.samples_seconds),
        "timing_method": EMBED_TIMING_METHOD,
        "settings": {
            "model": model,
            "calls": len(timing.samples_seconds),
            "text": EMBED_TEXT,
            "text_bytes": len(EMBED_TEXT.encode("utf-8")),
            "ollama_version": ollama_version,
            **_host_settings(host),
        },
    }


def render_embed_markdown(
    timing: Timing, *, model: str, ollama_version: str, host: HostFacts
) -> str:
    calls = len(timing.samples_seconds)
    lines = [
        f"# Embedding latency: {model}, {calls} calls",
        "",
        "| Figure | Per call (ms) |",
        "| --- | --- |",
        f"| min | {_ms(timing.min_seconds)} |",
        f"| median | {_ms(timing.median_seconds)} |",
        f"| max | {_ms(timing.max_seconds)} |",
        "",
        f"Timing: {EMBED_TIMING_METHOD}.",
        "",
        "## Settings",
        "",
        f"- Model: {model}; Ollama version: {ollama_version}",
        f"- Calls: {calls} timed, {DISCARDED_CALLS} discarded first",
        f"- Text: {EMBED_TEXT!r} ({len(EMBED_TEXT.encode('utf-8'))} bytes)",
        *_host_lines(host),
    ]
    return "\n".join(lines) + "\n"


def _seed(text: str) -> int:
    """Non-negative only: `random.Random` seeds with an int's absolute value, so -7 and 7 give
    the same vectors and the report would record a seed that did not decide them.
    """
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must not be negative")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = Parser(
        description="Measure the cache scan and the embedding call.", allow_abbrev=False
    )
    modes = parser.add_subparsers(dest="mode", required=True)
    scan = modes.add_parser("scan", allow_abbrev=False, help="time a full-partition lookup")
    scan.add_argument("--entries", type=positive_int, nargs="+", default=list(DEFAULT_ENTRIES))
    scan.add_argument(
        "--dimensions", type=positive_int, nargs="+", default=list(DEFAULT_DIMENSIONS)
    )
    scan.add_argument("--repeats", type=positive_int, default=DEFAULT_REPEATS)
    scan.add_argument("--seed", type=_seed, default=DEFAULT_SEED)
    scan.add_argument("--max-vector-bytes", type=positive_int, default=DEFAULT_MAX_VECTOR_BYTES)
    scan.add_argument("--output", type=Path, help="also write the report as JSON to this path")
    embed = modes.add_parser("embed", allow_abbrev=False, help="time the Ollama embedding call")
    embed.add_argument("--model", required=True, help="the Ollama embedding model")
    embed.add_argument("--url", help=f"the Ollama URL (default {DEFAULT_CACHE_EMBEDDER_URL})")
    embed.add_argument("--calls", type=positive_int, default=DEFAULT_CALLS)
    embed.add_argument("--output", type=Path, help="also write the report as JSON to this path")
    return parser


def _parse(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.mode == "embed":
        args.model = args.model.strip()
        if not args.model:
            parser.error("--model must not be blank")
        if args.url is not None:
            args.url = args.url.strip()
            if not args.url:
                parser.error("--url must not be blank")
    return args


async def _run_embed(
    args: argparse.Namespace,
    transport: httpx.AsyncBaseTransport | None,
    timer: Timer,
) -> tuple[Timing, str]:
    settings = CacheSettings(
        embedder="ollama",
        embedder_model=args.model,
        embedder_url=SecretStr(args.url or DEFAULT_CACHE_EMBEDDER_URL),
        similarity_threshold=0.5,  # unused by build_embedder
        ttl_seconds=DEFAULT_TTL_SECONDS,  # unused by build_embedder
        max_entries=1,  # unused by build_embedder
    )
    try:
        client, embedder = build_embedder(settings, transport)
    except SettingsError:
        raise ScriptError("--url is not a valid URL") from None
    failure: str | None = None
    async with client:
        version = await fetch_ollama_version(client)
        try:
            samples = await time_embeddings(embedder, calls=args.calls, timer=timer)
        except EmbeddingError as error:  # its message holds the kind and the status only
            failure = str(error)
    if failure is not None:
        raise ScriptError(failure)
    return summarize_times(samples), version


def _report(
    args: argparse.Namespace,
    transport: httpx.AsyncBaseTransport | None,
    timer: Timer,
    host: HostFacts,
) -> tuple[str, dict[str, object]]:
    if args.mode == "scan":
        rows = asyncio.run(
            run_scan(
                entries=args.entries,
                dimensions=args.dimensions,
                repeats=args.repeats,
                seed=args.seed,
                max_vector_bytes=args.max_vector_bytes,
                timer=timer,
            )
        )
        fields: dict[str, Any] = {
            "entries": args.entries,
            "dimensions": args.dimensions,
            "repeats": args.repeats,
            "seed": args.seed,
            "max_vector_bytes": args.max_vector_bytes,
            "host": host,
        }
        return render_scan_markdown(rows, **fields), scan_report_as_json(rows, **fields)
    timing, version = asyncio.run(_run_embed(args, transport, timer))
    return (
        render_embed_markdown(timing, model=args.model, ollama_version=version, host=host),
        embed_report_as_json(timing, model=args.model, ollama_version=version, host=host),
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    timer: Timer | None = None,
    host: HostFacts | None = None,
) -> int:
    args = _parse(argv)
    try:
        if args.output is not None and not args.output.parent.is_dir():
            # Checked before the run, so a mistyped path does not lose a long run.
            raise ScriptError("cannot write the --output file")
        markdown, report = _report(
            args, transport, timer or time.perf_counter, host or collect_host_facts()
        )
    except ScriptError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_FAILED
    if args.output is not None:
        try:
            with args.output.open("w", encoding="utf-8", newline="\n") as file:
                file.write(json.dumps(report, indent=2) + "\n")
        except OSError:
            print("error: cannot write the --output file", file=sys.stderr)
            return EXIT_FAILED
    print(markdown, end="")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
