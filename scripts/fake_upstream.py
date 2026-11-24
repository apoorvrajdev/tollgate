"""A fake OpenAI-compatible upstream for the load benchmark (T-406, ADR-0018 scenario B).

Usage:
  python scripts/fake_upstream.py [--host 127.0.0.1] [--port 8100] [--delay-ms 50]

It answers POST /v1/chat/completions with one fixed body after a fixed delay, so the gateway's
real `openai` adapter, client and routing run while the upstream's own time stays constant.
"""

import argparse
import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

type Sleep = Callable[[float], Awaitable[None]]

CHAT_PATH = "/v1/chat/completions"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8100
DEFAULT_DELAY_MS = 50
MILLISECONDS_PER_SECOND = 1000
# Every field the openai adapter checks (app/providers/openai.py), with fixed values.
FIXED_BODY: dict[str, Any] = {
    "id": "chatcmpl-fake-upstream",
    "object": "chat.completion",
    "created": 1767225600,
    "model": "fake-upstream",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "ok"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 9, "completion_tokens": 1, "total_tokens": 10},
}


def build_app(delay_seconds: float, sleep: Sleep) -> Starlette:
    """The fake: each chat request waits `await sleep(delay_seconds)`, then gets FIXED_BODY."""

    async def chat(request: Request) -> JSONResponse:
        await request.body()  # read the whole request before answering, as a real server does
        await sleep(delay_seconds)
        return JSONResponse(FIXED_BODY)

    app = Starlette(routes=[Route(CHAT_PATH, chat, methods=["POST"])])
    app.state.delay_seconds = delay_seconds
    return app


def _parse(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve a fake OpenAI-compatible upstream.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--delay-ms", type=int, default=DEFAULT_DELAY_MS)
    args = parser.parse_args(argv)
    if args.delay_ms < 0:
        parser.error("--delay-ms must not be negative")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse(argv)
    app = build_app(args.delay_ms / MILLISECONDS_PER_SECOND, asyncio.sleep)
    uvicorn.run(app, host=args.host, port=args.port, access_log=False, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
