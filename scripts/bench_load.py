"""Send load at a fixed arrival rate and report the run with its settings (T-406, T-407, ADR-0018).

Usage:
  python scripts/bench_load.py --url URL --rate N --duration-seconds S --scenario {A,B,C}
      (--same-machine | --separate-machine) [--warmup-seconds S] [--api-key-env NAME]
      [--max-connections N] [--limiter {memory,redis}] [--tokens-per-minute N]
      [--capacity-tokens N] [--routes-file PATH] [--upstream-delay-ms N]
      [--server {uvicorn,compose}] [--output report.json]

Request i is due at the start plus i divided by the rate, and is sent as its own task without
waiting for earlier answers (an open loop), so a slow answer never delays the next request.
Latency runs from the due time to the end of the response; lag runs from the due time to the
hand-over to httpx. Warm-up requests are sent, counted apart and left out of every figure.

The key is read from the variable named by --api-key-env and is never printed or written; nor
are the URL or the route file's content (only its SHA-256). Exit codes: 0 for a valid run, 3 for
an invalid run (the report is still printed and written), 1 when no report is produced, 2 on bad
usage.
"""

import argparse
import asyncio
import hashlib
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

import httpx

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # running a script puts scripts/ first, not the repository root
    sys.path.insert(0, str(ROOT))

from app.cache.evaluation import dataset_sha256  # noqa: E402
from app.clock import MonotonicClock, SystemMonotonicClock  # noqa: E402

type Sleep = Callable[[float], Awaitable[None]]

CHAT_PATH = "/v1/chat/completions"
DEFAULT_TIMEOUT_SECONDS = 30.0
# One fixed body for every request, so request size never varies within a run.
REQUEST_BODY = json.dumps(
    {"model": "bench", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 16},
    separators=(",", ":"),
).encode("utf-8")
JSON_HEADERS: Mapping[str, str] = {"Content-Type": "application/json"}


@dataclass(frozen=True, slots=True)
class LoadPlan:
    """`rate_per_second` requests each second for the warm-up, then for the measured duration."""

    rate_per_second: int
    duration_seconds: int
    warmup_seconds: int = 0

    def __post_init__(self) -> None:
        if self.rate_per_second < 1:
            raise ValueError("rate_per_second must be at least 1")
        if self.duration_seconds < 1:
            raise ValueError("duration_seconds must be at least 1")
        if self.warmup_seconds < 0:
            raise ValueError("warmup_seconds must not be negative")

    @property
    def request_count(self) -> int:
        return self.rate_per_second * (self.warmup_seconds + self.duration_seconds)

    @property
    def warmup_count(self) -> int:
        return self.rate_per_second * self.warmup_seconds


@dataclass(frozen=True, slots=True)
class Sample:
    """One request: its due, hand-over and end times on the run's monotonic clock, and either
    its HTTP status or the class name of its transport error (never the message, which can
    name the host).
    """

    index: int
    due_seconds: float
    hand_over_seconds: float
    end_seconds: float
    status: int | None
    transport_error: str | None
    warmup: bool


@dataclass(frozen=True, slots=True)
class RunResult:
    samples: tuple[Sample, ...]
    peak_in_flight: int


def due_time(start_seconds: float, index: int, rate_per_second: int) -> float:
    """Computed from the start each time, never accumulated, so rounding never drifts."""
    return start_seconds + index / rate_per_second


