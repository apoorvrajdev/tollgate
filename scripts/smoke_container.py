"""Smoke-test a running Tollgate container stack (T-405, ADR-0017). Standard library only.

Usage:
    TOLLGATE_API_KEYS=<key> TOLLGATE_METRICS_TOKEN=<token> python scripts/smoke_container.py [url]

The API key is the first entry of TOLLGATE_API_KEYS. Each check is a function over a status, the
headers and the body, so it can be unit-tested without a server. Exit code 0 means all passed.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
REQUEST_TIMEOUT_SECONDS = 10
CHAT_PATH = "/v1/chat/completions"
CHAT_BODY: dict[str, object] = {
    "model": "smoke",
    "messages": [{"role": "user", "content": "hello"}],
}
CHAT_200_METRIC_PREFIX = 'tollgate_http_requests_total{path="/v1/chat/completions",status="200"} '
LIMIT_HEADERS = (
    "x-ratelimit-limit-tokens",
    "x-ratelimit-remaining-tokens",
    "x-ratelimit-reset-tokens",
)

Headers = Mapping[str, str]


def check_health(status: int, headers: Headers, body: str) -> str | None:
    return None if status == 200 else f"expected 200, got {status}"


def check_chat_ok(status: int, headers: Headers, body: str) -> str | None:
    if status != 200:
        return f"expected 200, got {status}"
    if not headers.get("x-tollgate-provider"):
        return "missing x-tollgate-provider"
    if headers.get("x-tollgate-cache") != "skip":
        return f"expected x-tollgate-cache: skip, got {headers.get('x-tollgate-cache')!r}"
    for name in LIMIT_HEADERS:
        if name not in headers:
            return f"missing {name}"
    return None


def check_unauthorized(status: int, headers: Headers, body: str) -> str | None:
    return None if status == 401 else f"expected 401, got {status}"


def check_metrics_counts_chat(status: int, headers: Headers, body: str) -> str | None:
    if status != 200:
        return f"expected 200, got {status}"
    for line in body.splitlines():
        if line.startswith(CHAT_200_METRIC_PREFIX):
            try:
                count = float(line[len(CHAT_200_METRIC_PREFIX) :])
            except ValueError:
                return f"unreadable metric line: {line!r}"
            return None if count >= 1 else "chat 200 count is 0"
    return "no tollgate_http_requests_total line for the chat 200"


def send(
    url: str, *, token: str | None = None, body: dict[str, object] | None = None
) -> tuple[int, dict[str, str], str]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, method="GET" if data is None else "POST")
    if data is not None:
        request.add_header("content-type", "application/json")
    if token is not None:
        request.add_header("authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return response.status, _lower(response.headers.items()), response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, _lower(error.headers.items()), error.read().decode()


def _lower(items: Iterable[tuple[str, str]]) -> dict[str, str]:
    return {name.lower(): value for name, value in items}


def run(base_url: str, api_key: str, metrics_token: str) -> list[str]:
    """Send the five requests in order and return one failure message per failed check."""
    plan: list[tuple[str, str, dict[str, object] | None, str | None, Callable[..., str | None]]] = [
        ("GET /health", "/health", None, None, check_health),
        ("chat with key", CHAT_PATH, CHAT_BODY, api_key, check_chat_ok),
        ("chat without key", CHAT_PATH, CHAT_BODY, None, check_unauthorized),
        ("GET /metrics with token", "/metrics", None, metrics_token, check_metrics_counts_chat),
        ("GET /metrics without token", "/metrics", None, None, check_unauthorized),
    ]
    failures: list[str] = []
    for name, path, body, token, check in plan:
        status, headers, text = send(base_url + path, token=token, body=body)
        problem = check(status, headers, text)
        print(f"{'FAIL' if problem else 'ok  '} {name}" + (f": {problem}" if problem else ""))
        if problem:
            failures.append(f"{name}: {problem}")
    return failures


def main(argv: list[str]) -> int:
    api_key = os.environ.get("TOLLGATE_API_KEYS", "").split(",")[0].strip()
    metrics_token = os.environ.get("TOLLGATE_METRICS_TOKEN", "")
    if not api_key or not metrics_token:
        print("TOLLGATE_API_KEYS and TOLLGATE_METRICS_TOKEN must be set", file=sys.stderr)
        return 2
    base_url = argv[1] if len(argv) > 1 else DEFAULT_BASE_URL
    return 1 if run(base_url, api_key, metrics_token) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
