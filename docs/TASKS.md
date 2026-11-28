# Tasks

The task board for the project. One task is `in-progress` at a time. Each task is small enough to review as
one change and has acceptance criteria that can be checked with evidence.

**Statuses:** `todo` → `in-progress` (branch open) → `done`. `review` is used only while a pull request waits for
an owner check; a normal task goes straight from `in-progress` to `done`. `blocked` = stopped, reason in the Log.
A task becomes `done` in the pull request that delivers it (the status is set in the branch's last commit and
takes effect when the pull request merges). `in-progress` and `review` exist only on the task branch; `main`
shows `todo`, `blocked` or `done`.

## Current phase: 5 - Demo and write-up

A first-time reader, such as a recruiter or an interviewer, learns from the README and the pages it links what
Tollgate does, what was measured and what was found. Every figure can be traced to a committed report or a
recorded transcript. The write-up covers three findings:

- The semantic cache eval found no safe threshold for `all-minilm`.
- Every load run at 40 requests/s on Windows failed ADR-0018's lag rule, with a lag p99 consistent with the
  Windows timer tick (an external figure, not measured here).
- Through the `openai` adapter, the gateway fell behind targets of 100 requests/s and above, at about 46 to 54/s.
  T-502 either records the cause with measurements, or the write-up states it as suspected and unconfirmed, or
  that it does not reproduce on the current commit.

The demo is text: curl output, `/metrics` text and JSON log lines from one real local run, with optional
screenshots. There is no hosted demo and no published image (ADR-0019), and no Prometheus or Grafana. There is
no new dependency, no new image and no `app/` change. The contract is unchanged. Planned 2026-11-26;
ADR-0019 was accepted by the owner as written the same day. The owner also approved the card sizes,
including T-506 above the plan threshold, and runs the localhost runs of T-502 and T-505 by hand, as in T-409.

**Gate (owner signs off):**

- [ ] Every Phase 5 task is `done`, and `python scripts/check.py` is green locally and in CI
- [x] ADR-0019 accepted or revised, and ADR-0017's status line names it (accepted as written 2026-11-26)
- [ ] Every figure in the README, `docs/findings.md`, `docs/benchmarks.md` and `docs/demo.md` comes from a
      committed report or a recorded transcript, with its settings, and a figure from an invalid run is called
      invalid wherever it appears
- [ ] The throughput ceiling's cause is stated only as far as T-502's recorded measurements show it; otherwise
      it is "suspected, unconfirmed", or "not reproduced" if T-502 found that it does not reproduce
- [ ] The README's first screen states what Tollgate is and the three findings, with links to their sources,
      and neither the README nor ARCHITECTURE calls anything built "planned" or anything unbuilt "built"
- [ ] Every edge in every diagram is backed by a line of code, `compose.yaml`, the `Dockerfile` or a file in
      `deploy/`
- [ ] No key, token or other secret appears in any committed file, transcript or screenshot
- [ ] Every commit is authored by the owner, with no co-author trailers

## Phase 4 - Operations (complete; one gate item carried to Phase 5)

All nine tasks are done. The owner signed off the gate on 2026-11-26, except the item "README and ARCHITECTURE
describe what is built", which stays open and is delivered in Phase 5 by T-504 and T-506.

Every request writes one JSON log line built only from bounded fields, and `/metrics`, behind a token of its
own, exports Prometheus metrics written with the standard library. These include the settle cap, the reply size
cap, provider attempts and cache lookups. Durations come from an injected monotonic clock. The gateway ships as a
digest-pinned, non-root image with a Compose stack (gateway, Redis, optional Ollama), started and smoke-tested by
a CI job. The deployment target is one host running that stack. Load is measured at a fixed arrival rate from
each request's due time, against a fake upstream, and the cache scan and the embedding call are measured too.
Every figure comes from the owner's recorded runs. No new dependency. Planned 2026-11-23; ADR-0016 and ADR-0017
were accepted by the owner as written the same day, and ADR-0018 with one added line on the lag threshold.
The owner also approved the card sizes, including the five above the plan threshold.

**Gate (signed off by the owner, 2026-11-26, except the README and ARCHITECTURE item, carried to T-504 and
T-506):**

- [x] Every Phase 4 task is `done`, and `python scripts/check.py` is green locally and in CI
- [x] ADR-0016, ADR-0017 and ADR-0018 accepted or revised, the status lines of ADR-0013 and ADR-0014 updated
      to name ADR-0016, and ADR-0006's to name ADR-0017 (accepted 2026-11-23)
- [x] Durations come from the injected monotonic clock, never the wall clock, and tests use a fake
- [x] Every request writes one JSON log line holding only the ADR-0016 fields, and a test proves that no prompt,
      model, API key, key digest, caller id, header value or query string reaches the log
- [x] `/metrics` exists only when a metrics token is set, refuses API keys, is absent from the OpenAPI document,
      and exports the ADR-0016 metric set, including the settle cap, the reply size cap and the embedder failures
- [x] The image builds from a digest-pinned base, runs as a non-root user and holds only the app and its
      dependencies, and the CI job `container` starts the Compose stack and passes its smoke checks on `main`
- [x] The deployment target is the one ADR-0017 records
- [x] Every figure in the README or `docs/benchmarks.md` comes from a recorded run with its settings, including
      where the generator ran, and a run that fails the validity check is reported as invalid; or the owner
      waives a run in writing
- [x] Tests use no network and no paid API. The exceptions are the CI Redis container (ADR-0006) and, in the
      `container` job only, the image and wheel downloads and the localhost traffic to its own Compose stack
      (ADR-0017)
- [x] Every Phase 4 task that adds tests has a mutation table with no unexplained survivor
- [ ] README and ARCHITECTURE describe what is built, and every claim comes from a recorded run
- [x] Every commit is authored by the owner, with no co-author trailers

## Phase 3 - Semantic caching (complete)

An eligible chat completion (last message from the user) is embedded by a local Ollama and looked up, after the
reservation, in a bounded in-memory cache partitioned by caller and by every other part of the request. A hit
returns the stored answer and refunds the reservation; a miss runs the route and stores a `stop` answer. An
embedder failure skips the cache. The similarity threshold is required when the cache is on, and the value the
docs recommend comes from a recorded run of an eval harness of labelled prompt pairs. No new dependency.
Planned 2026-11-21; ADR-0014 and ADR-0015 were accepted by the owner the same day. The README and the
ARCHITECTURE status line were updated in the gate close-out pull request, as for Phase 2. The owner signed off
the gate on 2026-11-23. Phase 4 is planned at its own gate (`/plan-phase`).

**Gate (signed off by the owner, 2026-11-23):**

- [x] Every Phase 3 task is `done`, and `python scripts/check.py` is green locally and in CI
- [x] ADR-0014 and ADR-0015 accepted or revised, and the status lines of ADR-0007 and ADR-0011 updated to name
      ADR-0014 (accepted as written, 2026-11-21)
- [x] The cache is looked up only after route selection and the reservation; it is partitioned by caller and by
      every other part of the request; a hit settles 0 and runs no target; an embedder failure is a `skip`
      and the request is still served; only a `stop` answer within the size cap is stored; entries expire and
      are evicted on the injected clock
- [x] Every 200 carries `x-tollgate-cache` (`hit`, `miss` or `skip`), no other status does, and the OpenAPI
      snapshot records it
- [x] The Ollama embedder is tested through `httpx.MockTransport` only, and the app closes its client at shutdown
- [x] The eval harness runs in CI on the hashing baseline, and the threshold the docs recommend comes from the
      owner's recorded run against a local embedding model, or the owner explicitly waives the run and the docs
      recommend no threshold
- [x] Tests use no network and no paid API (the CI Redis container excepted, ADR-0006); an embedding model is
      called only by the owner, by hand
- [x] Every Phase 3 task that adds tests has a mutation table with no unexplained survivor
- [x] README and ARCHITECTURE describe what is built, and every claim comes from a recorded run
- [x] Every commit is authored by the owner, with no co-author trailers

## Phase 2 - Model routing (complete)

Each chat completion is routed by its `model` to an ordered list of provider targets read from a validated
route table file, and falls back to the next target on retryable failures. Ollama, OpenAI and Anthropic
adapters are written on plain `httpx` and tested only through `httpx.MockTransport`. One reservation and one
settle per request, as in Phase 1. Planned 2026-11-13; ADR-0010 and ADR-0011 were accepted by the owner the
same day. The README and the ARCHITECTURE status line were updated in the gate close-out pull
request, as for Phase 1. The owner signed off the gate on 2026-11-21. Phase 3 is planned at its own gate (`/plan-phase`).

**Gate (signed off by the owner, 2026-11-21):**

- [x] Every Phase 2 task is `done`, and `python scripts/check.py` is green locally and in CI
- [x] ADR-0010 and ADR-0011 accepted or revised, and the status lines of ADR-0007 and ADR-0008 updated to name
      the ADRs that amend them (accepted as written, 2026-11-13)
- [x] Routes come from a route table validated at startup; an unknown model gets 404 before any reservation;
      fallback happens only on retryable failures, each target is tried at most once, and each request has one
      reservation and one settle
- [x] The Ollama, OpenAI and Anthropic adapters translate requests, responses and errors as ADR-0010 says, each
      tested through `httpx.MockTransport` only; no provider SDK is a dependency
- [x] ADR-0012 accepted or revised, and the status line of ADR-0007 updated to name it (accepted as written,
      2026-11-14)
- [x] ADR-0013 accepted or revised, and the status line of ADR-0010 updated to name it (accepted as written,
      2026-11-14)
- [x] The app closes the HTTP and Redis clients it builds when it shuts down
- [x] Tests use no network and no paid API (the CI Redis container excepted, ADR-0006). A real provider is
      called only by the owner, by hand, and the owner's run against a local Ollama is recorded in the Log or
      explicitly waived by the owner
- [x] Every Phase 2 task that adds tests has a mutation table with no unexplained survivor
- [x] README and ARCHITECTURE describe what is built, and every claim comes from a recorded run
- [x] Every commit is authored by the owner, with no co-author trailers

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
T-004. Delivery order in Phase 1: T-101 to T-108 in number order. Delivery order in Phase 2: T-201 to T-204,
then T-208 and T-209 (both added 2026-11-14), then T-205 and T-206, then T-207 and T-210 (added
2026-11-14) in either order. Delivery order in Phase 3: T-301 to T-307 in number order. Delivery order in
Phase 4: T-401 to T-409 in number order. Delivery order in Phase 5: T-501 to T-507 in number order. The rows
below are in delivery order; the cards further down are listed by ID.

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
| T-201 | Provider errors and the route table | 2 | done | Phase 1 gate; ADR-0010 and ADR-0011 accepted 2026-11-13 |
| T-202 | Routing and fallback on chat completions | 2 | done | T-201 |
| T-203 | Close the clients the app builds on shutdown, and check provider names | 2 | done | T-202 |
| T-204 | Ollama adapter | 2 | done | T-203 |
| T-208 | Cap what `settle` charges | 2 | done | T-204; ADR-0012 accepted 2026-11-14 |
| T-209 | Cap the size of a provider reply | 2 | done | T-204; ADR-0013 accepted 2026-11-14 |
| T-205 | OpenAI adapter | 2 | done | T-204, T-208, T-209 |
| T-206 | Anthropic adapter | 2 | done | T-204, T-208, T-209 |
| T-207 | Real-provider guide and the owner's Ollama run | 2 | done | T-204, T-205, T-206 |
| T-210 | Share the HTTP adapters' reply checks and request handling | 2 | done | T-206 |
| T-301 | Embedders: the interface, the hashing baseline and the Ollama embedder | 3 | done | Phase 2 gate; ADR-0014 and ADR-0015 accepted 2026-11-21 |
| T-302 | Cache settings | 3 | done | T-301 |
| T-303 | In-memory semantic cache | 3 | done | T-301, T-302 |
| T-304 | Cache eval harness and its dataset | 3 | done | T-303 |
| T-305 | Build the cache in the app and share the id source | 3 | done | T-303, T-304 |
| T-306 | Semantic cache on chat completions | 3 | done | T-305 |
| T-307 | The owner's eval run, the recommended threshold and the cache guide | 3 | done | T-304, T-306 |
| T-401 | Request timing, route attempts and the reason for a skip | 4 | done | Phase 3 gate; ADR-0016, ADR-0017 and ADR-0018 accepted 2026-11-23 |
| T-402 | Structured request log | 4 | done | T-401 |
| T-403 | Metrics registry and the Prometheus text format | 4 | done | T-402 |
| T-404 | Metrics on the app and the `/metrics` endpoint | 4 | done | T-402, T-403 |
| T-405 | Container image, Compose stack and the CI container check | 4 | done | T-404 |
| T-406 | Fake upstream, benchmark route files and the fixed-rate runner | 4 | done | T-401 |
| T-407 | Load report: statistics, validity check and command line | 4 | done | T-406 |
| T-408 | Cache scan and embedding latency benchmarks | 4 | done | T-407 |
| T-409 | The owner's benchmark runs and the operations guide | 4 | done | T-405, T-407, T-408 |
| T-501 | Commit the ramp reports | 5 | done | Phase 5 plan merged |
| T-502 | Investigate the scenario B throughput ceiling | 5 | done | T-501 |
| T-503 | The findings write-up | 5 | done | T-502 |
| T-504 | ARCHITECTURE refresh: deployment and component diagrams | 5 | todo | ADR-0019 accepted |
| T-505 | The text demo | 5 | todo | ADR-0019 accepted |
| T-506 | README rewrite, findings first | 5 | todo | T-503, T-504, T-505 |
| T-507 | Phase 5 close-out and TASKS housekeeping | 5 | todo | T-506 |

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

- **Status:** done (2026-11-13)
- **Clarified by the owner at plan review (2026-11-13):** `api_key_env` must look like an environment variable
  name (`^[A-Za-z_][A-Za-z0-9_]*$`), so a key pasted there by mistake is rejected with a fixed reason and never
  printed; `TOLLGATE_ROUTES_FILE` set but blank is an error, not a fallback to the built-in table; the file must
  be UTF-8 without a BOM; the error for an unreadable file leaves out the path, which is the variable's value.
  The plan came to about 650 hand-written lines (mostly exact-message tests), approved by the owner. After
  review the owner also decided that an empty provider name, an empty alias and an empty upstream `model` are
  rejected at startup (an empty alias can never match a request, and an empty model would only fail upstream).
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

- **Status:** done (2026-11-14)
- **Clarified by the owner at plan review (2026-11-14):** the plan came to about 720 hand-written lines across
  12 files, approved; a `bad_response` from a later target, after a fallback, is also charged as reserved
  (ADR-0010 as written); the OpenAPI response-set test is renamed to include 404; `docs/setup.md` says that
  only the `mock` type is built until T-204 to T-206.
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

### T-203 - Close the clients the app builds on shutdown, and check provider names

- **Status:** done
- **Goal:** the app closes every client it builds when it shuts down, starting with the Redis client built from
  the URL (the first known gap in the T-108 Log), so the adapter tasks only register their HTTP clients. A
  provider name that cannot be sent as the `x-tollgate-provider` header stops the app at startup (the first
  known gap in the T-202 Log, folded into this card by the owner on 2026-11-14).
- **Context:** `app/main.py`, `app/routing/config.py`, `tests/test_app_wiring.py`,
  `tests/test_chat_rate_limits.py`, `tests/test_route_table.py`, ADR-0011.
- **Depends on:** T-202.
- **Deliverables:**
  - A list of owned clients on `app.state`, which `create_app()` appends to whenever it builds a client
    (T-204 appends its HTTP clients the same way), and an app lifespan that, on shutdown, closes every client in
    that list in the reverse order of building and continues past a client whose close raises. The Redis client
    built with `from_url` is appended; an injected client is not.
  - `app/routing/config.py` rejects a provider name that is not made only of visible ASCII characters (`\x21` to
    `\x7e`, so no space, control character, CR, LF or non-ASCII character), next to the existing empty-name
    check. The error is a `SettingsError` naming `TOLLGATE_ROUTES_FILE` and the path `providers` with a fixed
    reason, and never the name itself, since the name is the value that cannot be printed safely.
    `docs/setup.md` states the rule.
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. With the redis backend and no injected client, the client built from the URL is closed when the app shuts
     down (the lifespan run through `TestClient` as a context manager), and no connection is opened.
  2. An injected Redis client is still open after shutdown.
  3. With two clients in the owned list, both are closed in reverse order, and a close that raises does not stop the
     other.
  4. The memory backend builds nothing and closes nothing.
  5. A route file whose provider name contains a space, `\x7f`, a non-ASCII character, CR, LF or another control
     character fails at startup with the `SettingsError` above, and the message does not contain the name; a
     name using every visible ASCII character from `\x21` to `\x7e` is accepted and served, with that name in
     `x-tollgate-provider`.
- **Verification:** `python scripts/check.py` green; mutation table (the lifespan never closes, the injected
  client closed, the order not reversed, the first failing close stopping the rest, the memory backend
  registering a client, the name check skipped, the range widened to allow a space or `\x7f` or non-ASCII, the
  range narrowed to reject `\x21` or `\x7e`, the name echoed in the message); `gh pr checks <n> --watch`.
- **Branch and commits:** `feat/t-203-client-shutdown`; `feat(app): close the clients the app builds on
  shutdown`, `fix(routing): reject provider names that cannot be sent as a header`, `docs(tasks): complete
  T-203`.
- **Size:** about 200 lines.

### T-204 - Ollama adapter

- **Status:** done
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

- **Status:** done
- **Goal:** a route can be served by OpenAI chat completions, tested only with `httpx.MockTransport`.
- **Context:** ADR-0010, `app/providers/`, `app/main.py`, the T-204 adapter as the pattern.
- **Depends on:** T-204, T-208 and T-209: a provider's reported usage must be bounded before `settle` (owner
  decision, T-204 review), and its reply must be read with a size cap (owner decision, 2026-11-14), so this task
  does not start until T-208 and T-209 are `done`, or the owner records that either is waived. The adapter reads
  a 2xx body with `read_capped` and its provider's `max_response_bytes` (ADR-0013).
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

- **Status:** done
- **Goal:** a route can be served by the Anthropic Messages API, tested only with `httpx.MockTransport`.
- **Context:** ADR-0010, `app/providers/`, `app/main.py`, the T-204 adapter as the pattern.
- **Depends on:** T-204, T-208 and T-209: a provider's reported usage must be bounded before `settle` (owner
  decision, T-204 review), and its reply must be read with a size cap (owner decision, 2026-11-14), so this task
  does not start until T-208 and T-209 are `done`, or the owner records that either is waived. The adapter reads
  a 2xx body with `read_capped` and its provider's `max_response_bytes` (ADR-0013).
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

- **Status:** done
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

### T-208 - Cap what `settle` charges

- **Status:** done
- **Goal:** one absurd usage count from a provider can no longer lock the caller's key out. A 200 charges at
  most the bucket capacity, whichever adapter served it and whichever limiter is configured (ADR-0012).
- **Context:** ADR-0007, ADR-0010, ADR-0012, `app/api/chat.py`, `app/limits/limiter.py` (`Decision`),
  `tests/test_chat_rate_limits.py`, `tests/test_app_ollama.py`, the T-204 Log row (known gap 3).
- **Depends on:** T-204; ADR-0012 accepted 2026-11-14. Delivered before T-205 and T-206.
- **Deliverables:**
  - `app/limits/charge.py`: `charged_tokens(reported_tokens: int, limit_tokens: int) -> int`, the smaller of
    the two. A negative count is returned unchanged, so it still makes `settle` raise as today (ADR-0010, out
    of scope here).
  - `app/api/chat.py`: the 200 path settles with `charged_tokens(<the completion's total_tokens>,
    decision.limit_tokens)`. The 502 paths, the completion and its `usage`, and every header are unchanged.
    The module docstring states the cap.
  - `docs/ARCHITECTURE.md`: `charge.py` added to the `app/limits/` layout, and one sentence on the cap where
    the route's settle is described.
- **Contract:** unchanged. No response, header or field is added, and the snapshot does not change.
- **Acceptance criteria:**
  1. `charged_tokens` returns the reported count when it is at most the limit (0, the limit minus 1, exactly
     the limit) and the limit when it is above (the limit plus 1, `10**30`), returns a negative count
     unchanged, and a property test over 1,000 integer pairs from a seeded `random.Random` (no new dependency;
     reported counts from below 0 to above 2^63) shows the result is never above the limit and equals the
     reported count whenever that is at most the limit.
  2. Through the whole app with the in-memory limiter, at 60 tokens per minute (1 token per second) so that one
     token of balance moves every header: a provider reporting `total_tokens` of `10**30` gives a 200 whose
     `usage` is exactly what the provider reported; a follow-up request on the same frozen clock is a 429 whose
     `Retry-After` is the follow-up's reservation in seconds (a balance of exactly 0); after one full refill a
     follow-up is a 200.
  3. The same through the whole app with the Redis limiter on fakeredis; in addition the stored
     `balance_units` after the settle is exactly 0, not the debt floor, and the key's PTTL equals one full
     refill plus 1 ms plus the 60-second margin (the script's expiry, T-106), checked with the existing
     `assert_pttl` tolerance.
  4. Boundaries, through the whole app at 60 tokens per minute: a reported count of exactly the capacity and of
     the capacity plus 1 both leave a balance of exactly 0, and the capacity minus 1 leaves exactly 1. Shown by
     advancing the clock by exactly the follow-up's reservation in seconds: a balance of 0 gives a 200 with
     `x-ratelimit-remaining-tokens: 0`, a balance of 1 gives 1, and an uncapped balance of -1 gives a 429. On
     Redis the stored hash shows the same balances.
  5. A count at or below the capacity is charged exactly as before: the existing settle and 502 tests pass
     unchanged, and a new test charges a count above the reservation and below the capacity in full.
  6. Through the Ollama adapter and an `httpx.MockTransport`, counts summing to more than the capacity give a
     200 with the reported `usage` and a capped charge, so the cap holds for HTTP adapters, not only the mock.
     The charge is shown as in criterion 2: at 60 tokens per minute, the follow-up's `Retry-After` equals its
     reservation in seconds.
  7. The OpenAPI snapshot is unchanged.
- **Verification:** `python scripts/check.py` green; mutation table, listed before the first run: the cap
  removed; `max` in place of `min`; the cap at the reservation; the cap at twice the reservation; the cap at the
  limit plus the reservation; the cap at the limit plus 1 and the limit minus 1; the cap taken from
  `remaining_tokens`; the cap skipped for a served HTTP adapter (applied only when the mock served); the cap
  skipped when the limiter is the Redis one, and separately when it is the in-memory one; the client's
  `usage.total_tokens` rewritten to the charge; a negative count clamped to 0 inside `charged_tokens` (a clamp
  in the route is out of scope, since no criterion feeds a negative count through the app); the `bad_response`
  charge taken from the limit instead of the reservation. A comparison
  written as `<` instead of `<=` at the limit is equivalent and is recorded as such; `gh pr checks <n>
  --watch`.
- **Branch and commits:** `fix/t-208-settle-cap`; `feat(limits): add the capped settle charge` (the function
  and its unit tests), `fix(api): cap what a chat completion settles at the bucket capacity` (the route, the
  app tests and the ARCHITECTURE sentence), `docs(tasks): complete T-208`.
- **Size:** about 150 lines, mostly tests.

### T-209 - Cap the size of a provider reply

- **Status:** done
- **Goal:** no provider reply can make the gateway hold an unbounded body in memory. A 2xx body above the
  provider's `max_response_bytes` is a `bad_response`, read no further than the chunk that passes the limit
  (ADR-0013).
- **Context:** ADR-0010, ADR-0013, `app/providers/ollama.py`, `app/routing/config.py` (`_HttpProviderConfig`),
  `app/main.py` (`build_providers`), `tests/test_ollama_provider.py`, `tests/test_app_ollama.py`,
  `tests/test_route_table.py`, `docs/setup.md` (the route file fields), the T-204 Log row (known gap 3).
- **Depends on:** T-204; ADR-0013 accepted 2026-11-14. Delivered after T-208 and before T-205 and T-206.
- **Deliverables:**
  - `app/routing/config.py`: `max_response_bytes` on `_HttpProviderConfig` (so on `ollama`, `openai` and
    `anthropic`), a whole number from 1,024 to 67,108,864, default 8,388,608, with named constants.
  - `app/providers/http_body.py`: `async def read_capped(response: httpx.Response, max_response_bytes: int) ->
    bytes`, which adds up the chunks of `response.aiter_bytes()`, raises `ProviderError("bad_response",
    response.status_code)` as soon as the total is above the limit, and otherwise returns the joined body.
  - `app/providers/ollama.py`: `OllamaProvider` takes `max_response_bytes` and reads a 2xx body with
    `read_capped` instead of `aread()`; `build_providers` passes the provider's configured value. The status is
    still read first and a non-2xx body is never read.
  - `docs/setup.md`: the field, its bounds and default, and what an oversized reply costs. `docs/ARCHITECTURE.md`:
    `http_body.py` in the `app/providers/` layout.
- **Contract:** unchanged. No response, header or field is added, and the snapshot does not change.
- **Acceptance criteria:**
  1. `read_capped`, through an `httpx.MockTransport` whose body is an async generator of chunks: a body of
     exactly the limit, the limit minus 1, and 0 bytes is returned unchanged; a body of the limit plus 1 is
     `bad_response` with the reply's status. The total spans chunks: a limit crossed in the third of five chunks
     raises, and the generator was asked for no chunk after the third.
  2. The count is of decoded bytes: a gzip-encoded body (`Content-Encoding: gzip`) whose compressed size is below
     the limit and whose decoded size is the limit plus 1 is `bad_response`, and one whose decoded size is exactly
     the limit is returned decoded.
  3. The route table: `max_response_bytes` defaults to 8,388,608 on each of `ollama`, `openai` and `anthropic`;
     1,024 and 67,108,864 are accepted; 1,023, 67,108,865, `true`, `1024.0` and `"1024"` stop startup with a
     `SettingsError` naming `TOLLGATE_ROUTES_FILE` and the field path, never the value; it is rejected on `mock`.
  4. Through the whole app with an Ollama route whose `max_response_bytes` is 1,024: a 200 body of 1,025 bytes
     gives the ADR-0008 502 with no byte of the body in the response, does not fall back to the route's next
     target, and stays charged as reserved (a follow-up shows the balance less two reservations); a valid body
     padded with JSON whitespace to exactly 1,024 bytes gives a 200.
  5. Every existing test passes unchanged, and the OpenAPI snapshot is unchanged.
- **Verification:** `python scripts/check.py` green; mutation table, listed before the first run: the cap
  removed (`aread()` restored); `>=` in place of `>` at the limit; the limit plus 1 and minus 1; the encoded
  count (`aiter_raw()` or `num_bytes_downloaded`) in place of the decoded one; the whole body read before the
  check (`len(await response.aread())`); the configured value ignored (the default always used); the default,
  the lower bound and the upper bound each off by one; an oversized reply classified as retryable; an oversized
  reply refunded instead of charged; the body read before the status; the message holding part of the body;
  `gh pr checks <n> --watch`.
- **Branch and commits:** `feat/t-209-reply-size-cap`; `feat(routing): add max_response_bytes to the HTTP
  providers` (the field and its route table tests), `feat(providers): cap the size of an HTTP provider reply`
  (the helper, the Ollama adapter, their tests and the docs), `docs(tasks): complete T-209`.
- **Size:** about 200 lines, mostly tests.

### T-210 - Share the HTTP adapters' reply checks and request handling

- **Status:** done
- **Goal:** the Ollama, OpenAI and Anthropic adapters stop repeating the same request handling and reply
  checks. Each adapter keeps only its own translation, and every adapter error has no `__context__` that could
  hold a reply body or a key.
- **Context:** ADR-0010, ADR-0013, `app/providers/ollama.py`, `app/providers/openai.py`,
  `app/providers/anthropic.py`, `app/providers/http_body.py`, `tests/test_http_body.py`, the six adapter test
  files (`tests/test_{ollama,openai,anthropic}_provider.py`, `tests/test_app_{ollama,openai,anthropic}.py`),
  the T-205 Log row (known gaps 1 and 3) and the T-206 Log row (known gap 4). New test files:
  `tests/test_provider_fields.py` and `tests/test_adapter_wiring.py`.
- **Depends on:** T-206. Independent of T-207; either can go first.
- **Deliverables:**
  - `app/providers/fields.py` (new): the reply checks the adapters share, each raising
    `ProviderError("bad_response", status)` after any `try` block, never inside an `except`:
    `text(value, status) -> str` (a string that encodes as UTF-8; empty allowed), `non_empty_text(value,
    status) -> str`, `whole_number(value, status) -> int` (an `int` of at least 0, not a `bool`) and
    `required_count(mapping, key, status) -> int` (present and a whole number). Ollama's absent-is-0 count and
    Anthropic's absent-or-null-is-0 cache count stay in their adapters, built on `whole_number`.
  - `app/providers/http_body.py`: `async def post_json(client, path, *, body, headers, max_response_bytes) ->
    JsonReply`, where `JsonReply` is a `NamedTuple` of `payload: object` and `status_code: int`. It makes one
    `POST` of `body` as JSON through `client.stream`, reads the status first, maps a non-2xx to `rate_limited`
    (429) or `upstream_status` without reading its body, reads a 2xx body with `read_capped`, and parses it as
    UTF-8 JSON. A timeout is checked before `httpx.TransportError`, then `httpx.DecodingError`; invalid UTF-8,
    invalid JSON, an empty body and deep nesting are `bad_response`. Every `ProviderError` is raised outside
    its `except` block. `headers` may be `None` (Ollama sends none).
  - The OpenAI and Anthropic adapters call `post_json` and the `fields` checks; their own `_text`,
    `_non_empty_text`, `_whole_number`, `_required_count`, `_status_error`, `RATE_LIMITED_STATUS`, `json`
    import and exception handling are removed. No behaviour changes.
  - Behaviour change, on a line of its own: the Ollama adapter moves onto `post_json` and `fields.text` too, so
    its errors no longer carry a suppressed `__context__` (today it raises `from None` inside its `except`
    blocks; T-205 known gap 1).
  - `docs/ARCHITECTURE.md`: `fields.py` in the `app/providers/` layout and `post_json` beside `read_capped`.
- **Contract:** unchanged. No response, header or field changes, and the snapshot does not change.
- **Acceptance criteria:**
  1. Pure refactor for OpenAI and Anthropic: every existing test in `tests/test_openai_provider.py`,
     `tests/test_app_openai.py`, `tests/test_anthropic_provider.py` and `tests/test_app_anthropic.py` passes
     unchanged; the task's diff to those four files is empty.
  2. Ollama: every existing test in `tests/test_ollama_provider.py` and `tests/test_app_ollama.py` passes
     unchanged (the diff to them only adds tests). New tests show that every Ollama failure, namely a timeout,
     a connection error, a corrupt gzip body, invalid JSON, a lone surrogate in the reply and a body above
     `max_response_bytes`, is a `ProviderError` whose `__context__` and `__cause__` are `None`.
  3. `fields`, tested directly (`tests/test_provider_fields.py`, new): `text` accepts `""` and non-ASCII text
     and rejects a non-string (`None`, an int, a list) and a lone surrogate; `non_empty_text` also rejects
     `""`; `whole_number` accepts 0 and a large int and rejects -1, `True`, `False`, `1.0`, `1.5`, `"1"` and
     `None`; `required_count` rejects an absent key and a present -1 or `True`, and returns a present valid
     count. Every rejection is `bad_response` with the given status, which the tests set to 201 so that a
     check raising with 200 fails, and has no `__context__`.
  4. `post_json`, tested directly through `httpx.MockTransport` (`tests/test_http_body.py`): the request is one
     `POST` to the path with exactly the JSON body and the given headers, and with `headers` set to `None`
     it carries only httpx's default headers, the same set as a call that passes no headers; a 2xx returns the
     parsed payload with its status (200, 201 and 299); 429 is `rate_limited`, 500 and 529 are retryable
     `upstream_status`, 400 and 404 non-retryable, and none of their bodies is read (a corrupt gzip body does
     not turn them into `bad_response`); a redirect is not followed; each timeout type is `timeout` and other
     transport errors are `connection`; a corrupt gzip 2xx, invalid UTF-8, invalid JSON, an empty body, deep
     nesting and a body above the limit are `bad_response` with the reply's status, each tested on a 201 reply
     as well as a 200. No error holds the body, the URL or a header value, and none has a `__context__`.
  5. Each adapter forwards the reply's status (`tests/test_adapter_wiring.py`, new): for each of the three
     adapters, a 201 reply that is valid JSON but cannot be translated (`{}`, and a valid reply with an
     unknown finish reason) is `bad_response` with status 201.
  6. No adapter repeats the shared code: an AST test in `tests/test_adapter_wiring.py` shows that
     `ollama.py`, `openai.py` and `anthropic.py` contain no `ast.Try` or `ast.TryStar` node, no `json`
     import, no function named `_text`, `_non_empty_text`, `_whole_number`, `_required_count` or
     `_status_error`, no name `RATE_LIMITED_STATUS`, and that each imports `post_json`.
  7. `python scripts/check.py` is green, and the OpenAPI snapshot is unchanged.
- **Verification:** `python scripts/check.py` green; mutation table, listed before the first run, with a kill
  test named for each mutant: in `fields`, `text` accepting a non-string, `text` rejecting `""`, the
  surrogate check dropped, the surrogate error raised inside its `except`, `non_empty_text` accepting `""`,
  `whole_number` using `isinstance` (accepting a bool), accepting -1, accepting a float, rejecting 0,
  `required_count` treating an absent key as 0, `required_count` skipping `whole_number` on a present value,
  and each check raising with 200 instead of the given status; in `post_json`, 429 mapped to
  `upstream_status`, the timeout checked after `TransportError`, the `DecodingError` branch removed, each of
  the timeout, connection, decoding and JSON branches raising inside its `except` (four mutants),
  `RecursionError` removed from the JSON `except`, `ValueError` narrowed to `json.JSONDecodeError`, each
  `bad_response` branch raising with 200 instead of the reply's status, the body read before the status,
  `aread()` in place of `read_capped`, the status returned as 0 or 200 instead of the reply's, `headers`
  dropped (killed by the OpenAI and Anthropic key tests as well as the direct test),
  `follow_redirects=True`; in the adapters, each adapter passing a fixed 200 to its translation instead of the
  reply's status, each passing the default instead of its configured `max_response_bytes` (killed by the
  existing cap tests), each passing another adapter's path, and the Ollama adapter still raising inside an
  `except` (its old body restored). Run the batches one at a time with a per-run timeout; `gh pr checks <n>
  --watch`.
