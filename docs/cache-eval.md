# Cache eval

The semantic cache answers a request from an earlier answer when the two prompts are close enough. How close is
`TOLLGATE_CACHE_SIMILARITY_THRESHOLD`, and ADR-0014 says a threshold is never chosen without a measurement. This
harness is that measurement: it runs labelled prompt pairs through the real cache and reports, at every
threshold from 0.50 to 1.00, how often a same-meaning pair hits and how often a different-meaning pair hits.

## The dataset

`eval/cache_pairs.json` holds 80 pairs of English prompts written for this project. Each pair has an `id`, a
`label` (`same` or `different`), a `category`, and the two texts `first` and `second`.

- 40 `same` pairs are rewordings with the same answer, 8 of each kind: `synonym`, `word_order`, `register`
  (casual against formal), `question_vs_request` and `concise_vs_verbose`. Their ids are `same-01` to `same-40`.
- 40 `different` pairs need a different answer, 8 in each category, with ids `<category>-01` to `-08`:
  - `unrelated_topic`: different subjects, as a floor.
  - `negation`: "Which foods are good for dogs?" against "Which foods are not good for dogs?".
  - `changed_number`: "$250" against "$2500", "4 people" against "24 people".
  - `swapped_order`: Celsius to Fahrenheit against Fahrenheit to Celsius, upload against download.
  - `changed_entity`: Austria against Australia, koalas against pandas.

The near-miss categories keep most words the same on purpose: they are the pairs a lexical or semantic match
is most likely to confuse. Reports name the dataset by its SHA-256, computed with LF line endings so that a
Windows checkout (CRLF) and CI (LF) give the same digest. Changing any pair changes the digest, so a recorded
run must be repeated after the dataset changes; a test pins the digest recorded below to make that
happen.

## Method

`app/cache/evaluation.py` runs each pair through its own new `InMemorySemanticCache`, with a threshold of 0.5,
one entry, a fixed caller and a fixed model. It looks up `first` (a miss in the empty cache), stores an
answer for it, then looks up `second`, each as a one-message request.

- A hit reports its similarity. Under the cache's own rule (a hit needs a similarity at least equal to the
  threshold), the pair hits at every threshold up to that similarity. A miss at 0.5 misses at every threshold.
  This is exact, not an approximation.
- The thresholds are `i / 100` for `i` from 50 to 100, the same doubles that parsing the setting gives. Adding
  0.01 in a loop would not give them: `0.5 + 7 * 0.01` is `0.5700000000000001`, not `0.57`.
- For each threshold the report gives the hit rate on `same` pairs, the wrong-hit rate on `different` pairs,
  and the wrong hits per category.
- The recommended threshold is the lowest one below 1.00 with no wrong hit. If there is none, the report says
  not to use the cache with that embedder. 1.00 is excluded because two identical texts can score
  `0.9999999999999999` after normalisation, so a threshold of 1 may never hit.
- If any lookup is a `skip` (the embedder failed), the run stops with an error naming the pair and the
  failure kind, and prints no report. An embedder outage can never look like zero wrong hits.

## Limits

- Zero wrong hits on the dataset is not a guarantee. 0 wrong hits out of 40 `different` pairs gives a one-sided
  95% upper bound of about 7% on the true wrong-hit rate (Clopper-Pearson, 1 - 0.05^(1/40)), and about 31% for
  one category of 8 (ADR-0014).
- The threshold is chosen on the same data it is measured on, so the true rate can be higher still.
- 80 hand-written pairs cover a few kinds of rewording and near miss, not real traffic.
- The hashing embedder measures shared character trigrams: lexical overlap, not meaning. Its numbers are a
  baseline for the harness, never a recommendation for production.

## How to run

```
.venv/Scripts/python scripts/eval_cache.py --embedder hashing
.venv/Scripts/python scripts/eval_cache.py --embedder ollama --model all-minilm
.venv/Scripts/python scripts/eval_cache.py --embedder ollama --model all-minilm --url http://localhost:11434 --output report.json
```

- `--embedder` is `hashing` (the default, no network) or `ollama`.
- `--model` is required with `ollama`; `--url` defaults to `http://localhost:11434`. Both are refused with
  `hashing`.
- `--output` also writes the report as JSON.
- With Ollama the script calls `GET /api/version` once and `POST /api/embed` for each of the 160 texts, using
  the gateway's own embedder client (5-second connect timeout, 10 seconds for the rest).
