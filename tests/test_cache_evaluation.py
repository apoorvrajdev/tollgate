"""The cache eval harness and its script (ADR-0014, T-304).

Each pair's `first` text embeds to (1, 0) and its `second` to (similarity, 0), so the cache's dot
product is exactly the similarity the test names. No test touches the network: the Ollama path
runs on an `httpx.MockTransport`.
"""

import asyncio
import hashlib
import importlib.util
import json
from collections.abc import Coroutine, Sequence
from pathlib import Path
from typing import Any, Protocol, cast

import httpx
import pytest

from app.cache.embedder import EmbeddingError
from app.cache.evaluation import (
    DIFFERENT_CATEGORIES,
    THRESHOLDS,
    DatasetError,
    EvalReport,
    EvaluationError,
    Pair,
    PairLabel,
    SkippedLookupError,
    ThresholdRow,
    dataset_sha256,
    evaluate,
    load_pairs,
    render_markdown,
)
from app.cache.semantic import InMemorySemanticCache
from tests.fakes import FakeClock, FakeEmbedder

ROOT = Path(__file__).resolve().parent.parent
DATASET_BYTES = (ROOT / "eval" / "cache_pairs.json").read_bytes()
SENTINEL = "sentinel"  # appears only in the URL: the host and the password
SENTINEL_URL = "http://user:sentinel-pass@sentinel-host.test:11434"
RECORDED_DIGEST = "73aa98d68f99b48578e9b1f0ca6f30a609ceaf00388ee6ffcc32825472bb9e1f"


class EvalScript(Protocol):
    DATASET_PATH: Path

    def main(
        self,
        argv: Sequence[str] | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: FakeClock | None = None,
    ) -> int: ...


