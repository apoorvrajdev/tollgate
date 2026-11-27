# Benchmarks

Every figure here comes from a JSON report in [benchmarks/](benchmarks/), made by `scripts/bench_load.py`,
`scripts/bench_cache.py scan` or `scripts/bench_cache.py embed` (ADR-0018). Figures are rounded for reading; the
reports hold the full values. They describe one Windows 11 machine with the load generator and the server on it,
not a production deployment.

**Read this first: none of the 15 load runs is valid.** ADR-0018 calls a run valid only if the lag p99 is at
most 10% of the latency p99. Every run here fails that one rule, and every report says so. They are published
as invalid runs and not tuned until they pass. Everything else about them is clean: 10,000 measured requests
each, all 200, no transport error, no warm-up error. The cache scan and the embedding latency have no validity
rule and are measured runs. The 19 ramp runs, in their own section, are diagnostic and all invalid as well,
three of them also for transport errors. The four runs in "Throughput ceiling investigation" are diagnostic and
invalid as well, under the lag rule only.

## Platform and settings

Recorded in every report, and the same in all 15 load runs except the limiter and route rows, which apply to B and C only (A has no gateway, and C's route file is not B's):

| Setting | Value |
| --- | --- |
| Platform | Windows-11-10.0.26300-SP0, 16 CPUs, Python 3.13.2 |
| Generator and server | the same machine, so they compete for the CPU (`same_machine`: true) |
| Server | bare uvicorn, one process, no Compose (`server`: uvicorn) |
| Git commit | `75384aaf05580d5344a9b4d85d9614aff6102d1c` |
| Rate | 40 requests per second, 250 s measured after 10 s of warm-up (10,000 measured requests) |
| Request | one fixed body of 79 bytes (`"ping"`, `max_tokens` 16), SHA-256 `6a4d2343e3df5c4e0bcd26e7ef31f09c15091659e673995321c939a9da807efd` |
| Fake upstream delay | 50 ms in A and B (chosen, not measured from a provider; recorded but unused in C, which has no upstream) |
| Limiter | tokens per minute and capacity both 110,400, which is 2 x 23 reserved tokens x 60 x 40, so no request is refused |
| Route table | B: `deploy/bench/routes.fake-upstream.json` (SHA-256 with LF `4cb1056bbcb0dbbb4135369269d5ac2bd93acac3e8750b78a9bb562180dd71b2`); C: `deploy/bench/routes.mock.json` |
| Cache | off in every run |
| Redis | a local Redis on `127.0.0.1:6379` for the Redis-limiter runs; neither its address nor its version is in the reports |

Not recorded in the reports, and stated from how the runs were started: one uvicorn process served the gateway,
and no cache variable was set (the cache was off).

## Why every run is invalid

The lag is the time from when a request was due to when the generator handed it to the HTTP client. In all 15
runs the lag p99 is between 14.0 and 16.1 ms, whatever the scenario and whatever the gateway does. That is what a
coarse timer would give: the default Windows timer tick is about 15.6 ms, and the lag p99 sits at that value. The
tick itself was not measured here, so this is an explanation that fits the figures, not a measured cause. The
rule compares that fixed floor of about 15 ms with the latency p99, so it passes only when the latency p99 is above about
150 ms. Scenario A, at about 82 ms (the median of its three p99s), fails it at 0.17 to 0.18, B at 0.11 to 0.17, and C, whose latency p99 is only
26 to 39 ms, at 0.41 to 0.62. ADR-0018 anticipated this on Windows (it says runs there "may fail the lag check more often") and says to report the run as invalid, not to tune it.
A valid run needs the generator itself on Linux or WSL2; the Compose stack could only serve the gateway for scenario C (not run, see below).

What the lag does to the latency figures is not known from these runs. The latency is measured from the due
time, so a late hand-over counts in it, and every figure below may include up to one timer tick of generator delay.

## Load runs, per repeat

Latency is from the due time to the end of the response. Peak is the largest number of requests in flight.

