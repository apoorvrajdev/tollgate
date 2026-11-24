# Setup

How to get the project running on a Windows development machine with Git Bash. `python scripts/check.py` is the
single check command (ADR-0003).

## Prerequisites

| Tool | Required | Detected when this guide was written |
| --- | --- | --- |
| Python | standard Windows build of 3.13 from python.org (not the MSYS2/MinGW one) | 3.13.2 via `py -3.13` |
| Git | any recent version | 2.52.0 (Windows) |
| Node.js | 20 or newer, for the commit hooks and their tests | 24.12.0 locally; 26 in CI (`actions/setup-node`, `node-version: "26"`) |
| GitHub CLI | only for opening pull requests | 2.92.0 |

Why not the MSYS2 Python: `python -c "import sysconfig; print(sysconfig.get_platform())"` prints
`mingw_x86_64_ucrt_gnu` there, so pip finds no prebuilt wheels for packages such as pydantic-core and tries to
compile them. A standard Python prints `win-amd64`. Check with `py -0p`.

## Get the code and install

```bash
git clone https://github.com/apoorvrajdev/tollgate.git
cd tollgate
py -3.13 -m venv .venv
source .venv/Scripts/activate
python -m pip install --only-binary=:all: -r requirements-dev.txt
```

`requirements.txt` holds the runtime packages (what the gateway needs to run). `requirements-dev.txt` adds the
test and lint tools and includes the runtime file. `--only-binary=:all:` makes pip fail instead of compiling from
source if a wheel is missing. After activation, `python` is the venv's Python. Without activating, call
`.venv/Scripts/python` explicitly.

The project is run from the repository root and is not installed as a package (there is no build step), so
`pip install .` does not apply.

## Run and check

```bash
python scripts/check.py
uvicorn --factory app.main:create_app --reload
curl localhost:8000/health   # {"status":"ok"}
```

`scripts/check.py` runs five steps in order and stops at the first failure, naming it:

| Step | Command it runs |
| --- | --- |
| 1 | `ruff check .` |
| 2 | `ruff format --check .` |
| 3 | `mypy` (strict; paths come from `pyproject.toml`) |
| 4 | `contract`: `pytest tests/test_openapi_snapshot.py` (live OpenAPI equals the snapshot) |
| 5 | `pytest --ignore=tests/test_openapi_snapshot.py` (every other test) |

Run it before every commit. To fix formatting, run `python -m ruff format .`.

### Redis integration tests

The shared limiter suite also runs against a real Redis server. Those tests carry the `redis_server` marker,
which the default pytest options deselect, so `check.py` never touches the network. CI runs them in the
`redis integration` step against a `redis:7.4.12` service container. To run them by hand, if you have a local
Redis:

```bash
TOLLGATE_TEST_REDIS_URL=redis://localhost:6379/0 .venv/Scripts/python -m pytest -m redis_server
```

With the marker selected and the variable unset, the tests fail and name the variable; they never skip. Each
limiter writes under its own `tollgate-test:<run id>:<n>:` prefix and the tests delete those keys afterwards.

## Configuration

The gateway reads its settings from environment variables when the app is built, and refuses to start if one is
invalid. The error names the variable and the reason, never the value. API keys and the Redis URL are masked in
`repr()` and never appear in error messages. Do not put real values in the repository.

