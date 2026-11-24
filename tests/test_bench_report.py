"""The load report in scripts/bench_load.py (T-407): latency and lag from the right timestamps,
pinned percentiles, the 10,000-sample p99 floor, the validity check, every ADR-0018 setting, no
key or route file content in any output, and a tiny in-process run against `create_app()`.
"""

import asyncio
import hashlib
import json
import math
import os
import platform
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.main import create_app
from tests.fakes import (
    ROOT,
    TEST_API_KEY,
    FakeClock,
    FakeMonotonicClock,
    load_script,
    make_settings,
)

bench = load_script("bench_load")

BODY_BYTES = 79
BODY_SHA256 = "6a4d2343e3df5c4e0bcd26e7ef31f09c15091659e673995321c939a9da807efd"
HOST = bench.HostFacts(
    git_commit="0123456789abcdef0123456789abcdef01234567",
    python_version="3.13.9",
    os="TestOS-1.0",
    cpu_count=8,
)
BASE_ARGS = [
    "--url",
    "http://gateway.test",
    "--rate",
    "5",
    "--duration-seconds",
    "2",
    "--scenario",
    "C",
    "--same-machine",
]
TOP_LEVEL_KEYS = {
    "valid",
    "invalid_reasons",
    "requests",
    "errors",
    "warmup_errors",
    "latency_seconds",
    "lag_seconds",
    "p99_withheld",
    "quantile_method",
    "achieved_rate_per_second",
    "achieved_rate_formula",
    "peak_in_flight",
    "generator_cpu_seconds",
    "settings",
}
SETTING_KEYS = {
    "scenario",
    "rate_per_second",
    "duration_seconds",
    "warmup_seconds",
    "max_connections",
    "limiter",
    "tokens_per_minute",
    "capacity_tokens",
    "routes_sha256_lf",
    "upstream_delay_ms",
    "server",
    "request_body_bytes",
    "request_body_sha256",
    "git_commit",
    "python_version",
    "os",
    "cpu_count",
    "same_machine",
}


def sample(
    latency_seconds: float = 0.015,
    lag_seconds: float = 0.001,
    *,
    status: int = 200,
    error: str | None = None,
    warmup: bool = False,
    due_seconds: float = 0.0,
) -> Any:
    """A sample due at `due_seconds`; with the default due of 0.0 every subtraction is exact."""
    return bench.Sample(
        index=0,
        due_seconds=due_seconds,
        hand_over_seconds=due_seconds + lag_seconds,
        end_seconds=due_seconds + latency_seconds,
        status=None if error else status,
        transport_error=error,
        warmup=warmup,
    )


# Criterion 1: latency and lag from the right timestamps; warm-up counted apart and left out.


def test_latency_is_from_due_to_end_and_lag_from_due_to_hand_over() -> None:
    summary = bench.summarize([sample(0.015, 0.005)])
    assert summary.latency_p50_seconds == 0.015
    assert summary.latency_max_seconds == 0.015
    assert summary.lag_p50_seconds == 0.005
    assert summary.lag_max_seconds == 0.005


def test_warmup_requests_are_counted_apart_and_left_out_of_every_figure() -> None:
    warmups = [sample(9.0, 8.0, status=503, warmup=True, due_seconds=-1.0) for _ in range(3)]
    warmups.append(sample(error="ConnectError", warmup=True, due_seconds=-1.0))
    measured = [sample(0.015, 0.001), sample(0.010, 0.0005, due_seconds=0.5)]
    summary = bench.summarize([*warmups, *measured])
    assert (summary.total_requests, summary.warmup_requests, summary.measured_requests) == (6, 4, 2)
    assert summary.latency_max_seconds == 0.015
    assert summary.lag_max_seconds == 0.001
    assert (summary.errors_by_status, summary.transport_errors) == ({}, {})
    assert summary.warmup_errors_by_status == {"503": 3}
    assert summary.warmup_transport_errors == {"ConnectError": 1}
    assert summary.achieved_rate_per_second == 2 / 0.51
    # Warm-up errors are reported apart and do not make the run invalid (owner decision).
    assert summary.valid