| Scenario | Repeat | p50 (ms) | p95 (ms) | p99 (ms) | max (ms) | Lag p50 (ms) | Lag p99 (ms) | Lag p99 / latency p99 | Peak in flight | Achieved rate | Valid | Report |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | 1 | 70.8 | 79.6 | 81.6 | 95.2 | 5.6 | 14.02 | 0.172 | 5 | 39.99/s | no (lag rule) | `A-r40-rep1.json` |
| A | 2 | 70.8 | 79.5 | 81.5 | 93.6 | 5.6 | 13.96 | 0.171 | 6 | 39.99/s | no (lag rule) | `A-r40-rep2.json` |
| A | 3 | 71.1 | 80.7 | 84.4 | 112.1 | 5.3 | 15.54 | 0.184 | 6 | 39.99/s | no (lag rule) | `A-r40-rep3.json` |
| B-memory | 1 | 73.3 | 84.1 | 94.5 | 149.3 | 4.6 | 15.85 | 0.168 | 6 | 39.99/s | no (lag rule) | `B-memory-r40-rep1.json` |
| B-memory | 2 | 74.5 | 94.1 | 111.3 | 177.1 | 4.5 | 15.68 | 0.141 | 7 | 39.99/s | no (lag rule) | `B-memory-r40-rep2.json` |
| B-memory | 3 | 74.7 | 93.2 | 101.1 | 132.8 | 4.4 | 15.56 | 0.154 | 6 | 39.99/s | no (lag rule) | `B-memory-r40-rep3.json` |
| B-redis | 1 | 76.0 | 99.8 | 120.1 | 449.8 | 4.6 | 15.61 | 0.130 | 17 | 39.99/s | no (lag rule) | `B-redis-r40-rep1.json` |
| B-redis | 2 | 81.4 | 102.8 | 145.8 | 316.7 | 4.5 | 15.75 | 0.108 | 12 | 39.99/s | no (lag rule) | `B-redis-r40-rep2.json` |
| B-redis | 3 | 85.3 | 111.2 | 144.8 | 255.5 | 4.7 | 15.87 | 0.110 | 10 | 39.99/s | no (lag rule) | `B-redis-r40-rep3.json` |
| C-memory | 1 | 15.0 | 22.5 | 25.8 | 51.2 | 8.2 | 15.99 | 0.620 | 3 | 40.00/s | no (lag rule) | `C-memory-r40-rep1.json` |
| C-memory | 2 | 17.1 | 24.8 | 29.1 | 117.2 | 8.1 | 15.91 | 0.548 | 4 | 40.00/s | no (lag rule) | `C-memory-r40-rep2.json` |
| C-memory | 3 | 15.6 | 23.5 | 27.0 | 52.4 | 8.2 | 15.97 | 0.592 | 3 | 40.00/s | no (lag rule) | `C-memory-r40-rep3.json` |
| C-redis | 1 | 17.6 | 25.3 | 33.3 | 60.6 | 8.3 | 16.05 | 0.482 | 4 | 40.00/s | no (lag rule) | `C-redis-r40-rep1.json` |
| C-redis | 2 | 20.0 | 28.4 | 39.4 | 81.5 | 7.9 | 15.97 | 0.405 | 6 | 40.00/s | no (lag rule) | `C-redis-r40-rep2.json` |
| C-redis | 3 | 17.6 | 25.3 | 33.1 | 55.8 | 8.3 | 16.09 | 0.487 | 7 | 40.00/s | no (lag rule) | `C-redis-r40-rep3.json` |

A is the fake upstream called directly. B is the gateway with the `openai` adapter to the fake upstream. C is the
gateway with the mock provider. Scenario C has no upstream hop to subtract, so it has no "minus A" figure.

## What the gateway adds: B minus A, per repeat

Repeat n of B minus repeat n of A, at each percentile, in ms. Never one blended figure. These come from invalid
runs (above), and with the upstream hop through the `openai` adapter this difference includes the adapter and its
HTTP client as well as the gateway's own work, so it is not the cost of the rate limiter alone.

