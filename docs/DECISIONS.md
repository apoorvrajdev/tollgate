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
| [0006](#adr-0006) | Redis client, Lua token bucket and how it is tested | Accepted | 2026-11-12 |
| [0007](#adr-0007) | Rate-limit semantics: estimated tokens, token bucket, reserve and settle | Accepted | 2026-11-12 |
| [0008](#adr-0008) | HTTP contract for authentication, limit headers and errors | Accepted - amended by ADR-0009 | 2026-11-12 |
| [0009](#adr-0009) | Validation error codes and `param` format (extends ADR-0008) | Accepted | 2026-11-13 |
| [0010](#adr-0010) | Provider adapters: plain httpx, translation rules and a failure taxonomy (amends ADR-0007) | Proposed | 2026-11-13 |
| [0011](#adr-0011) | Routing: a route table file, ordered fallback on retryable failures | Proposed | 2026-11-13 |

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

**Redis client, Lua token bucket and how it is tested** · Accepted · 2026-11-12

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

**Rate-limit semantics: estimated tokens, token bucket, reserve and settle** · Accepted · 2026-11-12

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

**HTTP contract for authentication, limit headers and errors** · Accepted - amended by ADR-0009 · 2026-11-12

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

**Provider adapters: plain httpx, translation rules and a failure taxonomy (amends ADR-0007)** · Proposed ·
2026-11-13

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
    wrapper with no retries.
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
    cache fields. 529 means overloaded (platform.claude.com API docs). Anthropic's OpenAI-compatible endpoint
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
    and its timeout (connect 5 seconds). An app lifespan closes every client the app built, and the Redis client
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
    | `bad_response` | a 2xx that cannot be translated: invalid JSON, a missing field, an unknown finish reason, a negative or missing token count | no |

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
    `default_max_tokens`. Only `text` blocks form the reply. end_turn and stop_sequence map to stop, max_tokens
    and model_context_window_exceeded to length, refusal to content_filter, and anything else is
    `bad_response`. Prompt tokens are `input_tokens` plus `cache_creation_input_tokens` plus
    `cache_read_input_tokens`, an absent or null cache field counting 0; completion tokens are
    `output_tokens`. `id` comes from the injected id source and `created` from the injected clock.
  - **Settle on `bad_response` (amends ADR-0007).** The reservation is charged as made (settle with the actual
    amount equal to the reservation) and the answer is 502. Every failure before a 2xx keeps ADR-0007's full
    refund.
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
  - ADR-0007's status becomes "Accepted - amended by ADR-0010" when this ADR is accepted.

## ADR-0011

**Routing: a route table file, ordered fallback on retryable failures** · Proposed · 2026-11-13

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
  - **Route table file.** `TOLLGATE_ROUTES_FILE` names a JSON file with `providers` (name → `type` of `mock`,
    `ollama`, `openai` or `anthropic`, optional `base_url`, `api_key_env`, `timeout_seconds`, and
    `default_max_tokens` for `anthropic` only), `routes` (alias → 1 to 5 targets, each a `provider` and an
    optional upstream `model`; without one the client's model is passed through) and an optional `default`
    route. Unknown fields are rejected. A key is never in the file: `api_key_env` names the environment variable
    that holds it, read at startup. Every error names the variable and the field path, never a value. Without
    the variable a built-in table applies: one `mock` provider and a default route to it, so behaviour stays as
    it is today.
  - **Selection.** `Router.select(request) -> Route` matches `request.model` exactly against the aliases, then
    uses the default route, and otherwise refuses with 404 (`type: invalid_request_error`,
    `code: model_not_found`, `param: model`) before any estimate or reservation. A 404 carries no limit headers.
    The official SDK maps 404 to `NotFoundError`; whether OpenAI itself sends `model_not_found` in this case was
    not checked.
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
  - The worst-case latency of a request is the sum of the timeouts of its targets (at most 5). With no health
    tracking, a dead primary costs its timeout on every request until the configuration changes.
  - A 502 does not tell the client which upstream failed or why.
  - The contract gains the 404 and two response headers. `Router` and `Route` become final interfaces in
    ARCHITECTURE section 3.

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
