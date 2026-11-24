"""The cache scan and embedding latency benchmarks in scripts/bench_cache.py (T-408, ADR-0018).

`scan` fills exactly N entries into one partition, every timed lookup is a miss that scans them
all, the vectors are seeded unit vectors, the figures are exact under an injected timer, and the
vector memory guard skips a combination above its limit. A lookup that pauses stops the run.
`embed` discards its first call, times the next N, records the Ollama version, and stops with no
figure on an `EmbeddingError`. No test touches the network.
"""

import asyncio
import json
import math
import weakref
from array import array
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.cache.semantic import Hit, Miss, partition_key
from tests.fakes import FakeEmbedder, FakeMonotonicClock, load_script

bench = load_script("bench_cache")

HOST = bench.HostFacts(
    git_commit="0123456789abcdef0123456789abcdef01234567",
    python_version="3.13.9",
    os="TestOS-1.0",
    cpu_count=8,
)
BELOW_EVERY_SIMILARITY = -2.0
SENTINEL = "sentinel"  # appears only in the URL: the host and the password
SENTINEL_URL = "http://user:sentinel-pass@sentinel-host.test:11434"
MODEL = "test-model"
VERSION = "9.8.7-test"
# Three repeats whose times are 0.5, 0.25 and 1.0: the minimum, median and maximum all differ.
READINGS = [0.0, 0.5, 1.0, 1.25, 2.0, 3.0]
LOOKUP_PAUSED = (
    "a timed lookup paused on an await, so its time would include waiting, not only the scan;"
    " the run stopped and reports no figure"
)


class ScriptedTimer:
    """Returns the given readings in order and counts the reads; running out fails the test."""

    def __init__(self, readings: Sequence[float]) -> None:
        self._readings = list(readings)
        self.reads = 0

    def __call__(self) -> float:
        assert self.reads < len(self._readings), "the timer was read more often than expected"
        reading = self._readings[self.reads]
        self.reads += 1
        return reading


class PausingEmbedder:
    """Returns the query after awaiting `asyncio.sleep(delay_seconds)`, so every lookup pauses."""

    def __init__(self, query: array[float], delay_seconds: float = 0.0) -> None:
        self._query = query
        self._delay_seconds = delay_seconds

    @property
    def identity(self) -> str:
        return bench.FIXED_EMBEDDER_IDENTITY  # type: ignore[no-any-return]

    async def embed(self, text: str) -> array[float]:
        await asyncio.sleep(self._delay_seconds)
        return self._query


def seeded(seed: int = 0, entries: int = 10, dimensions: int = 8) -> tuple[Any, list[Any]]:
    query, vectors = bench.seeded_vectors(seed, entries, dimensions)
    return query, list(vectors)


def scan_cache(query: Any, vectors: Sequence[Any], threshold: float) -> Any:
    return bench.build_scan_cache(
        bench.FixedEmbedder(query), vectors, entries=len(vectors), similarity_threshold=threshold
    )


def lookup(cache: Any) -> Any:
    return asyncio.run(cache.lookup(bench.CALLER_ID, bench.REQUEST))


def in_event_loop[T](function: Callable[[], T]) -> T:
    """Call `function` inside a running event loop, as `run_scan` does."""

    async def call() -> T:
        return function()

    return asyncio.run(call())


def run_scan(timer: Callable[[], float], **overrides: Any) -> list[Any]:
    settings: dict[str, Any] = {
        "entries": [10],
        "dimensions": [8],
        "repeats": 3,
        "seed": 0,
        "max_vector_bytes": 640,
    }
    settings.update(overrides)
    rows: list[Any] = asyncio.run(bench.run_scan(timer=timer, **settings))
    return rows


# Criterion 1: exactly N entries in one partition, and every timed lookup scans them all.


def test_the_partition_holds_exactly_n_entries_and_a_lookup_reaches_the_most_similar() -> None:
    query, vectors = seeded()
    assert len(vectors) == 10
    cache = scan_cache(query, vectors, BELOW_EVERY_SIMILARITY)
    assert len(cache) == 10
    result = lookup(cache)
    assert isinstance(result, Hit)
    assert result.similarity == max(math.sumprod(query, vector) for vector in vectors)


