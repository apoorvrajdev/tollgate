"""The metric set and its observer (T-404, ADR-0016), checked through the real app.

Same limits as `test_request_log.py`: capacity 1000, the prompt "hello there world" reserves 11
tokens, scripted providers report 20 + 17 = 37 tokens, and a call to `first` moves the fake
monotonic clock by 0.25 s. Values are compared as exact rendered text.
"""

import re
from pathlib import Path
from typing import Any

import pytest

from app.cache.embedder import EmbeddingError
from app.providers.errors import ProviderError, ReplyTooLargeError
from tests.fakes import FakeEmbedder, FakeMonotonicClock, ScriptedProvider, advancing
from tests.test_request_log import LogGateway

TOKEN = "scrape-token-" + "x" * 30
TOKEN_ENV = {"TOLLGATE_METRICS_TOKEN": TOKEN}
BOUNDS = [
    "0.001",
    "0.0025",
    "0.005",
    "0.01",
    "0.025",
    "0.05",
    "0.1",
    "0.25",
    "0.5",
    "1.0",
    "2.5",
    "5.0",
    "10.0",
    "30.0",
    "60.0",
    "+Inf",
]
OUTCOMES = [
    "ok",
    "connection",
    "timeout",
    "rate_limited",
    "upstream_status",
    "bad_response",
    "reply_too_large",
    "error",
]
SAMPLE = re.compile(r"(?P<series>[a-z_]+(?:\{[^}]*\})?) (?P<value>\S+)")


def series_of(text: str) -> dict[str, str]:
    """Every sample line as {name{labels}: value}, in order."""
    found: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        match = SAMPLE.fullmatch(line)
        assert match is not None, line
        assert match["series"] not in found
        found[match["series"]] = match["value"]
    return found


def scraped(gateway: LogGateway) -> dict[str, str]:
    return series_of(gateway.app.state.metrics.render())


def nonzero(series: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in series.items() if value not in ("0", "0.0")}


def histogram_zero(name: str, labels: str = "") -> dict[str, str]:
    prefix = f"{labels}," if labels else ""
    expected = {f'{name}_bucket{{{prefix}le="{bound}"}}': "0" for bound in BOUNDS}
    plain = f"{{{labels}}}" if labels else ""
    expected[f"{name}_sum{plain}"] = "0.0"
    expected[f"{name}_count{plain}"] = "0"
    return expected


def expected_fresh(providers: list[str], *, with_metrics_path: bool) -> dict[str, str]:
    expected: dict[str, str] = {}
    paths = [
        "/v1/chat/completions",
        "/health",
        *(["/metrics"] if with_metrics_path else []),
        "other",
    ]
    for path in paths:
        expected.update(histogram_zero("tollgate_http_request_duration_seconds", f'path="{path}"'))
    for name in providers:
        for cache in ("hit", "miss", "skip", "off"):
            key = f'tollgate_chat_completions_total{{provider="{name}",cache="{cache}"}}'
            expected[key] = "0"
        for outcome in OUTCOMES:
            key = f'tollgate_provider_attempts_total{{provider="{name}",outcome="{outcome}"}}'
            expected[key] = "0"
        expected.update(
            histogram_zero("tollgate_provider_attempt_duration_seconds", f'provider="{name}"')
        )
    for result in ("hit", "miss", "not_eligible", "embedder_failed"):
        expected[f'tollgate_cache_lookups_total{{result="{result}"}}'] = "0"
    expected.update(histogram_zero("tollgate_cache_lookup_duration_seconds"))
    for name in ("reserved", "charged"):
        expected[f"tollgate_tokens_{name}_total"] = "0"
    expected["tollgate_settle_capped_total"] = "0"
    return expected


def test_a_fresh_app_exports_exactly_the_declared_series_at_zero(tmp_path: Path) -> None:
    gateway = LogGateway(tmp_path, extra_env=TOKEN_ENV)
    fresh = scraped(gateway)
    assert fresh == expected_fresh(["first", "second"], with_metrics_path=True)
    assert not any(key.startswith("tollgate_http_requests_total") for key in fresh)


def test_the_metrics_path_series_exist_only_when_the_endpoint_does(tmp_path: Path) -> None:
    gateway = LogGateway(tmp_path)
    assert scraped(gateway) == expected_fresh(["first", "second"], with_metrics_path=False)


