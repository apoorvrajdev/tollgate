"""What one request reports (ADR-0016): the chat route's record and the middleware's result.

The record lives in the ASGI scope's `state`, so it belongs to one request; two requests running on
the event loop at once never share one. A field stays `None` until its step has run.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from starlette.requests import Request
from starlette.types import Scope

from app.routing.router import Attempt

RECORD_KEY = "tollgate_chat_record"


@dataclass(slots=True)
class ChatRecord:
    """What the chat route learned, filled in as it goes.

    `cache` is `None` when no lookup ran (the cache is off, or the request ended before it).
    `lookup_duration_seconds` is for the metrics (T-404); the log does not carry it.
    """

    provider: str | None = None
    fallbacks: int | None = None
    cache: Literal["hit", "miss", "skip"] | None = None
    skip_reason: Literal["not_eligible", "embedder_failed"] | None = None
    reserved_tokens: int | None = None
    charged_tokens: int | None = None
    settle_capped: bool | None = None
    attempts: tuple[Attempt, ...] | None = None
    lookup_duration_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class RequestResult:
    """One finished HTTP request. `path` is already mapped to its bounded value. `chat` is set
    only when the request reached the chat route handler."""

    method: str
    path: str
    status: int
    duration_seconds: float
    chat: ChatRecord | None


type Observer = Callable[[RequestResult], None]


def begin_chat_record(request: Request) -> ChatRecord:
    """Create this request's record, and keep it where the middleware will find it."""
    record = ChatRecord()
    request.scope.setdefault("state", {})[RECORD_KEY] = record
    return record


def chat_record_of(scope: Scope) -> ChatRecord | None:
    record: ChatRecord | None = scope.get("state", {}).get(RECORD_KEY)
    return record