def test_every_entry_is_reachable_by_the_lookup() -> None:
    _, vectors = seeded()
    for vector in vectors:
        result = lookup(scan_cache(vector, vectors, BELOW_EVERY_SIMILARITY))
        assert isinstance(result, Hit)
        own_similarity = math.sumprod(vector, vector)
        assert result.similarity == own_similarity
        assert own_similarity == max(math.sumprod(vector, other) for other in vectors)


def test_timed_lookups_miss_on_the_filled_partition() -> None:
    assert bench.UNREACHABLE_THRESHOLD == 2.0
    query, vectors = seeded()
    result = lookup(scan_cache(query, vectors, bench.UNREACHABLE_THRESHOLD))
    assert isinstance(result, Miss)
    assert result.ticket.partition_key == partition_key(
        bench.CALLER_ID, bench.REQUEST, bench.FIXED_EMBEDDER_IDENTITY
    )


def test_time_lookups_rejects_a_hit() -> None:
    query, vectors = seeded()
    cache = scan_cache(query, vectors, BELOW_EVERY_SIMILARITY)
    with pytest.raises(bench.ScriptError) as caught:
        bench.time_lookups(cache, repeats=1, timer=ScriptedTimer([0.0, 1.0]))
    assert str(caught.value) == "a timed lookup was not a miss, so it did not scan every entry"


def test_a_fill_short_of_n_entries_is_an_error() -> None:
    query, vectors = seeded(entries=9)
    with pytest.raises(bench.ScriptError) as caught:
        bench.build_scan_cache(
            bench.FixedEmbedder(query),
            vectors,
            entries=10,
            similarity_threshold=bench.UNREACHABLE_THRESHOLD,
        )
    assert str(caught.value) == "the partition holds 9 entries, not 10"


# Criterion 2: seeded unit vectors.


def test_vectors_are_unit_vectors() -> None:
    for seed in range(20):
        for dimensions in (1, 8, 384):
            query, vectors = seeded(seed, entries=3, dimensions=dimensions)
            for vector in [query, *vectors]:
                assert len(vector) == dimensions
                assert abs(math.sumprod(vector, vector) - 1.0) <= 1e-12
                if dimensions == 1:
                    assert abs(vector[0]) == 1.0


def test_vectors_repeat_for_a_seed_and_differ_across_seeds() -> None:
    assert seeded(0) == seeded(0)
    assert seeded(0)[0] != seeded(1)[0]
    assert seeded(0)[1] != seeded(1)[1]


def test_first_vector_values_are_pinned() -> None:
    # Recorded from the first run of seeded_vectors(0, 2, 8) on 2026-11-25.
    query, vectors = seeded(0, entries=2, dimensions=8)
    assert list(query[:3]) == [0.5602102951583506, 0.41956894305259707, -0.12919220412319712]
    assert list(vectors[0][:3]) == [-0.038823933329510195, 0.13832467627313505, 0.6770292870802838]
    assert list(vectors[1][:3]) == [0.42245594471906783, 0.4977607272925038, 0.3198396900330319]


def test_vector_bytes_counts_eight_bytes_per_value() -> None:
    assert bench.vector_bytes(10, 8) == 640
    assert bench.vector_bytes(100_000, 1_024) == 819_200_000  # ADR-0018's 800 MB


# Criterion 3: exact figures under an injected timer.


def test_time_lookups_is_exact_with_an_injected_timer() -> None:
    query, vectors = seeded()
    timer = ScriptedTimer(READINGS)
    samples = bench.time_lookups(
        scan_cache(query, vectors, bench.UNREACHABLE_THRESHOLD), repeats=3, timer=timer
    )
    assert samples == [0.5, 0.25, 1.0]
    assert timer.reads == 6
    timing = bench.summarize_times(samples)
    assert (timing.min_seconds, timing.median_seconds, timing.max_seconds) == (0.25, 0.5, 1.0)
    assert timing.samples_seconds == (0.5, 0.25, 1.0)


