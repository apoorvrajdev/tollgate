"""A pure ASGI middleware that times each HTTP request and hands the result to its observers.

It is not `BaseHTTPMiddleware`: it wraps `send` to read the status from `http.response.start`, and
it reports once the app has returned, so the duration includes sending the body. A handler that
raises is reported once, with the status already sent or 500 when none was, and the exception
propagates. A request that is cancelled (a `CancelledError`) is not logged. Observers run on
the event loop, must not block and must not raise: one that raises on the error path replaces
the handler's exception.
"""

from collections.abc import Sequence

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.clock import MonotonicClock
from app.observability.record import Observer, RequestResult, chat_record_of

OTHER_PATH = "other"
LOGGED_PATHS = frozenset({"/v1/chat/completions", "/health", "/metrics"})
SERVER_ERROR_STATUS = 500


def mapped_path(path: str) -> str:
    """One of the three served paths exactly, else `other`: the value is bounded by the code."""
    return path if path in LOGGED_PATHS else OTHER_PATH


class RequestMiddleware:
    def __init__(self, app: ASGIApp, observers: Sequence[Observer]) -> None:
        self.app = app
        self._observers = tuple(observers)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        clock: MonotonicClock = scope["app"].state.monotonic_clock
        started_seconds = clock.monotonic_seconds()
        statuses: list[int] = []

        async def send_and_note(message: Message) -> None:
            if message["type"] == "http.response.start":
                statuses.append(message["status"])
            await send(message)

        def report() -> None:
            result = RequestResult(
                method=scope["method"],
                path=mapped_path(scope["path"]),
                status=statuses[0] if statuses else SERVER_ERROR_STATUS,
                duration_seconds=clock.monotonic_seconds() - started_seconds,
                chat=chat_record_of(scope),
            )
            for observe in self._observers:
                observe(result)

        try:
            await self.app(scope, receive, send_and_note)
        except Exception:
            report()
            raise
        report()
