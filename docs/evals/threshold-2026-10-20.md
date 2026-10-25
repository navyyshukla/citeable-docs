# Evidence threshold: what the dial does (2026-10-20)

Source: `docs/evals/retrieval-2026-10-20b.json` (28 dev questions: 19 answerable, 9 unanswerable;
paraphrased, so small and partly tuned). Made with `python -m app.cli calibrate`; no model call.
"wrong%" is a proxy: answered but no top-5 piece matches the gold page (or the question is
unanswerable). The real check is whether the final answer cites a gold piece.

## Finding: no score separates the two groups well

| Score | Answerable (19) range | Unanswerable (9) range | Overlap |
|---|---|---|---|
| hybrid fusion (RRF) | 0.0294 to 0.0328 | 0.0164 to 0.0328 | 5 of 9 unanswerable score 0.0323 or more |
| meaning (cosine) | 0.64 to 0.83 | 0.51 to 0.77 | wide |
| keyword (BM25) | 9.4 to 39.9 | 6.2 to 19.3 | wide |

Why fusion cannot separate: RRF uses ranks, not relevance. A top piece that both searches rank
first always scores about 0.033, even when the question is off-topic. So abstention has to come
mainly from the model's own `NOT_IN_DOCS` answer; the threshold is only a cheap pre-filter that
saves a model call.

## Chosen value (provisional): `search.evidence_threshold: 0.020`

- Meaning: the best piece must be found by both searches. A piece found by only one search at
  rank 1 scores 1/61 = 0.0164 at most; both-search agreement gives 0.025 or more.
- On the 28 dev questions: it abstains on 1 of 9 unanswerable (`t-003`, 0.0164) and on 0 of 19
  answerable, so it costs nothing here and saves a model call.
- Not tuned further on purpose: a value near 0.0294 would also catch `t-001`, but sits 0.0004 below
  the weakest answerable hit, which is fitting to noise on 28 questions.
- Revisit when friends' questions exist (held-out rows in the `questions` table).

Full table: run `python -m app.cli calibrate --retrieval docs/evals/retrieval-2026-10-20b.json`.