- **Branch and commits:** `refactor/t-210-shared-adapter-code`; `refactor(providers): share the reply checks
  and request handling of the OpenAI and Anthropic adapters` (the two helpers, their tests, the two adapters,
  the ARCHITECTURE line; no existing test changes), `fix(providers): raise the Ollama adapter's errors without
  a context` (the Ollama adapter on the shared code, its added context tests and
  `tests/test_adapter_wiring.py`, whose AST test fails until Ollama has moved),
  `docs(tasks): complete T-210`.
- **Size:** about 600 changed lines: production about 85 added and 145 removed (the code shrinks by about
  60 lines), tests about 360 added, docs about 10. Above the ~400-line plan threshold; the owner approves
  the size with this card. T-205 and T-206 both ran past their estimates, mostly in tests.

### T-301 - Embedders: the interface, the hashing baseline and the Ollama embedder

- **Status:** done
- **Goal:** the cache has embedders to call: a deterministic hashing baseline for tests and the eval harness, and
  an Ollama embedder tested only through `httpx.MockTransport`. Nothing in the request path uses them yet.
- **Context:** ADR-0013, ADR-0015, `app/providers/http_body.py`, `app/providers/errors.py`,
  `app/providers/ollama.py` (the adapter pattern), `tests/test_ollama_provider.py`, `tests/test_http_body.py`.
- **Depends on:** the Phase 2 gate (signed off); ADR-0014 and ADR-0015 accepted (2026-11-21).
- **Deliverables:**
  - `app/cache/__init__.py` and `app/cache/embedder.py`: an `Embedder` protocol with an `identity` string and
    `async def embed(self, text: str) -> array[float]`, which returns a unit vector; and `EmbeddingError(kind,
    status_code)`, using the `ProviderErrorKind` values, with a message built from the kind and the status only.
  - `app/cache/hashing.py`: `HashingEmbedder` as ADR-0015 says. The text is lower-cased and padded with one space
    at each end. Each 3-character window is hashed with `hashlib.blake2b(digest_size=8)` to an index modulo 512
    and counted, and the counts are L2-normalised. The identity is `hashing:v1`. A text with no window (the empty
    string) raises `EmbeddingError("bad_response", None)`.
  - `app/cache/ollama_embedder.py`: `OllamaEmbedder(client, model, *, max_response_bytes=1_048_576)` as ADR-0015
    says, posting through `post_json` and turning each `ProviderError` into an `EmbeddingError` with the same
    kind and status. The `EmbeddingError` is raised after the `except` block, so it has no `__context__`. The
    identity is `ollama:<model>`.
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. Hashing: the same text gives the same vector from two instances, and one fixed input gives a pinned list
     of non-zero indices and counts, so a change of hash, window or dimension fails. The length is 512 and the
     norm is 1 within 1e-12. Upper and lower case give the same vector, two different texts give different
     vectors, and the empty string raises.
  2. Ollama request translation is exact: one `POST /api/embed` per call, with the body exactly `{"model": <model>,
     "input": <text>, "truncate": false}`.
  3. Ollama reply: one vector is returned normalised (a reply of `[3, 4]` gives `[0.6, 0.8]`). Each of these
     gives `bad_response` with the status: a body that is not an object; `embeddings` missing, not a list, empty
     or holding two vectors; an empty vector; an element that is a bool, a string or null; `NaN` or `Infinity`
     (which `json.loads` accepts); an integer too large for a float (a 400-digit number, which must not escape
     as an `OverflowError`); a zero vector; a vector whose norm `math.sqrt(math.sumprod(v, v))` is not finite
     (`[1e308, 1e308]`); a later reply whose length differs from the first reply's; invalid JSON; and a body
     of 1,048,577 bytes. A body of exactly 1,048,576 bytes is read.
  4. Ollama failures: a connection error gives `connection`, a timeout `timeout`, 429 `rate_limited`, and 400
     (the over-long input), 404 and 500 give `upstream_status` with that status. No message contains the reply
     body, the text or the URL, and no `EmbeddingError` has a `__context__`.
- **Verification:** `python scripts/check.py` green; mutation table (`truncate` true or left out, `input` sent as a
  list, the reply not normalised again, a zero vector accepted, `NaN` or a bool accepted, the `float()`
  conversion moved outside the guard (the huge integer escaping), the norm taken with `math.hypot`, the first of two
  vectors taken, the length check skipped or compared with the latest reply instead of the first, the size cap
  removed or moved by one, the reply body in a message, a `__context__` kept, the hash replaced by Python's
  `hash()`, case kept, the dimension changed from 512, the hashing normalisation dropped); `gh pr checks <n>
  --watch`.
- **Branch and commits:** `feat/t-301-embedders`; `feat(cache): add the embedder interface and the hashing
  baseline`, `feat(cache): add the Ollama embedder`, `docs(tasks): complete T-301`.
- **Size:** about 400 lines, most of them reply and failure cases. At the limit, so the plan goes to the owner if
  it runs over.

### T-302 - Cache settings

- **Status:** done
- **Goal:** the cache settings are read and validated at startup. With the cache on, `create_app()` builds the
  Ollama embedder on its own client, which is closed at shutdown. Nothing in the request path uses it yet.
- **Context:** ADR-0014, ADR-0015, `app/settings.py`, `app/main.py`, `tests/test_settings.py`,
  `tests/test_app_wiring.py`, `docs/setup.md`.
- **Depends on:** T-301.
- **Deliverables:**
  - `Settings.cache: CacheSettings | None`, which is `None` when `TOLLGATE_CACHE_EMBEDDER` is unset.
    `CacheSettings` holds `embedder` (`"ollama"`), `embedder_model`, `embedder_url` (a `SecretStr`),
    `similarity_threshold` (a float), `ttl_seconds` and `max_entries`. The rules are:
    - `TOLLGATE_CACHE_EMBEDDER` is exactly `ollama`.
    - `TOLLGATE_CACHE_EMBEDDER_MODEL` is required and must not be blank. It is stripped.
    - `TOLLGATE_CACHE_EMBEDDER_URL` is optional and defaults to `http://localhost:11434`. Set but blank is an
      error.
    - `TOLLGATE_CACHE_SIMILARITY_THRESHOLD` is required. It must match `0\.[0-9]{1,4}`, `1` or `1\.0{1,4}` and
      be at least 0.5.
    - `TOLLGATE_CACHE_TTL_SECONDS` is a whole number from 60 to 604,800, default 3,600.
    - `TOLLGATE_CACHE_MAX_ENTRIES` is a whole number from 1 to 100,000, default 1,000.
    - Any other `TOLLGATE_CACHE_*` variable above that is set while `TOLLGATE_CACHE_EMBEDDER` is unset is an
      error naming that variable, so a half-configured cache never starts silently off.
    - Every error is a `SettingsError` naming the variable, with a fixed reason and never a value.
  - With the cache on, `create_app()` builds an `httpx.AsyncClient` with the URL, a 5-second connect timeout and
    10 seconds for reads, writes and the pool, using the `http_transport=` transport. It appends the client to
    `app.state.owned_clients` and keeps an `OllamaEmbedder` on `app.state.embedder`, which is `None` when the
    cache is off. A new `embedder=` keyword lets tests inject one, and then no client is built. Passing
    `embedder=` while the cache is off raises `ValueError`, so a test cannot believe it exercises a cache that
    is not there.
  - `docs/setup.md`: the variables and their rules.
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. With `TOLLGATE_CACHE_EMBEDDER` unset: `cache` is `None`, `app.state.embedder` is `None`, no client is added,
     and every existing test passes unchanged.
  2. A complete valid set loads the exact values. With the optional variables unset, the defaults apply: TTL
     3,600, 1,000 entries and the default URL.
  3. Each of these fails with a `SettingsError` naming its variable and holding no value:
     - The embedder is `redis`, `Ollama` or blank.
     - The model is unset or blank, or the URL is blank.
     - The threshold is unset, blank, `0.4999`, `1.0001`, `0.12345`, `.9`, `1e0`, `-0.9`, `nan`, or uses
       non-ASCII digits.
     - The TTL is 59, 604,801, `abc` or blank.
     - The maximum is 0, 100,001 or blank.
     - A cache variable is set while the embedder is unset.

     The boundaries are accepted: a threshold of `0.5`, `0.9999`, `1` or `1.0000`; a TTL of 60 or 604,800; a
     maximum of 1 or 100,000.
  4. With the cache on, the client has the URL and the timeouts above, opens no connection, and is closed at
     shutdown. With an injected embedder, no client is built. `embedder=` with the cache off raises.
  5. The URL never appears in a `repr` or an error.
- **Verification:** `python scripts/check.py` green; mutation table (each threshold bound moved, five decimal
  places accepted, each TTL and maximum bound moved by one, each default changed, a blank URL falling back to the
  default, a cache variable set without the embedder ignored, the client not registered for shutdown, the
  connect and read timeouts swapped, the URL in a message, a blank TTL or maximum taking the default,
  `embedder=` accepted with the cache off); `gh pr checks <n> --watch`.
- **Branch and commits:** `feat/t-302-cache-settings`; `feat(settings): read and validate the cache settings`,
  `feat(app): build the Ollama embedder when the cache is on`, `docs(tasks): complete T-302`.
- **Size:** about 320 lines.

### T-303 - In-memory semantic cache

- **Status:** done
- **Goal:** one class implements ADR-0014's partition, lookup, store, expiry and eviction. It is unit-tested with
  fake embedders and the fake clock, and the route does not use it yet.
- **Context:** ADR-0014, ADR-0015, `app/cache/`, `app/api/models.py`, `app/clock.py`, `tests/fakes.py`.
- **Depends on:** T-301, T-302.
- **Deliverables:**
  - `app/cache/semantic.py`:
    - `partition_key(caller_id, request, embedder_identity) -> str`, as ADR-0014 says. It hashes the request's
      `model_dump(mode="json")` with the last message's content removed, together with the caller id and the
      embedder identity, as `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=True)`, and returns
      the SHA-256 hex digest of that ASCII text.
    - `InMemorySemanticCache(embedder, clock, *, similarity_threshold, ttl_seconds, max_entries)`.
      `async lookup(caller_id, request)` returns one of three results:
      - `Hit(response, provider_name, similarity)`
      - `Miss(ticket)`, where the ticket holds the partition key and the vector for a later store
      - `Skip()`, when the request is not eligible or the embedder failed

      `store(ticket, response, provider_name) -> bool` stores only a response with exactly one choice whose
      finish reason is `stop` and whose `model_dump_json()` is at most 65,536 bytes in UTF-8. It keeps those
      bytes, not the model, and a hit validates them back into a `ChatResponse`. Vectors are kept as
      `array("d")`, and a lookup scans only its own partition.
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. Partition: two requests that differ only in the last message's content share a key. A change in any one of
     these gives a different key: the caller id, `model`, `max_completion_tokens`, `max_tokens`, `temperature`,
     `n`, `stream` (absent against `false`), `user`, an earlier message's role, content or name, the last
     message's name, or the embedder identity. One fixed request gives a pinned key, so the canonical form
     cannot drift. A lone surrogate (`"\ud800"`) in `user`, in an earlier message's `name` or in `model` gives a
     key without raising.
  2. Messages `[user, assistant]` and `[user, system]` give a `Skip`, and the embedder is not called; messages
     `[system, user]` and `[assistant, user]` are looked up.
  3. The threshold is exact: with fixed vectors, a similarity exactly equal to the threshold hits (`(1, 0)` against
     `(0.75, y)` at 0.75), and one just below it (`0.7499999999999999`) misses. The hit reports that similarity.
  4. Of two entries above the threshold, the more similar wins. At equal similarity the more recently stored
     wins.
  5. An identical vector in another partition (another caller) never hits.
  6. An entry hits 0.001 seconds before `stored_at + ttl_seconds` and misses at exactly that time; a hit does not
     extend its life.
  7. Eviction at `max_entries`: an expired entry goes first, even when it was used more recently than a live
     one (with a maximum of 2, store A, store B a little later, hit A, move the clock to where A has expired and
     B has not, store C, and B remains while A is gone; plain LRU would have evicted B).
     Otherwise the least recently used goes, where a hit counts as a use: with a maximum of 2, store A and B, hit
     A, store C, and B is gone. The count never passes the maximum.
  8. A `length` or `content_filter` answer is not stored, nor one with zero or two choices; a body of exactly
     65,536 bytes is stored and one of 65,537 is not, counted in UTF-8 (a body with non-ASCII text at the
     boundary).
  9. An `EmbeddingError` gives `Skip`; any other exception from the embedder propagates.
- **Verification:** `python scripts/check.py` green; mutation table (`>=` changed to `>`, the tie broken by the
  oldest entry, each partition field left out in turn (`stream` included), `ensure_ascii=False`, the size
  counted in characters instead of UTF-8 bytes, two choices accepted, the last content kept in the key, the
  role check removed or applied to the first message, expiry `>=` changed to `>`, a hit extending the life, FIFO instead of LRU,
  expired entries not evicted first, the size cap moved by one, a `length` answer stored, an `EmbeddingError`
  propagated, every exception caught, the scan reaching other partitions); `gh pr checks <n> --watch`.
- **Branch and commits:** `feat/t-303-semantic-cache`; `feat(cache): add the in-memory semantic cache`,
  `docs(tasks): complete T-303`.
- **Size:** about 400 lines: about 150 of production code and 250 of tests. At the limit, so the plan goes to
  the owner if it runs over.

### T-304 - Cache eval harness and its dataset

- **Status:** done
- **Goal:** one run measures the real cache's hit rate and wrong-hit rate on a fixed dataset of labelled prompt
  pairs, at every threshold from 0.50 to 1.00, and reports its settings. CI runs it with the hashing baseline
  (the Phase 3 requirement in "Later phases").
- **Context:** ADR-0014, ADR-0015, `app/cache/`, `scripts/check.py`, "Requirements that carry into the task
  cards" below.
- **Depends on:** T-303.
- **Deliverables:**
  - `eval/cache_pairs.json`: 80 pairs of English text written for this project, 40 `same` and 40 `different`.
    Each pair has an `id`, a `category`, `first`, `second` and a `label`. The `different` pairs have 8 in each of
    five categories: unrelated topic, negation, changed number, swapped direction or order, and changed entity.
    The `same` pairs are rewordings of varied kinds. The owner reviews the pairs in the pull request.
  - `app/cache/evaluation.py`:
    - `evaluate(pairs, embedder, clock) -> EvalReport` runs each pair through its own new
      `InMemorySemanticCache`, with a threshold of 0.5 and a single entry. It stores an answer for `first` and
      looks up `second`, both as a one-message request with a fixed model and caller.
    - The `Hit` similarity places the pair: it hits at every threshold up to that similarity, and a miss at 0.5
      misses at every threshold. This is exact under the cache's own `>=` rule.
    - A `Skip` on either the store's lookup or the second lookup stops the run with an error, and no report or
      recommendation is produced (ADR-0014).
    - The report holds the hit rate on `same` pairs and the wrong-hit rate on `different` pairs at each threshold
      `i / 100` for `i` from 50 to 100 (51 rows), with the wrong hits per category.
    - The recommended threshold is the lowest below 1.00 with no wrong hit, or none (ADR-0014).
  - `scripts/eval_cache.py`:
    - Options: `--embedder hashing|ollama`, `--model` and `--url` for Ollama, and `--output` for a JSON copy of
      the report.
    - It prints a Markdown report with the settings, the table and the recommendation. The settings are the date,
      the embedder identity, the dataset's SHA-256, the pair counts and, for Ollama, the version from
      `GET /api/version`. The URL is never printed.
  - `docs/cache-eval.md`: the method, how to run it, and the hashing baseline from a recorded local run with its
    settings, labelled as lexical, not semantic.
  - ARCHITECTURE section 5: `eval/`, `app/cache/evaluation.py` and `scripts/eval_cache.py` in the layout.
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. A test checks the dataset: exactly 80 pairs, 40 `same` and 40 `different`, 8 in each `different` category,
     unique ids, and no empty text.
  2. On a hand-made dataset with fixed vectors, the hit rate, the wrong-hit rate and the per-category counts are
     exact. A pair whose similarity equals a threshold counts as a hit at that threshold, including one whose
     similarity is exactly `float("0.57")`, which `0.5 + 7 * 0.01` would miss by one unit in the last place, and
     the 51 thresholds equal `[i / 100 for i in range(50, 101)]` exactly.
     An embedder that fails on one pair stops the run, and nothing is reported.
  3. The recommendation is the lowest threshold below 1.00 with no wrong hit. It is none when only 1.00, or no
     threshold, has zero wrong hits.
  4. The whole dataset runs with the hashing embedder in the test suite, with no network, and the report has 51
     rows and every setting.
  5. With `--embedder ollama` on an `httpx.MockTransport`, the script calls `/api/version` and `/api/embed`, and
     its output does not contain the URL.
  6. `docs/cache-eval.md` records the hashing baseline from a local run, with its settings.
- **Verification:** `python scripts/check.py` green; mutation table (`>=` changed to `>` when placing a pair, the
  hit rate divided by every pair, wrong hits counted on `same` pairs, the sweep missing 0.50 or 1.00, the
  recommendation taking the highest threshold or allowing 1.00, one cache shared by every pair, the URL printed,
  a `different` category miscounted, a `Skip` counted as a miss, the thresholds built by adding 0.01 in a loop);
  `gh pr checks <n> --watch`.
- **Branch and commits:** `feat/t-304-cache-eval`; `feat(eval): add the cache eval dataset`, `feat(eval): add the
  cache eval harness`, `docs(eval): record the hashing baseline`, `docs(tasks): complete T-304`.
- **Size:** about 380 hand-written lines of code, tests and docs, plus the dataset (about 330 lines of JSON).

### T-305 - Build the cache in the app and share the id source

- **Status:** done
- **Goal:** with the cache on, the app holds one `InMemorySemanticCache` built from the settings, on the injected
  clock, and the shared id source is on the app state, so the route can use both. No request uses the cache yet.
- **Context:** ADR-0014, ADR-0015, `app/main.py`, `app/providers/ids.py`, `app/cache/`, `tests/test_app_wiring.py`,
  `tests/test_chat_routing.py` (its direct `build_providers(table, FakeClock())` call),
  `tests/test_app_anthropic.py` (its monkeypatch of `app.main.UuidIdSource`).
- **Depends on:** T-303, T-304: the harness exists before the cache is built into the app.
- **Deliverables:**
  - `create_app()` builds one `UuidIdSource`, keeps it on `app.state.id_source` and passes it to
    `build_providers`, which gains a keyword `id_source: IdSource | None = None` and builds a new `UuidIdSource`
    inside the function when it is `None` (never a default evaluated once at import), so existing direct calls
    keep working. Every provider the app builds uses that one source.
  - With the cache on, `create_app()` builds an `InMemorySemanticCache` on the embedder (built or injected,
    T-302), the injected clock, and the threshold, TTL and maximum from `Settings.cache`, and keeps it on
    `app.state.cache`. With the cache off, `app.state.cache` is `None`.
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. Every existing test passes unchanged, including the direct `build_providers` call.
  2. The app's mock, Ollama and Anthropic providers share the source on `app.state.id_source` (a monkeypatched
     `app.main.UuidIdSource`, as in `tests/test_app_anthropic.py`, shows one instance).
  3. With the cache on, `app.state.cache` uses the injected clock and the embedder, and the settings' values,
     each pinned from both sides: an entry still hits just before the TTL and misses at it; a similarity at the
     threshold hits and one just below it misses; storing exactly the maximum evicts nothing and one more
     evicts. With the cache off it is `None`.
- **Verification:** `python scripts/check.py` green; mutation table (a second id source built for the
  providers, the system clock given to the cache, the threshold, TTL or maximum taken from a constant instead
  of the settings, the cache built while the cache is off); `gh pr checks <n> --watch`.
- **Branch and commits:** `feat/t-305-cache-wiring`; `refactor(app): keep the shared id source on the app
  state`, `feat(app): build the semantic cache from the settings`, `docs(tasks): complete T-305`.
- **Size:** about 200 lines.

### T-306 - Semantic cache on chat completions

- **Status:** done
- **Goal:** the chat route looks up the cache after the reservation. A hit is answered from the cache with a full
  refund, a `stop` answer is stored after a miss, and every 200 says which happened.