def test_there_is_no_achieved_rate_over_an_empty_span() -> None:
    summary = bench.summarize([sample(0.0, 0.0)])
    assert summary.achieved_rate_per_second is None
    assert "- Achieved rate: n/a (" in bench.render_markdown(make_report(summary))


# Criterion 2: percentiles on a known sample, and the p99 floor.


def test_percentiles_are_pinned_on_0_to_100() -> None:
    values = [float((k * 37) % 101) for k in range(101)]  # 0 to 100, shuffled
    assert sorted(values) == [float(k) for k in range(101)]
    assert bench.percentiles(values) == bench.Percentiles(50.0, 95.0, 99.0)


def test_the_p99_is_published_at_10000_measured_requests() -> None:
    samples = [sample(1.0, 0.0)] * 9_800 + [sample(2.0, 0.0)] * 200
    summary = bench.summarize(samples)
    assert summary.measured_requests == 10_000
    assert summary.latency_p99_seconds == 2.0
    assert summary.lag_p99_seconds == 0.0
    report = bench.report_as_json(make_report(summary))
    assert report["p99_withheld"] is None


@pytest.mark.parametrize("warmup_count", [0, 1])
def test_the_p99_is_too_few_samples_at_9999_measured_requests(warmup_count: int) -> None:
    samples = [sample(warmup=True)] * warmup_count + [sample(1.0, 0.0)] * 9_999
    summary = bench.summarize(samples)
    assert summary.measured_requests == 9_999
    assert summary.latency_p99_seconds is None
    assert summary.lag_p99_seconds is None
    assert summary.latency_p50_seconds == 1.0
    report = bench.report_as_json(make_report(summary))
    assert report["p99_withheld"] == "too few samples"
    assert report["latency_seconds"]["p99"] is None
    assert (
        "| p99 | too few samples | too few samples |"
        in bench.render_markdown(make_report(summary)).splitlines()
    )


# Criterion 3: the validity check.


@pytest.mark.parametrize("count", [9_999, 10_000])
def test_a_lag_p99_of_exactly_10_percent_is_valid_and_just_above_is_not(count: int) -> None:
    assert 0.1 * 0.625 == 0.0625  # the boundary is exact in binary
    at_limit = bench.summarize([sample(0.625, 0.0625)] * count)
    assert at_limit.valid
    above = bench.summarize([sample(0.625, math.nextafter(0.0625, math.inf))] * count)
    assert not above.valid
    assert above.invalid_reasons == ("lag p99 above 10% of latency p99",)


def test_validity_uses_the_lag_p99_not_the_maximum_or_the_median() -> None:
    one_outlier = [sample(1.0, 0.05)] * 100 + [sample(1.0, 0.5)]
    assert bench.summarize(one_outlier).valid  # the maximum is 0.5, the p99 0.05
    two_outliers = [sample(1.0, 0.05)] * 99 + [sample(1.0, 0.5)] * 2
    assert not bench.summarize(two_outliers).valid  # the median is 0.05, the p99 0.5


@pytest.mark.parametrize(
    ("failure", "reason"),
    [(sample(status=429), "non-200 responses"), (sample(error="ReadTimeout"), "transport errors")],
)
def test_one_failed_request_makes_the_run_invalid(failure: Any, reason: str) -> None:
    summary = bench.summarize([sample()] * 9 + [failure])
    assert not summary.valid
    assert summary.invalid_reasons == (reason,)


def test_errors_are_counted_by_status_and_by_transport_error() -> None:
    statuses = [sample(status=code) for code in (503, 200, 503, 429)]
    errors = [sample(error=name) for name in ("ConnectError", "ReadTimeout", "ConnectError")]
    summary = bench.summarize([*statuses, *errors])
    assert summary.errors_by_status == {"429": 1, "503": 2}
    assert summary.transport_errors == {"ConnectError": 2, "ReadTimeout": 1}
    assert summary.invalid_reasons == ("non-200 responses", "transport errors")


# Criterion 4: every ADR-0018 setting, and no key or route file content in any output.


