"""The JSON request log (ADR-0016): one line per request, and a safe line for every other logger.

`log_request` is an observer: it puts the record's fields on a `tollgate.request` log record, and
`JsonFormatter` renders them. A record from any other logger is written with `time`, `level`,
`logger` and `message` only, plus `exception_type` when it carries an exception; the exception's
message and traceback are never written, because they can echo a prompt or provider internals.
`ensure_ascii=True` escapes every non-ASCII and control character, so a line is one ASCII line.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.observability.record import RequestResult

REQUEST_LOGGER = "tollgate.request"
REQUEST_EVENT = "http_request"
FIELDS_ATTRIBUTE = "tollgate_fields"


def request_fields(result: RequestResult) -> dict[str, Any]:
    """The request's fields, in the order ADR-0016 lists them. Nothing else is ever added."""
    fields: dict[str, Any] = {
        "event": REQUEST_EVENT,
        "method": result.method,
        "path": result.path,
        "status": result.status,
        "duration_seconds": result.duration_seconds,
    }
    chat = result.chat
    if chat is not None:
        fields["provider"] = chat.provider
        fields["fallbacks"] = chat.fallbacks
        fields["cache"] = chat.cache
        fields["skip_reason"] = chat.skip_reason
        fields["reserved_tokens"] = chat.reserved_tokens
        fields["charged_tokens"] = chat.charged_tokens
        fields["settle_capped"] = chat.settle_capped
        fields["attempts"] = (
            None
            if chat.attempts is None
            else [
                {
                    "provider": attempt.provider_name,
                    "outcome": attempt.outcome,
                    "duration_seconds": attempt.duration_seconds,
                }
                for attempt in chat.attempts
            ]
        )
    return fields


def log_request(result: RequestResult) -> None:
    """The first observer: one INFO record on `tollgate.request`."""
    logging.getLogger(REQUEST_LOGGER).info(
        REQUEST_EVENT, extra={FIELDS_ATTRIBUTE: request_fields(result)}
    )


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        moment = datetime.fromtimestamp(record.created, UTC)
        line: dict[str, Any] = {
            "time": moment.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
        }
        fields: dict[str, Any] | None = getattr(record, FIELDS_ATTRIBUTE, None)
        if record.name == REQUEST_LOGGER and fields is not None:
            line.update(fields)
        else:
            line["message"] = record.getMessage()
            exc_info = record.exc_info
            if exc_info is not None and exc_info[0] is not None:
                line["exception_type"] = exc_info[0].__name__
        return json.dumps(line, ensure_ascii=True, allow_nan=False)
