# Decisions

Architecture Decision Records (ADRs). Each records one decision: its context, the options, the choice and its
consequences. Statuses: **Proposed** (awaiting the owner), **Accepted**, **Accepted - amended by ADR-NNNN**
(still in force, partly changed by a later ADR), **Superseded by ADR-NNNN**, **Rejected**.
Accepted decisions change only through a new ADR.

| ADR | Decision | Status | Date |
| --- | --- | --- | --- |
| [0001](#adr-0001) | Single-author repository with enforced commit identity | Accepted | 2026-11-09 |
| [0002](#adr-0002) | Pull-request delivery flow | Accepted | 2026-11-09 |
| [0003](#adr-0003) | Python toolchain, one check command, plain pip | Accepted | 2026-11-09 |
| [0004](#adr-0004) | OpenAI-compatible API; providers added in a fixed order; no paid calls in tests | Accepted | 2026-11-12 |
| [0005](#adr-0005) | Verification safeguards: contract snapshot, mutation checks, evidence-first numbers | Accepted | 2026-11-12 |
| [0006](#adr-0006) | Redis client, Lua token bucket and how it is tested | Accepted - amended by ADR-0017 | 2026-11-12 |
| [0007](#adr-0007) | Rate-limit semantics: estimated tokens, token bucket, reserve and settle | Accepted - amended by ADR-0010, ADR-0012 and ADR-0014 | 2026-11-12 |
| [0008](#adr-0008) | HTTP contract for authentication, limit headers and errors | Accepted - amended by ADR-0009, ADR-0010 and ADR-0011 | 2026-11-12 |
| [0009](#adr-0009) | Validation error codes and `param` format (extends ADR-0008) | Accepted | 2026-11-13 |
| [0010](#adr-0010) | Provider adapters: plain httpx, translation rules and a failure taxonomy (amends ADR-0007 and ADR-0008) | Accepted - amended by ADR-0013 | 2026-11-13 |
| [0011](#adr-0011) | Routing: a route table file, ordered fallback on retryable failures (amends ADR-0008) | Accepted - amended by ADR-0014 | 2026-11-13 |
| [0012](#adr-0012) | Cap the tokens a settle charges at the bucket capacity (amends ADR-0007) | Accepted | 2026-11-14 |
| [0013](#adr-0013) | Cap the size of a provider reply (amends ADR-0010) | Accepted - amended by ADR-0016 | 2026-11-14 |
| [0014](#adr-0014) | Semantic cache: what is compared, who shares it, what a hit costs, and how the threshold is chosen (amends ADR-0007 and ADR-0011) | Accepted - amended by ADR-0016 | 2026-11-21 |
| [0015](#adr-0015) | Embeddings from a local Ollama, cosine in the standard library, the cache in process memory | Accepted | 2026-11-21 |
| [0016](#adr-0016) | Observability: a JSON request log and Prometheus metrics with the standard library, from bounded fields only (amends ADR-0013 and ADR-0014) | Accepted | 2026-11-23 |
| [0017](#adr-0017) | Container image, Docker Compose, and the deployment target: one host (amends ADR-0006) | Accepted | 2026-11-23 |
| [0018](#adr-0018) | Load benchmarks: a fixed arrival rate measured from the due time, a fake upstream, recorded runs only | Accepted | 2026-11-23 |
| [0019](#adr-0019) | No published image and no hosted demo; the demo is a recorded local run (amends ADR-0017) | Proposed | 2026-11-26 |

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

**Python toolchain, one check command, plain pip** · Accepted · 2026-11-09

- **Context:** The default shell on the development machine resolves `python` to an MSYS2 build that pip treats
  as a non-Windows platform, so compiled dependencies such as pydantic-core fail to install. A standard
  Windows Python 3.13 is available through `py -3.13`.
- **Options:** (a) ruff and mypy configured loosely; (b) ruff and mypy strict; (c) add `uv` or pip-tools for
  locking; (d) plain pip with pinned requirements files.
- **Decision:** (b) and (d), accepted by the owner on 2026-11-09.
  - Python 3.13 only, locally and in CI.
  - `pyproject.toml` declares runtime dependencies and a `dev` group, and holds the ruff, mypy (strict) and
    pytest settings. `requirements.txt` (runtime) and `requirements-dev.txt` are pinned with exact versions.
  - `python scripts/check.py` runs lint, format check, type check and tests, in that order, using only the
    standard library. CI runs the same steps. No `make`.
  - Installs use binary wheels only, so a missing wheel fails loudly instead of compiling from source.
- **Consequences:** One command before every push, identical locally and in CI. Strict typing costs effort on
  each new module and pays back in refactors. Pins are updated by hand, one task at a time.

## ADR-0004

**OpenAI-compatible API; providers added in a fixed order; no paid calls in tests** · Accepted · 2026-11-12

- **Context:** Existing clients and SDKs already speak the OpenAI chat-completions format; a gateway that uses it
  needs no custom client. Provider calls cost money and are slow and nondeterministic.
- **Options:** (a) a custom API; (b) OpenAI-compatible `/v1/chat/completions`; (c) one adapter per provider API
  exposed as-is.
- **Decision:** (b).
  - Providers are added in this order: a mock provider, then Ollama (local), then OpenAI and Anthropic adapters.
  - Tests and CI use only the mock provider or recorded fakes. A real provider call happens only when the owner
    runs it by hand, with the owner's own keys.
  - Streaming and other endpoints are out of scope until a task card adds them.
- **Consequences:** Clients work unchanged. Adapters translate to and from each provider's native format, which
  is where most compatibility bugs will appear. Cost and latency numbers are measured separately from tests.

## ADR-0005

**Verification safeguards: contract snapshot, mutation checks, evidence-first numbers** · Accepted · 2026-11-12

- **Context:** The project has no upstream baseline to freeze, and tests alone can pass vacuously.
- **Options:** (a) rely on code review; (b) add automated safeguards for the contract, test quality and claims.
- **Decision:** (b), in three parts.
  1. **Contract snapshot.** The generated OpenAPI document is committed. A test compares it to the live app and
     fails on any difference. It is updated only in a task whose card says the contract changes.
  2. **Mutation checks.** For every task that adds tests, the verifier applies deliberate mutations to scratch
     copies of the code (never the repository) and confirms the tests fail. The mutation table goes in the PR.
     This is done by hand; no mutation-testing tool is adopted.
  3. **Evidence-first numbers.** Any figure in a README, doc or PR comes from a recorded run with its settings.
- **Consequences:** Slower task delivery, in exchange for tests that are known to detect real breakage. A
  deliberate API change needs a visible snapshot diff in review.

## ADR-0006

**Redis client, Lua token bucket and how it is tested** · Accepted - amended by ADR-0017 · 2026-11-12

- **Context:** The rate limiter keeps one bucket per API key, shared by every gateway instance, and each
  reservation must read, refill and update the bucket in one atomic step. ADR-0003 allows only packages with
  prebuilt wheels for Windows (`win-amd64`) and Python 3.13. Tests have no network access, and time is injected
  through a `Clock`. Facts checked on 2026-11-12 from the PyPI JSON API, the redis-py v8.1.0 source and redis.io:
  - `redis` (redis-py) 8.1.0, released 2026-07-30, MIT, a pure-Python `py3-none-any` wheel, ships `py.typed`
    (the `types-redis` stubs are obsolete since redis-py 5). `redis.asyncio.Redis.register_script` returns a
    script object that sends EVALSHA and, on a NOSCRIPT error, loads the script and retries once. Script
    results are typed `Any`.
  - `fakeredis` 2.40.0, released 2026-10-14, BSD-3-Clause, `py3-none-any`, has `FakeAsyncRedis`. Lua scripting
    needs its `lua` extra, which installs `lupa`. `lupa` 2.8 (2026-04-15, MIT-style licence) has
    `cp313-cp313-win_amd64` and `cp313-cp313-manylinux` x86_64 wheels. fakeredis reads `time.time()` for its
    `TIME` command and for key expiry, so a fake clock cannot control either.
  - Redis runs a script atomically, blocking other commands. Lua numbers are returned as integers with the
    fraction dropped, so fractional values must be returned as strings. Every key a script touches must be
    passed in `KEYS`.
  - GitHub Actions can run Redis as a service container, on Linux runners only. The job already uses
    `ubuntu-latest`. Official image tags include `7.4.12` and `8.10.3`.
- **Options:**
  - (a) redis-py's asyncio client, the bucket as a Lua script; unit tests on fakeredis with Lua; one CI step
    against a real Redis service container.
  - (b) Same client, but a WATCH/MULTI transaction in Python instead of Lua. Retries under contention, more
    round trips, and fakeredis's transaction emulation would be what the unit tests prove.
  - (c) An in-house fake instead of fakeredis. No dependency, but it cannot run Lua, so the unit tests would
    test a Python copy of the script, not the script.
  - (d) `coredis` (MIT, fully typed). Its compiled parts have no `win_amd64` wheel; the pure-Python fallback
    is unverified here.
- **Decision:** (a).
  - Runtime dependency: `redis==8.1.0`, without the optional `hiredis` extra. Dev dependencies:
    `fakeredis[lua]==2.40.0`, which brings `lupa==2.8`. Each is pinned exactly when the task that needs it adds
    it, and the install must pass with `--only-binary=:all:` on Windows and in CI.
  - The bucket update is one Lua script, loaded through `register_script`. The script never calls `TIME`: the
    caller passes the current time in milliseconds from the injected `Clock` as an argument. The script sets
    `PEXPIRE` on the bucket key so idle buckets disappear, and returns the fractional balance as a string.
  - Script results are converted to typed values in one adapter module, so `Any` does not spread under mypy
    strict.
  - Bucket keys never contain an API key. They use a prefix and a SHA-256 digest of the key.
  - Unit tests run the real Lua script on `FakeAsyncRedis`. One shared behaviour suite runs against every
    limiter implementation (in-memory, fakeredis, real Redis).
  - The real-Redis tests carry a registered pytest marker, `redis_server`. The default pytest options deselect
    that marker, so `scripts/check.py` and local runs stay network-free; nothing is skipped. CI adds a separate
    step, `redis integration`, after the `check.py` mirror steps. It runs only those tests against a
    `redis:7.4.12` service container on `localhost`. That localhost container is the one exception to "no
    network in tests", and it exists only in CI.
  - Until that CI step is green, docs and pull requests say only "unit-tested against fakeredis" (TASKS.md
    Phase 1 requirement).
- **Consequences:**
  - The Lua script is the single implementation of the bucket on Redis, and both fakeredis and a real server
    run it.
  - Instances that share a Redis but disagree on the time will refill slightly differently. Clock skew between
    gateway hosts is accepted at this scale and noted in the docs.
  - Tests cannot rely on keys expiring. They assert the TTL that was set (`PTTL`) instead of waiting.
  - CI gains one step that `check.py` does not run, so the "same steps as `check.py`" rule gains a single named
    exception. The licence of the Redis server image was not checked; it is used only in CI and never shipped.
  - `sortedcontainers` (a fakeredis dependency) has not been checked for a wheel yet. The task that adds
    fakeredis proves the install.

## ADR-0007

**Rate-limit semantics: estimated tokens, token bucket, reserve and settle** · Accepted - amended by ADR-0010,
ADR-0012 and ADR-0014 · 2026-11-12

- **Context:** The limit is in tokens per API key, but the true cost of a request is known only after the
  provider answers. OpenAI says it counts the maximum of `max_tokens` and an estimate "based on the character
  count" against its own limits (<https://developers.openai.com/api/docs/guides/rate-limits>, seen 2026-11-12).
  `tiktoken` 0.14.0 is MIT and has cp313 wheels for Windows and Linux. But its first `get_encoding()` call
  downloads the encoding file over HTTPS, it adds the `regex` and `requests` dependencies, and the licence of
  the encoding files is unknown. Stripe's limiters use a token bucket on Redis (<https://stripe.com/blog/rate-limiters>,
  2017-03-30). GCRA keeps less state but handles variable-cost refunds badly
  (<https://brandur.org/rate-limiting>, 2015-09-18).
- **Options:**
  - Estimator: (a) a character heuristic, no dependency; (b) `tiktoken` with a vendored or pre-seeded encoding
    file; (c) Hugging Face `tokenizers` (Apache-2.0), which also loads its files from the network.
  - Algorithm: (d) token bucket; (e) GCRA; (f) sliding-window counter.
- **Decision:** (a) and (d).
  - **Estimate.** For each message, `ceil(characters / 4)` of its text content plus 3 tokens, plus 1 if it has a
    `name`, plus 3 for the reply. This is the OpenAI cookbook's per-message overhead
    (`How_to_count_tokens_with_tiktoken.ipynb`) applied to a character count instead of a tokenizer. It sits
    behind a `TokenEstimator` protocol, so a real tokenizer can replace it through a later ADR.
  - **Reservation.** The reserved amount is the input estimate plus `max_completion_tokens`, or `max_tokens`
    if only that is given, or 0 if neither is.
  - **Bucket.** Each API key has a bucket with `capacity_tokens` and `refill_tokens_per_second`, which is
    derived from a configured `tokens_per_minute`. A reservation succeeds when the refilled balance is at least
    the reserved amount, and it subtracts that amount. Otherwise it fails and reports how long until the balance
    would cover it.
  - **Settle.** After the provider answers, the difference between the provider's reported `total_tokens` and
    the reservation is charged or refunded. A charge may take the balance below zero, and later requests wait
    until it refills. If the provider fails, the whole reservation is refunded.
  - **Oversized requests.** A reservation larger than `capacity_tokens` can never succeed. It is rejected at
    once with 429, and the response carries no `Retry-After` (ADR-0008).
- **Consequences:**
  - No new dependency, and estimates are cheap. The heuristic is rough, mostly for English text, and settling
    with the provider's usage corrects the error afterwards.
  - A negative balance after settle can make the next request wait longer than its own size suggests. That is
    intended: it charges for what was used.
  - The provider's usage figures are trusted. The mock provider reports exact, deterministic usage.
  - `tiktoken` is reconsidered in an ADR when the first real provider adapter arrives (Phase 2).

## ADR-0008

**HTTP contract for authentication, limit headers and errors** · Accepted - amended by ADR-0009, ADR-0010 and
ADR-0011 · 2026-11-12

- **Context:** ADR-0004 makes the API OpenAI-compatible, and the official OpenAI Python SDK is the reference
  client. Checked on 2026-11-12:
  - The OpenAI error body is `{"error": {"message", "type", "param", "code"}}`, all four required and `param`
    and `code` nullable (openai-openapi `manual_spec`). The SDK reads that object and maps 401 to
    `AuthenticationError` and 429 to `RateLimitError`. It retries 429 and honours `retry-after-ms` and
    `retry-after` (openai-python `_base_client.py`, main branch).
  - Observed but undocumented bodies: 401 has `type: "invalid_request_error"`, `code: "invalid_api_key"`
    (openai-python issue 886). A token 429 has `type: "tokens"`, `code: "rate_limit_exceeded"` (OpenAI
    community forum, 2024-04-15).
  - OpenAI sends `x-ratelimit-limit-tokens`, `x-ratelimit-remaining-tokens` and `x-ratelimit-reset-tokens`,
    with durations written like `6m0s`, but publishes no grammar for them.
  - `Retry-After` is a non-negative integer of seconds or an HTTP date (RFC 9110, section 10.2.3).
  - The IETF `RateLimit` header fields are still a draft (draft-ietf-httpapi-ratelimit-headers-11,
    2026-05-23), and "tokens" is not one of its registered quota units.
- **Options:** (a) OpenAI's error body and `x-ratelimit-*-tokens` headers; (b) the IETF draft fields; (c) both.
- **Decision:** (a).
  - **Authentication.** `Authorization: Bearer <key>`. Keys come from configuration, never from code. A
    missing or unknown key gets 401 with `type: "invalid_request_error"` and `code: "invalid_api_key"`, and the
    message never echoes the key.
  - **Limit headers.** Every response to an authenticated `/v1/chat/completions` request carries the three
    headers, on 200 and on 429:
    - `x-ratelimit-limit-tokens` is `capacity_tokens`.
    - `x-ratelimit-remaining-tokens` is the balance after the decision, rounded down and never below 0.
    - `x-ratelimit-reset-tokens` is the time until the bucket is full again, rounded up to whole seconds and
      written as `<s>s` below a minute or `<m>m<s>s` otherwise (`0s`, `45s`, `6m0s`). This project defines that
      grammar, since OpenAI does not publish one.
  - **429.** The body has `type: "tokens"`, `code: "rate_limit_exceeded"` and `param: null`, and a message that
    gives the limit, the requested amount and the wait. A request that can succeed later also gets
    `Retry-After` as whole seconds, rounded up. An oversized request (ADR-0007) gets no `Retry-After`, and its
    message says the request is larger than the limit.
  - **400.** Invalid requests get `type: "invalid_request_error"`, with `param` naming the field when known.
    `stream: true` is rejected with `code: "unsupported_parameter"` and `param: "stream"`, because streaming is
    out of scope (ADR-0004). FastAPI's default 422 validation response is replaced by this 400 shape.
  - **502.** If the provider fails, the reservation is refunded (ADR-0007) and the response is 502 with
    `type: "api_error"`, `code: "provider_error"` and `param: null`. The message does not include provider
    internals, and the limit headers are still sent.
  - The error shapes and headers appear in the OpenAPI document, so the snapshot (ADR-0005) records them.
- **Consequences:**
  - The official SDK raises its usual typed errors and retries 429 by itself.
  - The `x-ratelimit-*` headers are a vendor convention, not a standard. Adopting the IETF fields is a backlog
    item for when the draft becomes an RFC.
  - The 429 and 401 `type` and `code` values copy observed OpenAI behaviour that OpenAI does not document.
    They may need to change if OpenAI changes.

## ADR-0009

**Validation error codes and `param` format (extends ADR-0008)** · Accepted · 2026-11-13

- **Context:** ADR-0008 fixes the 400 body's `type` (`invalid_request_error`), says `param` names the field
  "when known", and fixes `code: "unsupported_parameter"` with `param: "stream"` for streaming. It does not
  fix `code` for any other rejection or the format of a nested `param`. Task T-102 needs both. Checked on
  2026-11-13:
  - OpenAI's error-codes guide documents no `code` list and no `param` format for validation errors
    (developers.openai.com/api/docs/guides/error-codes).
  - Real bodies quoted in third-party issues write nested params as `messages[0].role` and
    `messages[3].content[0].type` (openai-python issue 2047, opened 2025-01-22; langgraphjs issue 506, opened
    2024-09-23). No quoted body uses `messages.0.role`.
  - Observed, undocumented codes: `missing_required_parameter`, `invalid_type`, `unsupported_parameter`,
    `unsupported_value` and `decimal_above_max_value`. A missing top-level `model` or `messages` was quoted
    with `code: null` and `param: null`, in bodies from 2023 and 2025.
  - No real body was found for an invalid role value that the model accepts as a role, so that code is
    unverified.
- **Options:** (a) copy OpenAI's observed codes one by one, such as `decimal_above_max_value`; (b) a small
  vocabulary of our own that follows OpenAI's names where they exist; (c) `code: null` for everything except
  `stream`.
- **Decision (proposed):** (b), with the `param` format `messages[0].role`.
  - `param` is the field path without the leading `body`: an index is written `[i]` and a name `.name`. It is
    `null` for malformed JSON and when the whole body is wrong.
  - `code` is chosen from the first validation error:

    | Case | `code` |
    | --- | --- |
    | Required field absent, including an empty body | `missing_required_parameter` |
    | Streaming, `n` above 1, array `content` | `unsupported_parameter` |
    | Malformed JSON | `invalid_json` |
    | Wrong type: a string, integer, float, boolean, list or object where another type is required, or a number or boolean that cannot be parsed (an explicit set of pydantic error types) | `invalid_type` |
    | Anything else: out of range, empty, unknown role, a fractional number for an integer field, text that is not valid Unicode | `invalid_value` |

  - Only the first error is reported, in field declaration order, so the response is deterministic.
  - The message never contains the rejected value. Unsupported-parameter messages are fixed texts; others read
    `Invalid '<param>': <reason>`.
  - Request fields the gateway does not model, such as `top_p`, `stop` and `tools`, are ignored, not rejected.
    A client that sends them gets a normal answer and the parameters have no effect.
- **Consequences:**
  - SDK clients see the usual 400 `BadRequestError` with a `param` they can read.
  - Where OpenAI's observed bodies differ (`code: null` for a missing `model`, `decimal_above_max_value` for a
    temperature above 2), this gateway's codes are coarser or different. They are our contract, recorded in the
    OpenAPI snapshot only as plain strings, so a later change needs no schema change but does need a new ADR.
  - Silently ignored parameters can surprise a client that expects `stop` to work. Rejecting them is a
    separate decision for when the first real provider adapter arrives.
  - ADR-0008's status is "Accepted - amended by ADR-0009".

## ADR-0010

**Provider adapters: plain httpx, translation rules and a failure taxonomy (amends ADR-0007 and ADR-0008)** ·
Accepted - amended by ADR-0013 · 2026-11-13

- **Context:** ADR-0004 adds providers in a fixed order (mock, Ollama, OpenAI, Anthropic) and allows only the
  mock or recorded fakes in tests. ADR-0007 said `tiktoken` would be reconsidered when the first real adapter
  arrives, and ADR-0009 left open whether unmodelled request fields stay ignored. ADR-0003 allows only packages
  with `cp313` wheels for `win_amd64` and Linux. Checked on 2026-11-13 against the PyPI JSON API, provider
  documentation and provider source code:
  - `httpx` 0.28.1 (2024-12-06, BSD-3-Clause, `py3-none-any`) is the latest stable release; 1.0 exists only as
    `dev` pre-releases. It is already pinned as a dev dependency with `httpcore` 1.0.9 (BSD-3-Clause) and
    `certifi` 2026.10.23 (MPL-2.0); its other dependencies (`anyio`, `idna`, `h11`) are already runtime pins, so
    making it a runtime dependency adds no package. `httpx.MockTransport` is public in 0.28.1 and accepts an
    async handler (encode/httpx, tag 0.28.1).
  - The official SDKs, `openai` 3.41.0 and `anthropic` 2.3.0 (the newest releases at least two weeks old, both
    Apache-2.0), are built on `httpx2`, Pydantic's fork of httpx. Together they add 8 packages, among them the
    compiled `jiter` (which has the needed wheels) and a second HTTP stack. `anthropic` raises `TypeError` when
    given a plain `httpx` client (`main` branch, not the 2.3.0 tag). Both retry twice by default on connection
    errors, 408, 409, 429 and 5xx, and wait up to 10 minutes by default. `ollama` 0.6.3 (MIT) is a thin httpx
    wrapper with no retries. The `TypeError` was read on `main`, so it shows where later releases are going, not
    a property of 2.3.0; the reasons against the SDKs are the extra packages, the second HTTP stack and the
    built-in retries.
  - Ollama (MIT) native `POST /api/chat` streams unless `"stream": false` is sent, leaves `prompt_eval_count`,
    `eval_count` and `done_reason` out of the JSON when they are empty or 0, reports `done_reason` "stop" or
    "length", and answers errors as `{"error": "<text>"}`, with 404 for a missing model (docs.ollama.com/api and
    ollama/ollama `main`). Its OpenAI-compatible `/v1` layer has no `max_completion_tokens` field and drops
    unknown fields silently.
  - OpenAI chat completions: `max_tokens` is deprecated and "not compatible with o-series models", so
    `max_completion_tokens` is the field to send; `message.content` and `usage` can be null or absent; and
    `finish_reason` can also be `tool_calls` or `function_call` (developers.openai.com API reference).
  - Anthropic Messages API: `x-api-key` and `anthropic-version` headers. The newest version, `2026-10-21`,
    answers 400 to any `temperature`, `top_p` or `top_k`, even at the default (migration guide). `max_tokens` is
    required. System text is a top-level `system` field. Messages have no `name`. `content` is a list of blocks,
    including thinking blocks. `stop_reason` is one of end_turn, max_tokens, stop_sequence, tool_use,
    pause_turn, refusal or model_context_window_exceeded. Total input tokens are `input_tokens` plus the two
    cache fields. 529 means overloaded (Anthropic's API documentation). Anthropic's OpenAI-compatible endpoint
    is "not considered a long-term or production-ready solution for most use cases".
  - No provider documents an idempotency key for chat, so a retry after a timeout can be billed twice.
  - `tiktoken` 0.14.0 would add 5 packages, and the licence of its encoding files is still not stated anywhere
    official. Anthropic's `count_tokens` endpoint is free but needs a key and the network, and returns an
    estimate.
- **Options:**
  - HTTP client: (a) plain `httpx` adapters; (b) the official SDKs with `max_retries=0`; (c) the `ollama`
    package for Ollama and (a) for the others.
  - Ollama endpoint: (d) native `/api/chat`; (e) the OpenAI-compatible `/v1/chat/completions`.
  - Anthropic endpoint: (f) the Messages API; (g) its OpenAI-compatible endpoint.
  - A 2xx answer that cannot be translated: (h) refund the whole reservation, like any failure (ADR-0007 as
    written); (i) charge the reservation as made, because the provider has probably billed for it.
- **Decision (proposed):** (a), (d), (f) and (i). The token estimate stays heuristic.
  - **Dependencies.** `httpx==0.28.1`, `httpcore==1.0.9` and `certifi==2026.10.23` move from
    `requirements-dev.txt` to `requirements.txt`, and `httpx` moves to the runtime dependencies in
    `pyproject.toml`. No provider SDK and no `ollama` package.
  - **Clients.** `create_app()` builds one `httpx.AsyncClient` per configured HTTP provider, with its base URL
    and its timeout (`timeout_seconds` for reads, writes and the pool, and 5 seconds to connect, so
    `timeout_seconds` is at least 5). These timeouts apply to each network operation, not to the request as a
    whole, so a slow provider can take longer than `timeout_seconds`; a total deadline per request is deferred
    to the backlog. An app lifespan closes every client the app built, and the Redis client
    it built from the URL, on shutdown. Tests inject an `httpx.MockTransport`, so no test opens a socket.
  - **One attempt.** An adapter makes exactly one HTTP request, with no retry and no sleeping. Falling back is
    the router's job (ADR-0011).
  - **Failure taxonomy.** Every adapter failure raises `ProviderError` with a `kind`:

    | Kind | Cause | Retryable |
    | --- | --- | --- |
    | `connection` | could not connect, or the connection broke (`httpx.TransportError`) | yes |
    | `timeout` | the configured timeout passed (`httpx.TimeoutException`) | yes |
    | `rate_limited` | upstream 429 | yes |
    | `upstream_status` | any other non-2xx; retryable only when 500 or above, including 529 | 5xx only |
    | `bad_response` | a 2xx that cannot be translated: a body that cannot be decoded (`httpx.DecodingError`) or is not valid JSON, a missing field, an unknown finish reason, a negative or missing token count, a body above the provider's `max_response_bytes` (ADR-0013) | no |

    `httpx.TimeoutException` is a subclass of `httpx.TransportError`, so an adapter checks for a timeout first.
    Messages carry only the kind and the HTTP status. They never carry a response body, which can echo the
    prompt, or a key.
  - **Translation, all providers.** `user` is not forwarded. Fields the gateway does not model (`top_p`, `stop`,
    `tools` and others) stay ignored and are not forwarded (ADR-0009); rejecting them stays deferred. The reply
    must be a string. Token counts must be integers of at least 0, and `total_tokens` is computed by the gateway
    as prompt plus completion. A finish reason outside stop, length and content_filter is `bad_response`.
  - **Ollama.** Native `/api/chat` with `"stream": false`. The client's `max_completion_tokens`, else
    `max_tokens`, becomes `options.num_predict`, and `temperature` becomes `options.temperature`, each only when
    given. `name` is dropped. An absent count is 0. `done_reason` must be "stop" or "length". The response `id`
    comes from the injected id source and `created` from the injected clock.
  - **OpenAI.** The client's `max_completion_tokens`, else `max_tokens`, is sent as `max_completion_tokens`;
    `max_tokens` is never sent. `temperature` and `name` are forwarded. `content: null` with a `refusal` becomes
    an empty reply with finish reason `content_filter`. Any other null content, a missing `usage`, or a
    `tool_calls` or `function_call` finish is `bad_response`. The upstream `id` and `created` are kept.
  - **Anthropic.** `anthropic-version: 2026-10-21`. Every system message is joined with `\n`, in order, into
    `system`. `name` and `temperature` are dropped, because that version rejects any temperature. `max_tokens`
    is the client's `max_completion_tokens`, else `max_tokens`, else the provider's configured
    `default_max_tokens`. The `text` blocks, joined in order with no separator, form the reply; other blocks,
    such as thinking, are ignored, and a response with no `text` block gives an empty reply (a refusal, or a
    limit spent on thinking, can have none). end_turn and stop_sequence map to stop, max_tokens and
    model_context_window_exceeded to length, refusal to content_filter, and anything else is `bad_response`.
    Prompt tokens are `input_tokens` plus `cache_creation_input_tokens` plus `cache_read_input_tokens`, an absent or null cache field counting 0; completion tokens are
    `output_tokens`. `id` comes from the injected id source and `created` from the injected clock.
  - **Settle on `bad_response` (amends ADR-0007 and ADR-0008).** The reservation is charged as made (settle
    with the actual amount equal to the reservation) and the answer is the ADR-0008 502. Every failure before a
    2xx keeps the full refund that ADR-0007 and ADR-0008 describe.
  - **Estimator.** `tiktoken` stays out, for the reasons in ADR-0007, which have not changed. The heuristic
    estimate is used for every provider, and settling with the reported usage corrects it.
  - **Fakes.** Adapter tests use response bodies written from the documented shapes cited above. When the owner
    calls a provider by hand, a sanitised real body may replace a hand-written one.
- **Consequences:**
  - No new package and one HTTP stack. The adapters are hand-written, so translation bugs are the main risk
    (ADR-0004), and each adapter's tests cover every rule above.
  - Anthropic ignores the client's temperature, a visible difference from the other providers. A reservation
    for an Anthropic route with no max field understates the cost until settle.
  - Starlette's TestClient keeps warning that it prefers `httpx2`. Switching is a separate decision.
  - A provider that is not an HTTP adapter (the mock, or one injected in tests) is not checked by these rules,
    so a negative count from it still makes `settle` raise.
  - ADR-0007's status is "Accepted - amended by ADR-0010", and ADR-0008's names ADR-0010 among the ADRs that
    amend it (its 502 no longer always refunds). Accepted by the owner as written on 2026-11-13.

## ADR-0011

**Routing: a route table file, ordered fallback on retryable failures (amends ADR-0008)** · Accepted -
amended by ADR-0014 · 2026-11-13

- **Context:** The router picks a provider and model for each request (ARCHITECTURE section 2). Prior art,
  checked on 2026-11-13 in each project's documentation and source:
  - Every gateway maps a client-facing model name to upstream targets: LiteLLM model groups (`model_name`),
    Portkey `targets`, OpenRouter's `models` array, Kong `model_alias`, Envoy AI Gateway `backendRefs` with
    `priority`.
  - Fallback triggers differ. OpenRouter and Portkey fall back on any error by default. Kong's default is
    connection errors and timeouts only ("Client errors don't trigger failover"; 429 and 502 are opt-in), and
    LiteLLM does not cool down a deployment for most 4xx errors. LiteLLM and Portkey also retry the same target
    with backoff first (LiteLLM `num_retries` 2, Portkey up to 5 attempts at 1 to 16 seconds).
  - Cooldowns and circuit breakers exist (LiteLLM 5 seconds by default; Portkey's minimum is 30 seconds; Kong's
    is off by default), and their state is often shared through Redis.
  - On usage, OpenRouter: "An attempt that errors is not charged for its model tokens, so with fallback you pay
    only for the run that answers." Its response `model` is the model that served the request. LiteLLM reports
    the serving deployment and the attempted fallbacks in `x-litellm-*` headers.
  - Load balancing and latency-, cost- or usage-based routing are common, but LiteLLM calls usage-based routing
    "not recommended for production".
  - YAML configuration would need a new dependency; `json` is in the standard library.
- **Options:**
  - Configuration: (a) a JSON file whose path is an environment variable, validated with pydantic at startup;
    (b) environment variables only; (c) YAML.
  - Fallback trigger: (d) any error; (e) connection errors, timeouts, upstream 429 and upstream 5xx only.
  - Retries: (f) none in this phase, each target tried once; (g) same-target retries with backoff first.
  - Health: (h) none; (i) a per-process cooldown after repeated failures.
  - Unknown model: (j) 404 before any reservation; (k) 400; (l) always a default route.
- **Decision (proposed):** (a), (e), (f), (h), and (j) with an optional default route.
  - **Route table file.** `TOLLGATE_ROUTES_FILE` names a JSON file with three keys:
    - `providers`: provider name → `type` (`mock`, `ollama`, `openai` or `anthropic`) and its settings.
      `base_url` and `timeout_seconds` (at least 5, at most 600, default 60) are allowed for the three HTTP types
      and rejected for `mock`. `api_key_env` is required for `openai` and `anthropic` and rejected for `mock` and
      `ollama`. `default_max_tokens` is required for `anthropic` and rejected for every other type.
    - `routes`: alias → 1 to 5 targets, each a `provider` and an optional upstream `model`; without one the
      client's model is passed through.
    - `default`: an optional list of targets, with the same rules as a route.

    Unknown fields and duplicate keys at any level are rejected (Python's `json` would otherwise keep the last
    duplicate silently). A key is never in the file: `api_key_env` names the environment variable that holds
    it, read at startup, and a variable that is unset, empty or only whitespace is an error naming it. Every
    error names the variable and the field path, never a value. The table is read where the other settings
    are, from the same environment mapping, so tests never touch the process environment. Without the variable
    a built-in table applies: one provider named `mock` of type `mock`, and a default route to it with no
    upstream model, so behaviour stays as it is today.
  - **Selection.** `Router.select(request) -> Route` matches `request.model` exactly against the aliases, then
    uses the default route, and otherwise refuses with 404 (`type: invalid_request_error`,
    `code: model_not_found`, `param: model`, message "The requested model is not available on this gateway.",
    which does not echo the model, as ADR-0009 never echoes a rejected value) before any estimate or
    reservation. A 404 carries no limit headers (amends ADR-0008, under which every authenticated chat response
    carried them). The official SDK maps 404 to `NotFoundError`; whether OpenAI itself sends `model_not_found`
    in this case was not checked.
  - **Fallback.** The route's targets are tried in order, each at most once. The request goes to each target
    with its upstream model. Only a retryable `ProviderError` (ADR-0010) moves on to the next target. Any other
    error stops the route at once, and a route that runs out of targets ends in 502 (ADR-0008).
  - **Tokens (ADR-0007 unchanged).** One reservation before the first attempt and one settle with the usage of
    the attempt that served. The reservation is refunded in full when the route fails without a 2xx; a
    `bad_response` is charged as reserved (ADR-0010).
  - **Response.** The body's `model` is the upstream model the provider reported. A 200 also carries
    `x-tollgate-provider` (the configured provider name) and `x-tollgate-fallbacks` (the number of failed
    attempts before the one that served). Both, and the 404, are recorded in the OpenAPI document.
  - Deferred to the backlog: same-target retries and `Retry-After`, cooldowns, load balancing, latency- or
    cost-based routing, and fallback chains for context-length or content-policy errors.
- **Consequences:**
  - A broken route table stops the app at startup, not at the first request.
  - A request has no total deadline: each of up to 5 targets can take its timeouts, which apply per network
    operation, so a slow route can take much longer than the sum of its `timeout_seconds`. With no health
    tracking, a primary whose host does not answer costs up to its connect timeout (5 seconds) on every
    request until the configuration changes; a refused connection fails at once.
  - A 502 does not tell the client which upstream failed or why.
  - The contract gains the 404 and two response headers. `Router` and `Route` become final interfaces in
    ARCHITECTURE section 3.
  - ADR-0008's status is "Accepted - amended by ADR-0009, ADR-0010 and ADR-0011". Accepted by the owner as
    written on 2026-11-13.

## ADR-0012

**Cap the tokens a settle charges at the bucket capacity (amends ADR-0007)** · Accepted · 2026-11-14

- **Context:** ADR-0007 charges the difference between the provider's reported `total_tokens` and the
  reservation with no upper bound, and ADR-0010 rejects only a negative or missing count. In the T-204 review a
  count of `10**30` was accepted by the Ollama adapter and returned in `usage`, and nothing between the adapter
  and `settle` bounds it. Settling such a count at the limiter level: the Redis limiter stops at its debt
  floor of 75,059,993,789 tokens (T-106), about 238 years of refill at 600 tokens per minute, with the key's
  expiry set to match; the in-memory limiter holds -10**30 tokens and reports a `Retry-After` of 29 digits.
  Either way the caller's key is refused for the life of the deployment. The OpenAI and Anthropic adapters
  (T-205, T-206) will settle counts from remote services in the same way. A request with no max field reserves
  only its input estimate (ADR-0007), 7 tokens for one user message of `hi`, so a normal answer can cost many
  times its reservation.
- **Options:**
  - (a) Cap the charge at a multiple of the reservation. With no max field the reservation is only the input
    estimate, so any small multiple undercharges ordinary answers.
  - (b) Cap the charge at the bucket capacity, which the route already holds as `limit_tokens` on the reserve
    `Decision`. One request can never take more than one full bucket.
  - (c) Treat a count above a bound as `bad_response` (502, charged as reserved). A count above the capacity can
    be real (no max field, a long answer, a small capacity), and the client would lose an answer the provider
    has probably billed.
  - (d) Cap inside each limiter's `settle`. That changes the meaning of the `RateLimiter` protocol and the
    shared behaviour suite on both backends, when the route already has the number it needs.
  - (e) No cap.
- **Decision (proposed):** (b), applied in the route. A 200 settles with the smaller of the reported
  `total_tokens` and the reserve decision's `limit_tokens`.
  - The request is still a 200, and the response's `usage` shows the provider's figures unchanged. Only the
    limiter's charge is capped.
  - The 502 paths are unchanged: they charge the reservation or nothing, and both are at most the capacity.
  - A negative count is unchanged: an HTTP adapter turns it into `bad_response` (ADR-0010), and from the mock or
    an injected provider it still makes `settle` raise.
  - No header or field is added, so the contract is unchanged.
- **Consequences:**
  - The reservation was allowed, so the balance before it was at least the reservation, and one request leaves
    a balance of at least the reservation minus the capacity, never below minus the capacity. The key is full
    again within twice capacity divided by the refill rate: 2 minutes with the default capacity, which equals
    the tokens per minute. Concurrent requests are each bounded the same way, so the debt is bounded by the
    number in flight times the capacity.
  - An answer that really costs more than the whole bucket is undercharged by the excess. It still empties the
    bucket, and the response's `usage` shows the real figure, but nothing records that a cap applied until
    there is observability (Phase 4).
  - The Redis debt floor stays as a second guard; one request can no longer reach it.
  - ADR-0007's sentence "The provider's usage figures are trusted" holds up to the capacity. ADR-0007's status
    is "Accepted - amended by ADR-0010 and ADR-0012". Delivered by T-208. Accepted by the owner as written on
    2026-11-14.

## ADR-0013

**Cap the size of a provider reply (amends ADR-0010)** · Accepted - amended by ADR-0016 · 2026-11-14

- **Context:** The Ollama adapter (T-204) opens the reply with `client.stream` and reads it whole with
  `response.aread()`, which joins every decoded chunk in memory, so a 2xx body of any size is held in full before
  it is parsed. T-204 accepted this for a local Ollama (its known gap 3). The OpenAI and Anthropic adapters
  (T-205, T-206) will read replies from remote services in the same way. Checked on 2026-11-14 against the
  installed `httpx` 0.28.1 and `httpcore` 1.0.9 and their documentation:
  - httpx has no maximum body size option: the `Client` and `AsyncClient` API lists none, and a non-streaming
    `post` calls `aread()` before it returns (`httpx/_client.py`, `httpx/_models.py`, tag 0.28.1;
    <https://www.python-httpx.org/api/>).
  - `Response.aiter_bytes()` yields the decoded content: each raw chunk goes through the `Content-Encoding`
    decoder (gzip and deflate; br and zstd only when `brotli` or `zstandard` is installed, and neither is), so a
    count over it counts decompressed bytes. `aiter_raw()` and `num_bytes_downloaded` count the encoded bytes
    (<https://www.python-httpx.org/quickstart/>, <https://www.python-httpx.org/async/>, `httpx/_decoders.py`).
  - The gzip and deflate decoders decompress a whole raw chunk at once, with no output bound, and `httpcore` reads
    at most 64 KiB per chunk (`httpcore/_async/http11.py`, `READ_NUM_BYTES`), so memory can pass a decoded-byte
    limit by one decompressed chunk.
  - Leaving `async with client.stream(...)` closes the response without reading the rest; on HTTP/1.1 an
    unfinished response closes its connection instead of returning it to the pool (`httpx/_client.py`,
    `httpcore/_async/http11.py`).
  - `httpx.MockTransport` returns the handler's `Response` unchanged. A `bytes` body is read in the constructor
    and served as one chunk; an async iterator of bytes is streamed one part per item with `Transfer-Encoding:
    chunked` (`httpx/_transports/mock.py`, `httpx/_content.py`), so a test can show where reading stops.
  - Neither OpenAI's chat completions reference nor Anthropic's API overview documents a maximum response size;
    OpenAI bounds the reply in tokens (`max_completion_tokens`), and Anthropic documents request size limits only
    (<https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create>,
    <https://platform.claude.com/docs/en/api/overview>, both seen 2026-11-14).
- **Options:**
  - Where the limit is set: (a) one constant for every provider; (b) a `max_response_bytes` field on every HTTP
    provider in the route table, with a default and bounds, like `timeout_seconds`; (c) an environment variable
    for the whole gateway.
  - What is counted: (d) the decoded bytes from `aiter_bytes()`; (e) the encoded bytes (`aiter_raw()` or
    `num_bytes_downloaded`), which a compressed body can pass far below its decoded size; (f) the
    `Content-Length` header, which is absent on a chunked reply and is not checked against the bytes sent.
  - What an oversized reply is: (g) `bad_response`, charged as reserved, not retryable, the ADR-0008 502;
    (h) a new failure kind; (i) a retryable failure, so the next target is tried.
- **Decision (proposed):** (b), (d) and (g).
  - **The limit.** Every HTTP provider type in the route table (`ollama`, `openai`, `anthropic`) accepts an
    optional `max_response_bytes`: a whole number from 1,024 to 67,108,864 (64 MiB), default 8,388,608 (8 MiB).
    These numbers are chosen, not measured: no provider documents a reply size, and the default is far above a
    non-streaming chat reply while keeping one reply's memory bounded. A value outside the bounds, a bool or a
    non-integer stops startup with the `SettingsError` on `TOLLGATE_ROUTES_FILE` that the other fields give.
  - **The count.** An HTTP adapter reads a 2xx body through one shared helper that adds up the length of each
    chunk from `aiter_bytes()` and stops as soon as the total is above the limit; a body of exactly the limit is
    read. Reading stops there, and leaving the stream closes the response without reading the rest. The status is
    still read before the body, and a non-2xx body is still never read (ADR-0010).
  - **The failure.** A body above the limit is `bad_response` with the reply's status: not retryable, so the
    route does not fall back; the reservation is charged as made; and the client gets the ADR-0008 502. The
    message holds only the kind and the status, never any of the body.
  - The contract is unchanged: no response, header or field is added.
- **Consequences:**
  - One reply holds at most the limit plus one decompressed chunk in memory. A gzip chunk of 64 KiB can expand
    far beyond that, so the bound is the limit plus one chunk's expansion, not the limit itself. Bounding the
    decoder's output would need a decoder of our own and is not done.
  - A reply that really is larger than the limit is lost, and the caller is charged the reservation as for any
    `bad_response`; an operator raises `max_response_bytes` for that provider. Nothing records that the cap
    applied until there is observability (Phase 4).
  - The route table gains one optional field per HTTP provider, documented in `docs/setup.md`; existing route
    files stay valid.
  - The OpenAI and Anthropic adapters (T-205, T-206) read their replies through the same helper, with their own
    provider's limit.
  - ADR-0010's status is "Accepted - amended by ADR-0013", and its `bad_response` row names an oversized body.
    Delivered by T-209. Accepted by the owner as written on 2026-11-14.

## ADR-0014

**Semantic cache: what is compared, who shares it, what a hit costs, and how the threshold is chosen (amends
ADR-0007 and ADR-0011)** · Accepted - amended by ADR-0016 · 2026-11-21

- **Context:** Phase 3 adds the semantic cache that ARCHITECTURE section 2 places after the reservation: a request
  close in meaning to an earlier one is answered from the cache instead of a provider. The TASKS.md requirement
  for Phase 3 says a threshold is never chosen without an eval harness. Prior art, checked on 2026-11-21 in each
  project's documentation and source (LiteLLM and GPTCache on their `main` branches):
  - What is embedded differs. GPTCache embeds the last message (`last_content`), and Kong embeds the latest
    message by default (`message_countback: 1`). LiteLLM embeds the text of every message, system prompt
    included, and says its semantic cache "is designed for single-shot prompts" and "will replay stale
    responses" on multi-turn traffic. Portkey embeds user text and ignores the system prompt
    (docs.litellm.ai/docs/proxy/caching_semantic, developer.konghq.com/plugins/ai-semantic-cache/reference,
    portkey.ai/docs/product/ai-gateway/cache-simple-and-semantic).
  - What must match exactly also differs. LiteLLM keys every entry on a hash of the request parameters other than
    the messages, plus the key, team and organisation. Portkey requires an exact `model`, `temperature`,
    `max_tokens` and other body fields. Kong's cookbook says its cache "doesn't separate responses by AI
    Consumer". RedisVL and Redis LangCache share entries unless the caller adds filters. Portkey caches only
    requests of at most 4 messages, and LiteLLM skips requests of more than 4 messages by default.
  - Thresholds are cosine-based, with no common default. Portkey uses a similarity of 0.95. LangCache uses 0.85,
    allows 0.5 to 1.0, and recommends 0.8 to 0.9. RedisVL uses a cosine distance of 0.1. LiteLLM has no default
    and refuses to start without one. Published numbers are vendor-reported. One example, from Actian's blog
    (2026-11-13), on a Banking77 sample with all-MiniLM-L6-v2: a hit rate of 79.2% with 6.4% false positives at
    0.80. The same post reports 74 of 75 negated questions served from the cache, and "$2500" matching "$250" at
    0.962 (<https://www.actian.com/blog/developer/stop-trusting-your-cache-hit-rate-7-tests-show-why/>). vCache
    (arXiv 2502.03771) shows that a static threshold gives no correctness guarantee.
  - Leaks between tenants are documented. In Actian's simulation, 67.1% of hits crossed tenant boundaries when
    the cache had no tenant filter. InputSnatch (arXiv 2411.18191) recovers inputs from the timing of hits in
    caches shared across users.
  - On failure, LiteLLM fails open after a 5-second embedding timeout and treats the request as a miss. Kong's
    `stop_on_failure` defaults to false. GPTCache and RedisVL raise the error to the caller.
  - On a hit, LiteLLM records a cost of $0 and replays the original `usage`, and GPTCache sets `usage` to zeros.
    LiteLLM sends `x-litellm-cache-key`, Portkey `x-portkey-cache-status`, Kong `X-Cache-Status` and Cloudflare
    `cf-aig-cache-status`. No product was found that documents how hits count against a rate limit.
  - Default lifetimes: Portkey 7 days, Kong 300 seconds; LiteLLM, RedisVL and LangCache have no expiry by
    default. GPTCache keeps at most 1,000 entries and evicts the least recently used. No product documents
    invalidation when the embedding model changes.
- **Options:**
  - What is embedded: (a) the last message, only when it is a `user` message, with every other part of the
    request matched exactly; (b) all messages joined together; (c) user text only.
  - Who shares an entry: (d) only the same caller (API key); (e) every caller.
  - What a hit costs: (f) nothing: the reservation is refunded in full; (g) the stored answer's usage; (h) the
    input estimate.
  - Where the lookup happens: (i) after the reservation, as ARCHITECTURE section 2 shows; (j) before it, so a
    hit needs no tokens.
  - When the embedder fails: (k) a miss, and the provider answers (fail open); (l) a 502.
  - The threshold: (m) a built-in default; (n) required whenever the cache is on, with the value the docs
    recommend taken from a recorded eval run.
- **Decision (proposed):** (a), (d), (f), (i), (k) and (n).
  - **Eligibility.** A request is looked up and stored only when its last message has role `user`. Any other
    request skips the cache.
  - **Partition.** An entry can match only when every other part of the request is identical. This covers the
    caller id (the SHA-256 digest of the API key, T-103), the client's `model` as sent (the alias, not the
    upstream model), every other request field (`max_completion_tokens`, `max_tokens`, `temperature`, `n`,
    `stream`, `user`), every earlier message (role, content and name), the last message's `name`, and the
    embedder's identity (its type and model). A field left out and the same field sent with its default value
    partition apart (`stream` absent or `false`, `n` absent or `1`). The partition key is the SHA-256 digest of
    these values as canonical JSON: sorted keys, no whitespace, and every non-ASCII character escaped
    (`ensure_ascii=True`), so a lone surrogate in `user` or `name`, which validation accepts, still
    gives a key. (A lone surrogate in `model` never reaches the cache: validation rejects it with a 400,
    because `min_length` decodes the text. The key would still not raise.) The last message's content is the
    only text that is embedded.
  - **Similarity.** Cosine similarity between unit vectors. A hit needs a similarity at least equal to the
    threshold. Among the entries that pass, the most similar wins, and a tie goes to the most recently stored.
    Two identical texts can score `0.9999999999999999` after normalisation, so a threshold of `1` may never
    hit.
  - **Interface (final once accepted).** `SemanticCache.lookup(caller_id, request)` returns one of three
    results: `Hit(response, provider_name, similarity)`; `Miss(ticket)`, whose ticket holds the partition key
    and the vector for a later store; or `Skip()`, when the request is not eligible or the embedder failed.
    `SemanticCache.store(ticket, response, provider_name) -> bool` reports whether the answer was stored. These
    replace the illustrative `get` and `put` in ARCHITECTURE section 3.
  - **Threshold.** `TOLLGATE_CACHE_SIMILARITY_THRESHOLD` is required whenever the cache is on. It is a decimal
    from 0.5 to 1 with at most 4 decimal places, and there is no default. The value the docs recommend comes
    from a recorded run of the eval harness against the embedding model it is recommended for. The harness has
    a fixed set of hand-written prompt pairs, each labelled `same` or `different`, and the `different` pairs
    include near misses: negation, a changed number, a swapped direction, a changed entity. Each pair runs
    through the real cache: store an answer for the first prompt, then look up the second. The run reports the
    hit rate on `same` pairs and the wrong-hit rate on `different` pairs at each threshold from 0.50 to 1.00 in
    steps of 0.01 (each threshold computed as `i / 100`, so it is the same double that parsing the setting
    gives), together with its settings. A run in which any lookup is a `Skip` stops with an error and reports
    nothing, so an embedder outage can never look like zero wrong hits. The recommended threshold is the lowest
    one below 1 with no wrong hit on the dataset. If no such threshold exists, the docs recommend against using
    the cache with that model.
  - **Lookup and cost (amends ADR-0007 and ADR-0011).** The order is: route selection (a 404 still comes
    first), estimate, reservation (a 429 still comes first, even for a prompt that is cached), then the lookup.
    A hit runs no target and settles once with an actual amount of 0, so the reservation is refunded in full.
    A miss runs the route as today and settles as today.
  - **Hit response (amends ADR-0011's Response bullet).** The stored answer with a new `id` from the injected
    id source and a new `created` from the injected clock. `model`, `choices` and `usage` are as stored, so
    `usage` describes the answer as it was first produced. `x-tollgate-provider` names the provider that
    produced the stored answer, not one that served this request, and `x-tollgate-fallbacks` is `0`. The
    OpenAPI descriptions of both headers say so. The limit headers come from the reservation, as on every 200.
  - **Cache header.** Every 200 carries `x-tollgate-cache`, one of `hit`, `miss` (looked up, no match, the
    provider answered) or `skip` (not looked up: the cache is off, the request is not eligible, or the embedder
    failed). No other status carries it. The header and its values are recorded in the OpenAPI document.
  - **What is stored.** After a miss, a 200 with exactly one choice, whose finish reason is `stop`, is stored,
    unless its JSON body is larger than 65,536 bytes in UTF-8. Nothing is stored after a `skip`, a `length` or
    `content_filter` finish, or any failure. An entry holds the vector, the response as those UTF-8 JSON bytes
    (so the cap bounds its size), and the name of the provider that served it. It never holds the API key or
    the prompt text.
  - **Embedder failure.** It becomes a `skip`, and the route runs as if the cache were off. Only the embedder's
    classified failures are caught; any other exception is a bug and remains a 500.
  - **Invalidation.** Entries expire `TOLLGATE_CACHE_TTL_SECONDS` after they are stored, measured on the
    injected clock: a whole number from 60 to 604,800, default 3,600. A hit does not extend an entry's life.
    The cache holds at most `TOLLGATE_CACHE_MAX_ENTRIES` entries: a whole number from 1 to 100,000, default
    1,000. When it is full, expired entries go first, then the least recently used, where a store and a hit
    both count as a use. Changing the embedding model changes the partition, so old entries can no longer match.
    These defaults and bounds are chosen, not measured.
  - Deferred to the backlog: per-request controls (`Cache-Control: no-cache` and `no-store`), a purge endpoint,
    a cache shared between processes, and a limit on request count for hits.
- **Consequences:**
  - A multi-turn conversation can hit only when every earlier turn is identical, so multi-turn hits are rare
    but never replay an answer from a different conversation. One caller never receives another caller's
    answer, so a hit cannot leak data across API keys. Its timing can still reveal a caller's own earlier
    prompts to anyone holding the same key.
  - A wrong hit returns an answer to a different question. The eval harness measures this only on its own
    dataset, and "no wrong hit on the dataset" is not a guarantee. 0 wrong hits out of 40 `different` pairs
    gives a one-sided 95% upper bound of about 7% (Clopper-Pearson, 1 - 0.05^(1/40)), and about 31% for one
    category of 8. The threshold is chosen on the same data, so the true rate can be higher still.
  - A hit costs no tokens, so a caller with a full bucket can repeat cached prompts without limit. Each hit
    still needs the reservation to succeed at that moment. A request-count limit is a backlog item.
  - `usage` on a hit is the original answer's, but the limiter charged nothing for it. The `x-tollgate-cache`
    header says which applies.
  - Every eligible request now waits for an embedding call before the provider call, even on a miss. Its
    latency is unknown until Phase 4 measures it.
  - The contract gains one response header on 200, and the descriptions of `x-tollgate-provider` and
    `x-tollgate-fallbacks` change. ADR-0008 is not amended: the limit headers are unchanged on every status.
    `SemanticCache`, `Hit`, `Miss` and `Skip` become final interfaces in ARCHITECTURE section 3.
  - ADR-0007's status is "Accepted - amended by ADR-0010, ADR-0012 and ADR-0014", and ADR-0011's is
    "Accepted - amended by ADR-0014". Delivered by T-301 to T-307. Accepted by the owner as written on
    2026-11-21.

## ADR-0015

**Embeddings from a local Ollama, cosine in the standard library, the cache in process memory** · Accepted ·
2026-11-21

- **Context:** The cache in ADR-0014 needs an embedding for each eligible request, a similarity search, and a
  place to keep the entries. Tests have no network (ADR-0004), and ADR-0003 allows only packages with `cp313`
  wheels for `win_amd64` and Linux. Checked on 2026-11-21 against Ollama's documentation and source (`main`
  branch; the latest release was v0.40.17, 2026-11-10), the PyPI JSON API, redis.io, and the redis-py v8.1.0 and
  fakeredis v2.40.0 tags:
  - Ollama's `POST /api/embed` takes `model` and `input` (a string or a list), plus optional `truncate` (default
    true), `dimensions`, `keep_alive` and `options`. It returns `{"model", "embeddings": [[...]],
    "total_duration", "load_duration", "prompt_eval_count"}`. The handler L2-normalises every vector, and a NaN
    or infinite value is an error. With `truncate: false`, an input longer than the context gets 400 "the input
    length exceeds the context length". An unknown model gets 404, and errors are `{"error": "<text>"}`. The
    older `/api/embeddings` is "superseded" and does not normalise. Ollama also serves an OpenAI-compatible
    `POST /v1/embeddings`, but that endpoint has no `truncate` field (docs.ollama.com/api/embed,
    ollama/ollama `server/routes.go` and `openai/openai.go`).
  - Embedding models in the Ollama library: `all-minilm` (384 dimensions, 46 MB, Apache-2.0, no prompt prefix,
    256 word pieces), `bge-m3` (1,024 dimensions, 1.2 GB, MIT, no prefix), `nomic-embed-text` (768 dimensions,
    Apache-2.0, needs `search_query:`-style task prefixes), `mxbai-embed-large` and `snowflake-arctic-embed`
    (1,024 dimensions, Apache-2.0, query prefixes), and `embeddinggemma` (Gemma Terms of Use, task prompts).
  - `math.sumprod` (Python 3.12 and later) computes a dot product in C. numpy 2.5.5 (BSD-3-Clause and other
    permissive licences) has the needed wheels, but was uploaded on 2026-11-15, less than two weeks ago.
  - Vector search on Redis needs Redis 8. Vector sets (`VADD`, `VSIM`) arrived in 8.0.0, marked "preview", and
    the Query Engine's vector search (`FT.SEARCH` KNN) is built into Redis 8. CI runs `redis:7.4.12`, which has
    neither. fakeredis 2.40.0 emulates vector sets only with its `vectorset` extra, which pulls in numpy and
    `jsonpath-ng`, and it has no `FT.*` commands. Redis 8 is licensed RSALv2, SSPLv1 or AGPLv3.
- **Options:**
  - Embedder: (a) Ollama `/api/embed` on plain httpx; (b) Ollama's `/v1/embeddings`, which would also fit
    OpenAI and other compatible servers; (c) an embedding model in process (sentence-transformers or
    fastembed), which means large new dependencies and a model download at first use.
  - Similarity: (d) a linear scan with `math.sumprod`, no dependency; (e) numpy.
  - Storage: (f) in process memory, bounded; (g) Redis vector sets or the Query Engine, shared across processes.
  - Tests and the eval baseline: (h) a deterministic hashing embedder in the code base, never selectable at
    run time; (i) fixed vectors only.
- **Decision (proposed):** (a), (d), (f) and (h).
  - **Interface (final once accepted).** `Embedder` has an `identity` string and `async def embed(self, text:
    str) -> array[float]`, which returns a unit vector. Every classified failure raises `EmbeddingError(kind,
    status_code)`, using ADR-0010's failure kinds, with a message built from the kind and the status only.
  - **Configuration.** `TOLLGATE_CACHE_EMBEDDER` turns the cache on. Its only accepted value is `ollama`. Unset
    means the cache is off and every 200 carries `x-tollgate-cache: skip`. With the cache on,
    `TOLLGATE_CACHE_EMBEDDER_MODEL` is required (surrounding whitespace is stripped), and
    `TOLLGATE_CACHE_EMBEDDER_URL` is optional, defaulting to `http://localhost:11434`. A variable that is set but
    blank is an error. ADR-0014 adds the threshold, the lifetime and the maximum number of entries. If any of
    the other cache variables is set while `TOLLGATE_CACHE_EMBEDDER` is unset, startup fails naming that
    variable. This differs from `TOLLGATE_REDIS_URL`, which is ignored under the memory backend: an operator who
    sets a threshold and forgets the embedder would otherwise run with the cache silently off, and believe it
    on. Every error is a `SettingsError` naming the variable, never the value. The URL is kept as a secret,
    because it can hold credentials.
  - **Ollama embedder.** One `httpx.AsyncClient`, built by `create_app()` and closed at shutdown with the
    others (T-203). It has the fixed 5-second connect timeout and 10 seconds for reads, writes and the pool. Each
    call is one request with no retry: `POST /api/embed` with `model`, `input` as one string and
    `"truncate": false`, sent through `post_json`, with the reply capped at 1,048,576 bytes (ADR-0013's helper).
    The reply must hold exactly one vector: a non-empty list of numbers, not bools, each converted with `float()`
    and finite (an integer too large for a float is rejected, not raised). The embedder normalises the vector
    again by its norm `math.sqrt(math.sumprod(v, v))`, and rejects a vector whose norm is zero or not finite.
    Every vector must have the length of the first one the embedder returned. Every failure (connection,
    timeout, any non-2xx including the 400 for an over-long input, or a reply that breaks these rules) raises `EmbeddingError`. Its message holds only the kind and the
    status. Sending `"truncate": false` means a long prompt is never cut down to a prefix that it shares with
    other prompts; it becomes a `skip` instead (ADR-0014). The 10-second read timeout and the 1,048,576-byte
    reply cap are chosen, not measured. A float written by JSON takes at most about 24 characters, so a
    1,024-dimension vector is under 30,000 bytes, far below the cap.
  - **Identity.** The embedder's identity is `ollama:<model>`, part of the partition key (ADR-0014).
  - **Search.** Vectors are kept as `array("d")`. A lookup scans only the entries of its partition, and
    computes each similarity with `math.sumprod`, as a dot product of unit vectors.
  - **Storage.** One cache per process, in memory, lost on restart. The limits are ADR-0014's maximum number of
    entries and its 65,536-byte cap on a stored answer, kept as its UTF-8 JSON bytes.
  - **Hashing embedder.** Lower-cased character trigrams, feature-hashed with BLAKE2b into 512 dimensions and
    L2-normalised, with identity `hashing:v1`. It needs no dependency and gives the same output in every
    process. It is a lexical baseline, not a semantic model. Tests and the eval harness's CI run use it, and no
    setting selects it at run time.
  - The recommended model for the owner's eval run is `all-minilm` (small, Apache-2.0, no prefix); `bge-m3` is
    the larger alternative. Models that need a task prefix are not supported until a prefix setting exists.
- **Consequences:**
  - No new dependency. The cache works only with an Ollama that has the embedding model pulled. Without one,
    every eligible request is a `skip`, and requests are still served.
  - Each worker process has its own cache, so the hit rate falls as processes are added, and a restart empties
    it. A shared cache on Redis 8 is a backlog item. It would need a newer CI image, and fakeredis cannot run
    `FT.SEARCH`.
  - The scan is linear in the size of the partition. With at most 100,000 entries it is bounded, but its cost
    has not been measured. Phase 4 measures it.
  - Memory is bounded by the maximum number of entries times the stored answer cap plus the vector, because the
    answer is kept as bytes. For a 1,024-dimension model that is 1,000 times (65,536 + 8 times 1,024) bytes,
    about 70 MiB, with the default maximum, and about 7 GiB at the largest allowed maximum of 100,000, plus
    Python's overhead per object.
  - Every eligible request waits on the embedder before its provider call. A host that does not answer adds up
    to the 5-second connect timeout to every eligible request, and the 10-second timeouts apply per network
    operation, with no total deadline, as for providers (ADR-0011). A refused connection fails at once.
  - `all-minilm` reads at most 256 word pieces, so with `"truncate": false` a longer prompt is a `skip`.
    Choosing the model sets the longest prompt the cache can serve.
  - The prompt text goes to the embedding server. With the default local Ollama it stays on the machine.
  - The hashing embedder's numbers measure lexical overlap, and every report labels them that way.
  - Delivered by T-301 to T-307. Accepted by the owner as written on 2026-11-21.

---

## ADR-0016

**Observability: a JSON request log and Prometheus metrics with the standard library, from bounded fields only
(amends ADR-0013 and ADR-0014)** · Accepted · 2026-11-23

- **Context:** Phase 4 makes the gateway observable. Earlier ADRs left gaps that only this closes. Nothing
  records that the settle cap applied (ADR-0012) or that a reply passed its size cap (ADR-0013). An embedder
  failure is a `skip` that looks like an ineligible request (ADR-0014). The embedding call's latency and the
  cache scan's cost are unmeasured (ADR-0014, ADR-0015). Checked on 2026-11-23 against the PyPI JSON API, the
  prometheus/client_python v0.26.0 tag, prometheus.io, the installed fastapi 0.162.2 source, the uvicorn 0.54.0
  tag and docs.python.org (3.13):
  - The Prometheus text format 0.0.4 is UTF-8 with `\n` line endings and a final line feed. HELP text escapes
    `\\` and `\n`, and label values escape `\\`, `\"` and `\n`. A name has at most one TYPE and one HELP line,
    and TYPE comes before its first sample. A histogram has cumulative `_bucket{le="..."}` series ending in
    `le="+Inf"`, which equals `_count`, plus `_sum`. Prometheus 3 fails a scrape whose Content-Type is missing
    or unknown, and accepts `text/plain; version=0.0.4` (prometheus.io/docs/instrumenting/exposition_formats/,
    prometheus.io/docs/prometheus/latest/migration/).
  - Naming practice: base units (seconds, bytes) and `_total` on counters. Labels must not hold unbounded sets
    such as user ids. Keep a metric's cardinality below about 10 and reconsider it above 100, and export 0 for
    label sets known in advance (prometheus.io/docs/practices/naming/,
    prometheus.io/docs/practices/instrumentation/).
  - `prometheus_client` 0.26.0 (uploaded 2026-07-24, Apache-2.0 AND BSD-2-Clause, a `py3-none-any` wheel with
    `py.typed`, no runtime dependency). Registering a metric name twice in its default global registry raises
    an error for duplicated timeseries, so a second app built in one process, as the tests do, needs its own
    `CollectorRegistry`. It exports `_created` series by default. Its multiprocess mode needs a directory set
    before the module is imported and wiped between runs, and its documentation describes gunicorn only.
  - The OpenTelemetry route needs `opentelemetry-sdk` 1.45.2, `opentelemetry-semantic-conventions` 0.66b2 and
    `opentelemetry-exporter-prometheus` 0.66b2. The exporter is a Beta release, and its README says it has no
    multiprocessing support.
  - fastapi 0.162.2 depends on `opentelemetry-api` (since 0.142.0) for its native telemetry: HTTP spans and an
    `http.server.request.duration` metric. It is active only once a global tracer, meter or logger provider
    other than the default proxy is set, and the `telemetry=` argument of `FastAPI` turns each part off
    (`fastapi/telemetry/_asgi.py`, `fastapi/applications.py`).
  - A Prometheus scrape job sends a bearer token through `authorization: {type: Bearer, credentials_file: ...}`
    (prometheus.io/docs/prometheus/latest/configuration/configuration/).
  - `json.dumps` with the default `ensure_ascii=True` escapes every non-ASCII and control character, so one
    record stays on one line. uvicorn 0.54.0 takes `--log-config <file>.json` (a `logging.config.dictConfig`
    dictionary) and `--no-access-log`.
  - In CPython 3.13 `time.perf_counter` is the same clock as `time.monotonic` (QueryPerformanceCounter on
    Windows). The injected `Clock` (`app/clock.py`) is the wall clock `time.time()`, which can step, so it
    cannot time a request.
- **Options:**
  - Metrics: (a) a small module that writes the text format itself, with the standard library; (b)
    `prometheus_client` with a registry per app; (c) the OpenTelemetry SDK and its Prometheus exporter.
  - Logs: (d) the standard `logging` module with a JSON formatter; (e) structlog or python-json-logger.
  - Where metrics are served: (f) `/metrics` on the API port, behind a token of its own; (g) a second port.
  - What a label or a log field may hold: (h) only values from sets fixed by the code or the route table;
    (i) also request values such as the model or the caller.
- **Decision (proposed):** (a), (d), (f) and (h).
  - **Timing.** A new interface, final once accepted: `MonotonicClock` with `monotonic_seconds() -> float`.
    `SystemMonotonicClock` reads `time.perf_counter()`. `create_app()` takes an optional `monotonic_clock=`,
    and tests inject a fake. No duration is ever taken from the `Clock`.
  - **What a request reports.** `run_route` returns `attempts: tuple[Attempt, ...]` on both outcomes, one per
    target tried. An `Attempt` holds the provider name, the outcome and the duration on the monotonic clock.
    The outcome is `ok`, one of ADR-0010's five failure kinds, `reply_too_large`, or `error` (an exception that
    is not a `ProviderError`). ADR-0013's cap raises `ReplyTooLargeError`, a subclass of `ProviderError` with
    kind `bad_response`, so every existing check of the kind behaves as before (amends ADR-0013). `Skip` gains
    `reason: Literal["not_eligible", "embedder_failed"]` (amends ADR-0014's interface). The chat route records
    the reserved tokens, the charged tokens, whether `charged_tokens` capped the settle, the cache result and
    the lookup's duration.
  - **Log.** One record per HTTP request, on the logger `tollgate.request` at INFO. A pure ASGI middleware
    writes it once the response has been sent, or once the handler has raised. `JsonFormatter` renders each
    record as one JSON object, with `ensure_ascii=True` and `allow_nan=False`. The app installs no handler.
    The committed `deploy/logging.json` is a dictConfig file for `uvicorn --log-config`. It sends
    `tollgate.request` and uvicorn's own loggers to stdout as JSON. The image runs with `--no-access-log`, so
    each request is logged once.
  - **Other loggers.** A record from any other logger (uvicorn's, or a library's) is written with `time`,
    `level`, `logger` and `message` only. When it carries an exception, `JsonFormatter` adds `exception_type`
    (the class name) and writes neither the exception's message nor the traceback. An exception text can echo
    provider internals or a prompt (`app/api/chat.py`), and uvicorn logs every unhandled exception.
  - **Log fields.** This is the full set, and a test pins it: `time` (UTC, ISO 8601, from the log record's
    creation time, so a test pins its format, not its value), `level`, `logger`,
    `event` (`http_request`), `method`, `path` (`/v1/chat/completions`, `/health` or `/metrics`, and `other` for
    every other path, FastAPI's `/openapi.json`, `/docs` and `/redoc` included),
    `status` and `duration_seconds`. A chat request that reached the route handler also has `provider` (the
    serving provider, or null), `fallbacks`, `cache` (`hit`, `miss`, `skip`, or null when no lookup ran),
    `skip_reason`, `reserved_tokens`, `charged_tokens`, `settle_capped` and `attempts` (each with its provider,
    outcome and duration). The log never holds the prompt, the messages, the model, the API key or its digest,
    the caller id, a header value, the query string or the client address. Provider names come from the route
    table and may hold any printable ASCII character; JSON escaping keeps them safe.
  - **Metrics.** `app/observability/metrics.py` holds counters and histograms. Every label value comes from a
    set bounded by the code or the route table, never from the request. The label sets known at startup are
    exported at 0, and only `status` adds series on first use. It writes text format 0.0.4 with the
    Content-Type `text/plain; version=0.0.4; charset=utf-8`, and no `_created` series. Each app has its own
    registry, on `app.state.metrics`. The set:
    - `tollgate_http_requests_total{path, status}` and the histogram
      `tollgate_http_request_duration_seconds{path}`
    - `tollgate_chat_completions_total{provider, cache}`, counted on each 200, with `cache` one of `hit`,
      `miss`, `skip` and `off` (the cache is off; the header then says `skip`)
    - `tollgate_provider_attempts_total{provider, outcome}` and the histogram
      `tollgate_provider_attempt_duration_seconds{provider}`
    - `tollgate_cache_lookups_total{result}` (`hit`, `miss`, `not_eligible`, `embedder_failed`) and the
      histogram `tollgate_cache_lookup_duration_seconds`
    - `tollgate_tokens_reserved_total`, `tollgate_tokens_charged_total` and `tollgate_settle_capped_total`,
      with no label
    - Histogram buckets, in seconds: 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30,
      60 and `+Inf`. They are chosen to span a mock call and a slow provider call, not measured.
    - `path` takes the same values as the log field: `/v1/chat/completions`, `/health`, `/metrics` (while the
      endpoint exists) and `other`, which covers every other path, served or not. `status` takes the statuses
      the app and Starlette answer, so its set is bounded by the code, not by the caller. It is not exported
      in advance: a `{path, status}` series appears at its first request. Every other label set is exported
      at 0 at startup: each path for the duration histogram, each route-table provider with each `cache` value
      and with each of the 8 outcomes, and each lookup `result`.
  - **Endpoint.** `GET /metrics` exists only when `TOLLGATE_METRICS_TOKEN` is set. Unset, it is a 404 like any
    unknown path. The token must not be blank, must be at least 32 characters, and must differ from every API
    key; otherwise startup fails with a `SettingsError` naming the variable, never the value. A request must
    carry `Authorization: Bearer <token>`. The header is read as raw bytes and decoded as UTF-8, as for API
    keys (`app/api/auth.py`), and the token is compared as SHA-256 digests with `hmac.compare_digest`. Anything
    else gets a 401 with `WWW-Authenticate: Bearer` and a body in ADR-0008's shape, with the same `type` as an
    API-key failure but its own `code`, `invalid_metrics_token`, and the message "Missing or invalid metrics
    token.", so a scraper is not told to send an API key. An API key never opens `/metrics`, and the
    metrics token never opens the chat route. The route is left out of the OpenAPI document, which is the
    client contract, so the snapshot does not change; `docs/setup.md` documents the route.
  - **FastAPI's telemetry.** `create_app()` turns FastAPI's native tracing, metrics and logs off explicitly,
    so an OpenTelemetry SDK installed later never starts a second, unreviewed set of spans and metrics.
  - **Processes.** Metrics and the log are per process. ADR-0017 runs one uvicorn process per container, so
    each process is one scrape target.
- **Consequences:**
  - No new dependency. The renderer is code the project owns. A mistake in it shows as a failed scrape, so
    its tests compare the exact text and check each line against the format rules above. A later move to
    `prometheus_client` would keep every metric name.
  - ADR-0012's and ADR-0013's "nothing records" gaps close, through `tollgate_settle_capped_total` and the
    `reply_too_large` outcome. An embedder outage shows as `embedder_failed`.
  - Series counts, with P route-table providers: each histogram has 18 series per label set (16 buckets, `_sum`
    and `_count`), so the request duration has 72 with four paths and the attempt duration 18 P. Attempts have
    8 P, chat completions 4 P, lookups 4, and requests one per path and status seen, at most the four paths
    times the statuses the code can answer. Several
    exceed the guideline of about 10 cited above. That is accepted, because each set is fixed by the code or the
    route table and stays in the hundreds for a small table. `docs/setup.md` gives the formula.
  - Tracebacks never reach the JSON log. To debug an exception, an operator runs uvicorn without
    `--log-config`, which uses uvicorn's own text format with tracebacks.
  - The log holds token counts and provider names, never request content. One request cannot be traced across
    systems, because there is no request id; a request-id header would change the contract and is a backlog
    item.
  - The record is written after the response is sent, so a crash between the two loses it.
  - The middleware sees every request, including a 401 before the body is read. A 400 or a 401 has only the
    base fields.
  - `MonotonicClock`, `Attempt`, `ReplyTooLargeError` and the `reason` of `Skip` join ARCHITECTURE section 3.
    ADR-0013's status is "Accepted - amended by ADR-0016", and ADR-0014's "Accepted - amended by ADR-0016".
  - Delivered by T-401 to T-404. Accepted by the owner as written on 2026-11-23.

---

## ADR-0017

**Container image, Docker Compose, and the deployment target: one host (amends ADR-0006)** · Accepted ·
2026-11-23

- **Context:** The deployment target is decided in a Phase 4 ADR (TASKS.md, "Requirements that carry into the
  task cards"). Today the gateway runs only as `uvicorn --factory app.main:create_app` on a development
  machine. Checked on 2026-11-23 against Docker Hub, docker-library/python, docs.docker.com, the uvicorn source
  and documentation, actions/runner-images, the providers' pricing pages and the GitHub documentation:
  - `python:3.13-slim` is Python 3.13.18 on Debian trixie. The image sets no `USER`, and the tag is rebuilt in
    place, so only a digest pins it. Docker's best-practices page recommends multi-stage builds, a
    `.dockerignore`, a digest pin, a non-root `USER` and an exec-form `CMD`. A shell-form `CMD` runs under
    `/bin/sh -c` and does not pass SIGTERM on.
  - uvicorn handles SIGINT and SIGTERM. It stops accepting connections, waits for open ones (bounded by
    `--timeout-graceful-shutdown`), and then runs the lifespan shutdown, which closes the app's clients (T-203).
    Its host defaults to 127.0.0.1. Its Docker page recommends one worker per container, scaled by containers.
  - Compose has `depends_on` with `condition: service_healthy`, `healthcheck`, `profiles` (a service in a
    profile starts only when that profile is active), read-only mounts and `docker compose up --wait`.
    `stop_grace_period` defaults to 10 seconds.
  - GitHub's `ubuntu-latest` (ubuntu-24.04, image 20261116.376.1) has Docker 28.0.4, Compose 2.38.2 and
    Buildx 0.39.0.
  - `redis:7.4.12` is still the current 7.4 tag, and CI uses it (ADR-0006). Redis 7.4 is licensed RSALv2 or
    SSPLv1, and Redis 8 RSALv2, SSPLv1 or AGPLv3. The repository names the image and never redistributes it.
    ADR-0006 did not record the licence.
  - `ollama/ollama:0.40.17` is about 3.4 GB compressed for amd64.
  - hadolint v2.15.1 lints Dockerfiles. It is GPL-3.0 and runs as a container in CI; it is never shipped.
  - Hosted options, from the pricing pages read on 2026-11-23 (these change often). Fly.io gives $1 of credit
    without a card. Render's free web service sleeps after 15 minutes without traffic, and its free Key Value
    is in memory only. Railway's free plan gives $1 a month and sleeps idle services. Koyeb requires a card and
    scales to zero. Cloud Run and Azure Container Apps have free allowances, but both need a billing account
    with a card. A sleeping or restarted instance loses the in-memory limiter and the cache.
  - The GitHub Container Registry is free for public images. Publishing needs `packages: write` in the
    workflow.
- **Options:**
  - Target: (a) one host running Docker Compose: the gateway and Redis, with Ollama optional; (b) a hosted free
    tier; (c) Kubernetes manifests or a Helm chart.
  - Checking the image in CI: (d) a separate job that lints, builds, starts the stack and sends smoke requests;
    (e) a build only; (f) no check.
  - Publishing the image: (g) to the GitHub Container Registry now; (h) decided with the demo in Phase 5.
- **Decision (proposed):** (a), (d) and (h).
  - **Image.** A multi-stage `Dockerfile` on `python:3.13-slim@sha256:<digest>`: the index digest resolved when
    T-405 is built, with the tag in a comment. The builder stage creates a virtual environment and installs
    `requirements.txt` with `--only-binary=:all:` and `--no-cache-dir`. The runtime stage copies the virtual
    environment, `app/` and `deploy/logging.json`, and nothing else. It runs as a non-root user with a fixed
    uid, exposes port 8000, and starts with the exec-form `CMD ["uvicorn", "--factory", "app.main:create_app",
    "--host", "0.0.0.0", "--port", "8000", "--log-config", "deploy/logging.json", "--no-access-log"]`, one
    worker. `.dockerignore` excludes everything and lists back only the paths the build copies, so `.env*`,
    `.venv`, `.git`, local notes and editor files never enter the build context.
  - **Compose** (`compose.yaml`):
    - `gateway` is built from the `Dockerfile`, uses the Redis limiter, and waits for Redis to be healthy. Its
      own healthcheck calls `/health` with the image's Python.
    - `redis` runs `redis:7.4.12`, the tag CI uses, with the healthcheck `redis-cli ping` and no published port.
    - The route table is mounted read-only from `deploy/routes.compose.json` at `/config/routes.json`, outside
      the app directory. It routes only to the mock provider, so the stack runs with no provider key and no
      outside network.
    - The API port is published on `127.0.0.1:8000` only.
    - `TOLLGATE_API_KEYS` and `TOLLGATE_METRICS_TOKEN` come from the caller's environment or an uncommitted
      `.env`, required through `${VAR:?...}`, and are never written in the file.
    - An `ollama` service in the `ollama` profile, with a named volume for models, is off by default.
  - **CI.** A new job, `container`, in `ci.yml`: hadolint on the `Dockerfile`, `docker compose config
    --quiet`, `docker compose build`, `docker compose up --wait`, `scripts/smoke_container.py` (standard library
    only) against `127.0.0.1:8000`, and `docker compose down`. It pulls the base images from Docker Hub and the
    wheels from PyPI, as the `lint and test` job already does. Its key and token are random values generated in
    the job at run time and written to `$GITHUB_ENV`, never to a file in the repository. Whether `container`
    becomes a required check is the owner's decision, made in the ruleset.
  - **Network exception (amends ADR-0006).** ADR-0006 made the localhost Redis service container the one
    exception to "no network in tests". This adds a second, in CI only: the `container` job's traffic on
    localhost to its own Compose stack (the smoke requests, and the checks of Redis and the logs through
    `docker compose`). pytest uses no network apart from ADR-0006's `redis_server` tests in CI.
  - **Deployment target.** One host running this Compose stack, with one gateway process per container. More
    gateway containers are supported only with `TOLLGATE_LIMITER_BACKEND=redis`: with the memory backend, N
    processes would allow N times the capacity. The cache and the metrics are per process in every case. The
    gateway does not serve TLS. On a host reachable from outside, a reverse proxy in front of it terminates
    TLS, and that proxy is outside this repository. There is no hosted deployment in Phase 4.
  - **Publishing** an image to the GitHub Container Registry is decided with the Phase 5 demo.
- **Consequences:**
  - The stack runs wherever Docker runs, with no paid service. On the owner's Windows machine it needs Docker
    Desktop; T-409 records whether it was run there.
  - A digest pin means base-image fixes arrive only when the pin is updated by hand, as for the actions' SHAs.
    The Dependabot backlog item now covers Docker as well.
  - CI time grows by one image build. The job blocks no merge unless the owner adds it to the ruleset.
  - Redis's licence is recorded: the stack runs Redis unmodified from its official image, under RSALv2 or
    SSPLv1, and the repository's MIT code is unaffected.
  - Without a hosted instance there is no public demo URL; Phase 5 decides.
  - ADR-0006's status is "Accepted - amended by ADR-0017".
  - Delivered by T-405 and T-409. Accepted by the owner as written on 2026-11-23.

---

## ADR-0018

**Load benchmarks: a fixed arrival rate measured from the due time, a fake upstream, recorded runs only** ·
Accepted · 2026-11-23

- **Context:** The README has no performance figure, and ADR-0005 requires every number to come from a recorded
  run with its settings. Phase 4 measures the latency the gateway adds and its throughput with each limiter,
  the cache scan's cost (ADR-0015), and the embedding call's latency (ADR-0014). Checked on 2026-11-23 against
  the sources named below:
  - A closed loop (fixed concurrency) waits for each answer before sending the next request, so a slow answer
    delays the requests behind it and is under-counted. This is coordinated omission (Gil Tene,
    "Coordinated Omission", mechanical-sympathy list, 2013-08-04; the wrk2 README). An open model sends at a
    fixed rate and measures each request from when it should have been sent: wrk2's `-R`, oha's
    `--latency-correction`, and k6's arrival-rate executors, which count `dropped_iterations`
    (grafana.com/docs/k6/latest/using-k6/scenarios/concepts/open-vs-closed/).
  - Envoy's benchmarking guide says to prefer an open loop and to measure latency below the knee, never at
    maximum load (envoyproxy.io, "How do I benchmark Envoy?"). Kong's uses a request-termination baseline and an
    upstream with no plugins, repeats runs and discards the first one or two
    (developer.konghq.com/gateway/performance/establish-a-benchmark/). LiteLLM's uses a mock upstream that
    waits 200 ms, a 60-second warm-up and fixed request rates (docs.litellm.ai/docs/benchmarks).
  - Tools: k6 v2.4.0 (AGPL-3.0, a Go binary); Locust 2.47.0 (MIT, but closed loop: its wait time "can only
    constrain the throughput", and it pulls in gevent, pyzmq, flask and more); vegeta (MIT); oha (MIT, with a
    Windows binary); wrk2 (Apache-2.0, no Windows build, no commit since 2019).
  - `statistics.quantiles(..., method="inclusive")` interpolates between order statistics. A sample p99 rests
    on about n/100 observations. The `timeit` documentation advises taking the minimum of the repeats and then
    looking at the whole vector. httpx 0.28.1's default pool allows 100 connections and keeps 20 alive.
    asyncio's platform notes say the event loop's timer is coarser on Windows than on Linux.
- **Options:**
  - Load generator: (a) a script in the repository on the standard library and httpx; (b) k6, oha or vegeta,
    installed by the owner; (c) Locust.
  - Load model: (d) an open loop at a fixed rate; (e) a closed loop at a fixed concurrency.
  - Upstream: (f) the mock provider only; (g) also a fake OpenAI-compatible server with a fixed delay, reached
    through the real `openai` adapter.
- **Decision (proposed):** (a), (d) and (g).
  - **Fake upstream.** `scripts/fake_upstream.py` is a Starlette app served by uvicorn. It answers `POST
    /v1/chat/completions` with a fixed OpenAI-shaped body and usage after a fixed delay (50 ms by default,
    chosen, not measured), and nothing else. It exists for benchmarks and no setting selects it in the gateway.
  - **Generator.** In `scripts/bench_load.py`, request i is due at the start plus i divided by the rate, and
    each request is sent as its own task. Times come from ADR-0016's monotonic clock (`time.perf_counter`;
    `time.get_clock_info("perf_counter")` on the owner's machine on 2026-11-23 reported QueryPerformanceCounter
    with a resolution of 1e-07 seconds). Latency is measured from the due
    time to the end of the response. The lag is measured from the due time to the moment the task hands the
    request to httpx. By default the client has no connection cap, so no request waits in httpx's pool, and the
    report records the peak number of requests in flight. When a cap is set, the time spent waiting for a
    connection counts as latency, and the report names the cap. Warm-up requests are sent and discarded.
  - **Report.** A run reports the request count, errors by status and transport errors, the achieved rate,
    the latency p50, p95, p99 and maximum (inclusive quantiles, with the method named), the lag p50, p99 and
    maximum, and the generator's CPU time. It also records its settings:
    - the scenario (`A`, `B` or `C`), the rate, the duration, the warm-up and the connection cap
    - what the gateway ran with, as given on the command line: the limiter backend, its tokens per minute and
      capacity, the route file's SHA-256, the fake upstream's delay, and whether the server ran under bare
      uvicorn or Compose
    - the request body's size and SHA-256 (the script sends one fixed body, with `max_tokens` fixed)
    - the git commit, the Python version, the OS, the CPU count, and whether the generator shares a machine
      with the server
    - The API key is read from an environment variable named on the command line and never written to the
      report. Output is a JSON report and a Markdown table, as for `scripts/eval_cache.py`.
  - **Validity.** A run is valid only if every response was a 200, no transport error occurred, and the lag
    p99 is at most 10% of the latency p99, both computed from the raw samples whatever their number. The 10% is
    chosen, not measured. A p99 is published only from at least 10,000 measured requests; with fewer, the
    report says "too few samples" in its place, and validity is still computed. For the published scenario
    runs, the measured duration is at least 60 seconds and long enough that the rate times the duration
    reaches 10,000. The limiter's settings must leave room for twice the reserved tokens the rate needs per
    minute, so that no request can be refused, and the report records them.
  - **Scenarios** (the owner's runs, T-409), all with the cache off:
    - A: the fake upstream, called directly
    - B: the gateway, through the `openai` adapter, to the fake upstream
    - C: the gateway with the mock provider
    - B and C each run with the memory limiter and with the Redis limiter.
    - B and C read committed route files under `deploy/bench/`, so their route tables are the same on every
      machine.
    - Each scenario runs at a fixed rate below the knee, found by a short ramp that is recorded with the runs.
      Each run is repeated 3 times, with at least 60 seconds measured after 10 seconds of warm-up.
    - The latency the gateway adds is reported as B minus A at each percentile, per repeat, never as one
      blended figure.
  - **Cache scan.** `scripts/bench_cache.py` fills one partition of an `InMemorySemanticCache` with N seeded
    unit vectors of D dimensions (N of 1,000, 10,000 and 100,000; D of 384 and 1,024). It times `lookup` with a
    fake embedder and a threshold no entry reaches, so every entry is scanned. It repeats with `timeit` and
    reports the minimum and median time per lookup.
  - **Embedding latency.** 100 sequential calls through `OllamaEmbedder` after one discarded call, recording
    the model and the Ollama version.
  - **CI.** The scripts' logic is unit-tested with a fake clock and `httpx.MockTransport` or
    `httpx.ASGITransport`. One tiny in-process run checks the report's shape. CI publishes no figure, because
    shared runners are noisy.
  - **Publishing.** Every figure goes into `docs/benchmarks.md` with its run's settings, and the JSON reports
    are committed under `docs/benchmarks/`. The README quotes figures only from there.
- **Consequences:**
  - No new dependency, and no AGPL tool. The generator is the project's own code, so it is tested like the
    gateway. The lag check catches a saturated generator but cannot prove there is none.
  - A generator and a gateway on one machine compete for the CPU. Every report says so, and figures from such a
    run describe that machine, not a production deployment.
  - One Python process can sustain only a limited rate. A run that fails the lag check is reported as invalid,
    not tuned until it passes. On Windows the event loop's timer is coarser, so runs there may fail the lag
    check more often than on Linux; the owner may then run under Linux, WSL2 or the Compose stack, and the
    report names the platform.
  - The 10,000-request floor sets the shortest run for a published p99: at a rate of 50 requests per second it
    takes 200 seconds of measurement.
  - The fake upstream's delay is chosen, not measured from a real provider. B minus A reflects the gateway's
    own work only as far as that work does not depend on the upstream's timing.
  - 100,000 entries of 1,024 dimensions hold about 800 MB of vectors (100,000 x 1,024 x 8 bytes). A machine
    without the memory skips that combination, and the report says so.
  - The 10% lag threshold is a chosen operating margin, not measured from data.
  - Delivered by T-406 to T-409. Accepted by the owner on 2026-11-23, with the line on the lag threshold
    added.

---

## ADR-0019

**No published image and no hosted demo; the demo is a recorded local run (amends ADR-0017)** · Proposed ·
2026-11-26

- **Context:** ADR-0017 left two choices to the Phase 5 demo: whether to publish the image to the GitHub
  Container Registry (its option (h)), and whether there is a public demo URL.
  - From ADR-0017's sources, checked 2026-11-23: the registry is free for public images, but publishing needs
    `packages: write` in the workflow; every hosted free tier checked needs a card, sleeps when idle, or gives
    about $1 of credit, and a sleeping or restarted instance loses the in-memory limiter and cache.
  - In the repository today: `ci.yml` grants only `contents: read`. `compose.yaml` builds the gateway from the
    `Dockerfile` (`build: .`), so nothing pulls a published gateway image. The base image is pinned by digest
    and updated by hand (ADR-0017).
  - The owner decided on 2026-11-26: no hosted demo. The demo is local, shown as text transcripts with optional
    screenshots, with no Prometheus or Grafana.
- **Options:**
  - (a) Publish to the GitHub Container Registry on every push to `main`.
  - (b) Publish on version tags only.
  - (c) Do not publish. The image is built locally by `docker compose build`, and `docs/demo.md` is the demo.
- **Decision (proposed):** (c). With no hosted instance, nothing would use a published image. Publishing would
  add the first write permission to CI, a public artifact whose base image ages between manual digest updates,
  and a versioning policy, and none of that helps a reader. Anyone can run the stack from source with one
  command, and anyone can read the demo without running it.
- **Consequences:**
  - Running the gateway needs Docker or Python 3.13. Reading `docs/demo.md` is the only way to see it work
    without running it.
  - CI keeps `contents: read` only.
  - The Backlog item "Image publishing" becomes "revisit if a hosted instance is added" (T-507).
  - ADR-0017's status becomes "Accepted - amended by ADR-0019".
  - Delivered by T-505 and T-507.

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