def make_report(summary: Any, **settings: Any) -> Any:
    values: dict[str, Any] = {
        "scenario": "B",
        "rate_per_second": 50,
        "duration_seconds": 200,
        "warmup_seconds": 10,
        "max_connections": None,
        "limiter": None,
        "tokens_per_minute": None,
        "capacity_tokens": None,
        "routes_sha256": None,
        "upstream_delay_ms": None,
        "server": None,
        "same_machine": True,
    }
    values.update(settings)
    return bench.LoadReport(
        summary=summary,
        peak_in_flight=3,
        generator_cpu_seconds=1.5,
        settings=bench.RunSettings(**values),
        host=HOST,
    )


class Recorder(httpx.MockTransport):
    """Answers every request with `status` at once and records each request."""

    def __init__(self, status: int = 200) -> None:
        self.requests: list[httpx.Request] = []

        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return httpx.Response(status, json={})

        super().__init__(handle)


def run_main(
    argv: list[str],
    transport: httpx.AsyncBaseTransport,
    *,
    environ: dict[str, str] | None = None,
    cpu_readings: tuple[float, float] = (0.0, 0.0),
) -> int:
    clock = FakeMonotonicClock(50.0)

    async def sleep(seconds: float) -> None:
        await asyncio.sleep(0)
        clock.advance(seconds)

    readings: Iterator[float] = iter(cpu_readings)
    code: int = bench.main(
        argv,
        environ=environ or {},
        transport=transport,
        clock=clock,
        sleep=sleep,
        cpu_seconds=lambda: next(readings),
        host=HOST,
    )
    return code


def test_the_report_holds_every_adr_0018_setting(tmp_path: Path) -> None:
    routes = tmp_path / "routes.json"
    routes.write_bytes(b'{"providers": {}}\r\n')
    output = tmp_path / "report.json"
    argv = [
        *BASE_ARGS[:-2],
        "B",
        "--separate-machine",
        "--warmup-seconds",
        "1",
        "--max-connections",
        "64",
        "--limiter",
        "redis",
        "--tokens-per-minute",
        "600000",
        "--capacity-tokens",
        "20000",
        "--routes-file",
        str(routes),
        "--upstream-delay-ms",
        "50",
        "--server",
        "compose",
        "--output",
        str(output),
    ]
    assert run_main(argv, Recorder()) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert set(report) == TOP_LEVEL_KEYS
    assert report["settings"] == {
        "scenario": "B",
        "rate_per_second": 5,
        "duration_seconds": 2,
        "warmup_seconds": 1,
        "max_connections": 64,
        "limiter": "redis",
        "tokens_per_minute": 600000,
        "capacity_tokens": 20000,
        "routes_sha256_lf": hashlib.sha256(b'{"providers": {}}\n').hexdigest(),
        "upstream_delay_ms": 50,
        "server": "compose",
        "request_body_bytes": BODY_BYTES,
        "request_body_sha256": BODY_SHA256,
        "git_commit": "0123456789abcdef0123456789abcdef01234567",
        "python_version": "3.13.9",
        "os": "TestOS-1.0",
        "cpu_count": 8,
        "same_machine": False,
    }
    assert report["requests"] == {"total": 15, "warmup": 5, "measured": 10}
    assert report["quantile_method"] == 'statistics.quantiles(n=100, method="inclusive")'


def test_settings_not_given_are_null_in_json_and_n_a_in_markdown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "report.json"
    argv = [*BASE_ARGS, "--warmup-seconds", "0", "--output", str(output)]
    assert run_main(argv, Recorder()) == 0
    settings = json.loads(output.read_text(encoding="utf-8"))["settings"]
    for name in ("max_connections", "limiter", "tokens_per_minute", "capacity_tokens"):
        assert settings[name] is None, name
    for name in ("routes_sha256_lf", "upstream_delay_ms", "server"):
        assert settings[name] is None, name
    assert (settings["warmup_seconds"], settings["same_machine"]) == (0, True)
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "# Load run: scenario C, valid"
    assert "- Connection cap: none" in lines
    assert "- Limiter: n/a; tokens per minute n/a; capacity n/a" in lines
    assert "- Route file SHA-256 (with LF line endings): n/a" in lines
    assert "- Upstream delay: n/a" in lines
    assert "- Server: n/a" in lines
    assert "- Generator and server: same machine (they compete for the CPU)" in lines


