# Setup

How to get the project running on a Windows development machine with Git Bash. `python scripts/check.py` is the
single check command (ADR-0003).

## Prerequisites

| Tool | Required | Detected when this guide was written |
| --- | --- | --- |
| Python | standard Windows build of 3.13 from python.org (not the MSYS2/MinGW one) | 3.13.2 via `py -3.13` |
| Git | any recent version | 2.52.0 (Windows) |
| Node.js | 20 or newer, for the commit hooks and their tests | 24.12.0 locally; 26 in CI (`actions/setup-node`, `node-version: "26"`) |
| GitHub CLI | only for opening pull requests | 2.92.0 |

Why not the MSYS2 Python: `python -c "import sysconfig; print(sysconfig.get_platform())"` prints
`mingw_x86_64_ucrt_gnu` there, so pip finds no prebuilt wheels for packages such as pydantic-core and tries to
compile them. A standard Python prints `win-amd64`. Check with `py -0p`.

## Get the code and install

```bash
git clone https://github.com/apoorvrajdev/tollgate.git
cd tollgate
py -3.13 -m venv .venv
source .venv/Scripts/activate
python -m pip install --only-binary=:all: -r requirements-dev.txt
```

`requirements.txt` holds the runtime packages (what the gateway needs to run). `requirements-dev.txt` adds the
test and lint tools and includes the runtime file. `--only-binary=:all:` makes pip fail instead of compiling from
source if a wheel is missing. After activation, `python` is the venv's Python. Without activating, call
`.venv/Scripts/python` explicitly.

The project is run from the repository root and is not installed as a package (there is no build step), so
`pip install .` does not apply.

## Run and check

```bash
python scripts/check.py
uvicorn app.main:app --reload
curl localhost:8000/health   # {"status":"ok"}
```

`scripts/check.py` runs five steps in order and stops at the first failure, naming it:

| Step | Command it runs |
| --- | --- |
| 1 | `ruff check .` |
| 2 | `ruff format --check .` |
| 3 | `mypy` (strict; paths come from `pyproject.toml`) |
| 4 | `contract`: `pytest tests/test_openapi_snapshot.py` (live OpenAPI equals the snapshot) |
| 5 | `pytest --ignore=tests/test_openapi_snapshot.py` (every other test) |

Run it before every commit. To fix formatting, run `python -m ruff format .`.

## Regenerating the OpenAPI snapshot

`tests/contract/openapi.json` is the committed OpenAPI document (ADR-0005). `tests/test_openapi_snapshot.py`
compares it to the live app and fails on any difference. Tests and `scripts/check.py` never write it. Only this
command does, and only in a task whose card says the contract changes:

```bash
.venv/Scripts/python scripts/regenerate_openapi.py
```

Review the resulting diff before committing it.

## Updating pins

Pins are exact and updated by hand, one task at a time. Use throwaway venvs, not the project one:

1. In a new venv, install the runtime packages (`fastapi`, `uvicorn`) with `--only-binary=:all:`, run
   `pip freeze`, and write the result to `requirements.txt` under its two comment lines.
2. In a second new venv, install the new `requirements.txt`, then `httpx`, `pytest`, `ruff` and `mypy`, run
   `pip freeze`, and put every line that is not in the runtime freeze into `requirements-dev.txt`, after
   `-r requirements.txt`.
3. If a dev tool forces a different version of a runtime package, regenerate the runtime pins at that version so
   both files agree. Run `pip check` in both venvs, then `python scripts/check.py`.

The lower bounds in `pyproject.toml` are not checked against the pins; keep them in step by hand.

## Enable the commit hooks

The hooks in `.githooks/` check that the commit author and committer match one email address, reject
attribution trailers in commit messages and block files that must not be committed. They need Node.js and are
off until you opt in. Run these once per clone:

```bash
git config core.hooksPath .githooks
git config authorguard.email "<your email>"
```

Use the email address you commit with. Without `authorguard.email`, the pre-commit hook refuses to commit. The
reasons are in ADR-0001 and ADR-0002 in [DECISIONS.md](DECISIONS.md).

## Where to go next

[ARCHITECTURE.md](ARCHITECTURE.md) explains the design, [TASKS.md](TASKS.md) lists the work and its status.
