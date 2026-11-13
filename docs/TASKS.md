# Tasks

The task board for the project. One task is `in-progress` at a time. Each task is small enough to review as
one change and has acceptance criteria that can be checked with evidence.

**Statuses:** `todo` → `in-progress` (branch open) → `done`. `review` is used only while a pull request waits for
an owner check; a normal task goes straight from `in-progress` to `done`. `blocked` = stopped, reason in the Log.
A task becomes `done` in the pull request that delivers it (the status is set in the branch's last commit and
takes effect when the pull request merges). `in-progress` and `review` exist only on the task branch; `main`
shows `todo`, `blocked` or `done`.

## Current phase: 2 - Model routing

Each chat completion is routed by its `model` to an ordered list of provider targets read from a validated
route table file, and falls back to the next target on retryable failures. Ollama, OpenAI and Anthropic
adapters are written on plain `httpx` and tested only through `httpx.MockTransport`. One reservation and one
settle per request, as in Phase 1. Planned 2026-11-13; ADR-0010 and ADR-0011 were accepted by the owner the
same day. The README and the ARCHITECTURE status line are updated in the gate close-out pull
request, as for Phase 1.

**Gate (owner signs off):**

- [ ] Every Phase 2 task is `done`, and `python scripts/check.py` is green locally and in CI
- [x] ADR-0010 and ADR-0011 accepted or revised, and the status lines of ADR-0007 and ADR-0008 updated to name
      the ADRs that amend them (accepted as written, 2026-11-13)
- [ ] Routes come from a route table validated at startup; an unknown model gets 404 before any reservation;
      fallback happens only on retryable failures, each target is tried at most once, and each request has one
      reservation and one settle
- [ ] The Ollama, OpenAI and Anthropic adapters translate requests, responses and errors as ADR-0010 says, each
      tested through `httpx.MockTransport` only; no provider SDK is a dependency
- [ ] The app closes the HTTP and Redis clients it builds when it shuts down
- [ ] Tests use no network and no paid API (the CI Redis container excepted, ADR-0006). A real provider is
      called only by the owner, by hand, and the owner's run against a local Ollama is recorded in the Log or
      explicitly waived by the owner
- [ ] Every Phase 2 task that adds tests has a mutation table with no unexplained survivor
- [ ] README and ARCHITECTURE describe what is built, and every claim comes from a recorded run
- [ ] Every commit is authored by the owner, with no co-author trailers

## Phase 1 - Token-aware rate limiting (complete)

`POST /v1/chat/completions` (non-streaming) in front of a mock provider, with API-key authentication and a
per-key token bucket that reserves estimated tokens before the call and settles with actual usage after. State
lives in memory or in Redis. Planned 2026-11-12; ADR-0006 to ADR-0008 were accepted by the owner the same day.
The owner signed off the gate on 2026-11-13. Phase 2 is planned at its own gate (`/plan-phase`).

**Gate (signed off by the owner, 2026-11-13):**

- [x] Every Phase 1 task is `done`, and `python scripts/check.py` is green locally and in CI
- [x] ADR-0006, ADR-0007 and ADR-0008 accepted or revised (accepted as written, 2026-11-12)
- [x] `/v1/chat/completions` works with the mock provider, and the OpenAPI snapshot records its 200, 400, 401,
      429 and 502 responses and the limit headers
- [x] The shared limiter behaviour suite passes on the in-memory limiter, on fakeredis and on a real Redis
      server, the last in the CI step `redis integration`, green on `main`
- [x] Every Phase 1 task that adds tests has a mutation table with no unexplained survivor
- [x] Tests use no network and no paid API, except the CI-only Redis service container on localhost (ADR-0006)
- [x] README and ARCHITECTURE describe what is built, and every claim comes from a recorded run
- [x] Every commit is authored by the owner, with no co-author trailers

## Phase 0 - Foundation (complete)

A reproducible Python toolchain, one check command, commit guards under test, CI, and a frozen API contract.
No gateway features yet. The owner signed off the gate on 2026-11-12, and Phase 1 was planned the same day.

**Gate (signed off by the owner, 2026-11-12):**

- [x] `python scripts/check.py` is green locally and in CI (lint, format, mypy strict, tests)
- [x] CI runs on Python 3.13 for every pull request and push to `main`, in a job named exactly `lint and test`
- [x] `lint and test` is a required status check in the `protect-main` ruleset, which keeps no bypass actors
- [x] The commit guards are covered by tests, and those tests passed a mutation check
- [x] The OpenAPI snapshot test is in place and runs as part of `scripts/check.py`
- [x] ADR-0004 and ADR-0005 accepted or revised (ADR-0003 accepted 2026-11-09)
- [x] Every commit is authored by the owner, with no co-author trailers; merge commits created by GitHub may
      show GitHub as committer (the bootstrap commit `7370304` has the committer name `apoorvrajdev`,
      with the same email)

## Board

Delivery order in Phase 0: T-001, T-003, the owner makes `lint and test` a required check, then T-002, then
T-004. Delivery order in Phase 1: T-101 to T-108 in number order. Delivery order in Phase 2: T-201 to T-207 in
number order. The rows below are in delivery order; the cards further down are listed by ID.

| ID | Title | Phase | Status | Depends on |
| --- | --- | --- | --- | --- |
| T-000 | Project skeleton | 0 | done | - |
| T-001 | Toolchain: pyproject, pinned requirements, check script | 0 | done | - (ADR-0003 accepted) |
| T-003 | Continuous integration | 0 | done | T-001 |
| T-002 | Tests for the commit guards | 0 | done | T-003, and `lint and test` set as a required check (OWNER-CHECK) |
| T-004 | Typed app skeleton and OpenAPI snapshot | 0 | done | T-001, T-003 |
| T-101 | Injected clock and validated settings | 1 | done | Phase 0 gate |
| T-102 | Chat completions endpoint with a mock provider | 1 | done | T-101; ADR-0008 accepted 2026-11-12 |
| T-103 | API key authentication | 1 | done | T-101, T-102; ADR-0008 accepted 2026-11-12 |
| T-104 | Token estimator | 1 | done | T-102; ADR-0007 accepted 2026-11-12 |
| T-105 | In-memory token bucket and the shared behaviour suite | 1 | done | T-101; ADR-0007 accepted 2026-11-12 |
| T-106 | Redis token bucket, unit-tested against fakeredis | 1 | done | T-105; ADR-0006 accepted 2026-11-12 |
| T-107 | Real Redis in CI | 1 | done | T-106 |
| T-108 | Rate limiting on chat completions | 1 | done | T-103, T-104, T-105, T-106 |
| T-201 | Provider errors and the route table | 2 | todo | Phase 1 gate; ADR-0010 and ADR-0011 accepted |
| T-202 | Routing and fallback on chat completions | 2 | todo | T-201 |
| T-203 | Close the clients the app builds on shutdown | 2 | todo | T-202 |
| T-204 | Ollama adapter | 2 | todo | T-203 |
| T-205 | OpenAI adapter | 2 | todo | T-204 |
| T-206 | Anthropic adapter | 2 | todo | T-204 |
| T-207 | Real-provider guide and the owner's Ollama run | 2 | todo | T-204, T-205, T-206 |

---

### T-000 - Project skeleton

- **Status:** done (2026-11-09), delivered before this workflow existed
- **Result:** commit `7370304` added `app/main.py` (FastAPI app, `GET /health`), `tests/test_health.py`, a
  pinned `requirements.txt` (`pip freeze` of runtime and dev packages together) and a README setup section.
  It reached `main` by a direct commit, not a pull request. `pytest` passed (1 test) and `/health` returned
  200 under uvicorn, run on Python 3.13.2 (`win-amd64`).

### T-001 - Toolchain: pyproject, pinned requirements, check script

- **Status:** done (2026-11-09)
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
- **Result:** `pyproject.toml` (project metadata, `requires-python = "==3.13.*"`, runtime dependencies, a `dev`
  extra in `[project.optional-dependencies]` rather than a PEP 735 group so older pip can read it, settings for
  pytest, mypy strict and ruff; not installable, no build system). `requirements.txt` holds 14 runtime pins
  (fastapi 0.162.2, uvicorn 0.54.0 and their dependencies); `requirements-dev.txt` adds 15 (httpx, pytest, ruff
  0.17.4, mypy 2.4.1 and their dependencies). `redis` and `fakeredis` were dropped by the owner's decision: nothing
  imports them, and the Phase 1 ADR decides the Redis client. `scripts/check.py` runs the four steps with the
  interpreter that runs it and stops at the first failure. `[tool.ruff.format]` excludes `*.md`, because ruff
  0.17 also formats code blocks in Markdown and `docs/ARCHITECTURE.md` holds illustrative snippets. The pins were
  generated on Windows only; whether `ast_serialize` and `librt` (mypy dependencies) have Linux wheels at these
  versions is checked by the first CI run (T-003). `pytest` prints a Starlette deprecation warning about
  `httpx` in `TestClient`; it is not a failure.

### T-002 - Tests for the commit guards

- **Status:** done
- **Goal:** prove the guards in `.githooks/` behave as intended (the hooks are owner-managed and not edited).
- **Context:** `.githooks/check-commit-msg.mjs`, `.githooks/check-pre-commit.mjs`, ADR-0001.
- **Deliverables:**
  - `tests/test_hooks.py`, running each guard as a child process with `subprocess` (no shell, a temporary
    directory as working directory, pre-commit in its `--files` mode, so no test calls git or touches the
    repository).
  - `.github/workflows/ci.yml`: a Node.js setup step added before the checks, inside the existing job. The job
    name stays exactly `lint and test`.
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
  6. On the task's pull request, `lint and test` is green with the Node step in place, and it is already a
     required check, so the merge is gated by it.
- **Verification:** `python scripts/check.py` green, run 10 times in a row; the mutation table; `gh pr checks
  <n> --watch`.
- **Branch and commits:** `test/t-002-commit-guards`; `test(hooks): cover the commit-message guard`,
  `test(hooks): cover the pre-commit guard`, `ci: set up Node.js for the hook tests`,
  `docs(tasks): complete T-002`.
- **Size:** about 150 lines of tests plus a few workflow lines.
- **Result:** `tests/test_hooks.py` (168 lines, 49 tests) runs both guards as Node child processes with no shell
  and a temporary working directory; the pre-commit guard runs in `--files` mode, so no test calls git. Vendor
  names are built from fragments. A missing `node` fails the session fixture with a clear message rather than
  skipping, and one test proves that path. Beyond the card it also covers uppercase variants of every pattern and
  rule, prefixed lookalike paths that must pass, a comment line and a mid-line mention that must pass, a missing
  argument (exit 2) and a mixed list of paths. `.github/workflows/ci.yml` gained a `Set up Node.js` step
  (`actions/setup-node` v7.1.0, pinned by SHA, Node 26) before the checks; the job name is unchanged. Local Node
  is 24.12.0, so Node 26 is first exercised by the pull request's run (criterion 6).

### T-003 - Continuous integration

