"""The fake upstream (T-406): its fixed body, its delay, its command line, and the gateway's real
`openai` adapter accepting its answer through `create_app()`. No network and no real sleeping.
"""

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.fakes import AUTH_HEADERS, ROOT, FakeClock, load_script, make_settings

FAKE_ROUTES = ROOT / "deploy" / "bench" / "routes.fake-upstream.json"
DELAY_SECONDS = 0.05

fake = load_script("fake_upstream")


class RecordingSleep:
    """A sleep that records each delay and returns at once."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def test_fake_answers_the_fixed_body_after_sleeping_the_delay() -> None:
    sleep = RecordingSleep()
    with TestClient(fake.build_app(DELAY_SECONDS, sleep)) as client:
        response = client.post("/v1/chat/completions", json={"model": "bench", "messages": []})
    assert response.status_code == 200
    assert response.json() == fake.FIXED_BODY
    assert sleep.calls == [DELAY_SECONDS]


def test_fake_answers_no_other_method_or_path() -> None:
    sleep = RecordingSleep()
    with TestClient(fake.build_app(DELAY_SECONDS, sleep)) as client:
        wrong_method = client.get("/v1/chat/completions")
        wrong_path = client.post("/v1/completions", json={})
    assert wrong_method.status_code == 405
    assert wrong_path.status_code == 404
    assert sleep.calls == []


# Criterion 5: the gateway's openai adapter accepts the fake's body.


def test_gateway_serves_a_200_from_the_fake_through_the_openai_adapter() -> None:
    sleep = RecordingSleep()
    settings = make_settings(
        TOLLGATE_ROUTES_FILE=str(FAKE_ROUTES),
        TOLLGATE_BENCH_UPSTREAM_KEY="placeholder-upstream-key",
    )
    transport = httpx.ASGITransport(app=fake.build_app(DELAY_SECONDS, sleep))
    app = create_app(settings, FakeClock(1000.0), http_transport=transport)
    payload: dict[str, Any] = {"model": "bench", "messages": [{"role": "user", "content": "hi"}]}
    with TestClient(app) as client:
        response = client.post("/v1/chat/completions", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert response.headers["x-tollgate-provider"] == "fake-upstream"
    body = response.json()
    assert body["choices"][0]["message"]["content"] == "ok"
    assert body["id"] == fake.FIXED_BODY["id"]
    assert sleep.calls == [DELAY_SECONDS]


# The command line: the delay is given in milliseconds and defaults to 50.


class RecordingRun:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, dict[str, Any]]] = []

    def __call__(self, app: Any, **kwargs: Any) -> None:
        self.calls.append((app, kwargs))


def test_main_serves_on_the_defaults_with_a_50_ms_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    run = RecordingRun()
    monkeypatch.setattr(fake.uvicorn, "run", run)
    assert fake.main([]) == 0
    ((app, kwargs),) = run.calls
    assert app.state.delay_seconds == 0.05
    assert (kwargs["host"], kwargs["port"]) == ("127.0.0.1", 8100)


def test_main_reads_the_delay_in_milliseconds(monkeypatch: pytest.MonkeyPatch) -> None:
    run = RecordingRun()
    monkeypatch.setattr(fake.uvicorn, "run", run)
    assert fake.main(["--delay-ms", "200", "--port", "8123"]) == 0
    ((app, kwargs),) = run.calls
    assert app.state.delay_seconds == 0.2
    assert kwargs["port"] == 8123


def test_main_rejects_a_negative_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    run = RecordingRun()
    monkeypatch.setattr(fake.uvicorn, "run", run)
    with pytest.raises(SystemExit) as exit_info:
        fake.main(["--delay-ms", "-1"])
    assert exit_info.value.code == 2
    assert run.calls == []
