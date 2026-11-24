"""The structured request log (T-402, ADR-0016): one JSON line per HTTP request.

Limits: capacity 1000 tokens, refilled at 600 per minute. The prompt "hello there world" is 17
characters, so it reserves 11 tokens (ceil(17 / 4) + 3 + 3, no `max_tokens`). Scripted providers
report 20 + 17 = 37 tokens unless a test sets the usage. Each call to `first` moves the fake
monotonic clock by 0.25 s and each call to `second` by 0.5 s, so every duration is exact.
Route `pair` tries `first`, then `second`; `solo-first` and `solo-second` try one each.
"""

import asyncio
import json
import logging
import re
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

from app.api.models import ChatRequest, ChatResponse
from app.cache.embedder import EmbeddingError
from app.main import create_app
from app.observability.logs import REQUEST_LOGGER, JsonFormatter
from app.observability.middleware import RequestMiddleware, mapped_path
from app.observability.record import ChatRecord, RequestResult
from app.providers.errors import ProviderError
from tests.fakes import (
    AUTH_HEADERS,
    FakeClock,
    FakeEmbedder,
    FakeMonotonicClock,
    ScriptedProvider,
    advancing,
    make_settings,
)
from tests.test_chat_cache import CACHE_ENV, PROMPT, VECTORS
from tests.test_chat_rate_limits import RecordingLimiter

URL = "/v1/chat/completions"
START_SECONDS = 1000.0
LIMIT_SETTINGS = {"TOLLGATE_TOKENS_PER_MINUTE": "600", "TOLLGATE_CAPACITY_TOKENS": "1000"}
BASE_KEYS = ["level", "logger", "event", "method", "path", "status", "duration_seconds"]
CHAT_KEYS = [
    "provider",
    "fallbacks",
    "cache",
    "skip_reason",
    "reserved_tokens",
    "charged_tokens",
    "settle_capped",
    "attempts",
]
TIME_FORMAT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z")
ROUTE_TABLE: dict[str, Any] = {
    "providers": {"first": {"type": "mock"}, "second": {"type": "mock"}},
    "routes": {
        "pair": [{"provider": "first", "model": "up-1"}, {"provider": "second", "model": "up-2"}],
        "solo-first": [{"provider": "first"}],
        "solo-second": [{"provider": "second"}],
    },
}


class ListHandler(logging.Handler):
    """Collects each record as `JsonFormatter` renders it."""

    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.setFormatter(JsonFormatter())
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


@pytest.fixture
def lines() -> Iterator[list[str]]:
    """The lines written to `tollgate.request`, with the logger restored afterwards."""
    logger = logging.getLogger(REQUEST_LOGGER)
    saved = (logger.handlers[:], logger.level, logger.propagate, logger.disabled)
    handler = ListHandler()
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.disabled = False
    try:
        yield handler.lines
    finally:
        logger.handlers, logger.level, logger.propagate, logger.disabled = saved


def chat_values(**overrides: Any) -> dict[str, Any]:
    """The chat fields of a line: all null unless overridden."""
    values: dict[str, Any] = dict.fromkeys(CHAT_KEYS)
    assert set(overrides) <= set(CHAT_KEYS)
    values.update(overrides)
    return values


def check(
    line: str,
    *,
    method: str = "POST",
    path: str = URL,
    status: int,
    duration_seconds: float,
    chat: dict[str, Any] | None,
) -> None:
    """The line is one ASCII JSON line with exactly these keys, in this order, and these values."""
    assert line.isascii()
    assert "\n" not in line
    data = json.loads(line)
    assert TIME_FORMAT.fullmatch(data.pop("time"))
    assert list(data) == BASE_KEYS + (CHAT_KEYS if chat is not None else [])
    expected: dict[str, Any] = {
        "level": "INFO",
        "logger": REQUEST_LOGGER,
        "event": "http_request",
        "method": method,
        "path": path,
        "status": status,
        "duration_seconds": duration_seconds,
        **(chat or {}),
    }
    assert data == expected


def attempt(provider: str, outcome: str, duration_seconds: float) -> dict[str, Any]:
    return {"provider": provider, "outcome": outcome, "duration_seconds": duration_seconds}


