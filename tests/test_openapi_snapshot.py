"""Contract test: the live OpenAPI document must equal the committed snapshot (ADR-0005).

The snapshot is read here and never written. Only scripts/regenerate_openapi.py writes it.
"""

import copy
import json
from pathlib import Path
from typing import Any

from app.main import create_app

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
    assert not differs(load_snapshot(), create_app().openapi()), REGENERATE_HINT


def test_snapshot_file_is_canonical_lf_text() -> None:
    text = SNAPSHOT_PATH.read_bytes().decode("utf-8").replace("\r\n", "\n")
    canonical = json.dumps(load_snapshot(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    assert text == canonical


def test_comparison_detects_removed_route() -> None:
    live = copy.deepcopy(create_app().openapi())
    del live["paths"]["/health"]
    assert differs(load_snapshot(), live)


def test_comparison_detects_renamed_field() -> None:
    live = copy.deepcopy(create_app().openapi())
    properties = live["components"]["schemas"]["HealthResponse"]["properties"]
    properties["state"] = properties.pop("status")
    assert differs(load_snapshot(), live)


def test_comparison_detects_changed_status_code() -> None:
    live = copy.deepcopy(create_app().openapi())
    responses = live["paths"]["/health"]["get"]["responses"]
    responses["201"] = responses.pop("200")
    assert differs(load_snapshot(), live)


def test_comparison_detects_added_route() -> None:
    live = copy.deepcopy(create_app().openapi())
    live["paths"]["/extra"] = {"get": {"responses": {"200": {"description": "ok"}}}}
    assert differs(load_snapshot(), live)


def test_comparison_accepts_identical_documents() -> None:
    assert not differs(load_snapshot(), copy.deepcopy(load_snapshot()))


def test_comparing_does_not_modify_snapshot_file() -> None:
    before = SNAPSHOT_PATH.read_bytes()
    differs(load_snapshot(), create_app().openapi())
    assert SNAPSHOT_PATH.read_bytes() == before
