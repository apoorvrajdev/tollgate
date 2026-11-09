# tollgate

Token-aware rate limiting, model routing and semantic caching for LLM APIs

## Setup (Windows, Git Bash)

Requires a standard Windows Python 3.12 or 3.13 from python.org (not the MSYS2/MinGW one, which has no prebuilt wheels for pydantic-core).

```bash
py -3.13 -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
```

Run the tests:

```bash
python -m pytest
```

Run the server and check health:

```bash
uvicorn app.main:app --reload
curl localhost:8000/health   # {"status":"ok"}
```