- The URL is never printed: it can hold credentials, so every failure prints one fixed line, and an
  unrecognized argument is not repeated. `--url` set but blank is refused.
- Exit codes: 0 on success; 1 when the run fails, with nothing printed to standard output and no JSON written;
  2 for bad usage.

The test suite runs the whole dataset with the hashing embedder on every CI run, with no network.

## Hashing baseline (lexical, not semantic)

Recorded on 2026-11-22 on Windows 11 with Python 3.13.2, from the harness in the T-304 change, with:

```
.venv/Scripts/python scripts/eval_cache.py --embedder hashing
```

The output, unedited apart from its heading level:

#### Cache eval report

- Date (UTC): 2026-11-22
- Embedder: hashing:v1 (lexical baseline, not semantic)
- Dataset SHA-256 (LF line endings): 73aa98d68f99b48578e9b1f0ca6f30a609ceaf00388ee6ffcc32825472bb9e1f
- Pairs: 40 same, 40 different
- Ollama version: n/a

| Threshold | Same hits | Wrong hits | unrelated_topic | negation | changed_number | swapped_order | changed_entity |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.50 | 25/40 (62.5%) | 32/40 (80.0%) | 0 | 8 | 8 | 8 | 8 |
| 0.51 | 24/40 (60.0%) | 32/40 (80.0%) | 0 | 8 | 8 | 8 | 8 |
| 0.52 | 24/40 (60.0%) | 32/40 (80.0%) | 0 | 8 | 8 | 8 | 8 |
| 0.53 | 24/40 (60.0%) | 32/40 (80.0%) | 0 | 8 | 8 | 8 | 8 |
| 0.54 | 23/40 (57.5%) | 32/40 (80.0%) | 0 | 8 | 8 | 8 | 8 |
| 0.55 | 23/40 (57.5%) | 32/40 (80.0%) | 0 | 8 | 8 | 8 | 8 |
| 0.56 | 22/40 (55.0%) | 32/40 (80.0%) | 0 | 8 | 8 | 8 | 8 |
| 0.57 | 22/40 (55.0%) | 32/40 (80.0%) | 0 | 8 | 8 | 8 | 8 |
| 0.58 | 20/40 (50.0%) | 32/40 (80.0%) | 0 | 8 | 8 | 8 | 8 |
| 0.59 | 19/40 (47.5%) | 32/40 (80.0%) | 0 | 8 | 8 | 8 | 8 |
| 0.60 | 16/40 (40.0%) | 32/40 (80.0%) | 0 | 8 | 8 | 8 | 8 |
| 0.61 | 16/40 (40.0%) | 32/40 (80.0%) | 0 | 8 | 8 | 8 | 8 |
| 0.62 | 15/40 (37.5%) | 31/40 (77.5%) | 0 | 8 | 8 | 8 | 7 |
| 0.63 | 13/40 (32.5%) | 31/40 (77.5%) | 0 | 8 | 8 | 8 | 7 |
| 0.64 | 13/40 (32.5%) | 31/40 (77.5%) | 0 | 8 | 8 | 8 | 7 |
| 0.65 | 12/40 (30.0%) | 31/40 (77.5%) | 0 | 8 | 8 | 8 | 7 |
| 0.66 | 12/40 (30.0%) | 31/40 (77.5%) | 0 | 8 | 8 | 8 | 7 |
| 0.67 | 12/40 (30.0%) | 31/40 (77.5%) | 0 | 8 | 8 | 8 | 7 |
| 0.68 | 12/40 (30.0%) | 30/40 (75.0%) | 0 | 8 | 8 | 8 | 6 |
| 0.69 | 12/40 (30.0%) | 29/40 (72.5%) | 0 | 8 | 8 | 8 | 5 |
| 0.70 | 11/40 (27.5%) | 29/40 (72.5%) | 0 | 8 | 8 | 8 | 5 |
| 0.71 | 11/40 (27.5%) | 29/40 (72.5%) | 0 | 8 | 8 | 8 | 5 |
| 0.72 | 10/40 (25.0%) | 28/40 (70.0%) | 0 | 8 | 8 | 8 | 4 |
| 0.73 | 10/40 (25.0%) | 28/40 (70.0%) | 0 | 8 | 8 | 8 | 4 |
| 0.74 | 9/40 (22.5%) | 28/40 (70.0%) | 0 | 8 | 8 | 8 | 4 |
| 0.75 | 9/40 (22.5%) | 28/40 (70.0%) | 0 | 8 | 8 | 8 | 4 |
| 0.76 | 9/40 (22.5%) | 27/40 (67.5%) | 0 | 8 | 8 | 7 | 4 |
| 0.77 | 9/40 (22.5%) | 27/40 (67.5%) | 0 | 8 | 8 | 7 | 4 |
| 0.78 | 9/40 (22.5%) | 27/40 (67.5%) | 0 | 8 | 8 | 7 | 4 |
| 0.79 | 9/40 (22.5%) | 27/40 (67.5%) | 0 | 8 | 8 | 7 | 4 |
| 0.80 | 9/40 (22.5%) | 26/40 (65.0%) | 0 | 8 | 8 | 6 | 4 |
| 0.81 | 9/40 (22.5%) | 26/40 (65.0%) | 0 | 8 | 8 | 6 | 4 |
| 0.82 | 6/40 (15.0%) | 24/40 (60.0%) | 0 | 8 | 8 | 6 | 2 |
| 0.83 | 4/40 (10.0%) | 22/40 (55.0%) | 0 | 8 | 8 | 5 | 1 |
| 0.84 | 4/40 (10.0%) | 22/40 (55.0%) | 0 | 8 | 8 | 5 | 1 |
| 0.85 | 4/40 (10.0%) | 22/40 (55.0%) | 0 | 8 | 8 | 5 | 1 |
| 0.86 | 4/40 (10.0%) | 22/40 (55.0%) | 0 | 8 | 8 | 5 | 1 |
| 0.87 | 4/40 (10.0%) | 22/40 (55.0%) | 0 | 8 | 8 | 5 | 1 |
| 0.88 | 4/40 (10.0%) | 19/40 (47.5%) | 0 | 7 | 8 | 3 | 1 |
| 0.89 | 3/40 (7.5%) | 17/40 (42.5%) | 0 | 6 | 8 | 2 | 1 |
| 0.90 | 2/40 (5.0%) | 15/40 (37.5%) | 0 | 6 | 7 | 1 | 1 |
| 0.91 | 1/40 (2.5%) | 13/40 (32.5%) | 0 | 5 | 7 | 1 | 0 |
| 0.92 | 0/40 (0.0%) | 9/40 (22.5%) | 0 | 3 | 6 | 0 | 0 |
| 0.93 | 0/40 (0.0%) | 5/40 (12.5%) | 0 | 1 | 4 | 0 | 0 |
| 0.94 | 0/40 (0.0%) | 5/40 (12.5%) | 0 | 1 | 4 | 0 | 0 |
| 0.95 | 0/40 (0.0%) | 4/40 (10.0%) | 0 | 0 | 4 | 0 | 0 |
| 0.96 | 0/40 (0.0%) | 3/40 (7.5%) | 0 | 0 | 3 | 0 | 0 |
| 0.97 | 0/40 (0.0%) | 1/40 (2.5%) | 0 | 0 | 1 | 0 | 0 |
| 0.98 | 0/40 (0.0%) | 0/40 (0.0%) | 0 | 0 | 0 | 0 | 0 |
| 0.99 | 0/40 (0.0%) | 0/40 (0.0%) | 0 | 0 | 0 | 0 | 0 |
| 1.00 | 0/40 (0.0%) | 0/40 (0.0%) | 0 | 0 | 0 | 0 | 0 |

Recommended threshold: 0.98, the lowest below 1.00 with zero wrong hits on this dataset. That is not a guarantee of zero wrong hits.

What this shows, about the hashing embedder only:

- It cannot tell near misses from rewordings. At 0.50 every `negation`, `changed_number`, `swapped_order` and
  `changed_entity` pair hits, because those pairs share most of their characters.
- `changed_number` pairs are the last to stop hitting: their only difference is a digit or two.
- The lowest threshold below 1.00 with zero wrong hits is 0.98 (0.99 has none either), and at 0.98 no
  `same` pair hits. A cache configured from this baseline would never be useful: the expected result for a
  lexical baseline, and the reason the threshold must come from a semantic embedder's run.

## Ollama runs

Not yet recorded. The recommended threshold for a model comes from a run with `--embedder ollama` against that
model, recorded here with its settings (T-307).