| Variable | Meaning | Default | Required |
| --- | --- | --- | --- |
| `TOLLGATE_API_KEYS` | Comma-separated API keys that clients may present; surrounding spaces are trimmed, empty keys are rejected | none | yes |
| `TOLLGATE_TOKENS_PER_MINUTE` | Refill rate of each key's token bucket, as a whole number greater than 0; at most 75,059,993,789 with the `redis` backend | none | yes |
| `TOLLGATE_CAPACITY_TOKENS` | Bucket capacity in tokens, a whole number greater than 0; at most 75,059,993,789 with the `redis` backend | the value of `TOLLGATE_TOKENS_PER_MINUTE` | no |
| `TOLLGATE_LIMITER_BACKEND` | `memory` or `redis` (lower case, exact) | `memory` | no |
| `TOLLGATE_REDIS_URL` | Redis connection URL; may contain a password | none | only when the backend is `redis` |
| `TOLLGATE_ROUTES_FILE` | Path to a JSON route table (below); surrounding spaces are trimmed, and set but blank is an error | the built-in table: one `mock` provider and a default route to it | no |
| `TOLLGATE_CACHE_EMBEDDER` | Turns the semantic cache on; the only value is `ollama` (lower case, exact) | unset: the cache is off | no |
| `TOLLGATE_CACHE_EMBEDDER_MODEL` | The Ollama embedding model, for example `all-minilm`; surrounding spaces are trimmed | none | when the cache is on |
| `TOLLGATE_CACHE_EMBEDDER_URL` | Base URL of the Ollama server; may contain credentials, so it is masked in `repr()`; set but blank is an error | `http://localhost:11434` | no |
| `TOLLGATE_CACHE_SIMILARITY_THRESHOLD` | Cosine similarity needed for a hit: `0.5` to `1`, at most 4 decimal places (`0.9`, `0.8750`, `1`, `1.0000`) | none | when the cache is on |
| `TOLLGATE_CACHE_TTL_SECONDS` | How long an entry lives, a whole number from 60 to 604,800 | `3600` | no |
| `TOLLGATE_CACHE_MAX_ENTRIES` | Most entries kept, a whole number from 1 to 100,000 | `1000` | no |
| `TOLLGATE_METRICS_TOKEN` | Turns on `GET /metrics`, which needs `Authorization: Bearer <token>`; surrounding spaces are trimmed; at least 32 characters, not blank, and different from every API key; masked in `repr()`. The route is not in the OpenAPI document, and a scrape does not count itself | unset: no `/metrics` route (404) | no |

Numbers are plain ASCII digits, at most 18: `1_000`, `1e3`, `1.5`, signs and spaces inside the number are
rejected. `TOLLGATE_REDIS_URL` is ignored when the backend is `memory`.

The cache variables follow stricter rules. A cache variable that is set while `TOLLGATE_CACHE_EMBEDDER` is unset
stops startup and names that variable, even when it is blank: unlike `TOLLGATE_REDIS_URL`, it is never ignored,
so a threshold set without the embedder cannot leave the cache silently off. Set but blank is always an error and
never takes a default. The embedder URL is not checked for syntax at startup, only that it is not blank
(a malformed one that the HTTP client rejects stops startup naming the variable, never showing the value).
With the cache on, the app builds the embedder on its own HTTP client (5-second connect timeout, 10 seconds for
reads, writes and the pool), which it closes at shutdown; the chat route uses it (see "Semantic cache").

### Route table

The route table (ADR-0011) names the providers and the targets that serve each model. It is read and fully
checked when the settings are read, so a broken file stops the gateway at startup. Each request is routed by
its `model` and falls back to the next target on a retryable provider failure. All four types, `mock`,
`ollama`, `openai` and `anthropic`, are built. An `ollama` provider talks to `base_url` (default `http://localhost:11434`) through
Ollama's native `POST /api/chat`; `timeout_seconds` applies to each read, write and pool wait, and connecting
always waits at most 5 seconds. The gateway checks nothing about `base_url` at startup (an empty one counts as not given): a
malformed one fails when the first request uses it. Credentials in `base_url` are sent as HTTP Basic
authentication and are not treated as secrets by the gateway. An `openai` provider posts to
`<base_url>/v1/chat/completions` (default `base_url` `https://api.openai.com`), so `base_url` is the host
without `/v1`: `https://api.openai.com/v1` would request `/v1/v1/chat/completions`, a path that does not
exist; a 429 and any 5xx are retryable and fall back, and any other 4xx does not. Its key is sent only as `Authorization: Bearer <key>`. The client's `max_completion_tokens`,
else `max_tokens`, is sent as `max_completion_tokens` (never `max_tokens`); `temperature` and each message's
`name` are forwarded when given, and `user` is not. The upstream `id`, `created` and `model` are kept. An
`anthropic` provider posts to `<base_url>/v1/messages` (default `base_url` `https://api.anthropic.com`, again
the host without `/v1`) with `anthropic-version: 2026-10-21`; its key is sent only as `x-api-key`. Every
system message is joined with a line break, in order, into Anthropic's `system` field. `max_tokens` is the
client's `max_completion_tokens`, else `max_tokens`, else the provider's `default_max_tokens`. The client's
`temperature` is never sent, because that API version rejects any temperature, and neither are `name` and
`user`. The reply is the text blocks joined in order (thinking and other blocks are dropped), and prompt
tokens include both cache counts. The response `id` and `created` come from the gateway, and `model` is the
one Anthropic reports. A 429 and any 5xx, including 529 (overloaded), are retryable and fall back; any other
4xx does not. A request made only of system messages is sent with an empty `messages` list, and Anthropic's
answer to it has not been checked.