async def run_load(
    plan: LoadPlan,
    *,
    client: httpx.AsyncClient,
    clock: MonotonicClock,
    sleep: Sleep,
    headers: Mapping[str, str],
) -> RunResult:
    """Send `plan.request_count` requests, request i at its due time, and wait for every answer.

    Every request carries REQUEST_BODY with a JSON content type, plus `headers` (such as the
    gateway key). A transport error or a non-200 is recorded with its request; nothing httpx
    raises leaves the runner. The hand-over time is read inside the request's task just before
    the request is handed to the client, so a late start shows as the gap between due and
    hand-over.
    """
    request_headers = {**JSON_HEADERS, **headers}
    in_flight = 0
    peak_in_flight = 0

    async def one(index: int, due_seconds: float) -> Sample:
        nonlocal in_flight, peak_in_flight
        in_flight += 1
        peak_in_flight = max(peak_in_flight, in_flight)
        status: int | None = None
        transport_error: str | None = None
        hand_over_seconds = clock.monotonic_seconds()
        try:
            response = await client.post(CHAT_PATH, content=REQUEST_BODY, headers=request_headers)
            status = response.status_code
        except httpx.HTTPError as exc:
            transport_error = type(exc).__name__
        finally:
            in_flight -= 1
        return Sample(
            index=index,
            due_seconds=due_seconds,
            hand_over_seconds=hand_over_seconds,
            end_seconds=clock.monotonic_seconds(),
            status=status,
            transport_error=transport_error,
            warmup=index < plan.warmup_count,
        )

    start_seconds = clock.monotonic_seconds()
    tasks: list[asyncio.Task[Sample]] = []
    async with asyncio.TaskGroup() as group:
        for index in range(plan.request_count):
            due_seconds = due_time(start_seconds, index, plan.rate_per_second)
            await sleep(max(0.0, due_seconds - clock.monotonic_seconds()))
            tasks.append(group.create_task(one(index, due_seconds)))
    return RunResult(samples=tuple(task.result() for task in tasks), peak_in_flight=peak_in_flight)


def client_limits(max_connections: int | None) -> httpx.Limits:
    """No connection cap unless one is given: a cap would queue requests inside the client."""
    return httpx.Limits(max_connections=max_connections, max_keepalive_connections=max_connections)


