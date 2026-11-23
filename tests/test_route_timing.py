"""The monotonic clock reaches run_route through the app (T-401, ADR-0016).

A spy wraps `app.api.chat.run_route` and records the clock it was given and the outcome it returned.
The provider moves the wall clock and the monotonic clock by different amounts, so an attempt's
duration can only come from the monotonic one. Steps are powers of two, so float sums are exact.
"""

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import chat
from app.clock import SystemMonotonicClock
from app.main import create_app
from app.providers.errors import ProviderError
from app.routing.router import Attempt, RouteOutcome, run_route
from tests.fakes import AUTH_HEADERS, FakeClock, FakeMonotonicClock, ScriptedProvider, make_settings

URL = "/v1/chat/completions"
BODY = {"model": "m", "messages": [{"role": "user", "content": "hello"}]}


class Spy:
    def __init__(self) -> None:
        self.monotonic_clocks: list[object] = []
        self.outcomes: list[RouteOutcome] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> RouteOutcome:
        self.monotonic_clocks.append(kwargs.get("monotonic_clock"))
        outcome = await run_route(*args, **kwargs)
        self.outcomes.append(outcome)
        return outcome


def spied(monkeypatch: pytest.MonkeyPatch) -> Spy:
    spy = Spy()
    monkeypatch.setattr(chat, "run_route", spy)
    return spy


def test_the_app_keeps_the_monotonic_clock_it_is_given() -> None:
    monotonic = FakeMonotonicClock()
    assert create_app(make_settings(), monotonic_clock=monotonic).state.monotonic_clock is monotonic


def test_the_app_builds_a_system_monotonic_clock_by_default() -> None:
    assert isinstance(create_app(make_settings()).state.monotonic_clock, SystemMonotonicClock)


def test_system_monotonic_clock_reads_perf_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    readings = iter([5.5, 7.25])
    monkeypatch.setattr(time, "perf_counter", lambda: next(readings))
    clock = SystemMonotonicClock()
    assert (clock.monotonic_seconds(), clock.monotonic_seconds()) == (5.5, 7.25)


def test_system_monotonic_clock_never_goes_back() -> None:
    clock = SystemMonotonicClock()
    first = clock.monotonic_seconds()
    assert clock.monotonic_seconds() >= first


def test_the_chat_route_passes_the_apps_monotonic_clock_to_run_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spy = spied(monkeypatch)
    monotonic = FakeMonotonicClock()
    application = create_app(
        make_settings(), FakeClock(), provider=ScriptedProvider("mock"), monotonic_clock=monotonic
    )
    assert TestClient(application).post(URL, json=BODY, headers=AUTH_HEADERS).status_code == 200
    assert len(spy.monotonic_clocks) == 1
    assert spy.monotonic_clocks[0] is monotonic


def test_an_attempts_duration_comes_from_the_monotonic_clock_not_the_wall_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spy = spied(monkeypatch)
    wall, monotonic = FakeClock(start_seconds=1000.0), FakeMonotonicClock(start_seconds=50.0)

    def advance_both() -> None:
        wall.advance(8.0)
        monotonic.advance(0.25)

    provider = ScriptedProvider("mock", on_call=advance_both)
    application = create_app(make_settings(), wall, provider=provider, monotonic_clock=monotonic)
    assert TestClient(application).post(URL, json=BODY, headers=AUTH_HEADERS).status_code == 200
    outcome = spy.outcomes[0]
    assert outcome.attempts == (Attempt("mock", "ok", 0.25),)


def test_a_failed_route_reports_its_attempts_and_the_chat_route_still_answers_502(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spy = spied(monkeypatch)
    monotonic = FakeMonotonicClock()
    provider = ScriptedProvider(
        "mock",
        error=ProviderError("upstream_status", 400),
        on_call=lambda: monotonic.advance(0.5),
    )
    application = create_app(
        make_settings(), FakeClock(), provider=provider, monotonic_clock=monotonic
    )
    response = TestClient(application).post(URL, json=BODY, headers=AUTH_HEADERS)
    assert response.status_code == 502
    assert spy.outcomes[0].attempts == (Attempt("mock", "upstream_status", 0.5),)