```json
{
  "providers": {
    "local": {"type": "ollama", "base_url": "http://localhost:11434", "timeout_seconds": 60},
    "cloud": {"type": "openai", "api_key_env": "OPENAI_API_KEY"},
    "claude": {"type": "anthropic", "api_key_env": "ANTHROPIC_API_KEY", "default_max_tokens": 1024},
    "test": {"type": "mock"}
  },
  "routes": {
    "fast": [{"provider": "local", "model": "llama3.2"}, {"provider": "cloud", "model": "gpt-4o-mini"}]
  },
  "default": [{"provider": "test"}]
}
```

- `providers` and `routes` are required (either may be empty); `default` is optional. Unknown fields and
  duplicate keys are rejected at every level, and so are an empty provider name, an empty alias and an empty
  upstream `model`.
- A provider name is sent back to the client in the `x-tollgate-provider` header, so it must be made only of
  visible ASCII characters (`!` to `~`): no space, control character, line break or non-ASCII character. A name
  that is not fails at startup with `TOLLGATE_ROUTES_FILE: providers: has a provider name that is not made only
  of visible ASCII characters (! to ~)`; the message never shows the name.
- `type` is exactly `mock`, `ollama`, `openai` or `anthropic`. `base_url`, `timeout_seconds` (a whole number
  from 5 to 600, default 60) and `max_response_bytes` (a whole number from 1,024 to 67,108,864, default
  8,388,608) are allowed for the three HTTP types, not for `mock`. `api_key_env` is required for `openai` and
  `anthropic` and not allowed for the others. `default_max_tokens` (at least 1) is required for `anthropic` and
  not allowed for the others.
- `max_response_bytes` caps the body of a successful reply, counted after gzip or deflate is decoded. Reading
  stops at the chunk that passes the limit; the client gets the 502, the route does not fall back to its next
  target, and the request stays charged its reservation. Raise the value for that provider if its real replies
  are larger. Memory can pass the limit by one decompressed chunk, and a compressed chunk of up to 64 KiB can
  expand far beyond its size, so the cap bounds the body read, not exactly the memory used (ADR-0013).
- A route, and `default`, has 1 to 5 targets, each a defined `provider` and an optional upstream `model`;
  without `model`, the client's model is passed through.
- Keys never go in the file. `api_key_env` is the name of the environment variable that holds the key (letters,
  digits and underscores, not starting with a digit). The variable must be set and not blank; surrounding
  spaces are trimmed. The key is sent in an HTTP header, so what remains must be made only of visible ASCII
  characters (`!` to `~`); a key with a space, a line break or a non-ASCII character inside it stops the
  gateway at startup with an error that names the variable and never shows the key.
- The file must be UTF-8 without a byte order mark (some editors, such as Windows Notepad, add one).
- Errors name `TOLLGATE_ROUTES_FILE` and the field path, for example
  `TOLLGATE_ROUTES_FILE: routes.fast[0].provider: names an undefined provider`, or the key variable that is
  missing. They never show a value from the file or the environment, and an unreadable file is reported
  without its path.

### Running against real providers

[routes.example.json](routes.example.json) is a working route table with one provider of each real type and two
routes with fallback; a test loads it, so it cannot drift from the schema. The model names in it are examples:
change them to models your accounts can use. Real calls are made only by you, by hand, with your own keys; tests
and CI never make them. Calls to OpenAI and Anthropic cost money.

1. Copy the example outside the repository (or keep your copy untracked) and edit it. Keys never go in the file
   or in the repository: the file holds only the name of the variable, in `api_key_env`.
2. Set the variables in your shell and start the gateway (Git Bash, from the repository root):

   ```bash
   export TOLLGATE_API_KEYS="<a long random gateway key>"
   export TOLLGATE_TOKENS_PER_MINUTE=60000
   export TOLLGATE_ROUTES_FILE="<path to your copy>"
   export OPENAI_API_KEY="<your OpenAI key>"          # only if the file has an openai provider
   export ANTHROPIC_API_KEY="<your Anthropic key>"    # only if the file has an anthropic provider
   .venv/Scripts/python -m uvicorn --factory app.main:create_app
   ```

   A missing or blank key variable, or any schema error, stops the gateway at startup and names the variable,
   never the value. For a run against Ollama only, edit your copy of `routes.example.json`: remove the `openai`
   and `claude` providers and every target that names them, and delete the `smart` route, which is left with no
   target (`fast` keeps only `local`, and `default` already points to `local`). Make sure Ollama is running with
   the model pulled, for example `ollama pull llama3.2`.
