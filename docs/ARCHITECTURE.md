# Architecture

**Status:** Phase 4 complete (T-401 to T-409); Phase 5 is documentation only and changes no code. The app serves
`GET /health` and `POST /v1/chat/completions`, which is routed by model through a route table to the mock,
Ollama, OpenAI or Anthropic provider with ordered fallback, behind API key authentication and token-aware rate
limiting (tasks T-000 to T-210). With the cache on, it answers a request close in meaning to an earlier one from
an in-process semantic cache (T-301 to T-307); no similarity threshold is recommended, because the one embedding
model evaluated found none (`cache-eval.md`). Every completed request emits one record on the logger
`tollgate.request`, written as a JSON line when uvicorn runs with `deploy/logging.json`; `GET /metrics` exports
Prometheus metrics, and a Compose stack runs the gateway with Redis (T-401 to T-405).

Sections 1 to 5 describe parts of the system. Each part is labelled **built** or **not built**, and a part not
built names the ADR or Backlog item that keeps it out. Section 6 lists working rules, not parts. Decisions
behind the design are recorded in [DECISIONS.md](DECISIONS.md); work in progress is in [TASKS.md](TASKS.md).

## 1. Overview

Tollgate is an LLM gateway: one OpenAI-compatible HTTP API in front of several model providers. It adds three
things that a plain proxy lacks:

- **Token-aware rate limiting** (built). Limits are counted in tokens per minute, not requests, per API key, in
  memory or in Redis, chosen by `TOLLGATE_LIMITER_BACKEND`.
- **Model routing** (built). Each request goes to the route for its model alias, else the default route; the
  route's targets are tried in order, moving on only after a retryable failure (ADR-0010, ADR-0011).
- **Semantic caching** (built). A request that is close in meaning to an earlier one can be answered from an
  in-process cache, one per process; it is off by default, and no threshold is recommended (`cache-eval.md`).

Not built:

- Routing by cost, latency, load or health: ADR-0011 defers cost- and latency-based routing and load
  balancing, and has no health checks.
- Same-target retries, cooldowns and a request deadline: ADR-0010, ADR-0011; Backlog "Same-target retries,
  cooldowns and a request deadline".
- Streaming: `stream: true` is a 400 `unsupported_parameter` (ADR-0004, ADR-0009).
- A cache shared between processes: ADR-0015; Backlog "Shared semantic cache".
- A published image and a hosted demo: ADR-0019.
- TLS: the gateway serves plain HTTP, and a reverse proxy outside this repository would terminate TLS
  (ADR-0017; Backlog "TLS in front of the gateway").

It is a portfolio project. Every performance or cost claim must come from a reproducible run (see section 6).

## 2. Request flow (built)

One `POST /v1/chat/completions`, as `app/api/chat.py` runs it. `RequestMiddleware` wraps every request, so a
completed request is logged and counted whatever its status, after the app has returned.

```mermaid
flowchart TB
  C["Client"] --> MW["RequestMiddleware<br/>starts the monotonic timer"]
  MW --> AUTH{"API key valid?<br/>AuthenticatedRoute, before the body is read"}
  AUTH -->|"no"| R401(["401 invalid_api_key"])
  AUTH -->|"yes"| VAL{"Body valid?<br/>ChatRequest"}
  VAL -->|"no"| R400(["400 invalid_request_error"])
  VAL -->|"yes"| SEL{"Select route<br/>Router.select"}
  SEL -->|"no route"| R404(["404 model_not_found<br/>no limit headers"])
  SEL -->|"route"| EST["reserved_tokens:<br/>input estimate plus completion allowance"]
  EST --> RES{"RateLimiter.reserve<br/>under the caller id"}
  RES -->|"refused"| R429(["429 rate_limit_exceeded"])
  RES -->|"allowed"| CON{"Cache on?"}
  CON -->|"no"| RUN["run_route: targets in order, each once,<br/>next only after a retryable ProviderError"]
  CON -->|"yes"| LOOK{"SemanticCache.lookup<br/>under the caller id"}
  LOOK -->|"Hit"| SH["settle 0: full refund"]
  SH --> R200H(["200, x-tollgate-cache: hit"])
  LOOK -->|"Miss or Skip"| RUN
  RUN -->|"RouteFailed"| SF["settle: full refund,<br/>or as reserved after bad_response"]
  SF --> R502(["502 provider_error"])
  RUN -->|"Served"| SS["settle charged_tokens:<br/>usage capped at the bucket capacity"]
  SS -->|"after a Miss"| STORE["SemanticCache.store"]
  STORE --> R200(["200, x-tollgate-cache: miss or skip"])
  SS -->|"Skip or cache off"| R200
  R401 --> SENT["RequestMiddleware reports once the app returns:<br/>status, duration, ChatRecord"]
  R400 --> SENT
  R404 --> SENT
  R429 --> SENT
  R200H --> SENT
  R502 --> SENT
  R200 --> SENT
  SENT -->|"first observer"| LOG["log_request: one record<br/>on logger tollgate.request"]
  SENT -->|"second observer"| MET["request_metrics.observe:<br/>MetricsRegistry, read by GET /metrics"]
```