def make_client(
    base_url: str,
    *,
    max_connections: int | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> httpx.AsyncClient:
    """A client for the run. It ignores proxy settings in the environment (`trust_env=False`),
    so the measured path is the one to `base_url`.
    """
    transport = httpx.AsyncHTTPTransport(limits=client_limits(max_connections))
    return httpx.AsyncClient(
        base_url=base_url,
        transport=transport,
        timeout=timeout_seconds,
        trust_env=False,
    )


# Part two (T-407): the summary, the validity check, the report and the command line.

P99_MIN_SAMPLES = 10_000  # a p99 rests on about n / 100 observations (ADR-0018)
MAX_LAG_SHARE = 0.1  # the lag p99 may be at most this share of the latency p99 (chosen)
TOO_FEW_SAMPLES = "too few samples"
QUANTILE_METHOD = 'statistics.quantiles(n=100, method="inclusive")'
ACHIEVED_RATE_FORMULA = "measured requests / (last measured end - first measured due)"
REASON_NON_200 = "non-200 responses"
REASON_TRANSPORT = "transport errors"
REASON_LAG = f"lag p99 above {MAX_LAG_SHARE:.0%} of latency p99"
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_INVALID = 3
GIT_TIMEOUT_SECONDS = 10.0
GIT_COMMIT = re.compile(r"[0-9a-f]{40}")
MILLISECONDS_PER_SECOND = 1000


class ScriptError(Exception):
    """A failure with a fixed message that holds no URL, key or file content."""


@dataclass(frozen=True, slots=True)
class Percentiles:
    p50_seconds: float
    p95_seconds: float
    p99_seconds: float


def percentiles(values: Sequence[float]) -> Percentiles:
    """Inclusive quantiles: with 100 cut points, cut k - 1 is the k-th percentile."""
    cuts = statistics.quantiles(values, n=100, method="inclusive")
    return Percentiles(p50_seconds=cuts[49], p95_seconds=cuts[94], p99_seconds=cuts[98])


@dataclass(frozen=True, slots=True)
class Summary:
    """The figures from the measured (non-warm-up) requests. A p99 below P99_MIN_SAMPLES is None:
    it is withheld, while validity is still computed from the raw p99s.
    """

    total_requests: int
    warmup_requests: int
    measured_requests: int
    errors_by_status: Mapping[str, int]
    transport_errors: Mapping[str, int]
    warmup_errors_by_status: Mapping[str, int]
    warmup_transport_errors: Mapping[str, int]
    latency_p50_seconds: float
    latency_p95_seconds: float
    latency_p99_seconds: float | None
    latency_max_seconds: float
    lag_p50_seconds: float
    lag_p99_seconds: float | None
    lag_max_seconds: float
    achieved_rate_per_second: float | None
    valid: bool
    invalid_reasons: tuple[str, ...]


def _errors(samples: Sequence[Sample]) -> tuple[dict[str, int], dict[str, int]]:
    statuses = Counter(str(s.status) for s in samples if s.status is not None and s.status != 200)
    transport = Counter(s.transport_error for s in samples if s.transport_error is not None)
    return dict(sorted(statuses.items())), dict(sorted(transport.items()))


def summarize(samples: Sequence[Sample]) -> Summary:
    measured = [s for s in samples if not s.warmup]
    warmup = [s for s in samples if s.warmup]
    if not measured:
        raise ValueError("a summary needs at least one measured request")
    latencies = [s.end_seconds - s.due_seconds for s in measured]
    lags = [s.hand_over_seconds - s.due_seconds for s in measured]
    latency = percentiles(latencies)
    lag = percentiles(lags)
    errors_by_status, transport_errors = _errors(measured)
    warmup_errors_by_status, warmup_transport_errors = _errors(warmup)
    reasons: list[str] = []
    if errors_by_status:
        reasons.append(REASON_NON_200)
    if transport_errors:
        reasons.append(REASON_TRANSPORT)
    if not lag.p99_seconds <= MAX_LAG_SHARE * latency.p99_seconds:
        reasons.append(REASON_LAG)
    published = len(measured) >= P99_MIN_SAMPLES
    span_seconds = max(s.end_seconds for s in measured) - min(s.due_seconds for s in measured)
    return Summary(
        total_requests=len(samples),
        warmup_requests=len(warmup),
        measured_requests=len(measured),
        errors_by_status=errors_by_status,
        transport_errors=transport_errors,
        warmup_errors_by_status=warmup_errors_by_status,
        warmup_transport_errors=warmup_transport_errors,
        latency_p50_seconds=latency.p50_seconds,
        latency_p95_seconds=latency.p95_seconds,
        latency_p99_seconds=latency.p99_seconds if published else None,
        latency_max_seconds=max(latencies),
        lag_p50_seconds=lag.p50_seconds,
        lag_p99_seconds=lag.p99_seconds if published else None,
        lag_max_seconds=max(lags),
        achieved_rate_per_second=len(measured) / span_seconds if span_seconds > 0 else None,
        valid=not reasons,
        invalid_reasons=tuple(reasons),
    )


@dataclass(frozen=True, slots=True)
class RunSettings:
    """What the run and the gateway ran with, as given on the command line (None: not given)."""

    scenario: str
    rate_per_second: int
    duration_seconds: int
    warmup_seconds: int
    max_connections: int | None
    limiter: str | None
    tokens_per_minute: int | None
    capacity_tokens: int | None
    routes_sha256: str | None
    upstream_delay_ms: int | None
    server: str | None
    same_machine: bool


@dataclass(frozen=True, slots=True)
class HostFacts:
    git_commit: str | None
    python_version: str
    os: str
    cpu_count: int | None


type GitRunner = Callable[..., subprocess.CompletedProcess[str]]


def git_commit(run: GitRunner = subprocess.run) -> str | None:
    """HEAD's full hash from the local repository, or None when git cannot give one."""
    try:
        completed = run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = completed.stdout.strip()
    if completed.returncode != 0 or not GIT_COMMIT.fullmatch(commit):
        return None
    return commit


def collect_host_facts() -> HostFacts:
    return HostFacts(
        git_commit=git_commit(),
        python_version=platform.python_version(),
        os=platform.platform(),
        cpu_count=os.cpu_count(),
    )


@dataclass(frozen=True, slots=True)
class LoadReport:
    summary: Summary
    peak_in_flight: int
    generator_cpu_seconds: float
    settings: RunSettings
    host: HostFacts


def report_as_json(report: LoadReport) -> dict[str, object]:
    summary, settings, host = report.summary, report.settings, report.host
    published = summary.latency_p99_seconds is not None
    return {
        "valid": summary.valid,
        "invalid_reasons": list(summary.invalid_reasons),
        "requests": {
            "total": summary.total_requests,
            "warmup": summary.warmup_requests,
            "measured": summary.measured_requests,
        },
        "errors": {"by_status": summary.errors_by_status, "transport": summary.transport_errors},
        "warmup_errors": {
            "by_status": summary.warmup_errors_by_status,
            "transport": summary.warmup_transport_errors,
        },
        "latency_seconds": {
            "p50": summary.latency_p50_seconds,
            "p95": summary.latency_p95_seconds,
            "p99": summary.latency_p99_seconds,
            "max": summary.latency_max_seconds,
        },
        "lag_seconds": {
            "p50": summary.lag_p50_seconds,
            "p99": summary.lag_p99_seconds,
            "max": summary.lag_max_seconds,
        },
        "p99_withheld": None if published else TOO_FEW_SAMPLES,
        "quantile_method": QUANTILE_METHOD,
        "achieved_rate_per_second": summary.achieved_rate_per_second,
        "achieved_rate_formula": ACHIEVED_RATE_FORMULA,
        "peak_in_flight": report.peak_in_flight,
        "generator_cpu_seconds": report.generator_cpu_seconds,
        "settings": {
            "scenario": settings.scenario,
            "rate_per_second": settings.rate_per_second,
            "duration_seconds": settings.duration_seconds,
            "warmup_seconds": settings.warmup_seconds,
            "max_connections": settings.max_connections,
            "limiter": settings.limiter,
            "tokens_per_minute": settings.tokens_per_minute,
            "capacity_tokens": settings.capacity_tokens,
            "routes_sha256_lf": settings.routes_sha256,  # taken with LF line endings
            "upstream_delay_ms": settings.upstream_delay_ms,
            "server": settings.server,
            "request_body_bytes": len(REQUEST_BODY),
            "request_body_sha256": hashlib.sha256(REQUEST_BODY).hexdigest(),
            "git_commit": host.git_commit,
            "python_version": host.python_version,
            "os": host.os,
            "cpu_count": host.cpu_count,
            "same_machine": settings.same_machine,
        },
    }


def _ms(seconds: float | None) -> str:
    return TOO_FEW_SAMPLES if seconds is None else f"{seconds * MILLISECONDS_PER_SECOND:.3f}"


def _counts(by_status: Mapping[str, int], transport: Mapping[str, int]) -> str:
    parts = [f"{key}: {count}" for key, count in [*by_status.items(), *transport.items()]]
    return ", ".join(parts) or "none"


def _given(value: object, unit: str = "") -> str:
    return "n/a" if value is None else f"{value}{unit}"


def render_markdown(report: LoadReport) -> str:
    summary, settings, host = report.summary, report.settings, report.host
    verdict = "valid" if summary.valid else "invalid: " + "; ".join(summary.invalid_reasons)
    rate = summary.achieved_rate_per_second
    rate_text = "n/a" if rate is None else f"{rate:.2f} requests per second"
    machine = (
        "same machine (they compete for the CPU)" if settings.same_machine else "separate machines"
    )
    cap = "none" if settings.max_connections is None else str(settings.max_connections)
    lines = [
        f"# Load run: scenario {settings.scenario}, {verdict}",
        "",
        "| Figure | Latency (ms) | Lag (ms) |",
        "| --- | --- | --- |",
        f"| p50 | {_ms(summary.latency_p50_seconds)} | {_ms(summary.lag_p50_seconds)} |",
        f"| p95 | {_ms(summary.latency_p95_seconds)} | n/a |",
        f"| p99 | {_ms(summary.latency_p99_seconds)} | {_ms(summary.lag_p99_seconds)} |",
        f"| max | {_ms(summary.latency_max_seconds)} | {_ms(summary.lag_max_seconds)} |",
        "",
        f"Percentiles: {QUANTILE_METHOD}; a p99 needs at least {P99_MIN_SAMPLES:,} measured"
        " requests.",
        "",
        f"- Requests: {summary.measured_requests} measured, {summary.warmup_requests} warm-up"
        f" (left out), {summary.total_requests} sent",
        f"- Errors: {_counts(summary.errors_by_status, summary.transport_errors)}",
        "- Warm-up errors: "
        + _counts(summary.warmup_errors_by_status, summary.warmup_transport_errors),
        f"- Achieved rate: {rate_text} ({ACHIEVED_RATE_FORMULA})",
        f"- Peak in flight: {report.peak_in_flight}",
        f"- Generator CPU time: {report.generator_cpu_seconds:.3f} s",
        "",
        "## Settings",
        "",
        f"- Scenario: {settings.scenario}",
        f"- Rate: {settings.rate_per_second} requests per second for {settings.duration_seconds}"
        f" s after {settings.warmup_seconds} s of warm-up",
        f"- Connection cap: {cap}",
        f"- Limiter: {_given(settings.limiter)}; tokens per minute"
        f" {_given(settings.tokens_per_minute)}; capacity {_given(settings.capacity_tokens)}",
        f"- Route file SHA-256 (with LF line endings): {_given(settings.routes_sha256)}",
        f"- Upstream delay: {_given(settings.upstream_delay_ms, ' ms')}",
        f"- Server: {_given(settings.server)}",
        f"- Request body: {len(REQUEST_BODY)} bytes, SHA-256"
        f" {hashlib.sha256(REQUEST_BODY).hexdigest()}",
        f"- Git commit: {host.git_commit or 'unknown'}",
        f"- Python {host.python_version} on {host.os}, {_given(host.cpu_count)} CPUs",
        f"- Generator and server: {machine}",
    ]
    return "\n".join(lines) + "\n"


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # argparse repeats the values it rejects, and any of them may be the URL put in the
        # wrong place, so no value is ever repeated.
        if message.startswith("unrecognized arguments"):
            message = "unrecognized arguments (not repeated: one may hold the URL)"
        # A value holding a single quote is shown in double quotes instead.
        message = re.split(r": ['\"]", message, maxsplit=1)[0]
        super().error(message)


def positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def _non_negative_int(text: str) -> int:
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must not be negative")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = Parser(description="Send load at a fixed arrival rate.", allow_abbrev=False)
    parser.add_argument("--url", required=True, help="the base URL of the server under test")
    parser.add_argument("--api-key-env", help="the NAME of the variable that holds the key")
    parser.add_argument("--rate", type=positive_int, required=True, help="requests per second")
    parser.add_argument("--duration-seconds", type=positive_int, required=True)
    parser.add_argument("--warmup-seconds", type=_non_negative_int, default=0)
    parser.add_argument("--max-connections", type=positive_int, help="default: no cap")
    parser.add_argument("--scenario", choices=["A", "B", "C"], required=True)
    parser.add_argument("--limiter", choices=["memory", "redis"])
    parser.add_argument("--tokens-per-minute", type=positive_int)
    parser.add_argument("--capacity-tokens", type=positive_int)
    parser.add_argument("--routes-file", type=Path, help="only its SHA-256 is recorded")
    parser.add_argument("--upstream-delay-ms", type=_non_negative_int)
    parser.add_argument("--server", choices=["uvicorn", "compose"])
    machine = parser.add_mutually_exclusive_group(required=True)
    machine.add_argument("--same-machine", dest="same_machine", action="store_true")
    machine.add_argument("--separate-machine", dest="same_machine", action="store_false")
    parser.add_argument("--output", type=Path, help="also write the report as JSON to this path")
    return parser


def _parse(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = _parser()
    args = parser.parse_args(argv)
    args.url = args.url.strip()
    try:
        url: httpx.URL | None = httpx.URL(args.url)
    except httpx.InvalidURL:
        url = None
    if url is None or url.scheme not in ("http", "https") or not url.host:
        parser.error("--url must be an http or https URL")
    return args


def _auth_headers(name: str | None, environ: Mapping[str, str]) -> dict[str, str]:
    if name is None:
        return {}
    key = environ.get(name, "").strip()
    if not key:
        raise ScriptError("the variable named by --api-key-env is not set or is blank")
    # httpx encodes headers as ASCII, and its error would quote a character of the key.
    if not (key.isascii() and key.isprintable()):
        raise ScriptError("the variable named by --api-key-env must hold printable ASCII")
    return {"Authorization": f"Bearer {key}"}


def _routes_sha256(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return dataset_sha256(path.read_bytes())
    except OSError:
        raise ScriptError("cannot read the --routes-file") from None


async def _run(
    plan: LoadPlan,
    *,
    url: str,
    headers: Mapping[str, str],
    max_connections: int | None,
    transport: httpx.AsyncBaseTransport | None,
    clock: MonotonicClock,
    sleep: Sleep,
    cpu_seconds: Callable[[], float],
) -> tuple[RunResult, float]:
    if transport is None:
        client = make_client(url, max_connections=max_connections)
    else:  # tests: the cap is then recorded only
        client = httpx.AsyncClient(
            base_url=url, transport=transport, timeout=DEFAULT_TIMEOUT_SECONDS, trust_env=False
        )
    async with client:
        cpu_start_seconds = cpu_seconds()
        result = await run_load(plan, client=client, clock=clock, sleep=sleep, headers=headers)
        cpu_end_seconds = cpu_seconds()
    return result, cpu_end_seconds - cpu_start_seconds


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    clock: MonotonicClock | None = None,
    sleep: Sleep | None = None,
    cpu_seconds: Callable[[], float] | None = None,
    host: HostFacts | None = None,
) -> int:
    args = _parse(argv)
    try:
        headers = _auth_headers(args.api_key_env, os.environ if environ is None else environ)
        routes_sha256 = _routes_sha256(args.routes_file)
        if args.output is not None and not args.output.parent.is_dir():
            # Checked before the run, so a mistyped path does not lose a long run.
            raise ScriptError("cannot write the --output file")
    except ScriptError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_FAILED
    plan = LoadPlan(
        rate_per_second=args.rate,
        duration_seconds=args.duration_seconds,
        warmup_seconds=args.warmup_seconds,
    )
    result, generator_cpu_seconds = asyncio.run(
        _run(
            plan,
            url=args.url,
            headers=headers,
            max_connections=args.max_connections,
            transport=transport,
            clock=clock or SystemMonotonicClock(),
            sleep=sleep or asyncio.sleep,
            cpu_seconds=cpu_seconds or time.process_time,
        )
    )
    report = LoadReport(
        summary=summarize(result.samples),
        peak_in_flight=result.peak_in_flight,
        generator_cpu_seconds=generator_cpu_seconds,
        settings=RunSettings(
            scenario=args.scenario,
            rate_per_second=args.rate,
            duration_seconds=args.duration_seconds,
            warmup_seconds=args.warmup_seconds,
            max_connections=args.max_connections,
            limiter=args.limiter,
            tokens_per_minute=args.tokens_per_minute,
            capacity_tokens=args.capacity_tokens,
            routes_sha256=routes_sha256,
            upstream_delay_ms=args.upstream_delay_ms,
            server=args.server,
            same_machine=args.same_machine,
        ),
        host=host or collect_host_facts(),
    )
    if args.output is not None:
        try:
            with args.output.open("w", encoding="utf-8", newline="\n") as file:
                file.write(json.dumps(report_as_json(report), indent=2) + "\n")
        except OSError:
            print("error: cannot write the --output file", file=sys.stderr)
            return EXIT_FAILED
    print(render_markdown(report), end="")
    return EXIT_OK if report.summary.valid else EXIT_INVALID


if __name__ == "__main__":
    sys.exit(main())