3. Send a request. `model` selects the route (`fast` above). A model that is neither a route nor covered by
   `default` is a 404, but `routes.example.json` has a `default` to `local`, so with it any other model name goes
   to `local` and you will not see a 404:

   ```bash
   curl -i localhost:8000/v1/chat/completions \
     -H "Authorization: Bearer ${TOLLGATE_API_KEYS%%,*}" \
     -H "Content-Type: application/json" \
     -d '{"model": "fast", "messages": [{"role": "user", "content": "Say hello."}], "max_tokens": 50}'
   ```

   (The header uses the first of the gateway keys.) The response carries `usage`, the three
   `x-ratelimit-*-tokens` headers, `x-tollgate-provider` (the provider that answered) and `x-tollgate-fallbacks`
   (how many targets failed before it).
4. Fallback: targets are tried in order. A retryable failure (a timeout, a connection error, a 429 or a 5xx from
   the provider) moves to the next target; any other failure, such as a 4xx other than 429 or a reply over
   `max_response_bytes`, does not. If every target fails, or one fails without fallback, the client gets the 502.
   Stop the local Ollama and send the request again to see the second target answer (`x-tollgate-fallbacks: 1`); that call goes to OpenAI and is billed.
5. Timeouts: `timeout_seconds` (default 60, 5 to 600) applies to each read, write and pool wait of an HTTP
   provider, and connecting always waits at most 5 seconds. It is not a limit on the whole request.

### Authentication

`POST /v1/chat/completions` requires `Authorization: Bearer <key>`, where the key is one of
`TOLLGATE_API_KEYS`. Every failure gets the same 401 (a missing header, a scheme other than `Bearer`, an empty
or unknown key, or more than one `Authorization` header), with a `WWW-Authenticate: Bearer` header; a header
value with a NUL, form feed or vertical tab byte never reaches the gateway, because uvicorn answers it with its
own 400. The scheme
name is case-insensitive, and extra spaces between the scheme and the key (or after it) are ignored. A tab
between them, or other whitespace such as a non-breaking space, is not; a tab at the start or end of the whole
header value is removed by the HTTP parser (h11, which uvicorn uses here) before the gateway sees it. The
check runs before the body is
read, so an unauthenticated request never gets a validation error. The authenticator keeps only SHA-256
digests of the keys, and the digest is the caller id used later for rate limits; the configured keys themselves
stay in the settings as masked secrets. The digests are unsalted, so use long random keys. Header bytes are
read as UTF-8, so a non-ASCII key works only if the client sends it as UTF-8; plain printable ASCII keys avoid
the question.

`GET /health` needs no key. `/openapi.json` and `/docs` also need no key, which is a known gap: they describe
the API but not any key or user data.

### Rate limits

Each API key has a token bucket of `TOLLGATE_CAPACITY_TOKENS`, refilled at `TOLLGATE_TOKENS_PER_MINUTE`. A chat
completion reserves an estimate of its prompt plus `max_completion_tokens` (or `max_tokens`) before the
provider is called, and the provider's reported usage is charged or refunded afterwards. Responses that reach
the limiter (200, 429 and 502) carry `x-ratelimit-limit-tokens`, `x-ratelimit-remaining-tokens` and
`x-ratelimit-reset-tokens` (written `45s` or `6m0s`; an hour or more is written in minutes, such as `60m0s`).
Those headers show the balance right after the reservation, so the balance after settling shows on the next
request. A 429 carries `Retry-After` in whole seconds, except for a request larger than the capacity, which
can never succeed. A 401 or 400 carries no limit headers. If the provider fails, the reservation is refunded
and the answer is 502.

Start the server through the app factory, with the variables set in your shell:

```bash
TOLLGATE_API_KEYS="<your keys>" TOLLGATE_TOKENS_PER_MINUTE=60000 \
  uvicorn --factory app.main:create_app
```

## Semantic cache

