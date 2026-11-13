# Tasks

The task board for the project. One task is `in-progress` at a time. Each task is small enough to review as
one change and has acceptance criteria that can be checked with evidence.

**Statuses:** `todo` → `in-progress` (branch open) → `done`. `review` is used only while a pull request waits for
an owner check; a normal task goes straight from `in-progress` to `done`. `blocked` = stopped, reason in the Log.
A task becomes `done` in the pull request that delivers it (the status is set in the branch's last commit and
takes effect when the pull request merges). `in-progress` and `review` exist only on the task branch; `main`
shows `todo`, `blocked` or `done`.

## Current phase: 1 - Token-aware rate limiting

`POST /v1/chat/completions` (non-streaming) in front of a mock provider, with API-key authentication and a
per-key token bucket that reserves estimated tokens before the call and settles with actual usage after. State
lives in memory or in Redis. Planned 2026-11-12; ADR-0006 to ADR-0008 were accepted by the owner the same day.

**Gate (owner signs off):**

- [ ] Every Phase 1 task is `done`, and `python scripts/check.py` is green locally and in CI
- [x] ADR-0006, ADR-0007 and ADR-0008 accepted or revised (accepted as written, 2026-11-12)
- [ ] `/v1/chat/completions` works with the mock provider, and the OpenAPI snapshot records its 200, 400, 401,
      429 and 502 responses and the limit headers
- [ ] The shared limiter behaviour suite passes on the in-memory limiter, on fakeredis and on a real Redis
      server, the last in the CI step `redis integration`, green on `main`
- [ ] Every Phase 1 task that adds tests has a mutation table with no unexplained survivor
- [ ] Tests use no network and no paid API, except the CI-only Redis service container on localhost (ADR-0006)
- [ ] README and ARCHITECTURE describe what is built, and every claim comes from a recorded run
- [ ] Every commit is authored by the owner, with no co-author trailers

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
T-004. Delivery order in Phase 1: T-101 to T-108 in number order. The rows below are in delivery order; the
cards further down are listed by ID.

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
| T-105 | In-memory token bucket and the shared behaviour suite | 1 | todo | T-101; ADR-0007 accepted 2026-11-12 |
| T-106 | Redis token bucket, unit-tested against fakeredis | 1 | todo | T-105; ADR-0006 accepted 2026-11-12 |
| T-107 | Real Redis in CI | 1 | todo | T-106 |
| T-108 | Rate limiting on chat completions | 1 | todo | T-103, T-104, T-105, T-106 |

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

- **Status:** todo
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

- **Status:** todo
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

- **Status:** todo
- **Goal:** the Redis limiter is proven against a real Redis server, in CI only, without adding network use to
  local runs.
- **Context:** ADR-0006, `.github/workflows/ci.yml`, `pyproject.toml`, `scripts/check.py`,
  `tests/limits/behaviour.py`.
- **Depends on:** T-106.
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

- **Status:** todo
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
- **Contract:** changes (429, 502 and the headers); regenerated snapshot in its own commit.
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
  `feat(api): reserve and settle tokens on chat completions`, `test(contract): update the OpenAPI snapshot
  for rate limiting`, `docs(tasks): complete T-108`.
- **Size:** about 300 lines plus the snapshot diff.

## Later phases (broken into tasks at each gate)

| Phase | Epic |
| --- | --- |
| 1 | Token-aware rate limiting: planned 2026-11-12 as T-101 to T-108 (see the current phase) |
| 2 | Model routing: rules, fallback on provider failure, Ollama, then OpenAI and Anthropic adapters |
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
| 2026-11-13 | T-103 | Complete. At the owner's request the five remaining tests were added (whitespace or a no-break space before the scheme, an empty scheme, a key with an internal space, an authenticator with no keys) and the fake secret in `tests/test_settings.py` was renamed so it no longer begins with `sk-`; a literal scan of the repository for that prefix is now empty. `scripts/check.py` passed (14 contract and 444 other tests). In the last verification all five new survivors, the five from the previous round and 17 earlier mutations were caught, and four mutations of `app/settings.py` (keys or the Redis URL stored unmasked, a value in an error message, key text in `repr`) were still caught after the rename. A review of the test for the empty scheme found that its HTTP-level case did not contain an empty scheme; it was corrected. The owner decided that adversarial mutation stops here. Two mutations (header names decoded as latin-1, `casefold` for `lower` on the scheme) are equivalent. Known and accepted: `/openapi.json` and `/docs` need no key; each request hashes the key twice, to be merged when T-108 needs the identity | Verifier tables, iteration 4 and the final run |
| 2026-11-13 | T-104 | `app/limits/estimate.py` added: the `TokenEstimator` protocol (`estimate_input_tokens(request)`), `HeuristicEstimator` (`ceil(characters / 4) + 3` per message, +1 for a `name`, +3 for the reply, integer arithmetic only) and `reserved_tokens(request, estimator)` (the estimate plus `max_completion_tokens`, else `max_tokens`, else 0). Characters are Python string length, so a non-BMP character counts once and a combining mark counts as its own character. A `name` counts whenever it is present, including an empty string. No cap is put on `max_tokens`, so an oversized reservation is left to the limiter (ADR-0007). `scripts/check.py` passed (14 contract and 479 other tests); no dependency was added and the contract is unchanged. Mutation check on scratch copies: 39 mutations (the card's five and 34 more), the first round caught 36 and left a whitespace gap (characters counted after `strip()`), closed by a test with whitespace content; the second round caught 37 of 39. The two survivors are equivalent for any request the API accepts, because both max fields are validated to be at least 1: `or` instead of `is not None` on the max fields differs only when `max_completion_tokens` is 0, and a truthiness test on `max_tokens` differs only when it is negative. One feedback iteration. Reviewer APPROVE with three Minor findings (a layout line re-wrapped, a comment on the protocol test, a name-shadowing note for T-105). The `ARCHITECTURE.md` interface section was not changed; T-105 adds the new entries there | Verifier tables, two rounds; `check.py` output |