- **Context:** ADR-0007, ADR-0011, ADR-0014, ADR-0015, `app/api/chat.py`, `app/main.py`, `app/cache/`,
  `tests/test_chat_rate_limits.py`, `tests/test_chat_routing.py`, `tests/test_chat_completions.py`,
  `tests/test_chat_openapi.py`, ARCHITECTURE sections 2, 3 and 5.
- **Depends on:** T-305.
- **Deliverables:**
  - The route, after an allowed reservation:
    - With the cache on (`app.state.cache`), it looks up the request under the caller id.
    - A hit settles once with an actual amount of 0 and answers the stored response, with a new `id` from
      `app.state.id_source` and `created` from the clock. It carries the limit headers, `x-tollgate-provider`
      set to the stored provider, `x-tollgate-fallbacks: 0` and `x-tollgate-cache: hit`.
    - A miss runs the route. A 200 is then offered to `store`, and the response carries `x-tollgate-cache: miss`.
    - A skip, or the cache off, runs the route, and a 200 carries `x-tollgate-cache: skip`.
    - Nothing else changes: the 400, 401, 404, 429 and 502 paths are as today.
  - The OpenAPI document records `x-tollgate-cache` on 200 with its three values, and the descriptions of
    `x-tollgate-provider` and `x-tollgate-fallbacks` say what they mean on a hit (ADR-0014). In
    `tests/test_chat_openapi.py` the exact 200 header set gains `x-tollgate-cache`. The snapshot is regenerated
    in the route commit.
  - ARCHITECTURE: section 2 says a hit settles 0. Section 3 replaces the illustrative `SemanticCache` with the
    final `SemanticCache`, `Hit`, `Miss`, `Skip`, `Embedder` and `EmbeddingError`. Section 5 adds `app/cache/`
    and the cache to the chat-route paragraph.
- **Contract:** changes (one header on 200, two header descriptions); the snapshot is regenerated in the route
  commit.
- **Acceptance criteria:**
  1. With the cache off, every behavioural test in `tests/test_chat_rate_limits.py`, `tests/test_chat_routing.py`
     and `tests/test_chat_completions.py` passes unchanged. Each 200 carries `x-tollgate-cache: skip`, and no
     embedder is called.
  2. A miss, then a hit (a fake embedder with fixed vectors and a fixed id source):
     - The first request is a `miss`, served by the second target of its route after one retryable failure.
     - The second is a `hit`, and no provider is called again.
     - On the hit, `model`, `choices` and `usage` equal the stored answer's, the `id` is the id source's next id,
       and `created` is the clock's time at the hit, which has moved since the miss.
     - On the hit, `x-tollgate-provider` names the second target (the one that produced the answer), and
       `x-tollgate-fallbacks` is `0`, while the miss carried `1`.
  3. A hit makes one reserve and one settle with an actual amount of 0, and a follow-up request shows the balance
     unchanged by the hit.
  4. A 429 for a cached prompt, a 404 and a 400 never call the embedder.
  5. After a `length` answer, the next similar request is a `miss` again. A 502 stores nothing.
  6. An embedder failure gives a 200 with `skip`, served by the provider, and nothing is stored: the next similar
     request, with the embedder working, is a `miss` and the provider is called.
  7. `x-tollgate-cache` is absent on 400, 401, 404, 429 and 502.
  8. Another caller sending the same prompt gets a `miss`.
  9. Through the whole app, with a route table and one `httpx.MockTransport` answering both `/api/embed` and
     `/api/chat`, an Ollama route with the Ollama embedder serves a miss and then a hit.
- **Verification:** `python scripts/check.py` green; mutation table:
  - order and cost: the lookup moved before the reservation, a hit settling the stored usage or the reservation,
    a hit calling the provider
  - the hit response: the `id` or `created` kept from the stored answer, the fallback count copied from the miss,
    the provider taken from the route's first target
  - what is stored: a `length` answer, after a 502, after a skip
  - the header: on a 400, 401, 404, 429 or 502, a `skip` reported as `miss`
  - failure and scope: an embedder failure turned into a 500, a constant in place of the caller id

  Then `gh pr checks <n> --watch`.
- **Branch and commits:** `feat/t-306-cache-on-chat`; `feat(api): answer chat completions from the semantic
  cache` (with the regenerated snapshot), `docs(architecture): describe the semantic cache`,
  `docs(tasks): complete T-306`.
- **Size:** about 400 lines plus the snapshot diff. It is the card most likely to run over, so its plan goes to
  the owner if it does.

### T-307 - The owner's eval run, the recommended threshold and the cache guide

- **Status:** done
- **Goal:** the threshold the docs recommend comes from a recorded eval run against a local embedding model, and
  the owner can turn the cache on by hand.
- **Context:** ADR-0014, ADR-0015, `docs/setup.md`, `docs/cache-eval.md`, `scripts/eval_cache.py`.
- **Depends on:** T-304, T-306.
- **Deliverables:**
  - An OWNER-CHECK: the owner pulls `all-minilm` (or `bge-m3`) into a local Ollama and runs
    `scripts/eval_cache.py --embedder ollama --model <model>`. The report goes into `docs/cache-eval.md`, and the
    Log records a summary. The report holds the Ollama version, the model, the dataset digest, the date, the
    table, and the recommended threshold or none. A second model is optional.
  - `docs/setup.md`: turning the cache on. It covers the variables, the threshold from the recorded run, what each
    header value means, what a hit costs, the limits, that a threshold of `1` may never hit, and that each
    process has its own cache. If the run found no usable threshold, or the owner waived it, the guide says that
    no threshold is recommended.
  - An optional OWNER-CHECK: a gateway run with the cache on, with a `miss` and then a `hit` seen in the headers.
    It is recorded in the Log or marked "not run".
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. OWNER-CHECK: the eval run is recorded in `docs/cache-eval.md` and the Log, with its settings, or the owner
     waives it in writing.
  2. The threshold in `docs/setup.md` equals the recorded run's recommendation for that model, or the guide says
     that none is recommended.
  3. A search finds no key or real secret in any committed file.
- **Verification:** `python scripts/check.py` green. No test is added, so there is no mutation table, and the
  report says so. `gh pr checks <n> --watch`.
- **Branch and commits:** `docs/t-307-cache-guide`; `docs(eval): record the owner's eval run`, `docs(setup): add
  the cache guide`, `docs(tasks): complete T-307`.
- **Size:** about 120 lines.

### T-401 - Request timing, route attempts and the reason for a skip

- **Status:** done
- **Goal:** the code reports what each request did, timed on a monotonic clock: each target tried, with its
  outcome and duration, whether a reply passed the size cap, and why a lookup was skipped. Nothing is logged or
  exported yet.
- **Context:** ADR-0010, ADR-0013, ADR-0014, ADR-0016, `app/clock.py`, `app/providers/errors.py`,
  `app/providers/http_body.py`, `app/routing/router.py`, `app/cache/semantic.py`, `app/api/chat.py`,
  `app/main.py`, `tests/fakes.py`, `tests/test_router.py`, `tests/test_http_body.py`,
  `tests/test_semantic_cache.py`, ARCHITECTURE section 3.
- **Depends on:** the Phase 3 gate (signed off); ADR-0016, ADR-0017 and ADR-0018 accepted (2026-11-23).
- **Deliverables:**
  - `app/clock.py`: the `MonotonicClock` protocol (`monotonic_seconds() -> float`) and `SystemMonotonicClock`,
    which reads `time.perf_counter()`. `tests/fakes.py`: a `FakeMonotonicClock` that moves only when a test
    advances it, and a fake provider that advances it by a set step before it answers or raises.
  - `app/providers/errors.py`: `ReplyTooLargeError(ProviderError)`, always of kind `bad_response`, with the
    status. `read_capped` raises it in place of the plain `ProviderError` it raises today. Its message keeps the
    ADR-0010 form.
  - `app/routing/router.py`: `AttemptOutcome` (a `Literal` of `ok`, the five failure kinds, `reply_too_large` and
    `error`) and the frozen dataclass `Attempt(provider_name, outcome, duration_seconds)`. `run_route` takes a
    keyword `monotonic_clock` and times each provider call. `Served` and `RouteFailed` gain `attempts:
    tuple[Attempt, ...]`. Which target is tried, and what is charged or refunded, do not change.
  - `app/cache/semantic.py`: `Skip` gains `reason: Literal["not_eligible", "embedder_failed"]`.
  - `create_app()` takes `monotonic_clock: MonotonicClock | None = None`, builds a `SystemMonotonicClock` when it
    is `None`, and keeps it on `app.state.monotonic_clock`. The chat route passes it to `run_route`.
  - ARCHITECTURE section 3 adds `MonotonicClock`, `Attempt`, `ReplyTooLargeError` and the `reason` of `Skip`.
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. Every existing behavioural test passes. An existing test changes only to pass the new argument, to name a
     `Skip` reason, or, where it compares a whole `RouteFailed` or `Served` with `==` (as
     `tests/test_router.py` does), to compare `charged` or the served fields and `attempts` explicitly.
  2. On a three-target route whose first target times out and whose second answers 503, the third answers.
     `attempts` is exactly `timeout`, `upstream_status` and `ok`, with the provider names in route order and each
     duration equal to what the fake providers advanced the fake monotonic clock by.
  3. Every outcome is pinned by its own case: `ok`, `connection`, `timeout`, `rate_limited`, `upstream_status`
     (both a retryable 500 and a 400 that ends the route), `bad_response` (invalid JSON), `reply_too_large`
     and `error` (a `RuntimeError`). A `RouteFailed` holds every attempt up to the one that ended the route.
  4. A reply over the cap raises `ReplyTooLargeError`. It is a `ProviderError` with kind `bad_response` and the
     reply's status, and the route still ends charged as reserved, as ADR-0013 says. Invalid JSON is not a
     `ReplyTooLargeError`.
  5. A request whose last message is not from the user gives `Skip("not_eligible")`, and an `EmbeddingError`
     gives `Skip("embedder_failed")`. Any other embedder exception still propagates.
  6. Durations follow the monotonic clock alone: with the wall `Clock` advanced and the monotonic clock still,
     every duration is 0, and the other way round each is the monotonic step.
- **Verification:** `python scripts/check.py` green; mutation table: a duration from the wall clock, or taken
  before the call; the outcome taken from the wrong attempt; `attempts` left empty at each of the three
  `RouteFailed` returns (a non-retryable failure, a non-`ProviderError` exception, the route running out of
  targets); the attempt that ended the route left out; `Served` without its `ok` attempt;
  `reply_too_large` reported as `bad_response`, by checking the base class first; `ReplyTooLargeError` not
  derived from `ProviderError`, which makes the route uncharged; the two skip reasons swapped;
  `SystemMonotonicClock` reading `time.time()`. Then `gh pr checks <n> --watch`.
- **Branch and commits:** `feat/t-401-request-timing`; `feat(providers): raise ReplyTooLargeError at the reply
  size cap`, `feat(routing): record each attempt on a monotonic clock`, `feat(cache): give each skip a reason`,
  `docs(tasks): complete T-401`.
- **Size:** about 450 lines, most of it tests, counted as formatted lines. Above the ~400-line plan threshold;
  the owner approves the size with this card.

### T-402 - Structured request log

- **Status:** done
- **Goal:** every HTTP request writes one JSON line holding the ADR-0016 fields and nothing else.
- **Context:** ADR-0008, ADR-0016, `app/main.py`, `app/api/chat.py`, `app/api/auth.py`, the T-401 types,
  `tests/test_chat_rate_limits.py`, `tests/test_chat_cache.py`, `tests/test_auth_raw_headers.py` (calling the
  ASGI app with hand-built scopes).
- **Depends on:** T-401.
- **Deliverables:**
  - `app/observability/__init__.py` and `app/observability/record.py`: `ChatRecord`, which the chat route fills
    on `request.state` as it goes. It holds the serving provider, the fallbacks, the cache result, the skip
    reason, the reserved and charged tokens, whether the settle was capped, the attempts and the lookup's
    duration. Each field stays `None` until its step has run.
  - `app/observability/middleware.py`: a pure ASGI middleware (not `BaseHTTPMiddleware`). It times each HTTP
    request on the monotonic clock and takes the status from `http.response.start`. Once the response has been
    sent it hands the result to its observers. The log is the first observer, and T-404 adds metrics. The
    middleware maps the path to `/v1/chat/completions`, `/health` or `/metrics`, and every other path to `other`,
    FastAPI's documentation routes included. A handler that raises before a
    response started is recorded as 500, and the exception propagates.
  - `app/observability/logs.py`: `JsonFormatter`, which writes ADR-0016's fields for `tollgate.request` and only
    `time`, `level`, `logger`, `message` and `exception_type` for any other logger, and the observer that writes
    to `tollgate.request`.
  - `deploy/logging.json`: the dictConfig file for `uvicorn --log-config`, sending `tollgate.request` and
    uvicorn's loggers to stdout through `JsonFormatter`.
  - `create_app()` adds the middleware, and turns FastAPI's native telemetry off.
  - ARCHITECTURE section 5 describes the record, the middleware and the log.
- **Contract:** unchanged (the snapshot test stays green).
- **Acceptance criteria:**
  1. The key set and values of the line are pinned for each case: a 200 `miss`, a 200 `hit`, a 200 `skip` with
     each reason, the cache off, a 400, a 401, a 404 for an unknown model, a 404 for an unknown path (`path`
     `other`), a 200 for `GET /openapi.json` (`path` `other`), a 429, a 502 after one fallback, and a 500 from a
     raising limiter. Durations come from the fake
     monotonic clock, and `time` is pinned by its format.
  2. A unique marker is placed in the prompt, the model, the API key, a header value, the query string and the
     client address of a hand-built ASGI scope. A second case makes the limiter raise an exception whose
     message holds a marker. With every logger in `deploy/logging.json` set up, no line from any logger
     contains a marker, the key's SHA-256 digest or the caller id. The 500's uvicorn-style record carries only
     `exception_type`.
  3. Each request writes exactly one line, which is valid JSON and pure ASCII, including with a provider name
     holding `"` and `\`. A unit test of `JsonFormatter` gives a field U+2028, U+0085 and a control character,
     and each comes out escaped on one line.
  4. An answer above the capacity logs `settle_capped: true` with `charged_tokens` equal to the capacity, and an
     answer at the capacity logs `false`.
  5. `deploy/logging.json` loads through `logging.config.dictConfig` in a test, and a record sent to
     `tollgate.request` then comes out through `JsonFormatter`.
  6. A raising handler still produces one line with status 500, and the exception still propagates.
  7. A test pins that FastAPI's native telemetry is turned off on the app.
  8. Sending the response body advances the fake monotonic clock, and the logged duration includes that step.
  9. Two requests interleaved on the event loop (one held inside its provider while the other completes) each
     log their own provider and tokens.
- **Verification:** `python scripts/check.py` green; mutation table: the model or the caller id added to the
  fields; the raw path in place of the mapped one; a served documentation route given its own path value; the
  duration from the wall clock; the record written at
  `http.response.start` instead of after the body (killed by criterion 8); the record kept on `app.state`
  instead of the request (killed by criterion 9); the raise path not logged, or logged twice; `ensure_ascii`
  turned off; the exception message or traceback written for another logger; the cap flag inverted; `cache`
  reported as `skip` when no lookup ran; telemetry left on. Then `gh pr checks <n> --watch`.
- **Branch and commits:** `feat/t-402-request-log`; `feat(observability): log one JSON record per request`,
  `build(deploy): add the uvicorn logging config`, `docs(tasks): complete T-402`.
- **Size:** about 600 lines, most of it tests. Above the ~400-line plan threshold; the owner approves the size
  with this card, and is told as soon as the draft passes it.

### T-403 - Metrics registry and the Prometheus text format

- **Status:** done
- **Goal:** a registry of counters and histograms, with no dependency, writes Prometheus text format 0.0.4
  exactly. Nothing in the app uses it yet.
- **Context:** ADR-0016 (the format rules it cites), `app/observability/`.
- **Depends on:** T-402, which creates `app/observability/`.
- **Deliverables:**
  - `app/observability/metrics.py`:
    - `Counter`, which declares its label names and its known label sets up front, and whose `inc(labels,
      amount)` rejects a negative or non-finite amount. A counter may name one label whose values are added on
      first use (ADR-0016 uses this for `status` only). Such a counter declares the allowed values of each of
      its other labels instead of complete label sets, and renders nothing for a set until its first use. Any
      label set outside what a counter declares is rejected.
    - `Histogram`, with fixed ascending buckets and `observe(labels, seconds)`, which rejects a non-finite value
      and an undeclared label set.
    - `MetricsRegistry`, whose `render() -> str` writes the text format. It rejects a duplicate metric name, a
      metric or label name outside the format's character sets, a label name starting with `__`, and `le` as
      a histogram label name.
    - The `CONTENT_TYPE` constant.
    - Samples are written in registration order, with label sets in declaration order and then, for the
      first-use label, in first-use order. Integers are written as integers, floats with `repr`, and infinity as
      `+Inf`.
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. A registry with one labelled counter and one labelled histogram renders a pinned string exactly: HELP and
     TYPE lines, samples, and the final line feed.
  2. Escaping: a label value holding `\`, `"` and a line feed, and HELP text holding `\` and a line feed, are
     each escaped as the format says, backslash first.
  3. Histogram buckets are cumulative. A value equal to a bound counts in that bucket (`le` means at most),
     `le="+Inf"` equals `_count`, and `_sum` is exact for binary-exact values.
  4. Declared label sets render at 0 before any use. A first-use value appears only after its first
     increment, and in first-use order.
  5. Each rejection above is pinned by a case, including, on a counter with a first-use label, a value of another
     label that was not declared. A `"` in HELP text is written as is, since HELP escapes only `\` and the line
     feed.
  6. Every line of a rendered registry with several metrics matches the format's line grammar, as checked by a
     small checker in the test, and every name has its TYPE line before its first sample.
- **Verification:** `python scripts/check.py` green; mutation table: `<` in place of `<=` at a bucket bound;
  buckets not cumulative; the `+Inf` bucket dropped; each escape dropped, and backslash escaped last; the final
  line feed dropped; TYPE written after the samples; a negative amount accepted; a non-finite amount accepted by
  `inc`, or a non-finite value by `observe`; a duplicate name, an invalid name, a `__` label or `le` on a
  histogram accepted; an undeclared label set accepted; an undeclared value of a counter's other label accepted
  next to a first-use label; `"` escaped in HELP text; declared label sets not
  pre-exported. Then `gh pr checks <n> --watch`.
- **Branch and commits:** `feat/t-403-metrics-registry`; `feat(observability): add a metrics registry with
  Prometheus text output`, `docs(tasks): complete T-403`.
- **Size:** about 400 lines, most of it tests.

### T-404 - Metrics on the app and the `/metrics` endpoint

- **Status:** done
- **Goal:** with a metrics token set, `GET /metrics` exports the ADR-0016 metric set for the app's own requests,
  and nothing else can read it.
- **Context:** ADR-0008, ADR-0016, `app/settings.py`, `app/main.py`, `app/api/auth.py`, `app/observability/`,
  `tests/test_settings.py`, `tests/test_chat_openapi.py`, `tests/test_openapi_snapshot.py`, `docs/setup.md`
  ("Configuration").
- **Depends on:** T-402, T-403.
- **Deliverables:**
  - `app/settings.py`: `TOLLGATE_METRICS_TOKEN`, optional. Set, it must not be blank, must be at least 32
    characters, and must differ from every API key, each failure being a `SettingsError` naming the variable.
    It is kept as a `SecretStr`.
  - `create_app()` builds one `MetricsRegistry` with the ADR-0016 set on `app.state.metrics`, declaring every
    label set ADR-0016 lists as known at startup, with `status` as the one first-use label. The middleware's
    second observer updates the registry from the request record.
  - `GET /metrics`, registered only when the token is set, with `include_in_schema=False`. It checks the bearer
    token as ADR-0016 says, answers with `CONTENT_TYPE`, and otherwise sends the 401 with code
    `invalid_metrics_token`.
  - `docs/setup.md` lists the variable. The full metrics guide is T-409.
  - ARCHITECTURE section 5 describes the registry and the endpoint.
  - Carried from T-403: the registry does not stop a metric named `x` from colliding with the series of a
    histogram named `x` (`x_bucket`, `x_sum`, `x_count`), and the text format allows one TYPE per name. When this task registers the ADR-0016 set, pick names so that
    no metric's name equals another metric's name plus one of those three suffixes, and add a test that
    checks the whole set for it. Also from T-403: the constructors accept a bare `str` where a sequence of
    strings is expected (`label_values`, `label_names`), which is read one character at a time, so pass
    tuples.
  - Carried from T-402: the request log writes `method` as the server received it, so it is unbounded. No
    ADR-0016 metric labels by `method`, and none may until `method` is mapped to a fixed set (the standard
    verbs, else `other`) first, because an unbounded label value makes the series count grow without limit.
- **Contract:** unchanged. The route is left out of the OpenAPI document, and a test pins that.
- **Acceptance criteria:**
  1. With the token unset, `/metrics` gets the app's ordinary 404.
  2. A blank token, a token of 31 characters, and a token equal to one of the API keys each fail startup with a
     `SettingsError` that names the variable and not the value. A token of 32 characters is accepted.
  3. These each get the metrics 401 (code `invalid_metrics_token`, `WWW-Authenticate: Bearer`): no header, a
     wrong token, an API key, the `Basic` scheme, two `Authorization` headers, and a header that is not valid
     UTF-8, sent through a hand-built ASGI scope. The metrics token on the chat route gets the chat 401.
  4. The right token gets 200 with the exact Content-Type. After a scripted sequence (a miss after one
     fallback, a hit, a skip with `embedder_failed`, a 429, a 404, a 502 from a reply over the cap, and a 200
     whose settle was capped), every counter in the set has the exact expected value. With the cache off, a
     200 is counted with `cache="off"`.
  5. A fresh app exports exactly the label sets ADR-0016 lists as known at startup, each at 0, and no
     `tollgate_http_requests_total` series until a request has been answered.
  6. A duration from the fake monotonic clock lands in the expected histogram bucket, and on a bound it lands in
     the bucket of that bound.
  7. Two apps built in one process have separate registries.
  8. The OpenAPI snapshot is unchanged, and `/metrics` is not in the document.
- **Verification:** `python scripts/check.py` green; mutation table: the route registered with the token unset;
  an API key accepted; the minimum length off by one; the API-key comparison removed; a module-level registry
  shared by apps; `include_in_schema` left on; a skip counted as a miss; the cache off counted as `skip`;
  `tollgate_settle_capped_total` not incremented; `tollgate_tokens_charged_total` fed the uncapped amount; the
  API-key 401 body sent in place of the metrics one. The constant-time comparison cannot be told apart by a
  test; the table lists it as reviewed, not mutated. Then `gh pr checks <n> --watch`.
- **Branch and commits:** `feat/t-404-metrics-endpoint`; `feat(settings): read the metrics token`,
  `feat(observability): export request metrics at /metrics`, `docs(tasks): complete T-404`.
- **Size:** about 550 lines, most of it tests. Above the ~400-line plan threshold; the owner approves the size
  with this card.

### T-405 - Container image, Compose stack and the CI container check

- **Status:** done
- **Goal:** `docker compose up` starts the gateway on Redis from a pinned, non-root image, and CI proves it on
  every pull request.
- **Context:** ADR-0006, ADR-0016, ADR-0017, `.github/workflows/ci.yml`, `app/main.py`, `deploy/logging.json`,
  `docs/routes.example.json`, `tests/test_routes_example.py`.
- **Depends on:** T-404.
- **Deliverables:**
  - `Dockerfile` and `.dockerignore`, as ADR-0017 says. The `.dockerignore` excludes everything with `*` and
    lists back only what the build copies.
  - `compose.yaml`, as ADR-0017 says, and `deploy/routes.compose.json`, a route table with the mock provider only.
  - `scripts/smoke_container.py`, standard library only. It sends:
    - `GET /health`, which must answer 200
    - a chat request with the key, which must answer 200 with `x-tollgate-provider`, `x-tollgate-cache: skip`
      and the limit headers
    - a chat request with no key, which must answer 401
    - `/metrics` with the token, which must answer 200 and count that chat 200
    - `/metrics` with no token, which must answer 401
    - Its checks are functions over a status, headers and a body, so they can be unit-tested.
  - A new job, `container`, in `ci.yml`:
    - a random key and token generated with Python's `secrets` and written to `$GITHUB_ENV`
    - hadolint (the `hadolint/hadolint` image pinned by digest)
    - `docker compose config --quiet`, then `docker compose build` and `docker compose up --wait`
    - the smoke script
    - a check that at least one `tollgate:bucket:*` key exists in Redis
    - a check that the gateway's logs hold a JSON line with `event` `http_request`
    - a check that `id -u` in the gateway is not 0
    - a check of the file list under the image's app directory (the route table is mounted at
      `/config/routes.json`, outside it)
    - `docker compose stop gateway`, after which uvicorn's "Application shutdown complete." is in the log and
      the container was not killed (its exit code is not 137). The exact exit code is recorded from the first
      run, since it depends on how uvicorn ends after a signal as PID 1.
    - `docker compose down`, run even when an earlier step fails
  - ARCHITECTURE: section 2's Operations row and section 5 (the image, the Compose stack, `deploy/`, and the
    one-host deployment target).
  - `tests/test_deploy_files.py` checks:
    - `deploy/routes.compose.json` loads through `Settings.from_env`
    - the Redis tag in `compose.yaml` equals the one in `ci.yml`
    - the `FROM` lines carry a digest
    - `compose.yaml` takes the key and the token only as `${...:?...}` references
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. The `container` job is green on the pull request with every step above.
  2. hadolint passes with no ignored rule, or each ignored rule is named with its reason in the `Dockerfile`.
  3. The image's app directory holds only `app/`, `deploy/logging.json` and the virtual environment. It holds no
     `.env*`, `.git`, `tests/`, `docs/` or local notes.
  4. The gateway runs as a non-root user, and stopping it runs the lifespan shutdown within the grace period.
  5. The pytest checks above pass, and each fails when its file is changed to break it.
  6. A search finds no key or real secret in any committed file, `ci.yml` included: the job's key and token
     exist only at run time.
  7. OWNER-CHECK (optional): the owner decides whether `container` becomes a required check in `protect-main`.
     The Log records the decision.
- **Verification:** `python scripts/check.py` green; the `container` job green; mutation table for the pytest
  tests and the smoke checks: a digest removed, the Redis tags made to differ, a key written literally in
  `compose.yaml`, a smoke check that accepts a 401 as 200, and one that ignores a missing header. The job's
  wiring is proven only by its run, so the first push is made early. Then `gh pr checks <n> --watch`.
- **Branch and commits:** `build/t-405-container`; `build(docker): add the gateway image`, `build(compose): add
  the compose stack`, `ci(container): build and smoke-test the image`, `docs(architecture): describe the image
  and the deployment target`, `docs(tasks): complete T-405`.
- **Size:** about 400 lines.

### T-406 - Fake upstream, benchmark route files and the fixed-rate runner

- **Status:** done
- **Goal:** load can be sent at a fixed arrival rate, with each request timed from its due time, against a fake
  upstream reached through the gateway's real `openai` adapter. The raw samples come out; the statistics and
  the report are T-407.
- **Context:** ADR-0005, ADR-0016 (the monotonic clock), ADR-0018, `app/clock.py`, `app/providers/openai.py`,
  `app/main.py` (`http_transport=`), `docs/routes.example.json`, `tests/test_routes_example.py`.
