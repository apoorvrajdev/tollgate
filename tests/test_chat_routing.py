"""Routing and fallback on POST /v1/chat/completions (T-202, ADR-0010, ADR-0011).

Limits as in test_chat_rate_limits.py: capacity 1000 tokens, refilled at 600 per minute (10 per
second), on a fake clock. PAYLOAD_B ("hello there world", max_tokens 100) reserves 111, so a 200's
headers are ("1000", "889", "12s", None). A follow-up of 11 tokens ("hello there world" without
max_tokens) shows the settled balance: 989 after a full refund, 878 after the reservation stayed
charged (122 missing is 12.2 s, so 13 s).

Route files declare every provider as `mock`, and tests replace them through `providers=` with
scripted fakes that report the model "reported-2" (or "reported") and 20 + 17 = 37 tokens.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.models import ChatRequest
from app.main import create_app
from app.providers.errors import ProviderError, ProviderErrorKind
from app.providers.mock import MockProvider
from app.routing.config import TargetConfig
from app.routing.router import Route
from app.settings import SettingsError
from tests.fakes import AUTH_HEADERS, FakeClock, FixedIdSource, ScriptedProvider, make_settings
from tests.test_chat_rate_limits import CALLER_ID, RecordingLimiter

URL = "/v1/chat/completions"
START_SECONDS = 1000.0
LIMIT_SETTINGS = {"TOLLGATE_TOKENS_PER_MINUTE": "600", "TOLLGATE_CAPACITY_TOKENS": "1000"}
LIMIT_HEADER_NAMES = (
    "x-ratelimit-limit-tokens",
    "x-ratelimit-remaining-tokens",
    "x-ratelimit-reset-tokens",
    "retry-after",
)
ROUTING_HEADER_NAMES = ("x-tollgate-provider", "x-tollgate-fallbacks")
SECRET = "SENTINEL-provider-internals"
MODEL_SENTINEL = "SENTINEL-unknown-model"
PROVIDER_NAMES = ("first", "second", "third", "spare")
BAD_GATEWAY_BODY = {
    "error": {
        "message": "The upstream provider failed to complete the request.",
        "type": "api_error",
        "param": None,
        "code": "provider_error",
    }
}


def payload(model: str, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": "hello there world"}],
    }
    body.update(overrides)
    return body


def route_file(*, default: bool) -> dict[str, Any]:
    data: dict[str, Any] = {
        "providers": {name: {"type": "mock"} for name in PROVIDER_NAMES},
        "routes": {
            "pair": [
                {"provider": "first", "model": "up-1"},
                {"provider": "second", "model": "up-2"},
            ],
            "trio": [
                {"provider": "first", "model": "up-1"},
                {"provider": "second", "model": "up-2"},
                {"provider": "third"},
            ],
        },
    }
    if default:
        data["default"] = [{"provider": "spare"}]
    return data


def limit_values(response: httpx.Response) -> tuple[str | None, ...]:
    return tuple(response.headers.get(name) for name in LIMIT_HEADER_NAMES)


def routing_values(response: httpx.Response) -> tuple[str | None, ...]:
    return tuple(response.headers.get(name) for name in ROUTING_HEADER_NAMES)


class RoutedGateway:
    """The app on a route file in tmp_path, with scripted providers and a recording limiter."""

    def __init__(
        self, tmp_path: Path, *, default: bool = True, **providers: ScriptedProvider
    ) -> None:
        path = tmp_path / "routes.json"
        path.write_text(json.dumps(route_file(default=default)), encoding="utf-8")
        self.clock = FakeClock(START_SECONDS)
        settings = make_settings(**LIMIT_SETTINGS, TOLLGATE_ROUTES_FILE=str(path))
        self.app: FastAPI = create_app(settings, self.clock, providers=providers)
        self.recorder = RecordingLimiter(self.app.state.limiter)
        self.app.state.limiter = self.recorder
        self.client = TestClient(self.app, headers=AUTH_HEADERS)

    def post(self, body: dict[str, Any]) -> httpx.Response:
        response: httpx.Response = self.client.post(URL, json=body)
        return response


# Criterion 1: an unknown model.


def test_unknown_model_without_a_default_gets_404_with_no_reservation_and_no_limit_headers(
    tmp_path: Path,
) -> None:
    providers = {name: ScriptedProvider(name) for name in PROVIDER_NAMES}
    gateway = RoutedGateway(tmp_path, default=False, **providers)
    response = gateway.post(payload(MODEL_SENTINEL, max_tokens=100))
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "message": "The requested model is not available on this gateway.",
            "type": "invalid_request_error",
            "param": "model",
            "code": "model_not_found",
        }
    }
    assert MODEL_SENTINEL not in response.text
    assert limit_values(response) == (None, None, None, None)
    assert routing_values(response) == (None, None)
    assert gateway.recorder.calls == []
    assert all(provider.requests == [] for provider in providers.values())


def test_unknown_model_with_a_default_route_is_served_by_it(tmp_path: Path) -> None:
    spare = ScriptedProvider("spare")
    gateway = RoutedGateway(tmp_path, spare=spare)
    response = gateway.post(payload("unknown-model", max_tokens=100))
    assert response.status_code == 200
    assert routing_values(response) == ("spare", "0")
    assert limit_values(response) == ("1000", "889", "12s", None)
    # The default target has no upstream model, so the client's model is passed through.
    assert [request.model for request in spare.requests] == ["unknown-model"]
    assert gateway.recorder.calls == [("reserve", CALLER_ID, 111), ("settle", CALLER_ID, 111, 37)]


@pytest.mark.parametrize(
    ("headers", "body", "status_code"),
    [
        ({"Authorization": ""}, payload(MODEL_SENTINEL), 401),
        (AUTH_HEADERS, payload(MODEL_SENTINEL, stream=True), 400),
    ],
    ids=["no-key", "invalid-body"],
)
def test_auth_and_validation_come_before_route_selection(
    tmp_path: Path, headers: dict[str, str], body: dict[str, Any], status_code: int
) -> None:
    gateway = RoutedGateway(tmp_path, default=False)
    response = gateway.client.post(URL, json=body, headers=headers)
    assert response.status_code == status_code
    assert gateway.recorder.calls == []


def test_refused_request_on_a_route_gets_429_without_routing_headers_or_a_provider_call(
    tmp_path: Path,
) -> None:
    first = ScriptedProvider("first")
    gateway = RoutedGateway(tmp_path, first=first)
    response = gateway.post(payload("pair", max_tokens=990))  # 11 + 990 = 1001 > 1000
    assert response.status_code == 429
    assert limit_values(response) == ("1000", "1000", "0s", None)
    assert routing_values(response) == (None, None)
    assert first.requests == []
    assert gateway.recorder.calls == [("reserve", CALLER_ID, 1001)]


# Criterion 2: a retryable failure on the first target.

RETRYABLE: list[tuple[ProviderErrorKind, int | None]] = [
    ("connection", None),
    ("timeout", None),
    ("rate_limited", 429),
    ("upstream_status", 500),
    ("upstream_status", 529),
]


@pytest.mark.parametrize(
    ("kind", "status_code"), RETRYABLE, ids=[f"{kind}-{status}" for kind, status in RETRYABLE]
)
def test_each_retryable_failure_on_the_first_target_is_served_by_the_second(
    tmp_path: Path, kind: ProviderErrorKind, status_code: int | None
) -> None:
    first = ScriptedProvider("first", error=ProviderError(kind, status_code))
    second = ScriptedProvider("second", reported_model="reported-2")
    gateway = RoutedGateway(tmp_path, first=first, second=second)
    response = gateway.post(payload("pair", max_tokens=100))
    assert response.status_code == 200
    assert response.json()["model"] == "reported-2"
    assert response.json()["id"] == "chatcmpl-second"
    assert routing_values(response) == ("second", "1")
    assert limit_values(response) == ("1000", "889", "12s", None)
    assert gateway.recorder.calls == [("reserve", CALLER_ID, 111), ("settle", CALLER_ID, 111, 37)]
    assert [request.model for request in first.requests] == ["up-1"]
    assert [request.model for request in second.requests] == ["up-2"]


# Criterion 3: a non-retryable failure on the first target.

NON_RETRYABLE: list[tuple[str, Exception]] = [
    ("upstream_status-400", ProviderError("upstream_status", 400)),
    ("upstream_status-499", ProviderError("upstream_status", 499)),
    ("runtime-error", RuntimeError(SECRET)),
    ("http-exception", HTTPException(status_code=503, detail=SECRET)),
]


@pytest.mark.parametrize(
    "error", [case[1] for case in NON_RETRYABLE], ids=[case[0] for case in NON_RETRYABLE]
)
def test_non_retryable_failure_on_the_first_target_gives_502_and_a_full_refund(
    tmp_path: Path, error: Exception
) -> None:
    first = ScriptedProvider("first", error=error)
    second = ScriptedProvider("second")
    gateway = RoutedGateway(tmp_path, first=first, second=second, spare=ScriptedProvider("spare"))
    response = gateway.post(payload("pair", max_tokens=100))
    assert response.status_code == 502
    assert response.json() == BAD_GATEWAY_BODY
    assert SECRET not in response.text
    assert limit_values(response) == ("1000", "889", "12s", None)
    assert routing_values(response) == (None, None)
    assert second.requests == []
    assert gateway.recorder.calls == [("reserve", CALLER_ID, 111), ("settle", CALLER_ID, 111, 0)]
    # Refunded in full: back to 1000, so the follow-up of 11 leaves 989.
    assert limit_values(gateway.post(payload("other"))) == ("1000", "989", "2s", None)


# Criterion 4: a bad_response on the first target.


def test_bad_response_on_the_first_target_gives_502_and_stays_charged(tmp_path: Path) -> None:
    first = ScriptedProvider("first", error=ProviderError("bad_response"))
    second = ScriptedProvider("second")
    gateway = RoutedGateway(tmp_path, first=first, second=second, spare=ScriptedProvider("spare"))
    response = gateway.post(payload("pair", max_tokens=100))
    assert response.status_code == 502
    assert response.json() == BAD_GATEWAY_BODY
    assert second.requests == []
    assert gateway.recorder.calls == [("reserve", CALLER_ID, 111), ("settle", CALLER_ID, 111, 111)]
    # Still charged: 889, so the follow-up of 11 leaves 878.
    assert limit_values(gateway.post(payload("other"))) == ("1000", "878", "13s", None)


# Criterion 5: every target failing.


def test_every_target_failing_calls_each_once_in_order_then_502_and_a_full_refund(
    tmp_path: Path,
) -> None:
    log: list[str] = []
    gateway = RoutedGateway(
        tmp_path,
        first=ScriptedProvider("first", error=ProviderError("timeout"), log=log),
        second=ScriptedProvider("second", error=ProviderError("upstream_status", 503), log=log),
        third=ScriptedProvider("third", error=ProviderError("connection"), log=log),
        spare=ScriptedProvider("spare"),
    )
    response = gateway.post(payload("trio", max_tokens=100))
    assert response.status_code == 502
    assert response.json() == BAD_GATEWAY_BODY
    assert log == ["first", "second", "third"]
    assert gateway.recorder.calls == [("reserve", CALLER_ID, 111), ("settle", CALLER_ID, 111, 0)]
    assert limit_values(gateway.post(payload("other"))) == ("1000", "989", "2s", None)


def test_third_target_serving_sends_two_fallbacks_and_the_clients_model(tmp_path: Path) -> None:
    third = ScriptedProvider("third")
    gateway = RoutedGateway(
        tmp_path,
        first=ScriptedProvider("first", error=ProviderError("timeout")),
        second=ScriptedProvider("second", error=ProviderError("rate_limited", 429)),
        third=third,
    )
    response = gateway.post(payload("trio"))
    assert response.status_code == 200
    assert routing_values(response) == ("third", "2")
    assert [request.model for request in third.requests] == ["trio"]


# Criterion 6: without a route file.


@pytest.mark.parametrize("injected", [False, True], ids=["default-mock", "injected-provider"])
def test_without_a_route_file_each_200_names_mock_and_zero_fallbacks(injected: bool) -> None:
    clock = FakeClock(START_SECONDS)
    provider = MockProvider(clock, FixedIdSource()) if injected else None
    application = create_app(make_settings(**LIMIT_SETTINGS), clock, provider=provider)
    if injected:
        assert application.state.providers == {"mock": provider}
    response = TestClient(application, headers=AUTH_HEADERS).post(
        URL, json=payload("mock-1", max_tokens=100)
    )
    assert response.status_code == 200
    assert routing_values(response) == ("mock", "0")
    assert limit_values(response) == ("1000", "889", "12s", None)
    assert response.json()["model"] == "mock-1"


# Criterion 7: a provider type that is not built yet.

UNBUILT: list[tuple[str, dict[str, Any]]] = [
    ("openai", {"type": "openai", "api_key_env": "SENTINEL_KEY_VAR"}),
    (
        "anthropic",
        {"type": "anthropic", "api_key_env": "SENTINEL_KEY_VAR", "default_max_tokens": 1024},
    ),
]


@pytest.mark.parametrize("config", [case[1] for case in UNBUILT], ids=[case[0] for case in UNBUILT])
def test_route_file_with_an_unbuilt_provider_type_fails_startup_naming_the_variable(
    tmp_path: Path, config: dict[str, Any]
) -> None:
    path = tmp_path / "routes.json"
    data = {"providers": {"real": config, "test": {"type": "mock"}}, "routes": {}}
    path.write_text(json.dumps(data), encoding="utf-8")
    settings = make_settings(
        TOLLGATE_ROUTES_FILE=str(path), SENTINEL_KEY_VAR="SENTINEL-provider-key"
    )
    # An injected provider for the same name does not skip the check.
    with pytest.raises(SettingsError) as raised:
        create_app(settings, FakeClock(), providers={"real": ScriptedProvider("real")})
    assert raised.value.variable == "TOLLGATE_ROUTES_FILE"
    message = str(raised.value)
    assert message == (
        "TOLLGATE_ROUTES_FILE: providers.real.type: is not built yet; built types: mock, ollama"
    )
    assert "SENTINEL" not in message


# The registry.


def test_registry_has_one_mock_provider_per_mock_type_on_the_injected_clock(
    tmp_path: Path,
) -> None:
    gateway = RoutedGateway(tmp_path)
    registry = gateway.app.state.providers
    assert set(registry) == set(PROVIDER_NAMES)
    assert all(isinstance(provider, MockProvider) for provider in registry.values())
    body = gateway.post(payload("pair")).json()
    # The mock reports the model it was sent: the first target's upstream model.
    assert (body["model"], body["created"]) == ("up-1", int(START_SECONDS))


def test_provider_keyword_replaces_mock_and_providers_keyword_merges_after_it() -> None:
    clock = FakeClock()
    replaced, merged, extra = (MockProvider(clock, FixedIdSource()) for _ in range(3))
    application = create_app(
        make_settings(), clock, provider=replaced, providers={"mock": merged, "extra": extra}
    )
    assert application.state.providers == {"mock": merged, "extra": extra}
    assert application.state.providers["mock"] is merged


class StubRouter:
    def __init__(self, route: Route) -> None:
        self._route = route

    def select(self, request: ChatRequest) -> Route:
        return self._route


def test_route_reads_the_router_and_the_registry_from_app_state_per_request() -> None:
    clock = FakeClock(START_SECONDS)
    application = create_app(make_settings(**LIMIT_SETTINGS), clock)
    swapped = ScriptedProvider("swapped")
    application.state.router = StubRouter((TargetConfig(provider="mock", model="swapped-model"),))
    application.state.providers["mock"] = swapped
    response = TestClient(application, headers=AUTH_HEADERS).post(URL, json=payload("mock-1"))
    assert response.status_code == 200
    assert routing_values(response) == ("mock", "0")
    assert [request.model for request in swapped.requests] == ["swapped-model"]
