"""`deploy/logging.json` and what reaches stdout through it (T-402, ADR-0016).

Each test loads the file with `logging.config.dictConfig` after pytest's `capsys` is active, so
the config's `ext://sys.stdout` stream is the captured one, and puts every logger back afterwards.
"""

import asyncio
import hashlib
import json
import logging
import logging.config
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.types import Message, Scope

from app.main import create_app
from app.observability.logs import JsonFormatter
from tests.fakes import FakeClock, FakeMonotonicClock, ScriptedProvider, make_settings
from tests.test_chat_rate_limits import RecordingLimiter

CONFIG_PATH = Path(__file__).resolve().parent.parent / "deploy" / "logging.json"
CONFIGURED_LOGGERS = ["tollgate.request", "uvicorn", "uvicorn.error", "uvicorn.access"]
LOGGER_NAMES = ["", *CONFIGURED_LOGGERS]
MARKER = "SENTINEL-marker-7f3a"
API_KEY = f"key-{MARKER}"
URL = "/v1/chat/completions"


@pytest.fixture
def configured() -> Iterator[None]:
    """Every logger's state restored at the end of a test that calls `load_config`."""
    saved = {
        name: (logger.handlers[:], logger.level, logger.propagate, logger.disabled)
        for name in LOGGER_NAMES
        for logger in [logging.getLogger(name)]
    }
    try:
        yield
    finally:
        for name, (handlers, level, propagate, disabled) in saved.items():
            logger = logging.getLogger(name)
            logger.handlers, logger.level = handlers, level
            logger.propagate, logger.disabled = propagate, disabled


def load_config() -> None:
    """Apply `deploy/logging.json` now, so its `ext://sys.stdout` is the stream capsys holds."""
    logging.config.dictConfig(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))


def written_lines(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return [line for line in capsys.readouterr().out.splitlines() if line]


def serve(application: Any, body: bytes, headers: list[tuple[bytes, bytes]]) -> list[Message]:
    """Call the ASGI app with a hand-built scope, so the query string and the client address are
    exactly as written, and return the messages it sent."""
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": URL,
        "raw_path": URL.encode(),
        "query_string": f"q={MARKER}".encode(),
        "root_path": "",
        "client": (f"{MARKER}.example", 5000),
        "server": ("test", 80),
        "headers": [(b"content-type", b"application/json"), *headers],
    }
    pending: list[Message] = [{"type": "http.request", "body": body, "more_body": False}]
    sent: list[Message] = []

    async def receive() -> Message:
        return pending.pop(0) if pending else {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    asyncio.run(application(scope, receive, send))
    return sent


def build_app(tmp_path: Path, **limiter_options: Exception) -> Any:
    table = {
        "providers": {"only": {"type": "mock"}},
        "routes": {"alias": [{"provider": "only"}]},
        "default": [{"provider": "only"}],
    }
    path = tmp_path / "routes.json"
    path.write_text(json.dumps(table), encoding="utf-8")
    application = create_app(
        make_settings(TOLLGATE_API_KEYS=API_KEY, TOLLGATE_ROUTES_FILE=str(path)),
        FakeClock(),
        providers={"only": ScriptedProvider("only")},
        monotonic_clock=FakeMonotonicClock(),
    )
    application.state.limiter = RecordingLimiter(application.state.limiter, **limiter_options)
    return application


def request_body(model: str) -> bytes:
    message = {"role": "user", "content": f"prompt {MARKER}"}
    return json.dumps({"model": model, "messages": [message], "user": MARKER}).encode()


def headers() -> list[tuple[bytes, bytes]]:
    return [
        (b"authorization", f"Bearer {API_KEY}".encode()),
        (b"x-request-marker", MARKER.encode()),
    ]


def test_no_logger_writes_a_request_value_the_key_its_digest_or_the_caller_id(
    tmp_path: Path, configured: None, capsys: pytest.CaptureFixture[str]
) -> None:
    load_config()
    application = build_app(tmp_path)
    sent = serve(application, request_body(f"model-{MARKER}"), headers())
    assert sent[0]["status"] == 200
    # A record the way uvicorn's access logger would write it, had `--no-access-log` been left out.
    logging.getLogger("uvicorn.access").info('%s - "POST /?q=%s" 200', f"{MARKER}.example", MARKER)
    logging.getLogger("uvicorn").info("started")
    output = capsys.readouterr().out
    parsed = [json.loads(line) for line in output.splitlines()]
    assert [(d["logger"], d["event"], d["status"]) for d in parsed if "event" in d] == [
        ("tollgate.request", "http_request", 200)
    ]
    digest = hashlib.sha256(API_KEY.encode()).hexdigest()
    for forbidden in (MARKER, API_KEY, digest, "model-"):
        assert forbidden not in output


def test_a_limiter_error_message_reaches_no_line_and_the_500_record_has_only_the_type(
    tmp_path: Path, configured: None, capsys: pytest.CaptureFixture[str]
) -> None:
    load_config()
    error = RuntimeError(f"limiter down {MARKER}")
    application = build_app(tmp_path, reserve_error=error)
    with pytest.raises(RuntimeError):
        serve(application, request_body("any"), headers())
    # What uvicorn does with the exception that escaped the app.
    logging.getLogger("uvicorn.error").error("Exception in ASGI application\n", exc_info=error)
    lines = written_lines(capsys)
    assert MARKER not in "\n".join(lines)
    request_line, error_line = (json.loads(line) for line in lines)
    assert request_line["status"] == 500
    assert error_line["logger"] == "uvicorn.error"
    assert error_line["exception_type"] == "RuntimeError"
    assert sorted(error_line) == ["exception_type", "level", "logger", "message", "time"]


def test_the_config_loads_and_a_request_record_comes_out_through_the_json_formatter(
    configured: None, capsys: pytest.CaptureFixture[str]
) -> None:
    load_config()
    logger = logging.getLogger("tollgate.request")
    logger.info("http_request", extra={"tollgate_fields": {"event": "http_request", "status": 204}})
    (line,) = written_lines(capsys)
    data = json.loads(line)
    assert (data["logger"], data["level"], data["event"], data["status"]) == (
        "tollgate.request",
        "INFO",
        "http_request",
        204,
    )


@pytest.mark.parametrize("name", LOGGER_NAMES, ids=["root", *CONFIGURED_LOGGERS])
def test_every_configured_logger_writes_through_the_json_formatter(
    configured: None, name: str
) -> None:
    load_config()
    handlers = logging.getLogger(name).handlers
    assert len(handlers) == 1
    assert isinstance(handlers[0].formatter, JsonFormatter)


def test_the_config_names_exactly_the_expected_loggers_and_levels() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    assert {name: (v["level"], v["propagate"]) for name, v in config["loggers"].items()} == {
        "tollgate.request": ("INFO", False),
        "uvicorn": ("INFO", False),
        "uvicorn.error": ("INFO", False),
        "uvicorn.access": ("CRITICAL", False),
    }
    assert config["root"]["level"] == "WARNING"
    assert config["formatters"]["json"]["()"] == "app.observability.logs.JsonFormatter"
