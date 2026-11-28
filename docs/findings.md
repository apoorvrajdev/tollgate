# Findings

Three results this project measured. Each is told as question, method, result, meaning and
limits. This page adds no new measurement: every figure links to the page or report where it was recorded. The
load figures come from one Windows 11 machine with the load generator and the server on it, not from a production
deployment, and every load, ramp and ceiling run quoted here is invalid under ADR-0018, as its report says.

## Summary

- **No safe cache threshold:** With the `all-minilm` embedding model on an 80-pair dataset, no cosine threshold
  below 1.00 kept every different-meaning pair from hitting the cache. Pairs that change a negation, a number
  or a direction inside one topic score almost like rewordings. No threshold is recommended, and the cache is
  off by default.
- **The lag rule on Windows:** In all 15 load runs at 40 requests/s, every one invalid, the generator's lag p99
  was 14.0 to 16.1 ms whatever the scenario. That is consistent with the Windows timer tick of about 15.6 ms (an
  external figure, not measured here), and if that is the floor, the 10% rule could pass only when the latency
  p99 is above about 150 ms. Whether a generator on Linux or WSL2 gives a valid run is untested.
- **The throughput ceiling:** In the invalid ramp runs, scenario B (the gateway through its `openai` adapter to
  a fake OpenAI-compatible upstream, with the generator on the same machine) achieved 46.43 to 54.09 requests/s
  against targets of 100/s and above. The re-run gives this conclusion: not reproduced on commit `e280d37`: B
  followed 100/s in run `ceiling-B-memory-r100.json`, a run that is itself invalid under the lag rule. The cause
  of the earlier ceiling is unknown.

## Finding 1: no safe cache threshold

**Question.** The semantic cache answers a request from an earlier answer when the two prompts' embeddings are
close enough. Can one cosine threshold separate same-meaning pairs from different-meaning pairs?

