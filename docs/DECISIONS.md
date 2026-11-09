# Decisions

Architecture Decision Records (ADRs). Each records one decision: its context, the options, the choice and its
consequences. Statuses: **Proposed** (awaiting the owner), **Accepted**, **Accepted - amended by ADR-NNNN**
(still in force, partly changed by a later ADR), **Superseded by ADR-NNNN**, **Rejected**.
Accepted decisions change only through a new ADR.

| ADR | Decision | Status | Date |
| --- | --- | --- | --- |
| [0001](#adr-0001) | Single-author repository with enforced commit identity | Accepted | 2026-11-09 |
| [0002](#adr-0002) | Pull-request delivery flow | Accepted | 2026-11-09 |
| [0003](#adr-0003) | Python toolchain, one check command, plain pip | Proposed | 2026-11-09 |
| [0004](#adr-0004) | OpenAI-compatible API; providers added in a fixed order; no paid calls in tests | Proposed | 2026-11-09 |
| [0005](#adr-0005) | Verification safeguards: contract snapshot, mutation checks, evidence-first numbers | Proposed | 2026-11-09 |

Open decision for Phase 1: how the rate limiter talks to Redis (client library, Lua scripts, test double).
It gets its own ADR before any limiter code is written.

---

## ADR-0001

**Single-author repository with enforced commit identity** · Accepted · 2026-11-09

- **Context:** The owner is the sole author and contributor of this repository.
- **Options:** (a) rely on discipline; (b) enforce with local hooks.
- **Decision:** (b). Only the owner commits, pushes and merges. Hooks in `.githooks/` reject commits whose author
  or committer email differs from `authorguard.email`, messages with co-author or attribution trailers, and
  assistant configuration files. Nothing related to assistant tooling is committed.
- **Consequences:** Clean, accurate history. Hooks are enabled per clone (`git config core.hooksPath .githooks`,
  `git config authorguard.email "<email>"`) and need Node.js. Hooks only run locally, so this protects the owner's
  own commits; it is not a server-side control.

## ADR-0002

**Pull-request delivery flow** · Accepted · 2026-11-09

- **Context:** ADR-0001 says who commits, not how a change reaches `main`. Committing straight to `main` gives no
  review step, no place for checks to run, and no record of why a group of commits belongs together.
- **Options:** (a) commit directly to `main`; (b) pull requests merged by squash; (c) pull requests merged with
  a merge commit.
- **Decision:** (c), because every atomic commit stays visible in the history of `main` while the merge commit
  groups them into one reviewed change.
  - Work is delivered on short-lived branches. Task work uses `<type>/t-xxx-<slug>`. Docs-only or process work
    without a task card uses `docs/<slug>`, and its pull request body states "Task: none (process change)".
  - Each branch holds atomic Conventional Commits: one logical change per commit, each leaving the checks
    passing. No empty or artificially split commits.
  - Each branch is merged through a pull request with a merge commit (no squash, no rebase), only after all
    checks pass. The branch is deleted after the merge.
  - Nothing is pushed directly to `main`. Every commit, push and merge uses the owner's Git identity.
- **Consequences:** Changes reach `main` only through a merged pull request. A task becomes `done` in the pull
  request that delivers it. Once continuous integration exists (T-003), its checks gate every merge. Repository
  settings (merge commits only, delete merged branches, a ruleset on `main`) are configured by the owner.

## ADR-0003

**Python toolchain, one check command, plain pip** · Proposed · 2026-11-09

- **Context:** The default shell on the development machine resolves `python` to an MSYS2 build that pip treats
  as a non-Windows platform, so compiled dependencies such as pydantic-core fail to install. A standard
  Windows Python 3.13 is available through `py -3.13`.
- **Options:** (a) ruff and mypy configured loosely; (b) ruff and mypy strict; (c) add `uv` or pip-tools for
  locking; (d) plain pip with pinned requirements files.
- **Decision (proposed):** (b) and (d).
  - Python 3.13 only, locally and in CI.
  - `pyproject.toml` declares runtime dependencies and a `dev` group, and holds the ruff, mypy (strict) and
    pytest settings. `requirements.txt` (runtime) and `requirements-dev.txt` are pinned with exact versions.
  - `python scripts/check.py` runs lint, format check, type check and tests, in that order, using only the
    standard library. CI runs the same steps. No `make`.
  - Installs use binary wheels only, so a missing wheel fails loudly instead of compiling from source.
- **Consequences:** One command before every push, identical locally and in CI. Strict typing costs effort on
  each new module and pays back in refactors. Pins are updated by hand, one task at a time.

## ADR-0004

**OpenAI-compatible API; providers added in a fixed order; no paid calls in tests** · Proposed · 2026-11-09

- **Context:** Existing clients and SDKs already speak the OpenAI chat-completions format; a gateway that uses it
  needs no custom client. Provider calls cost money and are slow and nondeterministic.
- **Options:** (a) a custom API; (b) OpenAI-compatible `/v1/chat/completions`; (c) one adapter per provider API
  exposed as-is.
- **Decision (proposed):** (b).
  - Providers are added in this order: a mock provider, then Ollama (local), then OpenAI and Anthropic adapters.
  - Tests and CI use only the mock provider or recorded fakes. A real provider call happens only when the owner
    runs it by hand, with the owner's own keys.
  - Streaming and other endpoints are out of scope until a task card adds them.
- **Consequences:** Clients work unchanged. Adapters translate to and from each provider's native format, which
  is where most compatibility bugs will appear. Cost and latency numbers are measured separately from tests.

## ADR-0005

**Verification safeguards: contract snapshot, mutation checks, evidence-first numbers** · Proposed · 2026-11-09

- **Context:** The project has no upstream baseline to freeze, and tests alone can pass vacuously.
- **Options:** (a) rely on code review; (b) add automated safeguards for the contract, test quality and claims.
- **Decision (proposed):** (b), in three parts.
  1. **Contract snapshot.** The generated OpenAPI document is committed. A test compares it to the live app and
     fails on any difference. It is updated only in a task whose card says the contract changes.
  2. **Mutation checks.** For every task that adds tests, the verifier applies deliberate mutations to scratch
     copies of the code (never the repository) and confirms the tests fail. The mutation table goes in the PR.
     This is done by hand; no mutation-testing tool is adopted.
  3. **Evidence-first numbers.** Any figure in a README, doc or PR comes from a recorded run with its settings.
- **Consequences:** Slower task delivery, in exchange for tests that are known to detect real breakage. A
  deliberate API change needs a visible snapshot diff in review.

---

## Template

```markdown
## ADR-NNNN

**Title** · Proposed · YYYY-MM-DD

- **Context:** what forces the decision; facts with sources.
- **Options:** (a) ...; (b) ...; (c) ...
- **Decision (proposed):** which option and why.
- **Consequences:** what becomes easier, harder, or must be done next.
```
