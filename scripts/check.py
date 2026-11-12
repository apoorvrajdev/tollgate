"""Run every project check in order and stop at the first failure.

Usage: python scripts/check.py

Uses only the standard library. Each step runs with the interpreter that runs this
script, from the repository root, so the result does not depend on the current directory.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Each step is (name, command). mypy and pytest take their paths from pyproject.toml.
STEPS: list[tuple[str, list[str]]] = [
    ("ruff check", [sys.executable, "-m", "ruff", "check", "."]),
    ("ruff format --check", [sys.executable, "-m", "ruff", "format", "--check", "."]),
    ("mypy", [sys.executable, "-m", "mypy"]),
    # The contract test is its own step so a snapshot failure names itself. The pytest step
    # skips that file so no test runs twice; keep the two entries and ci.yml in step.
    ("contract", [sys.executable, "-m", "pytest", "tests/test_openapi_snapshot.py"]),
    ("pytest", [sys.executable, "-m", "pytest", "--ignore=tests/test_openapi_snapshot.py"]),
]


def main() -> int:
    total = len(STEPS)
    for number, (name, command) in enumerate(STEPS, start=1):
        print(f"==> [{number}/{total}] {name}", flush=True)
        result = subprocess.run(command, cwd=ROOT, check=False)
        if result.returncode != 0:
            print(f"FAILED: {name} (exit {result.returncode})", file=sys.stderr, flush=True)
            return 1
    print(f"All {total} steps passed", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
