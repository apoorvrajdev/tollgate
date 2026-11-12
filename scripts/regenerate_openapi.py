"""Regenerate the committed OpenAPI snapshot.

Usage: python scripts/regenerate_openapi.py

This is the only code that writes tests/contract/openapi.json. Tests and scripts/check.py
never run it. Run it only in a task whose card says the contract changes (ADR-0005).
"""

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = ROOT / "tests" / "contract" / "openapi.json"


def render(document: dict[str, Any]) -> str:
    """Canonical text of an OpenAPI document: sorted keys, indent 2, LF, trailing newline."""
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    # Running a script puts scripts/ first on sys.path, so add the repository root.
    sys.path.insert(0, str(ROOT))
    from app.main import create_app
    from app.settings import Settings

    # The OpenAPI document does not depend on settings; explicit placeholders avoid reading the
    # caller's environment.
    settings = Settings.from_env(
        {"TOLLGATE_API_KEYS": "openapi-generation-placeholder", "TOLLGATE_TOKENS_PER_MINUTE": "1"}
    )
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SNAPSHOT_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(render(create_app(settings).openapi()))
    print(f"Wrote {SNAPSHOT_PATH.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