**Dataset.** [`eval/cache_pairs.json`](../eval/cache_pairs.json) holds 80 hand-written English pairs
([The dataset](cache-eval.md#the-dataset)):

- 40 `same` pairs, rewordings with the same answer, 8 of each of 5 kinds (synonym, word order, register,
  question against request, concise against verbose).
- 40 `different` pairs, 8 in each of 5 categories: `unrelated_topic`, `negation`, `changed_number`,
  `swapped_order` and `changed_entity`. All but the first keep most words the same on purpose.
- SHA-256 with LF line endings: `73aa98d68f99b48578e9b1f0ca6f30a609ceaf00388ee6ffcc32825472bb9e1f`. A test
  pins this digest, so a changed dataset forces a new run.

**Method.** The eval harness runs each pair through its own new in-memory cache: it stores an answer for the
first prompt, then looks up the second, and records the similarity of a hit
([Method](cache-eval.md#method)). It reports the same-pair hit rate and the wrong-hit rate at every threshold
from 0.50 to 1.00 in steps of 0.01. The run was made on 2026-11-23 with Ollama 0.40.17 and
`all-minilm:latest` (ID `1b226e2802db`) ([all-minilm](cache-eval.md#all-minilm)).

**Result** (from the table in [all-minilm](cache-eval.md#all-minilm)):

- No threshold below 1.00 had zero wrong hits.
- At 0.99, 2 of 40 `same` pairs hit and 4 of 40 `different` pairs hit, all four `swapped_order`. At 0.98 the
  counts are 4 and 4. At 1.00 no pair of either kind hits.
- All 8 `negation` pairs hit through 0.88. All 8 `changed_number` pairs hit through 0.79, and all 8
  `swapped_order` pairs through 0.78.
- `unrelated_topic` pairs never hit at any threshold from 0.50. The model separates topics, but not a change of
  meaning inside one topic.
- From 0.94 up, the wrong hits are at least as many as the same hits, so raising the threshold removes correct
  hits as fast as wrong ones.

**What follows.** The harness's rule recommends the lowest threshold below 1.00 with zero wrong hits, and on this
run there is none, so no threshold is recommended for `all-minilm`, and the setup guide gives none
([Semantic cache](setup.md#semantic-cache)). Two earlier design decisions fit this result, but the run did not
cause them. [ADR-0014](DECISIONS.md#adr-0014) gives the threshold no default and requires it whenever the cache is
on, and says to recommend against the cache with a model that has no such threshold.
[ADR-0015](DECISIONS.md#adr-0015) leaves the cache off unless `TOLLGATE_CACHE_EMBEDDER` is set.

**Limits** ([Limits](cache-eval.md#limits)):

- One model. `bge-m3` was not run and has no recorded result. The finding applies to `all-minilm` on this
  dataset only.
- 80 hand-written pairs cover a few kinds of rewording and near miss, not real traffic.
- A threshold would be chosen on the same data it is measured on, so its true wrong-hit rate could be higher.
- Even zero wrong hits would not be a guarantee: 0 out of 40 `different` pairs gives a one-sided 95% upper
  bound of about 7% on the true wrong-hit rate, and about 31% for one category of 8 (Clopper-Pearson).

## Finding 2: the lag rule on Windows

**What the rule guards against.** The load generator sends at a fixed rate and measures each request's latency
from the moment it was due, so a request the generator hands over late counts its delay as latency. The lag is
that delay: from the due time to the hand-over to the HTTP client. [ADR-0018](DECISIONS.md#adr-0018) calls a
run valid only if the lag p99 is at most 10% of the latency p99, so that the latency figures describe the
server and not a late generator. The 10% is chosen, not measured, and the check catches a saturated generator
but cannot prove there is none.

**What was observed** ([Why every run is invalid](benchmarks.md#why-every-run-is-invalid) and
[Load runs, per repeat](benchmarks.md#load-runs-per-repeat)):

- The 15 invalid load runs (scenarios A, B and C, B and C each with the memory and the Redis limiter, 3 repeats
  each) ran at 40 requests/s with 10,000 measured requests each. Every one is invalid under the lag rule and
  under no other condition: all responses were 200 and there was no transport error.
- In those 15 invalid runs the lag p99 was 14.0 to 16.1 ms, whatever the scenario and whatever the gateway did.
- That is consistent with the default Windows timer tick of about 15.6 ms. The tick is an external figure and
  was not measured here, so this is an explanation that fits the figures, not a measured cause.
- If the tick is the floor, the rule can pass only with a latency p99 above about 150 ms. In these invalid runs
  the ratio of lag p99 to latency p99 was 0.17 to 0.18 for A, 0.11 to 0.17 for B, and 0.41 to 0.62 for C,
  whose latency p99 is the lowest.
- ADR-0018 anticipated this: it says runs on Windows may fail the lag check more often, and that a run which
  fails it is reported as invalid, not tuned until it passes.

**The ramp runs are a different matter** ([Ramp (diagnostic)](benchmarks.md#ramp-diagnostic)). All 19 ramp
runs are invalid under the lag rule, including those that kept up with their target. Some runs that fell
behind their target show lags of seconds, not of one timer tick:

- Six had a lag p50 of 1.9 s to 124.1 s, all invalid: `ramp-B-redis-r100.json` (1.9 s),
  `ramp-A-r200.json` (23.7 s), `ramp-B-redis-r200.json` (35.6 s), `ramp-B-redis-r300.json` (53.9 s),
  `ramp-B-redis-r400.json` (75.9 s) and `ramp-B-redis-r600.json` (124.1 s).
- Two others fell behind with a lag p50 in milliseconds, but had `ConnectError` transport errors and are
  invalid for those as well: `ramp-B-memory-r100.json` (6.3 ms, 14 errors) and
  `ramp-B-redis-r100-cpucheck.json` (6.7 ms, 111 errors).

The lags of seconds are far larger than one timer tick, and why these eight runs fell behind is not known from
these runs. Finding 3 covers scenario B's ceiling.

**What it means for the published figures.**

- All 15 load runs are published as invalid, with their figures, and none was tuned until it passed.
- What the lag does to the latency figures is not known from these runs. Every latency figure may include up to
  one timer tick of generator delay.
- The latency the gateway adds is reported as B minus A per repeat, from these invalid runs, and it includes the
  `openai` adapter and its HTTP client as well as the gateway's own work
  ([B minus A](benchmarks.md#what-the-gateway-adds-b-minus-a-per-repeat)).
- It is untested whether a generator on Linux or WSL2 gives a valid run. No such run has been made
  ([Not run, or not published](benchmarks.md#not-run-or-not-published)).

## Finding 3: the throughput ceiling

**Not reproduced on commit `e280d37`: B followed 100/s in run `ceiling-B-memory-r100.json`**, a diagnostic run
that, like the three others made with it, is invalid under ADR-0018's lag rule.

**Question.** Scenario B is the gateway calling a fake OpenAI-compatible upstream through the real `openai`
adapter. In the invalid ramp runs, with the upstream set to answer after 50 ms, it stopped near 50 requests/s
([Ramp (diagnostic)](benchmarks.md#ramp-diagnostic)):

- B kept up at 25/s (memory limiter only) and at 50/s with both limiters, in invalid runs.
- At 100/s and above it achieved 46.43 to 54.09/s, in invalid runs, with peaks of 638 to 1,107 requests in
  flight at 100/s.
- Scenario C, the gateway with the in-process mock provider, kept up at 100/s with both limiters, and A, the fake
  upstream called directly, at 100/s, both in invalid runs.
- The published load runs, all invalid, used 40/s, chosen as below B's ceiling.

Why did B stop near 50/s in those invalid runs?

**Method** ([Throughput ceiling investigation](benchmarks.md#throughput-ceiling-investigation)). On 2026-11-27
four ramp runs were repeated with their recorded settings on commit `e280d37`, as diagnostic runs that are all
invalid under the lag rule: B with the memory limiter at 50/s and 100/s, and the A and C controls at 100/s. No
`app/`, `scripts/` or `deploy/` file had changed since the ramp runs' commit `75384aa`. A run **follows** its
target when it achieves at least 98% of the target rate, has at most 50 requests in flight at its peak, and has
no transport error. The method stopped after this first step if B followed 100/s.

**Result.** All four runs followed their targets, and all four are invalid under the lag rule only:

- B at 100/s achieved 99.66/s with a peak of 17 in flight and no transport error, in the invalid run
  [`ceiling-B-memory-r100.json`](benchmarks/ceiling-B-memory-r100.json). Every request reached the upstream in one
  successful attempt.
- B at 50/s achieved 49.86/s ([`ceiling-B-memory-r50.json`](benchmarks/ceiling-B-memory-r50.json)), A at 100/s
  99.72/s ([`ceiling-A-r100.json`](benchmarks/ceiling-A-r100.json)) and C at 100/s 100.01/s
  ([`ceiling-C-memory-r100.json`](benchmarks/ceiling-C-memory-r100.json)), all in invalid runs.
- The generator's CPU time per request in B at 100/s was 14.39 ms in the invalid ramp run and 4.25 ms in the
  invalid re-run. In the re-run it was about as much as in the A and C controls. This is an observation, not a
  cause.

**What follows.** The method allows three conclusions: a cause shown by a run, a suspected cause, or "not
reproduced". This is the third. The profile and the two variations the method allowed were not run, and no cause
is claimed. The gateway runs in the re-run set the metrics token and a JSON log configuration with output to a
file, which the ramp runs did not record. That is a difference between the two sets of runs, not a shown cause.

**Limits.**

- Only the memory-limiter case was re-run. B with the Redis limiter at 100/s, and B at 200/s and above, were not
  re-run, so those invalid ramp results stand unexplained.
- Each invalid re-run measured 20 s, with 2,000 measured requests at 100/s, too few to publish a p99.
- One machine, with the generator on it, and every run invalid.

## How the figures were produced

- **Evidence first** ([ADR-0005](DECISIONS.md#adr-0005)). Any figure in a README, doc or pull request must come
  from a recorded run with its settings. This page quotes figures recorded in [cache-eval.md](cache-eval.md),
  [benchmarks.md](benchmarks.md) and the JSON reports under [benchmarks/](benchmarks/).
- **Load runs** ([ADR-0018](DECISIONS.md#adr-0018)):
  - An open loop: request i is due at the start plus i divided by the rate, latency is measured from the due
    time, and a slow answer cannot hold back the requests behind it.
  - A run is valid only if every response is a 200, there is no transport error, and the lag p99 is at most 10%
    of the latency p99. A p99 is published only from at least 10,000 measured requests, and a run with fewer is
    still checked for validity.
  - Each report records its settings, including the git commit, the platform and whether the generator shares a
    machine with the server. The reports are committed under `docs/benchmarks/`.
  - The fake upstream's 50 ms delay, used in every A and B run (all invalid), is chosen, not measured from a
    real provider.
- **The cache eval** ([cache-eval.md](cache-eval.md)):
  - Each pair goes through the real cache code, not a separate similarity calculation.
  - If any lookup cannot embed its text, the run stops with an error and prints no report, so an embedder
    outage can never look like zero wrong hits.
  - The dataset is named by its SHA-256, and a test pins the digest.

## What I would do next

From the [Backlog](TASKS.md#backlog):

- **Gateway throughput with an `openai` provider.** Re-run the invalid ramp cases T-502 did not cover: B with
  the Redis limiter at 100/s and B at 200/s and above, and the same runs with the generator on Linux or WSL2. A
  Linux or WSL2 generator would also show whether the lag rule can pass there (Finding 2).
- **More embedders.** Add a prompt-prefix setting for models that need one, such as `nomic-embed-text` and
  `mxbai-embed-large`, and an embedder for the OpenAI-compatible `/v1/embeddings`. Models that need a prefix
  are not supported today ([ADR-0015](DECISIONS.md#adr-0015)), so the eval cannot yet run them with the prefixes
  they need.
  Whether any of them gives a safe threshold is unknown.