- **Depends on:** T-401.
- **Deliverables:**
  - `scripts/fake_upstream.py`: `build_app(delay_seconds, sleep)`, a Starlette app answering `POST
    /v1/chat/completions` with a fixed OpenAI-shaped body after `await sleep(delay_seconds)`. A `main` serves it
    with uvicorn, with the delay given in milliseconds and defaulting to 50.
  - `deploy/bench/routes.fake-upstream.json` (scenario B: one `openai` provider at the fake upstream's local
    address, its key named by `api_key_env`) and `deploy/bench/routes.mock.json` (scenario C: the mock provider).
  - `scripts/bench_load.py`, part one:
    - the schedule: request i is due at the start plus i divided by the rate
    - the runner, on an injected `MonotonicClock`, sleep function and `httpx.AsyncClient`. It sends each request
      as its own task with one fixed body, and returns per request the due time, the hand-over time, the end
      time, the status or the transport error, and whether it was a warm-up request. It also returns the peak
      number of requests in flight.
    - the client: no connection cap unless one is given
  - `tests/test_fake_upstream.py`, `tests/test_bench_runner.py`, and a test that loads both route files through
    `Settings.from_env` with placeholder values.
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. Request i is due at the start plus i divided by the rate. With integer settings, the number of requests is
     the rate times the warm-up plus the duration, exactly, and the first rate times warm-up requests are marked
     as warm-up.
  2. With a fake clock and a fake transport, a request handed over 5 ms after its due time that takes 10 ms has
     a due time, hand-over time and end time 0, 5 and 15 ms apart.
  3. Requests are sent without waiting for earlier answers: with every answer slower than the interval, each
     hand-over happens at its due time, and the peak in flight equals the expected overlap.
  4. A transport error and a non-200 are each returned with the request, never raised out of the runner.
  5. Through `create_app()` with `deploy/bench/routes.fake-upstream.json` and an `http_transport` of
     `httpx.ASGITransport` on the fake upstream, a chat request gets a 200, which proves that the adapter
     accepts the fake's body. The fake calls `sleep` once with the configured delay.
  6. Both route files load through `Settings.from_env`.
- **Verification:** `python scripts/check.py` green; mutation table: the due time computed from the previous
  answer instead of the schedule; requests awaited one after another (a closed loop, killed by criterion 3);
  the hand-over time taken after the response; warm-up marking off by one; a transport error raised out of the
  runner; the fake's delay ignored; a connection cap applied by default. Then `gh pr checks <n> --watch`.
- **Branch and commits:** `feat/t-406-load-runner`; `feat(bench): add a fake OpenAI-compatible upstream`,
  `feat(bench): send load at a fixed arrival rate`, `docs(tasks): complete T-406`.
- **Size:** about 450 lines, most of it tests. Above the ~400-line plan threshold; the owner approves the size
  with this card.

### T-407 - Load report: statistics, validity check and command line

- **Status:** done
- **Goal:** a run of the T-406 runner becomes a JSON report and a Markdown table with ADR-0018's figures,
  validity check and settings, started from the command line.
- **Context:** ADR-0005, ADR-0018, `scripts/bench_load.py`, `scripts/eval_cache.py` (the report style),
  `tests/test_cache_evaluation.py`.
