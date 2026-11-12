"""Contract test: the live OpenAPI document must equal the committed snapshot (ADR-0005).

The snapshot is read here and never written. Only scripts/regenerate_openapi.py writes it.
"""

import copy
import json
from pathlib import Path
from typing import Any

from app.main import create_app
from tests.fakes import FakeClock, make_settings

SNAPSHOT_PATH = Path(__file__).parent / "contract" / "openapi.json"
REGENERATE_HINT = (
    "The OpenAPI contract changed. If the task allows it, run "
    "'.venv/Scripts/python scripts/regenerate_openapi.py' and commit the diff."
)


def load_snapshot() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    return loaded


def differs(snapshot: dict[str, Any], live: dict[str, Any]) -> bool:
    return snapshot != live


def test_live_openapi_matches_snapshot() -> None:
    assert not differs(load_snapshot(), create_app(make_settings(), FakeClock()).openapi()), (
        REGENERATE_HINT
    )


def is_canonical(text: str) -> bool:
    """True for sorted keys, indent 2, LF line endings and a final newline."""
    canonical = json.dumps(json.loads(text), indent=2, sort_keys=True, ensure_ascii=False)
    return text == canonical + "\n"


def test_snapshot_file_is_canonical_lf_text() -> None:
    assert is_canonical(SNAPSHOT_PATH.read_bytes().decode("utf-8"))


def test_is_canonical_accepts_canonical_text() -> None:
    assert is_canonical('{\n  "a": 1,\n  "b": 2\n}\n')


def test_is_canonical_keeps_non_ascii_characters_raw() -> None:
    # The regenerate script writes ensure_ascii=False: raw UTF-8 is canonical, \u escapes are not.
    assert is_canonical('{\n  "title": "café"\n}\n')
    assert not is_canonical('{\n  "title": "caf\\u00e9"\n}\n')


def test_is_canonical_rejects_wrong_indent() -> None:
    assert not is_canonical('{\n    "a": 1\n}\n')


def test_is_canonical_rejects_unsorted_keys() -> None:
    assert not is_canonical('{\n  "b": 2,\n  "a": 1\n}\n')


def test_is_canonical_rejects_crlf_line_endings() -> None:
    assert not is_canonical('{\r\n  "a": 1\r\n}\r\n')


def test_is_canonical_rejects_missing_trailing_newline() -> None:
    assert not is_canonical('{\n  "a": 1\n}')


def test_comparison_detects_removed_route() -> None:
    live = copy.deepcopy(create_app(make_settings(), FakeClock()).openapi())
    del live["paths"]["/health"]
    assert differs(load_snapshot(), live)


def test_comparison_detects_renamed_field() -> None:
    live = copy.deepcopy(create_app(make_settings(), FakeClock()).openapi())
    properties = live["components"]["schemas"]["HealthResponse"]["properties"]
    properties["state"] = properties.pop("status")
    assert differs(load_snapshot(), live)


def test_comparison_detects_changed_status_code() -> None:
    live = copy.deepcopy(create_app(make_settings(), FakeClock()).openapi())
    responses = live["paths"]["/health"]["get"]["responses"]
    responses["201"] = responses.pop("200")
    assert differs(load_snapshot(), live)


def test_comparison_detects_added_route() -> None:
    live = copy.deepcopy(create_app(make_settings(), FakeClock()).openapi())
    live["paths"]["/extra"] = {"get": {"responses": {"200": {"description": "ok"}}}}
    assert differs(load_snapshot(), live)


def test_comparison_accepts_identical_documents() -> None:
    assert not differs(load_snapshot(), copy.deepcopy(load_snapshot()))


def test_comparing_does_not_modify_snapshot_file() -> None:
    before = SNAPSHOT_PATH.read_bytes()
    differs(load_snapshot(), create_app(make_settings(), FakeClock()).openapi())
    assert SNAPSHOT_PATH.read_bytes() == before