| Limiter | Repeat | p50 | p95 | p99 | max |
| --- | --- | --- | --- | --- | --- |
| memory | 1 | +2.5 | +4.5 | +12.9 | +54.1 |
| memory | 2 | +3.7 | +14.6 | +29.8 | +83.5 |
| memory | 3 | +3.6 | +12.5 | +16.6 | +20.7 |
| redis | 1 | +5.1 | +20.2 | +38.5 | +354.5 |
| redis | 2 | +10.6 | +23.3 | +64.2 | +223.1 |
| redis | 3 | +14.2 | +30.5 | +60.4 | +143.3 |

In each of the three repeats the Redis run is above the memory run at p50, p95 and p99. The gap is
2.6 to 10.6 ms at p50, 8.7 to 18.0 ms at p95 and 25.6 to 43.8 ms at p99, across the repeats, so the direction is consistent and the size is not.
Three invalid runs per limiter, on one machine, do not fix its size, and a maximum is a single request.

## Cache scan

Time for one `lookup` that scans every entry of one partition of an `InMemorySemanticCache` and misses (the
similarity threshold is 2.0, which no entry reaches). A fixed query vector, no embedding call. Minimum and median of 20 repeats, seed 0.

| Entries | Dimensions | Vectors (bytes) | Min (ms) | Median (ms) | Max (ms) |
| --- | --- | --- | --- | --- | --- |
| 1,000 | 384 | 3,072,000 | 7.97 | 8.06 | 8.75 |
| 1,000 | 1,024 | 8,192,000 | 21.28 | 21.59 | 25.84 |
| 10,000 | 384 | 30,720,000 | 81.57 | 82.52 | 89.74 |
| 10,000 | 1,024 | 81,920,000 | 214.33 | 220.69 | 317.24 |
| 100,000 | 384 | 307,200,000 | 819.54 | 833.14 | 1051.46 |
| 100,000 | 1,024 | 819,200,000 | 2135.75 | 2296.65 | 2524.30 |

Settings: Python 3.13.2 on Windows-11-10.0.26300-SP0, 16 CPUs, commit `75384aaf05580d5344a9b4d85d9614aff6102d1c`. Report: `cache-scan.json`.
The minimum grows close to linearly with the entries and with the dimensions, as a full scan should. A lookup over
a full partition of the default `TOLLGATE_CACHE_MAX_ENTRIES` (1,000) takes 8.0 ms at 384 dimensions and 21.3 ms at 1,024;
at the setting's largest value (100,000 entries) it takes 820 ms and 2136 ms. These are single-process timings of a
Python loop on this machine, not a production figure.

## Embedding latency

100 sequential calls through `OllamaEmbedder` after 1 discarded call, model `all-minilm`, Ollama 0.40.18 on the same machine (`http://localhost:11434`, the default; the Compose profile pins 0.40.17, so these figures do not describe it), text 'How do I reset my password?' (27 bytes).

| Figure | Per call (ms) |
| --- | --- |
| min | 12.62 |
| median | 14.81 |
| max | 47.35 |

