"""The checks in scripts/smoke_container.py, as functions over a status, headers and body."""

import importlib.util
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent


def _load() -> ModuleType:
    # scripts/ is not a package.
    spec = importlib.util.spec_from_file_location(
        "smoke_container_script", ROOT / "scripts" / "smoke_container.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


smoke = _load()
type Check = Callable[[int, dict[str, str], str], str | None]
check_health: Check = smoke.check_health
check_chat_ok: Check = smoke.check_chat_ok
check_unauthorized: Check = smoke.check_unauthorized
check_metrics_counts_chat: Check = smoke.check_metrics_counts_chat

GOOD_HEADERS = {
    "x-tollgate-provider": "mock",
    "x-tollgate-cache": "skip",
    "x-ratelimit-limit-tokens": "60000",
    "x-ratelimit-remaining-tokens": "59990",
    "x-ratelimit-reset-tokens": "1s",
}
CHAT_LINE = 'tollgate_http_requests_total{path="/v1/chat/completions",status="200"} '


def test_health_accepts_only_200() -> None:
    assert check_health(200, {}, "") is None
    for status in (204, 401, 404, 500, 503):
        assert check_health(status, {}, "") is not None


def test_chat_ok_accepts_a_complete_200() -> None:
    assert check_chat_ok(200, GOOD_HEADERS, "{}") is None


def test_chat_ok_rejects_every_status_but_200() -> None:
    for status in (201, 401, 429, 502):
        assert check_chat_ok(status, GOOD_HEADERS, "{}") is not None


def test_chat_ok_rejects_each_missing_or_wrong_header() -> None:
    for name in GOOD_HEADERS:
        headers = {k: v for k, v in GOOD_HEADERS.items() if k != name}
        assert check_chat_ok(200, headers, "{}") is not None, name
    assert check_chat_ok(200, {**GOOD_HEADERS, "x-tollgate-cache": "hit"}, "{}") is not None
    assert check_chat_ok(200, {**GOOD_HEADERS, "x-tollgate-provider": ""}, "{}") is not None


def test_unauthorized_accepts_only_401() -> None:
    assert check_unauthorized(401, {}, "") is None
    for status in (200, 403, 404, 429):
        assert check_unauthorized(status, {}, "") is not None


def test_metrics_counts_a_chat_200() -> None:
    body = "# HELP x y\n" + CHAT_LINE + "3\nother 1\n"
    assert check_metrics_counts_chat(200, {}, body) is None
    assert check_metrics_counts_chat(200, {}, CHAT_LINE + "1.0\n") is None


def test_metrics_rejects_a_zero_missing_or_other_status_count() -> None:
    assert check_metrics_counts_chat(200, {}, CHAT_LINE + "0\n") is not None
    assert check_metrics_counts_chat(200, {}, "") is not None
    other = CHAT_LINE.replace('status="200"', 'status="401"') + "5\n"
    assert check_metrics_counts_chat(200, {}, other) is not None
    assert check_metrics_counts_chat(401, {}, CHAT_LINE + "3\n") is not None
    assert check_metrics_counts_chat(200, {}, CHAT_LINE + "abc\n") is not None