class LogGateway:
    """The app on a route table in tmp_path, scripted providers and a recording limiter."""

    def __init__(
        self,
        tmp_path: Path,
        *,
        cache: bool = False,
        embedder: FakeEmbedder | None = None,
        first_error: Exception | None = None,
        second_error: Exception | None = None,
        usage: tuple[int, int] = (20, 17),
        on_first_call: Callable[[], None] | None = None,
        reserve_error: Exception | None = None,
        settle_error: Exception | None = None,
        raise_server_exceptions: bool = True,
        table: dict[str, Any] | None = None,
        providers: dict[str, Any] | None = None,
    ) -> None:
        path = tmp_path / "routes.json"
        path.write_text(json.dumps(table or ROUTE_TABLE), encoding="utf-8")
        env = {**LIMIT_SETTINGS, "TOLLGATE_ROUTES_FILE": str(path)}
        if cache:
            env.update(CACHE_ENV)
        self.clock = FakeClock(START_SECONDS)
        self.monotonic = FakeMonotonicClock()
        scripted: dict[str, Any] = providers or {
            "first": ScriptedProvider(
                "first",
                error=first_error,
                prompt_tokens=usage[0],
                completion_tokens=usage[1],
                on_call=on_first_call or advancing(self.monotonic, 0.25),
            ),
            "second": ScriptedProvider(
                "second", error=second_error, on_call=advancing(self.monotonic, 0.5)
            ),
        }
        self.app: FastAPI = create_app(
            make_settings(**env),
            self.clock,
            providers=scripted,
            embedder=(embedder or FakeEmbedder(VECTORS)) if cache else None,
            monotonic_clock=self.monotonic,
        )
        self.app.state.limiter = RecordingLimiter(
            self.app.state.limiter, reserve_error=reserve_error, settle_error=settle_error
        )
        self.client = TestClient(
            self.app, headers=AUTH_HEADERS, raise_server_exceptions=raise_server_exceptions
        )

    def post(self, content: str = PROMPT, model: str = "pair", **overrides: Any) -> httpx.Response:
        body: dict[str, Any] = {"model": model, "messages": [{"role": "user", "content": content}]}
        body.update(overrides)
        response: httpx.Response = self.client.post(URL, json=body)
        return response


def test_a_200_miss_logs_the_provider_the_tokens_and_the_attempt(
    tmp_path: Path, lines: list[str]
) -> None:
    LogGateway(tmp_path, cache=True).post(model="solo-first")
    (line,) = lines
    check(
        line,
        status=200,
        duration_seconds=0.25,
        chat=chat_values(
            provider="first",
            fallbacks=0,
            cache="miss",
            reserved_tokens=11,
            charged_tokens=37,
            settle_capped=False,
            attempts=[attempt("first", "ok", 0.25)],
        ),
    )


def test_a_200_hit_logs_the_stored_provider_and_no_attempts(
    tmp_path: Path, lines: list[str]
) -> None:
    gateway = LogGateway(tmp_path, cache=True)
    gateway.post(model="solo-first")
    gateway.post(model="solo-first")
    assert len(lines) == 2
    check(
        lines[1],
        status=200,
        duration_seconds=0.0,
        chat=chat_values(
            provider="first",
            fallbacks=0,
            cache="hit",
            reserved_tokens=11,
            charged_tokens=0,
            settle_capped=False,
        ),
    )


def test_a_skip_for_an_assistant_message_logs_not_eligible(
    tmp_path: Path, lines: list[str]
) -> None:
    gateway = LogGateway(tmp_path, cache=True)
    body = {"role": "assistant", "content": PROMPT}
    response = gateway.client.post(URL, json={"model": "solo-first", "messages": [body]})
    assert response.status_code == 200
    (line,) = lines
    check(
        line,
        status=200,
        duration_seconds=0.25,
        chat=chat_values(
            provider="first",
            fallbacks=0,
            cache="skip",
            skip_reason="not_eligible",
            reserved_tokens=11,
            charged_tokens=37,
            settle_capped=False,
            attempts=[attempt("first", "ok", 0.25)],
        ),
    )


def test_a_skip_after_an_embedder_failure_logs_embedder_failed(
    tmp_path: Path, lines: list[str]
) -> None:
    embedder = FakeEmbedder(VECTORS, error=EmbeddingError("timeout", None))
    LogGateway(tmp_path, cache=True, embedder=embedder).post(model="solo-first")
    (line,) = lines
    check(
        line,
        status=200,
        duration_seconds=0.25,
        chat=chat_values(
            provider="first",
            fallbacks=0,
            cache="skip",
            skip_reason="embedder_failed",
            reserved_tokens=11,
            charged_tokens=37,
            settle_capped=False,
            attempts=[attempt("first", "ok", 0.25)],
        ),
    )