The cache is off until `TOLLGATE_CACHE_EMBEDDER=ollama` is set. It needs a running Ollama with an embedding model
pulled (`ollama pull all-minilm`), and these variables, described in the table under Configuration:
`TOLLGATE_CACHE_EMBEDDER`, `TOLLGATE_CACHE_EMBEDDER_MODEL` and `TOLLGATE_CACHE_SIMILARITY_THRESHOLD` are required
together; `TOLLGATE_CACHE_EMBEDDER_URL`, `TOLLGATE_CACHE_TTL_SECONDS` and `TOLLGATE_CACHE_MAX_ENTRIES` are optional.

```bash
TOLLGATE_API_KEYS="<your keys>" TOLLGATE_TOKENS_PER_MINUTE=60000 \
TOLLGATE_CACHE_EMBEDDER=ollama TOLLGATE_CACHE_EMBEDDER_MODEL=<model> \
TOLLGATE_CACHE_SIMILARITY_THRESHOLD=<threshold> \
  uvicorn --factory app.main:create_app
```

**Threshold: none is recommended.** The only semantic run recorded so far is `all-minilm` on 2026-11-23
([cache-eval.md](cache-eval.md)), and it found no threshold below 1 with zero wrong hits on the eval dataset: even
at 0.99, 4 of 40 different-meaning pairs hit, while only 2 of 40 same-meaning pairs do. So this guide gives no value
to copy. Any threshold you set is your own choice, and for `all-minilm` it will return wrong answers for questions
whose meaning differs by a negation, a number or the order of words. To get a recommendation for another model,
run `scripts/eval_cache.py --embedder ollama --model <model>` and read its last line. A threshold of `1` may never
hit: normalised vectors of identical text can score just under 1 (`0.9999999999999999`).

**The `x-tollgate-cache` header.** Every 200 carries it, and no other status does:

| Value | Meaning |
| --- | --- |
| `hit` | A stored answer was returned and no provider was called |
| `miss` | The request was looked up, nothing matched, and a provider answered (the answer may not be stored, see below) |
| `skip` | The request was not looked up: the cache is off, the last message is not from the `user`, or the embedder failed |

**What a hit costs.** The reservation is made first, as for any request, so a request that does not fit the bucket
gets a 429 even when its answer is cached. A hit then settles at 0 tokens and refunds the whole reservation. A
hit's `id` and `created` are new, `usage` describes the answer as it was first produced, and `x-tollgate-provider`
names the provider that produced it, not one that served this request. Every eligible request that passes the rate limit, hit or miss, makes
one embedding call to Ollama before any provider call, so a slow or stopped Ollama adds latency (up to the
10-second read timeout) or turns the request into a `skip`.

**Limits.**

- Entries are shared only by the same API key, the same `model` and the same other request fields and earlier
  messages. Only the last `user` message is compared by meaning.
- Only a 200 with one choice, finish reason `stop` and a JSON body of at most 65,536 bytes is stored.
- An entry lives `TOLLGATE_CACHE_TTL_SECONDS` (default 3600) from when it was stored; a hit does not extend it. At
  most `TOLLGATE_CACHE_MAX_ENTRIES` (default 1000) are kept; when it is full, an expired entry goes first, then the least recently used. Both defaults
  are chosen, not measured.
- Each process has its own cache, held in memory. Several workers or instances do not share entries, and a restart
  empties it.
- There is no way yet to bypass or purge the cache per request.

## Running with Docker Compose

`compose.yaml` runs the gateway and Redis on one host (ADR-0017). The gateway uses the Redis limiter, listens on
`127.0.0.1:8000` only, and routes to the mock provider through `deploy/routes.compose.json`, so the stack needs no
provider key and no outside network.

```bash
TOLLGATE_API_KEYS="<your keys>" TOLLGATE_METRICS_TOKEN="<a token of 32 or more characters>" \
  docker compose up --wait
curl localhost:8000/health   # {"status":"ok"}
docker compose down
```

- `TOLLGATE_API_KEYS` and `TOLLGATE_METRICS_TOKEN` are required, and Compose stops with a message when either is
  missing. `TOLLGATE_TOKENS_PER_MINUTE` is optional and defaults to 60000 here.
- Instead of putting them on the command line, write them in a `.env` file next to `compose.yaml`. `.env*` files
  are git-ignored and never enter the image (`.dockerignore`). Keep it that way: never commit one.
