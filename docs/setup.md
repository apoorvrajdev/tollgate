# Setup

How to get the project running on a Windows development machine with Git Bash. Until task T-001 lands, the
commands below are the whole workflow; T-001 adds `python scripts/check.py` as the single check command.

## Prerequisites

| Tool | Required | Detected when this guide was written |
| --- | --- | --- |
| Python | standard Windows build of 3.13 from python.org (not the MSYS2/MinGW one) | 3.13.2 via `py -3.13` |
| Git | any recent version | 2.52.0 (Windows) |
| Node.js | 20 or newer, only for the commit hooks | 24.12.0 |
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
python -m pip install --only-binary=:all: -r requirements.txt
```

`--only-binary=:all:` makes pip fail instead of compiling from source if a wheel is missing. After activation,
`python` is the venv's Python. Without activating, call `.venv/Scripts/python` explicitly.

## Run and test

```bash
python -m pytest
uvicorn app.main:app --reload
curl localhost:8000/health   # {"status":"ok"}
```

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