def _load_script() -> EvalScript:
    # scripts/ is not a package, and mypy checks the file as the module eval_cache.
    spec = importlib.util.spec_from_file_location(
        "eval_cache_script", ROOT / "scripts" / "eval_cache.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(EvalScript, module)


script = _load_script()
type Spec = tuple[PairLabel, str, float]


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


def dataset(
    *specs: tuple[PairLabel, str, float],
) -> tuple[list[Pair], dict[str, tuple[float, ...]]]:
    pairs: list[Pair] = []
    vectors: dict[str, tuple[float, ...]] = {}
    for n, (label, category, similarity) in enumerate(specs):
        pair = Pair(f"p{n}", label, category, f"p{n} first", f"p{n} second")
        pairs.append(pair)
        vectors[pair.first] = (1.0, 0.0)
        vectors[pair.second] = (similarity, 0.0)
    return pairs, vectors


def report_of(*specs: Spec) -> EvalReport:
    pairs, vectors = dataset(*specs)
    return run(evaluate(pairs, FakeEmbedder(vectors), FakeClock(0.0)))


def row_at(report: EvalReport, threshold: float) -> ThresholdRow:
    rows = [row for row in report.rows if row.threshold == threshold]
    assert len(rows) == 1
    return rows[0]


SAME_HIT: Spec = ("same", "synonym", 1.0)
DIFFERENT_MISS: Spec = ("different", "negation", 0.0)


# --- Thresholds and placement (AC2) ---


def test_thresholds_are_exactly_i_over_100() -> None:
    expected = tuple(i / 100 for i in range(50, 101))
    assert expected == THRESHOLDS
    assert len(THRESHOLDS) == 51
    report = report_of(SAME_HIT, DIFFERENT_MISS)
    assert tuple(row.threshold for row in report.rows) == expected


def test_a_similarity_equal_to_a_threshold_hits_at_it() -> None:
    additive = 0.5 + 7 * 0.01
    assert additive != float("0.57")  # an additive sweep would miss the 0.57 pair
    report = report_of(
        ("same", "synonym", float("0.57")),
        ("same", "synonym", 0.5),
        ("same", "synonym", 1.0),
        DIFFERENT_MISS,
    )
    hits = {t: row_at(report, t).same_hits for t in (0.5, 0.51, 0.57, 0.58, 0.99, 1.0)}
    assert hits == {0.5: 3, 0.51: 2, 0.57: 2, 0.58: 1, 0.99: 1, 1.0: 1}


def test_hit_and_wrong_hit_rates_are_exact() -> None:
    report = report_of(
        ("same", "synonym", 1.0),
        ("same", "synonym", 0.6),
        ("same", "synonym", 0.3),
        ("different", "negation", 0.55),
        ("different", "negation", 0.2),
    )
    assert row_at(report, 0.6).same_hit_rate == 2 / 3
    assert row_at(report, 0.55).wrong_hit_rate == 1 / 2
    assert row_at(report, 0.56).wrong_hits == 0
    assert (report.same_pairs, report.different_pairs) == (3, 2)


def test_wrong_hits_are_counted_per_category() -> None:
    report = report_of(
        SAME_HIT,
        ("different", "negation", 0.9),
        ("different", "negation", 0.9),
        ("different", "negation", 0.9),
        ("different", "changed_number", 0.9),
        ("different", "swapped_order", 0.9),
        ("different", "swapped_order", 0.9),
        ("different", "unrelated_topic", 0.1),
        ("different", "changed_entity", 0.1),
    )
    row = row_at(report, 0.5)
    assert row.wrong_hits_by_category == {
        "unrelated_topic": 0,
        "negation": 3,
        "changed_number": 1,
        "swapped_order": 2,
        "changed_entity": 0,
    }
    assert list(row.wrong_hits_by_category) == list(DIFFERENT_CATEGORIES)
    assert (row.wrong_hits, row.wrong_hit_rate) == (6, 6 / 8)
    assert row_at(report, 0.91).wrong_hits_by_category == dict.fromkeys(DIFFERENT_CATEGORIES, 0)


def test_each_pair_runs_in_its_own_cache() -> None:
    # Every first text has the same vector, so a cache shared by the pairs would hit at once.
    report = report_of(("same", "synonym", 0.7), ("different", "negation", 0.6))
    assert row_at(report, 0.7).same_hits == 1
    assert row_at(report, 0.6).wrong_hits == 1


# --- Stopping the run (AC2) ---


class FailingOn(FakeEmbedder):
    def __init__(self, vectors: dict[str, tuple[float, ...]], failing_text: str) -> None:
        super().__init__(vectors)
        self.failing_text = failing_text

    async def embed(self, text: str) -> Any:
        if text == self.failing_text:
            self.calls.append(text)
            raise EmbeddingError("connection", None)
        return await super().embed(text)


@pytest.mark.parametrize("lookup", ["first", "second"])
def test_a_skip_stops_the_run_and_names_its_cause(lookup: str) -> None:
    pairs, vectors = dataset(SAME_HIT, DIFFERENT_MISS, SAME_HIT)
    embedder = FailingOn(vectors, f"p1 {lookup}")
    with pytest.raises(SkippedLookupError) as caught:
        run(evaluate(pairs, embedder, FakeClock(0.0)))
    assert (
        str(caught.value)
        == f"pair p1: the {lookup} lookup was skipped (embedding failed: connection)"
    )
    assert "p2 first" not in embedder.calls


def test_an_unstored_answer_stops_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(InMemorySemanticCache, "store", lambda *_args: False)
    with pytest.raises(EvaluationError, match="not stored"):
        report_of(SAME_HIT, DIFFERENT_MISS)


@pytest.mark.parametrize(
    "specs", [(SAME_HIT,), (DIFFERENT_MISS,)], ids=["only-same", "only-different"]
)
def test_evaluate_needs_one_same_and_one_different_pair(specs: tuple[Any, ...]) -> None:
    with pytest.raises(ValueError, match="at least one same and one different"):
        report_of(*specs)


# --- Settings in the report ---


@pytest.mark.parametrize(
    ("now_seconds", "date"), [(86_399.0, "1970-01-01"), (86_400.0, "1970-01-02")]
)
def test_the_report_date_is_the_clock_date_in_utc(now_seconds: float, date: str) -> None:
    pairs, vectors = dataset(SAME_HIT, DIFFERENT_MISS)
    report = run(evaluate(pairs, FakeEmbedder(vectors, identity="fake:v7"), FakeClock(now_seconds)))
    assert (report.run_date, report.embedder_identity) == (date, "fake:v7")


# --- Recommendation (AC3) ---


@pytest.mark.parametrize(
    ("wrong_similarity", "expected"),
    [(0.734, 0.74), (0.74, 0.75), (0.0, 0.5), (0.995, None), (1.0, None)],
)
def test_the_recommendation_is_the_lowest_threshold_below_1_with_no_wrong_hit(
    wrong_similarity: float, expected: float | None
) -> None:
    report = report_of(SAME_HIT, ("different", "negation", wrong_similarity))
    assert report.recommended_threshold == expected


# --- Loading the dataset ---


def test_load_pairs_reads_the_real_dataset() -> None:
    pairs = load_pairs(DATASET_BYTES)
    assert len(pairs) == 80
    assert pairs[0] == Pair(
        "same-01",
        "same",
        "synonym",
        "How do I delete my account?",
        "How can I remove my account?",
    )


GOOD = {"id": "a", "label": "same", "category": "synonym", "first": "x", "second": "y"}


@pytest.mark.parametrize(
    ("items", "message"),
    [
        pytest.param({"id": "a"}, "JSON array", id="not-a-list"),
        pytest.param([["a"]], "exactly", id="not-an-object"),
        pytest.param(
            [{k: v for k, v in GOOD.items() if k != "second"}], "exactly", id="missing-key"
        ),
        pytest.param([{**GOOD, "extra": "z"}], "exactly", id="extra-key"),
        pytest.param([{**GOOD, "first": 1}], "first must be a string", id="not-a-string"),
        pytest.param([{**GOOD, "label": "similar"}], "label", id="bad-label"),
        pytest.param([{**GOOD, "category": "negation"}], "not a same category", id="same-category"),
        pytest.param(
            [{**GOOD, "label": "different"}], "not a different category", id="different-category"
        ),
        pytest.param([GOOD, {**GOOD, "first": "SECRET"}], "duplicate id", id="duplicate-id"),
        pytest.param(
            [{**GOOD, "first": "SECRET"}, {**GOOD, "id": "b", "second": " "}], "blank", id="blank"
        ),
    ],
)
def test_load_pairs_rejects_invalid_data(items: object, message: str) -> None:
    with pytest.raises(DatasetError, match=message) as caught:
        load_pairs(json.dumps(items).encode())
    assert "SECRET" not in str(caught.value)


def test_load_pairs_rejects_text_that_is_not_json() -> None:
    with pytest.raises(DatasetError, match="JSON array"):
        load_pairs(b"[{")


def test_the_dataset_digest_ignores_crlf() -> None:
    assert dataset_sha256(b"a\r\nb\n") == hashlib.sha256(b"a\nb\n").hexdigest()


def test_the_dataset_digest_matches_the_recorded_baseline() -> None:
    # docs/cache-eval.md records a run on this digest. A dataset change fails here until the
    # baseline is re-recorded and this value updated with it.
    assert dataset_sha256(DATASET_BYTES) == RECORDED_DIGEST


RECOMMENDED_LINE = (
    "Recommended threshold: 0.74, the lowest below 1.00 with zero wrong hits on this dataset."
    " That is not a guarantee of zero wrong hits."
)
NO_RECOMMENDATION_LINE = (
    "Recommended threshold: none. No threshold below 1.00 has zero wrong hits on this dataset,"
    " so do not use the cache with this embedder."
)


def test_the_markdown_table_and_recommendation_are_exact() -> None:
    report = report_of(
        ("same", "synonym", 1.0), ("same", "synonym", 0.3), ("different", "negation", 0.734)
    )
    lines = render_markdown(report, dataset_sha256="d", ollama_version="0.1").splitlines()
    header = "| Threshold | Same hits | Wrong hits | " + " | ".join(DIFFERENT_CATEGORIES) + " |"
    assert header in lines
    assert "| 0.50 | 1/2 (50.0%) | 1/1 (100.0%) | 0 | 1 | 0 | 0 | 0 |" in lines
    assert "| 0.74 | 1/2 (50.0%) | 0/1 (0.0%) | 0 | 0 | 0 | 0 | 0 |" in lines
    assert "- Ollama version: 0.1" in lines
    assert lines[-1] == RECOMMENDED_LINE


def test_the_markdown_says_when_there_is_no_recommendation() -> None:
    report = report_of(SAME_HIT, ("different", "negation", 1.0))
    text = render_markdown(report, dataset_sha256="d", ollama_version=None)
    assert text.splitlines()[-1] == NO_RECOMMENDATION_LINE


@pytest.mark.parametrize(("identity", "lexical"), [("hashing:v1", True), ("fake:v1", False)])
def test_the_markdown_labels_the_hashing_embedder_lexical(identity: str, lexical: bool) -> None:
    report = report_of(SAME_HIT, DIFFERENT_MISS)
    report = EvalReport(**{**_fields(report), "embedder_identity": identity})
    text = render_markdown(report, dataset_sha256="d", ollama_version=None)
    assert ("lexical baseline, not semantic" in text) is lexical


def _fields(report: EvalReport) -> dict[str, Any]:
    return {name: getattr(report, name) for name in EvalReport.__slots__}


# --- The script (AC4, AC5) ---

SETTINGS_KEYS = {
    "date",
    "embedder",
    "dataset_sha256",
    "same_pairs",
    "different_pairs",
    "ollama_version",
}


def table_rows(stdout: str) -> list[str]:
    return [line for line in stdout.splitlines() if line.startswith(("| 0.", "| 1."))]


def test_the_hashing_run_reports_51_rows_and_every_setting(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "report.json"
    assert (
        script.main(["--embedder", "hashing", "--output", str(output)], clock=FakeClock(0.0)) == 0
    )
    stdout = capsys.readouterr().out
    assert stdout.isascii()
    assert len(table_rows(stdout)) == 51
    digest = dataset_sha256(DATASET_BYTES)
    for expected in [
        "- Date (UTC): 1970-01-01",
        "- Embedder: hashing:v1 (lexical baseline, not semantic)",
        f"- Dataset SHA-256 (LF line endings): {digest}",
        "- Pairs: 40 same, 40 different",
        "- Ollama version: n/a",
        "| 0.50 | 25/40 (62.5%) | 32/40 (80.0%) | 0 | 8 | 8 | 8 | 8 |",
        "Recommended threshold: 0.98, the lowest below 1.00 with zero wrong hits on this dataset.",
    ]:
        assert expected in stdout
    report = json.loads(output.read_text(encoding="utf-8"))
    assert set(report["settings"]) == SETTINGS_KEYS
    assert report["settings"] == {
        "date": "1970-01-01",
        "embedder": "hashing:v1",
        "dataset_sha256": digest,
        "same_pairs": 40,
        "different_pairs": 40,
        "ollama_version": None,
    }
    assert [row["threshold"] for row in report["rows"]] == list(THRESHOLDS)
    assert report["rows"][0] == {
        "threshold": 0.5,
        "same_hits": 25,
        "same_hit_rate": 25 / 40,
        "wrong_hits": 32,
        "wrong_hit_rate": 32 / 40,
        "wrong_hits_by_category": {
            "unrelated_topic": 0,
            "negation": 8,
            "changed_number": 8,
            "swapped_order": 8,
            "changed_entity": 8,
        },
    }
    assert report["recommended_threshold"] == 0.98


def ollama_transport(
    calls: list[tuple[str, str]], *, version: httpx.Response | None = None, embed_status: int = 200
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path == "/api/version":
            return (
                version if version is not None else httpx.Response(200, json={"version": "0.40.17"})
            )
        if embed_status != 200:
            return httpx.Response(embed_status, json={"error": "model not found"})
        return httpx.Response(200, json={"embeddings": [[1.0, 0.0]]})

    return httpx.MockTransport(handler)


def test_the_ollama_run_calls_version_and_embed_and_hides_the_url(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[str, str]] = []
    output = tmp_path / "report.json"
    argv = [
        "--embedder",
        "ollama",
        "--model",
        "all-minilm",
        "--url",
        f" {SENTINEL_URL} ",  # stripped, as the setting is; unstripped it is a malformed base URL
        "--output",
        str(output),
    ]
    assert script.main(argv, transport=ollama_transport(calls), clock=FakeClock(0.0)) == 0
    assert calls.count(("GET", "/api/version")) == 1
    assert calls.count(("POST", "/api/embed")) == 160
    assert len(calls) == 161
    captured = capsys.readouterr()
    assert "- Ollama version: 0.40.17" in captured.out
    assert "- Embedder: ollama:all-minilm\n" in captured.out
    written = output.read_text(encoding="utf-8")
    assert json.loads(written)["settings"]["ollama_version"] == "0.40.17"
    for text in (captured.out, captured.err, written):
        assert SENTINEL not in text


EMBED_404_MESSAGE = (
    "pair same-01: the first lookup was skipped (embedding failed: upstream_status (HTTP 404))"
)


def _raise_connect_error(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError(f"cannot reach {SENTINEL_URL}", request=request)


@pytest.mark.parametrize(
    ("transport_kwargs", "message"),
    [
        pytest.param(
            {"version": httpx.Response(500)}, "GET /api/version failed: HTTP 500", id="version-500"
        ),
        pytest.param(
            {"version": httpx.Response(200, json=["0.1"])},
            "GET /api/version failed: the reply has no valid version",
            id="version-not-dict",
        ),
        pytest.param(
            {"version": httpx.Response(200, json={"version": "0.1\n" + SENTINEL})},
            "GET /api/version failed: the reply has no valid version",
            id="version-odd-text",
        ),
        pytest.param(
            {"version": httpx.Response(200, json={"version": "1" * 5_000})},
            "GET /api/version failed: the reply is too large",
            id="version-too-large",
        ),
        pytest.param(
            {"embed_status": 404},
            EMBED_404_MESSAGE,
            id="embed-404",
        ),
    ],
)
def test_an_ollama_failure_prints_no_report_and_no_url(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    transport_kwargs: dict[str, Any],
    message: str,
) -> None:
    output = tmp_path / "report.json"
    argv = ["--embedder", "ollama", "--model", "m", "--url", SENTINEL_URL, "--output", str(output)]
    transport = ollama_transport([], **transport_kwargs)
    assert script.main(argv, transport=transport, clock=FakeClock(0.0)) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"error: {message}\n"
    assert SENTINEL not in captured.err
    assert not output.exists()


def test_a_connection_error_names_no_host(capsys: pytest.CaptureFixture[str]) -> None:
    argv = ["--embedder", "ollama", "--model", "m", "--url", SENTINEL_URL]
    transport = httpx.MockTransport(_raise_connect_error)
    assert script.main(argv, transport=transport, clock=FakeClock(0.0)) == 1
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "error: GET /api/version failed: connection\n")


def test_an_invalid_url_fails_without_echoing_it(capsys: pytest.CaptureFixture[str]) -> None:
    argv = ["--embedder", "ollama", "--model", "m", "--url", "http://user:sentinel-pass@[::1"]
    assert script.main(argv, clock=FakeClock(0.0)) == 1
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "error: --url is not a valid URL\n")


def test_a_malformed_dataset_fails_without_a_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "pairs.json"
    bad.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(script, "DATASET_PATH", bad)
    assert script.main([], clock=FakeClock(0.0)) == 1
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == (
        "",
        "error: the dataset must be a JSON array of pairs\n",
    )


def test_an_unwritable_output_prints_no_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert script.main(["--output", str(tmp_path)], clock=FakeClock(0.0)) == 1  # a directory
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "error: cannot write the --output file\n")


@pytest.mark.parametrize(
    "argv",
    [
        ["--embedder", "ollama"],
        ["--embedder", "ollama", "--model", " "],
        ["--model", "m"],
        ["--embedder", "hashing", "--url", SENTINEL_URL],
        ["--embedder", "ollama", "--model", "m", "--url", " "],
        ["--embedder", "ollama", "--model", "m", "--ulr", SENTINEL_URL],
    ],
    ids=[
        "ollama-no-model",
        "ollama-blank-model",
        "hashing-model",
        "hashing-url",
        "ollama-blank-url",
        "mistyped-flag",
    ],
)
def test_bad_usage_exits_with_2_and_never_repeats_the_url(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as caught:
        script.main(argv)
    assert caught.value.code == 2
    assert SENTINEL not in capsys.readouterr().err
