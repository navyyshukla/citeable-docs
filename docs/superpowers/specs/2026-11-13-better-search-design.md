# Better search for plainly worded questions: design

Date: 2026-11-13. Status: draft for owner approval. **(owner)** = said or chosen by the owner; **(call)** = my decision, to be checked.

## Why

The sealed held-out test (98 questions, D29) showed the main limit of the assistant is search, not the model: the right docs page was in the top 5 results for 82 of 98 questions (84%; 68% if the right section is also required), and when it was, the assistant answered 94% of the time. **(owner)** chose "better search for plainly worded questions" as the next project, and chose the approach: re-weight the fusion first, and add a reranker only if that falls short. Rewriting questions or expanding the docs at ingest stays a later option (decision D16 rejected a rewriting call for cost and delay).

## What the diagnostic found (dev + generated tuning sets, 48 questions; held-out questions not used)

| Right page within the top | 1 | 3 | 5 | 8 | 10 | 20 | never in 30 |
|---|---|---|---|---|---|---|---|
| keyword only | 20 | 26 | 31 | 32 | 33 | 42 | 3 |
| meaning only | 32 | 38 | 42 | 44 | 44 | 45 | 2 |
| hybrid (today) | 22 | 35 | 38 | 43 | 44 | 47 | 1 |

Today's search fuses a keyword list (exact-key definitions first, then BM25) with a meaning list using equal weights. On plain wording the keyword half drags good meaning matches down (meaning-only is better at the top), but exact keys such as `&` need the keyword side. And the right page is almost always found, only ranked too low (9 of 10 misses sit at rank 6 to 17).

## The plan in one picture

```
 today:   RRF( keyword[key-path first, then BM25] , meaning )              equal weights
 step 1:  RRF( key-path×wk , BM25×wb , meaning×wm )                       weights tuned on the tuning sets
 step 2 (only if step 1 falls short):  take the top 20, let a reranker re-order them, keep 5
```

## Goals / non-goals / anti-goals

- **Goal. (call)** Raise "right page in the top 5" on plainly worded questions from about 79% (tuning sets) to at least 88%, with no loss on the dev set (17/19 today) and none on symbol questions such as "what does the `&` key do?". Success is confirmed once on a NEW sealed set, not on the tuning sets.
- **Non-goals:** changing the answer prompt, the model chain, ingest or the database; question rewriting; follow-up memory.
- **Anti-goals:** a gain that only shows on the questions we tuned on; more wrong answers (refusal must stay 60/60 on the refusal set); a slower or costlier assistant without a measured gain.

## Method and the sealing rules

1. **A second sealed set first. (call)** Before any tuning, generate and two-checker-validate about 100 new plain-wording questions (`heldout-2`), different from every earlier question (deduplicated against all sets). Measure today's search on it, retrieval only (about zero neurons), and save that as the baseline. **After that, no one looks at its failures while tuning.**
2. **Tune only on dev + `synthetic-checked` (48 questions).** A small grid of weights, evaluated offline from cached per-leg rankings (no model calls while searching the grid). Prefer a simple, round setting over the single best number, and require the gain to show on both tuning sets separately.
3. **Re-check the evidence gate.** The gate (a minimum fused score, 0.020 today) lives on the fusion's score scale, so any weight change moves it. It is re-derived on the dev unanswerable questions, then the refusal set is run as a safety check: it must stay 60/60. If the threshold needs changing after looking at the refusal set, the refusal set is spent as a held-out test and I say so on `/evals`.
4. **Confirm once** on `heldout-2`: retrieval and answers, one run, compared with its baseline. Whatever it shows is what we report, including no gain.
5. Step 2 (reranker) is a separate decision after step 1's numbers.

## Constraints

Free tiers; no change to the page or API contract; weights live in `config/visidata.yaml` (defaults reproduce today's behaviour exactly, tested); retrieval-only measurements stay near zero neurons; ask before every push.

## Left to the builder

The weight grid values, the cache format for per-leg rankings, and how the `/evals` page shows the before and after.