def test_the_markdown_shows_the_figures_and_every_setting() -> None:
    summary = bench.summarize([sample(0.015, 0.0015), sample(0.025, 0.0005, status=503)])
    report = make_report(
        summary,
        max_connections=64,
        limiter="memory",
        tokens_per_minute=600000,
        capacity_tokens=20000,
        routes_sha256="ab" * 32,
        upstream_delay_ms=50,
        server="uvicorn",
        same_machine=False,
    )
    lines = bench.render_markdown(report).splitlines()
    assert lines[:8] == [
        "# Load run: scenario B, invalid: non-200 responses",
        "",
        "| Figure | Latency (ms) | Lag (ms) |",
        "| --- | --- | --- |",
        "| p50 | 20.000 | 1.000 |",
        "| p95 | 24.500 | n/a |",
        "| p99 | too few samples | too few samples |",
        "| max | 25.000 | 1.500 |",
    ]
    json_report = bench.report_as_json(report)
    assert json_report["latency_seconds"] == {"p50": 0.02, "p95": 0.0245, "p99": None, "max": 0.025}
    assert json_report["lag_seconds"] == {"p50": 0.001, "p99": None, "max": 0.0015}
    assert json_report["achieved_rate_per_second"] == 80.0  # 2 requests over 0.025 s
    assert json_report["peak_in_flight"] == 3
    for line in [
        "- Requests: 2 measured, 0 warm-up (left out), 2 sent",
        "- Errors: 503: 1",
        "- Warm-up errors: none",
        "- Achieved rate: 80.00 requests per second (measured requests / (last measured end"
        " - first measured due))",
        "- Peak in flight: 3",
        "- Generator CPU time: 1.500 s",
        "- Scenario: B",
        "- Rate: 50 requests per second for 200 s after 10 s of warm-up",
        "- Connection cap: 64",
        "- Limiter: memory; tokens per minute 600000; capacity 20000",
        f"- Route file SHA-256 (with LF line endings): {'ab' * 32}",
        "- Upstream delay: 50 ms",
        "- Server: uvicorn",
        f"- Request body: {BODY_BYTES} bytes, SHA-256 {BODY_SHA256}",
        "- Git commit: 0123456789abcdef0123456789abcdef01234567",
        "- Python 3.13.9 on TestOS-1.0, 8 CPUs",
        "- Generator and server: separate machines",
    ]:
        assert line in lines, line


def test_an_unknown_git_commit_is_shown_as_unknown() -> None:
    report = bench.LoadReport(
        summary=bench.summarize([sample()]),
        peak_in_flight=1,
        generator_cpu_seconds=0.0,
        settings=make_report(bench.summarize([sample()])).settings,
        host=bench.HostFacts(git_commit=None, python_version="3.13.9", os="x", cpu_count=None),
    )
    lines = bench.render_markdown(report).splitlines()
    assert "- Git commit: unknown" in lines
    assert "- Python 3.13.9 on x, n/a CPUs" in lines


def test_neither_the_key_nor_the_route_file_content_appears_in_any_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    key_marker = "key-marker-91c2"
    routes_marker = "routes-marker-5e7a"
    routes = tmp_path / "routes.json"
    routes.write_text(json.dumps({"note": routes_marker}), encoding="utf-8")
    output = tmp_path / "report.json"
    transport = Recorder()
    argv = [*BASE_ARGS, "--api-key-env", "BENCH_KEY", "--routes-file", str(routes)]
    code = run_main([*argv, "--output", str(output)], transport, environ={"BENCH_KEY": key_marker})
    assert code == 0
    # The key was read and sent, so its absence below is not vacuous.
    assert {r.headers["authorization"] for r in transport.requests} == {f"Bearer {key_marker}"}
    captured = capsys.readouterr()
    written = output.read_text(encoding="utf-8")
    for text in (captured.out, captured.err, written):
        assert key_marker not in text
        assert routes_marker not in text
    assert "BENCH_KEY" not in written