def test_timer_reads_bracket_each_lookup() -> None:
    query, vectors = seeded()
    embedder = FakeEmbedder({bench.LOOKUP_TEXT: tuple(query)}, identity="bench:counting")
    cache = bench.build_scan_cache(
        embedder, vectors, entries=10, similarity_threshold=bench.UNREACHABLE_THRESHOLD
    )
    lookups_at_each_read: list[int] = []

    def timer() -> float:
        lookups_at_each_read.append(len(embedder.calls))
        return float(len(lookups_at_each_read))

    assert bench.time_lookups(cache, repeats=3, timer=timer) == [1.0, 1.0, 1.0]
    assert lookups_at_each_read == [0, 1, 1, 2, 2, 3]


def test_median_of_even_repeats_averages_the_middle_two() -> None:
    timing = bench.summarize_times([8.0, 1.0, 4.0, 2.0])
    assert (timing.min_seconds, timing.median_seconds, timing.max_seconds) == (1.0, 3.0, 8.0)


# The runtime guard: a lookup that pauses stops the run.


@pytest.mark.parametrize("delay_seconds", [0.0, 0.001])
def test_a_lookup_that_pauses_stops_the_scan_with_a_clear_error(delay_seconds: float) -> None:
    query, vectors = seeded()
    cache = bench.build_scan_cache(
        PausingEmbedder(query, delay_seconds),
        vectors,
        entries=10,
        similarity_threshold=bench.UNREACHABLE_THRESHOLD,
    )
    with pytest.raises(bench.ScriptError) as caught:
        in_event_loop(lambda: bench.time_lookups(cache, repeats=3, timer=ScriptedTimer(READINGS)))
    assert str(caught.value) == LOOKUP_PAUSED


def test_a_paused_coroutine_is_closed_before_the_error_is_raised() -> None:
    closed: list[bool] = []

    async def pauses_then_finishes() -> int:
        try:
            await asyncio.sleep(0)
            return 1
        finally:
            closed.append(True)

    async def call() -> list[bool] | None:
        try:
            bench.run_to_completion(pauses_then_finishes())
        except bench.ScriptError:
            # Read while the traceback, which holds the coroutine, is alive: dropping it would
            # close the coroutine too, and hide a missing close().
            return list(closed)
        return None

    assert asyncio.run(call()) == [True]


def test_a_paused_lookup_in_a_real_run_exits_1_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(bench, "FixedEmbedder", PausingEmbedder)
    output = tmp_path / "report.json"
    argv = ["scan", "--entries", "10", "--dimensions", "8", "--output", str(output)]
    assert bench.main(argv, timer=ScriptedTimer(READINGS * 20), host=HOST) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"error: {LOOKUP_PAUSED}\n"
    assert not output.exists()


# Criterion 4: the vector memory guard.


def test_a_combination_at_exactly_the_limit_runs() -> None:
    timer = ScriptedTimer(READINGS)
    (row,) = run_scan(timer, max_vector_bytes=640)
    assert row.vector_bytes == 640
    assert row.timing is not None
    assert row.timing.samples_seconds == (0.5, 0.25, 1.0)
    assert timer.reads == 6


def test_a_combination_one_byte_over_the_limit_is_skipped_and_reported() -> None:
    timer = ScriptedTimer([])
    rows = run_scan(timer, max_vector_bytes=639)
    assert [(row.entries, row.dimensions, row.vector_bytes, row.timing) for row in rows] == [
        (10, 8, 640, None)
    ]
    assert timer.reads == 0
    report = bench.scan_report_as_json(
        rows, entries=[10], dimensions=[8], repeats=3, seed=0, max_vector_bytes=639, host=HOST
    )
    assert report["rows"] == [
        {
            "entries": 10,
            "dimensions": 8,
            "vector_bytes": 640,
            "status": "skipped",
            "skipped_reason": "vectors above --max-vector-bytes",
            "per_lookup_seconds": None,
            "samples_seconds": None,
        }
    ]
    markdown = bench.render_scan_markdown(
        rows, entries=[10], dimensions=[8], repeats=3, seed=0, max_vector_bytes=639, host=HOST
    )
    assert "| 10 | 8 | 640 | skipped: vectors above --max-vector-bytes | n/a | n/a |" in markdown


