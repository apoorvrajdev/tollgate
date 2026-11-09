# tollgate

Token-aware rate limiting, model routing and semantic caching for LLM APIs

Documentation: [setup](docs/setup.md) · [architecture](docs/ARCHITECTURE.md) · [decisions](docs/DECISIONS.md) · [tasks](docs/TASKS.md)

## Setup (Windows, Git Bash)

Requires a standard Windows Python 3.13 from python.org (not the MSYS2/MinGW one, which has no prebuilt wheels for pydantic-core).

```bash
py -3.13 -m venv .venv
source .venv/Scripts/activate
pip install --only-binary=:all: -r requirements-dev.txt
```

Run the checks (lint, format, types, tests):

```bash
python scripts/check.py
```

Run the server and check health:

```bash
uvicorn app.main:app --reload
curl localhost:8000/health   # {"status":"ok"}
```