Not drawn: a handler that raises is reported as a 500 and the exception propagates, and a cancelled request is
not logged. A 400 or 401 log line has only the base fields, and a 404 or 429 has null chat fields. The app
installs no log handler: the record becomes a JSON line on stdout only through `deploy/logging.json`.
`GET /health` and `GET /metrics` pass through the same middleware.

| Stage | Responsibility | Status |
| --- | --- | --- |
| API layer | `/v1/chat/completions`, `/health`, request and response models, error shape | Built (Phase 0-1) |
| Providers | Adapters behind one interface: mock, then Ollama, then OpenAI and Anthropic | Built (Phase 1-2) |
| Token counting | Estimate before the call, settle with the provider's reported usage after | Built (Phase 1) |
| Rate limiter | Per-key token bucket, in memory (the default) or in Redis through redis-py and one Lua script (ADR-0006) | Built (Phase 1) |
| Router | Route table by model alias (ADR-0011); targets tried in order, each once, moving on only after a retryable failure (ADR-0010); a failed route is refunded, an untranslatable answer charged | Built (Phase 2) |
| Semantic cache | Looked up after the reservation under the caller id; embedding of the last user message, a similarity threshold, expiry after `TOLLGATE_CACHE_TTL_SECONDS` and eviction at `TOLLGATE_CACHE_MAX_ENTRIES`; a hit settles 0, and only a `stop` answer of at most 65,536 bytes after a miss is stored (ADR-0014, ADR-0015) | Built (Phase 3) |
| Operations | A pinned non-root image, a Docker Compose stack (gateway and Redis, Ollama optional) checked in CI, metrics, structured logs, load benchmarks (ADR-0016, ADR-0017, ADR-0018) | Built (Phase 4) |

## 3. Core interfaces (built)

Names are final once an ADR or task card fixes them. `Clock`, `Provider`, `TokenEstimator`,
`reserved_tokens`, `Decision` and `RateLimiter` are final (tasks T-101 to T-105); `ProviderError`,
`Route` and `Router` are final (T-201, T-202); `Embedder`, `EmbeddingError`, `SemanticCache`, `Hit`, `Miss`
and `Skip` are final (T-301 to T-306, ADR-0014, ADR-0015). `MonotonicClock`, `ReplyTooLargeError`,
`Attempt`, `AttemptOutcome` and `Skip.reason` are final (T-401, ADR-0016).