- `compose.yaml` passes only the variables above to the gateway, plus the fixed backend, Redis URL and routes
  file. To turn on the semantic cache or change the capacity, add the variable to the `gateway` service's
  `environment` first.
- The Ollama service is off by default. `docker compose --profile ollama up --wait` starts it, and
  `docker compose exec ollama ollama pull all-minilm` pulls a model into the `ollama-models` volume. The image is
  about 3.4 GB compressed. Nothing uses it until you change two things:
  - To route chat requests to it, copy `deploy/routes.compose.json` outside the repository, add an `ollama`
    provider with `"base_url": "http://ollama:11434"`, make it a target of `default` or of a route (a provider alone
    receives no traffic), and mount your copy over `/config/routes.json` in `compose.yaml` instead of the tracked file.
  - To use it for the semantic cache, add `TOLLGATE_CACHE_EMBEDDER=ollama`, `TOLLGATE_CACHE_EMBEDDER_MODEL`,
    `TOLLGATE_CACHE_SIMILARITY_THRESHOLD` and `TOLLGATE_CACHE_EMBEDDER_URL=http://ollama:11434` to the `gateway`
    service's `environment`. Without the URL, the gateway looks for Ollama on its own `localhost`, which is the
    container itself.
- CI's `container` job starts this stack and sends smoke requests. It has not been run on the owner's machine:
  [benchmarks.md](benchmarks.md) records it as not run.

### One process per container

The image runs one uvicorn worker per container (ADR-0017). Each process has its own metrics and its own
semantic cache, and a restart empties both. More than one gateway container works only with
`TOLLGATE_LIMITER_BACKEND=redis`, which keeps one bucket per key in Redis for all of them. With the `memory`
backend, N processes would each hold their own bucket and together allow N times the capacity.
The gateway does not serve TLS; on a host reachable from outside, put a reverse proxy in front of it.

## Metrics

`GET /metrics` exists only when `TOLLGATE_METRICS_TOKEN` is set; unset, it is a 404 like any unknown path. The
token must be at least 32 characters and differ from every API key. A scrape needs `Authorization: Bearer
<token>`, and an API key never opens it. Any other request gets a 401 with the code `invalid_metrics_token`.

```bash
curl -H "Authorization: Bearer $TOLLGATE_METRICS_TOKEN" localhost:8000/metrics
```

A Prometheus scrape job reads the token from a file, so it never sits in the configuration:

```yaml
scrape_configs:
  - job_name: tollgate
    metrics_path: /metrics
    authorization:
      type: Bearer
      credentials_file: /etc/prometheus/tollgate_token
    static_configs:
      - targets: ["tollgate:8000"]
```

That target resolves for a Prometheus on the same Compose network. The stack publishes the port on
`127.0.0.1:8000` only, so a Prometheus running on the host uses `localhost:8000`.

The text format is Prometheus 0.0.4. Every label value comes from a set fixed by the code or the route table,
never from a request. These are the metrics (ADR-0016):

| Metric | Labels | What it counts |
| --- | --- | --- |
| `tollgate_http_requests_total` | `path`, `status` | HTTP requests answered |
| `tollgate_http_request_duration_seconds` (histogram) | `path` | Request duration |
| `tollgate_chat_completions_total` | `provider`, `cache` | Chat completions answered with 200; `cache` is `hit`, `miss`, `skip` or `off` |
| `tollgate_provider_attempts_total` | `provider`, `outcome` | Provider calls; `outcome` is `ok`, `connection`, `timeout`, `rate_limited`, `upstream_status`, `bad_response`, `reply_too_large` or `error` |
| `tollgate_provider_attempt_duration_seconds` (histogram) | `provider` | Provider call duration |
| `tollgate_cache_lookups_total` | `result` | `hit`, `miss`, `not_eligible` or `embedder_failed` |
| `tollgate_cache_lookup_duration_seconds` (histogram) | none | Semantic cache lookup duration |
| `tollgate_tokens_reserved_total` | none | Tokens reserved from the rate limiter |
| `tollgate_tokens_charged_total` | none | Tokens charged after a call |
| `tollgate_settle_capped_total` | none | Settles where the charge was capped at the capacity |

`path` is `/v1/chat/completions`, `/health`, `/metrics` or `other` (every other path). Histogram buckets, in
seconds, are 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60 and `+Inf`; they were
chosen to span a mock call and a slow provider call, not measured.