def test_with_the_cache_off_the_line_has_no_cache_result_and_no_skip_reason(
    tmp_path: Path, lines: list[str]
) -> None:
    LogGateway(tmp_path).post(model="solo-first")
    (line,) = lines
    check(
        line,
        status=200,
        duration_seconds=0.25,
        chat=chat_values(
            provider="first",
            fallbacks=0,
            reserved_tokens=11,
            charged_tokens=37,
            settle_capped=False,
            attempts=[attempt("first", "ok", 0.25)],
        ),
    )


def test_a_400_logs_only_the_base_fields(tmp_path: Path, lines: list[str]) -> None:
    response = LogGateway(tmp_path).post(messages=[])
    assert response.status_code == 400
    (line,) = lines
    check(line, status=400, duration_seconds=0.0, chat=None)


def test_a_401_logs_only_the_base_fields(tmp_path: Path, lines: list[str]) -> None:
    gateway = LogGateway(tmp_path)
    body = {"model": "pair", "messages": [{"role": "user", "content": PROMPT}]}
    response = gateway.client.post(URL, json=body, headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401
    (line,) = lines
    check(line, status=401, duration_seconds=0.0, chat=None)


def test_a_404_for_an_unknown_model_logs_the_chat_fields_as_null(
    tmp_path: Path, lines: list[str]
) -> None:
    assert LogGateway(tmp_path).post(model="no-such-model").status_code == 404
    (line,) = lines
    check(line, status=404, duration_seconds=0.0, chat=chat_values())


def test_a_404_for_an_unknown_path_logs_other(tmp_path: Path, lines: list[str]) -> None:
    assert LogGateway(tmp_path).client.get("/no/such/path").status_code == 404
    (line,) = lines
    check(line, method="GET", path="other", status=404, duration_seconds=0.0, chat=None)


def test_a_200_for_openapi_json_logs_other(tmp_path: Path, lines: list[str]) -> None:
    assert LogGateway(tmp_path).client.get("/openapi.json").status_code == 200
    (line,) = lines
    check(line, method="GET", path="other", status=200, duration_seconds=0.0, chat=None)


def test_a_429_logs_the_chat_fields_as_null_because_nothing_was_reserved(
    tmp_path: Path, lines: list[str]
) -> None:
    assert LogGateway(tmp_path).post(max_tokens=5000).status_code == 429
    (line,) = lines
    check(line, status=429, duration_seconds=0.0, chat=chat_values())


def test_a_502_after_one_fallback_logs_both_attempts_and_no_serving_provider(
    tmp_path: Path, lines: list[str]
) -> None:
    gateway = LogGateway(
        tmp_path,
        first_error=ProviderError("timeout"),
        second_error=ProviderError("upstream_status", 400),
    )
    assert gateway.post().status_code == 502
    (line,) = lines
    check(
        line,
        status=502,
        duration_seconds=0.75,
        chat=chat_values(
            reserved_tokens=11,
            charged_tokens=0,
            settle_capped=False,
            attempts=[attempt("first", "timeout", 0.25), attempt("second", "upstream_status", 0.5)],
        ),
    )


def test_a_500_from_a_raising_limiter_logs_the_chat_fields_as_null(
    tmp_path: Path, lines: list[str]
) -> None:
    gateway = LogGateway(
        tmp_path, reserve_error=RuntimeError("limiter down"), raise_server_exceptions=False
    )
    assert gateway.post().status_code == 500
    (line,) = lines
    check(line, status=500, duration_seconds=0.0, chat=chat_values())


def test_a_settle_that_raises_leaves_the_charge_and_the_cap_null(
    tmp_path: Path, lines: list[str]
) -> None:
    gateway = LogGateway(tmp_path, settle_error=RuntimeError("settle down"))
    with pytest.raises(RuntimeError):
        gateway.post(model="solo-first")
    (line,) = lines
    check(
        line,
        status=500,
        duration_seconds=0.25,
        chat=chat_values(
            provider="first",
            fallbacks=0,
            reserved_tokens=11,
            attempts=[attempt("first", "ok", 0.25)],
        ),
    )


@pytest.mark.parametrize(
    ("usage", "charged_tokens", "capped"),
    [((700, 301), 1000, True), ((700, 300), 1000, False), ((700, 299), 999, False)],
    ids=["above-capacity", "at-capacity", "below-capacity"],
)
def test_settle_capped_is_true_only_above_the_capacity(
    tmp_path: Path,
    lines: list[str],
    usage: tuple[int, int],
    charged_tokens: int,
    capped: bool,
) -> None:
    LogGateway(tmp_path, usage=usage).post(model="solo-first")
    data = json.loads(lines[0])
    assert (data["charged_tokens"], data["settle_capped"]) == (charged_tokens, capped)


@pytest.mark.parametrize(
    ("method", "path", "status", "logged_path"),
    [
        ("GET", "/health", 200, "/health"),
        ("GET", "/metrics", 404, "/metrics"),
        ("GET", "/docs", 200, "other"),
        ("GET", "/redoc", 200, "other"),
        ("GET", "/openapi.json", 200, "other"),
        ("GET", "/healthz", 404, "other"),
        ("GET", "/docs/oauth2-redirect", 200, "other"),
    ],
)
def test_each_path_is_logged_as_one_of_the_bounded_values(
    tmp_path: Path, lines: list[str], method: str, path: str, status: int, logged_path: str
) -> None:
    response = LogGateway(tmp_path).client.request(method, path)
    assert response.status_code == status
    check(lines[0], method=method, path=logged_path, status=status, duration_seconds=0.0, chat=None)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/v1/chat/completions", "/v1/chat/completions"),
        ("/health", "/health"),
        ("/metrics", "/metrics"),
        ("/health/", "other"),
        ("/Health", "other"),
        ("/v1/chat/completions/extra", "other"),
        ("/", "other"),
        ("", "other"),
        ("/docs", "other"),
    ],
)
def test_mapped_path_matches_the_three_served_paths_exactly(path: str, expected: str) -> None:
    assert mapped_path(path) == expected