def test_a_skipped_combination_does_not_stop_later_ones() -> None:
    rows = run_scan(ScriptedTimer(READINGS), entries=[10], dimensions=[16, 8])
    assert [(row.dimensions, row.timing is None) for row in rows] == [(16, True), (8, False)]


def test_each_cache_is_freed_before_the_next_fill(monkeypatch: pytest.MonkeyPatch) -> None:
    # Two caches alive at once would let peak vector memory pass --max-vector-bytes.
    build = bench.build_scan_cache
    built: list[weakref.ref[Any]] = []

    def recording_build(*args: Any, **kwargs: Any) -> Any:
        assert all(ref() is None for ref in built), "an earlier cache is still alive"
        cache = build(*args, **kwargs)
        built.append(weakref.ref(cache))
        return cache

    monkeypatch.setattr(bench, "build_scan_cache", recording_build)
    rows = run_scan(ScriptedTimer(READINGS * 3), dimensions=[8, 16, 4], max_vector_bytes=1_280)
    assert [row.dimensions for row in rows] == [8, 16, 4]
    assert len(built) == 3


def test_seed_and_memory_limit_reach_the_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seeded_with: list[int] = []
    seed_vectors = bench.seeded_vectors

    def recording_seeded_vectors(seed: int, entries: int, dimensions: int) -> Any:
        seeded_with.append(seed)
        return seed_vectors(seed, entries, dimensions)

    monkeypatch.setattr(bench, "seeded_vectors", recording_seeded_vectors)
    output = tmp_path / "report.json"
    argv = ["scan", "--entries", "10", "--dimensions", "8", "16", "--repeats", "3"]
    argv += ["--seed", "7", "--max-vector-bytes", "640", "--output", str(output)]
    assert bench.main(argv, timer=ScriptedTimer(READINGS), host=HOST) == 0
    assert seeded_with == [7]
    report = json.loads(output.read_text(encoding="utf-8"))
    assert [row["status"] for row in report["rows"]] == ["measured", "skipped"]
    assert (report["settings"]["seed"], report["settings"]["max_vector_bytes"]) == (7, 640)
    assert "| 10 | 16 | 1,280 | skipped:" in capsys.readouterr().out


# Criterion 6 (and 3): a tiny run completes, and its report is pinned.

SCAN_ARGV = ["scan", "--entries", "10", "--dimensions", "8", "--repeats", "3"]
SCAN_MARKDOWN = """\
# Cache scan: time per lookup over one full partition

| Entries | Dimensions | Vector bytes | Min (ms) | Median (ms) | Max (ms) |
| --- | --- | --- | --- | --- | --- |
| 10 | 8 | 640 | 250.0000 | 500.0000 | 1000.0000 |

Timing: timeit.Timer(lookup, timer=time.perf_counter).repeat(repeat=<repeats>, number=1): one \
lookup per repeat, garbage collection off while timing; minimum and statistics.median of the \
repeats.

## Settings

- Entries: 10; dimensions: 8
- Repeats: 3; seed: 0
- Vector memory limit: 1,073,741,824 bytes (entries x dimensions x 8 (array('d'); vectors only, \
not Python's overhead per entry))
- Similarity threshold: 2.0 (no entry reaches it, so every lookup scans every entry and misses)
- Embedder: fixed query vector, no embedding call
- Git commit: 0123456789abcdef0123456789abcdef01234567
- Python 3.13.9 on TestOS-1.0, 8 CPUs
"""