```python
class Clock(Protocol):
    def now_seconds(self) -> float: ...        # injected everywhere; tests use a fake

class MonotonicClock(Protocol):
    def monotonic_seconds(self) -> float: ...  # differences only, never goes back; the system one
                                               # reads time.perf_counter(); times each provider call

class Provider(Protocol):
    async def complete(self, request: ChatRequest) -> ChatResponse: ...

class TokenEstimator(Protocol):
    def estimate_input_tokens(self, request: ChatRequest) -> int: ...

def reserved_tokens(request: ChatRequest, estimator: TokenEstimator) -> int: ...
# the estimate plus max_completion_tokens, else max_tokens, else 0; this is what reserve() receives

@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    limit_tokens: int                          # the bucket capacity
    remaining_tokens: int                      # after the decision, rounded down, never below 0
    retry_after_seconds: int | None            # rounded up; None if allowed or larger than the capacity
    reset_seconds: int                         # until the bucket is full again, rounded up

class RateLimiter(Protocol):
    async def reserve(self, key: str, estimated_tokens: int) -> Decision: ...
    async def settle(self, key: str, reserved_tokens: int, actual_tokens: int) -> None: ...

class ProviderError(Exception):
    kind: ProviderErrorKind                    # connection, timeout, rate_limited,
                                               # upstream_status, bad_response
    status_code: int | None
    @property
    def retryable(self) -> bool: ...           # connection, timeout, rate_limited, and
                                               # upstream_status from 500 up

class ReplyTooLargeError(ProviderError):       # a 2xx reply passed the size cap; always a
    def __init__(self, status_code: int): ...  # bad_response, so existing callers are unchanged

type AttemptOutcome = Literal["ok", "connection", "timeout", "rate_limited", "upstream_status",
                              "bad_response", "reply_too_large", "error"]  # error: not a ProviderError

@dataclass(frozen=True, slots=True)
class Attempt:                                 # one provider call
    provider_name: str
    outcome: AttemptOutcome
    duration_seconds: float                    # on the MonotonicClock

# Served(completion, provider_name, fallbacks, attempts) and RouteFailed(charged, attempts) hold every
# Attempt in call order; run_route(route, providers, request, *, monotonic_clock) returns one of them.

type Route = tuple[TargetConfig, ...]          # ordered targets: a provider name and an
                                               # optional upstream model

class Router(Protocol):
    def select(self, request: ChatRequest) -> Route: ...   # alias, else default,
                                                           # else UnknownModelError

class Embedder(Protocol):
    @property
    def identity(self) -> str: ...             # type and model, such as "ollama:all-minilm"
    async def embed(self, text: str) -> array[float]: ...   # a unit vector

class EmbeddingError(Exception):               # not a ProviderError, so no fallback catches it
    kind: ProviderErrorKind
    status_code: int | None

@dataclass(frozen=True, slots=True)
class Hit:
    response: ChatResponse
    provider_name: str                         # the provider that produced the stored answer
    similarity: float

@dataclass(frozen=True, slots=True)
class Miss:
    ticket: Ticket                             # the partition key and the vector, for store()

@dataclass(frozen=True, slots=True)
class Skip:
    reason: Literal["not_eligible", "embedder_failed"]

class SemanticCache(Protocol):
    async def lookup(self, caller_id: str, request: ChatRequest) -> Hit | Miss | Skip: ...
    def store(self, ticket: Ticket, response: ChatResponse, provider_name: str) -> bool: ...
```

Interface changes require an ADR.

## 4. External contract (built)

The public HTTP API is OpenAI-compatible for chat completions (ADR-0004). A snapshot of the generated OpenAPI
document is committed, and a test fails when it changes unless the task allows it (task T-004). This is the
project's equivalent of a frozen baseline: callers can rely on the contract, and a change to it is always
deliberate.

## 5. Repository layout (built)

