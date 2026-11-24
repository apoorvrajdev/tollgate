"""`GET /metrics` (T-404, ADR-0016): present only with a token, and opened only by that token."""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.types import Message, Scope

from app.main import create_app
from app.observability.metrics import CONTENT_TYPE
from tests.auth_cases import EXPECTED_401_BODY
from tests.fakes import TEST_API_KEY, FakeClock, make_settings
from tests.test_request_log import URL, LogGateway

TOKEN = "scrape-token-" + "x" * 30
EXPECTED_METRICS_401 = {
    "error": {
        "message": "Missing or invalid metrics token.",
        "type": "invalid_request_error",
        "param": None,
        "code": "invalid_metrics_token",
    }
}
TOKEN_ENV = {"TOLLGATE_METRICS_TOKEN": TOKEN}


def anonymous(gateway: LogGateway) -> TestClient:
    """A client with no default headers, so each test sends exactly the Authorization it means."""
    return TestClient(gateway.app)


def get(gateway: LogGateway, *values: str) -> Any:
    headers = [("Authorization", value) for value in values]
    return anonymous(gateway).get("/metrics", headers=headers)


def raw_status(headers: list[tuple[bytes, bytes]], token: str = TOKEN) -> tuple[int, bytes]:
    """GET /metrics with exactly these raw headers; return the status and the body."""
    application = create_app(make_settings(TOLLGATE_METRICS_TOKEN=token), FakeClock())
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/metrics",
        "raw_path": b"/metrics",
        "query_string": b"",
        "root_path": "",
        "client": ("127.0.0.1", 5000),
        "server": ("test", 80),
        "headers": headers,
    }
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    asyncio.run(application(scope, receive, send))
    start = next(m for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return start["status"], body


def test_with_the_token_unset_metrics_is_the_ordinary_404(tmp_path: Path) -> None:
    gateway = LogGateway(tmp_path)
    unknown = anonymous(gateway).get("/no-such-path")
    assert unknown.status_code == 404
    for headers in ({}, {"Authorization": f"Bearer {TOKEN}"}, {"Authorization": "Bearer x"}):
        response = anonymous(gateway).get("/metrics", headers=headers)
        assert response.status_code == 404
        assert response.json() == unknown.json()
        assert "www-authenticate" not in response.headers
    paths = {getattr(route, "path", None) for route in gateway.app.routes}
    assert "/metrics" not in paths


@pytest.mark.parametrize(
    "values",
    [
        [],
        ["Bearer " + "w" * 43],
        [f"Bearer {TEST_API_KEY}"],
        [f"Basic {TOKEN}"],
        [f"Token {TOKEN}"],
        [TOKEN],
        ["Bearer"],
        ["Bearer "],
        [f"Bearer {TOKEN}x"],
        [f"Bearer {TOKEN[:-1]}"],
        [f"Bearer {TOKEN.upper()}"],
        [f"Bearer {TOKEN} extra"],
        [f"Bearer\t{TOKEN}"],
        [f"Bearer {TOKEN}", f"Bearer {TOKEN}"],
        [f"Bearer {TOKEN}", "Bearer wrong"],
        ["Bearer wrong", f"Bearer {TOKEN}"],
    ],
    ids=[
        "no header",
        "wrong token",
        "an API key",
        "basic scheme",
        "token scheme",
        "no scheme",
        "scheme only",
        "scheme and a space",
        "token plus a character",
        "token minus a character",
        "upper-cased token",
        "token and an extra word",
        "tab instead of a space",
        "two equal headers",
        "right then wrong",
        "wrong then right",
    ],
)
def test_every_bad_authorization_gets_the_metrics_401(tmp_path: Path, values: list[str]) -> None:
    gateway = LogGateway(tmp_path, extra_env=TOKEN_ENV)
    response = get(gateway, *values)
    assert response.status_code == 401
    assert response.json() == EXPECTED_METRICS_401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() != EXPECTED_401_BODY


@pytest.mark.parametrize(
    "value",
    [b"\xff", b"Bearer \xff", b"Bearer " + TOKEN.encode() + b"\xff", b"Bearer \xc0\xaf"],
    ids=["lone byte", "byte as the token", "trailing byte", "overlong"],
)
def test_invalid_utf8_gets_the_metrics_401(value: bytes) -> None:
    status, body = raw_status([(b"authorization", value)])
    assert status == 401
    assert json.loads(body) == EXPECTED_METRICS_401


def test_two_raw_authorization_headers_get_the_401_even_when_one_is_right() -> None:
    right = (b"authorization", f"Bearer {TOKEN}".encode())
    assert raw_status([right])[0] == 200
    assert raw_status([right, right])[0] == 401
    assert raw_status([right, (b"Authorization", b"Bearer wrong")])[0] == 401


def test_the_scheme_is_case_insensitive_and_extra_spaces_are_allowed(tmp_path: Path) -> None:
    gateway = LogGateway(tmp_path, extra_env=TOKEN_ENV)
    for value in (f"bearer {TOKEN}", f"BEARER {TOKEN}", f"Bearer   {TOKEN}"):
        assert get(gateway, value).status_code == 200


def test_the_right_token_gets_200_with_the_exact_content_type(tmp_path: Path) -> None:
    gateway = LogGateway(tmp_path, extra_env=TOKEN_ENV)
    before = gateway.app.state.metrics.render()
    response = get(gateway, f"Bearer {TOKEN}")
    assert response.status_code == 200
    assert response.headers["content-type"] == CONTENT_TYPE
    # The scrape is counted after it is rendered, so the body is the registry as it stood before.
    assert response.text == before
    assert 'tollgate_http_requests_total{path="/metrics",status="200"} 1\n' in (
        gateway.app.state.metrics.render()
    )
    assert response.text.startswith("# HELP tollgate_http_requests_total ")


def test_an_api_key_never_opens_metrics_and_the_token_never_opens_chat(tmp_path: Path) -> None:
    gateway = LogGateway(tmp_path, extra_env=TOKEN_ENV)
    assert get(gateway, f"Bearer {TEST_API_KEY}").json() == EXPECTED_METRICS_401
    body = {"model": "solo-first", "messages": [{"role": "user", "content": "hi"}]}
    response = anonymous(gateway).post(URL, json=body, headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 401
    assert response.json() == EXPECTED_401_BODY


def test_other_methods_never_get_the_metrics_body(tmp_path: Path) -> None:
    gateway = LogGateway(tmp_path, extra_env=TOKEN_ENV)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    for method in ("POST", "PUT", "DELETE"):
        response = anonymous(gateway).request(method, "/metrics", headers=headers)
        assert response.status_code == 405
        assert "tollgate_" not in response.text


def test_two_apps_have_separate_registries(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first = LogGateway(tmp_path / "a", extra_env=TOKEN_ENV)
    second = LogGateway(tmp_path / "b", extra_env=TOKEN_ENV)
    assert first.app.state.metrics is not second.app.state.metrics
    before = second.app.state.metrics.render()
    assert first.post(model="solo-first").status_code == 200
    assert first.app.state.metrics.render() != before
    assert second.app.state.metrics.render() == before


def test_metrics_is_not_in_the_openapi_document(tmp_path: Path) -> None:
    gateway = LogGateway(tmp_path, extra_env=TOKEN_ENV)
    app: FastAPI = gateway.app
    assert any(getattr(route, "path", None) == "/metrics" for route in app.routes)
    assert "/metrics" not in app.openapi()["paths"]


def test_a_tab_next_to_the_token_is_not_stripped_but_spaces_are() -> None:
    token = TOKEN.encode()
    assert raw_status([(b"authorization", b"Bearer \t" + token)])[0] == 401
    assert raw_status([(b"authorization", b"Bearer " + token + b"\t")])[0] == 401
    assert raw_status([(b"authorization", b"Bearer " + token + b"  ")])[0] == 200


def test_a_non_breaking_space_next_to_the_token_is_not_trimmed() -> None:
    nbsp = b"\xc2\xa0"
    token = TOKEN.encode()
    assert raw_status([(b"authorization", b"Bearer " + nbsp + token)])[0] == 401
    assert raw_status([(b"authorization", b"Bearer " + token + nbsp)])[0] == 401


@pytest.mark.parametrize("scheme", [b"Bearerx", b"Bearers", b"Bearer2", b"xBearer", b"Bear"])
def test_a_scheme_that_only_resembles_bearer_gets_the_401(scheme: bytes) -> None:
    assert raw_status([(b"authorization", scheme + b" " + TOKEN.encode())])[0] == 401


def test_a_non_ascii_token_is_compared_as_utf8() -> None:
    token = "\u00e9" * 32
    right = b"Bearer " + token.encode("utf-8")
    assert raw_status([(b"authorization", right)], token)[0] == 200
    mojibake = b"Bearer " + token.encode("utf-8").decode("latin-1").encode("utf-8")
    assert raw_status([(b"authorization", mojibake)], token)[0] == 401