def test_the_duration_comes_from_the_monotonic_clock_not_the_wall_clock(
    tmp_path: Path, lines: list[str]
) -> None:
    holder: list[LogGateway] = []

    def move_both() -> None:
        holder[0].monotonic.advance(0.25)
        holder[0].clock.advance(999.0)

    gateway = LogGateway(tmp_path, on_first_call=move_both)
    holder.append(gateway)
    gateway.post(model="solo-first")
    assert json.loads(lines[0])["duration_seconds"] == 0.25


def test_the_lookup_duration_is_recorded_on_the_monotonic_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results: list[RequestResult] = []
    monkeypatch.setattr("app.main.log_request", results.append)
    mono_holder: list[FakeMonotonicClock] = []

    class SlowEmbedder(FakeEmbedder):
        async def embed(self, text: str) -> Any:
            mono_holder[0].advance(0.125)
            return await super().embed(text)

    gateway = LogGateway(tmp_path, cache=True, embedder=SlowEmbedder(VECTORS))
    mono_holder.append(gateway.monotonic)
    gateway.post(model="solo-first")
    chat = results[0].chat
    assert chat is not None
    assert chat.lookup_duration_seconds == 0.125


def test_a_new_chat_record_has_every_field_unset() -> None:
    record = ChatRecord()
    assert [getattr(record, name) for name in ChatRecord.__slots__] == [None] * 9


def test_two_interleaved_requests_log_their_own_provider_and_tokens(
    tmp_path: Path, lines: list[str]
) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    class HeldProvider(ScriptedProvider):
        async def complete(self, request: ChatRequest) -> ChatResponse:
            entered.set()
            await release.wait()
            return await super().complete(request)

    held = HeldProvider("first", prompt_tokens=100, completion_tokens=50)
    quick = ScriptedProvider("second", prompt_tokens=30, completion_tokens=12)
    gateway = LogGateway(tmp_path, providers={"first": held, "second": quick})

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=gateway.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH_HEADERS
        ) as client:
            body: dict[str, Any] = {"messages": [{"role": "user", "content": PROMPT}]}
            slow = asyncio.create_task(client.post(URL, json={**body, "model": "solo-first"}))
            await entered.wait()
            done = await client.post(URL, json={**body, "model": "solo-second"})
            assert done.status_code == 200
            assert lines != []  # the quick request has logged while the slow one is held
            release.set()
            assert (await slow).status_code == 200

    asyncio.run(scenario())
    parsed = [json.loads(line) for line in lines]
    assert [(d["provider"], d["charged_tokens"]) for d in parsed] == [
        ("second", 42),
        ("first", 150),
    ]
    assert [d["attempts"][0]["provider"] for d in parsed] == ["second", "first"]


