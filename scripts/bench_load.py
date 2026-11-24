"""Fixed-rate load against the gateway (T-406, ADR-0018), part one: the schedule and the runner.

Request i is due at the start plus i divided by the rate, and is sent as its own task without
waiting for earlier answers (an open loop), so a slow answer never delays the next request.
Every request is timed from its due time, not from when it was sent. The runner returns the raw
samples; the statistics, the validity check and the command line are T-407.
"""

import asyncio
import json
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # running a script puts scripts/ first, not the repository root
    sys.path.insert(0, str(ROOT))

from app.clock import MonotonicClock  # noqa: E402

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