| Path | Contents | Committed |
| --- | --- | --- |
| `app/` | Gateway code (section 5.2) | yes |
| `tests/` | Unit, integration and contract tests; no network access | yes |
| `scripts/` | Cross-platform helper scripts: `check.py` (the one check command), `eval_cache.py` (the cache eval run), `regenerate_openapi.py` (the only writer of the contract snapshot, run only when a card changes the contract), `smoke_container.py` (the CI `container` job's smoke checks), and the benchmark scripts: `fake_upstream.py` (a fake OpenAI-compatible upstream with a fixed delay), `bench_load.py` (the fixed-rate load runner and its report, ADR-0018) and `bench_cache.py` (the cache scan and embedding latency benchmarks, ADR-0018) | yes |
| `eval/` | Fixed datasets for measurements: `cache_pairs.json`, the cache eval pairs | yes |
| `deploy/` | Deployment files: `logging.json` (the `uvicorn --log-config` file, copied into the image), `routes.compose.json` (the Compose route table, mock provider only, mounted read-only) and `bench/` (the load benchmark's route tables: `routes.fake-upstream.json` for scenario B, `routes.mock.json` for scenario C) | yes |
| `Dockerfile`, `.dockerignore`, `compose.yaml` | The gateway image and the one-host stack (section 5.1) | yes |
| `docs/` | `ARCHITECTURE.md`, `DECISIONS.md`, `TASKS.md`, `setup.md`, `cache-eval.md`, `benchmarks.md` with `benchmarks/` (the committed JSON run reports), `findings.md` and `routes.example.json` | yes |
| `pyproject.toml`, `requirements.txt`, `requirements-dev.txt` | Tool configuration and the pinned runtime and dev dependencies; `requirements.txt` is installed into the image | yes |
| `README.md`, `LICENSE`, `.gitignore`, `.gitattributes` | Project front page, licence and Git settings | yes |
| `.githooks/` | Commit guards (identity, message, blocked files); need Node.js | yes |
| `.github/workflows/` | CI: `ci.yml`, with the `lint and test` job and the `container` job (section 5.1) | yes |
| `.venv/` | Local virtual environment | no |

### 5.1 Image and deployment target (built; ADR-0017, ADR-0019)

- **Image** (built). Multi-stage `Dockerfile` on `python:3.13-slim` pinned by digest. `/app` holds `.venv`,
  `app/` and `deploy/logging.json` only; `.dockerignore` excludes everything except those inputs. It runs as uid
  10001 and starts uvicorn in exec form, so uvicorn is PID 1 and receives SIGTERM, with one worker.
- **Compose stack** (built). `gateway` (Redis limiter, `/health` healthcheck, published on `127.0.0.1:8000`
  only) and `redis` (`redis:7.4.12`, no published port). `TOLLGATE_API_KEYS` and `TOLLGATE_METRICS_TOKEN` are
  required `${VAR:?...}` references, never written in the file. The route table is mounted read-only at
  `/config/routes.json`, outside `/app`. An `ollama` service sits in the `ollama` profile, off by default.
- **CI** (built). The `container` job lints the `Dockerfile` with hadolint, builds and starts the stack, runs
  `scripts/smoke_container.py`, and checks Redis keys, the JSON log line, the non-root user, the contents of
  `/app` and a graceful stop. Its key and token are random per run.
- **Deployment target** (built). One host running this stack, one gateway process per container. More gateway
  containers need `TOLLGATE_LIMITER_BACKEND=redis`; the cache and the metrics stay per process.
- **Not built:** a hosted deployment and a published image (ADR-0019), and TLS: the gateway serves plain HTTP,
  and a reverse proxy outside this repository would terminate TLS (ADR-0017).

The deployment, as `compose.yaml`, the `Dockerfile` and `deploy/` define it. Prometheus is not part of the
stack: it is drawn dashed because only the gateway's `/metrics` route exists for it to scrape.

```mermaid
flowchart LR
  CLIENT["Client on the host"]
  subgraph STACK["docker compose stack on the same host, compose.yaml"]
    GW["gateway container<br/>built from the Dockerfile<br/>uid 10001, not root<br/>one uvicorn process on port 8000"]
    RD[("redis:7.4.12<br/>no published port")]
    OL["ollama/ollama:0.40.17<br/>profile ollama, off by default"]
    RF["deploy/routes.compose.json<br/>mock provider only"]
    OUT["container stdout<br/>JSON log lines"]
  end
  PROM["Prometheus<br/>outside the stack"]
  CLIENT -->|"127.0.0.1:8000 only"| GW
  RF -->|"mounted read-only at /config/routes.json"| GW
  GW -->|"token buckets at redis://redis:6379/0"| RD
  GW -.->|"only if a route or the cache embedder points at http://ollama:11434"| OL
  GW -->|"deploy/logging.json, JsonFormatter"| OUT
  PROM -.->|"GET /metrics with TOLLGATE_METRICS_TOKEN"| GW
  classDef outside stroke-dasharray: 5 5
  class PROM outside
```

In the stack as committed, the route table names only the mock provider and no cache variable is set, so the
gateway calls no upstream and the cache is off; Ollama is used only after a route or the cache is pointed at it.

### 5.2 Package layout and runtime behaviour (built)

The six packages and three top-level modules of `app/`, with each arrow pointing the way an import goes.

```mermaid
flowchart TB
  MAIN["app/main.py"] --> API["app/api"]
  MAIN --> CACHE["app/cache"]
  MAIN --> CLOCK["app/clock.py"]
  MAIN --> LIMITS["app/limits"]
  MAIN --> OBS["app/observability"]
  MAIN --> PROVIDERS["app/providers"]
  MAIN --> ROUTING["app/routing"]
  MAIN --> SETTINGS["app/settings.py"]
  API --> CACHE
  API --> CLOCK
  API --> LIMITS
  API --> OBS
  API --> PROVIDERS
  API --> ROUTING
  CACHE --> API
  CACHE --> CLOCK
  CACHE --> PROVIDERS
  LIMITS --> API
  LIMITS --> CLOCK
  OBS --> API
  OBS --> CLOCK
  OBS --> ROUTING
  PROVIDERS --> API
  PROVIDERS --> CLOCK
  PROVIDERS --> ROUTING
  ROUTING --> API
  ROUTING --> CLOCK
  ROUTING --> PROVIDERS
  SETTINGS --> ROUTING
```

The arrows into `app/api` from `cache`, `limits`, `providers` and `routing` import only `app/api/models.py`
(`ChatRequest`, `ChatResponse` and the types they hold); `observability` imports `app/api/auth.py` and
`app/api/errors.py` for `/metrics`. `providers` imports `routing` only for `DEFAULT_MAX_RESPONSE_BYTES`
(`app/routing/config.py`). No import is made only for type checking.

The modules in each package: `app/api/` (request and response models, the error body and handler, API key
authentication, the rate-limit headers in `limit_headers.py`, the chat router) and
`app/providers/` (the `Provider` protocol, `MockProvider`, `ProviderError` with its failure kinds in
`errors.py`, the Ollama adapter `OllamaProvider` in `ollama.py`, the OpenAI adapter `OpenAIProvider` in
`openai.py`, the Anthropic adapter `AnthropicProvider` in `anthropic.py`, `fields.py`: the reply checks the
adapters share, and `http_body.py`: `read_capped`, which reads a 2xx body in decoded chunks up to the
provider's `max_response_bytes` (ADR-0013), and `post_json`, beside it, the one request with its status and
failure mapping), `app/routing/` (`config.py`: the route table file, validated when the settings are read,
and the built-in table; `router.py`: `Route`, `Router`, `TableRouter` and `run_route`, the ordered fallback
loop),
`app/limits/` (the token estimator, the `RateLimiter` interface, `charge.py` (`charged_tokens`: the settle
charge capped at the bucket capacity, ADR-0012), the in-memory token
bucket, and the Redis token bucket: `redis_limiter.py` running `token_bucket.lua`, unit-tested against
fakeredis), plus `clock.py`, `settings.py` and `main.py`. The shared limiter
behaviour suite is `tests/limits/behaviour.py`; every limiter's test module runs it. `app/cache/` holds the
semantic cache: `embedder.py` (the `Embedder` protocol and `EmbeddingError`), `ollama_embedder.py`
(`OllamaEmbedder`, `POST /api/embed` through `post_json`), `hashing.py` (`HashingEmbedder`, the lexical
baseline for tests and the eval, never selectable at run time), `semantic.py` (`SemanticCache`, `Hit`, `Miss`,
`Skip`, `Ticket`, `partition_key` and `InMemorySemanticCache`: partitions, a `math.sumprod` scan, expiry and
eviction) and `evaluation.py`, the eval harness that measures hit and wrong-hit rates on
`eval/cache_pairs.json` (`docs/cache-eval.md`). `app/observability/` holds the request log and the metrics
(ADR-0016): `record.py`, `middleware.py` and `logs.py` for the log, and `metrics.py` (`MetricsRegistry` and the
text format), `request_metrics.py` and `endpoint.py` (`GET /metrics`) for the metrics, described below.
The OpenAPI document omits FastAPI's automatic 422, because the
API answers 400 (ADR-0008), so `create_app()` builds a small `FastAPI` subclass that strips it. Authentication
has two parts: the chat router's `AuthenticatedRoute` checks the key before the body is read, so a caller
without a key never sees a validation error, and the `require_api_key` dependency returns the caller identity
and makes the OpenAPI document record the bearer scheme.

`create_app()` also builds the `HeuristicEstimator` and the limiter chosen by `TOLLGATE_LIMITER_BACKEND`, on
the injected clock, and keeps them on `app.state`: `InMemoryRateLimiter`, or `RedisRateLimiter` on an optional
injected Redis client (tests pass fakeredis) or one built from `TOLLGATE_REDIS_URL`, kept on
`app.state.redis_client`. Every client `create_app()` builds (one `httpx.AsyncClient` per HTTP provider of the route table, then the
embedder's client when the cache is on, then the Redis client built from the URL; an injected client is the caller's) is appended to
`app.state.owned_clients`, and the app lifespan closes the
list at shutdown, last built first. A close that raises does not stop the others; once all have been tried the
errors are raised together as an `ExceptionGroup`, so a failure is never hidden. It also builds the provider
registry (provider name to `Provider`: a `MockProvider` per `mock` entry, an `OllamaProvider` per `ollama`
entry, an `OpenAIProvider` per `openai` entry with the key read from its `api_key_env`, and an
`AnthropicProvider` per `anthropic` entry with its key and `default_max_tokens`; the mock, Ollama and Anthropic
ones on the injected clock and one shared id source; the HTTP ones each on their own client with the ADR-0010 timeouts, their
provider's default base URL when `base_url` is absent or empty, their `max_response_bytes` and the
`http_transport=` keyword's transport, which tests set to an
`httpx.MockTransport`; every route table type has a branch, which mypy checks through `assert_never`) and a
`TableRouter` on the route table, kept on
`app.state.providers` and `app.state.router`. The `provider=` keyword sets the entry named `mock` and
`providers=` then sets entries by name; an entry the route table does not name is never routed to. With the
cache on (`TOLLGATE_CACHE_EMBEDDER`), it builds an `OllamaEmbedder` on its own client, or takes the injected
`embedder=`, kept on `app.state.embedder`, and an `InMemorySemanticCache` on it and the clock, kept on
`app.state.cache`; both are `None` with the cache off. The id source the providers share is kept on
`app.state.id_source`. The chat route reads the registry, the router, the limiter, the cache, the id source,
the clock and the monotonic clock (`monotonic_clock=`, else a `SystemMonotonicClock`) from `app.state` on
every request. It selects the route first, answering a model that no route
serves with the ADR-0011 404 before any estimate or reservation, and with no limit headers. It then
reserves the estimate plus the completion allowance under the caller id and answers a refusal with 429, so
a 404, 400 or 429 never reaches the embedder. With the cache on it then looks the request up under the caller
id (ADR-0014). A hit runs no target and settles once with 0, refunding the reservation in full, and answers
the stored response with a new `id` from the id source and `created` from the clock, `x-tollgate-provider`
naming the provider that produced the stored answer and `x-tollgate-fallbacks: 0`. A miss runs the route, and
after the settle its 200 is offered to `store`, which keeps only a single `stop` choice of at most 65,536 bytes of JSON. A skip (not eligible,
or an `EmbeddingError`) runs the route as if the cache were off; any other exception from the lookup is a 500.
Every 200, and no other status, carries `x-tollgate-cache`: `hit`, `miss` or `skip`.
`run_route` tries each target once, in order, with the request's `model` replaced by the target's upstream
model (the client's when it has none), and moves on only after a retryable `ProviderError`. It times
each call on the monotonic clock and returns an `Attempt` for every call, whatever its outcome; the
request log and the metrics (below) report them. A 200 settles
once with the serving attempt's `usage.total_tokens`, capped at the bucket capacity (`charged_tokens` with the
reserve decision's `limit_tokens`, ADR-0012) while the response's `usage` is returned unchanged, keeps the body
`model` the provider reported, and carries `x-tollgate-provider` and `x-tollgate-fallbacks`. A route that ends without an answer gives the
ADR-0008 502: the whole reservation is refunded, except after a `bad_response`, which is charged as
reserved (ADR-0010). Only the provider calls are guarded, so a limiter error is a 500, never a refund.
The limit headers come from the `Decision` that `reserve` returned, so a 200 shows the balance after the
reservation and a 502 the balance before the settle; the next request sees the settled balance.

Every HTTP request writes one JSON line to the logger `tollgate.request` (ADR-0016). The chat route creates a
`ChatRecord` (`app/observability/record.py`) in the ASGI scope's `state`, so the record belongs to one request,
and fills it as each step runs: the serving provider and the fallbacks, the cache result and the skip reason,
the reserved and charged tokens, whether the settle was capped (the reported total was above the capacity),
the attempts and the cache lookup's duration. A field stays `None` until its step has run, so a 404 or a 429
has null chat fields, a cache hit has no attempts, a 502 has no serving provider, and a cache that is off has
no cache result. `RequestMiddleware` (`middleware.py`) is a pure ASGI middleware, added by `create_app()`. It
times the request on the monotonic clock, reads the status from `http.response.start`, and reports once the
app has returned, so the duration includes sending the body. A handler that raises is reported once, with
the status already sent or 500, and the exception propagates; a cancelled request is not logged. It maps the path to `/v1/chat/completions`,
`/health` or `/metrics` exactly, and everything else, FastAPI's documentation routes included, to `other`.
The result goes to its observers, `log_request` first and the metrics second. `JsonFormatter` (`logs.py`)
writes the ADR-0016 fields for `tollgate.request`, and only `time`, `level`, `logger`, `message` and
`exception_type` for any other logger, never an exception's message or traceback. It uses `ensure_ascii`,
so a line is one ASCII line. The app installs no handler: `deploy/logging.json` is the `dictConfig` file for
`uvicorn --log-config`. It sends `tollgate.request` and uvicorn's loggers to stdout through `JsonFormatter`,
and silences `uvicorn.access`, whose message holds the path, the query string and the client address.
`create_app()` also turns FastAPI's native telemetry off (`NATIVE_TELEMETRY_OFF` in `app/main.py`).

The metrics (ADR-0016) live in one `MetricsRegistry` per app, on `app.state.metrics`, built by
`build_request_metrics` (`app/observability/request_metrics.py`) from the route table's provider names; it is
never a module-level object. Its `observe` is the middleware's second observer and reads only the request
result: the path and status feed the request counter and duration histogram, a 200 with a serving provider
feeds `tollgate_chat_completions_total` (`off` when no lookup ran), each attempt feeds the attempt counter and
histogram, a lookup feeds `tollgate_cache_lookups_total` by its result or skip reason, and the reserved and
charged tokens (the charge already capped) and a capped settle feed the three token counters. Label sets known
at startup are exported at 0; `status` is the one label that appears on first use. No label is `method`, which
the log carries as received. `GET /metrics` (`app/observability/endpoint.py`) is registered only when
`TOLLGATE_METRICS_TOKEN` is set, is left out of the OpenAPI document, and answers with the registry's text
format. It accepts exactly one `Authorization: Bearer <token>` and compares SHA-256 digests with
`hmac.compare_digest`; anything else is a 401 with code `invalid_metrics_token`. A scrape is counted after it is
rendered, so it never shows itself. With the token unset, `/metrics` is an ordinary 404 and counts as `other`.

The Redis token bucket keeps one hash per API key at a prefix plus the SHA-256 digest of the key
(default prefix `tollgate:bucket:`), so the key itself is never written to Redis. The hash holds
`balance_units` (tokens x 60000) and `updated_milliseconds`; in those units one millisecond refills
exactly `tokens_per_minute` units, so the script works only with integers below 2^53 and agrees with
the exact in-memory reference. The script takes the time from the injected `Clock`, rounded down to
whole milliseconds, never from the server, and returns the balance as the fraction string
`"<n>/60000"`. `capacity_tokens` and `tokens_per_minute` are each at most 75,059,993,789, and a
charge stops at a debt of that many tokens, which the in-memory limiter does not. Each call sets
the key to expire once the bucket would be full again plus 60 seconds, because a missing key starts
full. Calls that reach Redis out of order are handled like a clock that steps back: no refill, and
the timestamp never moves back.

## 6. Conventions

- **Language and tools:** Python 3.13. ruff for lint and format, mypy in strict mode, pytest (ADR-0003).
  One command runs everything: `python scripts/check.py`.
- **Shell:** commands in the docs work in Git Bash on Windows. Use `.venv/Scripts/python -m ...`, never the
  MSYS2 `python`, which has no prebuilt wheels for compiled dependencies.
- **Units in names:** `tokens`, `seconds`, `milliseconds`, `usd` appear in names (`window_seconds`,
  `estimated_tokens`). No bare numbers that could mean either.
- **Time:** code never calls `time.time()` or `asyncio.sleep` directly where logic depends on it; it takes a
  `Clock`. Tests advance a fake clock instead of waiting.
- **Tests never touch the network or a paid API.** Providers are mocked or faked; Redis is replaced by an
  in-process fake unless an ADR says otherwise. Real provider calls happen only by hand.
- **Secrets:** read from environment variables only; never committed, never logged. `.env.example` lists names
  without values.
- **Evidence-first claims:** a latency, throughput, hit-rate or cost figure in a README or PR comes from a
  recorded run with its configuration stated. Unknown means "unknown".
- **Dependencies:** each one is listed in the task that needs it. Runtime and dev dependencies are separate.
