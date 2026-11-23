"""Route selection and ordered fallback, without HTTP (T-202, ADR-0010, ADR-0011)."""

import asyncio
from types import MappingProxyType

import pytest

from app.api.models import ChatMessage, ChatRequest
from app.providers.errors import ProviderError, ProviderErrorKind, ReplyTooLargeError
from app.routing.config import (
    BUILTIN_ROUTE_TABLE,
    MockProviderConfig,
    RouteTable,
    TargetConfig,
)
from app.routing.router import (
    Attempt,
    AttemptOutcome,
    Route,
    RouteFailed,
    RouteOutcome,
    Served,
    TableRouter,
    UnknownModelError,
    run_route,
)
from tests.fakes import FakeMonotonicClock, ScriptedProvider, advancing

FAST_ROUTE = (
    TargetConfig(provider="a", model="up-a"),
    TargetConfig(provider="b", model="up-b"),
    TargetConfig(provider="c"),
)
DEFAULT_ROUTE = (TargetConfig(provider="d", model="up-d"),)
MODEL_SENTINEL = "SENTINEL-client-model"


def table(*, default: Route | None = DEFAULT_ROUTE) -> RouteTable:
    names = ("a", "b", "c", "d")
    return RouteTable(
        providers=MappingProxyType({name: MockProviderConfig(type="mock") for name in names}),
        routes=MappingProxyType({"fast": FAST_ROUTE, "slow": (TargetConfig(provider="d"),)}),
        default=default,
        api_keys=MappingProxyType({}),
    )


def request(model: str = "fast") -> ChatRequest:
    return ChatRequest(
        model=model,
        messages=[ChatMessage(role="user", content="hello")],
        max_tokens=50,
        temperature=0.5,
    )


def run(
    route: Route,
    *providers: ScriptedProvider,
    client: ChatRequest | None = None,
    monotonic_clock: FakeMonotonicClock | None = None,
) -> RouteOutcome:
    registry = {provider.name: provider for provider in providers}
    clock = monotonic_clock if monotonic_clock is not None else FakeMonotonicClock()
    return asyncio.run(run_route(route, registry, client or request(), monotonic_clock=clock))


def failed(outcome: RouteOutcome) -> RouteFailed:
    assert isinstance(outcome, RouteFailed)
    return outcome


def route_of(*names: str) -> Route:
    return tuple(TargetConfig(provider=name) for name in names)


# Selection.


def test_select_returns_the_exact_alias_targets_in_order() -> None:
    assert TableRouter(table()).select(request("fast")) == FAST_ROUTE
    assert TableRouter(table()).select(request("slow")) == (TargetConfig(provider="d"),)


@pytest.mark.parametrize("model", ["Fast", "fast ", " fast", "fas", "fastest"])
def test_select_matches_aliases_exactly(model: str) -> None:
    assert TableRouter(table()).select(request(model)) == DEFAULT_ROUTE


def test_select_uses_the_default_route_for_an_unknown_model() -> None:
    assert TableRouter(table()).select(request("unknown")) == DEFAULT_ROUTE


def test_select_raises_unknown_model_error_without_a_default_and_never_echoes_the_model() -> None:
    with pytest.raises(UnknownModelError) as raised:
        TableRouter(table(default=None)).select(request(MODEL_SENTINEL))
    assert MODEL_SENTINEL not in str(raised.value)
    # An alias still matches when there is no default.
    assert TableRouter(table(default=None)).select(request("fast")) == FAST_ROUTE


def test_builtin_table_routes_every_model_to_mock_without_an_upstream_model() -> None:
    router = TableRouter(BUILTIN_ROUTE_TABLE)
    for model in ("mock-1", "gpt-4o", MODEL_SENTINEL):
        assert router.select(request(model)) == (TargetConfig(provider="mock"),)


# Fallback.


def test_first_target_serving_reports_zero_fallbacks_and_never_calls_the_next() -> None:
    a, b = ScriptedProvider("a"), ScriptedProvider("b")
    outcome = run(route_of("a", "b"), a, b)
    assert isinstance(outcome, Served)
    assert (outcome.completion.id, outcome.provider_name, outcome.fallbacks) == (
        "chatcmpl-a",
        "a",
        0,
    )
    assert len(a.requests) == 1
    assert b.requests == []


RETRYABLE_ERRORS: list[tuple[ProviderErrorKind, int | None]] = [
    ("connection", None),
    ("timeout", None),
    ("rate_limited", 429),
    ("upstream_status", 500),
    ("upstream_status", 503),
    ("upstream_status", 529),
]


