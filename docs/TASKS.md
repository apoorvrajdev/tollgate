# Tasks

The task board for the project. One task is `in-progress` at a time. Each task is small enough to review as
one change and has acceptance criteria that can be checked with evidence.

**Statuses:** `todo` → `in-progress` (branch open) → `done`. `review` is used only while a pull request waits for
an owner check; a normal task goes straight from `in-progress` to `done`. `blocked` = stopped, reason in the Log.
A task becomes `done` in the pull request that delivers it (the status is set in the branch's last commit and
takes effect when the pull request merges). `in-progress` and `review` exist only on the task branch; `main`
shows `todo`, `blocked` or `done`.

## Current phase: 0 - Foundation

A reproducible Python toolchain, one check command, commit guards under test, CI, and a frozen API contract.
No gateway features yet.

**Gate (owner signs off):**

- [ ] `python scripts/check.py` is green locally and in CI (lint, format, mypy strict, tests)
- [ ] The commit guards are covered by tests, and those tests passed a mutation check
- [ ] CI runs on Python 3.13 for every pull request and push to `main`
- [ ] The OpenAPI snapshot test is in place
- [ ] ADR-0003, ADR-0004 and ADR-0005 accepted or revised
- [ ] Every commit is authored by the owner, with no co-author trailers; merge commits created by GitHub may
      show GitHub as committer

## Board

| ID | Title | Phase | Status | Depends on |
| --- | --- | --- | --- | --- |
| T-000 | Project skeleton | 0 | done | - |
| T-001 | Toolchain: pyproject, pinned requirements, check script | 0 | todo | ADR-0003 accepted |
| T-002 | Tests for the commit guards | 0 | todo | T-001 |
| T-003 | Continuous integration | 0 | todo | T-001, T-002 |
| T-004 | Typed app skeleton and OpenAPI snapshot | 0 | todo | T-001 |

---

### T-000 - Project skeleton

- **Status:** done (2026-11-09), delivered before this workflow existed
- **Result:** commit `7370304` added `app/main.py` (FastAPI app, `GET /health`), `tests/test_health.py`, a
  pinned `requirements.txt` (`pip freeze` of runtime and dev packages together) and a README setup section.
  It reached `main` by a direct commit, not a pull request. `pytest` passed (1 test) and `/health` returned
  200 under uvicorn, run on Python 3.13.2 (`win-amd64`).

### T-001 - Toolchain: pyproject, pinned requirements, check script

- **Status:** todo
- **Goal:** one command that lints, type-checks and tests the project the same way everywhere (ADR-0003).
- **Context:** ADR-0003, ARCHITECTURE §6, `requirements.txt`, `app/`, `tests/`.
- **Deliverables:**
  - `pyproject.toml`: project metadata, runtime dependencies, a `dev` group, and settings for ruff, mypy
    (`strict = true`) and pytest.
  - `requirements.txt` (runtime only) and `requirements-dev.txt` (adds the dev tools), exact versions, installed
    with `--only-binary=:all:`.
  - `scripts/check.py`: standard library only; runs `ruff check`, `ruff format --check`, `mypy`, `pytest` in
    that order, stops at the first failure, prints which step failed.
  - Existing code made to pass the strict checks.
  - `docs/setup.md` updated if commands change.
- **Acceptance criteria:**
  1. A fresh venv built with `py -3.13` installs both requirements files with no source builds.
  2. `python scripts/check.py` exits 0, and exits non-zero for each of four planted faults (a lint error, a
     format error, a type error, a failing test), naming the failing step.
  3. Runtime requirements contain no dev-only package (pytest, ruff, mypy, fakeredis).
  4. No dependency outside the task's list is added without owner approval.
- **Verification:** the planted-fault table (criterion 2) on scratch copies; a clean-venv install; `check.py`.
- **Branch and commits:** `build/t-001-toolchain`; `build: add pyproject and split pinned requirements`,
  `build(scripts): add check script`, `refactor(app): satisfy strict typing`, `docs(tasks): complete T-001`.
- **Size:** about 120 lines.

### T-002 - Tests for the commit guards

- **Status:** todo
- **Goal:** prove the guards in `.githooks/` behave as intended (the hooks are owner-managed and not edited).
- **Context:** `.githooks/check-commit-msg.mjs`, `.githooks/check-pre-commit.mjs`, ADR-0001.
- **Deliverables:** `tests/test_hooks.py`, running each guard as a child process with `subprocess` (no shell, a
  temporary directory as working directory, pre-commit in its `--files` mode, so no test calls git or touches
  the repository).