**Series count.** With P providers in the route table and R distinct (`path`, `status`) pairs seen so far, one
process exports `97 + 30 P + R` series: each histogram series set has 18 series (16 buckets, `_sum`, `_count`),
and the fixed counts are 72 for the request duration (four paths), 18 for the cache lookup duration, 4 for the
lookups and 3 for the counters with no label (tokens reserved, tokens charged, settle capped), plus `18 P` for the attempt duration, `8 P` for the attempts and `4 P`
for the chat completions. R is at most four paths times the statuses the app can answer. With one provider and
no request yet, that is 127 series (R is 0).

## Logs

Run uvicorn with `--log-config deploy/logging.json` (the image does, with `--no-access-log`) and the gateway
writes one JSON object per line to stdout: one record per HTTP request, on the logger `tollgate.request`, plus
uvicorn's own messages.

| Field | Present | Meaning |
| --- | --- | --- |
| `time`, `level`, `logger` | always | UTC time in ISO 8601, level and logger name |
| `event`, `method`, `path`, `status`, `duration_seconds` | request records | `event` is `http_request`; `path` is as for the metrics |
| `provider`, `fallbacks`, `cache`, `skip_reason`, `reserved_tokens`, `charged_tokens`, `settle_capped`, `attempts` | chat requests that reached the route handler | The serving provider (or null), the cache result, the tokens, and one entry per provider tried with its outcome and duration |
| `message` | records from other loggers | uvicorn's and libraries' text |
| `exception_type` | records from other loggers that carry an exception | The exception's class name only |

**Never logged:** the prompt, the messages, the model, the API key or its digest, the caller, a header value, the
query string and the client address. For an exception the log carries the class name (`exception_type`) and
neither its message nor its traceback, because an exception text can echo provider internals or a prompt. To
debug an exception, run uvicorn without `--log-config`: its text format prints tracebacks. There is no request id,
so one request cannot be followed across systems. The record is written after the response is sent, so a crash
between the two loses it.

## Running the benchmarks

The load benchmarks are ADR-0018's. Every figure published in [benchmarks.md](benchmarks.md) comes from a run
recorded by `scripts/bench_load.py`, with its settings, in `docs/benchmarks/`. The generator sends requests at a
fixed rate and measures each one from the moment it was due, so a slow answer is not hidden by the requests that
waited behind it.

1. **The fake upstream** (scenarios A and B). In its own terminal:
   `python scripts/fake_upstream.py --delay-ms 50`. It listens on `127.0.0.1:8100` and answers one OpenAI-shaped
   chat completion after the delay. Nothing in the gateway can select it.
2. **The route files.** `deploy/bench/routes.fake-upstream.json` sends every request through the `openai`
   adapter to `http://127.0.0.1:8100` (scenario B). It reads the upstream key from the variable named in its
   `api_key_env`, `TOLLGATE_BENCH_UPSTREAM_KEY`; set it to any non-empty value, since the fake upstream checks
   nothing. `deploy/bench/routes.mock.json` uses the mock provider (scenario C). Scenario A has no gateway.
3. **The limiter settings.** A benchmark request ("ping", `max_tokens` 16) reserves 23 tokens and is charged 10
   (scenario B) or 4 (scenario C) after the call. The bucket must never refuse a request, so set
   `TOLLGATE_TOKENS_PER_MINUTE` and `TOLLGATE_CAPACITY_TOKENS` to at least twice the reserved tokens per minute
   at the rate you test: `2 * 23 * 60 * rate`, which is `2760 * rate` (110400 at 40 requests per second). Pass the
   same two numbers to `bench_load.py`, which records them.
4. **The gateway,** in a third terminal, with `TOLLGATE_LIMITER_BACKEND` set to `memory` or `redis` (and
   `TOLLGATE_REDIS_URL` for `redis`):
   ```bash
   TOLLGATE_API_KEYS="<a key>" TOLLGATE_BENCH_UPSTREAM_KEY="<anything>" \
   TOLLGATE_ROUTES_FILE=deploy/bench/routes.fake-upstream.json \
   TOLLGATE_TOKENS_PER_MINUTE=110400 TOLLGATE_CAPACITY_TOKENS=110400 \
   TOLLGATE_LIMITER_BACKEND=memory \
     uvicorn --factory app.main:create_app --host 127.0.0.1 --port 8001 --no-access-log
   ```
   With the `redis` backend the bucket lives in Redis under the API key, so a new key gives a run a full bucket. Reusing
   a key continues from whatever balance the last run left. (`FLUSHDB` also resets it, but only run that on a Redis
   dedicated to benchmarks.)