# Calling the ASGI app and the middleware directly, with hand-built scopes.


def http_scope(path: str, app: Any) -> Scope:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "client": ("127.0.0.1", 5000),
        "server": ("test", 80),
        "headers": [],
        "app": app,
    }


async def no_receive() -> Message:
    return {"type": "http.disconnect"}


def test_the_duration_includes_sending_the_body(tmp_path: Path, lines: list[str]) -> None:
    gateway = LogGateway(tmp_path)

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body":
            gateway.monotonic.advance(0.5)

    asyncio.run(gateway.app(http_scope("/health", gateway.app), no_receive, send))
    (line,) = lines
    check(line, method="GET", path="/health", status=200, duration_seconds=0.5, chat=None)


def test_nothing_is_logged_before_the_last_message_is_sent(
    tmp_path: Path, lines: list[str]
) -> None:
    gateway = LogGateway(tmp_path)
    seen: list[tuple[str, int]] = []

    async def send(message: Message) -> None:
        seen.append((message["type"], len(lines)))

    asyncio.run(gateway.app(http_scope("/health", gateway.app), no_receive, send))
    assert seen == [("http.response.start", 0), ("http.response.body", 0)]
    assert len(lines) == 1


class Probe:
    """A bare ASGI app for the middleware: sends `messages`, then raises `error` if one is set."""

    def __init__(self, messages: list[Message], error: Exception | None = None) -> None:
        self.messages = messages
        self.error = error

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        for message in self.messages:
            await send(message)
        if self.error is not None:
            raise self.error


def run_middleware(
    probe: Probe, scope_type: str = "http"
) -> tuple[list[RequestResult], list[Message]]:
    results: list[RequestResult] = []
    sent: list[Message] = []
    host = SimpleNamespace(state=SimpleNamespace(monotonic_clock=FakeMonotonicClock()))
    middleware = RequestMiddleware(probe, observers=(results.append,))
    scope = http_scope("/health", host)
    scope["type"] = scope_type

    async def send(message: Message) -> None:
        sent.append(message)

    asyncio.run(middleware(scope, no_receive, send))
    return results, sent


START: Message = {"type": "http.response.start", "status": 204, "headers": []}
BODY: Message = {"type": "http.response.body", "body": b""}


def test_a_raise_before_the_response_starts_is_logged_once_as_500_and_propagates(
    tmp_path: Path, lines: list[str]
) -> None:
    gateway = LogGateway(tmp_path, reserve_error=RuntimeError("down"))
    with pytest.raises(RuntimeError, match="down"):
        gateway.post()
    assert len(lines) == 1
    assert json.loads(lines[0])["status"] == 500


def test_the_middleware_logs_a_raise_before_start_once_as_500_and_re_raises() -> None:
    results: list[RequestResult] = []
    host = SimpleNamespace(state=SimpleNamespace(monotonic_clock=FakeMonotonicClock()))
    middleware = RequestMiddleware(Probe([], ValueError("boom")), observers=(results.append,))

    async def send(message: Message) -> None:
        raise AssertionError("nothing is sent")

    with pytest.raises(ValueError, match="boom"):
        asyncio.run(middleware(http_scope("/health", host), no_receive, send))
    assert [result.status for result in results] == [500]


def test_a_raise_after_the_response_started_logs_the_status_already_sent_once() -> None:
    results: list[RequestResult] = []
    host = SimpleNamespace(state=SimpleNamespace(monotonic_clock=FakeMonotonicClock()))
    middleware = RequestMiddleware(Probe([START], ValueError("late")), observers=(results.append,))

    async def send(message: Message) -> None:
        return None

    with pytest.raises(ValueError, match="late"):
        asyncio.run(middleware(http_scope("/health", host), no_receive, send))
    assert [result.status for result in results] == [204]


def test_an_app_that_returns_without_a_response_is_logged_as_500_once() -> None:
    results, sent = run_middleware(Probe([]))
    assert [result.status for result in results] == [500]
    assert sent == []