- **Status:** done (2026-11-09); criterion 4 (the owner's required-check step) completed 2026-11-10, read-back in the Log
- **Goal:** the check command runs on every pull request and every push to `main`.
- **Depends on:** T-001 only.
- **Context:** ADR-0002, ADR-0003, `scripts/check.py`.
- **Deliverables:** `.github/workflows/ci.yml` with one job named exactly `lint and test` (the name is what the
  `protect-main` ruleset matches): ubuntu-latest, Python 3.13 with a pip cache, install both requirements files
  with `--only-binary=:all:`, then the check steps as separate steps so a failure names its step. No Node.js
  yet; T-002 adds it. Permissions `contents: read`; `persist-credentials: false`; cancel superseded
  pull-request runs; current major versions of the actions, looked up rather than assumed.
- **Acceptance criteria:**
  1. The workflow file is valid YAML, the job is named exactly `lint and test`, and it runs the same steps in
     the same order as `scripts/check.py`.
  2. On the task's pull request, the run triggered by the `pull_request` event is green (`gh pr checks <n>`)
     before merge.
  3. No secret and no paid API is used by the workflow.
  4. After the merge, the owner makes `lint and test` a required status check in the `protect-main` ruleset,
     with no bypass actors, and confirms it (OWNER-CHECK). T-002 does not start before that.
- **Verification:** `gh pr checks <n> --watch`; the workflow compared line by line with `check.py`; after the
  merge, the ruleset read back with `gh api repos/apoorvrajdev/tollgate/rulesets/<id>`. The first run must show
  that every pin in both requirements files installs on ubuntu-latest with `--only-binary=:all:` (T-001 generated
  them on Windows); if one has no Linux wheel, the pins are regenerated per `docs/setup.md`.
- **Branch and commits:** `ci/t-003-workflow`; `ci: run lint, types and tests on every pull request`,
  `docs(tasks): complete T-003`.
- **Size:** about 50 lines. The required-check setting is a repository setting that only the owner changes.
  This PR cannot be gated by its own check, because the check does not exist as a required check until after
  the merge (see the Log).
- **Result:** `.github/workflows/ci.yml`: workflow `ci`, one job (key `lint-and-test`, display name exactly
  `lint and test`, which is the status-check context), ubuntu-latest, Python 3.13 with a pip cache keyed on both
  requirements files, the four checks as separate steps named as in `scripts/check.py`, triggers on pull requests
  and pushes to `main`, `contents: read`, `persist-credentials: false`, 10-minute timeout, pull-request runs
  cancelled by a newer push and `main` runs never cancelled. The two actions are pinned by commit SHA with the
  version in a comment (checkout v7.0.1, setup-python v7.1.0, resolved from their release tags), not by major tag.
  The run triggered by the pull request (run `42670858105`) was green in 23 seconds. It installed every pin on
  Linux from prebuilt wheels with `--only-binary=:all:`, including `ast_serialize` 0.13.1 and `librt` 0.16.0
  (mypy dependencies) and `pydantic_core`, `mypy` and `ruff`; no source build ran. The runner image at that time
  was Ubuntu 26.04 with Python 3.13.18. The first push to the branch failed with "Invalid workflow file": line 36
  held an unquoted `run:` value containing `:all:` followed by a space, and a colon followed by a space inside an unquoted YAML value
  reads as a nested mapping. The value is now quoted. The checker used before the first push compared strings and
  did not parse YAML, so it missed this; it now flags any such value.

### T-004 - Typed app skeleton and OpenAPI snapshot

- **Status:** done
- **Goal:** a typed app factory, a response model for `/health`, and a committed OpenAPI snapshot that tests
  compare against (ADR-0005, part 1).
- **Context:** `app/main.py`, `tests/test_health.py`, ADR-0004, ADR-0005, ARCHITECTURE §4.
- **Depends on:** T-001, T-003 (the contract step is added to the check script from T-001 and to the workflow
  from T-003). It is planned after T-002 but does not depend on it.
- **Deliverables:** `app/main.py` with `create_app()` and a typed `/health` response; `tests/contract/`
  snapshot file and `tests/test_openapi_snapshot.py`; a documented, explicit way to regenerate the snapshot
  that tests never run; the contract test added to `scripts/check.py` as its own named step, mirrored as a
  separate step in `.github/workflows/ci.yml` inside the job `lint and test` (the job name does not change).
- **Acceptance criteria:**
  1. `/health` still returns `{"status": "ok"}` with 200, and the response model appears in the OpenAPI document.
  2. The snapshot test passes, and fails when a route, field or status code changes in a scratch copy.
  3. Tests never write the snapshot; only the explicit regenerate command does.
  4. Mutation check: at least three mutations of `app/` (renamed field, removed route, changed status code) are
     caught.
  5. `python scripts/check.py` runs the contract test as a named step, and CI runs the same step; a planted
     snapshot difference makes both fail at that step.
- **Verification:** `python scripts/check.py` green; the mutation table; `gh pr checks <n> --watch`.
- **Branch and commits:** `feat/t-004-openapi-snapshot`; `refactor(app): add app factory and typed health
  response`, `test(contract): add OpenAPI snapshot test`, `ci: run the contract test in CI`,
  `docs(tasks): complete T-004`.
- **Size:** about 80 lines plus the generated snapshot.

---

### T-101 - Injected clock and validated settings

- **Status:** done
- **Goal:** time and configuration reach the app through `create_app()`, so later tasks can use a fake clock
  and per-test settings instead of globals.
- **Context:** `app/main.py`, `tests/test_health.py`, ARCHITECTURE §3 and §6, CLAUDE.md §8.
- **Depends on:** the Phase 0 gate (signed off). No ADR.
- **Deliverables:**
  - `app/clock.py`: a `Clock` protocol with `now_seconds() -> float` and `SystemClock` (wall-clock time, since
    several instances share one Redis). `tests/fakes.py`: `FakeClock` that moves only when `advance(seconds)`
    is called.
  - `app/settings.py`: a frozen `Settings` model built by `Settings.from_env(environ)`, from
    `TOLLGATE_API_KEYS` (comma-separated, at least one non-empty key), `TOLLGATE_TOKENS_PER_MINUTE`
    (integer > 0), `TOLLGATE_CAPACITY_TOKENS` (integer > 0, defaults to the per-minute value),
    `TOLLGATE_LIMITER_BACKEND` (`memory` by default, or `redis`) and `TOLLGATE_REDIS_URL` (required when the
    backend is `redis`). API keys are held so that `repr()` and validation errors never show them.
  - `create_app(settings: Settings | None = None, clock: Clock | None = None)`; with no arguments it reads
    `os.environ`. The module-level `app` object is removed, because it would read the environment on import.
    The server starts with `uvicorn --factory app.main:create_app`; `docs/setup.md` and README change to match.
  - `docs/setup.md`: a table of the variables, their meaning and their defaults, without values for keys.
- **Contract:** unchanged. The snapshot test must pass without regeneration.
- **Acceptance criteria:**
  1. Each invalid configuration fails at startup with a message that names the variable: no keys, an empty
     key, a non-integer or non-positive number, an unknown backend, and `redis` without a URL.
  2. No configured API key appears in `repr(settings)` or in any validation error message (tested with a
     sentinel key).
  3. `/health` still returns 200 `{"status": "ok"}`, and the OpenAPI snapshot is unchanged.
  4. `FakeClock` changes only through `advance`; no test calls `time.sleep` or `asyncio.sleep` (grep).
  5. `uvicorn --factory app.main:create_app` serves `/health` when the variables are set (OWNER-CHECK: run by
     hand, since tests do not start a server).
- **Verification:** `python scripts/check.py` green; mutation table (defaults swapped, a validation rule
  removed, key masking removed, clock advance ignored); `gh pr checks <n> --watch`.
- **Branch and commits:** `feat/t-101-clock-settings`; `feat(app): add an injected clock`, `feat(app): read
  settings from the environment at startup`, `docs(setup): document the configuration variables`,
  `docs(tasks): complete T-101`.
- **Size:** about 200 lines.

### T-102 - Chat completions endpoint with a mock provider

- **Status:** done
- **Goal:** `POST /v1/chat/completions` accepts an OpenAI-style request and returns an OpenAI-style response
  from a deterministic mock provider. Authentication (T-103) and limits (T-108) come later.
- **Context:** ADR-0004, ADR-0008, ARCHITECTURE §2 to §4, `app/main.py`, `tests/test_openapi_snapshot.py`.
- **Depends on:** T-101; ADR-0008 accepted.
- **Deliverables:**
  - `app/api/models.py`: request model with `model`, `messages` (at least one; `role` is `system`, `user` or
    `assistant`; `content` is a string; optional `name`), `max_completion_tokens`, `max_tokens`,
    `temperature` (0 to 2), `n` (only 1), `stream` and `user`; response model with `id`, `object`
    (`"chat.completion"`), `created`, `model`, `choices` (`index`, `message`, `finish_reason`) and `usage`
    (`prompt_tokens`, `completion_tokens`, `total_tokens`). Array content, `n` above 1 and `stream: true` are
    rejected with 400 (ADR-0008).
  - `app/api/errors.py`: the OpenAI error body and exception handlers. FastAPI's 422 is replaced by 400, both
    at runtime and in the OpenAPI document.
  - `app/providers/base.py`: the `Provider` protocol. `app/providers/mock.py`: `MockProvider`, whose reply and
    usage depend only on the request (for example, usage counts whitespace-separated words), with `created`
    from the `Clock` and `id` from an injected id source.
  - `app/api/chat.py`: the router, registered in `create_app()`.
- **Contract:** changes. The snapshot is regenerated with `scripts/regenerate_openapi.py` in its own commit,
  and the diff is reviewed in the PR.
- **Acceptance criteria:**
  1. A valid request returns 200 with every field the OpenAI SDK's `ChatCompletion` type requires, and the
     same body every time under a fixed clock and id source.
  2. A missing `model`, empty `messages`, an unknown role, `temperature` 3, `n` 2, array content and
     `stream: true` each return 400 with the ADR-0008 body and the right `param`; no response is ever 422.
  3. The OpenAPI document lists the route with its 200 and 400 responses, and the snapshot diff contains only
     the new route, its models and the error model.
  4. No test uses the network; only `MockProvider` is used.
- **Verification:** `python scripts/check.py` green; mutation table (a response field renamed,
  `finish_reason` changed, the `stream` check removed, the 400 handler removed, the `n` check removed,
  usage arithmetic changed); `gh pr checks <n> --watch`.
- **Branch and commits:** `feat/t-102-chat-completions`; `feat(api): add chat completion models and the
  error body`, `feat(providers): add the provider interface and a mock provider`, `feat(api): add the chat
  completions endpoint`, `test(contract): update the OpenAPI snapshot for chat completions`,
  `docs(tasks): complete T-102`.
- **Size:** about 350 lines plus the snapshot diff.

### T-103 - API key authentication

- **Status:** done
- **Goal:** only configured API keys can call `/v1/chat/completions`; `/health` stays open.
- **Context:** ADR-0008, `app/settings.py`, `app/api/chat.py`, `app/api/errors.py`.
- **Depends on:** T-101, T-102; ADR-0008 accepted.
- **Deliverables:** `app/api/auth.py`: a FastAPI dependency that reads `Authorization: Bearer <key>`, compares
  it with every configured key using `hmac.compare_digest`, and returns a caller identity whose id is a
  SHA-256 digest of the key (used later for bucket keys). The OpenAPI document gets a bearer security scheme on
  the route and its 401 response.
- **Contract:** changes (security scheme and 401 response); regenerated snapshot in its own commit.
- **Acceptance criteria:**
  1. A missing header, a scheme other than `Bearer`, an empty key and an unknown key each return 401 with
     `type: "invalid_request_error"`, `code: "invalid_api_key"`, `param: null`.
  2. A configured key gets 200. `/health` needs no key.
  3. No response body or log record contains the submitted key (tested with a sentinel key and `caplog`).
  4. The caller identity contains no key text, only the digest.
- **Verification:** `python scripts/check.py` green; mutation table (comparison inverted, scheme check
  removed, `/health` protected, digest replaced by the raw key, key echoed in the message);
  `gh pr checks <n> --watch`.
- **Branch and commits:** `feat/t-103-api-keys`; `feat(api): require an API key for chat completions`,
  `test(contract): update the OpenAPI snapshot for authentication`, `docs(tasks): complete T-103`.
- **Size:** about 150 lines.

### T-104 - Token estimator

- **Status:** done
- **Goal:** the number of tokens to reserve for a request is computed by the rule in ADR-0007.
- **Context:** ADR-0007, `app/api/models.py`.
- **Depends on:** T-102; ADR-0007 accepted.
- **Deliverables:** `app/limits/estimate.py`: a `TokenEstimator` protocol, `HeuristicEstimator` (per message
  `ceil(characters / 4) + 3`, plus 1 with a `name`, plus 3 for the reply; characters are Python string length),
  and `reserved_tokens(request, estimator)` (estimate plus `max_completion_tokens`, else `max_tokens`, else 0).
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. Boundary table: one message with empty content gives 6; 1 to 4 characters give 7; 5 characters give 8;
     a `name` adds exactly 1; each extra message adds its own share plus 3.
  2. The estimate never decreases when content grows by one character (checked over lengths 0 to 200).
  3. `max_completion_tokens` wins over `max_tokens` when both are given; neither gives the estimate alone.
  4. No dependency is added.
- **Verification:** `python scripts/check.py` green; mutation table (`ceil` to `floor`, divisor changed, reply
  overhead removed, `name` overhead removed, precedence of the two max fields swapped);
  `gh pr checks <n> --watch`.
- **Branch and commits:** `feat/t-104-token-estimator`; `feat(limits): add the token estimator`,
  `docs(tasks): complete T-104`.
- **Size:** about 120 lines.

### T-105 - In-memory token bucket and the shared behaviour suite

- **Status:** done
- **Goal:** a correct reference limiter, and one behaviour suite that every later limiter must also pass.
- **Context:** ADR-0007, ARCHITECTURE §3 (`RateLimiter`), `app/clock.py`, `tests/fakes.py`.
- **Depends on:** T-101; ADR-0007 accepted.
- **Deliverables:**
  - `app/limits/limiter.py`: the `RateLimiter` protocol (`reserve(key, estimated_tokens) -> Decision`,
    `settle(key, reserved_tokens, actual_tokens)`) and `Decision` (`allowed`, `limit_tokens`,
    `remaining_tokens`, `retry_after_seconds` or `None`, `reset_seconds`).
  - `app/limits/memory.py`: `InMemoryRateLimiter`, driven by the injected `Clock`, with one `asyncio.Lock` so
    concurrent calls cannot overspend.
  - `tests/limits/behaviour.py`: the shared suite, parametrised by a limiter factory and a `FakeClock`, so
    T-106 and T-107 run the same cases. ARCHITECTURE §3 is updated with the final names.
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. A reservation equal to the balance is allowed; one token more is refused with the exact wait, rounded up.
  2. The balance refills at `tokens_per_minute / 60` per second and never exceeds `capacity_tokens`.
  3. A reservation larger than `capacity_tokens` is refused with `retry_after_seconds` `None`.
  4. Settle charges or refunds the difference; a charge can make the balance negative, and a refund never
     lifts it above capacity.
  5. Keys are independent; 50 concurrent reservations (`asyncio.gather`) never spend more than the balance.
  6. Every case uses `FakeClock`; nothing sleeps.
- **Verification:** `python scripts/check.py` green; mutation table with at least eight mutations (`>=` to
  `>`, capacity cap removed, refill rate doubled, settle sign flipped, oversized check removed, wait rounded
  down, lock removed, key ignored); `gh pr checks <n> --watch`.
- **Branch and commits:** `feat/t-105-memory-limiter`; `feat(limits): add the rate limiter interface and the
  in-memory token bucket`, `test(limits): add the shared limiter behaviour suite`, `docs(architecture): fix
  the rate limiter interface`, `docs(tasks): complete T-105`.
- **Size:** about 300 lines.

### T-106 - Redis token bucket, unit-tested against fakeredis

- **Status:** done
- **Goal:** the token bucket runs as one Lua script on Redis and passes the shared suite on fakeredis.
- **Context:** ADR-0006, ADR-0007, `app/limits/limiter.py`, `tests/limits/behaviour.py`, ADR-0003,
  `docs/setup.md` ("Updating pins").
- **Depends on:** T-105; ADR-0006 accepted (it lists the dependencies this task adds).
- **Deliverables:**
  - Pins: `redis==8.1.0` in `requirements.txt` and `pyproject.toml`; `fakeredis[lua]==2.40.0` with `lupa`
    and every other new transitive pin in `requirements-dev.txt`, regenerated per `docs/setup.md`.
  - `app/limits/token_bucket.lua`: reads and refills the bucket, decides, writes, sets `PEXPIRE`, and returns
    the balance as a string. The current time arrives as an argument in milliseconds; the script never calls
    `TIME`.
  - `app/limits/redis_limiter.py`: `RedisRateLimiter` on `redis.asyncio`, using `register_script`; bucket keys
    are a prefix plus the SHA-256 digest of the API key; one adapter function turns script results into typed
    values.
  - `tests/limits/test_redis_limiter.py`: the shared suite on `fakeredis.FakeAsyncRedis`, plus checks of the
    key names and the TTL (`PTTL`).
- **Carried over from T-105 (the in-memory limiter is the reference; the Redis one must agree):**
  - **A clock that steps backwards.** `SystemClock` can step back (a time correction). The in-memory
    limiter clamps the elapsed time to 0 and never moves its timestamp backwards, so it never refills the
    same interval twice and never over-grants. The Lua script must do the same: `elapsed = max(0, now -
    updated)` and `updated = max(updated, now)`. The shared suite cannot test this, because `FakeClock`
    cannot go backwards, so this task adds its own test for it.
  - **Exact arithmetic.** The shared suite needs exact results over many calls, not only within one call:
    100 tokens per minute refills 5/3 per second, 11 per minute must give a wait of exactly 60 seconds,
    and 120 one-second steps at 1 per minute must leave exactly 2 tokens
    (`case_many_small_refills_add_up_exactly`). Multiplying first and dividing last fixes a single call,
    but a balance stored as a double and refilled on every call drifts. The proposed fix is to keep the
    balance in the script as an integer scaled by 60000 (tokens x 60000): the refill is then exactly
    `elapsed_ms * tokens_per_minute`, the capacity is `capacity_tokens * 60000`, and a reservation is
    compared with `amount * 60000`. If a different representation is chosen, any change to the suite must
    be explicit and reviewed and must not loosen an assertion. Four things must be settled when this task
    is planned, because the proposal does not cover them:
    - **Range.** Lua numbers are doubles, exact for integers up to 2^53 (9,007,199,254,740,992), so the
      scaled capacity is exact only while `capacity_tokens` is at most 150,119,987,579 (2^53 // 60000). The
      in-memory limiter (exact fractions) has no such bound, and `app/settings.py` accepts integers of up to
      18 digits, so decide whether `RedisRateLimiter.__init__` rejects a larger capacity with a
      `ValueError`, Settings refuses it, or the script uses another representation. A charge from a
      provider that reports usage near that size is scaled too.
    - **Number formatting and division.** Lua 5.1 prints large doubles in exponent form (`1e+15`), so format
      the returned balance with `string.format("%.0f", x)`; the adapter's `int()` would reject `1e+15`. Lua
      5.1 has no integer division, so compute the ceilings for the wait and the reset with `math.floor`
      and `math.fmod` (or a remainder check), not a bare float division.
    - **Seconds to milliseconds.** The script takes the time in whole milliseconds, while the in-memory
      reference works in exact seconds, so the adapter must state how it rounds `now_seconds()` (for
      example `floor(seconds * 1000)`). The shared suite moves the clock in 0.25 second steps and cannot
      see a sub-millisecond difference; this task adds its own test for the rounding.
    - **ADR-0006 says the script returns "the fractional balance as a string"**; the integer-scaled balance
      above is different. Reconcile it in the plan: either keep the fraction, or record the change in a new
      ADR (an accepted ADR changes only through a new one).
  - **Negative amounts.** The suite requires `ValueError` for a negative `reserve` or `settle` amount, with
    the word "negative" in the message, so the adapter must raise it before calling the script.
  - **One event loop per case.** Each suite case is one `asyncio.run` and the factory is called inside it;
    create the `FakeAsyncRedis` inside the factory, not at import time. Pass a `cleanup` coroutine
    function to `run_behaviour_case` to close the client after each case.
  - **A fresh keyspace per factory call.** Several cases build two limiters with different rates and use the
    same key on each, and `case_two_limiters_from_the_factory_do_not_share_state` checks it. The factory
    must give every limiter its own key prefix (a counter or a UUID), because two `FakeAsyncRedis()`
    instances can share one server.
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. Both requirements files install with `--only-binary=:all:` on Windows and in CI.
  2. The shared suite passes on fakeredis with the real Lua script.
  3. No key written to Redis contains the API key; the bucket key has a TTL.
  4. The script contains no `TIME` call (grep), and mypy strict passes with no `type: ignore` outside the
     adapter.
  5. Docs and the PR say "unit-tested against fakeredis" and make no claim about real Redis (ADR-0006).
- **Verification:** `python scripts/check.py` green; mutation table on the Lua script and the adapter
  (comparison loosened, capacity cap removed, refill computed from the wrong timestamp, `PEXPIRE` removed,
  balance returned as a number, settle sign flipped); `gh pr checks <n> --watch`.
- **Branch and commits:** `feat/t-106-redis-limiter`; `build(deps): add redis and fakeredis`,
  `feat(limits): add the Redis token bucket`, `test(limits): run the shared suite on fakeredis`,
  `docs(tasks): complete T-106`.
- **Size:** about 250 lines plus the pin updates.

### T-107 - Real Redis in CI

- **Status:** done
- **Goal:** the Redis limiter is proven against a real Redis server, in CI only, without adding network use to
  local runs.
- **Context:** ADR-0006, `.github/workflows/ci.yml`, `pyproject.toml`, `scripts/check.py`,
  `tests/limits/behaviour.py`.
- **Depends on:** T-106.
- **Carried over from T-105:** the real-server factory must give each limiter its own key prefix (not only
  each test), because the shared suite builds several limiters per case and uses the same key on each, and
  it should pass a `cleanup` to `run_behaviour_case` that closes the client (see the T-106 card).
- **Deliverables:**
  - `pyproject.toml`: the `redis_server` marker registered, and `-m "not redis_server"` in the default pytest
    options, so the tests are deselected (not skipped) in `check.py` and local runs.
  - `tests/limits/test_redis_server.py`: the shared suite on a real server at `TOLLGATE_TEST_REDIS_URL`, each
    test with its own key prefix. When the marker is selected and the variable is missing, the tests fail;
    they never skip.
  - `ci.yml`: a `redis:7.4.12` service container with a `redis-cli ping` health check, and a step named
    `redis integration` after the `check.py` mirror steps that runs `python -m pytest -m redis_server`. The job
    name `lint and test` does not change.
  - `docs/setup.md`: how to run those tests by hand against a local Redis, if the owner has one.
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. Locally and in `check.py`, the `redis_server` tests show as deselected and none as skipped.
  2. On the PR, the `redis integration` step is green, and its log shows the shared suite's test count passed.
  3. With the marker selected and no URL set, the run fails with a message naming `TOLLGATE_TEST_REDIS_URL`.
  4. After the merge, README and ARCHITECTURE may say the limiter is tested against Redis 7.4.12 in CI, and
     only that.
- **Verification:** `python scripts/check.py` green; the CI log of the `redis integration` step; the
  deselection count from a local run; `gh pr checks <n> --watch`.
- **Branch and commits:** `ci/t-107-redis-integration`; `test(limits): run the shared suite on a real Redis
  server`, `ci: add the redis integration step`, `docs(tasks): complete T-107`.
- **Size:** about 80 lines.

### T-108 - Rate limiting on chat completions

- **Status:** done (2026-11-13)
- **Clarified by the owner (2026-11-13):** a 200's limit headers come from the `Decision` that `reserve`
  returned, so they show the balance after the reservation (ADR-0008's "balance after the decision");
  criterion 2 is tested through a follow-up request. A 502's headers also come from the reserve `Decision`,
  so they show the balance before the refund; this is accepted. No interface change. The snapshot is
  regenerated in the `reserve and settle` commit, not a commit of its own, so every commit passes the check
  (as in T-102). At plan review the owner also decided: an authenticated 400 is rejected before any
  reservation and carries no limit headers; the double hashing of the key (T-103) stays open; a reset of an
  hour or more is written `60m0s`, ADR-0008's grammar taken literally, not `1h0m0s`.
- **Goal:** each chat completion reserves tokens before the provider call, settles after it, and answers with
  the ADR-0008 headers, 429 and 502 responses.
- **Context:** ADR-0007, ADR-0008, `app/api/chat.py`, `app/api/auth.py`, `app/limits/`, `app/settings.py`.
- **Depends on:** T-103, T-104, T-105, T-106.
- **Deliverables:**
  - `create_app()` builds the limiter from `Settings` (`memory` or `redis`), with the injected clock.
  - The route: authenticate, estimate, reserve; on refusal 429; otherwise call the provider, settle with its
    `usage.total_tokens`, and on provider failure refund the whole reservation and return 502.
  - `app/api/limit_headers.py`: builds the three `x-ratelimit-*-tokens` headers and `Retry-After` from a
    `Decision`, including the `<m>m<s>s` duration format.
  - The 429 and 502 responses and the headers in the OpenAPI document.
- **Needs clarifying before this task is planned (found in T-105):** the limit headers come from the
  `Decision` that `reserve` returns, so on a 200 they show the balance after the reservation, which was made
  from the estimate. `settle` returns nothing and runs after the provider answers, so a response cannot show
  the balance after settling; only the next request's headers can. Criterion 2 below ("after a 200, the
  remaining balance reflects the mock's reported usage") is therefore true of a later request or probe, not of
  the 200's own headers. Decide before planning whether criterion 2 is tested through a follow-up request,
  or `settle` should return a `Decision` (an interface change that needs an ADR and a change to T-105's
  suite and to T-106). The same applies to a 502: ADR-0008 says it still carries the limit headers, but they
  come from the `Decision` that `reserve` returned, so they show the balance before the refund; decide
  whether that is accepted. Also, buckets are never evicted, so `reserve` and `settle` must only receive the
  caller id of an authenticated key (T-103), never a value taken from the request.
- **Carried over from T-106:** `RedisRateLimiter` raises `ValueError` when `tokens_per_minute` or
  `capacity_tokens` is above 75,059,993,789 (2^52 // 60000), while `Settings` accepts up to 18 digits. When
  the backend is `redis`, building the limiter must turn that into a startup error that names the variable.
  The Redis limiter takes the API key as given and hashes it into its bucket key itself, so the caller id
  from T-103 (already a SHA-256 digest) is hashed again, which is harmless.
- **Contract:** changes (429, 502 and the headers); the snapshot is regenerated in the `reserve and settle`
  commit (owner clarification above).
- **Acceptance criteria:**
  1. Under the limit: 200 with exact header values. Over it: 429 with the ADR-0008 body and `Retry-After`
     rounded up. Larger than capacity: 429 without `Retry-After`.
  2. After a 200, the remaining balance reflects the mock's reported usage, not the estimate.
  3. A failing provider gives 502 with the ADR-0008 body, and the full reservation is refunded.
  4. Reset durations format as `0s`, `45s`, `1m0s` and `6m0s` at those boundaries; remaining is never shown
     below 0.
  5. 401 responses and `/health` carry no limit headers.
  6. With `TOLLGATE_LIMITER_BACKEND=redis`, the app uses `RedisRateLimiter` (tested with fakeredis).
- **Verification:** `python scripts/check.py` green; mutation table (settle skipped, refund skipped,
  `Retry-After` rounded down, header on the wrong decision value, duration format off by one at 60 seconds,
  oversized `Retry-After` sent, backend selection ignored); `gh pr checks <n> --watch`.
- **Branch and commits:** `feat/t-108-rate-limited-chat`; `feat(api): add the rate-limit headers`,
  `feat(api): reserve and settle tokens on chat completions` (with the regenerated snapshot),
  `docs(tasks): complete T-108`.
- **Size:** estimated at about 300 lines; the plan came to about 630 hand-written lines, approved by the owner.

---

### T-201 - Provider errors and the route table

- **Status:** todo
- **Goal:** the failure taxonomy and the route table exist, and a bad route table stops the app at startup,
  before anything routes with it.
- **Context:** ADR-0010, ADR-0011, `app/providers/`, `app/settings.py`, `app/main.py`, `tests/test_settings.py`,
  `tests/test_app_wiring.py`, `tests/fakes.py`.
- **Depends on:** the Phase 1 gate (signed off); ADR-0010 and ADR-0011 accepted.
- **Deliverables:**
  - `app/providers/errors.py`: `ProviderError` with a `kind` (`connection`, `timeout`, `rate_limited`,
    `upstream_status`, `bad_response`) and an optional `status_code`, and a `retryable` property that is true
    exactly for `connection`, `timeout`, `rate_limited`, and `upstream_status` with a status of 500 or above.
    The message is built from the kind and the status only.
  - `app/routing/config.py`: pydantic models for the route table file with every rule in ADR-0011 (provider
    types and which settings each type allows or requires, 1 to 5 targets, `timeout_seconds` from 5 to 600 with
    default 60, an optional `default` target list, unknown fields rejected), and a loader that rejects duplicate
    keys at any level (`object_pairs_hook`) and reads each `api_key_env` variable, keeping the keys as
    `SecretStr`.
  - `Settings.from_env(environ)` reads `TOLLGATE_ROUTES_FILE` and loads the table, taking the keys from the same
    `environ`, so tests never touch `os.environ`. Every error is a `SettingsError` naming `TOLLGATE_ROUTES_FILE`
    and the field path (for example `routes.fast[0].provider`), or naming the `api_key_env` variable, and never
    shows a value from the file or the environment. Without the variable `Settings` holds the built-in table:
    one provider named `mock` of type `mock` and a default route to it with no upstream model. Nothing in the
    request path uses the table yet.
  - `docs/setup.md`: the variable and the file format.
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. A valid file loads into the expected table: aliases, target order, upstream models, defaults and keys
     exact.
  2. Each invalid file fails with a `SettingsError` naming the variable and the field path, and no value from
     the file in the message: malformed JSON, an unreadable path, a duplicate provider name, alias or field, an
     unknown field, an unknown provider type, a target naming an undefined provider, an empty route, six
     targets, a timeout of 4 or 601, `base_url` or `timeout_seconds` on `mock`, `default_max_tokens` missing for
     `anthropic` or present for another type, `api_key_env` missing for `openai` or `anthropic` or present for
     `mock` or `ollama`.
  3. A provider whose `api_key_env` variable is unset, empty or only whitespace fails naming that variable; a
     key never appears in a `repr` or an error.
  4. Without `TOLLGATE_ROUTES_FILE`, the built-in table is used and every existing test passes unchanged.
  5. `retryable` is exact at its boundaries: `upstream_status` 499 is not retryable, 500 and 529 are;
     `rate_limited`, `connection` and `timeout` are; `bad_response` is not.
- **Verification:** `python scripts/check.py` green; mutation table (the 500 boundary moved to 501 or 499,
  `rate_limited` not retryable, `bad_response` retryable, the target limit 5 changed to 6 or 4, the timeout
  bounds 5 and 600 moved by one, unknown fields allowed, duplicate keys kept, an unset or empty key variable
  accepted, `api_key_env` accepted for `ollama`, `default_max_tokens` accepted for `openai`, a file value or a
  key in an error message, the field path missing from the message, the built-in table changed); `gh pr checks
  <n> --watch`.
- **Branch and commits:** `feat/t-201-route-table`; `feat(providers): add the provider error taxonomy`,
  `feat(routing): load and validate the route table`, `docs(tasks): complete T-201`.
- **Size:** about 380 lines.

### T-202 - Routing and fallback on chat completions

- **Status:** todo
- **Goal:** each chat completion is routed by its `model` and falls back along its route on retryable
  failures, with one reservation and one settle.
- **Context:** ADR-0007, ADR-0008, ADR-0010, ADR-0011, `app/api/chat.py`, `app/main.py`, `app/routing/`,
  `tests/test_chat_rate_limits.py`, `tests/test_chat_openapi.py`, `tests/test_chat_completions.py`,
  ARCHITECTURE sections 2, 3 and 5.
- **Depends on:** T-201.
- **Deliverables:**
  - `app/routing/router.py`: `Router.select(request) -> Route` (an ordered tuple of targets), or an
    `UnknownModelError` when no alias matches and there is no default route.
  - A provider registry built by `create_app()`: provider name to `Provider`, kept on `app.state`. This task
    builds the `mock` type only; a table naming a type not built yet fails startup with a `SettingsError`
    naming the variable, and each adapter task removes its type from that list. The existing `provider=`
    keyword replaces the registry entry named `mock`; a new `providers=` keyword (name to `Provider`) lets
    tests supply several. The route reads the registry, the router and the limiter from `app.state` on every
    request, so tests that swap them after `create_app()` keep working; the follow-up in
    `tests/test_chat_rate_limits.py` that swaps `app.state.provider` is changed to swap the registry entry, with
    its assertion unchanged.
  - The route: authenticate, validate, select (404 before any estimate or reservation), estimate, reserve, then
    try each target in order with the request's `model` replaced by the target's upstream model (the client's
    model when the target has none). A retryable `ProviderError` moves to the next target. Any other error, or
    the last target failing, ends the route. Success settles once with that attempt's usage. A route that ends
    without a 2xx refunds the whole reservation; a `bad_response` is charged as reserved. Both give the
    ADR-0008 502.
  - The 404 body from ADR-0011, with its fixed message and no limit headers.
  - A 200 carries `x-tollgate-provider` and `x-tollgate-fallbacks`, and its body `model` is the one the provider
    reported. The 404 and the two headers are in the OpenAPI document. In `tests/test_chat_openapi.py` the
    response set becomes exactly `{200, 400, 401, 404, 429, 502}` and the 200 header set exactly the three limit
    headers plus the two new ones, so the assertions stay exact. The snapshot is regenerated in the route
    commit, so every commit passes the check (as in T-102 and T-108).
  - The 502 description in the OpenAPI document and the docstring of `app/api/chat.py` say that a provider
    failure is refunded and an untranslatable answer is charged.
  - ARCHITECTURE: section 3 marks `Router`, `Route` and `ProviderError` final; section 2 and the section 5
    layout and chat-route paragraph describe routing, fallback and the `bad_response` charge.
- **Contract:** changes (the 404 and two headers on 200); snapshot regenerated in the route commit.
- **Acceptance criteria:**
  1. An unknown model with no default route gets the 404 body, no limiter call and no limit headers. With a
     default route, it is served by that route.
  2. For each retryable kind on the first target, the second target serves: 200, body `model` is the second
     target's reported model, `x-tollgate-provider` is its name, `x-tollgate-fallbacks` is `1`; exactly one
     reserve and one settle, with the second target's usage.
  3. A non-retryable `ProviderError`, or any other exception, on the first target: no other target is called,
     502, and the whole reservation is refunded.
  4. A `bad_response` on the first target: no other target is called, 502, and settle leaves the reservation
     charged (a follow-up request shows the balance).
  5. Every target failing with a retryable error: each is called exactly once, in order, then 502 and a full
     refund.
  6. Without a route table file, every behavioural test in `tests/test_chat_rate_limits.py` and
     `tests/test_chat_completions.py` passes, unchanged except for the one registry swap above, and each 200
     carries `x-tollgate-provider: mock` and `x-tollgate-fallbacks: 0`.
  7. A route table naming a provider type that is not built yet fails startup naming the variable.
- **Verification:** `python scripts/check.py` green; mutation table (fallback on a non-retryable error, no
  fallback on a retryable one, targets in another order, a target tried twice, settle with the failed attempt's
  usage, a second settle, the refund skipped when every target fails, `bad_response` refunded, the 404 after the
  reservation, limit headers on the 404, the default route ignored, the fallback count off by one,
  `x-tollgate-provider` naming the first target instead of the one that served, the client's alias sent
  upstream instead of the target's model); `gh pr checks <n> --watch`.
- **Branch and commits:** `feat/t-202-routing-fallback`; `feat(routing): select a route and fall back on
  retryable failures`, `feat(api): route chat completions` (with the regenerated snapshot),
  `docs(tasks): complete T-202`.
- **Size:** about 400 lines plus the snapshot diff; the card most likely to run over, so its plan is shown to
  the owner if it does.

### T-203 - Close the clients the app builds on shutdown

- **Status:** todo
- **Goal:** the app closes every client it builds when it shuts down, starting with the Redis client built from
  the URL (the first known gap in the T-108 Log), so the adapter tasks only register their HTTP clients.
- **Context:** `app/main.py`, `tests/test_app_wiring.py`, `tests/test_chat_rate_limits.py`.
- **Depends on:** T-202.
- **Deliverables:**
  - A list of owned clients on `app.state`, which `create_app()` appends to whenever it builds a client
    (T-204 appends its HTTP clients the same way), and an app lifespan that, on shutdown, closes every client in
    that list in the reverse order of building and continues past a client whose close raises. The Redis client
    built with `from_url` is appended; an injected client is not.
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. With the redis backend and no injected client, the client built from the URL is closed when the app shuts
     down (the lifespan run through `TestClient` as a context manager), and no connection is opened.
  2. An injected Redis client is still open after shutdown.
  3. With two clients in the owned list, both are closed in reverse order, and a close that raises does not stop the
     other.
  4. The memory backend builds nothing and closes nothing.
- **Verification:** `python scripts/check.py` green; mutation table (the lifespan never closes, the injected
  client closed, the order not reversed, the first failing close stopping the rest, the memory backend
  registering a client); `gh pr checks <n> --watch`.
- **Branch and commits:** `feat/t-203-client-shutdown`; `feat(app): close the clients the app builds on
  shutdown`, `docs(tasks): complete T-203`.
- **Size:** about 150 lines.

### T-204 - Ollama adapter

- **Status:** todo
- **Goal:** a route can be served by a local Ollama through its native API, tested only with
  `httpx.MockTransport`.
- **Context:** ADR-0010, ADR-0011, `app/providers/`, `app/main.py`, `requirements.txt`,
  `requirements-dev.txt`, `pyproject.toml`.
- **Depends on:** T-203.
- **Deliverables:**
  - `httpx==0.28.1`, `httpcore==1.0.9` and `certifi==2026.10.23` move from `requirements-dev.txt` to
    `requirements.txt`, and `httpx>=0.28.1` moves to the runtime dependencies in `pyproject.toml`. Both files
    install with `--only-binary=:all:` on Windows and in CI, `pip check` is clean, and no package is added.
  - `IdSource` and `UuidIdSource` move from `app/providers/mock.py` to `app/providers/ids.py`, so adapters do
    not import from the mock.
  - `create_app()` builds one `httpx.AsyncClient` per HTTP provider in the route table (base URL, default
    `http://localhost:11434` for Ollama, and the ADR-0010 timeouts), appends each to the owned list (T-203), and
    gains an `http_transport=` keyword used by every client it builds, so tests pass an `httpx.MockTransport`.
  - `app/providers/ollama.py`: `OllamaProvider(client, clock, id_source)` posting to `/api/chat` by the
    ADR-0010 rules. The registry builds the `ollama` type.
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. Request translation is exact: `POST /api/chat`, body `model`, `messages` of `role` and `content`,
     `"stream": false`, and `options.num_predict` (from `max_completion_tokens`, else `max_tokens`) and
     `options.temperature` only when given; no `name` and no `user`.
  2. Response translation: the reply text; `done_reason` "stop" and "length" mapped as they are; usage from
     `prompt_eval_count` and `eval_count`, an absent count being 0, and the total their sum; `id` from the id
     source, `created` from the clock, `model` from the response.
  3. Errors: a connection error and a timeout give retryable kinds; 404 `{"error": "model 'x' not found"}` gives
     a non-retryable `upstream_status`; 500 a retryable one; a 2xx that cannot be decoded, invalid JSON, no
     `message`, a missing or unknown `done_reason`, or a negative count gives `bad_response`. No message
     contains the response body.
  4. The clients the app built for HTTP providers are closed on shutdown.
  5. Through the whole app with a route table and a `MockTransport`, Ollama serves a 200, and a follow-up request
     shows the balance settled with Ollama's usage; a route of Ollama then `mock` falls back on an Ollama 503.
  6. The requirements move adds no package; the install passes on Windows and in CI.
- **Verification:** `python scripts/check.py` green; mutation table (`"stream": false` dropped, `num_predict`
  from the wrong field or `max_completion_tokens` ignored, an absent count raising or counting 1, the total from
  one count, an unknown `done_reason` accepted, `id` or `created` taken from the response or the system clock,
  404 retryable, 500 not retryable, a timeout not retryable, a timeout checked after `TransportError`, the body
  in an error message, an HTTP client not registered for shutdown, `name` forwarded); `gh pr checks <n>
  --watch`.
- **Branch and commits:** `feat/t-204-ollama-adapter`; `build(deps): move httpx to the runtime requirements`,
  `refactor(providers): move the id source out of the mock`, `feat(providers): add the Ollama adapter`,
  `docs(tasks): complete T-204`.
- **Size:** about 350 lines.

### T-205 - OpenAI adapter

- **Status:** todo
- **Goal:** a route can be served by OpenAI chat completions, tested only with `httpx.MockTransport`.
- **Context:** ADR-0010, `app/providers/`, `app/main.py`, the T-204 adapter as the pattern.
- **Depends on:** T-204.
- **Deliverables:**
  - `app/providers/openai.py`: `OpenAIProvider(client, api_key)` posting to `/v1/chat/completions` (default
    base URL `https://api.openai.com`) with `Authorization: Bearer <key>`, by the ADR-0010 rules. The registry
    builds the `openai` type.
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. Request translation is exact: `max_completion_tokens` from the client's `max_completion_tokens`, else
     `max_tokens`; `max_tokens` never sent; `temperature` and `name` forwarded when given; no `user`; the key
     only in the `Authorization` header.
  2. Response translation: `id`, `created` and `model` kept; content and finish reason mapped; `content: null`
     with a `refusal` gives an empty reply with `content_filter`; the total is prompt plus completion.
  3. Errors: 429 and 500, 502, 503 give retryable kinds; 400, 401, 403 and 404 non-retryable; a connection error
     and a timeout retryable; null content without a refusal, a missing `usage`, a negative count, or a
     `tool_calls` or `function_call` finish gives `bad_response`.
  4. The key never appears in an error message or a `repr`, even when the upstream body echoes it.
  5. Through the whole app, a route of OpenAI then `mock` falls back on an OpenAI 429 and settles with the mock's
     usage.
- **Verification:** `python scripts/check.py` green; mutation table (`max_tokens` sent, `max_completion_tokens`
  taken only from `max_completion_tokens`, the key in an error, a refusal mapped to `stop`, a missing `usage`
  settled as 0, 429 not retryable, 401 retryable, the `Authorization` scheme wrong or missing, `user`
  forwarded); `gh pr checks <n> --watch`.
- **Branch and commits:** `feat/t-205-openai-adapter`; `feat(providers): add the OpenAI adapter`,
  `docs(tasks): complete T-205`.
- **Size:** about 300 lines.

### T-206 - Anthropic adapter

- **Status:** todo
- **Goal:** a route can be served by the Anthropic Messages API, tested only with `httpx.MockTransport`.
- **Context:** ADR-0010, `app/providers/`, `app/main.py`, the T-204 adapter as the pattern.
- **Depends on:** T-204.
- **Deliverables:**
  - `app/providers/anthropic.py`: `AnthropicProvider(client, api_key, default_max_tokens, clock, id_source)`
    posting to `/v1/messages` (default base URL `https://api.anthropic.com`) with `x-api-key`,
    `anthropic-version: 2026-10-21` and `content-type: application/json`, by the ADR-0010 rules. The registry
    builds the `anthropic` type.
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. Request translation is exact: system messages joined with `\n`, in order, into `system`, and absent when
     there are none; the other messages in order with `role` and `content`; no `name`, `temperature` or `user`;
     `max_tokens` from the client's `max_completion_tokens`, else `max_tokens`, else `default_max_tokens`.
  2. Response translation: the `text` blocks joined in order with no separator (thinking blocks ignored), and
     an empty reply when there is none; `stop_reason` end_turn and stop_sequence to `stop`, max_tokens and
     model_context_window_exceeded to `length`, refusal to `content_filter`; prompt tokens include both cache
     fields, an absent or null one counting 0; `id` from the id source, `created` from the clock.
  3. Errors: 429, 500 and 529 give retryable kinds; 400, 401, 402, 403 and 404 non-retryable; a connection
     error and a timeout retryable; tool_use, pause_turn or another `stop_reason`, or a negative count gives
     `bad_response`.
  4. The key never appears in an error message or a `repr`.
  5. Through the whole app, a route of Anthropic then `mock` falls back on a 529.
- **Verification:** `python scripts/check.py` green; mutation table (system messages left in `messages`, only
  the first system message kept, `temperature` forwarded, `default_max_tokens` used when the client gave a max,
  cache tokens not counted, a null cache field raising, thinking text included, a separator added between text
  blocks, a refusal with no text block turned into `bad_response`, 529 not retryable, refusal mapped to `stop`,
  `model_context_window_exceeded` mapped to `stop`, the version header missing); `gh pr checks <n> --watch`.
- **Branch and commits:** `feat/t-206-anthropic-adapter`; `feat(providers): add the Anthropic adapter`,
  `docs(tasks): complete T-206`.
- **Size:** about 350 lines.

### T-207 - Real-provider guide and the owner's Ollama run

- **Status:** todo
- **Goal:** the owner can run the gateway against real providers by hand, and one run against a local Ollama is
  recorded.
- **Context:** ADR-0004, ADR-0010, ADR-0011, `docs/setup.md`, `app/routing/config.py`.
- **Depends on:** T-204, T-205, T-206.
- **Deliverables:**
  - `docs/routes.example.json`: one provider of each type and a route with fallback; keys only as
    `api_key_env` names.
  - A test that loads the example with placeholder environment values, so the file cannot drift from the
    schema.
  - `docs/setup.md`: running against real providers (the route table, the key variables, a request with
    `curl`, what fallback does, the timeouts, and that keys never go in files).
  - An OWNER-CHECK: the owner runs the gateway with an Ollama route against a local Ollama, and the Log records
    the date, the Ollama version, the model, the status, the usage and the limit headers seen. Runs against
    OpenAI or Anthropic are optional, with the owner's own keys, recorded the same way or marked "not run".
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. The example file loads in a test with placeholder environment values.
  2. `docs/setup.md` gives the steps, with no key or real secret in any committed file (checked with a search).
  3. OWNER-CHECK: the Ollama run is recorded in the Log, or the owner waives it in writing.
- **Verification:** `python scripts/check.py` green; mutation table for the example-file test (an unknown field
  added to the example, a target naming an undefined provider); `gh pr checks <n> --watch`.
- **Branch and commits:** `docs/t-207-provider-guide`; `docs(setup): add the real-provider guide and example
  routes`, `test(routing): load the example route table`, `docs(tasks): complete T-207`.
- **Size:** about 150 lines.

## Later phases (broken into tasks at each gate)

| Phase | Epic |
| --- | --- |
| 1 | Token-aware rate limiting: planned 2026-11-12 as T-101 to T-108 (see the current phase) |
| 2 | Model routing: planned 2026-11-13 as T-201 to T-207 (see the current phase) |
| 3 | Semantic caching: embeddings, similarity lookup, thresholds, invalidation |
| 4 | Docker Compose, observability, reproducible load benchmarks |
| 5 | Demo and write-up |

### Requirements that carry into the task cards

These are written into the cards when each phase is planned. The two Phase 1 items are in ADR-0006, T-106 and
T-107.

- **Phase 1, Redis ADR first.** Before the Phase 1 ADR on how the rate limiter talks to Redis, the researcher
  checks, with sources, that every package the Redis and Lua tests would need has a prebuilt wheel for Windows
  (`win-amd64`) and Python 3.13, so it installs under ADR-0003's binary-only rule. No Redis package is added
  before that ADR.
- **Phase 1, acceptance.** The rate limiter has a test against a real Redis server in CI (for example a service
  container). Until that test exists and is green, docs and PRs say only "unit-tested against fakeredis" and
  make no claim about behaviour on real Redis.
- **Phase 3, acceptance.** Semantic caching ships with a minimal eval harness: a small fixed set of prompt pairs
  labelled same-meaning or different-meaning, a run that reports hit rate and wrong-hit rate at the chosen
  similarity threshold, and the settings of the run. A threshold is never chosen without it.
- **Phase 4, deployment ADR.** The deployment target (where and how the gateway runs beyond Docker Compose on a
  development machine) is decided in a Phase 4 ADR, not before.

## Backlog

Not scheduled. Each item becomes a task card when a phase is planned.

- **OpenAI SDK compatibility test:** run the official OpenAI Python SDK against the gateway with the mock
  provider and check that chat completions work unchanged (ADR-0004). Streaming stays out of scope unless a
  card adds it.
- **Dependabot for GitHub Actions SHA pins:** the workflow pins its actions by commit SHA, which is updated by
  hand today. A Dependabot configuration for the `github-actions` ecosystem would propose those updates as pull
  requests. It adds a configuration file to the repository, so it is a task of its own, with a check that the
  proposed updates keep the version comment next to each SHA.
- **Same-target retries, cooldowns and a request deadline:** retrying a target with backoff and honouring
  `Retry-After`, a cooldown that skips a target after repeated failures, measured on the injected clock, and a
  total deadline per request across all targets (deferred by ADR-0010 and ADR-0011).
- **Malformed Redis URL:** turn redis-py's `ValueError` for a `TOLLGATE_REDIS_URL` with an unknown scheme into
  a `SettingsError` naming the variable (T-108 known gap 2).
- **Redis outage and settle failures:** decide fail-open or fail-closed when Redis is down (today a 500); keep a
  completion when settle fails after the provider answered; refund when a client disconnects mid-request (T-108
  known gaps 3 to 5).
- **One key hash per request:** merge the authentication done by `AuthenticatedRoute` and `require_api_key`, so
  each request hashes the key once (open since T-103).
- **httpx2:** decide whether to move from `httpx` to Pydantic's `httpx2` fork, which removes Starlette's
  TestClient warning and adds three packages (ADR-0010).
- **Unmodelled request fields:** decide whether `stop`, `top_p`, `tools` and similar fields are rejected or
  forwarded instead of ignored (ADR-0009, ADR-0010).
- **IETF RateLimit header fields:** emit `RateLimit` and `RateLimit-Policy` alongside the `x-ratelimit-*`
  headers once draft-ietf-httpapi-ratelimit-headers becomes an RFC and has a unit for tokens (ADR-0008).

## Log

| Date | Task | Event | Evidence |
| --- | --- | --- | --- |
| 2026-11-09 | T-000 | Project skeleton delivered by a direct commit, before the pull-request flow existed | Commit `7370304`; `pytest` 1 passed; `/health` 200 under uvicorn |
| 2026-11-09 | - | Process change: single-author guards (ADR-0001) and pull-request delivery (ADR-0002) adopted; hooks, ignore rules, architecture, decisions and board added in one docs-only pull request. Toolchain, CI and contract decisions proposed as ADR-0003 to ADR-0005 for the owner | `docs/DECISIONS.md`; guards checked by hand: a trailer and three blocked paths rejected, normal paths accepted (automated tests are T-002) |
| 2026-11-09 | - | Bootstrap exception: pull request #1 (merge commit `711b73f`) merged with no CI and no independent review, because neither existed yet; the owner approved the scope in advance | PR #1; `gh pr checks 1` reported no checks |
| 2026-11-09 | - | Decisions by the owner: ADR-0003 accepted; Phase 0 order is T-001, T-003, required check, T-002, T-004; the CI job is named exactly `lint and test`; `protect-main` stays strict with no bypass actors | `docs/DECISIONS.md`; `gh api repos/apoorvrajdev/tollgate/rulesets/26862192` showed `bypass_actors: []` and `current_user_can_bypass: never` |
| 2026-11-09 | - | Known gap: T-001 merges with no CI at all, and T-003 merges before `lint and test` is a required check (its own run happens on the pull request, but the ruleset cannot require a check that has not run yet). Each pull request body says so; the local check is the gate until the owner sets the required check after T-003 | T-001 and T-003 pull requests, once opened |
| 2026-11-09 | - | Bootstrap exception: pull request #2 (accept ADR-0003, reorder Phase 0) merged with no CI yet, after the owner's check; T-004 dependency set to T-001 and T-003 before the merge | PR #2; `gh pr checks 2` reported no checks |
| 2026-11-09 | T-001 | Toolchain added; verifier PASS (fresh `py -3.13` venv installed both files with no source builds; baseline plus lint, format, type and test faults each exited non-zero naming the step; a combined fault stopped at the first step; three mutations of the script and config all caught), reviewer APPROVE with four Minor findings (all recorded or accepted, none changing behaviour); no CI exists yet, so the local check was the gate | `python scripts/check.py` passed just now (ruff, format, mypy strict on 5 files, 1 test); `pip check` clean; runtime file holds none of pytest, ruff, mypy, httpx, redis, fakeredis |
| 2026-11-09 | T-001 | Quirks worth knowing: a literal `assert 1 == 2` fails at the mypy step (strict `comparison-overlap`), not at pytest, so a planted test fault needs a non-literal assertion; `pip freeze` on Windows writes CRLF, so generated pin files are converted to LF before commit | Verifier fault table |
| 2026-11-09 | - | Ruleset read-back for the README: `protect-main` is active on the default branch with the rules `deletion`, `non_fast_forward` and `pull_request` (0 required approvals, only the `merge` method allowed); no bypass actors. The repository also allows only merge commits and deletes merged branches | `gh api repos/apoorvrajdev/tollgate/rulesets/26862192` and `gh api repos/apoorvrajdev/tollgate`, read-only |
| 2026-11-09 | - | Process change: the README was rewritten for a first-time reader, stating only what is merged and marking the rest as planned. The owner decided it is updated at the end of each phase. Merged without CI, like the earlier pull requests | README pull request (task: none) |
| 2026-11-09 | T-003 | CI workflow added; verifier PASS on criteria 1 and 3 (steps, names and order equal `STEPS` in `scripts/check.py`; 11 mutations of the workflow caught by a line-based checker), reviewer APPROVE with three Minor findings; the pull request's own `lint and test` run is green and every pin installed from Linux wheels (criterion 2). Feedback iteration 1: the first push failed with "Invalid workflow file" on line 36 (unquoted `:all:` followed by a space in a `run:` value), fixed by quoting it. Criterion 4 is the owner's step after the merge: make `lint and test` a required status check in `protect-main`, with no bypass actors, then read it back; T-002 does not start before that | Runs `42670209879` (failed, invalid file) and `42670858105` (passed, 23 s); `gh pr checks 5` |
| 2026-11-09 | T-003 | Worth knowing: validating YAML by comparing lines is not validating it; the first GitHub run is the real parse test, and a check that does not parse the file must say so. `ubuntu-latest` is a floating image, so a runner change could turn the required check red without any change here; the fallback is to pin `ubuntu-24.04`. The concurrency group has no workflow prefix, which is fine for one workflow; add `${{ github.workflow }}` if a second one appears. A `merge_group` trigger would be needed only if a merge queue is adopted | Run log of `42670858105`; reviewer findings |
| 2026-11-10 | T-003 | Criterion 4 complete: the owner made `lint and test` a required status check in `protect-main`. Read back by id: the required check is `lint and test` from GitHub Actions (integration id 15368, which the apps API names `github-actions`); `bypass_actors` is empty and `current_user_can_bypass` is `never`; the `pull_request` rule is present with 0 required approvals and merge commits as the only allowed method; `non_fast_forward` blocks force pushes and `deletion` blocks deletion. `strict_required_status_checks_policy` is false, so a pull request need not be up to date with `main` to merge. The dependency of T-002 on the required check is met | `gh api repos/apoorvrajdev/tollgate/rulesets/26862192` (ruleset updated 2026-11-10 00:21 +05:30) and `gh api apps/github-actions`; the `lint and test` check run on `main` commit `1be7c61` came from app 15368 and succeeded |
| 2026-11-09 | - | Exception: pull request #6 (a backlog-only docs change, the Dependabot item) was merged at 18:50:21Z by the owner, before `lint and test` became a required check (the ruleset was saved at 18:51:45Z). CI had passed on it first. Like #5, it was merged before the check was required, and unlike #1 to #4 it had CI | PR #6 merge time from `gh pr view 6`; CI run `42676255873` (success); ruleset `updated_at` 2026-11-10T00:21:45+05:30 |
| 2026-11-10 | T-002 | Guard tests added; `scripts/check.py` passed 10 runs in a row (50 tests). Mutation check: 30 mutations of scratch copies of the hooks (each pattern or rule removed, `/i` dropped, anchors loosened or removed, comment skip removed, exit codes inverted, backslash normalisation removed); the first round left 10 survivors (comment skip, five loosened anchors, four dropped `/i` on path rules), closed by samples in a second round, after which all 30 were caught. Run with `node` off PATH, 39 tests error with the Node.js message and none skip. Reviewer APPROVE with three Minor findings | Verifier tables, two rounds; the pull request's `lint and test` run (criterion 6) is recorded in the pull request |
| 2026-11-12 | T-004 | `create_app()` and a typed `/health` response added; the OpenAPI snapshot `tests/contract/openapi.json` is committed and compared by `tests/test_openapi_snapshot.py`; only `scripts/regenerate_openapi.py` writes it. `scripts/check.py` and the `lint and test` job each run a named `contract` step, and the main pytest step ignores that file so no test runs twice. `.gitattributes` gained `tests/contract/*.json text eol=lf` at the owner's request. `scripts/check.py` passed (5 steps, 63 tests). Mutation check on scratch copies: renamed field, removed route, status code 201, `Literal` value changed and title changed were all caught; one survivor, removing `response_model` while keeping the return annotation, is an equivalent mutant (the generated document is byte-identical). A first round left two test-quality survivors (the canonical-format check could be made vacuous, and CRLF was normalised away); both are now caught. Criterion 5 was shown locally: a planted snapshot difference in a scratch copy fails `check.py` at `contract`. The CI red run was waived by the owner, so the first CI run on the pull request is the proof that the step is green | Verifier tables; `check.py` output |
| 2026-11-12 | T-004 | Correction to the row above: the final count is 65 tests (14 in the `contract` step, 51 in the `pytest` step), and the mutation check ran in three rounds. Round one left two test-quality survivors (the canonical-format check could be made vacuous, and CRLF was normalised away). Round two, on the CRLF fix, left one more: `ensure_ascii=True` made no test fail because no input was non-ASCII. It is now caught by `test_is_canonical_keeps_non_ascii_characters_raw`. After the last round, six mutations of the canonical-format check (always true, `sort_keys` dropped, indent 4, no trailing newline, CRLF normalisation restored, `ensure_ascii=True`) are all caught, and so is a CRLF copy of the snapshot. The only survivor is the equivalent `response_model` mutant. `scripts/check.py` passed (5 steps) and the `lint and test` job was green on the last push | Verifier tables; `check.py` output; PR #9 checks |
| 2026-11-12 | - | Phase 0 gate signed off by the owner: all seven gate items met. ADR-0004 and ADR-0005 accepted as written, no revisions. Gate check read back the same day: `protect-main` active with required check `lint and test` and no bypass actors; `ci` green on `main` at `f5c34f4`; 54 commits, all with the owner's author email, none with a trailer or attribution line | `gh api repos/apoorvrajdev/tollgate/rulesets/26862192`, `gh run list --branch main`, `git log` (read-only) |
| 2026-11-12 | - | Phase 1 planned: cards T-101 to T-108, the Phase 1 gate and board rows; ADR-0006 (Redis client, Lua bucket, tests), ADR-0007 (estimate, token bucket, reserve and settle) and ADR-0008 (authentication, limit headers, errors) proposed. Package versions, licences and `cp313` wheel availability were checked against the PyPI JSON API on this date; nothing was installed | `docs/DECISIONS.md`; the planning pull request |
| 2026-11-12 | T-101 | Injected `Clock` and `SystemClock` (`app/clock.py`), frozen `Settings` read from the environment with masked keys and variable-naming errors (`app/settings.py`), `create_app(settings, clock)` with no module-level `app`; pydantic added as a direct runtime dependency (already pinned in `requirements.txt`). Criterion 5 (`uvicorn --factory`) is an OWNER-CHECK, pending | `scripts/check.py` green (123 tests, snapshot unchanged); 25 mutations, all killed after one test fix (24 first run, then the blank-keys reason check) |
| 2026-11-13 | T-102 | `POST /v1/chat/completions` added: request and response models and the ADR-0008 error body (`app/api/models.py`, `app/api/errors.py`), the `Provider` protocol and a deterministic `MockProvider` with an injected clock and id source (`app/providers/`), the router (`app/api/chat.py`) and `create_app(settings, clock, *, provider=None)`. FastAPI's 422 is replaced by 400 at runtime and removed from the OpenAPI document by a small `FastAPI` subclass. The snapshot gained 330 lines and lost none (the route, eight models and the error model); it is regenerated in the endpoint commit rather than in its own commit, because the contract test cannot pass between the two (owner-approved). Error `code` values and the `messages[0].role` form of `param` are proposed as ADR-0009 (Proposed then, accepted by the owner on 2026-11-13); request fields the gateway does not model are ignored; the mock ignores `max_tokens`, `max_completion_tokens`, `temperature` and `user`. `scripts/check.py` passed (5 steps, 14 contract and 295 other tests). Three feedback iterations: the first verifier round (22 mutations, all caught) still found a 500 for a lone surrogate in message content and a non-ADR 400 body for JSON nested beyond the parser limit, both now fixed and tested; round two left one survivor (the status check in the parse-failure handler); round three left five (`int_parsing`, `int_type`, `float_type`, `bool_type`, `dict_type` in the wrong-type set), exposed when a test that only compared the set with a copy of itself was removed. The last round caught 41 of 41 mutations. Reviewer APPROVE with seven Minor findings, five applied | Verifier tables; `check.py` output; `gh pr checks` is recorded in the pull request |
| 2026-11-13 | T-102 | Known limits: the response-field list used for criterion 1 is transcribed from the openai-python types read on 2026-11-13, not checked against an installed SDK (it is not a dependency); the openai-openapi spec also marks `choices[].logprobs`, `message.content` and `message.refusal` as required but nullable, and this gateway omits `logprobs` and `refusal`; a provider exception is a 500 until the 502 body (ADR-0008) has a task; lone surrogates in `name` and `user` are accepted because they are never echoed; duplicate JSON keys are accepted, last one wins; `app/providers` imports its models from `app/api`, as the card places them | Reviewer and verifier findings; research with cited URLs in ADR-0009 |
| 2026-11-13 | T-103 | Blocked after three feedback iterations. The branch holds a working implementation and the open items are tests only. Implemented: `app/api/auth.py` (SHA-256 digests of the configured keys, every digest compared with `hmac.compare_digest` and no early exit, caller id is the digest of the submitted key, one fixed 401 with `WWW-Authenticate: Bearer`), an `AuthenticatedRoute` that checks the key before the body is read, the `ApiKeyAuth` bearer scheme (name and `http`/`bearer` type read in OpenAI's published spec on 2026-11-13) and the 401 in OpenAPI (snapshot +30 lines, none removed). `scripts/check.py` passes (5 steps, 14 contract and 420 other tests) and criteria 1 to 4 pass. Iteration 1 found that a configured non-ASCII key could not authenticate over HTTP, because Starlette decodes headers as latin-1 (fixed by decoding the raw bytes as UTF-8). Iteration 2 found that the invalid-UTF-8 test was vacuous through `TestClient`, which re-encodes headers, and left six surviving mutations (fixed with tests that call the ASGI app directly). Iteration 3 caught the leading-BOM survivor, then left five more that a test can kill: a trailing no-break space, a UTF-16 header name, a scheme that only starts with `bearer`, a leading space-and-tab trimmed before the key, and whitespace trimmed from configured keys in the authenticator. Six tests that kill all five exist and pass but are not in the branch, because the loop limit was reached. Two other survivors are equivalent mutants: decoding header names as latin-1, and `casefold()` for `lower()` on the scheme. Also open: `docs/setup.md` names only the trailing tab that h11 strips, and h11 also strips a leading one | Verifier tables, iterations 1 to 3 |
| 2026-11-13 | T-103 | Fourth iteration, run at the owner's request after the limit. The six tests were added (trailing no-break space, UTF-16 header name, a scheme with an extra letter, a leading space-and-tab, a configured key matched exactly) and the `docs/setup.md` wording was fixed. `scripts/check.py` passed (14 contract and 434 other tests) and criteria 1 to 4 pass. All 80 mutations from the third round are resolved: 78 caught and 2 proven equivalent (header names decoded as latin-1, and `casefold` for `lower` on the scheme, checked over every code point). A further 20 adversarial mutations left five survivors that a test can kill: whitespace or a no-break space before the scheme or the key, an empty scheme, spaces removed from inside a key, and an authenticator with no keys. Tests for them are written but not added, and the owner decides. The task stays `blocked` until then | Verifier tables, iteration 4 |
| 2026-11-13 | T-103 | Complete. At the owner's request the five remaining tests were added (whitespace or a no-break space before the scheme, an empty scheme, a key with an internal space, an authenticator with no keys) and the fake secret in `tests/test_settings.py` was renamed so it no longer looks like an API key (the old value began with the prefix that one provider's keys use); a literal scan of the repository for that prefix is now empty. `scripts/check.py` passed (14 contract and 444 other tests). In the last verification all five new survivors, the five from the previous round and 17 earlier mutations were caught, and four mutations of `app/settings.py` (keys or the Redis URL stored unmasked, a value in an error message, key text in `repr`) were still caught after the rename. A review of the test for the empty scheme found that its HTTP-level case did not contain an empty scheme; it was corrected. The owner decided that adversarial mutation stops here. Two mutations (header names decoded as latin-1, `casefold` for `lower` on the scheme) are equivalent. Known and accepted: `/openapi.json` and `/docs` need no key; each request hashes the key twice, to be merged when T-108 needs the identity | Verifier tables, iteration 4 and the final run |
| 2026-11-13 | T-104 | `app/limits/estimate.py` added: the `TokenEstimator` protocol (`estimate_input_tokens(request)`), `HeuristicEstimator` (`ceil(characters / 4) + 3` per message, +1 for a `name`, +3 for the reply, integer arithmetic only) and `reserved_tokens(request, estimator)` (the estimate plus `max_completion_tokens`, else `max_tokens`, else 0). Characters are Python string length, so a non-BMP character counts once and a combining mark counts as its own character. A `name` counts whenever it is present, including an empty string. No cap is put on `max_tokens`, so an oversized reservation is left to the limiter (ADR-0007). `scripts/check.py` passed (14 contract and 479 other tests); no dependency was added and the contract is unchanged. Mutation check on scratch copies: 39 mutations (the card's five and 34 more), the first round caught 36 and left a whitespace gap (characters counted after `strip()`), closed by a test with whitespace content; the second round caught 37 of 39. The two survivors are equivalent for any request the API accepts, because both max fields are validated to be at least 1: `or` instead of `is not None` on the max fields differs only when `max_completion_tokens` is 0, and a truthiness test on `max_tokens` differs only when it is negative. One feedback iteration. Reviewer APPROVE with three Minor findings (a layout line re-wrapped, a comment on the protocol test, a name-shadowing note for T-105). The `ARCHITECTURE.md` interface section was not changed; T-105 adds the new entries there | Verifier tables, two rounds; `check.py` output |
| 2026-11-13 | T-105 | `app/limits/limiter.py` (the `RateLimiter` protocol and a frozen `Decision` of plain integers) and `app/limits/memory.py` (`InMemoryRateLimiter`) added. Balances and times are exact fractions, so a reservation equal to the balance is allowed and a wait is rounded up from an exact value even at 5/3 tokens per second. The clock is read once per call, inside one `asyncio.Lock`; a clock that steps back gives no refill and never moves the timestamp back. The shared suite `tests/limits/behaviour.py` has 45 cases with hand-computed values, run through a limiter factory and a `FakeClock`, so T-106 and T-107 run the same cases; it documents that each factory call must return a limiter with its own keyspace and allows a `cleanup` coroutine. `scripts/check.py` passed (14 contract and 534 other tests); no dependency was added and the contract is unchanged. Mutation check on scratch copies: 64 mutations, the first round left a float-arithmetic mutant alive (all cases passed with floats) and an empty key sharing a bucket with `default`, both closed by new cases (a wait of exactly 60 seconds at 11 tokens per minute, 120 one-second steps at 1 per minute leaving exactly 2 tokens, and a lookalike key); the second round caught 60 of 64. The four survivors are equivalent (a refund above capacity and an oversized check against the balance cannot be observed because every call caps the balance first; a retry clamped to at least 1 and `int()` for `floor` agree for every reachable state), shown by comparing 40 random operation sequences byte for byte. The lock itself is covered only by a white-box test that records whether it is held when the clock is read, because with no `await` in the critical section asyncio never interleaves the tasks, so removing the lock changes no behaviour. One feedback iteration. Reviewer APPROVE with Minor findings (documentation of the 2^53 range, Lua number formatting and the seconds-to-milliseconds rule, now in the T-106 card). The `ARCHITECTURE.md` interface section now lists `TokenEstimator`, `reserved_tokens`, `Decision` and `RateLimiter` as final | Verifier tables, two rounds; `check.py` output |
| 2026-11-13 | T-105 | Carried to later cards: T-106 gets the clock-steps-back rule, the exact-arithmetic proposal (an integer balance scaled by 60000, exact only for a capacity up to 150,119,987,579 tokens, so its range must be decided), Lua number formatting, the seconds-to-milliseconds rounding, a note that ADR-0006 says the script returns a fractional balance, negative amounts raising `ValueError` with "negative" in the message, and a fresh key prefix per factory call; T-107 gets the same prefix and cleanup notes; T-108 gets a note that a 200's limit headers come from the reserve `Decision` and so cannot show the balance after settling (its criterion 2 needs clarifying before it is planned), that a 502's headers show the balance before the refund, and that only authenticated caller ids may reach the limiter | `docs/TASKS.md` cards T-106, T-107 and T-108 |
| 2026-11-13 | T-106 | `app/limits/token_bucket.lua` and `app/limits/redis_limiter.py` (`RedisRateLimiter` on `redis.asyncio`, loaded with `register_script`) added, unit-tested against fakeredis. The bucket is one Redis hash per API key at `tollgate:bucket:` plus the SHA-256 digest of the key, holding `balance_units` (tokens x 60000) and `updated_milliseconds`, so every refill is exactly `elapsed_ms x tokens_per_minute` and every stored value is an integer below 2^53. The time is the injected clock rounded down to whole milliseconds (`floor(Fraction(seconds) x 1000)`); the script never calls `TIME`. It returns the balance as the fraction string `"<n>/60000"`, which keeps ADR-0006's "fractional balance as a string" without a new ADR, and one strict parser turns the reply into typed values. Remaining, retry and reset are computed in Python with integer arithmetic. Range, decided by the owner: `capacity_tokens` and `tokens_per_minute` are each at most 75,059,993,789 (2^52 // 60000, a `ValueError` otherwise), and a charge stops at a debt of that many tokens, which the in-memory limiter does not do. Each call sets `PEXPIRE` to the time until the bucket is full again (including a clock that stepped back) plus 60 seconds, because a missing key starts full. Pins: `redis==8.1.0` (no new transitive packages) in `requirements.txt`; `fakeredis==2.40.0`, `lupa==2.8` and `sortedcontainers==2.4.0` (Apache 2.0 per its package metadata, a `py3-none-any` wheel) in `requirements-dev.txt`; both files installed with `--only-binary=:all:` on Windows and `pip check` was clean; the existing pins did not change. `pyproject.toml` holds lower bounds (`redis>=8.1.0`, `fakeredis[lua]>=2.40.0`) like its other entries, with the exact pins in the requirements files (owner decision). fakeredis runs the script on Lua 5.1. `scripts/check.py` passed (14 contract and 618 other tests, 84 of them in `tests/limits/test_redis_limiter.py`: the 45 shared cases plus key, TTL, clock step-back, millisecond rounding, range, debt-floor, parser and no-`TIME` tests); the shared suite is unchanged and the contract is unchanged. Mutation check on scratch copies: 31 mutations; round one left the refill cap and the refund cap alive, closed by a test at 1 token per millisecond that also reads the stored hash after a refund; in the last round 28 of 31 are caught. The three survivors are equivalent (the idle-time clamp before the refill product, the settle clamp in Python, and the `+ 1` ms in the TTL, which the 1 second PTTL tolerance cannot see), shown by comparing 300 random operation sequences byte for byte. Two feedback iterations. Reviewer APPROVE twice, all Minor findings applied | Verifier tables, three rounds; `check.py` output; `gh pr checks` is recorded in the pull request |
| 2026-11-13 | T-106 | Known limits: a key that disappears other than by expiry (for example eviction, which fakeredis does not model) starts full; gateway hosts whose clocks differ by more than 60 seconds can expire a bucket shortly before it is full; fakeredis expiry uses the real time, so TTL tests assert the PTTL that was set within 1 second. Nothing here is proven against a real Redis server until T-107. Carried to T-108: a capacity or rate above 75,059,993,789 passes `Settings` but fails when the Redis limiter is built, so it must become a startup error that names the variable | `docs/TASKS.md` card T-108 |
| 2026-11-13 | T-107 | The shared limiter suite now also runs on a real Redis server in CI. `pyproject.toml` registers the `redis_server` marker and deselects it by default (`-m 'not redis_server'`), so `scripts/check.py` and local runs show 45 deselected and none skipped. `tests/limits/test_redis_server.py` runs the 45 shared cases at `TOLLGATE_TEST_REDIS_URL`, each limiter under its own `tollgate-test:<run id>:<n>:` prefix, deleting those keys and closing the clients afterwards; with the marker selected and the variable unset the tests fail and name it. `ci.yml` gains a `redis:7.4.12` service container with a `redis-cli ping` health check and a `redis integration` step after the five `check.py` mirror steps (the job name is unchanged). On the PR run the step's log shows `45 passed, 632 deselected`; the suite is therefore tested against Redis 7.4.12 in CI, and only that (nothing was run against a real server locally, none is installed). `scripts/check.py` passed (14 contract and 605 other tests, 45 deselected). Mutation check on scratch copies: the deselection, marker, strict-marker and `pytestmark` mutations were caught; the first round left one survivor, the missing-URL failure turning into a skip (CI always sets the URL, so nothing could see it), closed by an unmarked guard test that runs the `redis_server` selection in a subprocess without the variable and asserts exit 1, the variable name and no skips. Known: a case that fails before cleanup leaves its keys in a local Redis used by hand (CI's container is discarded). One feedback iteration. Reviewer APPROVE with one Minor finding, left as noted | Verifier table; CI run log of the `redis integration` step; `gh pr checks` is recorded in the pull request |
| 2026-11-13 | T-108 | Chat completions are rate limited. `create_app()` builds the estimator and the limiter chosen by `TOLLGATE_LIMITER_BACKEND`, on the injected clock: `InMemoryRateLimiter`, or `RedisRateLimiter` on an injected client (tests pass fakeredis) or one built with `Redis.from_url`, which connects lazily. With the redis backend, a capacity or rate above 75,059,993,789 is a startup `SettingsError` naming the variable, without the value. The route estimates, reserves under the authenticated caller id (never a request value), answers a refusal with 429 (`tokens`, `rate_limit_exceeded`; `Retry-After` only when waiting can help), otherwise calls the provider and settles with `usage.total_tokens`; only the provider call is guarded, and a provider exception refunds the whole reservation and gives 502 (`api_error`, `provider_error`, a fixed message). `app/api/limit_headers.py` builds the three `x-ratelimit-*-tokens` headers and `Retry-After` from a `Decision`. Owner decisions: a 200's and a 502's headers come from the reserve decision (criterion 2 tested through a follow-up request); an authenticated 400 carries no limit headers; `60m0s` for an hour or more. The snapshot gained 87 lines and lost none (one line gained a comma), regenerated in the route commit; no dependency added; `RateLimiter` and `Decision` unchanged. `scripts/check.py` passed (14 contract and 653 other tests, 45 deselected). Mutation check on scratch copies: the card's seven mutations and 29 more (key from the body or the raw key, settle with the estimate or the reservation, `max_tokens` dropped, the guard widened to `reserve`, exception text in the 502, headers missing or from a probe, injected client ignored, every range-check variant, swapped rate and capacity, `SystemClock` on the memory backend, provider or settle called on a refusal) and three OpenAPI-only ones (39 in all) were caught in the first round. Reviewer APPROVE with four Minor findings, all applied in one feedback iteration: the remaining header's OpenAPI description now says "after the limiter's decision", a test that a settle error on the success path is neither a 502 nor refunded, the Redis test advances the clock so a Redis-backend `SystemClock` mutant fails, and ARCHITECTURE's layout. After it, 41 of 41 mutations were caught (the 39 plus those two new mutants: settle moved inside the guard, and the Redis-backend `SystemClock`) | Verifier tables, two rounds; `check.py` output; `gh pr checks` is recorded in the pull request |
| 2026-11-13 | T-108 | Known gaps, accepted by the owner and left for later tasks: (1) the Redis client that `create_app()` builds from the URL is never closed on shutdown (no lifespan hook); (2) a malformed `TOLLGATE_REDIS_URL` scheme gives redis-py's `ValueError`, which does not echo the URL, rather than a `SettingsError`; (3) a Redis outage during `reserve` or `settle` gives a 500 with no limit headers (fail closed); (4) a `settle` that fails after a successful provider call loses the completion and gives a 500, never a refund or a 502 (pinned by a test); (5) a client that disconnects mid-request (`CancelledError`) leaves the reservation charged at the estimate; (6) a negative `total_tokens` from a provider makes `settle` raise. Also still open from T-103: each request hashes the key twice (the route class and the `require_api_key` dependency) | Plan review and reviewer findings |
| 2026-11-13 | - | Phase 1 gate signed off by the owner: all eight gate items met, the README item by this pull request (the sign-off takes effect when it merges). ADR-0006, ADR-0007 and ADR-0008 stay accepted as written (ADR-0009, accepted 2026-11-13, amends ADR-0008). Gate check run the same day on `main` at `c5060af`: T-101 to T-108 `done`; `scripts/check.py` passed (14 contract and 653 other tests, 45 deselected); the `ci` run `43448484605` succeeded, its `pytest` step showing 667 passed and 45 deselected and its `redis integration` step 45 passed against `redis:7.4.12`; the committed snapshot lists the 200, 400, 401, 429 and 502 responses, with the limit headers on 200, 429 and 502 and none on 400; each Phase 1 task that added tests has a mutation table in this Log, and every survivor is explained as an equivalent mutant (T-103: 2, T-104: 2, T-105: 4, T-106: 3); tests use no network, the only HTTP client being `httpx` over an in-process ASGI transport; 112 commits, all with the owner's author email, none with a trailer or attribution line. The README was rewritten to describe what is built, with the Redis claim limited to Redis 7.4.12 in CI and a list of the known gaps. The known gaps in the T-108 rows carry into Phase 2 | `scripts/check.py` output; `gh run view 43448484605 --log`; `tests/contract/openapi.json`; `git log` (read-only) |
| 2026-11-13 | - | Phase 2 planned: cards T-201 to T-207, the Phase 2 gate and board rows; ADR-0010 (plain httpx adapters, translation rules, failure taxonomy, `bad_response` charged as reserved, amending ADR-0007 and ADR-0008) and ADR-0011 (route table file, ordered fallback on retryable failures, 404 for an unknown model, two response headers, amending ADR-0008) proposed. A review of the first draft found that T-202 overstated which existing tests pass unchanged, that both ADRs amended ADR-0008 without saying so, and that the Anthropic card added a failure rule the ADR did not have; all were corrected in the planning pull request before it went to the owner, and the client-shutdown work was split out of the Ollama card. Research checked on this date: package versions, licences, dependencies and wheels against the PyPI JSON API (moving httpx 0.28.1 to runtime adds no package; the official SDKs would add 8, built on `httpx2`, and retry by default; `tiktoken` would add 5 and its encoding files' licence is still unstated); Ollama, OpenAI and Anthropic request, response and error formats in their documentation and source; fallback behaviour in LiteLLM, OpenRouter, Portkey, Kong and Envoy AI Gateway documentation and source. Nothing was installed. Of the T-108 known gaps, the unclosed Redis client is closed in T-203, and a negative count from an HTTP adapter becomes `bad_response` (ADR-0010; a negative count from the mock or an injected provider still makes `settle` raise); gaps 2 to 5 are backlog items | `docs/DECISIONS.md`; the planning pull request |
| 2026-11-13 | - | Decisions by the owner: ADR-0010 and ADR-0011 accepted as written, no revisions. ADR-0007's status is now "Accepted - amended by ADR-0010" and ADR-0008's "Accepted - amended by ADR-0009, ADR-0010 and ADR-0011". The Phase 2 gate item for the ADRs is ticked; T-201 can start once the planning pull request merges | `docs/DECISIONS.md` (index and ADR headers); commit `7f89231` |