def test_the_first_request_adds_one_status_series_and_later_ones_follow_in_order(
    tmp_path: Path,
) -> None:
    gateway = LogGateway(tmp_path, extra_env=TOKEN_ENV)
    gateway.client.get("/health")
    gateway.client.get("/health")
    gateway.client.get("/nope")
    gateway.client.get("/health?x=1")
    gateway.client.get("/other-nope")
    counted = {k: v for k, v in scraped(gateway).items() if k.startswith("tollgate_http_requests")}
    assert counted == {
        'tollgate_http_requests_total{path="/health",status="200"}': "3",
        'tollgate_http_requests_total{path="other",status="404"}': "2",
    }


FIRST = "hello there world"
SECOND = "bonjour le monde!!"
THIRD = "hola mundo amigos!"
FOURTH = "ciao mondo bello!!"
PROMPT_VECTORS: dict[str, tuple[float, ...]] = {
    FIRST: (1.0, 0.0, 0.0, 0.0),
    SECOND: (0.0, 1.0, 0.0, 0.0),
    THIRD: (0.0, 0.0, 1.0, 0.0),
    FOURTH: (0.0, 0.0, 0.0, 1.0),
}
SEQUENCE_TABLE: dict[str, Any] = {
    "providers": {
        "flaky": {"type": "mock"},
        "good": {"type": "mock"},
        "oversize": {"type": "mock"},
        "huge": {"type": "mock"},
    },
    "routes": {
        "fb": [{"provider": "flaky"}, {"provider": "good"}],
        "solo-good": [{"provider": "good"}],
        "big": [{"provider": "oversize"}],
        "huge": [{"provider": "huge"}],
    },
}


def histogram_of(name: str, labels: str, observations: list[float]) -> dict[str, str]:
    """The non-zero series a histogram holds after these observations, computed independently."""
    prefix = f"{labels}," if labels else ""
    plain = f"{{{labels}}}" if labels else ""
    expected: dict[str, str] = {}
    for bound in BOUNDS:
        limit = float("inf") if bound == "+Inf" else float(bound)
        count = sum(1 for seen in observations if seen <= limit)
        if count:
            expected[f'{name}_bucket{{{prefix}le="{bound}"}}'] = str(count)
    expected[f"{name}_sum{plain}"] = repr(sum(observations))
    expected[f"{name}_count{plain}"] = str(len(observations))
    return expected


def test_the_scripted_sequence_gives_the_exact_value_of_every_series(tmp_path: Path) -> None:
    monotonic = FakeMonotonicClock()
    embedder = FakeEmbedder(PROMPT_VECTORS)
    providers = {
        "flaky": ScriptedProvider(
            "flaky", error=ProviderError("timeout"), on_call=advancing(monotonic, 0.5)
        ),
        "good": ScriptedProvider("good", on_call=advancing(monotonic, 0.25)),
        "oversize": ScriptedProvider(
            "oversize", error=ReplyTooLargeError(200), on_call=advancing(monotonic, 2.0)
        ),
        "huge": ScriptedProvider(
            "huge", prompt_tokens=700, completion_tokens=301, on_call=advancing(monotonic, 1.0)
        ),
    }
    gateway = LogGateway(
        tmp_path,
        cache=True,
        embedder=embedder,
        table=SEQUENCE_TABLE,
        providers=providers,
        extra_env=TOKEN_ENV,
        monotonic=monotonic,
    )
    assert gateway.post(FIRST, model="fb").status_code == 200  # a miss after one fallback
    assert gateway.post(FIRST, model="fb").status_code == 200  # a hit
    embedder.error = EmbeddingError("timeout", None)
    assert gateway.post(SECOND, model="solo-good").status_code == 200  # skip: embedder_failed
    embedder.error = None
    assert gateway.post(FIRST, model="fb", max_tokens=5000).status_code == 429
    assert gateway.post(FIRST, model="no-such-model").status_code == 404
    assert gateway.post(THIRD, model="big").status_code == 502  # a reply over the cap
    assert gateway.post(FOURTH, model="huge").status_code == 200  # the settle was capped
    chat = "/v1/chat/completions"
    expected = {
        f'tollgate_http_requests_total{{path="{chat}",status="200"}}': "4",
        f'tollgate_http_requests_total{{path="{chat}",status="429"}}': "1",
        f'tollgate_http_requests_total{{path="{chat}",status="404"}}': "1",
        f'tollgate_http_requests_total{{path="{chat}",status="502"}}': "1",
        'tollgate_chat_completions_total{provider="good",cache="miss"}': "1",
        'tollgate_chat_completions_total{provider="good",cache="hit"}': "1",
        'tollgate_chat_completions_total{provider="good",cache="skip"}': "1",
        'tollgate_chat_completions_total{provider="huge",cache="miss"}': "1",
        'tollgate_provider_attempts_total{provider="flaky",outcome="timeout"}': "1",
        'tollgate_provider_attempts_total{provider="good",outcome="ok"}': "2",
        'tollgate_provider_attempts_total{provider="oversize",outcome="reply_too_large"}': "1",
        'tollgate_provider_attempts_total{provider="huge",outcome="ok"}': "1",
        'tollgate_cache_lookups_total{result="miss"}': "3",
        'tollgate_cache_lookups_total{result="hit"}': "1",
        'tollgate_cache_lookups_total{result="embedder_failed"}': "1",
        "tollgate_tokens_reserved_total": "55",
        # 37 + 0 (hit) + 37 + 11 (a bad_response stays charged as reserved) + 1000 (capped)
        "tollgate_tokens_charged_total": "1085",
        "tollgate_settle_capped_total": "1",
    }
    expected |= histogram_of(
        "tollgate_http_request_duration_seconds",
        f'path="{chat}"',
        [0.75, 0.0, 0.25, 0.0, 0.0, 2.0, 1.0],
    )
    for name, seen in (
        ("flaky", [0.5]),
        ("good", [0.25, 0.25]),
        ("oversize", [2.0]),
        ("huge", [1.0]),
    ):
        expected |= histogram_of(
            "tollgate_provider_attempt_duration_seconds", f'provider="{name}"', seen
        )
    expected |= histogram_of("tollgate_cache_lookup_duration_seconds", "", [0.0] * 5)
    assert nonzero(scraped(gateway)) == nonzero(expected)