@pytest.mark.parametrize(
    ("kind", "status_code"),
    RETRYABLE_ERRORS,
    ids=[f"{kind}-{status}" for kind, status in RETRYABLE_ERRORS],
)
def test_each_retryable_failure_moves_to_the_next_target(
    kind: ProviderErrorKind, status_code: int | None
) -> None:
    a = ScriptedProvider("a", error=ProviderError(kind, status_code))
    b, c = ScriptedProvider("b"), ScriptedProvider("c")
    outcome = run(route_of("a", "b", "c"), a, b, c)
    assert isinstance(outcome, Served)
    assert (outcome.completion.id, outcome.provider_name, outcome.fallbacks) == (
        "chatcmpl-b",
        "b",
        1,
    )
    assert (len(a.requests), len(b.requests), c.requests) == (1, 1, [])


NON_RETRYABLE_ERRORS: list[tuple[str, Exception]] = [
    ("upstream_status-400", ProviderError("upstream_status", 400)),
    ("upstream_status-499", ProviderError("upstream_status", 499)),
    ("upstream_status-no-status", ProviderError("upstream_status")),
    ("runtime-error", RuntimeError("boom")),
]


@pytest.mark.parametrize(
    "error",
    [case[1] for case in NON_RETRYABLE_ERRORS],
    ids=[case[0] for case in NON_RETRYABLE_ERRORS],
)
def test_non_retryable_failure_stops_the_route_and_refunds(error: Exception) -> None:
    a, b = ScriptedProvider("a", error=error), ScriptedProvider("b")
    assert failed(run(route_of("a", "b"), a, b)).charged is False
    assert len(a.requests) == 1
    assert b.requests == []


def test_bad_response_stops_the_route_and_is_charged() -> None:
    a = ScriptedProvider("a", error=ProviderError("bad_response"))
    b = ScriptedProvider("b")
    assert failed(run(route_of("a", "b"), a, b)).charged is True
    assert b.requests == []


def test_every_target_failing_tries_each_once_in_order_then_refunds() -> None:
    log: list[str] = []
    providers = [
        ScriptedProvider("a", error=ProviderError("timeout"), log=log),
        ScriptedProvider("b", error=ProviderError("upstream_status", 502), log=log),
        ScriptedProvider("c", error=ProviderError("connection"), log=log),
    ]
    assert failed(run(route_of("a", "b", "c"), *providers)).charged is False
    assert log == ["a", "b", "c"]


def test_bad_response_after_a_fallback_is_charged_and_ends_the_route() -> None:
    a = ScriptedProvider("a", error=ProviderError("timeout"))
    b = ScriptedProvider("b", error=ProviderError("bad_response"))
    c = ScriptedProvider("c")
    assert failed(run(route_of("a", "b", "c"), a, b, c)).charged is True
    assert c.requests == []


def test_third_target_serving_reports_two_fallbacks() -> None:
    a = ScriptedProvider("a", error=ProviderError("timeout"))
    b = ScriptedProvider("b", error=ProviderError("rate_limited", 429))
    c = ScriptedProvider("c")
    outcome = run(route_of("a", "b", "c"), a, b, c)
    assert isinstance(outcome, Served)
    assert (outcome.provider_name, outcome.fallbacks) == ("c", 2)


def test_each_target_gets_its_upstream_model_or_the_clients_and_the_rest_is_unchanged() -> None:
    client = request("fast")
    before = client.model_dump()
    a = ScriptedProvider("a", error=ProviderError("timeout"))
    b = ScriptedProvider("b", error=ProviderError("connection"))
    c = ScriptedProvider("c")
    outcome = run(FAST_ROUTE, a, b, c, client=client)
    assert isinstance(outcome, Served)
    assert a.requests[0].model_dump() == {**before, "model": "up-a"}
    assert b.requests[0].model_dump() == {**before, "model": "up-b"}
    # The third target has no upstream model, so it gets the client's model.
    assert c.requests[0].model_dump() == before
    assert client.model_dump() == before


# Attempts (T-401, ADR-0016). Steps are powers of two, so the float sums are exact.

OUTCOME_CASES: list[tuple[str, Exception, AttemptOutcome]] = [
    ("connection", ProviderError("connection"), "connection"),
    ("timeout", ProviderError("timeout"), "timeout"),
    ("rate_limited", ProviderError("rate_limited", 429), "rate_limited"),
    ("upstream_500", ProviderError("upstream_status", 500), "upstream_status"),
    ("upstream_503", ProviderError("upstream_status", 503), "upstream_status"),
    ("upstream_400", ProviderError("upstream_status", 400), "upstream_status"),
    ("bad_response", ProviderError("bad_response", 200), "bad_response"),
    ("reply_too_large", ReplyTooLargeError(200), "reply_too_large"),
    ("runtime_error", RuntimeError("boom"), "error"),
]