- **Depends on:** T-406.
- **Deliverables:**
  - `scripts/bench_load.py`, part two:
    - the summary statistics: latency from the due time to the end, lag from the due time to the hand-over,
      `statistics.quantiles` with `method="inclusive"`, warm-up requests left out
    - the validity check and the 10,000-sample floor for a published p99, as ADR-0018 says
    - the JSON report and the Markdown table, with every setting ADR-0018 lists
    - the command line: `--url`, `--api-key-env` (the variable's name, never the key), `--rate`,
      `--duration-seconds`, `--warmup-seconds`, `--max-connections`, `--scenario`, `--limiter`,
      `--tokens-per-minute`, `--capacity-tokens`, `--routes-file` (only its SHA-256 is recorded),
      `--upstream-delay-ms`, `--server` (`uvicorn` or `compose`), a required `--same-machine` or
      `--separate-machine`, and `--output`
  - `tests/test_bench_report.py`.
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. Latency and lag come from the right timestamps: a request handed over 5 ms late that takes 10 ms counts as
     a latency of 15 ms and a lag of 5 ms. Warm-up requests are counted apart and left out of every statistic.
  2. Percentiles are pinned on a known sample. The p99 is published at 10,000 measured requests and replaced by
     "too few samples" at 9,999.
  3. A lag p99 of exactly 10% of the latency p99 is valid, and one just above it is invalid. Validity is
     computed at 9,999 samples too. Any non-200 or transport error makes the run invalid, and errors are
     counted by status.
  4. The report holds every setting ADR-0018 lists, including the body's size and SHA-256 and the routes
     file's SHA-256. A marker placed in the key appears in no output, and the routes file's content does not
     appear either.
  5. A tiny in-process run (20 requests against `create_app()` through `httpx.ASGITransport`, on the fake
     clock) produces a report that passes the shape checks.
- **Verification:** `python scripts/check.py` green; mutation table: latency measured from the hand-over time
  instead of the due time; warm-up included; `inclusive` changed to `exclusive`; 9,999 samples accepted for a
  p99; validity skipped below the floor; `<=` changed to `<` in the lag check; a non-200 left out of the
  validity check; the key or the routes file's content written to the report. Then `gh pr checks <n> --watch`.
- **Branch and commits:** `feat/t-407-load-report`; `feat(bench): report a load run with its settings`,
  `docs(tasks): complete T-407`.
- **Size:** about 450 lines, most of it tests. Above the ~400-line plan threshold; the owner approves the size
  with this card.

### T-408 - Cache scan and embedding latency benchmarks

- **Status:** done
- **Goal:** the owner can measure the cache scan's cost by partition size and dimension, and the embedding
  call's latency against a local Ollama.
- **Context:** ADR-0015, ADR-0018, `app/cache/semantic.py`, `app/cache/ollama_embedder.py`,
  `scripts/eval_cache.py` (`fetch_ollama_version`), `scripts/bench_load.py` (its report helpers, reused where
  they fit).
- **Depends on:** T-407.
- **Deliverables:**
  - `scripts/bench_cache.py` with two modes:
    - `scan`, with `--entries`, `--dimensions`, `--repeats`, `--seed` and `--max-vector-bytes`
    - `embed`, with `--url`, `--model` and `--calls`
  - A JSON and Markdown report with the settings, as ADR-0018 says.
  - `tests/test_bench_cache.py`.
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. `scan` fills exactly N entries in one partition (`len` of the cache is N), and every timed lookup is a
     `Miss`. A companion lookup with a threshold below every similarity is a `Hit` whose similarity equals the
     maximum over all N entries, computed independently in the test. That shows the scan reaches every entry.
  2. The vectors are unit vectors and the same for a given seed; their first values are pinned.
  3. With an injected timer, the reported minimum and median per lookup are exact.
  4. A combination whose vectors would exceed `--max-vector-bytes` is skipped and reported as skipped. At exactly
     the limit it runs.
  5. `embed`, through `httpx.MockTransport`: the first call is discarded, the next N are timed, and the Ollama
     version is recorded with `fetch_ollama_version`. An `EmbeddingError` stops the run with a fixed message and
     reports no figure.
  6. A tiny run (N of 10, D of 8) completes in CI.
- **Verification:** `python scripts/check.py` green; mutation table: a threshold that lets entries hit; each
  entry in its own partition (killed by criterion 1's companion lookup); the scan stopped early; the discarded
  first call kept; minimum and median swapped; the memory guard off by one; an `EmbeddingError` swallowed. Then
  `gh pr checks <n> --watch`.
- **Branch and commits:** `feat/t-408-cache-bench`; `feat(bench): measure the cache scan and the embedding
  call`, `docs(tasks): complete T-408`.
- **Size:** about 400 lines, most of it tests.

### T-409 - The owner's benchmark runs and the operations guide

- **Status:** done
- **Goal:** the figures the docs publish come from the owner's recorded runs, and the owner can run, scrape and
  read the gateway from the docs alone.
- **Context:** ADR-0005, ADR-0016, ADR-0017, ADR-0018, `docs/setup.md`, `scripts/bench_load.py`,
  `scripts/bench_cache.py`, `scripts/fake_upstream.py`, `deploy/bench/`, `compose.yaml`.
- **Depends on:** T-405, T-407, T-408.
- **Deliverables:**
  - OWNER-CHECK: the owner runs ADR-0018's scenarios A, B and C (B and C with each limiter), the ramp, the
    cache scan and, with a local Ollama, the embedding latency. `docs/benchmarks.md` gets the tables and the
    settings, and the JSON reports go under `docs/benchmarks/`. Invalid runs are reported as invalid. The Log
    records a summary. A scenario the owner does not run is marked "not run" with the owner's reason.
  - OWNER-CHECK (optional): the Compose stack started on the owner's machine, recorded in the Log or marked
    "not run".
  - `docs/setup.md` gains:
    - running with Docker Compose: the variables, `.env` kept uncommitted, and the Ollama profile
    - "Metrics": the token, a Prometheus scrape job with `authorization.credentials_file`, the metric list and
      ADR-0016's series-count formula
    - "Logs": `deploy/logging.json`, the fields, what is never logged, and that tracebacks need uvicorn's text
      format
    - running the benchmarks: the fake upstream, the route files, the limiter settings that leave room for the
      rate, and the lag check on Windows
    - one process per container, and the memory backend's N-times capacity
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. OWNER-CHECK: each scenario is recorded with its settings, or the owner waives it in writing.
  2. Every figure in `docs/benchmarks.md` matches a committed JSON report, and each report says where the
     generator ran and on which platform.
  3. The gateway's added latency is shown as B minus A at each percentile, per repeat.
  4. A search finds no key, token or real secret in any committed file.
- **Verification:** `python scripts/check.py` green. No test is added, so there is no mutation table, and the
  report says so. `gh pr checks <n> --watch`.
- **Branch and commits:** `docs/t-409-benchmarks`; `docs(benchmarks): record the owner's benchmark runs`,
  `docs(setup): add the operations guide`, `docs(tasks): complete T-409`.
- **Size:** about 250 lines plus the JSON reports.

### T-501 - Commit the ramp reports

- **Status:** done
- **Goal:** the ramp figures in `docs/benchmarks.md` and in the Backlog have a committed source.
- **Context:** ADR-0018; `docs/benchmarks.md` ("Not run, or not published"); the Backlog item "Gateway
  throughput with an `openai` provider"; the 19 untracked `docs/benchmarks/ramp-*.json` reports; the T-409 Log
  row.
- **Depends on:** the Phase 5 plan merged.
- **Deliverables:**
  - The 19 `ramp-*.json` reports, committed byte for byte. Each is read in full first and searched with the
    T-409 key patterns. If one holds a key or token, stop and ask the owner.
  - `docs/benchmarks.md`: a "Ramp" section replaces the "run, reports not committed" row. It has one row per
    report: scenario, limiter, target rate, achieved rate, measured seconds, request count, status counts,
    transport errors by kind, peak in flight, lag p50 and lag p99 (or "withheld: too few samples", as the
    report records), validity with the rule or rules that fail, and file.
  - The two reports with suffixes (`ramp-A-r100-full.json` and `ramp-B-redis-r100-cpucheck.json`) are
    described only from their own fields. If the fields do not show what a run was for, the owner says so
    (OWNER-CHECK), or the row reads "purpose not recorded".
  - The Backlog item is reworded to cite the committed reports.
  - The T-409 Log row is not edited. A new Log row records that on 2026-11-26 the owner reversed the
    2026-11-25 choice to leave the reports uncommitted.
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. All 19 files are committed and identical to the working copies (SHA-256 before and after, listed in the
     PR body).
  2. Every ramp figure in `docs/benchmarks.md` and in the Backlog matches a field of a committed report. The
     verifier recomputes each and finds 0 mismatches.
  3. Every ramp row states its validity and the failing rule as the report records them.
  4. A search of the committed files with the T-409 patterns finds no key, token or secret.
- **Verification:** `python scripts/check.py` green. No test is added, so there is no mutation table.
  `gh pr checks <n> --watch`.
- **Branch and commits:** `docs/t-501-ramp-reports`; `docs(benchmarks): commit the ramp reports`,
  `docs(tasks): complete T-501`.
- **Size:** about 60 lines plus the 19 reports.

### T-502 - Investigate the scenario B throughput ceiling

- **Status:** done
- **Goal:** the ceiling of scenario B (about 46 to 54 requests/s against targets of 100 and above) is either
  explained by recorded measurements, or stated as suspected and unconfirmed, with what was ruled out, or shown
  not to reproduce on the current commit.
- **Context:** ADR-0018; `docs/benchmarks.md` (the ramp section from T-501); the Backlog item; "Running the
  benchmarks" in `docs/setup.md`.
  - The provider client is built in `app/main.py` (`build_http_client`) with no `limits=`, so it uses httpx's
    default pool. That is a thing to measure, not an assumed cause.
  - Code: `app/providers/openai.py`, `run_route` and its attempts in `app/routing/`.
  - The request log's `attempts` field, and the metrics `tollgate_provider_attempt_duration_seconds` and
    `tollgate_http_request_duration_seconds`.
  - The owner's account of `ramp-B-redis-r100-cpucheck.json` (`docs/benchmarks.md`, 2026-11-26): during that
    run the gateway was at 100% CPU and the generator at 44 to 67%, sampled by a method that was not
    recorded. It points at the gateway process, but it is not in any report and is not a cause.
  - Scripts: `scripts/fake_upstream.py`, `scripts/bench_load.py`. No `app/`, `scripts/` or `deploy/` file has
    changed since the ramp runs' commit `75384aa`, so runs on the current `main` are comparable with them.
- **Depends on:** T-501.
- **Definition of "follows":** a run follows its target when its achieved rate is at least 98% of the target,
  its peak in flight is at most 50, and it has no transport error. The ramp baselines that followed: A at 100/s
  (99.68/s, peak 13), C memory at 100/s (100.00/s, peak 10) and B memory at 50/s (49.88/s, peak 15). B memory
  at 100/s did not (48.95/s, peak 1107, 14 `ConnectError`s).
- **Timebox:** at most seven runs: the four in step 1, one in step 3 and two variations in step 4. If B at 100/s
  did not follow in step 1 and no variation confirms a cause, the conclusion is "suspected, unconfirmed". That is an accepted outcome, not a
  blocked task.
- **Settings:** standard library only, so no `py-spy` and no new dependency.
  - Each step 1 run reproduces one ramp report with the values recorded there:
    - B memory at 50 and 100/s (`ramp-B-memory-r50.json`, `ramp-B-memory-r100.json`)
    - A at 100/s (`ramp-A-r100.json`, not the 100 s `ramp-A-r100-full.json`)
    - C memory at 100/s (`ramp-C-memory-r100.json`)
  - The shared values are 20 s measured, 5 s warm-up and no `--max-connections` cap. B and C use tokens per
    minute and capacity of 276,000. B and A use a 50 ms upstream delay, and C has no upstream.
  - At 100/s a 25 s run reserves 57,500 tokens from a full bucket of 276,000, so the limiter refuses nothing. A
    variation that changes the rate rechecks this.
  - Every gateway run (B and C, in every step) sets `TOLLGATE_METRICS_TOKEN` and `--log-config
    deploy/logging.json` and sends stdout to a file outside the repository, never the console. The ramp runs of
    2026-11-25 recorded neither setting. The section says so, since step 1's runs may differ from them in that
    respect.
  - Every run samples the CPU time of the gateway and the fake upstream processes, each found by its
    listening port, with Windows' own `netstat` and PowerShell `Get-Process` (no new dependency), just before
    the generator starts and just after it ends. The section reports CPU seconds per request (over all
    requests, warm-up included, like `generator_cpu_seconds / requests.total`) and CPU seconds per wall
    second, and states the method. A sample that fails is recorded as "not sampled".
  - A report's `git_commit` comes from `git rev-parse HEAD`, so it does not show a variation's diff. The section
    quotes, for every run, the full commands for the fake upstream, the gateway (variable names, flags, log
    config) and the generator. Each variation report is marked "commit field does not include the quoted diff".
- **Method:**
  1. **Reproduce.** Run the four step 1 runs on the current `main` commit. For the B and C runs at 100/s,
     scrape `/metrics` before and after, and keep the request log. If B at 100/s follows its target, record that
     and go straight to the conclusion. If A or C at 100/s does not follow, the section says so, comparison
     (c) is not used, and no generator-side variation can support a "Cause".
  2. **Locate the time.** No new run: use step 1's runs for three comparisons.
     - (a) The provider-attempt duration against the request duration, both from the metrics and the log. This
       is the time inside the attempt (the adapter, httpx and the upstream) against the time around it in the
       app.
     - (b) The median `duration_seconds` from the request log, over the measured window only (selected by
       timestamp, so the warm-up is left out), against the report's latency p50. The histogram is only a
       cross-check: its buckets are too coarse near 50 ms, and a before-and-after delta includes the warm-up.
       The gap is time outside the app's timer: the generator's lag before the hand-over (the report's lag p50)
       and its work after it, or uvicorn's accept and parse and event-loop queueing before the timer starts. (b)
       alone cannot tell the generator from uvicorn.
     - (c) Generator CPU per request (`generator_cpu_seconds / requests.total`, both in every report), lag max
       and peak in flight, against the A and C controls at 100/s, with the gateway's and the fake upstream's
       CPU per request and per wall second beside them. In the ramp reports this was about 4.6 ms for
       A, 4.8 ms for C and 14.4 ms for B at 100/s. Only these controls bound the generator, and only up to
       100/s.
  3. **Profile.** Run B at 100/s once more under `python -m cProfile -o <a path outside the repository> -m
     uvicorn --factory app.main:create_app ...`, with the step 1 settings. This run is diagnostic and is not
     compared with the others. Record the top 20 functions by `tottime` and by cumulative time. `cProfile` sees
     only the main thread, so work in FastAPI's thread pool is not profiled, and the section says so. `cProfile` writes its file only
     when uvicorn exits normally, so the owner stops the server with Ctrl+C in a Windows console, not by killing
     it, and the run counts only if the profile file exists and is not empty.
  4. **Isolate.** Make at most two variations, each a single change applied to a scratch copy and never
     committed, such as the client's pool limits or the generator's `--max-connections`. The section quotes
     each diff. A variation confirms a cause only if B at 100/s then follows its target, with every other
     setting as in step 1.
- **Deliverables:**
  - `docs/benchmarks.md` gains a "Throughput ceiling investigation" section: each run with its commands,
    settings and report; the three comparisons; the profile's top entries; each variation with its diff.
  - The conclusion takes exactly one of three forms:
    - "Cause: X, shown by run Y"
    - "Suspected, unconfirmed: X; ruled out: ..."
    - "Not reproduced on commit `<hash>`: B followed 100/s in run `<file>`"
  - The reports, under `docs/benchmarks/` as `ceiling-*.json`.
  - The Backlog item is updated. A fix, if a cause is found, becomes a new Backlog item and is not part of this
    task. There is no `app/` change.
  - OWNER-CHECK: the owner runs them by hand, as in T-409 (decided 2026-11-26). They use only localhost (the
    gateway, the fake upstream and the generator). The task starts by giving the owner the exact commands for
    each run, with every setting.
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. Every figure in the section matches a committed report, or a `/metrics` excerpt or log excerpt quoted in
     the section.
  2. The conclusion uses one of the three forms. A "Cause" names the variation run that shows it, and every
     "follows" uses the definition above.
  3. Each run is labelled valid or invalid under ADR-0018, as its report says.
  4. Every run's commands are quoted in full, and every variation report is marked as such.
  5. There is no change in `app/` and no dependency, and the secret search is clean.
  6. OWNER-CHECK: the owner confirms the wording of the conclusion.
- **Verification:** `python scripts/check.py` green. No test is added, so there is no mutation table.
  `gh pr checks <n> --watch`.
- **Branch and commits:** `docs/t-502-ceiling`; `docs(benchmarks): record the throughput ceiling
  investigation`, `docs(tasks): complete T-502`.
- **Size:** about 180 lines plus the reports.

### T-503 - The findings write-up

- **Status:** done
- **Goal:** one page tells the three findings, each as question, method, result, meaning and limits, with
  every figure linked to its source.
- **Context:** `docs/cache-eval.md`, `docs/benchmarks.md`, ADR-0005, ADR-0014, ADR-0015, ADR-0018, the T-307
  and T-409 Log rows, and T-502's conclusion.
- **Depends on:** T-502.
- **Deliverables:** `docs/findings.md`, with these parts:
  - **Summary.** The three findings, in at most three sentences each.
  - **Finding 1: no safe cache threshold.**
    - The question: can one cosine threshold separate same-meaning from different-meaning pairs?
    - The dataset: 80 pairs and their SHA-256.
    - The result: no threshold below 1.00 had zero wrong hits. At 0.99, 2 of 40 same-meaning pairs hit and 4
      of 40 different-meaning pairs hit. All 8 negation pairs hit through 0.88, and all 8 changed-number pairs
      through 0.78.
    - What follows from it: no default threshold, the cache off by default, no threshold recommended.
    - Limits: one model, and a small hand-written dataset (80 pairs), with the threshold judged on the same
      data it was measured on. `bge-m3` was not run.
  - **Finding 2: the lag rule on Windows.**
    - What the rule guards against.
    - What was observed: in the 15 runs at 40 requests/s, the lag p99 was 14.0 to 16.1 ms. That is consistent
      with the Windows timer tick of about 15.6 ms, an external figure not measured here. If the tick is the
      floor, the 10% rule could pass only with a latency p99 above about 150 ms.
    - The ramp runs at and above the ceiling fail the rule with lags of seconds. That is a different matter,
      covered under Finding 3.
    - What that means for the published figures. It is untested whether a generator on Linux or WSL2 gives a
      valid run.
  - **Finding 3: the throughput ceiling,** worded exactly as T-502's conclusion allows.
  - **How the figures were produced:** the evidence rules (ADR-0005, ADR-0018).
  - **What I would do next,** taken from Backlog items and linked to them.
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. Every number appears in a committed report, in `docs/cache-eval.md` or in `docs/benchmarks.md`. The
     verifier recomputes each and finds 0 mismatches.
  2. Every figure from an invalid run is called invalid in the same sentence or table row.
  3. Finding 3 uses T-502's conclusion form.
  4. No sentence claims more than its source. The reviewer's table gives a source for each claim.
- **Verification:** `python scripts/check.py` green. No test is added, so there is no mutation table.
  `gh pr checks <n> --watch`.
- **Branch and commits:** `docs/t-503-findings`; `docs(findings): write up the cache, lag and ceiling
  findings`, `docs(tasks): complete T-503`.
- **Size:** about 200 lines.

### T-504 - ARCHITECTURE refresh: deployment and component diagrams

- **Status:** todo
- **Goal:** `docs/ARCHITECTURE.md` describes what is built, with three diagrams checked against the code.
- **Context:** `docs/ARCHITECTURE.md`, `compose.yaml`, `Dockerfile`, `deploy/`, the cross-package imports in
  `app/`, ADR-0016, ADR-0017, ADR-0019.
- **Depends on:** ADR-0019 accepted.
- **Deliverables:**
  - **Status line.** Phase 4 done. The line "sections 2 to 4 describe the target design" is replaced by a
    built or not-built label on each part.
  - **Request flow.** The existing diagram is checked against the chat route and gains the log line and the
    metrics.
  - **Deployment diagram** (Mermaid), labelled from `compose.yaml` and `deploy/`:
    - the client reaches `127.0.0.1:8000`, served by the gateway container (non-root, one uvicorn process)
    - `redis:7.4.12`, with no published port
    - `ollama`, in an opt-in profile
    - the route file, mounted read-only
    - logs on stdout
    - `/metrics` scraped by a Prometheus outside the repository, drawn dashed and labelled "outside the
      stack", backed by the `/metrics` route in `app/` rather than by `compose.yaml`
  - **Component diagram** (Mermaid): the six `app/` packages (`api`, `routing`, `providers`, `limits`,
    `cache`, `observability`) and the three top-level modules (`settings`, `clock`, `main`), with arrows in
    import direction.
  - Section 5's layout updated: `deploy/`, `Dockerfile`, `compose.yaml` and the benchmark scripts.
- **Contract:** unchanged. No interface in section 3 changes. If one turns out wrong, stop and ask the owner:
  an interface change needs the owner's approval.
- **Acceptance criteria:**
  1. The verifier's table backs every diagram edge with a line of code, `compose.yaml`, the `Dockerfile` or a
     file in `deploy/`.
  2. Every import between those packages and modules appears as an edge in the component diagram.
  3. No built part is labelled planned, and every part has a label.
  4. OWNER-CHECK: the diagrams render on the PR's GitHub page.
- **Verification:** `python scripts/check.py` green. No test is added, so there is no mutation table.
  `gh pr checks <n> --watch`.
- **Branch and commits:** `docs/t-504-architecture`; `docs(architecture): add deployment and component
  diagrams`, `docs(tasks): complete T-504`.
- **Size:** about 150 lines.

### T-505 - The text demo

- **Status:** todo
- **Goal:** a reader sees the gateway work without running it: real requests and their real outputs.
- **Context:** `docs/setup.md` (Compose, Metrics, Logs), `compose.yaml`, `deploy/routes.compose.json`,
  `scripts/smoke_container.py`, ADR-0016, ADR-0019.
- **Depends on:** ADR-0019 accepted.
- **Deliverables:**
  - `docs/demo.md`: one sequence, each step with its exact command and the output captured from one real run.
    The page header records the date, the commit, the platform, and how the gateway was served: the Compose
    stack, or bare uvicorn with the mock route if Docker is not available. The steps:
    1. `GET /health`
    2. a chat completion through the mock: a 200 with `x-tollgate-provider`, `x-tollgate-fallbacks` and the
       `x-ratelimit-*-tokens` headers
    3. no API key: 401
    4. a small bucket exhausted: 429 with `Retry-After` (the run sets a low `TOLLGATE_TOKENS_PER_MINUTE`, and the
       page says so). On the Compose stack the Redis bucket persists per key across runs, so this step uses a
       fresh key.
    5. a `/metrics` excerpt after the run, saying how the lines were chosen
    6. the JSON log lines of those requests
    7. optional, only if a local Ollama runs: a cache miss and then a hit (`x-tollgate-cache`). The page states
       the threshold used and that it is not a recommended one, since none was found.
  - Commands read the key and the token from environment variables, so no value appears in a command. Output is
    pasted unedited, apart from elisions marked `...`.
  - OWNER-CHECK (optional): screenshots of the same run under `docs/demo/`, PNG, at most 300 KB each, checked
    by eye for secrets.
  - No unknown-model 404 step: both mock route files (`deploy/routes.compose.json` and
    `deploy/bench/routes.mock.json`) have a `default` route, so any model name returns a 200 (`docs/setup.md`).
  - OWNER-CHECK: the owner runs the sequence by hand on localhost, as in T-409 (decided 2026-11-26). The task
    starts by giving the owner the exact commands.
- **Contract:** unchanged. No new script and no dependency.
- **Acceptance criteria:**
  1. Every output block comes from the recorded run named in the header, and every elision is marked.
  2. The verifier replays the same sequence in-process (TestClient, the mock and the route file named in the
     page header). Status codes and header names (not their values) match the page.
  3. No key or token value appears in any committed file or image.
- **Verification:** `python scripts/check.py` green. No test is added, so there is no mutation table.
  `gh pr checks <n> --watch`.
- **Branch and commits:** `docs/t-505-demo`; `docs(demo): add the recorded text demo`,
  `docs(tasks): complete T-505`.
- **Size:** about 200 lines, plus optional images.

### T-506 - README rewrite, findings first

- **Status:** todo
- **Goal:** within the first screen, a first-time reader learns what Tollgate is, what was found, and where to
  see it run.
- **Context:** `README.md`, `docs/findings.md`, `docs/benchmarks.md`, `docs/demo.md`, `docs/ARCHITECTURE.md`,
  the index of `docs/DECISIONS.md`, and the latest green CI run on `main`.
- **Depends on:** T-503, T-504, T-505.
- **Deliverables:** `README.md` rewritten in this order:
  1. a one-sentence description and the badges
  2. "What I found": the three findings, two or three lines each, linking `docs/findings.md`
  3. "See it run": a short excerpt of `docs/demo.md`, linking it
  4. what it does: one short table of the built features
  5. architecture: one diagram taken from ARCHITECTURE, with a link
  6. how it was built: pull requests only, mutation checks, the contract snapshot, evidence-first figures, kept
     short
  7. running it locally: Compose and bare uvicorn
  8. limitations, kept and brought up to date
  9. the documentation table (findings, benchmarks and demo added) and the ADR table through 0019

  Everything stale goes: the Phase 3 status, "No performance figures yet", Compose, metrics and benchmarks
  listed as planned, and "None" under operations in the tech stack. The test counts and the CI run id are
  current, taken from `main` at the time of writing.
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. The first two sections are the description with the badges, and "What I found" with the three findings
     and their links; "See it run" follows them.
  2. Every figure matches its linked source (verifier table).
  3. No built feature is called planned, and nothing unbuilt is called built (verifier table against the code
     and the docs).
  4. Every relative link and anchor resolves.
  5. OWNER-CHECK: the owner reads the rendered README on the PR and approves it.
- **Verification:** `python scripts/check.py` green. No test is added, so there is no mutation table.
  `gh pr checks <n> --watch`.
- **Branch and commits:** `docs/t-506-readme`; `docs(readme): rewrite the README to lead with the findings`,
  `docs(tasks): complete T-506`.
- **Size:** a 258-line file rewritten to about 250 lines, about 450 changed lines. That is above the ~400-line
  plan threshold, and approving this plan approves the size.

### T-507 - Phase 5 close-out and TASKS housekeeping

- **Status:** todo
- **Goal:** `docs/TASKS.md` and `docs/DECISIONS.md` show the project's state at the end of Phase 5.
- **Context:** `docs/TASKS.md` (the phase sections, the board, Later phases, the Backlog), the DECISIONS index.
- **Depends on:** T-506.
- **Deliverables:**
  - The Phase 5 section marked complete once the owner signs off its gate. The current-phase header updated
    to say that no phase is open.
  - The Later phases row for Phase 5 marked done.
  - The Backlog: the "Image publishing" item reworded or removed per ADR-0019, the throughput item as T-502
    left it, and any other item a Phase 5 task closed.
  - A Log row.
- **Contract:** unchanged.
- **Acceptance criteria:**
  1. The board's statuses match the cards.
  2. Every Backlog item left is still open.
  3. Every new Log row has exactly four cells (Python scan of unescaped pipes).
- **Verification:** `python scripts/check.py` green. No test is added, so there is no mutation table.
  `gh pr checks <n> --watch`.
- **Branch and commits:** `docs/t-507-close-out`; `docs(tasks): close out Phase 5`.
- **Size:** about 60 lines.

## Later phases (broken into tasks at each gate)

| Phase | Epic |
| --- | --- |
| 1 | Token-aware rate limiting: planned 2026-11-12 as T-101 to T-108 (see the current phase) |
| 2 | Model routing: planned 2026-11-13 as T-201 to T-207; T-208, T-209 and T-210 added 2026-11-14 (see the current phase) |
| 3 | Semantic caching: planned 2026-11-21 as T-301 to T-307 (see the current phase) |
| 4 | Operations: Docker Compose, observability, reproducible load benchmarks: planned 2026-11-23 as T-401 to T-409 (see the current phase) |
| 5 | Demo and write-up: planned 2026-11-26 as T-501 to T-507 (see the current phase) |

### Requirements that carry into the task cards

These are written into the cards when each phase is planned. The two Phase 1 items are in ADR-0006, T-106 and
T-107. The Phase 3 item is in ADR-0014, T-304 and T-307. The Phase 4 item is in ADR-0017, T-405 and T-409.

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
- **Gateway throughput with an `openai` provider:** in the diagnostic ramp runs on Windows
  (`docs/benchmarks/ramp-*.json`: 20 s each, one A run of 100 s, all invalid; see "Ramp (diagnostic)" in
  `docs/benchmarks.md`), scenario B did not follow targets of 100 requests/s and above, achieving 46.43 to 54.09
  requests/s (the memory limiter at 100 only, Redis at 100, 200, 300, 400 and 600), while scenario C followed 100
  requests/s with both limiters. Two of the 100 requests/s runs also had `ConnectError` transport errors
  (`ramp-B-memory-r100.json` 14, `ramp-B-redis-r100-cpucheck.json` 111). T-502 did not reproduce the memory case.
  On commit `e280d37`, B with the memory limiter followed 100/s (`ceiling-B-memory-r100.json`: 99.66/s, peak 17,
  no transport error). These runs differed from the ramp runs in their metrics and logging settings. That is a
  difference between the two sets, not a shown cause (see "Throughput ceiling investigation" in
  `docs/benchmarks.md`). The cause of the ramp ceiling is unknown. Still open: B with Redis at 100/s, B at 200/s
  and above, and the same runs with the generator on Linux or WSL2. None of these has been run since.
- **Dependabot for GitHub Actions SHA pins:** the workflow pins its actions by commit SHA, which is updated by
  hand today. A Dependabot configuration for the `github-actions` ecosystem would propose those updates as pull
  requests. It adds a configuration file to the repository, so it is a task of its own, with a check that the
  proposed updates keep the version comment next to each SHA. Since ADR-0017 it also covers the `docker`
  ecosystem: the base image digest in the `Dockerfile`, and the image tags in `compose.yaml` and `ci.yml`.
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
- **Validate `base_url` at startup:** an `ollama` (and later `openai` and `anthropic`) `base_url` is checked
  by nothing today: a malformed one fails at the first request (`httpx.InvalidURL` or `UnsupportedProtocol`, a
  502 after a full refund or a fallback), and an empty string counts as not given and uses the default host
  (pinned by a test in T-204). A startup check would name `TOLLGATE_ROUTES_FILE` and the field path, never the
  value, since the value can hold credentials, and would decide whether an empty string is rejected (T-204 plan
  review, owner decision to log it).
- **IETF RateLimit header fields:** emit `RateLimit` and `RateLimit-Policy` alongside the `x-ratelimit-*`
  headers once draft-ietf-httpapi-ratelimit-headers becomes an RFC and has a unit for tokens (ADR-0008).
- **Shared semantic cache:** keep cache entries in Redis so that every process shares them, through Redis 8
  vector sets or the Query Engine. It needs a newer CI Redis image, and fakeredis cannot run `FT.SEARCH`
  (ADR-0015).
- **Per-request cache controls:** `Cache-Control: no-cache` (do not read) and `no-store` (do not write) on a
  chat request; changes the contract (ADR-0014).
- **Cache purge:** an authenticated way to empty the cache without a restart (ADR-0014).
- **Request-count limit for cache hits:** a hit costs no tokens, so a caller can repeat cached prompts without
  limit while the reservation succeeds (ADR-0014).
- **More embedders:** a prompt-prefix setting for models that need one (`nomic-embed-text`,
  `mxbai-embed-large`), and an embedder for the OpenAI-compatible `/v1/embeddings` (ADR-0015).
- **Request id:** a response header carrying an id that the request log also holds, so one request can be
  traced across systems. Changes the contract (ADR-0016).
- **Cache size metric:** a gauge of the entries the cache holds, read from `len()` of the
  `InMemorySemanticCache` at each scrape (ADR-0016).
- **`prometheus_client`:** move the metrics to `prometheus_client` with a registry per app if the hand-written
  registry outgrows its tests. Metric names stay the same (ADR-0016).
- **API-key parsing edge cases:** `app/api/auth.py` strips only spaces from the key (`rest.strip(" ")`) and
  matches the `bearer` scheme case-insensitively, the same rules the `/metrics` token check uses. T-404's second
  mutation pass found that a non-breaking space next to the token, a lookalike scheme (`Bearerx`, `Bearer2`,
  `xBearer`) and a non-ASCII token were unpinned there. Nobody has checked whether the API-key tests pin them.
  Mutate that path, add the missing tests, and fix any real gap (T-404 review, owner decision to track it).
- **Image publishing:** publish the image to the GitHub Container Registry on pushes to `main`, decided with
  the Phase 5 demo (ADR-0017).
- **TLS in front of the gateway:** an example reverse-proxy configuration for a host reachable from outside
  (ADR-0017).

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
| 2026-11-13 | T-201 | `app/providers/errors.py` (`ProviderError` with the five ADR-0010 kinds; `retryable` for connection, timeout, rate_limited and upstream_status from 500) and `app/routing/config.py` (strict pydantic models with one model per provider type, a read-only `RouteTable`, the built-in table of one `mock` provider and a default route to it) added; `Settings.from_env` reads the table and its keys from the same mapping, so a bad table stops `create_app()` at startup. Errors name the variable and a field path with a fixed reason per error type; pydantic's own messages are never used, because some echo the input. Owner decisions at plan review and after it: `api_key_env` must be a variable name, a blank variable is an error, UTF-8 without a byte order mark, an unreadable file is reported without its path, and empty provider names, aliases and upstream models are rejected. `app/main.py` and the contract are unchanged; no dependency added. `scripts/check.py` passed (14 contract and 787 other tests). The change is about 1,113 added lines (355 code, 718 tests, 40 docs), against about 650 approved at plan review; the difference is the tests added in review and verification, the empty-name rules, and formatting. Mutation check on scratch copies: 64 mutants, 62 caught; the 2 survivors (removing `from None` on two inner re-raises) are equivalent, because the raised `SettingsError` keeps its own suppression and its message and formatted traceback are unchanged. One feedback iteration. Review found that a duplicate key's dropped value could be freed and its `id` reused, giving a wrong path (fixed by keeping every parsed object alive); that the recursive duplicate walk raised `RecursionError` between depths 1000 and 2999, which the JSON parser accepts (now iterative); that a test nesting 5000 levels would have passed on Windows and failed on Linux, where the parser's limit is higher (now 100,000); and that the walk's order was not pinned (two tests). Verification found that a NUL in the path raised a raw `ValueError` (now caught) and that `sk-` placeholders tripped the secret search (replaced). The first verifier run stalled after its driver crashed on three parallel test runs that timed out; the 14 unfinished mutants were re-run one at a time with a timeout and none hung | Verifier tables; `check.py` output; `gh pr checks` is recorded in the pull request |
| 2026-11-14 | T-202 | Chat completions are routed. `app/routing/router.py` adds `Route` (an ordered tuple of targets), the `Router` protocol and `TableRouter` (exact alias, else the default route, else `UnknownModelError`), and `run_route`, which tries each target once, in order, with the request's `model` replaced by the target's upstream model (the client's when it has none, never changing the client's request), moves on only after a retryable `ProviderError`, and returns `Served` (completion, provider name, fallbacks) or `RouteFailed` (charged only for `bad_response`, also after a fallback). `create_app()` builds the provider registry on `app.state.providers` (one `MockProvider` on the injected clock per `mock` entry; any other type is a startup `SettingsError` on `TOLLGATE_ROUTES_FILE` naming `providers.<name>.type`), with `provider=` setting the `mock` entry and a new `providers=` keyword setting entries by name, and a `TableRouter` on `app.state.router`. The route reads both from `app.state` per request, selects before any estimate or reservation (404 `model_not_found`, `param: model`, a fixed message, no limit headers), settles once with the serving attempt's usage, refunds a failed route in full and charges a `bad_response` as reserved (502 either way), and adds `x-tollgate-provider` and `x-tollgate-fallbacks` to a 200 only. The snapshot gains the 404, the two headers and the new 502 description. `scripts/check.py` passed: 14 contract and 838 other tests, 45 deselected. Mutation table, one mutant at a time on scratch copies: 50 mutants (the card's 14 plus 36 more, among them a loosened alias match, an in-place request change, a later `bad_response` refunded, each unbuilt type accepted, injection order, the router or registry captured at startup, table mocks on the system clock, selection before authentication or validation, routing headers on a 502 or 429, and the 404 status, code, param and OpenAPI entry); 49 killed in round one. The survivor, routing headers on a 429, was killed after `test_refused_request_on_a_route_gets_429_without_routing_headers_or_a_provider_call` was added (rerun on its own) | `tests/test_router.py`, `tests/test_chat_routing.py`; `gh pr checks` is recorded in the pull request |
| 2026-11-14 | T-202 | Known gaps from review: (1), folded into T-203 by the owner, a provider name that is not a valid header value (characters outside latin-1, or CR or LF) passes the route table checks, and the 200 then fails with a 500 after the provider answered and settle ran, so the caller is charged without an answer; the fix is a startup check on provider names; (2) `provider=` adds a `mock` entry even when a route file names no such provider, which nothing routes to. Unchanged from T-108: a provider name missing from the registry (only possible by editing `app.state.providers`) is a 500 after the reservation, never a refund | Reviewer findings |
| 2026-11-14 | T-203 | The app closes the clients it builds, and a provider name that cannot be a header value stops startup. `create_app()` keeps a list of owned clients on `app.state.owned_clients` and an app lifespan closes it at shutdown, last built first. `build_limiter` now returns a `LimiterBuild` (limiter, Redis client, clients it built); only a client built with `Redis.from_url` is added, an injected client and the memory backend add nothing. A close that raises does not stop the others; once every client has been tried, the errors are raised together as an `ExceptionGroup`, so a failure is not hidden (uvicorn logs it at ERROR). A `BaseException` such as `KeyboardInterrupt` or `CancelledError` is not collected: it propagates at once, so the clients not yet closed stay open (pinned by a test). `app/routing/config.py` rejects a provider name that is not made only of the characters `\x21` to `\x7e`, next to the empty-name check, with a `SettingsError` on `TOLLGATE_ROUTES_FILE` naming `providers` and a fixed reason that never shows the name; the empty-name message is unchanged. `docs/setup.md` states the rule and `ARCHITECTURE.md` the lifespan. Contract unchanged, no dependency added. `scripts/check.py` passed: 14 contract and 908 other tests, 45 deselected. Mutation check on scratch copies, one mutant at a time with a timeout: 42 mutants (the card's list as 17 variants and 25 more: close at startup, a snapshot of the list, a double close, errors swallowed or only the first kept, the built client unregistered or registered twice, `any` for `all`, first or last character only, only the first provider checked, the new check before or replacing the empty-name check, the check applied to aliases, the header lowercased or percent-encoded, `except BaseException`, a Redis client built and discarded in the memory branch or beside an injected client). Round one caught 35 of 37 and left two survivors, `except BaseException` and a discarded `Redis.from_url` in the memory branch; round two added four mutants and left two more, a discarded `Redis(...)` in the memory branch and a discarded `Redis.from_url` beside an injected client; the final round caught all 42, the last one added (the client built with `Redis(...)` instead of `from_url`) by the URL-parsing test. All four survivors were closed by tests that make any Redis construction in `app.main` fail, and by a test calling `_close_all` with a `KeyboardInterrupt`. Two feedback iterations, then a third verification round with no survivor. Reviewer APPROVE, no Critical or Major finding, six Minor findings, recorded below | Verifier tables, three rounds; `check.py` output; `gh pr checks` is recorded in the pull request |
| 2026-11-14 | T-203 | Process deviation and known gaps. (1) Commit `7fec641` does not pass `mypy` on its own: its test passed a `KeyboardInterrupt` to a fake typed for `Exception`, and the next commit `cb4e224` widens the type. History is not rewritten, so the branch has one commit that is not green by itself, and the two follow-up test commits are in addition to the three the card named. (2) A provider name is still printed by any other error in the same provider entry, because pydantic validates before the name check and its error path contains the name (a bad name and an unknown field, for one); this is the T-201 path format, startup only, and the one-fault files in criterion 5 do not reach it; the fix is a name check before validation, or printing a placeholder for the key, and is left to the owner. (3) A failing close is raised with the library's own error text and no redaction; redis-py's close path was read and none of its errors carries the password, but no test pins that. (4) No length cap on a provider name, which is copied into every 200's header. (5) `_close_all` is imported by one test, the only dependency on a private name. (6) `LimiterBuild` and `AsyncCloseable` are not named in `ARCHITECTURE.md`, which does not list `build_limiter` either. The T-108 gap of the unclosed Redis client is closed by this task; the HTTP clients are registered by the adapter tasks | Reviewer and verifier findings |
| 2026-11-14 | T-204 | The Ollama adapter is built. `app/providers/ollama.py` (`OllamaProvider(client, clock, id_source)`) posts `POST /api/chat` with exactly `model`, `messages` (role and content only), `"stream": false` and, only when given, `options.num_predict` (from `max_completion_tokens`, else `max_tokens`) and `options.temperature` (0.0 is sent); `name`, `user` and `n` are not sent. A reply must be a JSON object with a `message` object holding a string `content`, a non-empty string `model` and a `done_reason` of exactly `stop` or `length`; `prompt_eval_count` and `eval_count` are 0 when absent, and must otherwise be whole numbers of at least 0 (a bool, a float, `NaN`, `Infinity`, a string or null is a `bad_response`); `id` and `created` come from the injected sources (never the body) and the output role is always `assistant`. Failures are `ProviderError`s whose message holds only the kind and the status: a timeout (checked before the other `httpx.TransportError`s) and a connection error, both retryable; 429 `rate_limited`; any other non-2xx `upstream_status`, retryable from 500 only; an undecodable, empty or untranslatable 2xx `bad_response` with its status. The response is streamed so the body of a non-2xx answer is never read, and redirects are not followed. `create_app()` gains `http_transport=` and builds one `httpx.AsyncClient` per `ollama` provider (base URL, default `http://localhost:11434`; 5 seconds to connect and `timeout_seconds` for reads, writes and the pool, per ADR-0010) on `app.state.owned_clients`, so T-203's lifespan closes them; `build_providers` now returns a `ProvidersBuild` like the limiter's `LimiterBuild`. `httpx`, `httpcore` and `certifi` moved from `requirements-dev.txt` to `requirements.txt` and `httpx>=0.28.1` to the runtime dependencies in `pyproject.toml`: the union of the two files is identical to `main`'s, and fresh Windows venvs for both files installed with `--only-binary=:all:` with a clean `pip check` and a freeze equal to the union (the Linux install is shown only by CI). `IdSource` and `UuidIdSource` moved to `app/providers/ids.py`; a test checks the adapter does not import the mock. The contract is unchanged. `scripts/check.py` passed: 14 contract and 1052 other tests, 45 deselected. The change is 1,063 added lines (215 in `app/`, 826 in tests, the rest requirements and docs) in 14 files, against about 350 planned for the code; the owner approved the full size at plan review because the card's figure counts only production code. Mutation check on scratch copies, one mutant at a time with a timeout: 74 mutants (the card's 13 as 29 variants, and 45 more: temperature by truthiness, options sent empty, `user` or `n` forwarded, each of read, write and pool and the connect timeout changed, one client shared or the transport not passed, a wrong or ignored default `base_url`, a bool or a negative or zero count accepted, the model or either lone-surrogate check dropped, the 2xx test `== 200`, `< 300`, `<= 300`, `>= 300` or `< 400`, the 429 branch dropped, `DecodingError` unhandled, a non-2xx body read, redirects followed per request or on the client, UTF-8 decoding removed, each shape check dropped, the status of a `bad_response` 0 or None, an unbuilt type, a client built for a mock, the mock imported, a 204 as `upstream_status`, the role taken from the reply). Round one caught 65 of 70 and left five survivors: `base_url` with `is None` instead of `or`, the surrogate check missing for `model` only, a 1xx status accepted as success, redirects followed per request, and the output role taken from the reply. Round two killed those and added five mutants, one of which survived: `follow_redirects=True` on the app's client, because the redirect test used its own client; a whole-app redirect test kills it (the final mutant was run by hand on a scratch copy, and the full check passed on the final tree). No equivalent mutant is claimed. Two feedback iterations. Reviewer APPROVE with eight Minor findings, five applied (the client order in `ARCHITECTURE.md`, stale comments in `app/main.py`, a note on credentials in `base_url`, a working-directory-independent path in a test, and the `NaN`, `Infinity` and surrogate cases), the rest below | Verifier tables, rounds one and two; `check.py` output; `gh pr checks` is recorded in the pull request |
| 2026-11-14 | T-204 | Known gaps and decisions. (1) A bad `base_url` is not checked at startup: a malformed one raises `httpx.InvalidURL` or `UnsupportedProtocol` at the first request, which `run_route` turns into a 502 with a full refund and no fallback (an unclassified exception) or a retryable `connection` error; an empty string counts as not given and uses the default host, which a test pins; the owner logged startup validation as a backlog item. (2) Credentials in `base_url` become HTTP Basic authentication and are kept as plain text in the route file and in `OllamaProviderConfig`, so a repr of the route table would show them; no message, header or log line does (tested for errors and the 502), and `docs/setup.md` says the gateway does not treat them as secrets. (3) The reply is read whole with no size cap, which suits a local Ollama; a count such as `10**30` is accepted and returned in `usage`, and nothing between the adapter and `settle` bounds it. The Redis limiter clamps the charge to its debt floor (`test_charges_stop_at_the_debt_floor_exactly` covers `10**30` at the limiter level; no test goes through the adapter or the app), so the stored balance stays valid, but the key is then in the deepest debt and refused for years (about 238 years at 600 tokens per minute, with the key's expiry set to match); the in-memory limiter has no floor and holds exactly -10**30 tokens, with a `Retry-After` of 29 digits. The owner logged a cap on what `settle` charges as a backlog item, to land before T-205. (4) A startup `SettingsError` after an Ollama client was built leaves that unopened client unclosed, which is harmless; the provider clients are appended before the Redis client, so Redis closes first. (5) `provider=` and `providers=` overrides keep the client built for that name, and the table stays the source of truth. (6) Criterion 6 for CI (the Linux install of the moved requirements) is shown only by the pull request's `lint and test` run, and CI never installs `requirements.txt` alone. T-205 and T-206 reuse `build_http_client` and the owned-client list | Reviewer and verifier findings; plan review |
| 2026-11-14 | - | T-208 planned from the backlog item "Cap what `settle` charges", which it replaces; ADR-0012 proposed (cap a 200's charge at the bucket capacity, `limit_tokens` on the reserve decision, amending ADR-0007). The backlog's example, a multiple of the reservation, was not chosen: a request with no max field reserves only its input estimate (7 tokens for one user message of `hi`), so any small multiple undercharges ordinary answers. T-205 and T-206 now depend on T-208, which is delivered after T-204; the Phase 2 gate gains the ADR-0012 item. The owner accepted ADR-0012 as written the same day, and ADR-0007's status now names it | `docs/DECISIONS.md`; this planning pull request |
| 2026-11-14 | T-208 | A 200 now settles at most one full bucket. `app/limits/charge.py` adds `charged_tokens(reported_tokens, limit_tokens)`, the smaller of the two, with a negative count returned unchanged so `settle` still raises (ADR-0010); `app/api/chat.py` settles a 200 with `charged_tokens(usage.total_tokens, decision.limit_tokens)`, and the response's `usage`, the 502 paths and every header are unchanged (ADR-0012). This closes the unbounded-count part of T-204's known gap 3; the reply is still read with no size cap. Through the whole app at 60 tokens per minute, on the in-memory limiter and on the Redis limiter over fakeredis, a reported `total_tokens` of `10**30` gives a 200 with that `usage`, a follow-up 429 with `Retry-After: 11` (the follow-up's own reservation, a balance of exactly 0) and a 200 after one full refill; on Redis the stored `balance_units` is 0 and the PTTL is 120,001 ms within the 1 s tolerance. Counts of 59, 60 and 61 leave balances of 1, 0 and 0, a count of 30 is charged in full, and an Ollama count of `10**30 + 5` through an `httpx.MockTransport` is capped the same way. `scripts/check.py` passed (14 contract and 1071 other tests, 45 deselected). Mutation run: 17 mutants, each on the full suite, 16 killed (the cap removed; `max`; the cap at the reservation, twice it, the limit plus it, the limit plus 1 and minus 1; the cap from `remaining_tokens`; the cap skipped for the Ollama adapter or for anything but the mock entry; the cap skipped on the Redis limiter and on the in-memory one; the client's `usage` rewritten to the charge; a negative count clamped to 0; the `bad_response` charge taken from the limit); `<` in place of `<=` survives and is equivalent, since both return the limit when the count equals it. Review: approved; its three minor findings (a unit in a local name, a test comment, a `Mapping` type) were fixed before commit. The contract is unchanged | `app/limits/charge.py`, `app/api/chat.py`, `tests/limits/test_charge.py`, `tests/test_chat_settle_cap.py`, `tests/test_app_ollama.py`, `docs/ARCHITECTURE.md` |
| 2026-11-14 | - | T-209 planned from the backlog item "Cap the size of a provider reply", logged the same day from T-204 known gap 3 (the part T-208 does not close), which it replaces; ADR-0013 proposed (a `max_response_bytes` field on every HTTP provider, default 8 MiB, bounds 1 KiB to 64 MiB, counted over the decoded body while it streams, an oversized reply a `bad_response`, amending ADR-0010). By the owner's decision T-205 and T-206 now depend on T-209 as well as T-208, and the Phase 2 gate gains the ADR-0013 item. Research checked on this date against the installed `httpx` 0.28.1 and `httpcore` 1.0.9 and their documentation: no body size option; `aiter_bytes()` counts decoded bytes and `num_bytes_downloaded` encoded ones; gzip and deflate decode a whole raw chunk of up to 64 KiB at once; `MockTransport` streams an async-iterator body one part at a time. Neither OpenAI nor Anthropic documents a maximum response size. The limit values are chosen, not measured. Nothing was installed. The owner accepted ADR-0013 as written the same day, and ADR-0010's status now names it | `docs/DECISIONS.md`; this planning pull request |
| 2026-11-14 | T-209 | A provider reply's size is capped. `app/routing/config.py` adds `max_response_bytes` to the `ollama`, `openai` and `anthropic` provider types (a whole number from 1,024 to 67,108,864, default 8,388,608, not allowed on `mock`). `app/providers/http_body.py` adds `read_capped(response, max_response_bytes)`, which adds up the decoded chunks of `aiter_bytes()` and raises `bad_response` with the reply's status as soon as the total is above the limit; a body of exactly the limit is returned. `OllamaProvider` takes a keyword-only `max_response_bytes` (default 8,388,608, pinned by a test) and reads a 2xx body with it instead of `aread()`; the status is still read first and a non-2xx body is never read. `build_providers` passes each provider's configured value. An oversized reply is the ADR-0008 502, does not fall back, and stays charged as reserved (ADR-0013). This closes the reply-size part of T-204's known gap 3; T-208 closed the unbounded-count part. `docs/setup.md` documents the field and its cost, and `docs/ARCHITECTURE.md` lists `ollama.py` and `http_body.py` in the `app/providers/` layout. Known gap: memory can pass the limit by one decompressed chunk, which a gzip chunk of up to 64 KiB can make far larger than its size (ADR-0013 Consequences). | `python scripts/check.py` green (1119 passed, contract 14 passed, ruff, format and mypy clean); the first commit passes the check on its own (1098 passed). New tests: `tests/test_http_body.py` (limit, limit minus 1, 0 bytes, limit plus 1 with status 201, a limit crossed in the third of five chunks with chunks `[0, 1, 2]` served, gzip decoded to the limit and the limit plus 1 in one chunk and in 16-byte chunks, no body in the error); route table default, bounds, 5 rejected values on each HTTP type, no leaked value, rejected on `mock`, startup stop; adapter cap, status-first, no leak, 8 MiB default; whole app 502 with no fallback and the balance less two reservations, and a 200 at exactly 1,024 bytes. Mutation table of 26 mutants, all killed: the cap removed, `>=`, the limit plus and minus 1, `aiter_raw()` and `num_bytes_downloaded`, the whole body read first, the configured value ignored in `build_providers` and in the adapter, the default and both bounds each off by one in both directions, a retryable kind, a refunded kind, the body read before the status, the body in the error's cause, the status hard-coded to 200, a count per chunk, the adapter default off by one, a dropped chunk. Review APPROVE; the Minor findings on the memory-bound wording and the ARCHITECTURE wrapping were fixed, and an `Any` return type on a test helper was left. |
| 2026-11-14 | T-205 | Done. `app/providers/openai.py` adds `OpenAIProvider(client, api_key, *, max_response_bytes)`: `POST /v1/chat/completions` (default base URL `https://api.openai.com`) with the key, held as a `SecretStr`, put only into each request's `Authorization: Bearer` header, never into a client default header or an attribute in plain text. Request: `max_completion_tokens` from the client's `max_completion_tokens`, else `max_tokens`, only when given; `max_tokens`, `user`, `n` and `stream` never sent; `temperature` and each message's `name` forwarded when given. Response: the upstream `id`, `created` (a whole number of at least 0) and `model` kept; the first choice used; stop, length and content_filter mapped as they are, any other finish reason (tool_calls, function_call, null) a `bad_response`, checked before the content; null or absent content with a non-empty string `refusal` an empty reply with `content_filter`, a refusal beside string content keeping both the content and the finish reason, and null content with an empty or missing refusal a `bad_response` (owner decision, this task); `usage` and both counts required, and the total recomputed. The 2xx body is read with `read_capped` (ADR-0013). Every `ProviderError` is raised after its `except` block, so it has no `__context__` that could hold a body or a header echoing the key. `build_http_client` takes the provider's default base URL as a keyword, and `build_providers` builds `openai` with the key from its `api_key_env`; `BUILT_PROVIDER_TYPES` is `mock, ollama, openai`. By owner decision in this task, `_read_keys` in `app/routing/config.py` rejects at startup a key that, once trimmed, is not made only of visible ASCII (`!` to `~`), naming the variable and never the key, for `openai` and `anthropic`: without it, a key with an inner line break made every request a silent retryable `connection` failure, and a non-ASCII key a refunded 502. `docs/setup.md` documents the provider, that `base_url` is the host without `/v1`, and the key rule; `docs/ARCHITECTURE.md` lists the adapter and its wiring. The owner approved a plan of about 660 changed lines against the card's 300; the delivered diff is about 1,290 (production about 250, tests about 1,010, docs about 30), because the planned tests ran longer than estimated. Known gaps: (1) `ollama.py` still raises `from None` inside its `except` blocks and in `_text`, so a suppressed `__context__` can hold a reply string or an httpx message; nothing in Ollama's requests carries a key. (2) `build_providers` reads `table.api_keys[name]` directly, so a `RouteTable` built without `load_route_table` and missing a key would raise a bare `KeyError` at startup; no path builds one. (3) About 35 lines (`_text`, the status mapping, the exception and JSON blocks) repeat `ollama.py`; T-206 adds a third copy, after which an extraction is worth a card. (4) `created` and the counts have no upper bound; the counts are capped at settle (ADR-0012) | `python scripts/check.py` green (1314 passed, 45 deselected; ruff, format, mypy and contract clean); the first commit passes the check on its own (1147 passed). Mutation table of 68 mutants in round one, 67 killed: the survivor, the registry passing another provider's key, is killed by `test_each_openai_provider_sends_its_own_key`; round two (13 mutants, incl. each failure branch raising inside its `except`) left the decoding branch alive, killed in round three by a `__context__` check on every bad response, with the `_text` context and lone-surrogate mutants. Review APPROVE in each of three rounds; Minor findings on an unrecorded 404 claim, the suppressed context, a docstring and the shared visible-ASCII helper were fixed |
| 2026-11-14 | T-206 | Done. `app/providers/anthropic.py` adds `AnthropicProvider(client, api_key, default_max_tokens, clock, id_source, *, max_response_bytes)`: `POST /v1/messages` (default base URL `https://api.anthropic.com`) with `anthropic-version: 2026-10-21` and the key, held as a `SecretStr`, put only into each request's `x-api-key` header, never into a client default header. Request: every system message joined with `\n`, in order, into `system`, which is absent when there are none and present (possibly empty) when any exists; the other messages in order with `role` and `content` only; `max_tokens` from the client's `max_completion_tokens`, else `max_tokens`, else `default_max_tokens`; `temperature`, `name` and `user` never sent; `content-type` set by httpx's `json=`. Response: the `text` blocks joined in order with no separator, any other block type (thinking, redacted_thinking, tool_use, an unknown or missing type, a lookalike such as `Text`) ignored and a block that is not an object a `bad_response`; no text block gives an empty reply; end_turn and stop_sequence map to stop, max_tokens and model_context_window_exceeded to length, refusal to content_filter, anything else a `bad_response`; prompt tokens are `input_tokens` plus both cache fields, an absent or null cache field counting 0, and `input_tokens` and `output_tokens` required; `id` from the injected id source and `created` from the clock; `model` from the response, required and non-empty, and the upstream `id` ignored (owner decision, this task). Errors and the body follow T-205: `read_capped`, the status read before the body, every `ProviderError` raised after its `except` block so it has no `__context__`. `build_providers` builds `anthropic` with its key, `default_max_tokens`, the injected clock and the shared id source. By owner decision, the startup error for a type not built yet, unreachable once all four types are built (mypy `warn_unreachable` rejects it), is replaced by `typing.assert_never`, `BUILT_PROVIDER_TYPES` is deleted, and the T-202 criterion 7 test is replaced by `test_every_route_table_provider_type_is_built` and a literal `PROVIDER_TYPES` pin; mypy fails when a branch is removed (checked on a mutated copy), and a runtime test pins the guard, because mypy accepts a plain `raise` in its place. By owner request, `README.md`'s stale status lines (routing, the providers, the refund rule, the diagram, the phase table, the ADR table and a closed Redis-shutdown gap) were brought up to date. `docs/setup.md` and `docs/ARCHITECTURE.md` document the adapter; the OpenAI sentence in `docs/setup.md` now says a 429 falls back. The owner approved a plan of about 1,400 changed lines against the card's 350; the delivered diff is about 1,670 (production about 250, tests about 1,330, docs about 90). Known gaps: (1) a request made only of system messages is sent with `messages: []`; Anthropic's answer to it, and to an empty `system`, consecutive same-role messages or a first assistant message, has not been checked (owner decision, this task). (2) `anthropic-version: 2026-10-21` and its rejection of any temperature come from ADR-0010 (checked 2026-11-13) and were not re-checked; no test can prove them. (3) A reservation for an Anthropic route with no max field does not include `default_max_tokens`, so it understates the cost until settle (ADR-0010 consequence). (4) The adapter is a third copy of about 35 lines shared with `ollama.py` and `openai.py`; the backlog item "Extract the HTTP adapters' shared code" covers it. (5) T-205 gap 2 applies here too: `build_providers` reads `table.api_keys[name]` directly. (6) `assert_never` raises an `AssertionError` whose message holds a repr of the config; it is reachable only through a `RouteTable` built without validation | `python scripts/check.py` green (1546 passed, 45 deselected; ruff, format, mypy and contract clean). Mutation round one: 103 mutants, 98 killed; the survivors (a bad response's status hard-coded to 200, `assert_never` replaced by a raise, the registry building its own id source, message and system text stripped) were killed in round two (12 of 12, incl. 6 earlier kills re-run) by new tests. The test keys were renamed so they no longer start with `sk-`. Review round one CHANGES REQUIRED on docs only (429 fallback wording in `docs/setup.md`, the closed Redis gap and the refund wording in `README.md`, the diagram's order, the README update rule, a line wrap), all fixed |
| 2026-11-14 | - | T-210 planned from the backlog item "Extract the HTTP adapters' shared code", which it replaces, now that T-206 is merged (owner request, 2026-11-14). The shared code was read in `ollama.py`, `openai.py` and `anthropic.py` on this date: `_text`, `_whole_number`, `_required_count`, `_status_error` with `RATE_LIMITED_STATUS`, and the streamed request with its httpx exception handling and JSON parsing are identical in the OpenAI and Anthropic adapters (`_non_empty_text` is OpenAI's alone); Ollama has the same `_text`, `_status_error` and request block but raises `from None` inside its `except` blocks, and its counts use its own `_count` (absent is 0). The card moves the reply checks into a new `app/providers/fields.py` and the request into `post_json` beside `read_capped` in `http_body.py`; the OpenAI and Anthropic move is a pure refactor whose four test files must not change, and the Ollama move is the one behaviour change, in its own commit (T-205 known gap 1). `tests/test_ollama_provider.py` checks `__cause__` but not `__context__`, so no existing Ollama test changes. No ADR: no decision, interface or contract changes. Phase 2 gains the card, so its gate waits for it. A review of the first draft found the size total did not match its parts (now about 600, above the plan threshold), no mutant or test for the status each adapter forwards, and smaller gaps in the AST ban, the mutation list and the board's delivery order; all were corrected before the pull request | this planning pull request |
| 2026-11-14 | T-210 | Done. `app/providers/fields.py` (new) holds the reply checks the adapters shared: `text`, `non_empty_text`, `whole_number` and `required_count`, each raising `ProviderError("bad_response", status)` after any `try`, never inside an `except`. `app/providers/http_body.py` adds `post_json(client, path, *, body, headers, max_response_bytes) -> JsonReply` (a `NamedTuple` of `payload` and `status_code`) beside `read_capped`: one `POST` through `client.stream`, the status read first, a non-2xx mapped to `rate_limited` (429) or `upstream_status` without reading its body, a 2xx body read with `read_capped` and parsed as UTF-8 JSON, a timeout checked before `httpx.TransportError`, then `httpx.DecodingError`, every error raised after its `except`. The OpenAI and Anthropic adapters call `post_json` and `fields` and lost their own `_text`, `_non_empty_text`, `_whole_number`, `_required_count`, `_status_error`, `RATE_LIMITED_STATUS`, `json` import and exception handling; their four test files are unchanged. Behaviour change, on a line of its own: the Ollama adapter moved onto `post_json` and `fields.text` too, so its errors no longer carry a suppressed `__context__` (it raised `from None` inside its `except` blocks); its absent-is-0 count stays in `ollama.py` on `fields.whole_number`, as does Anthropic's absent-or-null-is-0 cache count. `docs/ARCHITECTURE.md` lists `fields.py` and `post_json`. The contract is unchanged. This closes T-205 known gap 1 (the Ollama `__context__`) and gap 3 (the repeated adapter code), and T-206 known gap 4; T-205 gap 2 (`build_providers` reading `table.api_keys[name]` directly) and gap 4 (no upper bound on `created`, counts capped at settle) stay open. The delivered diff is about 1,220 changed lines (990 added, 228 removed) against the card's about 600: production +167 and -220 (the code shrinks by 53 lines), tests +817 (the card said about 360), docs +6 and -4; the tests ran long on parametrised cases, the 25-case self-test of the AST scanner and the per-failure context checks, as in T-205 and T-206 | `python scripts/check.py` green (1727 passed, 45 deselected; ruff, format, mypy and contract clean); the first commit passes the check on its own (1678 passed, run on a scratch copy of that state). New tests: `tests/test_provider_fields.py` (every rejection at status 201 with no context), `tests/test_http_body.py` (request shape, `headers=None`, 200, 201 and 299, status mapping with no body read, no redirect, each timeout and transport type on send and mid-body, corrupt gzip, invalid UTF-8 and JSON, empty body, deep nesting, the limit exactly and plus 1, no body, URL or header value in any error), `tests/test_adapter_wiring.py` (a 201 that cannot be translated is `bad_response` with 201 for each adapter, the AST test and its scanner self-test), `tests/test_ollama_provider.py` (ten failures with no `__context__` or `__cause__`). Mutation run, one at a time with a timeout, on a scratch copy: 53 mutants, all killed (16 in `fields`, 21 in `post_json` and `read_capped`, 10 in the adapters, 6 extra on the adapters' translation); one timed out on its first run and was killed on two reruns, cause not identified. The verifier failed the first round: the deep-nesting cases used the default 1,024-byte limit, so the 100,000-byte body was rejected as oversize before `json.loads` and the `RecursionError` mutant was killed only by the adapter files; the cases now pass a limit of 200,000 and the mutant is killed in `tests/test_http_body.py` (run after the fix). Three scanner mutants (the first imported name only, the call check removed, any call counted) were killed after the review. Review APPROVE with four Minor findings (stale adapter docstrings, an import check on the first name only, an unused import passing the AST test, one orphaned line in ARCHITECTURE), all fixed. Two test placeholders starting `sk-` were renamed after the verifier's secret scan. Files: `app/providers/fields.py`, `app/providers/http_body.py`, `app/providers/openai.py`, `app/providers/anthropic.py`, `app/providers/ollama.py`, `docs/ARCHITECTURE.md`, `tests/test_provider_fields.py`, `tests/test_http_body.py`, `tests/test_adapter_wiring.py`, `tests/test_ollama_provider.py` |
| 2026-11-21 | T-207 | Done. `docs/routes.example.json` (new) is a route table with one provider of each real type (`local` ollama, `openai`, `claude` anthropic), a `fast` route (local, then openai) and a `smart` route (claude, then openai), and a default to `local`; keys appear only as `api_key_env` names. `tests/test_routes_example.py` (new) loads it through `Settings.from_env` with placeholder environment values and checks the provider types, the target order of both routes and the default, and that only the `openai` and `claude` providers hold keys, each with the value of its own variable. `docs/setup.md` gains "Running against real providers": the example, copying it outside the repository, the variables to export, a `curl` request, what fallback does, and the timeouts. The contract is unchanged, and no dependency was added. OWNER-CHECK done by the owner on 2026-11-21 against a local Ollama (version 0.40.17), model `llama3.2`: HTTP 200; `usage` `{"prompt_tokens": 28, "completion_tokens": 26, "total_tokens": 54}`; headers `x-ratelimit-limit-tokens: 60000`, `x-ratelimit-remaining-tokens: 59941`, `x-ratelimit-reset-tokens: 1s`, `x-tollgate-provider: local`, `x-tollgate-fallbacks: 0`. Runs against OpenAI and Anthropic: not run. The fallback to a second target with a real provider was not exercised | `python scripts/check.py` passed just now (ruff, format, mypy strict on 74 files, 14 contract tests, 1728 other tests passed, 45 deselected); a search of `docs/` for key patterns (`sk-`, `sk-ant-`, `AKIA`, a Bearer value, an `api_key` value) found no key-shaped value; mutation table for `tests/test_routes_example.py`: 18 mutants, each a changed copy of the example file, run one at a time on scratch copies: an unknown field (on a provider and at the top level), a target naming an undefined provider (in `fast` and in `default`), a reversed `fast` order, two swapped provider types, a missing `api_key_env`, a missing `default_max_tokens`, a changed `default`, a deleted route, an empty route, a deleted `default`, a low `timeout_seconds`, a bad variable name and a duplicate key were all killed; `claude`'s `api_key_env` changed to `OPENAI_API_KEY` survived the first version of the test and was killed once the test also asserted the `claude` key's value (re-run just now); one survivor remains by design, a renamed upstream model, because model names are not part of the schema; reviewer APPROVE with five Minor findings (the guide wording, the `claude` key assertion and this Log wording fixed in this pull request; two long lines in `docs/setup.md` and the unpinned model names accepted); the Ollama run is the owner's report, not a run in this repository |
| 2026-11-21 | - | Phase 2 gate signed off by the owner: all eight open gate items met (the three ADR items were ticked earlier, on 2026-11-13 and 2026-11-14). T-201 to T-210 are `done` on the board, the last being T-207 (pull request #41, merge commit `8516d0a`). The README and the ARCHITECTURE status line were updated in the close-out pull request: Phase 2 complete, T-201 to T-210 done, the one manual Ollama run recorded as the only real call and as a correctness check, not a measurement, OpenAI and Anthropic never called, the example route table and the real-provider guide listed. Evidence read back the same day, read-only: `ci` run `44911284742` succeeded on `main` at `8516d0a`; `python scripts/check.py` passed locally (14 contract tests, 1728 other tests, 45 deselected); routing tests assert the 404 with no reservation for an unknown model (`test_unknown_model_without_a_default_gets_404_with_no_reservation_and_no_limit_headers`), each target tried once in order, and exactly one reserve and one settle per request, also after a fallback and after every target failed (`tests/test_chat_routing.py`, `tests/test_router.py`); client shutdown is tested in `tests/test_app_wiring.py`; `requirements.txt` and `requirements-dev.txt` name no OpenAI, Anthropic or Ollama package, and a search of `tests/` for socket, urllib, requests and bare httpx client use found none; every Phase 2 card's Log row records a mutation table, and each survivor is explained (T-201 two equivalent, T-208 one equivalent, T-207 one by design, the rest killed in a later round, T-210 one run that timed out and was killed on two reruns with the cause not identified); the Ollama run is recorded in the T-207 row as the owner's report; 196 commits on `main`, all with the owner's author email (the first skeleton commit shows the name `apoorvrajdev`, the rest `Apoorv Raj`) and none with a co-author trailer or attribution line in its message. Phase 3 is not planned yet | `gh run list --branch main`, `python scripts/check.py`, `git log`, `grep` over `requirements*.txt`, `tests/` and `docs/TASKS.md` (all read-only) |
| 2026-11-21 | - | Phase 3 planned: cards T-301 to T-307, the Phase 3 gate and board rows, and five backlog items for deferred cache work; ADR-0014 (what is compared, who shares an entry, what a hit costs, how the threshold is chosen; amends ADR-0007 and ADR-0011) and ADR-0015 (Ollama `/api/embed`, cosine with `math.sumprod`, the cache in process memory, a hashing baseline for tests) proposed. No dependency is added. Ollama's embed API and source, embedding model licences, `math.sumprod`, numpy wheels, Redis 8 vector search, redis-py 8.1.0, fakeredis 2.40.0 and the semantic caches of LiteLLM, GPTCache, Portkey, Kong, RedisVL, LangCache and Cloudflare were checked on this date; nothing was installed | `docs/DECISIONS.md`; the planning pull request |
| 2026-11-21 | - | Decisions by the owner: ADR-0014 and ADR-0015 accepted as written, no revisions, and the Phase 3 plan approved. ADR-0007's status is now "Accepted - amended by ADR-0010, ADR-0012 and ADR-0014" and ADR-0011's "Accepted - amended by ADR-0014". The Phase 3 gate item for the ADRs is ticked; T-301 can start once the planning pull request merges | `docs/DECISIONS.md` (index and ADR headers); pull request #43 |
| 2026-11-21 | T-301 | Done. `app/cache/` (new) holds the embedders; nothing in the request path uses them yet. `embedder.py`: the `Embedder` protocol (a read-only `identity` property and `async def embed(text) -> array[float]`, a unit vector) and `EmbeddingError(kind, status_code)` with ADR-0010's kinds and the message `embedding failed: <kind>`, followed by `(HTTP <n>)` when there is a status; it is not a `ProviderError`, so the router's fallback cannot catch it. `hashing.py`: `HashingEmbedder` (identity `hashing:v1`), as the card says: lower-cased, one space of padding at each end, 3-character windows hashed with `blake2b(digest_size=8)` read big-endian, modulo 512, counted and L2-normalised; the empty string raises `bad_response` with no status. By the owner's decision the windows are encoded with `surrogatepass`, so a lone surrogate is hashed instead of raising; every valid string gives the same bytes as strict UTF-8. `ollama_embedder.py`: `OllamaEmbedder(client, model, *, max_response_bytes=1_048_576)` (identity `ollama:<model>`) posts `{"model", "input", "truncate": false}` to `/api/embed` through `post_json`, turns each `ProviderError` into an `EmbeddingError` with the same kind and status, raised after the `except` block, and checks the reply: an object whose `embeddings` is a list of exactly one list of numbers, each a float or a non-bool int converted with `float()` (an integer too large for a float is rejected, not raised), a norm `math.sqrt(math.sumprod(v, v))` that is neither 0 nor non-finite, and the length of the first vector that passed every check; the vector is divided by its norm again. By the owner's decision the norm check alone also enforces ADR-0015's "non-empty" and "each element finite" rules (an empty vector has norm 0; a NaN or infinite element makes the norm NaN or infinite), so no separate check exists to be an equivalent mutant. The contract is unchanged. `docs/ARCHITECTURE.md` is not changed: the T-306 card owns making `Embedder` and `EmbeddingError` final in section 3 and adding `app/cache/` to section 5, so until then its layout still says "Planned: `cache/`". About 635 changed lines (production 173, tests 456, docs 5), above the card's about 400; the owner approved the size at the plan stage | `python scripts/check.py` green (1836 passed, 45 deselected; ruff, format, mypy and contract clean); the first commit passes the check on its own (1747 passed, run on a scratch copy of that state). New tests: `tests/test_hashing_embedder.py` (the error messages; identity; length 512, typecode `d` and norm 1 within 1e-12 on five inputs; the pinned non-zero entries of "Banana", `{60: 2, 136: 1, 198: 1, 441: 1, 504: 1}` over the square root of 8, computed from the card's description by a separate script; two instances; case; different texts; one window for one character; the empty string; `lower` not `casefold`; a lone surrogate), `tests/test_ollama_embedder.py` (identity; the exact body with `truncate is False` on two calls; `[3, 4]` to exactly `[0.6, 0.8]` on 200 and 201; 28 bad replies each on 200 and 201, among them NaN, Infinity, `1e400`, a 400-digit integer of each sign, a zero and a signed-zero vector and `[1e308, 1e308]`, whose norm overflows under `math.sumprod` but not `math.hypot`; the length of the first reply and a rejected first reply not setting it; the default cap at exactly 1,048,576 bytes and one more, and a configured cap; connection, timeout, 429, 400, 404 and 500 with one request each; 13 failures with no body, text, password or host in the message, repr or traceback and no `__context__` or `__cause__`). Mutation run, one at a time with a timeout, on a scratch copy: 59 mutants, 58 killed, 0 timeouts; the survivor sets the length again after every check has passed, which is equivalent (a passing reply already has that length); the forms that store the latest length or store it before the checks are killed. Review APPROVE with three Minor findings: the pinned-count comment now gives the computation, a test's `kind` parameter is typed `ProviderErrorKind`, and this row records the deferred ARCHITECTURE update. Files: `app/cache/__init__.py`, `app/cache/embedder.py`, `app/cache/hashing.py`, `app/cache/ollama_embedder.py`, `tests/test_hashing_embedder.py`, `tests/test_ollama_embedder.py` |
| 2026-11-21 | T-302 | Done. `app/settings.py` adds `CacheSettings` (embedder, model, URL as a `SecretStr`, threshold, TTL, maximum entries) and `Settings.cache`, which is `None` when `TOLLGATE_CACHE_EMBEDDER` is unset; the cache is parsed after the route table. Rules as the card says: the embedder is exactly `ollama`; the model is required and stripped; the URL defaults to `http://localhost:11434` and set but blank is an error; the threshold matches `0\.[0-9]{1,4}`, `1` or `1\.0{1,4}` and is at least 0.5 (the pattern is also the upper bound); TTL 60 to 604,800 (default 3,600) and maximum 1 to 100,000 (default 1,000), where set but blank is an error and never a default; a cache variable set while the embedder is unset, even blank, is an error naming it; errors are reported in declaration order (embedder, model, URL, threshold, TTL, maximum) and never hold a value. Owner decisions: the threshold, TTL and maximum are stripped like the model (so `0.9` with a trailing newline is accepted), the embedder value is not; leading zeros are accepted for TTL and maximum, as for the other numbers. `app/main.py` adds `build_embedder` and the `embedder=` keyword of `create_app()`: with the cache on it builds an `httpx.AsyncClient` (URL, 5-second connect timeout, 10 seconds for read, write and pool, the `http_transport=` transport), appends it to `owned_clients` so shutdown closes it, and keeps an `OllamaEmbedder` on `app.state.embedder` (`None` when the cache is off); an injected embedder builds no client; passing one while the cache is off raises `ValueError`. Beyond the card, by the owner's decision: `httpx.InvalidURL` from a malformed URL becomes a `SettingsError` naming `TOLLGATE_CACHE_EMBEDDER_URL` with no value and no `__context__`, raised before the Redis client is built. The URL is otherwise not checked for syntax at startup. `docs/setup.md` documents the six variables and the rules. The contract is unchanged; `docs/ARCHITECTURE.md` is not changed (its sentence on the order of owned clients is now slightly stale; T-306 owns the update). About 533 changed lines (production 165, tests 354, docs 14), above the card's about 320 and the about 430 the owner approved at plan time; the tests ran long on the bound and boundary cases | `python scripts/check.py` green (1927 passed, 45 deselected; ruff, format, mypy and contract clean); the first commit passes the check on its own (1921 passed). New tests: `tests/test_settings_cache.py` (cache off; exact values and defaults, each default on its own; the embedder exactly `ollama` against seven values; blank and unset model; blank URL; accepted and rejected thresholds including `0.4999`, `1.0001`, five decimals, `.9`, `1e0`, `nan`, fullwidth and Arabic-Indic digits and an embedded newline; both bounds of TTL and maximum with blank, huge and non-ASCII values; each of the five variables set without the embedder, also blank; error order; route-table error before cache error; no value in any error; the URL masked in `repr`; frozen), `tests/test_app_cache.py` (cache off; client URL and timeouts; no connection at build; registered and closed at shutdown and not before; model and transport reach the request; injected embedder builds no client; `embedder=` with the cache off raises; a malformed URL with a password is a `SettingsError` before the Redis client is built). Mutation run, one at a time with a timeout, on a scratch copy: 75 mutants, 73 killed, 0 timeouts; one survivor was an unpinned order of the route-table error and the cache error (the owner's plan puts the cache last), killed by a new test; the other, the `ValueError` check moved after `build_providers`, is equivalent (only unopened provider clients are built first and the app is never returned). After review three test cleanups were made and two affected mutants (swapped timeouts, a blank embedder read as unset) re-run and killed. Review APPROVE with Minor findings, all in tests, fixed. Files: `app/settings.py`, `app/main.py`, `docs/setup.md`, `tests/test_settings_cache.py`, `tests/test_app_cache.py` |
| 2026-11-22 | T-303 | Done. `app/cache/semantic.py` (new): `Ticket`, `Hit`, `Miss`, `Skip`, `partition_key` and `InMemorySemanticCache`; nothing in the request path uses it yet. `partition_key` hashes `{"caller_id", "embedder", "request"}`, where `request` is `model_dump(mode="json")` with the last message's `content` key deleted, as `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=True)`, and returns the SHA-256 hex digest of that ASCII text; a fixed request's canonical text and digest are pinned. `lookup` returns `Skip` before embedding unless the last message is `user`, catches only `EmbeddingError` (also a `Skip`), scans only its own partition's entries, ignores entries at or past `stored_at + ttl_seconds`, and hits on a `math.sumprod` similarity at least equal to the threshold: the most similar wins, a tie goes to the most recently stored (a store sequence number), and a hit moves the entry to the most recently used end without extending its life. `store` keeps only a response with exactly one choice whose finish reason is `stop` and whose `model_dump_json()` is at most 65,536 bytes in UTF-8; it keeps those bytes, the vector copied into `array("d")` and the provider's name, and a hit validates the bytes back into a `ChatResponse`. When full, a store evicts the oldest stored entry if it has expired, else the least recently used one (both orders are `OrderedDict`s, so eviction is O(1)); an emptied partition is deleted. Owner decisions: a public `__len__`; no `SemanticCache` Protocol, and `docs/ARCHITECTURE.md` is not changed (T-306 owns both); one test reads the private `_partitions` to kill the empty-partition leak mutant. `tests/fakes.py` adds `FakeEmbedder` (fixed vectors per text, records calls, optional error). Known gaps: ADR-0014's Partition bullet says validation accepts a lone surrogate in `model`, but the route rejects it with a 400 (`min_length` decodes the text; `user` and `name` are accepted), so the `model` case is built with `model_copy` and the ADR text is left for the owner (owner decision); checking only the oldest stored entry finds an expired entry whenever one exists only while the clock does not step back, and after a wall-clock step back a live entry may be evicted while an expired one keeps its slot (the count bound holds and expired entries are never returned; recorded in the module docstring, not testable with the forward-only fake clock). The contract is unchanged. About 685 changed lines (production 177, tests 506), above the card's about 400 and the about 500 the owner approved at plan time; the owner accepted the size when it passed 500 | `python scripts/check.py` green (1974 passed, 45 deselected; ruff, format, mypy and contract clean). New tests: `tests/test_semantic_cache.py`, 47 cases (the shared key; 13 single-field changes including `n` and `stream` set against absent and the embedder identity; the pinned key; a lone surrogate in `user`, an earlier `name` and `model`; `[user, assistant]` and `[user, system]` skip with no embedder call, `[system, user]` and `[assistant, user]` looked up; a similarity of exactly 0.75 hits and reports 0.75, `0.7499999999999999` misses; the more similar of two wins in both store orders; a tie goes to the more recently stored, not the more recently used; another caller or model never hits; the ticket's key and vector; a hit at 59.999 seconds, a miss at exactly 60, a hit not extending life; the card's expired-before-LRU scenario, plain LRU with a hit counted as a use, the count never above the maximum; `length`, `content_filter`, zero and two choices not stored; 65,536 UTF-8 bytes stored and 65,537 not, with 2-byte characters so a count in characters would accept both; the stored bytes unaffected by a later change to the response; the stored vector unaffected by a later change to the ticket; an emptied partition deleted; an `EmbeddingError` gives `Skip` and a `RuntimeError` propagates). Mutation run, one at a time with a 120-second timeout, on a scratch copy: 44 mutants (every one on the card plus 12 more); round one killed 42, and the two survivors (the vector copy removed, an empty partition kept) were killed by two new tests; all 44 killed again after the review changes. Review APPROVE with three Minor findings: `_by_store` became an `OrderedDict` (a plain dict measured about 10 times slower at popping its front at 100,000 entries), the lone-surrogate test takes its requests from the parametrize list, and the clock step-back limitation is recorded here. Files: `app/cache/semantic.py`, `tests/test_semantic_cache.py`, `tests/fakes.py` |
| 2026-11-22 | T-304 | Done. `eval/cache_pairs.json` (new): 80 English pairs written for this project, 40 `same` (8 each of `synonym`, `word_order`, `register`, `question_vs_request`, `concise_vs_verbose`, by the owner's decision) and 40 `different` (8 each of `unrelated_topic`, `negation`, `changed_number`, `swapped_order`, `changed_entity`), ids `same-NN` and `<category>-NN`. `app/cache/evaluation.py` (new): `load_pairs` (a JSON array of objects with exactly the five string fields, a known label and category, unique ids, no blank text; errors name the pair index and field, never its text), `dataset_sha256` (SHA-256 with CRLF normalised to LF, by the owner's decision, so a Windows checkout and CI agree), `THRESHOLDS` (`i / 100` for 50 to 100), and `evaluate(pairs, embedder, clock)`: each pair in its own new `InMemorySemanticCache` (threshold 0.5, one entry, fixed caller and model), the first text looked up and stored, the second looked up, the hit similarity placing the pair under the cache's `>=` rule; a `Skip` on either lookup raises `SkippedLookupError` naming the pair, the lookup and the embedder's failure kind and status (a small wrapper records the `EmbeddingError` the cache swallows), so no report exists. The report holds the date (UTC, from the clock), the embedder identity, the counts, 51 rows (same hits and rate, wrong hits and rate, wrong hits per category) and the recommendation: the lowest threshold below 1.00 with no wrong hit, or none. `render_markdown` labels a `hashing:` embedder "lexical baseline, not semantic"; `report_as_json` gives the same data. `scripts/eval_cache.py` (new): `--embedder hashing\|ollama` (default `hashing`), `--model` (required with Ollama), `--url` (stripped, blank refused; both refused with hashing), `--output`; the Ollama path reuses `build_embedder` (the gateway's client and timeouts) and reads `GET /api/version` capped at 4,096 bytes, accepting only a version matching `[0-9A-Za-z.+_-]{1,64}`. The URL is never printed: every failure is one fixed line, an `InvalidURL` becomes "--url is not a valid URL", and argparse's "unrecognized arguments" message is replaced so a mistyped flag cannot repeat the URL. Exit 0, 1 (nothing printed to stdout, no JSON written) or 2. `docs/cache-eval.md` (new): the dataset, the method, the limits (the Clopper-Pearson bounds, a threshold chosen on its own data, lexical baseline), how to run, and the hashing baseline from a recorded run: recommended 0.98, where no `same` pair hits either, so the baseline is useless for caching, as expected of a lexical measure; Ollama runs are left to T-307. `docs/ARCHITECTURE.md` section 5: the `eval/` row, `eval_cache.py` in the `scripts/` row, and `evaluation.py` in `app/cache/` (T-306 still owns the full description). Dataset changes made during review: same-01, negation-01, -05, -07 and -08 rewritten so each `same` pair clearly has one answer and each negation is an explicit "not". Known gaps: the mutant that computes the date in local time is killed only on a non-UTC host (the owner's machine, not CI); the recorded baseline and the pinned digest must be re-recorded together after any dataset change. The contract is unchanged; no new dependency. About 1,150 hand-written lines (production 479, tests 629, docs about 106 plus the pasted run of about 60 lines), above the card's about 380 and the about 730 approved at plan time; the owner was told when it passed 730 and kept it after a trim that removed only tests killing no unique mutant | `python scripts/check.py` green (2030 passed, 45 deselected; ruff, format, mypy and contract clean); the first two commits each pass the check on their own (1978 and 2030 passed, run on a copy of each staged state). New tests: `tests/test_cache_eval_dataset.py`, 4 tests with the standard library only (counts per label and category, ids matching their label or category, exactly five string fields, non-blank printable texts that differ); `tests/test_cache_evaluation.py`, 26 tests (52 cases): thresholds exactly `i / 100`; hits at exactly `float("0.57")`, 0.5 and 1.0 and misses one step above; exact rates and per-category counts in order; separate caches; a `Skip` on the first or the second lookup stopping the run with its cause and no later embedding; an unstored answer; the same/different guard; the UTC date and the identity; five recommendation cases including 0.995 and 1.0 giving none; the real dataset loaded; ten malformed datasets; the CRLF digest; the digest pinned to the recorded baseline; the exact Markdown header, rows and both recommendation lines; the lexical label; the full hashing run (51 rows, every setting, the exact 0.50 row and recommendation, the JSON first row and recommendation); the Ollama run on a `MockTransport` with a padded URL (one version call, 160 embed calls, no URL in stdout, stderr or JSON); five Ollama failures and a connection error printing one fixed line and no report; an invalid URL; a malformed dataset; an unwritable output; six bad usages, none repeating the URL. Mutation run, one at a time with a 120-second timeout, on a scratch copy: 58 mutants (every one on the card plus 22 more, the reviewer's nine and 6 on the dataset), 57 killed; the survivor removes the first-lookup hit check, which is unreachable because each cache starts empty. Round one also left a doc error (0.98 called the only zero-wrong threshold below 1.00, though 0.99 also has none), fixed; round three left `--url` unstripped alive, killed by the padded URL. Review: CHANGES REQUIRED with one Major (the rendered table, the recommendation line and the JSON values were unchecked) and seven Minors, all fixed; second review APPROVE with no findings. Files: `eval/cache_pairs.json`, `app/cache/evaluation.py`, `scripts/eval_cache.py`, `tests/test_cache_eval_dataset.py`, `tests/test_cache_evaluation.py`, `docs/cache-eval.md`, `docs/ARCHITECTURE.md` |
| 2026-11-22 | T-305 | Done. `create_app()` builds one `UuidIdSource`, keeps it on `app.state.id_source` and passes it to `build_providers`, which gains the keyword `id_source: IdSource \| None = None` and builds a new `UuidIdSource` inside the call when it is `None` (not a default evaluated at import), so the direct call in `tests/test_chat_routing.py` is unchanged; the mock, Ollama and Anthropic providers share that source. With the cache on, `create_app()` builds an `InMemorySemanticCache` on the app's embedder (built or injected), the injected clock and the threshold, TTL and maximum from `Settings.cache`, kept on `app.state.cache`; with the cache off it is `None`. No request uses the cache yet (T-306). The contract is unchanged; `docs/ARCHITECTURE.md` is not changed (T-306 owns it); no new dependency. About 290 changed lines (production 27, tests 260), above the card's about 200 | `python scripts/check.py` green (2042 passed, 45 deselected; ruff, format, mypy and contract clean); the first commit passes the check on its own (2033 passed). New tests: `tests/test_app_cache_state.py`, 12 tests: one id source shared by the mock, Ollama and Anthropic providers (one instance built, `app.state.id_source` is it, ids 1 to 4 in order); `build_providers` uses a given source and builds a new one inside each call without one; the cache off gives `None`; the cache embeds through an injected embedder and through the one the app built; a hit at 59.5 seconds and a miss at 60; a similarity of exactly 0.5 hits and 0.5 - 2**-10 misses; the maximum of 2 evicts nothing at 2 entries and one at the third; and each of TTL, threshold and maximum taken from settings values that differ from the defaults (120, 0.75, 3). Mutation run, one at a time with a 120-second timeout, on a scratch copy: 12 mutants (every one on the card plus 3 more), 11 killed in round one; the survivor, a default `UuidIdSource()` evaluated once at import, was killed by a new test. Review APPROVE with four Minor findings: a vacuous assertion and an overlapping test removed, a test for the built embedder added, and one style note on the `None` assignment left as is. Files: `app/main.py`, `tests/test_app_cache_state.py` |
| 2026-11-22 | T-306 | Done. `app/api/chat.py`: after an allowed reservation, with `app.state.cache` set, the route looks the request up under `caller.caller_id`. A `Hit` runs no target, settles once with an actual amount of 0 and answers the stored response through `model_copy` with a new `id` from `app.state.id_source` and `created = int(clock.now_seconds())` (the providers' rule), `x-tollgate-provider` set to the stored provider and `x-tollgate-fallbacks: 0`. A `Miss` runs the route; after the settle its 200 is offered to `store` through a `partial` bound to the ticket, so a settle error stores nothing. A `Skip` or the cache off runs the route. `set_success_headers` writes the limit, routing and cache headers on the two 200 returns only, so the cache header never enters the shared limit-header dict that the 429 and 502 use. The route reads the cache, the id source and the clock from `app.state` on every request. The OpenAPI 200 gains `x-tollgate-cache` (`string`, enum `hit`, `miss`, `skip`), and the descriptions of `x-tollgate-provider` and `x-tollgate-fallbacks` say what they mean on a hit; the snapshot was regenerated in the route commit (13 lines added, 2 changed). `app/cache/semantic.py` adds the `SemanticCache` Protocol (`lookup`, `store`), which ADR-0014 makes final; `app/main.py` assigns the cache through a local typed `SemanticCache \| None`, so mypy checks that `InMemorySemanticCache` satisfies it. `tests/fakes.py`: `ScriptedProvider` gains `finish_reason` (default `stop`, owner decision). `docs/ARCHITECTURE.md`: section 2 shows a hit settling 0 and the cache row; section 3 replaces the illustrative `get`/`put` with the final `Embedder`, `EmbeddingError`, `Hit`, `Miss`, `Skip` and `SemanticCache`; section 5 describes `app/cache/`, the embedder and cache on `app.state`, and the cache in the chat-route paragraph; by the owner's decision the status line ("no caching yet") and the owned-clients sentence (missing the embedder client from T-302) were also corrected. Behaviour the card leaves open: the header stays `miss` when `store` refuses an answer (ADR-0014's definition), and an exception from the lookup other than an `EmbeddingError` is a 500 that stays charged as reserved, like a limiter error. Known gaps: the three unchanged chat test files do not themselves assert `skip`; that is asserted in the new file over the cache-off paths; the mutant that drops the type annotation on the cache in `create_app()` is equivalent at run time and mypy accepts it, so the Protocol check there is a static guard only. The contract changes as the card allows; no new dependency. About 690 hand-written changed lines (production 131, tests 486, docs 71) plus the snapshot diff, within the about 650 to 750 the owner approved at plan time | `python scripts/check.py` green (2069 passed, 45 deselected; ruff, format, mypy and contract clean); the route commit passes the check on its own. `git diff main` is empty for `tests/test_chat_rate_limits.py`, `tests/test_chat_routing.py` and `tests/test_chat_completions.py`. New tests: `tests/test_chat_cache.py`, 16 tests (25 cases): the cache off says `skip` after a fallback, on the built-in mock route and on an Ollama route that never calls `/api/embed`; a miss served by the second target after a timeout, then a hit 42.5 seconds later with the next id, `created` 1042, provider `second`, fallbacks 0 and each provider called once; a hit's exact reserve and settle-0 calls with the balance checked by a follow-up (952, where settling the usage gives 915 and keeping the reservation 941); a 429 for a cached prompt, a 404 and a 400 with no embedding; a `length` answer and a 502 storing nothing; an `EmbeddingError` giving `skip` with nothing stored, then a miss and a hit naming `first`; the header absent on 400, 401, 404, 429 and 502 with the cache on and off; another caller getting a miss; the whole app with the Ollama embedder and one `MockTransport` serving a miss then a hit (two embed calls with `truncate: false`, one chat call, the app's id source and clock); an ineligible request giving `skip` with no embedding; a `RuntimeError` from the embedder being a 500 with no settle and no provider call; a settle error after a miss storing nothing. `tests/test_chat_openapi.py`: the exact 200 header set gains `x-tollgate-cache`; the enum and both new descriptions are pinned. Mutation run, one at a time with a 120-second timeout, on a scratch copy: 44 mutants (every one on the card plus extras, two of them named by the review); 43 killed, 0 timeouts. "Stored after a 502" has no typed form (a failed route carries no answer) and was run as a fabricated answer stored in the 502 branch, killed; the survivor is the dropped annotation above, equivalent. Review APPROVE with six Minor findings, all fixed: two missed mutants (the provider from the route's last target, a lookup error swallowed as a skip) now killed, a stale docstring sentence, the Protocol check, the 65,536-byte cap in ARCHITECTURE, and a helper name. Files: `app/api/chat.py`, `app/cache/semantic.py`, `app/main.py`, `tests/test_chat_cache.py`, `tests/fakes.py`, `tests/test_chat_openapi.py`, `tests/contract/openapi.json`, `docs/ARCHITECTURE.md` |
| 2026-11-23 | T-307 | Done. The eval run against a local Ollama is recorded in `docs/cache-eval.md` (new section `all-minilm`), run at the owner's instruction ("go ahead and pull and run") on the owner's machine. Settings: Ollama 0.40.17, model `all-minilm:latest` (ID `1b226e2802db`), Python 3.13.2, Windows 11, 2026-11-23, dataset SHA-256 `73aa98d6...9e1f` (40 same, 40 different pairs). The first attempt failed with an embedding timeout while the model loaded; the second ran clean. Result: no threshold below 1.00 has zero wrong hits (0.99: 2/40 same hits, 4/40 wrong hits; 0.98: 4/40 and 4/40; `negation` pairs hit through 0.88, `changed_number` and `swapped_order` through 0.78), so the run recommends none. `docs/setup.md` gains a "Semantic cache" section: the variables, the statement that no threshold is recommended and why, the `x-tollgate-cache` values, what a hit costs (reservation first, settle 0, one embedding call per eligible request), the limits, that a threshold of `1` may never hit, and that each process has its own cache; a stale sentence ("no request uses it yet") was corrected. The optional second model (`bge-m3`) and the optional gateway run with a `miss` then a `hit` were not run. The contract is unchanged; no dependency, no test added. About 140 changed lines of docs, against about 120 on the card | `python scripts/check.py` green (2069 passed, 45 deselected; ruff, format, mypy and contract clean). No mutation table: no test was added. A search of `docs/setup.md` and `docs/cache-eval.md` for key-like strings found nothing. OWNER-CHECK (criterion 1): the run is recorded; the owner confirms it with the approval of this PR. Files: `docs/cache-eval.md`, `docs/setup.md`, `docs/TASKS.md` |
| 2026-11-23 | - | Phase 3 gate signed off by the owner: all nine open gate items met (the ADR item was ticked earlier, on 2026-11-21). T-301 to T-307 are `done` on the board, the last being T-307 (pull request #51, merge commit `535ff46`). The README, the ARCHITECTURE status line and this phase's heading and gate were updated in the close-out pull request: Phase 3 complete, T-301 to T-307 done, the cache described as optional and off by default, ADR-0014 and ADR-0015 listed, and the one recorded eval run reported as it is: `all-minilm` found no threshold without wrong hits, so no threshold is recommended anywhere, and the run is one model on 80 pairs chosen and measured on the same data. Evidence read back the same day, read-only: `ci` run `45194691428` succeeded on `main` at `535ff46` (job `lint and test`); `python scripts/check.py` passed locally on that tree (14 contract tests, 2069 other tests, 45 deselected); the cache tests are in `tests/test_semantic_cache.py` (lookup, partition, expiry, eviction), `tests/test_chat_cache.py` (lookup only after the reservation, so a 429, 404 and 400 never reach the embedder; a hit reserves once and settles 0 once; an embedder failure is a `skip` that is still served; a `length` answer and a 502 store nothing; the header absent on every status but 200) and `tests/test_chat_openapi.py` (the header in the snapshot); the Ollama embedder is tested through `httpx.MockTransport` in `tests/test_ollama_embedder.py` and the app's client close in `tests/test_app_cache.py` and `tests/test_app_wiring.py`; the harness runs the whole dataset on the hashing baseline in `tests/test_cache_evaluation.py` on every CI run; a search of `tests/`, `app/` and `scripts/` for `socket`, `urllib`, `requests` and `aiohttp` imports found none, and `requirements*.txt` name no embedding or provider package; the embedding model was called only by hand, once, outside the tests and CI (T-307, run at the owner's instruction); every Phase 3 card's Log row records a mutation table, and each survivor is explained (T-301 one equivalent, T-302 one killed by a new test and one equivalent, T-303 and T-305 all killed in a later round, T-304 one unreachable, T-306 one equivalent, T-307 added no test); 238 commits on `main`, all with the owner's author email and none with a co-author trailer or attribution line in its message. Phase 4 is not planned yet | `gh run view`, `python scripts/check.py`, `git log`, `grep` over `tests/`, `app/`, `scripts/`, `requirements*.txt` and `docs/TASKS.md` (all read-only) |
| 2026-11-23 | - | Phase 4 planned: cards T-401 to T-409, the Phase 4 gate and board rows, and five backlog items (a request id, a cache size metric, `prometheus_client`, image publishing, TLS in front of the gateway), with the Dependabot item extended to Docker. Proposed: ADR-0016 (a JSON request log and Prometheus metrics with the standard library, labels and fields from bounded sets only, `/metrics` behind its own token, a monotonic clock; amends ADR-0013 and ADR-0014), ADR-0017 (a digest-pinned non-root image, a Compose stack, a CI `container` job and its localhost exception; the deployment target is one host running that stack; amends ADR-0006) and ADR-0018 (an open-loop load generator measuring from each request's due time, a fake upstream, a validity check, recorded runs only). No dependency is added. Checked on this date, with nothing installed: `prometheus_client`, the OpenTelemetry SDK and exporter, structlog, python-json-logger, the Prometheus text format and naming practice, FastAPI's native telemetry, uvicorn's logging and signal handling, the `python` and `redis` images and their licences, the Compose specification, GitHub's runner image, hadolint, hosted free tiers, k6, Locust, vegeta, oha and wrk2, and the Envoy, Kong and LiteLLM benchmark methods | `docs/DECISIONS.md`; the planning pull request |
| 2026-11-23 | - | Decisions by the owner: the Phase 4 plan approved, with all nine card sizes, including the five above the plan threshold (T-401, T-402, T-404, T-406 and T-407). ADR-0016 accepted as written, including the Prometheus text format written by the project instead of `prometheus_client`. ADR-0017 accepted as written, including one host running the Compose stack as the only deployment target. ADR-0018 accepted with one added line: the 10% lag threshold is a chosen operating margin, not measured from data. ADR-0006's status is now "Accepted - amended by ADR-0017", and the statuses of ADR-0013 and ADR-0014 are "Accepted - amended by ADR-0016". The Phase 4 gate item for the ADRs is ticked; T-401 can start once the planning pull request merges | `docs/DECISIONS.md` (index and ADR headers); pull request #53 |
| 2026-11-24 | T-401 | Done. The code now reports what each request did, timed on a monotonic clock, and nothing logs or exports it yet. `run_route` takes a required `monotonic_clock` keyword and returns an `Attempt` (provider name, outcome, duration) for every provider call, held in `attempts` on both `Served` and `RouteFailed` with no default, so a return site that forgets it fails mypy. The outcomes are `ok`, the five failure kinds, `reply_too_large` and `error` (an exception that is not a `ProviderError`). `read_capped` raises `ReplyTooLargeError`, a `ProviderError` of kind `bad_response`, so the route still ends charged as reserved. `Skip` carries `not_eligible` or `embedder_failed`. `create_app()` takes `monotonic_clock=` and keeps it on `app.state.monotonic_clock`. Tests: 2099 pass (2069 before). Four existing assertions that compared a whole `RouteFailed` now compare `charged`, as the card allows. 40 of 40 mutants were killed. The card's mutant "ReplyTooLargeError raised inside an except" cannot exist, because `read_capped` has no except block, so it is recorded as not applicable. One feedback round: the three-target test used a 429 where the card says 503, and the wall-clock-only case of criterion 6 was missing; both were added. Size: 443 lines added and 33 removed across 12 files, plus the docs, against an estimate of about 540 (the card said about 450, and the owner approved 540 before the code was written). The pull request waits for the owner's approval. | Commits for the three code changes and one test fix; `python scripts/check.py` passed (14 contract tests, 2099 passed, 45 deselected); ARCHITECTURE section 3 and the section 5 prose updated; contract unchanged |
| 2026-11-24 | T-401 | Known gap, recorded at the owner's instruction after the T-401 merge (pull request #55, merge commit `b94f451`): whether attempt durations stay correct across several attempts in one request when the wall clock drifts is untested. The criterion 6 case where only the wall clock moves covers one attempt, through the chat route; the multi-attempt tests move only the monotonic clock. `run_route` reads no wall clock, so no mutant of it can fail this today, but T-406 (the fake upstream and the fixed-rate runner) and T-407 (the load report) depend on attempt timing under fallback, so each should watch for it and add a multi-attempt case where the wall clock moves between attempts if its numbers rely on those durations. Nothing was changed in code | Merge commit `b94f451` on `main`; `tests/test_route_timing.py` (single-attempt wall-clock case); `tests/test_router.py` (multi-attempt cases) |
| 2026-11-24 | T-402 | Done. Every HTTP request now writes one JSON line to the logger `tollgate.request` with the ADR-0016 fields and nothing else. `RequestMiddleware` is a pure ASGI middleware that times the request on the monotonic clock, reads the status from `http.response.start`, and reports after the last body message, or once with the status sent (500 if none) when the handler raises, and the exception propagates. It maps the path to `/v1/chat/completions`, `/health`, `/metrics` or `other`. The chat route fills a `ChatRecord` kept in the ASGI scope state, so it belongs to one request; a 400 or 401 has no chat fields, a 404 and a 429 have them null, a hit has no attempts, a 502 has no serving provider, and a cache that is off has no cache result. `settle_capped` is true only when the reported total is above the capacity. `JsonFormatter` writes ASCII only, refuses NaN, and gives any other logger only `time`, `level`, `logger`, `message` and `exception_type`. `deploy/logging.json` sends `tollgate.request` and uvicorn's loggers to stdout and silences `uvicorn.access` (level CRITICAL, no propagation), an addition beyond the card that the owner approved. FastAPI's native telemetry is off. Tests: 2161 pass (2113 before). 27 of 27 mutants were killed, the card's list plus extras; no feedback round was needed. Known limits: a cancelled request is not logged, an observer that raises on the error path replaces the handler's exception, and `method` is written as the server received it (bound it before T-404 uses it as a label). Size: about 1,250 lines against the card's 600; the owner approved about 1,020 before the code was written, and the test matrix made up most of the difference. The pull request waits for the owner's approval. | Commits `feat(observability)` and `build(deploy)`; files `app/observability/`, `app/api/chat.py`, `app/main.py`, `deploy/logging.json`, `tests/test_request_log.py`, `tests/test_request_log_config.py`, `docs/ARCHITECTURE.md` section 5; `python scripts/check.py` passed (14 contract tests, 2161 passed, 45 deselected); contract unchanged |
| 2026-11-24 | T-403 | Done. `app/observability/metrics.py` holds `Counter`, `Histogram`, `MetricsRegistry` and `CONTENT_TYPE`, and writes Prometheus text format 0.0.4 with the standard library only. Nothing in the app uses it yet. The registry creates its metrics, writes them in registration order, and rejects a duplicate name, an invalid metric or label name, a label starting with two underscores, and `le` on a histogram. A counter may take one label on first use, and then declares the allowed values of its other labels; every declared label set is written at 0 before use. A rejected call changes no state. Bucket bounds are always written as floats (`le="1.0"`), `_sum` is always a float, first-use series are grouped by the declared order of the other label and then by first use, and there is no `_created` series. Guards beyond the card were kept: duplicate label names or sets, bad bucket bounds and bad first-use declarations. Tests: 2278 pass (2161 before). The grammar checker in the test file has its own self-test. Verification took three rounds: round one had 2 of 83 mutants surviving (a list-valued label, a double-underscore label on a histogram), round two found a third on the first-use counter path, and all were then killed by added tests. Known gaps, left open: a bare string is accepted for `label_values` and `label_names` and read one character at a time, several rejection tests match only the word label, and an integer above about 1.8e308 raises `OverflowError`; the first is noted on the T-404 card, which also carries the collision of a metric name with a histogram suffix. Before the merge the owner asked about the `label_sets` asymmetry (`Histogram` positional, `Counter` keyword); it was an oversight, so `label_sets` is now keyword-only on `Histogram` and `MetricsRegistry.histogram` too, and a test pins all four signatures. Size: about 946 lines (module 321, tests about 625) against the card's 400; the owner approved about 700 before the code was written, so it went past the approved figure and the owner was told at the first full draft. The pull request waits for the owner's approval. | Commits `feat(observability)` for the module and tests; `python scripts/check.py` passed (14 contract tests, 2278 passed, 45 deselected); contract unchanged; `docs/ARCHITECTURE.md` not changed, since T-404 wires the module in |
| 2026-11-24 | T-404 | Done. With `TOLLGATE_METRICS_TOKEN` set, `GET /metrics` exports the ADR-0016 metric set for the app's own requests, and nothing else can read it. `Settings.metrics_token` is a `SecretStr`; blank, under 32 characters, or equal to an API key each fail startup naming the variable. `create_app()` builds one `MetricsRegistry` per app on `app.state.metrics` (`app/observability/request_metrics.py`), with every known label set exported at 0 and `status` as the one first-use label, and the middleware's second observer feeds it from the request record. The route (`app/observability/endpoint.py`) exists only with the token, is left out of the OpenAPI document, and answers any failure with the 401 `invalid_metrics_token`; `_digest` in `app/api/auth.py` became the public `digest_of` so both share it. Carried items closed: no metric name equals another plus a histogram suffix (a test checks the whole set), the constructors get tuples, and no label is `method`. A scrape is counted after it is rendered, so it never shows itself, and an unset `/metrics` counts as `other`. A `bad_response` 502 stays charged as reserved, so `tollgate_tokens_charged_total` includes it. Known gap: a POST to `/metrics` gets an unauthenticated 405 when the token is set, which shows the route exists. Contract unchanged | Branch `feat/t-404-metrics-endpoint`; files `app/settings.py`, `app/api/auth.py`, `app/main.py`, `app/observability/request_metrics.py`, `app/observability/endpoint.py`, `docs/setup.md`, `docs/ARCHITECTURE.md`, `tests/test_settings_metrics_token.py`, `tests/test_metrics_endpoint.py`, `tests/test_request_metrics.py`, `tests/test_openapi_snapshot.py`, `tests/test_request_log.py`; `scripts/check.py` 2347 passed; two mutation passes, 47 mutants run: pass one 24, 22 caught, 2 survivors (a chat completion counted on a 500, tabs stripped from the token) killed by new tests; pass two 23 run on the token check, settings and completion counting (24 listed), 18 caught, 3 survivors (a non-breaking space trimmed, a lookalike scheme such as `Bearerx` accepted, a non-ASCII token not compared as UTF-8) killed by three more tests, 2 equivalent (an empty-token check removed, `status < 500` for `== 200`); constant-time compare reviewed, not mutated; snapshot unchanged, also with the token set; the same non-breaking-space and lookalike-scheme cases are not probed on the API-key path (see the Backlog) |
| 2026-11-24 | T-405 | Done. `docker compose up` starts the gateway on Redis from a pinned, non-root image, and a new `container` CI job proves it on every pull request. `Dockerfile` is multi-stage on `python:3.13-slim` pinned by index digest (uid 10001, exec-form `CMD`, one worker); `.dockerignore` excludes everything and lists back `requirements.txt`, `app/` and `deploy/logging.json`; `/app` holds only `.venv`, `app` and `deploy`. `compose.yaml` has `gateway` (Redis limiter, `/health` healthcheck, `127.0.0.1:8000` only), `redis` (`redis:7.4.12`, no published port) and an `ollama` service in a profile; the key and token are `${VAR:?...}` references only; the route table is mounted read-only at `/config/routes.json`. `scripts/smoke_container.py` (standard library only) has checks as functions over status, headers and body. The job runs hadolint v2.15.1 (pinned by digest, no ignored rule), compose config, build and up, the smoke script, and checks of a Redis `tollgate:bucket:*` key, the JSON `http_request` log line, `id -u` (10001), the `/app` listing and a graceful stop. Recorded from the first green run: exit code on `docker compose stop gateway` is 0 and `Application shutdown complete.` is in the log. Both checks green on PR 60 (run 45441669935). Contract unchanged. Three CI wiring bugs found only by running the job: a YAML plain scalar holding `: ` made the first run fail in 0s, `::add-mask::` was written to the env file, and `grep -q` under `pipefail` was replaced by capturing output first. Known gaps: the key and token test reads only the `environment:` lines of `compose.yaml`; OWNER-CHECK 7 decided by the owner on 2026-11-24: `container` becomes a required status check on `protect-main`, the same as `lint and test`; the owner adds it in the ruleset settings | Branch `build/t-405-container`; files `Dockerfile`, `.dockerignore`, `compose.yaml`, `deploy/routes.compose.json`, `scripts/smoke_container.py`, `.github/workflows/ci.yml`, `docs/ARCHITECTURE.md`, `tests/test_deploy_files.py`, `tests/test_smoke_container.py`; `scripts/check.py` 2358 passed; mutation table 8 of 8 caught (digest removed, a second `FROM` without a digest, Redis tags differing, a literal key in `compose.yaml`, a smoke check accepting 401 as 200, one accepting 200 as 401, one ignoring a missing limit header, a zero metric count accepted, a non-mock provider in the route file) |
| 2026-11-24 | T-406 | Done. Load can be sent at a fixed arrival rate against a fake upstream reached through the real `openai` adapter; the raw samples come out, and the statistics and report stay with T-407. `scripts/fake_upstream.py` has `build_app(delay_seconds, sleep)`, a Starlette app that answers `POST /v1/chat/completions` with a fixed body holding every field the adapter checks after `await sleep(delay_seconds)`; its `main` serves it with uvicorn on `127.0.0.1:8100` with `--delay-ms` defaulting to 50. `deploy/bench/routes.fake-upstream.json` (scenario B: provider `fake-upstream`, type `openai`, key from `TOLLGATE_BENCH_UPSTREAM_KEY`) and `deploy/bench/routes.mock.json` (scenario C). `scripts/bench_load.py` part one: `LoadPlan` (integer rate, duration and warm-up), `due_time` (start plus i divided by the rate, never accumulated), and `run_load` on an injected `MonotonicClock`, sleep and `httpx.AsyncClient`, which starts each request as its own task in a `TaskGroup`, reads the hand-over time inside the task just before the request goes to the client, and returns per request the due, hand-over and end times, the status or the transport error class name (never its message), the warm-up flag, and the peak in flight; `make_client` has no connection cap unless one is given and ignores proxy settings in the environment. Tests run on a virtual-time event loop whose clock jumps to the next timer only when every task waits, so nothing sleeps for real. The owner approved about 670 lines over the card's 450 (final 691), and the port, env name, provider name, 30 s timeout and catching `httpx.HTTPError`. Review round one left two mutants alive (a connection cap by default through `make_client`, and the peak taken as the last count instead of the maximum); both now have kill tests. Contract unchanged. Known gaps: the rate, duration and warm-up are integers only | Branch `feat/t-406-load-runner`; files `scripts/fake_upstream.py`, `scripts/bench_load.py`, `deploy/bench/routes.fake-upstream.json`, `deploy/bench/routes.mock.json`, `tests/fakes.py` (`load_script`), `tests/test_fake_upstream.py`, `tests/test_bench_runner.py`, `tests/test_deploy_files.py`, `docs/ARCHITECTURE.md`; `scripts/check.py` 2384 passed; mutation table 24 of 24 caught (due from the previous answer, a closed loop, hand-over after the response, hand-over read in the scheduler, end read before the post, warm-up off by one, warm-up left out of the count, due accumulated, a transport error raised or not caught, the in-flight count not lowered on error, the peak never set or taken as the last count, the fake's delay ignored or skipped, the delay read as seconds, a default delay of 40 ms, GET allowed on the fake, the route file's port changed, a connection cap by default in `client_limits` or through a dropped `limits=`, proxy settings trusted, the JSON content type dropped) |
| 2026-11-24 | T-407 | Done. `python scripts/bench_load.py` turns a T-406 run into a JSON report and a Markdown table with ADR-0018's figures, validity check and settings. Latency runs from the due time to the end and lag from the due time to the hand-over; percentiles are `statistics.quantiles(n=100, method="inclusive")` (p50, p95, p99 and the maximum for latency; p50, p99 and the maximum for lag). Warm-up requests are counted apart, with their own error counts, and left out of every figure and of validity (owner decision). A run is valid only with no non-200, no transport error, and a lag p99 at most 10% of the latency p99, always computed from the raw p99s; a p99 is published only from 10,000 measured requests and otherwise shown as "too few samples". Errors are counted by status and by transport error class. The achieved rate is measured requests over the last measured end minus the first measured due (owner decision), or none over an empty span. The report records the scenario, rate, duration, warm-up, connection cap, limiter, tokens per minute, capacity, the route file's SHA-256 with LF line endings (`routes_sha256_lf`, never its content), the upstream delay, the server, the body's size (79 bytes) and SHA-256, the git commit (`git rev-parse HEAD`, or unknown), Python version, OS, CPU count, same or separate machine, the peak in flight and the generator's CPU time. The key is read from the variable named by `--api-key-env`, must be printable ASCII, and is never printed or written; the URL is never recorded, and argparse errors never repeat a rejected value. The gateway's settings are optional flags shown as null or n/a (owner decision). Exit codes: 0 valid, 3 invalid with the report still printed and written, 1 no report (key missing or unusable, route file unreadable, output directory missing, which is checked before any load is sent), 2 usage. The owner approved about 900 lines over the card's 450, then accepted about 1100 (final 1184). Review round one found no test on the JSON figure values and ten minor gaps (the empty-span rate, a zero warm-up, a URL without a host, the cap reaching the real client, a non-ASCII key, values repeated by argparse, a late output failure, the digest's line endings, the lag reason's text, the host facts); all now have tests. Contract unchanged. Known gaps: the in-process run on `create_app()` checks the report's shape and counts only, because FastAPI runs the gateway's sync dependencies in threads, so its timings are not deterministic; per-scenario flag requirements are left to T-409 | Branch `feat/t-407-load-report`; files `scripts/bench_load.py`, `tests/test_bench_report.py`, `docs/ARCHITECTURE.md`; `scripts/check.py` 2436 passed; mutation table 53 of 53 caught (latency from the hand-over, lag from the end, warm-up in the figures, the error counts, the achieved rate or the floor count, warm-up errors invalidating the run, `exclusive` quantiles, `n=99` or a cut index off by one, the floor at 9,999 or `>`, validity skipped below the floor, `<` in the lag check, a lag share of 0.11, a non-200 or a transport error left out of validity, 200 counted as an error, the key or the route file content in the report, the digest without LF normalising, the maximum as the last value, exit 0 for an invalid run, the machine flag inverted, CPU time as the end reading, an unchecked git result, a p99 shown below the floor, a blank or non-printable key accepted, the empty-span guard, JSON figures swapped or dropped, a zero warm-up rejected, a URL without a host or unstripped, the cap not passed to the client, argparse repeating a value in single or double quotes, the output check after the run, wrong host facts, a hard-coded lag reason) |
| 2026-11-25 | T-408 | Done. `python scripts/bench_cache.py` has two modes. `scan` fills one partition of an `InMemorySemanticCache` with N seeded unit vectors of D dimensions for each combination of `--entries` and `--dimensions` (several values each; the defaults are ADR-0018's grid of 1,000, 10,000 and 100,000 by 384 and 1,024, owner decision), and times `lookup` with `timeit.Timer(...).repeat(number=1)` at a similarity threshold of 2.0 that no entry reaches, so every lookup scans every entry and misses; it reports the minimum, median and maximum per lookup. Each timed lookup is run to completion directly inside a running event loop (owner decision), and a lookup that pauses on an await stops the run at run time with a fixed error, exit 1 and no report (owner requirement). A combination whose vectors (entries x dimensions x 8 bytes) exceed `--max-vector-bytes` (default 1 GiB, chosen) is skipped and reported as skipped; only one combination's cache is held at a time. Seeds are non-negative, because `random.Random` seeds with an int's absolute value. `embed` builds the gateway's `OllamaEmbedder`, records the Ollama version with `fetch_ollama_version`, discards one call and times `--calls` sequential calls (default 100); an `EmbeddingError` stops the run with its kind-and-status message and no figure, and the URL is never printed or written. Both modes write a Markdown report and, with `--output` (added, owner decision), a JSON report with their settings, the git commit, Python version, OS and CPU count. `Parser` and `positive_int` in `scripts/bench_load.py` are now public and shared with `bench_cache.py` (owner request), which also imports `ScriptError` and `fetch_ollama_version` from `scripts/eval_cache.py`. No figure is published here: the owner's runs are T-409. Size about 1,290 changed lines against the card's ~400 (the owner approved ~900, and was told of the overrun). Review round one found that the previous combination's cache stayed alive during the next fill, so peak vector memory could pass the limit; fixed. | `scripts/bench_cache.py`, `tests/test_bench_cache.py`, `scripts/bench_load.py`, `docs/ARCHITECTURE.md`; `scripts/check.py` 2477 passed; mutation table 34 of 34 caught after one kill test was added for a removed `coroutine.close()` (a threshold of 0.0 or -2.0 that lets entries hit, each entry in its own partition, the fill stopped one short, the discarded call kept, minimum and median swapped, `>=` in the memory guard, an `EmbeddingError` swallowed on the discarded call, mid-run or in the runner, the previous cache kept alive, the pause guard returning None or another message, `close()` removed, the miss check removed or neutered, the fill check removed with one entry fewer allowed, `number=repeats` or one repeat too many, `median_low`, 4 bytes per value, `break` after a skip, normalising dropped, the query drawn after the entries, the default seed or limit passed instead of the given one, another default URL, the URL in the report, a report written after a failure, the version fetch removed, one timer start for every call, a negative seed accepted or zero rejected) |
| 2026-11-25 | T-409 | Done. The owner's benchmark runs are recorded and the operations guide is written. Load: 15 runs (scenarios A, B and C, B and C each with the memory limiter and the Redis limiter, 3 repeats each) at 40 requests/s, 250 s measured after 10 s of warm-up, 10,000 measured requests each, on Windows 11 (Windows-11-10.0.26300-SP0, 16 CPUs, Python 3.13.2), with the generator and the server on the same machine; the fake upstream delay was 50 ms and the limiter's tokens per minute and capacity were both 110,400. Every run is invalid under ADR-0018's lag rule (lag p99 above 10% of latency p99): the lag p99 was 14.0 to 16.1 ms in all 15, consistent with the Windows timer tick of about 15.6 ms (not measured), and every other validity condition held (all 200, no transport errors). Latency p99 in ms: A 81.5 to 84.4, B memory 94.5 to 111.3, B Redis 120.1 to 145.8, C memory 25.8 to 29.1, C Redis 33.1 to 39.4. B minus A per repeat: memory p50 +2.5 to +3.7 ms and p99 +12.9 to +29.8 ms; Redis p50 +5.1 to +14.2 ms and p99 +38.5 to +64.2 ms. Cache scan (minimum per lookup): 8.0 ms at 1,000 entries of 384 dimensions, 2,136 ms at 100,000 entries of 1,024. Embedding latency: `all-minilm` on Ollama 0.40.18, 100 calls, median 14.81 ms, minimum 12.62 ms, maximum 47.35 ms. `docs/setup.md` gains running with Docker Compose, Metrics, Logs, running the benchmarks, and one process per container. A Backlog item records that scenario B did not follow targets of 100 requests/s and above in diagnostic runs. The contract is unchanged, and no dependency or test was added. OWNER-CHECK, confirmed in writing by the owner on 2026-11-25: all 15 load runs are published as invalid under the lag rule (Windows timer tick against the 10% limit). Ramp diagnostic files: not committed, per owner instruction (2026-11-25) to keep diagnostic ramp-* runs untracked since they back no published figure. Compose run: not run. Investigated and found Compose could not isolate the lag-rule question (the generator's own clock is the failure, not the gateway's platform) and would not cleanly test the throughput ceiling either; the owner accepted this reasoning and chose option 3 (publish at 40/s, report as invalid) instead, 2026-11-25 | `python scripts/check.py` passed just now (exit 0: ruff, format, mypy strict, contract, 2477 tests passed, 45 deselected); no test is added, so there is no mutation table; the OpenAPI snapshot is unchanged; a search of the committed files (`docs/benchmarks.md`, `docs/setup.md`, `docs/TASKS.md` and the 17 reports) for key patterns (`sk-`, `sk-ant-`, `AKIA`, `ghp_`, a Bearer value, an `api_key` value, the benchmark keys) found no key-shaped value; verifier, round one: every figure in `docs/benchmarks.md` recomputed from the committed reports with 0 mismatches, each load report names the OS, CPU count, Python version, same-machine flag and server, the setup guide's commands, variables, metric names, log fields and the series count (127 for one provider before any request) checked against the code; its one FAIL, the first wording of the Backlog item (figures with no committed source), was fixed by rewording it to what the ramp reports hold; reviewer, round one: CHANGES REQUIRED (the ramp row said B stopped following its target a little above 40/s, when it followed 50/s and fell behind at 100/s and above; the Backlog item's figures; the waivers; minor items on the setup guide and the embedding note), all fixed; reviewer, round two: APPROVE, with every number in `docs/benchmarks.md` recomputed again and four Minor items (the ramp row's in-flight peaks and transport errors, the Redis targets in the Backlog item, the Compose wording, and the settings row for A) fixed in this pull request; accepted: the Windows timer tick of about 15.6 ms is an external fact and not measured here, and the figures come from invalid runs |
| 2026-11-26 | - | Phase 5 planned: cards T-501 to T-507, the Phase 5 gate and board rows; ADR-0019 (no published image and no hosted demo, amending ADR-0017) proposed. Owner decisions taken before planning: the 19 ramp reports are committed (reversing the 2026-11-25 choice); the throughput ceiling's suspected cause in the `openai` adapter was never recorded and is treated as unconfirmed, so T-502 profiles it with a timebox, and otherwise the write-up says "suspected, unconfirmed"; the demo is text only (curl output, `/metrics` text, JSON log lines), with no Prometheus or Grafana; there is no hosted demo. The Phase 4 gate is left for the owner's sign-off, with its README and ARCHITECTURE item delivered by T-504 and T-506. No research beyond ADR-0017's 2026-11-23 sources was needed; nothing was installed | `docs/TASKS.md`; `docs/DECISIONS.md`; the planning pull request |
| 2026-11-26 | - | Decisions by the owner: ADR-0019 accepted as written, so ADR-0017's status is now "Accepted - amended by ADR-0019"; the Phase 5 card sizes approved, including T-506 at about 450 changed lines, a docs-only overrun; the owner runs the localhost runs of T-502 and T-505 by hand, as in T-409, from commands given at the start of each task; the Phase 4 gate signed off except "README and ARCHITECTURE describe what is built", which stays open and is carried into T-504 and T-506. A second review of the plan was requested, because T-502's scope and settings changed after the first | `docs/DECISIONS.md` (index and ADR headers); `docs/TASKS.md` (Phase 4 and Phase 5 gates) |
| 2026-11-26 | - | Second plan review: CHANGES REQUIRED with 4 Major findings, all in T-502, and 9 Minor; all fixed. T-502 now defines "follows" (achieved rate at least 98% of the target, peak in flight at most 50, no transport error) from the ramp baselines; names the ramp report each run reproduces and its settings; runs every gateway with the metrics token and the JSON log config, sending stdout to a file, and says that the ramp runs recorded neither; locates the time with three comparisons (attempt against request duration, the app's timer against the generator's latency, generator CPU against the A and C controls), stating what each cannot separate; adds a third conclusion form, "not reproduced"; quotes every run's commands and marks variation reports; and records that `cProfile` sees only the main thread. Its run budget drops from eight to seven, because step 2 reuses step 1's runs. Minor: diagram edges may be backed by the `Dockerfile` or `deploy/`; the T-504 packages and modules named apart; T-505's check is an in-process replay, with a fresh key on the Compose stack; `gh pr checks` added to T-502 to T-507; ADR-0019 keeps its "Decision (proposed)" label, as accepted ADRs do | The planning pull request |
| 2026-11-26 | - | Third plan review: APPROVE, with 7 Minor findings, all fixed in the planning pull request. T-502: the "suspected, unconfirmed" rule now applies only when B at 100/s did not follow and no variation confirms a cause; a failing A or C control voids comparison (c); comparison (b) uses the request log's median over the measured window, with the histogram as a cross-check, and its gap includes the generator's lag; comparison (c) uses generator CPU per request; the profile run counts only if Ctrl+C left a non-empty profile file. The Phase 5 intro names the "not reproduced" outcome | The planning pull request |
| 2026-11-26 | T-501 | Done. The 19 ramp reports in `docs/benchmarks/` are committed byte for byte (on 2026-11-26 the owner reversed the 2026-11-25 choice to leave them uncommitted; the T-409 Log row is unchanged). `docs/benchmarks.md` gains "Ramp (diagnostic)": a table generated from the reports with one row per run (scenario, limiter, target and achieved rate, measured seconds and requests, non-200 and transport errors, peak in flight, lag p50 and lag p99 or "withheld", validity as each report's `invalid_reasons`), the shared settings, what the table shows, and the two suffixed reports described from their fields plus the owner's account of their purpose (2026-11-26: `-full` to get 10,000 measured requests so the p99 publishes; `-cpucheck` a re-run with per-process CPU sampling, where the owner saw the gateway at 100% CPU and the generator at 44 to 67%, figures not in any report and with the sampling method unrecorded). The "Not run, or not published" ramp row is removed, and the page intro says the ramp runs are diagnostic and all invalid. The Backlog item on the `openai` throughput cites the reports and T-502. The contract is unchanged; no dependency or test was added | `python scripts/check.py` passed just now (exit 0: ruff, format, mypy strict, contract, 2477 tests passed, 45 deselected); no test is added, so there is no mutation table; verifier, round one: FAIL on criterion 2 (B with Redis was claimed at 25/s, which was never run; the run date and order had no source in the reports; the Backlog said 20 s for every run); round two: PASS on all four criteria, with 228 table cells recomputed from the JSON and 0 mismatches, the route files' SHA-256 with LF matching the reports, and the 19 files' SHA-256 recorded before commit; reviewer, round one: CHANGES REQUIRED (the same Redis 25/s claim, plus 8 Minor items), all fixed; round two: APPROVE, with two wrapping items fixed; a search of the reports, `docs/benchmarks.md` and `docs/TASKS.md` for key patterns found no key-shaped value; the post-commit comparison of the committed blobs with the recorded SHA-256 is in the pull request |
| 2026-11-27 | T-502 | Done. Conclusion: not reproduced on commit `e280d37`: B followed 100/s in run `ceiling-B-memory-r100.json` (99.66/s, peak in flight 17, no transport error). The owner ran the four step 1 runs by hand on 2026-11-27 on `main` at `e280d37`: B memory at 50/s and 100/s, A at 100/s and C memory at 100/s. All four followed their targets and all are invalid under ADR-0018 for the lag rule only. B followed 100/s, so the method stopped after step 1: the three comparisons, the profile and the two variations were not run, and no cause is claimed. `docs/benchmarks.md` gains "Throughput ceiling investigation": the runs table, the shared settings, the quoted commands (env values withheld), the runs against their ramp reports (generator CPU per request for B at 100/s 14.39 ms in the ramp run, 4.25 ms here), gateway and upstream CPU from `netstat` and `Get-Process` samples (raw samples quoted; the gateway not sampled in A, which has no gateway), `/metrics` excerpts, and what was not done. These runs set the metrics token and the JSON log config to a file, which the ramp runs did not record; the section names that as a difference, not a cause. The Backlog item now records the result and keeps B with Redis at 100/s, B at 200/s and above, and Linux or WSL2 open. The owner confirmed the conclusion wording (OWNER-CHECK, 2026-11-27). No `app/` change, no dependency, no test; the contract is unchanged | `python scripts/check.py` passed (exit 0: 2477 tests passed, 45 deselected); no test is added, so there is no mutation table; tables generated from the reports and `cpu.txt` by a script, and the verifier recomputed every figure with its own scripts: PASS, no mismatch; `git diff --stat 75384aa e280d37 -- app scripts deploy` is empty; reviewer: APPROVE with 5 Minor findings, all fixed (both B gateway commands quoted, the shells' `source env.sh` stated, the C upstream request count, the Backlog wording, the intro sentence); files: `docs/benchmarks.md`, `docs/benchmarks/ceiling-A-r100.json`, `ceiling-B-memory-r50.json`, `ceiling-B-memory-r100.json`, `ceiling-C-memory-r100.json`, `docs/TASKS.md` |
| 2026-11-28 | T-503 | Done. `docs/findings.md` tells the three findings, each as question, method, result, meaning and limits, with every figure linked to its page or report: no safe cache threshold for `all-minilm` on the 80-pair dataset; the lag p99 of 14.0 to 16.1 ms in all 15 invalid load runs, consistent with the Windows timer tick (external, not measured), with the ramp's seconds-long lags kept separate; and the throughput ceiling in T-502's form, quoted verbatim: not reproduced on commit `e280d37`: B followed 100/s in run `ceiling-B-memory-r100.json`. It adds how the figures were produced (ADR-0005, ADR-0018) and next steps from two Backlog items. Every figure from an invalid run is called invalid in its own sentence or bullet. Deviations from the card text: the card says all 8 changed-number pairs hit through 0.78, but the all-minilm table in `docs/cache-eval.md` shows 8 of 8 at 0.79 and 6 at 0.80, so the page says through 0.79; the 0.78 in that file's prose and in the T-307 Log row is true but not the highest such threshold, and is left unchanged here as out of scope. The card's no default threshold and cache off by default are worded as earlier ADR-0014 and ADR-0015 decisions that fit the result, not as results of the run. The Summary describes scenario B as a whole, not the gateway alone, since the cause is unknown. Not yet linked from the README or ARCHITECTURE (T-506, T-504). No `app/` change, no dependency, no test; the contract is unchanged | `python scripts/check.py` passed just now (exit 0: ruff, format, mypy strict, contract, 2477 tests passed, 45 deselected); no test is added, so there is no mutation table; verifier, round one: FAIL (six sentences with run figures lacked the word invalid, and one said All 19 short ramp runs when one ran 100 s); round two: FAIL (the 50 ms delay bullet); round three: FAIL (the next-steps bullet); round four: PASS on every criterion, with 175 numeric tokens mapped to `docs/cache-eval.md` or `docs/benchmarks.md` (0 unmapped), the run figures recomputed from the committed JSON reports (0 mismatches), the dataset SHA-256 recomputed with LF, 29 links and anchors resolving and 0 non-ASCII code points; one Minor clause on generator CPU reworded after round four and rechecked with the token script and the check command; reviewer, round one: CHANGES REQUIRED (2 Major: an unsupported did not expect, and the Summary placing the ceiling in the gateway; 6 Minor), all fixed; round two: APPROVE with 3 Minor, all fixed and covered by verifier rounds three and four; a search for key and attribution patterns found nothing; files: `docs/findings.md`, `docs/TASKS.md` |