def test_every_message_reaches_the_server_unchanged() -> None:
    results, sent = run_middleware(Probe([START, BODY]))
    assert sent == [START, BODY]
    assert [result.status for result in results] == [204]


@pytest.mark.parametrize("scope_type", ["lifespan", "websocket"])
def test_a_scope_that_is_not_http_is_passed_through_and_not_logged(scope_type: str) -> None:
    results, sent = run_middleware(Probe([START]), scope_type)
    assert results == []
    assert sent == [START]


# The formatter.


def make_record(
    name: str = REQUEST_LOGGER,
    message: str = "m",
    *,
    fields: dict[str, Any] | None = None,
    exc_info: Any = None,
    args: Any = None,
) -> logging.LogRecord:
    record = logging.LogRecord(name, logging.INFO, __file__, 1, message, args, exc_info)
    record.created = 1700000000.123456
    if fields is not None:
        record.tollgate_fields = fields
    return record


def test_the_time_field_is_the_utc_creation_time_in_iso_8601_with_milliseconds() -> None:
    data = json.loads(JsonFormatter().format(make_record(fields={"event": "x"})))
    assert data["time"] == "2023-11-14T22:13:20.123Z"
    assert data["level"] == "INFO"
    assert data["logger"] == REQUEST_LOGGER


def test_a_field_with_separators_and_control_characters_stays_on_one_ascii_line() -> None:
    value = 'a\u2028b\u0085c\x01d\u2029e\r\u00e9"\\'
    out = JsonFormatter().format(make_record(fields={"event": value}))
    assert out.isascii()
    assert len(out.splitlines()) == 1
    for escape in ("\\u2028", "\\u0085", "\\u0001", "\\u2029", "\\r", "\\u00e9", '\\"', "\\\\"):
        assert escape in out
    assert json.loads(out)["event"] == value


def test_a_provider_name_with_a_quote_and_a_backslash_is_one_valid_ascii_line(
    tmp_path: Path, lines: list[str]
) -> None:
    name = 'we"ird\\name'
    table = {"providers": {name: {"type": "mock"}}, "routes": {"r": [{"provider": name}]}}
    providers = {name: ScriptedProvider(name)}
    gateway = LogGateway(tmp_path, table=table, providers=providers)
    assert gateway.post(model="r").status_code == 200
    (line,) = lines
    assert line.isascii()
    assert len(line.splitlines()) == 1
    data = json.loads(line)
    assert data["provider"] == name
    assert data["attempts"][0]["provider"] == name


def test_another_logger_gets_only_the_safe_fields_and_the_exception_type() -> None:
    marker = "SENTINEL-exception-text"
    try:
        raise RuntimeError(marker)
    except RuntimeError:
        exc_info = sys.exc_info()
    out = JsonFormatter().format(make_record("uvicorn.error", "failed %s", args=("x",)))
    assert list(json.loads(out)) == ["time", "level", "logger", "message"]
    assert json.loads(out)["message"] == "failed x"
    record = make_record("uvicorn.error", "Exception in ASGI application", exc_info=exc_info)
    out = JsonFormatter().format(record)
    assert list(json.loads(out)) == ["time", "level", "logger", "message", "exception_type"]
    assert json.loads(out)["exception_type"] == "RuntimeError"
    assert marker not in out
    assert "Traceback" not in out


def test_another_logger_ignores_request_fields_and_a_request_record_without_them_is_plain() -> None:
    out = JsonFormatter().format(make_record("uvicorn", "hello", fields={"event": "x"}))
    assert list(json.loads(out)) == ["time", "level", "logger", "message"]
    out = JsonFormatter().format(make_record(REQUEST_LOGGER, "plain"))
    assert json.loads(out)["message"] == "plain"


def test_a_non_finite_number_is_refused_rather_than_written() -> None:
    with pytest.raises(ValueError, match="Out of range float"):
        JsonFormatter().format(make_record(fields={"duration_seconds": float("nan")}))


def test_fastapi_native_telemetry_is_off_even_when_the_environment_asks_for_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FASTAPI_OTEL_AUTO_CONFIGURE", "true")
    application = create_app(make_settings(), FakeClock())
    config: dict[str, Any] = dict(application._telemetry)  # a private attribute: the only handle
    flags = ("tracing", "metrics", "logs", "operation_spans", "auto_configure")
    assert [config[flag] for flag in flags] == [False] * 5