def test_a_200_with_the_cache_off_is_counted_as_off_and_no_lookup_is_counted(
    tmp_path: Path,
) -> None:
    gateway = LogGateway(tmp_path)
    assert gateway.post(model="solo-first").status_code == 200
    series = nonzero(scraped(gateway))
    assert series['tollgate_chat_completions_total{provider="first",cache="off"}'] == "1"
    assert not any(key.startswith("tollgate_cache_lookups_total") for key in series)
    assert not any(key.startswith("tollgate_cache_lookup_duration") for key in series)
    assert 'tollgate_chat_completions_total{provider="first",cache="skip"}' not in series


def test_a_skip_counts_its_own_reason_and_never_a_miss(tmp_path: Path) -> None:
    gateway = LogGateway(tmp_path, cache=True)
    body = {"role": "assistant", "content": FIRST}
    response = gateway.client.post(
        "/v1/chat/completions", json={"model": "solo-first", "messages": [body]}
    )
    assert response.status_code == 200
    lookups = {k: v for k, v in scraped(gateway).items() if k.startswith("tollgate_cache_lookups")}
    assert nonzero(lookups) == {'tollgate_cache_lookups_total{result="not_eligible"}': "1"}
    skipped = 'tollgate_chat_completions_total{provider="first",cache="skip"}'
    assert scraped(gateway)[skipped] == "1"


def test_a_failed_route_counts_attempts_and_tokens_but_no_completion(tmp_path: Path) -> None:
    gateway = LogGateway(
        tmp_path, first_error=ProviderError("timeout"), second_error=ProviderError("connection")
    )
    assert gateway.post().status_code == 502
    series = nonzero(scraped(gateway))
    assert series['tollgate_provider_attempts_total{provider="first",outcome="timeout"}'] == "1"
    assert series['tollgate_provider_attempts_total{provider="second",outcome="connection"}'] == "1"
    assert series["tollgate_tokens_reserved_total"] == "11"
    assert "tollgate_tokens_charged_total" not in series  # refunded in full: charged 0
    assert not any(key.startswith("tollgate_chat_completions_total") for key in series)
    assert "tollgate_settle_capped_total" not in series