@pytest.mark.parametrize(
    ("environ", "message"),
    [
        ({}, "is not set or is blank"),
        ({"BENCH_KEY": "  "}, "is not set or is blank"),
        ({"BENCH_KEY": "caf\u00e9-key"}, "must hold printable ASCII"),
        ({"BENCH_KEY": "key\x7fmore"}, "must hold printable ASCII"),
    ],
)
def test_a_missing_or_unusable_key_fails_without_a_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], environ: dict[str, str], message: str
) -> None:
    output = tmp_path / "report.json"
    transport = Recorder()
    argv = [*BASE_ARGS, "--api-key-env", "BENCH_KEY", "--output", str(output)]
    assert run_main(argv, transport, environ=environ) == 1
    captured = capsys.readouterr()
    assert captured.err == f"error: the variable named by --api-key-env {message}\n"
    assert captured.out == ""
    assert not output.exists()
    assert transport.requests == []


def test_an_unreadable_route_file_fails_without_a_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = [*BASE_ARGS, "--routes-file", str(tmp_path / "missing.json")]
    assert run_main(argv, Recorder()) == 1
    captured = capsys.readouterr()
    assert captured.err == "error: cannot read the --routes-file\n"
    assert captured.out == ""


def test_an_output_in_a_missing_directory_fails_before_any_load_is_sent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    transport = Recorder()
    argv = [*BASE_ARGS, "--output", str(tmp_path / "no-such-dir" / "report.json")]
    assert run_main(argv, transport) == 1
    assert capsys.readouterr().err == "error: cannot write the --output file\n"
    assert transport.requests == []


def test_an_output_that_cannot_be_opened_fails_after_the_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "a-directory"
    output.mkdir()
    assert run_main([*BASE_ARGS, "--output", str(output)], Recorder()) == 1
    captured = capsys.readouterr()
    assert captured.err == "error: cannot write the --output file\n"
    assert captured.out == ""


