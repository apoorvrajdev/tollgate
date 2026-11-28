# Demo: one recorded run

Real requests to a running gateway and the real responses, so you can see it work without running it. Every
output block below was captured from one run and pasted unedited, except where `...` marks an elision.

| | |
| --- | --- |
| Date | 2026-11-28, from 16:24 UTC to the last request record shown in step 6, at 16:33:52 UTC |
| Commit | `9577b4a` |
| Platform | Windows-11-10.0.26300-SP0, Git Bash; Docker 29.9.3 (server linux/amd64), Docker Compose v5.7.1 |
| How the gateway was served | The Compose stack (`compose.yaml`): the gateway image built from the `Dockerfile`, Redis limiter, `redis:7.4.12` |
| Route file | `deploy/routes.compose.json`: the mock provider as the `default` route, so no provider key and no outside network |
| Budget | `TOLLGATE_TOKENS_PER_MINUTE=60`, set low for this run so step 4 can reach the limit. The capacity is not set, so it equals the rate (60). The Compose default is 60000 |
| Not run | Step 7, the semantic cache, which needs a local Ollama |

The two API keys and the metrics token were made fresh for this run and kept in shell variables, so no value
appears in any command or output. To repeat the run, see [setup.md](setup.md#running-with-docker-compose).

## Start the stack

```bash
export DEMO_KEY=$(.venv/Scripts/python -c "import secrets; print(secrets.token_urlsafe(32))")
export DEMO_KEY_2=$(.venv/Scripts/python -c "import secrets; print(secrets.token_urlsafe(32))")
export TOLLGATE_METRICS_TOKEN=$(.venv/Scripts/python -c "import secrets; print(secrets.token_urlsafe(32))")
export TOLLGATE_API_KEYS="$DEMO_KEY,$DEMO_KEY_2"
export TOLLGATE_TOKENS_PER_MINUTE=60
docker compose down
docker compose up --build --wait
```

```text
...
[+] up 4/4
 ✔ Image tollgate-gateway       Built                                                                                 5.2s
 ✔ Network tollgate_default     Created                                                                               0.1s
 ✔ Container tollgate-redis-1   Healthy                                                                               7.0s
 ✔ Container tollgate-gateway-1 Healthy                                                                              11.4s
```

## 1. Health

```bash
curl -si http://127.0.0.1:8000/health
```

```text
HTTP/1.1 200 OK
date: Sat, 28 Nov 2026 16:28:43 GMT
server: uvicorn
content-length: 15
content-type: application/json

{"status":"ok"}
```

## 2. A chat completion through the mock

```bash
curl -si http://127.0.0.1:8000/v1/chat/completions -H "Authorization: Bearer $DEMO_KEY" -H "content-type: application/json" -d '{"model":"demo","messages":[{"role":"user","content":"Hello, Tollgate"}]}'
```

```text
HTTP/1.1 200 OK
date: Sat, 28 Nov 2026 16:29:50 GMT
server: uvicorn
content-length: 298
content-type: application/json
x-ratelimit-limit-tokens: 60
x-ratelimit-remaining-tokens: 50
x-ratelimit-reset-tokens: 10s
x-tollgate-provider: mock
x-tollgate-fallbacks: 0
x-tollgate-cache: skip

{"id":"chatcmpl-f83807c25df44effac414b5c6e40c13f","object":"chat.completion","created":1795883391,"model":"demo","choices":[{"index":0,"message":{"role":"assistant","content":"Mock reply: Hello, Tollgate"},"finish_reason":"stop"}],"usage":{"prompt_tokens":2,"completion_tokens":4,"total_tokens":6}}
```

The request reserved 10 tokens: the estimate is ceil(15 characters / 4) + 3 per message + 3 for the reply
(`app/limits/estimate.py`), so 50 of 60 remain. The headers show the
balance right after the reservation. The mock then reported 6 tokens of usage, and the 4 unused tokens were
refunded. `x-tollgate-provider` names the provider that answered, and `x-tollgate-fallbacks: 0` says no earlier
provider failed. `x-tollgate-cache: skip` means the cache was not consulted: it is off in this run.

## 3. No API key

```bash
curl -si http://127.0.0.1:8000/v1/chat/completions -H "content-type: application/json" -d '{"model":"demo","messages":[{"role":"user","content":"Hello, Tollgate"}]}'
```

```text
HTTP/1.1 401 Unauthorized
date: Sat, 28 Nov 2026 16:30:33 GMT
server: uvicorn
www-authenticate: Bearer
content-length: 162
content-type: application/json

{"error":{"message":"Missing or invalid API key. Send it as 'Authorization: Bearer <key>'.","type":"invalid_request_error","param":null,"code":"invalid_api_key"}}
```

## 4. A small bucket runs out: 429 with Retry-After

This step uses the second key, `DEMO_KEY_2`, so it starts with a full bucket of its own. On the Compose stack
each key's bucket lives in Redis. The same 25-word request is sent twice, back to back. The mock counts one token
per word and its reply repeats the prompt, so the first request is charged 52 tokens. The second needs a
reservation of 37 (ceil(124 characters / 4) + 6) while 8 remain.

```bash
BODY='{"model":"demo","messages":[{"role":"user","content":"word word word word word word word word word word word word word word word word word word word word word word word word word"}]}'
curl -si http://127.0.0.1:8000/v1/chat/completions -H "Authorization: Bearer $DEMO_KEY_2" -H "content-type: application/json" -d "$BODY"; echo; echo ---; curl -si http://127.0.0.1:8000/v1/chat/completions -H "Authorization: Bearer $DEMO_KEY_2" -H "content-type: application/json" -d "$BODY"
```

```text
HTTP/1.1 200 OK
date: Sat, 28 Nov 2026 16:32:37 GMT
server: uvicorn
content-length: 410
content-type: application/json
x-ratelimit-limit-tokens: 60
x-ratelimit-remaining-tokens: 23
x-ratelimit-reset-tokens: 37s
x-tollgate-provider: mock
x-tollgate-fallbacks: 0
x-tollgate-cache: skip

{"id":"chatcmpl-360a6bd927fa4449b09c28b7056fcf19","object":"chat.completion","created":1795883558,"model":"demo","choices":[{"index":0,"message":{"role":"assistant","content":"Mock reply: word word word word word word word word word word word word word word word word word word word word word word word word word"},"finish_reason":"stop"}],"usage":{"prompt_tokens":25,"completion_tokens":27,"total_tokens":52}}
---
HTTP/1.1 429 Too Many Requests
date: Sat, 28 Nov 2026 16:32:37 GMT
server: uvicorn
x-ratelimit-limit-tokens: 60
x-ratelimit-remaining-tokens: 8
x-ratelimit-reset-tokens: 52s
retry-after: 29
content-length: 154
content-type: application/json

{"error":{"message":"Rate limit reached for tokens: limit 60, requested 37. Try again in 29s.","type":"tokens","param":null,"code":"rate_limit_exceeded"}}
```

The provider was not called for the 429. The bucket refills at 1 token per second. `Retry-After: 29` is the time
until it holds the 37 tokens the request needs ((37 - 8) / 1), rounded up to whole seconds.
`x-ratelimit-reset-tokens: 52s` is the time until it is full again ((60 - 8) / 1).

## 5. Metrics after the run

```bash
curl -s -H "Authorization: Bearer $TOLLGATE_METRICS_TOKEN" http://127.0.0.1:8000/metrics | grep -E '^tollgate_(http_requests_total|chat_completions_total|provider_attempts_total|tokens_reserved_total|tokens_charged_total|settle_capped_total)'
```

The lines were chosen by that `grep`: every sample of the six counters it names. It leaves out the cache-lookup
counter (all zero, since the cache is off), the `# HELP` and `# TYPE` lines and the histograms (`docs/setup.md`
lists all the metrics).

```text
tollgate_http_requests_total{path="/v1/chat/completions",status="200"} 2
tollgate_http_requests_total{path="/v1/chat/completions",status="401"} 1
tollgate_http_requests_total{path="/v1/chat/completions",status="429"} 1
tollgate_http_requests_total{path="/health",status="200"} 100
tollgate_chat_completions_total{provider="mock",cache="hit"} 0
tollgate_chat_completions_total{provider="mock",cache="miss"} 0
tollgate_chat_completions_total{provider="mock",cache="skip"} 0
tollgate_chat_completions_total{provider="mock",cache="off"} 2
tollgate_provider_attempts_total{provider="mock",outcome="ok"} 2
tollgate_provider_attempts_total{provider="mock",outcome="connection"} 0
tollgate_provider_attempts_total{provider="mock",outcome="timeout"} 0
tollgate_provider_attempts_total{provider="mock",outcome="rate_limited"} 0
tollgate_provider_attempts_total{provider="mock",outcome="upstream_status"} 0
tollgate_provider_attempts_total{provider="mock",outcome="bad_response"} 0
tollgate_provider_attempts_total{provider="mock",outcome="reply_too_large"} 0
tollgate_provider_attempts_total{provider="mock",outcome="error"} 0
tollgate_tokens_reserved_total 47
tollgate_tokens_charged_total 58
tollgate_settle_capped_total 0
```

- Only one of the 100 `/health` requests is step 1. The others were not recorded one by one. The likely source is
  the Compose healthcheck, which calls `/health` inside the container every 5 seconds (`compose.yaml`).
- Tokens reserved: 10 + 37 = 47, for the two 200s. The 429's reservation was refused, so it is not counted.
  Tokens charged: 6 + 52 = 58.

## 6. The JSON log lines of those requests

```bash
docker compose logs --no-log-prefix gateway | grep '"logger": "tollgate.request"' | grep -v '"path": "/health"'
```

The second `grep` leaves out every `/health` record, which also drops step 1's record. Most of them are likely
the healthcheck's (see step 5).

```text
{"time": "2026-11-28T16:29:51.080Z", "level": "INFO", "logger": "tollgate.request", "event": "http_request", "method": "POST", "path": "/v1/chat/completions", "status": 200, "duration_seconds": 0.03328256400004648, "provider": "mock", "fallbacks": 0, "cache": null, "skip_reason": null, "reserved_tokens": 10, "charged_tokens": 6, "settle_capped": false, "attempts": [{"provider": "mock", "outcome": "ok", "duration_seconds": 7.782599993788608e-05}]}
{"time": "2026-11-28T16:30:34.354Z", "level": "INFO", "logger": "tollgate.request", "event": "http_request", "method": "POST", "path": "/v1/chat/completions", "status": 401, "duration_seconds": 0.00038770599996951205}
{"time": "2026-11-28T16:32:38.279Z", "level": "INFO", "logger": "tollgate.request", "event": "http_request", "method": "POST", "path": "/v1/chat/completions", "status": 200, "duration_seconds": 0.003623695999976917, "provider": "mock", "fallbacks": 0, "cache": null, "skip_reason": null, "reserved_tokens": 37, "charged_tokens": 52, "settle_capped": false, "attempts": [{"provider": "mock", "outcome": "ok", "duration_seconds": 5.582500000400614e-05}]}
{"time": "2026-11-28T16:32:38.334Z", "level": "INFO", "logger": "tollgate.request", "event": "http_request", "method": "POST", "path": "/v1/chat/completions", "status": 429, "duration_seconds": 0.0029845120000118186, "provider": null, "fallbacks": null, "cache": null, "skip_reason": null, "reserved_tokens": null, "charged_tokens": null, "settle_capped": null, "attempts": null}
{"time": "2026-11-28T16:33:52.489Z", "level": "INFO", "logger": "tollgate.request", "event": "http_request", "method": "GET", "path": "/metrics", "status": 200, "duration_seconds": 0.0028156799999123905}
```

- No prompt, model, key or client address appears. The log never records them (`docs/setup.md`, Logs).
- The durations are those of single requests on this machine, not a benchmark.
- With the cache off, the same fact has three spellings: `x-tollgate-cache: skip` in the response, `cache="off"`
  in the metrics and `"cache": null` in the log.

```bash
docker compose down
```

## 7. Semantic cache: not run

This step needs a local Ollama with an embedding model, and it was not run for this recording. To try it, see
[setup.md](setup.md#semantic-cache). No similarity threshold is recommended: for `all-minilm` on the eval dataset, none
below 1 gave zero wrong hits ([cache-eval.md](cache-eval.md)). A threshold you choose is your own.