- **Acceptance criteria:**
  1. `check-commit-msg.mjs` exits 1 for one sample of every forbidden pattern it defines, and 0 for three normal
     Conventional Commits messages, one of which names a tool in plain prose.
  2. `check-pre-commit.mjs --files` exits 1 for one sample path of every blocked rule, at the root and in a
     subfolder, plus a Windows backslash path; exits 0 for `app/main.py`, `README.md`, `docs/TASKS.md`.
  3. Samples that name a vendor are built from fragments at runtime, so the test file holds no literal
     attribution strings.
  4. Mutation check: the verifier applies at least five mutations to scratch copies of the hooks (a removed
     pattern, a loosened anchor, an inverted exit code, a dropped path rule, a case-sensitive match) and the
     tests catch every one.
  5. If Node.js is missing, the tests fail with a clear message instead of passing.
- **Verification:** `python scripts/check.py` green, run 10 times in a row; the mutation table.
- **Branch and commits:** `test/t-002-commit-guards`; `test(hooks): cover the commit-message guard`,
  `test(hooks): cover the pre-commit guard`, `docs(tasks): complete T-002`.
- **Size:** about 150 lines of tests.

### T-003 - Continuous integration

- **Status:** todo
- **Goal:** the check command runs on every pull request and every push to `main`.
- **Context:** ADR-0002, ADR-0003, `scripts/check.py`.
- **Deliverables:** `.github/workflows/ci.yml`: ubuntu-latest, Python 3.13 with a pip cache, Node.js (for the
  hook tests), install both requirements files, then the check steps as separate steps so a failure names its
  step. Permissions `contents: read`; `persist-credentials: false`; cancel superseded pull-request runs; current
  major versions of the actions, looked up rather than assumed.
- **Acceptance criteria:**
  1. The workflow file is valid YAML and runs the same steps in the same order as `scripts/check.py`.
  2. On the task's pull request, the run triggered by the `pull_request` event is green (`gh pr checks <n>`)
     before merge.
  3. No secret and no paid API is used by the workflow.
- **Verification:** `gh pr checks <n> --watch`; the workflow compared line by line with `check.py`.
- **Branch and commits:** `ci/t-003-workflow`; `ci: run lint, types and tests on every pull request`,
  `docs(tasks): complete T-003`.
- **Size:** about 50 lines. Making the job a required status check is a repository setting for the owner.

### T-004 - Typed app skeleton and OpenAPI snapshot

- **Status:** todo
- **Goal:** a typed app factory, a response model for `/health`, and a committed OpenAPI snapshot that tests
  compare against (ADR-0005, part 1).
- **Context:** `app/main.py`, `tests/test_health.py`, ADR-0004, ADR-0005, ARCHITECTURE §4.
- **Deliverables:** `app/main.py` with `create_app()` and a typed `/health` response; `tests/contract/`
  snapshot file and `tests/test_openapi_snapshot.py`; a documented, explicit way to regenerate the snapshot
  that tests never run.
- **Acceptance criteria:**
  1. `/health` still returns `{"status": "ok"}` with 200, and the response model appears in the OpenAPI document.
  2. The snapshot test passes, and fails when a route, field or status code changes in a scratch copy.
  3. Tests never write the snapshot; only the explicit regenerate command does.
  4. Mutation check: at least three mutations of `app/` (renamed field, removed route, changed status code) are
     caught.
- **Verification:** `python scripts/check.py` green; the mutation table.
- **Branch and commits:** `feat/t-004-openapi-snapshot`; `refactor(app): add app factory and typed health
  response`, `test(contract): add OpenAPI snapshot test`, `docs(tasks): complete T-004`.
- **Size:** about 80 lines plus the generated snapshot.

---

## Later phases (broken into tasks at each gate)

| Phase | Epic |
| --- | --- |
| 1 | Token-aware rate limiting: token counting, Redis token bucket (client decided by ADR), 429 with rate-limit headers, mock provider, `/v1/chat/completions` |
| 2 | Model routing: rules, fallback on provider failure, Ollama, then OpenAI and Anthropic adapters |
| 3 | Semantic caching: embeddings, similarity lookup, thresholds, invalidation |
| 4 | Docker Compose, observability, reproducible load benchmarks |
| 5 | Demo and write-up |

## Log

| Date | Task | Event | Evidence |
| --- | --- | --- | --- |
| 2026-11-09 | T-000 | Project skeleton delivered by a direct commit, before the pull-request flow existed | Commit `7370304`; `pytest` 1 passed; `/health` 200 under uvicorn |
| 2026-11-09 | - | Process change: single-author guards (ADR-0001) and pull-request delivery (ADR-0002) adopted; hooks, ignore rules, architecture, decisions and board added in one docs-only pull request. Toolchain, CI and contract decisions proposed as ADR-0003 to ADR-0005 for the owner | `docs/DECISIONS.md`; guards checked by hand: a trailer and three blocked paths rejected, normal paths accepted (automated tests are T-002) |