5. **The run.** The key goes in the environment and only its variable's name on the command line:
   ```bash
   BENCH_GATEWAY_KEY="<the same key>" python scripts/bench_load.py \
     --url http://127.0.0.1:8001 --api-key-env BENCH_GATEWAY_KEY --rate 40 \
     --duration-seconds 250 --warmup-seconds 10 --scenario B --limiter memory \
     --tokens-per-minute 110400 --capacity-tokens 110400 \
     --routes-file deploy/bench/routes.fake-upstream.json --upstream-delay-ms 50 \
     --server uvicorn --same-machine --output docs/benchmarks/B-memory-r40-rep1.json
   ```
   For scenario A, point `--url` at `http://127.0.0.1:8100` and leave out the key, limiter and route options. The
   exit code is 0 for a valid run, 3 for an invalid one and 1 when no report was written.
6. **The length.** A p99 is published only from at least 10,000 measured requests, so the rate times
   `--duration-seconds` must reach 10,000, and the measurement must last at least 60 seconds. Repeat each run 3
   times. The latency the gateway adds is B minus A at each percentile, per repeat.
7. **The rate.** Choose it below the knee. A short ramp of separate runs at rising rates shows where the achieved
   rate stops following the target and the number of requests in flight keeps growing.

**The lag check, and Windows.** A run is valid only if every response was a 200, no transport error occurred,
and the lag p99 (the time from a request's due moment to the moment the generator hands it over) is at most 10%
of the latency p99. On Windows the lag p99 of all 15 runs recorded for this repository was 14 to 16 ms
([benchmarks.md](benchmarks.md)). That is consistent with the default Windows timer tick of about 15.6 ms, though the
tick was not measured. Such a floor fails the check whenever the latency p99 is under about 150 ms. The report
then says it is invalid, and the run is not tuned until it passes. For a valid run, run the generator itself on Linux
or WSL2: moving only the server does not change the generator's timer, and the Compose stack has only the mock
provider with Redis, so it can serve scenario C and not B. A generator and a gateway on one machine also compete for
the CPU, so the report states whether they shared one.

## Regenerating the OpenAPI snapshot

`tests/contract/openapi.json` is the committed OpenAPI document (ADR-0005). `tests/test_openapi_snapshot.py`
compares it to the live app and fails on any difference. Tests and `scripts/check.py` never write it. Only this
command does, and only in a task whose card says the contract changes:

```bash
.venv/Scripts/python scripts/regenerate_openapi.py
```

Review the resulting diff before committing it.

## Updating pins

Pins are exact and updated by hand, one task at a time. Use throwaway venvs, not the project one:

1. In a new venv, install the runtime packages (`fastapi`, `pydantic`, `uvicorn`, `redis`, `httpx`) with
   `--only-binary=:all:`, run `pip freeze`, and write the result to `requirements.txt` under its comment lines.
2. In a second new venv, install the new `requirements.txt`, then `pytest`, `ruff`, `mypy` and
   `fakeredis[lua]`, run `pip freeze`, and put every line that is not in the runtime freeze into
   `requirements-dev.txt`, after `-r requirements.txt`.
3. If a dev tool forces a different version of a runtime package, regenerate the runtime pins at that version so
   both files agree. Run `pip check` in both venvs, then `python scripts/check.py`.

The lower bounds in `pyproject.toml` are not checked against the pins; keep them in step by hand.

## Enable the commit hooks

The hooks in `.githooks/` check that the commit author and committer match one email address, reject
attribution trailers in commit messages and block files that must not be committed. They need Node.js and are
off until you opt in. Run these once per clone:

```bash
git config core.hooksPath .githooks
git config authorguard.email "<your email>"
```

Use the email address you commit with. Without `authorguard.email`, the pre-commit hook refuses to commit. The
reasons are in ADR-0001 and ADR-0002 in [DECISIONS.md](DECISIONS.md).

## Where to go next

[ARCHITECTURE.md](ARCHITECTURE.md) explains the design, [TASKS.md](TASKS.md) lists the work and its status.