def test_tiny_scan_run_completes_and_pins_its_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "report.json"
    argv = [*SCAN_ARGV, "--output", str(output)]
    assert bench.main(argv, timer=ScriptedTimer(READINGS), host=HOST) == 0
    assert capsys.readouterr().out == SCAN_MARKDOWN
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "mode": "scan",
        "rows": [
            {
                "entries": 10,
                "dimensions": 8,
                "vector_bytes": 640,
                "status": "measured",
                "skipped_reason": None,
                "per_lookup_seconds": {"min": 0.25, "median": 0.5, "max": 1.0},
                "samples_seconds": [0.5, 0.25, 1.0],
            }
        ],
        "timing_method": (
            "timeit.Timer(lookup, timer=time.perf_counter).repeat(repeat=<repeats>, number=1):"
            " one lookup per repeat, garbage collection off while timing; minimum and"
            " statistics.median of the repeats"
        ),
        "settings": {
            "entries": [10],
            "dimensions": [8],
            "repeats": 3,
            "seed": 0,
            "max_vector_bytes": 1_073_741_824,
            "vector_bytes_formula": (
                "entries x dimensions x 8 (array('d'); vectors only, not Python's overhead per"
                " entry)"
            ),
            "similarity_threshold": 2.0,
            "embedder": "fixed query vector, no embedding call",
            "git_commit": "0123456789abcdef0123456789abcdef01234567",
            "python_version": "3.13.9",
            "os": "TestOS-1.0",
            "cpu_count": 8,
        },
    }


def test_tiny_scan_run_completes_on_the_real_timer(capsys: pytest.CaptureFixture[str]) -> None:
    assert bench.main(SCAN_ARGV, host=HOST) == 0
    assert "| 10 | 8 | 640 | " in capsys.readouterr().out


def test_scan_defaults_are_the_adr_grid() -> None:
    args = bench._parse(["scan"])
    assert (args.entries, args.dimensions) == ([1_000, 10_000, 100_000], [384, 1_024])
    assert (args.repeats, args.seed, args.max_vector_bytes) == (20, 0, 1_073_741_824)
    assert bench._parse(["embed", "--model", MODEL]).calls == 100
    assert bench._parse(["scan", "--seed", "0"]).seed == 0  # zero is a valid seed


# Criterion 5: embed.


class FakeOllama:
    """Answers GET /api/version and POST /api/embed, moving `clock` by the next duration on each
    POST, and answering `fail_status` on the POST numbered `fail_at` (0 is the discarded call).
    """

    def __init__(
        self,
        durations: Sequence[float] = (8.0, 0.5, 0.25, 1.0),
        *,
        fail_at: int | None = None,
        fail_status: int = 500,
        version_status: int = 200,
    ) -> None:
        self.clock = FakeMonotonicClock()
        self.requests: list[tuple[str, str, bytes]] = []
        self.hosts: set[tuple[str, int | None]] = set()
        self._durations = list(durations)
        self._fail_at = fail_at
        self._fail_status = fail_status
        self._version_status = version_status
        self._posts = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((request.method, request.url.path, request.content))
        self.hosts.add((request.url.host, request.url.port))
        if request.method == "GET" and request.url.path == "/api/version":
            return httpx.Response(self._version_status, json={"version": VERSION})
        assert (request.method, request.url.path) == ("POST", "/api/embed")
        index = self._posts
        self._posts += 1
        self.clock.advance(self._durations[index])
        if index == self._fail_at:
            return httpx.Response(self._fail_status, json={"error": "failed"})
        return httpx.Response(200, json={"embeddings": [[3.0, 4.0]]})

    def run(self, *extra: str, url: str | None = None, output: Path | None = None) -> int:
        argv = ["embed", "--model", MODEL, "--calls", "3", *extra]
        if url is not None:
            argv += ["--url", url]
        if output is not None:
            argv += ["--output", str(output)]
        return bench.main(  # type: ignore[no-any-return]
            argv,
            transport=httpx.MockTransport(self.handle),
            timer=self.clock.monotonic_seconds,
            host=HOST,
        )


EMBED_BODY = json.dumps(
    {"model": MODEL, "input": "How do I reset my password?", "truncate": False},
    separators=(",", ":"),
).encode("utf-8")
EMBED_MARKDOWN = """\
# Embedding latency: test-model, 3 calls

| Figure | Per call (ms) |
| --- | --- |
| min | 250.0000 |
| median | 500.0000 |
| max | 1000.0000 |

Timing: time.perf_counter around each sequential OllamaEmbedder.embed call, after one discarded \
call.

## Settings

- Model: test-model; Ollama version: 9.8.7-test
- Calls: 3 timed, 1 discarded first
- Text: 'How do I reset my password?' (27 bytes)
- Git commit: 0123456789abcdef0123456789abcdef01234567
- Python 3.13.9 on TestOS-1.0, 8 CPUs
"""


