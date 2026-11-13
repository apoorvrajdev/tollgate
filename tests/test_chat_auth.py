import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.models import ChatRequest, ChatResponse
from app.main import create_app
from app.providers.mock import MockProvider
from tests.auth_cases import EXPECTED_401_BODY, REJECTED_HEADER_VALUES
from tests.fakes import AUTH_HEADERS, FakeClock, FixedIdSource, make_settings

URL = "/v1/chat/completions"
SENTINEL = "SENTINEL-key-9c1d"
JSON_HEADER = {"content-type": "application/json"}


def valid_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"model": "mock-1", "messages": [{"role": "user", "content": "hi"}]}
    payload.update(overrides)
    return payload


def make_client(keys: str = "test-key", **kwargs: Any) -> TestClient:
    settings = make_settings(TOLLGATE_API_KEYS=keys)
    return TestClient(create_app(settings, FakeClock(), **kwargs))


def raw_headers(values: list[str]) -> list[tuple[str, bytes]]:
    return [("Authorization", value.encode("utf-8", errors="surrogatepass")) for value in values]


class RecordingProvider:
    def __init__(self) -> None:
        self.requests: list[ChatRequest] = []

    async def complete(self, request: ChatRequest) -> ChatResponse:
        self.requests.append(request)
        return await MockProvider(FakeClock(), FixedIdSource()).complete(request)


@pytest.mark.parametrize("values", REJECTED_HEADER_VALUES.values(), ids=REJECTED_HEADER_VALUES)
def test_bad_authorization_headers_get_the_same_401_with_a_bearer_challenge(
    values: list[str],
) -> None:
    response = make_client().post(URL, json=valid_payload(), headers=raw_headers(values))
    assert response.status_code == 401
    assert response.json() == EXPECTED_401_BODY
    assert response.headers["www-authenticate"] == "Bearer"


def test_each_configured_key_gets_200() -> None:
    client = make_client("key-one,key-two")
    for key in ("key-one", "key-two"):
        response = client.post(
            URL, json=valid_payload(), headers={"Authorization": f"Bearer {key}"}
        )
        assert response.status_code == 200


def test_a_utf8_key_sent_as_raw_bytes_authenticates() -> None:
    # Valid UTF-8 survives the test transport unchanged, unlike invalid bytes (see
    # test_auth_raw_headers.py, which calls the ASGI app directly).
    client = make_client("clé-ü")
    response = client.post(
        URL, json=valid_payload(), headers=[("Authorization", "Bearer clé-ü".encode())]
    )
    assert response.status_code == 200
    assert response.json()["model"] == "mock-1"


def test_a_key_that_is_not_configured_gets_401_when_others_are() -> None:
    response = make_client("key-one,key-two").post(
        URL, json=valid_payload(), headers={"Authorization": "Bearer key-three"}
    )
    assert response.status_code == 401


def test_health_needs_no_key() -> None:
    response = make_client().get("/health")
    assert (response.status_code, response.json()) == (200, {"status": "ok"})


UNAUTHENTICATED_BODIES: dict[str, dict[str, Any]] = {
    "stream true": {"json": valid_payload(stream=True)},
    "empty messages": {"json": valid_payload(messages=[])},
    "missing model": {"json": {"messages": [{"role": "user", "content": "x"}]}},
    "wrong types": {"json": {"model": 5, "messages": "x"}},
    "malformed json": {"content": b"{oops", "headers": JSON_HEADER},
    "empty body": {"headers": JSON_HEADER},
    "json list": {"json": [1, 2]},
    "text plain": {"content": b"x", "headers": {"content-type": "text/plain"}},
    "deeply nested json": {"content": b"[" * 100_000 + b"]" * 100_000, "headers": JSON_HEADER},
}


@pytest.mark.parametrize("kwargs", UNAUTHENTICATED_BODIES.values(), ids=UNAUTHENTICATED_BODIES)
def test_unauthenticated_request_with_an_invalid_body_gets_401_not_400(
    kwargs: dict[str, Any],
) -> None:
    response = make_client().post(URL, **kwargs)
    assert response.status_code == 401
    assert response.json() == EXPECTED_401_BODY


@pytest.mark.parametrize(
    ("name", "expected_code"),
    [
        ("stream true", "unsupported_parameter"),
        ("empty messages", "invalid_value"),
        ("missing model", "missing_required_parameter"),
        ("wrong types", "invalid_type"),
        ("malformed json", "invalid_json"),
        ("deeply nested json", "invalid_json"),
    ],
)
def test_authenticated_request_with_an_invalid_body_still_gets_the_adr_0009_400(
    name: str, expected_code: str
) -> None:
    kwargs = dict(UNAUTHENTICATED_BODIES[name])
    kwargs["headers"] = {**kwargs.get("headers", {}), **AUTH_HEADERS}
    response = make_client().post(URL, **kwargs)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == expected_code


def test_unauthenticated_request_never_reaches_the_provider() -> None:
    provider = RecordingProvider()
    client = make_client(provider=provider)
    client.post(URL, json=valid_payload())
    client.post(URL, json=valid_payload(), headers={"Authorization": "Bearer wrong"})
    assert provider.requests == []


def test_authenticated_request_reaches_the_provider() -> None:
    provider = RecordingProvider()
    make_client(provider=provider).post(URL, json=valid_payload(), headers=AUTH_HEADERS)
    assert len(provider.requests) == 1


def test_401_response_never_contains_the_submitted_key() -> None:
    submitted = {"Authorization": f"Bearer {SENTINEL}"}
    response = make_client().post(URL, json=valid_payload(), headers=submitted)
    assert response.status_code == 401
    assert SENTINEL not in response.text
    assert SENTINEL not in str(dict(response.headers))


def log_text(caplog: pytest.LogCaptureFixture) -> str:
    parts = [caplog.text]
    for record in caplog.records:
        parts += [
            record.getMessage(),
            str(record.args),
            record.exc_text or "",
            str(record.__dict__),
        ]
    return "\n".join(parts)


def test_the_log_check_detects_a_deliberate_leak(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    logging.getLogger("control").warning("key=%s", SENTINEL)
    assert SENTINEL in log_text(caplog)


def test_no_log_record_contains_the_submitted_key(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    client = make_client(keys=SENTINEL)
    good = {"Authorization": f"Bearer {SENTINEL}"}
    bad = {"Authorization": f"Bearer {SENTINEL}x"}
    responses = [
        client.post(URL, json=valid_payload(), headers=good),
        client.post(URL, json=valid_payload(stream=True), headers=good),
        client.post(URL, json=valid_payload(), headers=bad),
        client.post(URL, json=valid_payload(), headers=raw_headers([f"Bearer {SENTINEL}"] * 2)),
        client.post(URL, json=valid_payload()),
    ]
    assert [response.status_code for response in responses] == [200, 400, 401, 401, 401]
    assert SENTINEL not in log_text(caplog)
    for response in responses:
        assert SENTINEL not in response.text
        assert SENTINEL not in str(dict(response.headers))
