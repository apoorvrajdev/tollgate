"""The fixed-rate runner in scripts/bench_load.py (T-406): the schedule, the timing of each
request from its due time, the open loop, and errors returned per request.

The runner runs on a virtual-time event loop: its clock jumps to the next timer only when every
task is waiting, so concurrent requests are timed exactly and nothing sleeps for real.
"""

import asyncio
import selectors
from collections.abc import Callable, Coroutine
from typing import Any

import httpx
import pytest

from tests.fakes import FakeMonotonicClock, load_script

START_SECONDS = 100.0
AUTH = {"Authorization": "Bearer bench-key"}

bench = load_script("bench_load")


class _VirtualSelector(selectors.SelectSelector):
    """Moves the clock forward by the loop's timeout instead of waiting for it.

    asyncio passes a timeout of 0 while any callback is ready, and the time to the next timer
    only when every task is waiting, so the clock jumps straight to the next event.
    """

    def __init__(self, clock: FakeMonotonicClock) -> None:
        super().__init__()
        self._clock = clock

    def select(self, timeout: float | None = None) -> list[tuple[selectors.SelectorKey, int]]:
        if timeout is None:
            raise AssertionError("deadlock: nothing is ready and no timer is due")
        if timeout > 0:
            self._clock.advance(timeout)
        return super().select(0)


class VirtualTimeLoop(asyncio.SelectorEventLoop):
    def __init__(self, start_seconds: float) -> None:
        self.clock = FakeMonotonicClock(start_seconds)
        super().__init__(_VirtualSelector(self.clock))

    def time(self) -> float:
        return self.clock.monotonic_seconds()


def run_virtual[T](
    make: Callable[[VirtualTimeLoop], Coroutine[Any, Any, T]], start_seconds: float
) -> T:
    loop = VirtualTimeLoop(start_seconds)
    try:
        return loop.run_until_complete(make(loop))
    finally:
        loop.close()


type Answer = Callable[[httpx.Request, int], httpx.Response]


def ok(request: httpx.Request, index: int) -> httpx.Response:
    return httpx.Response(200, json={"ok": True})


class SlowTransport(httpx.MockTransport):
    """Answers request n (in arrival order) after `latency_seconds` of virtual time, or after
    `latency_seconds(n)` when it is a function; records every request.
    """

    def __init__(
        self, latency_seconds: float | Callable[[int], float], answer: Answer = ok
    ) -> None:
        self.requests: list[httpx.Request] = []

        async def handle(request: httpx.Request) -> httpx.Response:
            index = len(self.requests)
            self.requests.append(request)
            if callable(latency_seconds):
                await asyncio.sleep(latency_seconds(index))
            else:
                await asyncio.sleep(latency_seconds)
            return answer(request, index)

        super().__init__(handle)


def run_plan(
    plan: Any,
    transport: httpx.MockTransport,
    *,
    start_delay_seconds: float = 0.0,
    start_seconds: float = START_SECONDS,
) -> Any:
    """Run `plan` on virtual time, its clock starting at `start_seconds`.

    `start_delay_seconds` is time lost in the scheduler on each call to sleep, as busy work
    would. The scheduler creates request i's task and then calls sleep for request i + 1; that
    call moves the clock before task i first runs, so task i is handed over that much late.
    Request 0 is the exception: the sleep before it also moves the clock, so it is twice as late.
    """

    async def go(loop: VirtualTimeLoop) -> Any:
        async def sleep(seconds: float) -> None:
            loop.clock.advance(start_delay_seconds)
            await asyncio.sleep(max(0.0, seconds - start_delay_seconds))

        async with httpx.AsyncClient(base_url="http://gateway.test", transport=transport) as client:
            return await bench.run_load(
                plan, client=client, clock=loop.clock, sleep=sleep, headers=AUTH
            )

    return run_virtual(go, start_seconds)


# Criterion 1: the schedule, the number of requests and the warm-up marking.


def test_due_time_is_the_start_plus_the_index_over_the_rate() -> None:
    assert bench.due_time(10.0, 3, 4) == 10.75
    assert bench.due_time(10.0, 0, 4) == 10.0


def test_request_count_and_warmup_marking_follow_the_plan() -> None:
    plan = bench.LoadPlan(rate_per_second=4, duration_seconds=3, warmup_seconds=2)
    assert (plan.request_count, plan.warmup_count) == (20, 8)
    result = run_plan(plan, SlowTransport(0.01))
    assert [s.index for s in result.samples] == list(range(20))
    assert [s.warmup for s in result.samples] == [True] * 8 + [False] * 12
    assert [s.due_seconds for s in result.samples] == [START_SECONDS + i / 4 for i in range(20)]


def test_due_times_are_computed_from_the_start_not_accumulated() -> None:
    # From 0.0 at rate 10, adding 0.1 three times gives 0.30000000000000004, not 3 / 10.
    plan = bench.LoadPlan(rate_per_second=10, duration_seconds=1)
    result = run_plan(plan, SlowTransport(0.01), start_seconds=0.0)
    assert [s.due_seconds for s in result.samples] == [i / 10 for i in range(10)]


def test_no_request_is_warmup_without_a_warmup() -> None:
    plan = bench.LoadPlan(rate_per_second=5, duration_seconds=1)
    result = run_plan(plan, SlowTransport(0.01))
    assert len(result.samples) == 5
    assert [s.warmup for s in result.samples] == [False] * 5


@pytest.mark.parametrize(
    ("rate", "duration", "warmup"), [(0, 1, 0), (1, 0, 0), (1, 1, -1), (-2, 1, 0)]
)
def test_a_plan_out_of_range_is_rejected(rate: int, duration: int, warmup: int) -> None:
    with pytest.raises(ValueError, match="must"):
        bench.LoadPlan(rate_per_second=rate, duration_seconds=duration, warmup_seconds=warmup)