@pytest.mark.parametrize(
    ("seconds", "first_bucket"),
    [
        (0.0, "0.001"),
        (0.001, "0.001"),
        (0.0011, "0.0025"),
        (0.25, "0.25"),
        (0.2501, "0.5"),
        (60.0, "60.0"),
        (61.0, "+Inf"),
    ],
)
def test_a_duration_lands_in_its_bucket_and_one_on_a_bound_lands_in_that_bound(
    tmp_path: Path, seconds: float, first_bucket: str
) -> None:
    monotonic = FakeMonotonicClock()
    gateway = LogGateway(
        tmp_path, monotonic=monotonic, on_first_call=advancing(monotonic, seconds), cache=False
    )
    assert gateway.post(model="solo-first").status_code == 200
    series = scraped(gateway)
    prefix = 'tollgate_http_request_duration_seconds_bucket{path="/v1/chat/completions",le='
    counts = [series[f'{prefix}"{bound}"}}'] for bound in BOUNDS]
    start = BOUNDS.index(first_bucket)
    assert counts == ["0"] * start + ["1"] * (len(BOUNDS) - start)
    total = 'tollgate_http_request_duration_seconds_sum{path="/v1/chat/completions"}'
    assert series[total] == repr(seconds)


def test_no_metric_name_equals_another_name_plus_a_histogram_suffix(tmp_path: Path) -> None:
    text = LogGateway(tmp_path, extra_env=TOKEN_ENV).app.state.metrics.render()
    types = re.findall(r"^# TYPE (\S+) (\S+)$", text, flags=re.MULTILINE)
    names = [name for name, _ in types]
    assert len(names) == len(set(names)) == 10
    histograms = [name for name, kind in types if kind == "histogram"]
    assert len(histograms) == 3
    taken = set(names)
    for name in histograms:
        for suffix in ("_bucket", "_sum", "_count"):
            assert name + suffix not in taken
    for name in names:  # a counter that ends in a suffix could shadow a histogram's series
        assert not name.endswith(("_bucket", "_sum", "_count"))


def test_no_label_is_method_and_an_odd_method_adds_no_value_to_any_label(tmp_path: Path) -> None:
    gateway = LogGateway(tmp_path, extra_env=TOKEN_ENV)
    for method in ("PURGE", "BREW", "get"):
        gateway.client.request(method, "/health")
    text = gateway.app.state.metrics.render()
    label_names = set(re.findall(r"[{,]([a-z_]+)=", text))
    assert label_names == {"path", "status", "provider", "cache", "outcome", "result", "le"}
    assert "PURGE" not in text
    assert "BREW" not in text


def test_the_log_and_the_metrics_both_see_each_request(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    gateway = LogGateway(tmp_path)
    with caplog.at_level("INFO", logger="tollgate.request"):
        gateway.post(model="solo-first")
    assert [r.name for r in caplog.records] == ["tollgate.request"]
    counted = 'tollgate_http_requests_total{path="/v1/chat/completions",status="200"}'
    assert scraped(gateway)[counted] == "1"


def test_the_default_route_table_exports_its_one_provider(tmp_path: Path) -> None:
    table: dict[str, Any] = {
        "providers": {"first": {"type": "mock"}},
        "routes": {"solo-first": [{"provider": "first"}]},
    }
    gateway = LogGateway(tmp_path, table=table)
    series = scraped(gateway)
    assert 'tollgate_provider_attempts_total{provider="first",outcome="ok"}' in series
    assert 'tollgate_provider_attempts_total{provider="second",outcome="ok"}' not in series


def test_a_provider_name_with_a_quote_and_a_backslash_is_escaped_in_the_text(
    tmp_path: Path,
) -> None:
    backslash = chr(92)
    name = f'we"ird{backslash}name'
    table: dict[str, Any] = {
        "providers": {name: {"type": "mock"}},
        "routes": {"solo": [{"provider": name}]},
    }
    gateway = LogGateway(tmp_path, table=table, providers={name: ScriptedProvider(name)})
    assert gateway.post(model="solo").status_code == 200
    text = gateway.app.state.metrics.render()
    escaped = f'we{backslash}"ird{backslash * 2}name'
    assert f'tollgate_chat_completions_total{{provider="{escaped}",cache="off"}} 1\n' in text


def test_a_500_after_the_provider_answered_is_not_counted_as_a_completion(tmp_path: Path) -> None:
    gateway = LogGateway(tmp_path, settle_error=RuntimeError("settle down"))
    with pytest.raises(RuntimeError):
        gateway.post(model="solo-first")
    series = scraped(gateway)
    assert series['tollgate_chat_completions_total{provider="first",cache="off"}'] == "0"
    assert series['tollgate_provider_attempts_total{provider="first",outcome="ok"}'] == "1"
    assert series['tollgate_http_requests_total{path="/v1/chat/completions",status="500"}'] == "1"