@pytest.mark.parametrize(
    ("error", "outcome"),
    [case[1:] for case in OUTCOME_CASES],
    ids=[case[0] for case in OUTCOME_CASES],
)
def test_a_failed_call_is_recorded_with_its_outcome_and_duration(
    error: Exception, outcome: AttemptOutcome
) -> None:
    clock = FakeMonotonicClock(start_seconds=100.0)
    a = ScriptedProvider("a", error=error, on_call=advancing(clock, 0.25))
    result = failed(run(route_of("a"), a, monotonic_clock=clock))
    assert result.attempts == (Attempt("a", outcome, 0.25),)


def test_a_served_call_is_recorded_as_ok_with_its_duration() -> None:
    clock = FakeMonotonicClock(start_seconds=7.0)
    a = ScriptedProvider("a", on_call=advancing(clock, 0.5))
    outcome = run(route_of("a", "b"), a, ScriptedProvider("b"), monotonic_clock=clock)
    assert isinstance(outcome, Served)
    assert outcome.attempts == (Attempt("a", "ok", 0.5),)


def test_each_attempt_is_timed_from_its_own_start() -> None:
    clock = FakeMonotonicClock()
    a = ScriptedProvider("a", error=ProviderError("timeout"), on_call=advancing(clock, 0.25))
    b = ScriptedProvider(
        "b", error=ProviderError("upstream_status", 503), on_call=advancing(clock, 1.0)
    )
    c = ScriptedProvider("c", on_call=advancing(clock, 0.5))
    outcome = run(route_of("a", "b", "c"), a, b, c, monotonic_clock=clock)
    assert isinstance(outcome, Served)
    assert outcome.fallbacks == 2
    assert outcome.attempts == (
        Attempt("a", "timeout", 0.25),
        Attempt("b", "upstream_status", 1.0),
        Attempt("c", "ok", 0.5),
    )


def test_a_route_that_runs_out_of_targets_reports_every_attempt() -> None:
    clock = FakeMonotonicClock()
    providers = [
        ScriptedProvider("a", error=ProviderError("timeout"), on_call=advancing(clock, 0.25)),
        ScriptedProvider("b", error=ProviderError("connection"), on_call=advancing(clock, 0.5)),
    ]
    result = failed(run(route_of("a", "b"), *providers, monotonic_clock=clock))
    assert (result.charged, result.attempts) == (
        False,
        (Attempt("a", "timeout", 0.25), Attempt("b", "connection", 0.5)),
    )


def test_a_non_retryable_failure_after_a_fallback_reports_both_attempts() -> None:
    clock = FakeMonotonicClock()
    a = ScriptedProvider("a", error=ProviderError("timeout"), on_call=advancing(clock, 0.25))
    b = ScriptedProvider("b", error=ReplyTooLargeError(200), on_call=advancing(clock, 0.5))
    result = failed(
        run(route_of("a", "b", "c"), a, b, ScriptedProvider("c"), monotonic_clock=clock)
    )
    assert (result.charged, result.attempts) == (
        True,
        (Attempt("a", "timeout", 0.25), Attempt("b", "reply_too_large", 0.5)),
    )


def test_an_unexpected_exception_after_a_fallback_reports_both_attempts() -> None:
    clock = FakeMonotonicClock()
    a = ScriptedProvider("a", error=ProviderError("connection"), on_call=advancing(clock, 1.0))
    b = ScriptedProvider("b", error=RuntimeError("boom"), on_call=advancing(clock, 0.25))
    result = failed(run(route_of("a", "b"), a, b, monotonic_clock=clock))
    assert (result.charged, result.attempts) == (
        False,
        (Attempt("a", "connection", 1.0), Attempt("b", "error", 0.25)),
    )


def test_a_call_that_takes_no_time_has_a_zero_duration() -> None:
    result = failed(run(route_of("a"), ScriptedProvider("a", error=ProviderError("timeout"))))
    assert result.attempts == (Attempt("a", "timeout", 0.0),)


def test_attempt_durations_add_up_to_the_time_the_clock_moved() -> None:
    clock = FakeMonotonicClock()
    a = ScriptedProvider("a", error=ProviderError("timeout"), on_call=advancing(clock, 0.25))
    b = ScriptedProvider("b", on_call=advancing(clock, 0.5))
    outcome = run(route_of("a", "b"), a, b, monotonic_clock=clock)
    assert isinstance(outcome, Served)
    assert (
        sum(attempt.duration_seconds for attempt in outcome.attempts) == clock.monotonic_seconds()
    )


def test_an_attempt_is_immutable() -> None:
    attempt = Attempt("a", "ok", 0.25)
    with pytest.raises(AttributeError):
        attempt.outcome = "error"  # type: ignore[misc]


def test_a_plain_bad_response_is_not_recorded_as_reply_too_large() -> None:
    plain = failed(run(route_of("a"), ScriptedProvider("a", error=ProviderError("bad_response"))))
    assert plain.attempts[0].outcome == "bad_response"
