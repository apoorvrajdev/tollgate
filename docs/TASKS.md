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
- [ ] CI runs on Python 3.13 for every pull request and push to `main`, in a job named exactly `lint and test`
- [ ] `lint and test` is a required status check in the `protect-main` ruleset, which keeps no bypass actors
- [ ] The commit guards are covered by tests, and those tests passed a mutation check
- [ ] The OpenAPI snapshot test is in place and runs as part of `scripts/check.py`
- [ ] ADR-0004 and ADR-0005 accepted or revised (ADR-0003 accepted 2026-11-09)
- [ ] Every commit is authored by the owner, with no co-author trailers; merge commits created by GitHub may
      show GitHub as committer

## Board

Delivery order in Phase 0: T-001, T-003, the owner makes `lint and test` a required check, then T-002, then
T-004. The rows below are in that order; the cards further down are listed by ID.

| ID | Title | Phase | Status | Depends on |
| --- | --- | --- | --- | --- |
| T-000 | Project skeleton | 0 | done | - |
| T-001 | Toolchain: pyproject, pinned requirements, check script | 0 | done | - (ADR-0003 accepted) |
| T-003 | Continuous integration | 0 | done | T-001 |
| T-002 | Tests for the commit guards | 0 | done | T-003, and `lint and test` set as a required check (OWNER-CHECK) |
| T-004 | Typed app skeleton and OpenAPI snapshot | 0 | done | T-001, T-003 |

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

## Later phases (broken into tasks at each gate)

| Phase | Epic |
| --- | --- |
| 1 | Token-aware rate limiting: token counting, Redis token bucket (client decided by ADR), 429 with rate-limit headers, mock provider, `/v1/chat/completions` |
| 2 | Model routing: rules, fallback on provider failure, Ollama, then OpenAI and Anthropic adapters |
| 3 | Semantic caching: embeddings, similarity lookup, thresholds, invalidation |
| 4 | Docker Compose, observability, reproducible load benchmarks |
| 5 | Demo and write-up |

### Requirements that carry into the task cards

These are written into the cards when each phase is planned.

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