def test_the_generator_cpu_time_is_the_difference_around_the_run(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    code = run_main([*BASE_ARGS, "--output", str(output)], Recorder(), cpu_readings=(2.0, 2.75))
    assert code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["generator_cpu_seconds"] == 0.75


def test_an_invalid_run_exits_3_and_still_prints_and_writes_its_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "report.json"
    assert run_main([*BASE_ARGS, "--output", str(output)], Recorder(503)) == 3
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["valid"] is False
    assert report["errors"] == {"by_status": {"503": 10}, "transport": {}}
    assert capsys.readouterr().out.startswith(
        "# Load run: scenario C, invalid: non-200 responses\n"
    )


class RecordingFactory:
    """Stands in for make_client: records its arguments and returns a client on a MockTransport."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int | None]] = []

    def __call__(self, base_url: str, *, max_connections: int | None = None) -> httpx.AsyncClient:
        self.calls.append((base_url, max_connections))
        return httpx.AsyncClient(base_url=base_url, transport=Recorder())


@pytest.mark.parametrize(("extra", "cap"), [([], None), (["--max-connections", "64"], 64)])
def test_the_real_client_gets_the_connection_cap_given(
    monkeypatch: pytest.MonkeyPatch, extra: list[str], cap: int | None
) -> None:
    factory = RecordingFactory()
    monkeypatch.setattr(bench, "make_client", factory)
    clock = FakeMonotonicClock(0.0)

    async def sleep(seconds: float) -> None:
        await asyncio.sleep(0)
        clock.advance(seconds)

    code = bench.main(
        [*BASE_ARGS, *extra],
        environ={},
        clock=clock,
        sleep=sleep,
        cpu_seconds=lambda: 0.0,
        host=HOST,
    )
    assert code == 0
    assert factory.calls == [("http://gateway.test", cap)]


@pytest.mark.parametrize(
    "argv",
    [
        BASE_ARGS[:-1],  # neither machine flag
        [*BASE_ARGS, "--separate-machine"],  # both
        [*BASE_ARGS, "--server", "docker"],
        [*BASE_ARGS, "--limiter", "postgres"],
        [*BASE_ARGS, "--rate", "0"],
        [*BASE_ARGS, "--warmup-seconds", "-1"],
        [*BASE_ARGS, "--scenario", "D"],
        ["--url", "  ", *BASE_ARGS[2:]],
        ["--url", "ftp://gateway.test", *BASE_ARGS[2:]],
        ["--url", "http://", *BASE_ARGS[2:]],
    ],
)
def test_bad_usage_exits_2(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        run_main(argv, Recorder())
    assert exit_info.value.code == 2


def test_a_padded_url_is_accepted_and_stripped() -> None:
    transport = Recorder()
    assert run_main(["--url", " http://gateway.test ", *BASE_ARGS[2:]], transport) == 0
    assert str(transport.requests[0].url) == "http://gateway.test/v1/chat/completions"


@pytest.mark.parametrize(
    "argv",
    [
        [*BASE_ARGS, "--uurl", "http://user:secret-91@host"],
        [*BASE_ARGS, "--scenario", "http://user:secret-91@host"],
        [*BASE_ARGS, "--rate", "http://user:secret-91@host"],
        [*BASE_ARGS, "--scenario", "http://user:it's-secret-91@host"],  # shown in double quotes
    ],
)
def test_a_value_in_the_wrong_place_is_not_repeated(
    capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    with pytest.raises(SystemExit):
        run_main(argv, Recorder())
    assert "secret-91" not in capsys.readouterr().err


# The host facts, and the git commit: only a full hash from a successful `git rev-parse HEAD`.


def test_host_facts_come_from_this_interpreter_and_machine() -> None:
    facts = bench.collect_host_facts()
    assert facts.python_version == platform.python_version()
    assert facts.os == platform.platform()
    assert facts.cpu_count == os.cpu_count()


def completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["git"], returncode, stdout=stdout, stderr="")


def test_git_commit_reads_head() -> None:
    calls: list[list[str]] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert kwargs["cwd"] == ROOT
        return completed("0123456789abcdef0123456789abcdef01234567\n")

    assert bench.git_commit(run) == "0123456789abcdef0123456789abcdef01234567"
    assert calls == [["git", "rev-parse", "HEAD"]]


@pytest.mark.parametrize(
    ("stdout", "returncode"),
    [("0123456789abcdef0123456789abcdef01234567\n", 128), ("fatal: not a repo\n", 0), ("", 0)],
)
def test_git_commit_is_none_without_a_full_hash(stdout: str, returncode: int) -> None:
    assert bench.git_commit(lambda *args, **kwargs: completed(stdout, returncode)) is None


@pytest.mark.parametrize(
    "error", [FileNotFoundError("git"), subprocess.TimeoutExpired(["git"], 10.0)]
)
def test_git_commit_is_none_when_git_cannot_run(error: Exception) -> None:
    def run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise error

    assert bench.git_commit(run) is None


# Criterion 5: a tiny in-process run against create_app() has the report's shape.


def test_a_tiny_in_process_run_against_the_gateway_has_the_report_shape(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    routes = ROOT / "deploy" / "bench" / "routes.mock.json"
    settings = make_settings(TOLLGATE_ROUTES_FILE=str(routes), TOLLGATE_TOKENS_PER_MINUTE="100000")
    transport = httpx.ASGITransport(app=create_app(settings, FakeClock(1000.0)))
    output = tmp_path / "report.json"
    argv = [
        *BASE_ARGS,
        "--duration-seconds",
        "3",
        "--warmup-seconds",
        "1",
        "--api-key-env",
        "BENCH_KEY",
        "--routes-file",
        str(routes),
        "--output",
        str(output),
    ]
    code = run_main(argv, transport, environ={"BENCH_KEY": TEST_API_KEY})
    report = json.loads(output.read_text(encoding="utf-8"))
    assert set(report) == TOP_LEVEL_KEYS
    assert set(report["settings"]) == SETTING_KEYS
    assert report["requests"] == {"total": 20, "warmup": 5, "measured": 15}
    assert report["errors"] == {"by_status": {}, "transport": {}}
    assert report["warmup_errors"] == {"by_status": {}, "transport": {}}
    assert set(report["latency_seconds"]) == {"p50", "p95", "p99", "max"}
    assert set(report["lag_seconds"]) == {"p50", "p99", "max"}
    assert report["latency_seconds"]["p99"] is None
    assert report["p99_withheld"] == "too few samples"
    assert report["settings"]["routes_sha256_lf"] == bench.dataset_sha256(routes.read_bytes())
    assert code == (0 if report["valid"] else 3)
    out = capsys.readouterr().out.splitlines()
    assert "| Figure | Latency (ms) | Lag (ms) |" in out
