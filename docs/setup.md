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
uvicorn --factory app.main:create_app --reload
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

## Configuration

The gateway reads its settings from environment variables when the app is built, and refuses to start if one is
invalid. The error names the variable and the reason, never the value. API keys and the Redis URL are masked in
`repr()` and never appear in error messages. Do not put real values in the repository.

| Variable | Meaning | Default | Required |
| --- | --- | --- | --- |
| `TOLLGATE_API_KEYS` | Comma-separated API keys that clients may present; surrounding spaces are trimmed, empty keys are rejected | none | yes |
| `TOLLGATE_TOKENS_PER_MINUTE` | Refill rate of each key's token bucket, as a whole number greater than 0 | none | yes |
| `TOLLGATE_CAPACITY_TOKENS` | Bucket capacity in tokens, a whole number greater than 0 | the value of `TOLLGATE_TOKENS_PER_MINUTE` | no |
| `TOLLGATE_LIMITER_BACKEND` | `memory` or `redis` (lower case, exact) | `memory` | no |
| `TOLLGATE_REDIS_URL` | Redis connection URL; may contain a password | none | only when the backend is `redis` |

Numbers are plain ASCII digits, at most 18: `1_000`, `1e3`, `1.5`, signs and spaces inside the number are
rejected. `TOLLGATE_REDIS_URL` is ignored when the backend is `memory`.

### Authentication

`POST /v1/chat/completions` requires `Authorization: Bearer <key>`, where the key is one of
`TOLLGATE_API_KEYS`. Every failure gets the same 401 (a missing header, a scheme other than `Bearer`, an empty
or unknown key, or more than one `Authorization` header), with a `WWW-Authenticate: Bearer` header; a header
value with a NUL, form feed or vertical tab byte never reaches the gateway, because uvicorn answers it with its
own 400. The scheme
name is case-insensitive, and extra spaces between the scheme and the key (or after it) are ignored. A tab
between them, or other whitespace such as a non-breaking space, is not; a tab at the start or end of the whole
header value is removed by the HTTP parser (h11, which uvicorn uses here) before the gateway sees it. The
check runs before the body is
read, so an unauthenticated request never gets a validation error. The authenticator keeps only SHA-256
digests of the keys, and the digest is the caller id used later for rate limits; the configured keys themselves
stay in the settings as masked secrets. The digests are unsalted, so use long random keys. Header bytes are
read as UTF-8, so a non-ASCII key works only if the client sends it as UTF-8; plain printable ASCII keys avoid
the question.

`GET /health` needs no key. `/openapi.json` and `/docs` also need no key, which is a known gap: they describe
the API but not any key or user data.

Start the server through the app factory, with the variables set in your shell:

```bash
TOLLGATE_API_KEYS="<your keys>" TOLLGATE_TOKENS_PER_MINUTE=60000 \
  uvicorn --factory app.main:create_app
```

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

1. In a new venv, install the runtime packages (`fastapi`, `pydantic`, `uvicorn`) with `--only-binary=:all:`, run
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