# Criterion 2: a request handed over 5 ms late that takes 10 ms is timed 0, 5 and 15 ms from due.


def test_a_late_hand_over_and_the_latency_are_timed_from_the_due_time() -> None:
    plan = bench.LoadPlan(rate_per_second=10, duration_seconds=1)
    result = run_plan(plan, SlowTransport(0.010), start_delay_seconds=0.005)
    sample = result.samples[3]
    assert sample.due_seconds == START_SECONDS + 0.3
    assert sample.hand_over_seconds - sample.due_seconds == pytest.approx(0.005, abs=1e-9)
    assert sample.end_seconds - sample.due_seconds == pytest.approx(0.015, abs=1e-9)
    assert (sample.status, sample.transport_error) == (200, None)


# Criterion 3: requests go out at their due times without waiting for earlier answers.


def test_requests_are_sent_without_waiting_for_earlier_answers() -> None:
    # 35 ms answers at 100 requests a second: up to ceil(35 / 10) = 4 overlap, with no ties.
    plan = bench.LoadPlan(rate_per_second=100, duration_seconds=1)
    result = run_plan(plan, SlowTransport(0.035))
    assert len(result.samples) == 100
    for sample in result.samples:
        assert sample.hand_over_seconds == pytest.approx(sample.due_seconds, abs=1e-9)
        assert sample.end_seconds - sample.hand_over_seconds == pytest.approx(0.035, abs=1e-9)
    assert result.peak_in_flight == 4


def test_peak_in_flight_is_the_maximum_not_the_last_count() -> None:
    # The first 5 answers take 50 ms, the rest 1 ms: 5 overlap at 40 ms, then only 1 at a time.
    plan = bench.LoadPlan(rate_per_second=100, duration_seconds=1)
    result = run_plan(plan, SlowTransport(lambda index: 0.050 if index < 5 else 0.001))
    assert result.peak_in_flight == 5


# Criterion 4: a transport error and a non-200 come back with their request.


def test_transport_errors_and_non_200s_are_returned_per_request() -> None:
    def answer(request: httpx.Request, index: int) -> httpx.Response:
        if index % 2:
            raise httpx.ConnectError("connection refused by 10.0.0.1", request=request)
        return httpx.Response(503, json={"error": "busy"})

    plan = bench.LoadPlan(rate_per_second=10, duration_seconds=1)
    result = run_plan(plan, SlowTransport(0.025, answer))
    assert len(result.samples) == 10
    for sample in result.samples:
        if sample.index % 2:
            assert (sample.status, sample.transport_error) == (None, "ConnectError")
        else:
            assert (sample.status, sample.transport_error) == (503, None)
        assert sample.end_seconds - sample.hand_over_seconds == pytest.approx(0.025, abs=1e-9)


def test_failed_requests_leave_the_in_flight_count() -> None:
    def refuse(request: httpx.Request, index: int) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    # 25 ms failures at 100 requests a second overlap by ceil(25 / 10) = 3.
    plan = bench.LoadPlan(rate_per_second=100, duration_seconds=1)
    result = run_plan(plan, SlowTransport(0.025, refuse))
    assert {s.transport_error for s in result.samples} == {"ReadTimeout"}
    assert result.peak_in_flight == 3


def test_every_request_sends_the_one_fixed_body_as_json_with_the_given_headers() -> None:
    transport = SlowTransport(0.01)
    run_plan(bench.LoadPlan(rate_per_second=5, duration_seconds=1), transport)
    assert len(transport.requests) == 5
    for request in transport.requests:
        assert request.method == "POST"
        assert str(request.url) == "http://gateway.test/v1/chat/completions"
        assert request.content == bench.REQUEST_BODY
        assert request.headers["authorization"] == "Bearer bench-key"
        assert request.headers["content-type"] == "application/json"


# The client: no connection cap unless one is given.


def test_client_limits_have_no_cap_unless_one_is_given() -> None:
    assert bench.client_limits(None) == httpx.Limits(
        max_connections=None, max_keepalive_connections=None
    )
    assert bench.client_limits(8) == httpx.Limits(max_connections=8, max_keepalive_connections=8)


class RecordingTransport(httpx.AsyncBaseTransport):
    built: list[httpx.Limits]

    def __init__(self, *, limits: httpx.Limits) -> None:
        RecordingTransport.built.append(limits)


def test_make_client_has_no_connection_cap_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    RecordingTransport.built = []
    monkeypatch.setattr(bench.httpx, "AsyncHTTPTransport", RecordingTransport)
    bench.make_client("http://gateway.test")
    (limits,) = RecordingTransport.built
    assert (limits.max_connections, limits.max_keepalive_connections) == (None, None)


def test_make_client_gives_its_transport_a_given_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    RecordingTransport.built = []
    monkeypatch.setattr(bench.httpx, "AsyncHTTPTransport", RecordingTransport)
    bench.make_client("http://gateway.test", max_connections=8)
    (limits,) = RecordingTransport.built
    assert (limits.max_connections, limits.max_keepalive_connections) == (8, 8)


def test_make_client_has_the_base_url_and_ignores_proxy_settings() -> None:
    client = bench.make_client("http://gateway.test:8000")
    assert str(client.base_url) == "http://gateway.test:8000"
    assert client.trust_env is False
    assert client.timeout == httpx.Timeout(bench.DEFAULT_TIMEOUT_SECONDS)
    asyncio.run(client.aclose())