def test_embed_discards_the_first_call_and_times_the_next_n(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ollama = FakeOllama()
    output = tmp_path / "report.json"
    assert ollama.run(output=output) == 0
    assert [(method, path) for method, path, _ in ollama.requests] == [
        ("GET", "/api/version"),
        ("POST", "/api/embed"),
        ("POST", "/api/embed"),
        ("POST", "/api/embed"),
        ("POST", "/api/embed"),
    ]
    assert all(body == EMBED_BODY for _, _, body in ollama.requests[1:])
    assert ollama.hosts == {("localhost", 11434)}  # the default URL when --url is omitted
    assert capsys.readouterr().out == EMBED_MARKDOWN
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "mode": "embed",
        "calls": 3,
        "discarded_calls": 1,
        "per_call_seconds": {"min": 0.25, "median": 0.5, "max": 1.0},
        "samples_seconds": [0.5, 0.25, 1.0],
        "timing_method": (
            "time.perf_counter around each sequential OllamaEmbedder.embed call, after one"
            " discarded call"
        ),
        "settings": {
            "model": "test-model",
            "calls": 3,
            "text": "How do I reset my password?",
            "text_bytes": 27,
            "ollama_version": "9.8.7-test",
            "git_commit": "0123456789abcdef0123456789abcdef01234567",
            "python_version": "3.13.9",
            "os": "TestOS-1.0",
            "cpu_count": 8,
        },
    }


@pytest.mark.parametrize("fail_at", [0, 2])
def test_an_embedding_error_stops_the_run_and_reports_no_figure(
    fail_at: int, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ollama = FakeOllama(fail_at=fail_at)
    output = tmp_path / "report.json"
    assert ollama.run(output=output) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: embedding failed: upstream_status (HTTP 500)\n"
    assert not output.exists()
    assert len(ollama.requests) == 1 + fail_at + 1  # the version, then no call after the failure


def test_a_version_failure_stops_the_run_before_any_embedding(
    capsys: pytest.CaptureFixture[str],
) -> None:
    ollama = FakeOllama(version_status=404)
    assert ollama.run() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: GET /api/version failed: HTTP 404\n"
    assert [(method, path) for method, path, _ in ollama.requests] == [("GET", "/api/version")]


def test_embed_never_writes_the_url(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "report.json"
    ollama = FakeOllama()
    assert ollama.run(url=SENTINEL_URL, output=output) == 0
    assert ollama.hosts == {("sentinel-host.test", 11434)}  # the given URL is the one called
    assert SENTINEL not in output.read_text(encoding="utf-8")
    assert SENTINEL not in capsys.readouterr().out

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {request.url}")

    argv = ["embed", "--model", MODEL, "--url", SENTINEL_URL]
    assert bench.main(argv, transport=httpx.MockTransport(refuse), host=HOST) == 1
    captured = capsys.readouterr()
    assert SENTINEL not in captured.out + captured.err
    assert captured.err == "error: GET /api/version failed: connection\n"


# The command line.


def test_a_missing_output_folder_fails_before_the_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    timer = ScriptedTimer([])
    argv = [*SCAN_ARGV, "--output", str(tmp_path / "missing" / "report.json")]
    assert bench.main(argv, timer=timer, host=HOST) == 1
    assert capsys.readouterr().err == "error: cannot write the --output file\n"
    assert timer.reads == 0


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["scan", "--entries", "0"],
        ["scan", "--dimensions", "0"],
        ["scan", "--repeats", "0"],
        ["scan", "--seed", "-1"],
        ["scan", "--max-vector-bytes", "0"],
        ["embed"],
        ["embed", "--model", "  "],
        ["embed", "--model", MODEL, "--url", " "],
        ["embed", "--model", MODEL, "--calls", "0"],
    ],
)
def test_bad_usage_exits_2(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        bench.main(argv, timer=ScriptedTimer([]), host=HOST)
    assert caught.value.code == 2


def test_a_stray_url_is_not_echoed(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        bench.main(["embed", "--model", MODEL, SENTINEL_URL], host=HOST)
    assert SENTINEL not in capsys.readouterr().err