Report: `embed-all-minilm.json`. Calls 1 to 5 took 30.7 to 42.8 ms, against a median of 14.8 ms, so one discarded call did not fully warm the path; the maximum is call 100.
A first attempt, made while Ollama had not yet loaded the model, timed out and wrote no report; a plain request to
Ollama then took about 17 s. That is an observation made during this task, not in a report. The run above is the
second attempt. A request that reaches an Ollama that has not yet loaded the model can therefore become a cache `skip`
(the gateway's embedder has its own timeout). Every eligible request pays one such call before any provider call.

## Ramp (diagnostic)

Short runs at rising target rates, to find where each scenario stops following its target (ADR-0018). The
reports carry no timestamp; they were made during T-409 (its Log row is dated 2026-11-25). They are diagnostic:
every one is invalid, and no other figure on this page comes from them.

- **Lag p99 "withheld":** a report withholds a p99 from fewer than 10,000 measured requests ("too few samples").
- **Valid:** each report's own `invalid_reasons`, shortened. "lag" is `lag p99 above 10% of latency p99` and
  "transport" is `transport errors`. The validity check uses the p99s computed before withholding
  (`scripts/bench_load.py`), so a run can fail the lag rule while its lag p99 is withheld.

Settings shared by all 19, as recorded in each report:

- the platform, commit and request of the table above, with bare uvicorn serving B and C
- 20 s measured after 5 s of warm-up, except `ramp-A-r100-full.json` (100 s after 10 s)
- no connection cap
- a 50 ms fake upstream delay in A and B
- tokens per minute and capacity of 276,000 for B with the memory limiter and for every C run, and 1,656,000 for
  B with Redis. Every report's `errors.by_status` is empty, so no request was refused.
- routes: B used `deploy/bench/routes.fake-upstream.json` and C `deploy/bench/routes.mock.json`; their SHA-256
  with LF match the reports' `routes_sha256_lf`.

| Scenario | Limiter | Target | Achieved | Measured | Requests measured | Non-200 | Transport errors | Peak in flight | Lag p50 | Lag p99 | Valid | Report |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | - | 100/s | 99.68/s | 20 s | 2,000 | none | none | 13 | 4.7 ms | withheld | no (lag) | `ramp-A-r100.json` |
| A | - | 100/s | 99.95/s | 100 s | 10,000 | none | none | 13 | 4.8 ms | 15.6 ms | no (lag) | `ramp-A-r100-full.json` |
| A | - | 200/s | 66.03/s | 20 s | 4,000 | none | none | 94 | 23.7 s | withheld | no (lag) | `ramp-A-r200.json` |
| B | memory | 25/s | 24.96/s | 20 s | 500 | none | none | 5 | 5.1 ms | withheld | no (lag) | `ramp-B-memory-r25.json` |
| B | memory | 50/s | 49.88/s | 20 s | 1,000 | none | none | 15 | 5.3 ms | withheld | no (lag) | `ramp-B-memory-r50.json` |
| B | memory | 100/s | 48.95/s | 20 s | 2,000 | none | `ConnectError` 14 | 1,107 | 6.3 ms | withheld | no (transport; lag) | `ramp-B-memory-r100.json` |
| B | redis | 50/s | 49.85/s | 20 s | 1,000 | none | none | 12 | 4.5 ms | withheld | no (lag) | `ramp-B-redis-r50.json` |
| B | redis | 100/s | 50.61/s | 20 s | 2,000 | none | none | 638 | 1.9 s | withheld | no (lag) | `ramp-B-redis-r100.json` |
| B | redis | 100/s | 46.43/s | 20 s | 2,000 | none | `ConnectError` 111 | 1,067 | 6.7 ms | withheld | no (transport; lag) | `ramp-B-redis-r100-cpucheck.json` |
| B | redis | 200/s | 50.52/s | 20 s | 4,000 | none | `ReadError` 1 | 104 | 35.6 s | withheld | no (transport; lag) | `ramp-B-redis-r200.json` |
| B | redis | 300/s | 54.09/s | 20 s | 6,000 | none | none | 101 | 53.9 s | withheld | no (lag) | `ramp-B-redis-r300.json` |
| B | redis | 400/s | 53.93/s | 20 s | 8,000 | none | none | 105 | 75.9 s | withheld | no (lag) | `ramp-B-redis-r400.json` |
| B | redis | 600/s | 52.80/s | 20 s | 12,000 | none | none | 101 | 124.1 s | 204.7 s | no (lag) | `ramp-B-redis-r600.json` |
| C | memory | 25/s | 25.04/s | 20 s | 500 | none | none | 2 | 8.4 ms | withheld | no (lag) | `ramp-C-memory-r25.json` |
| C | memory | 50/s | 50.01/s | 20 s | 1,000 | none | none | 4 | 4.8 ms | withheld | no (lag) | `ramp-C-memory-r50.json` |
| C | memory | 100/s | 100.00/s | 20 s | 2,000 | none | none | 10 | 2.5 ms | withheld | no (lag) | `ramp-C-memory-r100.json` |
| C | redis | 25/s | 25.03/s | 20 s | 500 | none | none | 3 | 8.5 ms | withheld | no (lag) | `ramp-C-redis-r25.json` |
| C | redis | 50/s | 49.99/s | 20 s | 1,000 | none | none | 4 | 4.2 ms | withheld | no (lag) | `ramp-C-redis-r50.json` |
| C | redis | 100/s | 100.01/s | 20 s | 2,000 | none | none | 9 | 1.9 ms | withheld | no (lag) | `ramp-C-redis-r100.json` |

Read from the table:

- B followed its target at 25/s (memory only) and at 50/s with both limiters. At 100/s and above it achieved
  46.43 to 54.09/s, with peaks of 638 to 1,107 requests in flight at 100/s and 101 to 105 at 200/s and above.
- Three B runs had transport errors: `ConnectError` in two runs at 100/s (14 and 111), and one `ReadError` at
  200/s.
- A followed 100/s, in both the 20 s and the 100 s run, and achieved 66.03/s against 200/s.
- C followed 100/s with both limiters.

40/s was chosen for the published runs as below B's ceiling. Why B stops near 50/s is not known from these runs.
The memory-limiter case did not reproduce on a later commit, as shown in "Throughput ceiling investigation" below.
The rest is a Backlog item in [TASKS.md](TASKS.md).

Two reports carry a suffix. Their fields do not say why they were made; the purposes below are the owner's
account (2026-11-26):

- `ramp-A-r100-full.json` is the full-length run of A at 100/s: 100 s measured, so it has 10,000 measured
  requests and its p99s are published instead of withheld.
- `ramp-B-redis-r100-cpucheck.json` re-runs B with Redis at 100/s, with the same settings as
  `ramp-B-redis-r100.json`, while the CPU use of each process was sampled. The owner reports the gateway at 100%
  CPU and the generator at 44 to 67%. Those figures are not in the report, and how they were sampled (the tool,
  the interval, and whether 100% means one core) was not recorded, so they are an observation, not a measurement
  this page can reproduce. They do not by themselves establish the cause of B's ceiling. T-502 investigated it:
  see "Throughput ceiling investigation" below.

## Throughput ceiling investigation

**Conclusion: not reproduced on commit `e280d37`: B followed 100/s in run `ceiling-B-memory-r100.json`.**

The ramp runs above showed scenario B stopping near 50 requests/s against targets of 100/s and above. T-502
re-ran four of them on 2026-11-27 on `main` at `e280d37018b5fe4ff8a8fae985b66066f9b30eb3`. No `app/`,
`scripts/` or `deploy/` file changed between the ramp runs' commit `75384aa` and `e280d37`. B with the
memory limiter followed 100/s, so the investigation stopped after its first step, as the task allows. The
diagnostic profile and the two variations were not run, and no cause is claimed. The cause of the earlier
ceiling is unknown.

A run **follows** its target when it achieves at least 98% of the target rate, its peak in flight is at most 50,
and it has no transport error. All four runs are diagnostic and invalid under ADR-0018 for the same reason as every
other run on this page: the lag rule. Every report's `errors.by_status` is empty, so the limiter refused nothing.
The generator exited with code 3 (a report was written, and the run is invalid) in all four.

| Scenario | Limiter | Target | Achieved | Requests measured | Non-200 | Transport errors | Peak in flight | Latency p50 | Lag p50 | Follows | Valid | Report |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B | memory | 50/s | 49.86/s | 1,000 | none | none | 21 | 72.8 ms | 5.7 ms | yes | no (lag) | `ceiling-B-memory-r50.json` |
| B | memory | 100/s | 99.66/s | 2,000 | none | none | 17 | 75.3 ms | 3.2 ms | yes | no (lag) | `ceiling-B-memory-r100.json` |
| A | - | 100/s | 99.72/s | 2,000 | none | none | 12 | 71.1 ms | 4.7 ms | yes | no (lag) | `ceiling-A-r100.json` |
| C | memory | 100/s | 100.01/s | 2,000 | none | none | 11 | 9.7 ms | 2.6 ms | yes | no (lag) | `ceiling-C-memory-r100.json` |

### Settings

Each run repeats one ramp report's recorded settings. Every field of each report's `settings` matches its ramp
report's except `git_commit`:

- 20 s measured after 5 s of warm-up
- no connection cap
- the request of the tables above
- a 50 ms fake upstream delay in A and B
- tokens per minute and capacity of 276,000 for B and C
- B used `deploy/bench/routes.fake-upstream.json` and C used `deploy/bench/routes.mock.json`

At 100/s a run sends 2,500 requests, warm-up included. The gateway's `/metrics` shows 57,500 tokens reserved
(below), well inside the bucket of 276,000.

**What differs from the ramp runs.** Every gateway run here set `TOLLGATE_METRICS_TOKEN`, used `--log-config
deploy/logging.json`, and sent stdout and stderr to a file outside the repository. The ramp runs of 2026-11-25
recorded none of these, so how their gateway logged, and where, is not known. This is a difference between the two
sets of runs. It is not shown to be the cause: no run here changed one of these settings alone.

Other ramp runs are not covered. B with the Redis limiter at 100/s, and B at 200/s and above, were not re-run.

### Commands

These are run from the repository root in Git Bash. There were three shells: the fake upstream, the gateway and
the generator. Each first ran `source ~/tollgate-t502/env.sh`, and the generator's shell then ran
`source ~/tollgate-t502/t502.sh`. `env.sh` exports `BENCH_GATEWAY_KEY`, `TOLLGATE_API_KEYS`,
`TOLLGATE_METRICS_TOKEN`, `TOLLGATE_BENCH_UPSTREAM_KEY` and `OUT`. It holds throwaway local keys, and its values
are not published. `run` is a shell function. It samples CPU, scrapes `/metrics` (`curl` with the metrics token),
runs `.venv/Scripts/python scripts/bench_load.py` with the arguments that follow the label, then samples and
scrapes again.

The fake upstream ran unchanged through all four runs:

```bash
.venv/Scripts/python scripts/fake_upstream.py --delay-ms 50
```

The gateway for B. A fresh process was started for each B run, first for 50/s, then for 100/s:

```bash
TOLLGATE_ROUTES_FILE=deploy/bench/routes.fake-upstream.json TOLLGATE_TOKENS_PER_MINUTE=276000 TOLLGATE_CAPACITY_TOKENS=276000 TOLLGATE_LIMITER_BACKEND=memory \
  .venv/Scripts/python -m uvicorn --factory app.main:create_app --host 127.0.0.1 --port 8001 --no-access-log --log-config deploy/logging.json > ~/tollgate-t502/B-memory-r50.log 2>&1
TOLLGATE_ROUTES_FILE=deploy/bench/routes.fake-upstream.json TOLLGATE_TOKENS_PER_MINUTE=276000 TOLLGATE_CAPACITY_TOKENS=276000 TOLLGATE_LIMITER_BACKEND=memory \
  .venv/Scripts/python -m uvicorn --factory app.main:create_app --host 127.0.0.1 --port 8001 --no-access-log --log-config deploy/logging.json > ~/tollgate-t502/B-memory-r100.log 2>&1
```

The gateway for C:

```bash
TOLLGATE_ROUTES_FILE=deploy/bench/routes.mock.json TOLLGATE_TOKENS_PER_MINUTE=276000 TOLLGATE_CAPACITY_TOKENS=276000 TOLLGATE_LIMITER_BACKEND=memory \
  .venv/Scripts/python -m uvicorn --factory app.main:create_app --host 127.0.0.1 --port 8001 --no-access-log --log-config deploy/logging.json > ~/tollgate-t502/C-memory-r100.log 2>&1
```

The generator. No gateway was running during the A run:

```bash
run B-memory-r50 --url http://127.0.0.1:8001 --api-key-env BENCH_GATEWAY_KEY --rate 50 --duration-seconds 20 --warmup-seconds 5 --scenario B --limiter memory --tokens-per-minute 276000 --capacity-tokens 276000 --routes-file deploy/bench/routes.fake-upstream.json --upstream-delay-ms 50 --server uvicorn --same-machine --output docs/benchmarks/ceiling-B-memory-r50.json
run B-memory-r100 --url http://127.0.0.1:8001 --api-key-env BENCH_GATEWAY_KEY --rate 100 --duration-seconds 20 --warmup-seconds 5 --scenario B --limiter memory --tokens-per-minute 276000 --capacity-tokens 276000 --routes-file deploy/bench/routes.fake-upstream.json --upstream-delay-ms 50 --server uvicorn --same-machine --output docs/benchmarks/ceiling-B-memory-r100.json
run A-r100 --url http://127.0.0.1:8100 --rate 100 --duration-seconds 20 --warmup-seconds 5 --scenario A --upstream-delay-ms 50 --same-machine --output docs/benchmarks/ceiling-A-r100.json
run C-memory-r100 --url http://127.0.0.1:8001 --api-key-env BENCH_GATEWAY_KEY --rate 100 --duration-seconds 20 --warmup-seconds 5 --scenario C --limiter memory --tokens-per-minute 276000 --capacity-tokens 276000 --routes-file deploy/bench/routes.mock.json --server uvicorn --same-machine --output docs/benchmarks/ceiling-C-memory-r100.json
```

### Against the ramp runs

Generator CPU per request is the report's `generator_cpu_seconds / requests.total`, with warm-up included.

| Scenario | Limiter | Target | Ramp achieved | Ramp peak | Ramp generator CPU per request | Ceiling achieved | Ceiling peak | Ceiling generator CPU per request |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B | memory | 50/s | 49.88/s | 15 | 4.15 ms | 49.86/s | 21 | 5.30 ms |
| B | memory | 100/s | 48.95/s | 1,107 | 14.39 ms | 99.66/s | 17 | 4.25 ms |
| A | - | 100/s | 99.68/s | 13 | 4.58 ms | 99.72/s | 12 | 4.03 ms |
| C | memory | 100/s | 100.00/s | 10 | 4.77 ms | 100.01/s | 11 | 3.45 ms |

The B run at 100/s, which had stood out at 14.39 ms per request, now uses about as much generator CPU per request
as the A and C controls. This is an observation, not a cause.

### Gateway and upstream CPU

The method: `run` found each process by its listening port (`netstat -ano`, the gateway on 8001 and the fake upstream
on 8100). It read `TotalProcessorTime` with PowerShell `Get-Process` just before the generator started and just after
it ended. "Wall" is the time between the two samples' own timestamps. Per request divides by the report's
`requests.total`, warm-up included. A CPU per wall second of 1.00 is one core fully busy. The raw samples are
quoted below the table.

| Run | Process | CPU before (s) | CPU after (s) | CPU used (s) | Wall between samples (s) | CPU per wall second | Requests | CPU per request |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `B-memory-r50` | gateway | 1.047 | 11.656 | 10.609 | 28.4 | 0.37 | 1,250 | 8.49 ms |
| `B-memory-r50` | upstream | 0.563 | 1.547 | 0.984 | 28.1 | 0.03 | 1,250 | 0.79 ms |
| `B-memory-r100` | gateway | 1.125 | 17.641 | 16.516 | 27.4 | 0.60 | 2,500 | 6.61 ms |
| `B-memory-r100` | upstream | 1.688 | 3.250 | 1.562 | 27.7 | 0.06 | 2,500 | 0.62 ms |
| `A-r100` | gateway | not sampled | not sampled | - | - | - | - | - |
| `A-r100` | upstream | 3.297 | 4.938 | 1.641 | 26.7 | 0.06 | 2,500 | 0.66 ms |
| `C-memory-r100` | gateway | 0.781 | 6.328 | 5.547 | 27.0 | 0.21 | 2,500 | 2.22 ms |
| `C-memory-r100` | upstream | 4.969 | 5.031 | 0.062 | 27.0 | 0.00 | 2,500 | n/a (no requests reach it) |

The gateway was not sampled in A because A has no gateway, and nothing listened on port 8001. The fake upstream
stayed running during C but received no requests. In B at 100/s the gateway used 0.60 CPU seconds per wall second.
The owner's earlier account of the gateway at 100% CPU came from a different run (B with Redis at 100/s), with an
unrecorded method, so these figures neither confirm nor contradict it.

The raw samples (`cpu.txt`):

```text
B-memory-r50-before gateway pid=23172 2026-11-27T21:38:20.5548354+05:30 1.047
B-memory-r50-before upstream pid=10300 2026-11-27T21:38:21.3243553+05:30 0.563
B-memory-r50-after gateway pid=23172 2026-11-27T21:38:48.9310216+05:30 11.656
B-memory-r50-after upstream pid=10300 2026-11-27T21:38:49.4574100+05:30 1.547
B-memory-r100-before gateway pid=11648 2026-11-27T21:40:27.3620200+05:30 1.125
B-memory-r100-before upstream pid=10300 2026-11-27T21:40:27.8699193+05:30 1.688
B-memory-r100-after gateway pid=11648 2026-11-27T21:40:54.7399040+05:30 17.641
B-memory-r100-after upstream pid=10300 2026-11-27T21:40:55.5548407+05:30 3.250
A-r100-before gateway not-sampled (no listener on port 8001)
A-r100-before upstream pid=10300 2026-11-27T21:42:11.5220455+05:30 3.297
A-r100-after gateway not-sampled (no listener on port 8001)
A-r100-after upstream pid=10300 2026-11-27T21:42:38.1813470+05:30 4.938
C-memory-r100-before gateway pid=5940 2026-11-27T21:43:30.1386884+05:30 0.781
C-memory-r100-before upstream pid=10300 2026-11-27T21:43:30.6264890+05:30 4.969
C-memory-r100-after gateway pid=5940 2026-11-27T21:43:57.1169200+05:30 6.328
C-memory-r100-after upstream pid=10300 2026-11-27T21:43:57.5958051+05:30 5.031
```

### Gateway metrics

These are excerpts from the `/metrics` scrape taken after each gateway run. In every scrape before a run, each of
these counters was 0 or not yet present. The `http_requests_total` series for this path appears only after the
first request. Each run's counts include its warm-up.

```text
B-memory-r50-after
tollgate_http_requests_total{path="/v1/chat/completions",status="200"} 1250
tollgate_provider_attempts_total{provider="fake-upstream",outcome="ok"} 1250
tollgate_provider_attempts_total{provider="fake-upstream",outcome="connection"} 0
tollgate_tokens_reserved_total 28750
B-memory-r100-after
tollgate_http_requests_total{path="/v1/chat/completions",status="200"} 2500
tollgate_provider_attempts_total{provider="fake-upstream",outcome="ok"} 2500
tollgate_provider_attempts_total{provider="fake-upstream",outcome="connection"} 0
tollgate_tokens_reserved_total 57500
C-memory-r100-after
tollgate_http_requests_total{path="/v1/chat/completions",status="200"} 2500
tollgate_provider_attempts_total{provider="mock",outcome="ok"} 2500
tollgate_provider_attempts_total{provider="mock",outcome="connection"} 0
tollgate_tokens_reserved_total 57500
```

Every request reached the provider in one successful attempt, with no connection failure.

### Not done

The task's method ends at step 1 when B follows 100/s. For that reason the following were not done:

- the three time-location comparisons (the attempt duration against the request duration, the log median against
  the report p50, and CPU against the controls), beyond the CPU tables above
- the `cProfile` run
- the two variations

The request logs and the full `/metrics` scrapes stay outside the repository.

## Not run, or not published

| Item | Status | Reason |
| --- | --- | --- |
| A valid run of any scenario | none obtained on this machine | The Windows timer floor fails the lag rule (above). The generator would have to run on Linux or WSL2. |
| The Compose stack, on the owner's machine | not run | It routes only to the mock provider with the Redis limiter and does not contain the fake upstream, so it cannot run scenario B; the generator would still have run on Windows. CI's `container` job starts it. |

## Reproducing

See "Running the benchmarks" in [setup.md](setup.md): the fake upstream, the route files, the limiter settings that
leave room for the rate, and the lag check.
