# Better Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (native). Steps use checkbox syntax.

**Goal:** Raise the right-page-in-top-5 rate for plainly worded questions by weighting the search fusion, confirmed on a new sealed set.

**Architecture:** `Searcher` fuses three ranked lists (exact-key, BM25, meaning) with configurable weights; an offline tuner replays cached per-leg rankings so weights can be searched without model calls.

**Spec:** `docs/superpowers/specs/2026-11-13-better-search-design.md`.

## Global Constraints
- Defaults (all weights 1.0, the exact-key list inside the keyword list) must reproduce today's search results exactly (a test pins this). Free tiers; ask before every push; the owner authorised testing spend on 2026-11-11 for that testing window only, so ask before runs that spend more than about 2,000 neurons.
- Tune only on `evals/data/dev.jsonl` and `evals/data/synthetic-checked.jsonl`. Never read the failures of `evals/data/heldout.jsonl` (spent for tuning) or of `heldout-2` (until the single confirm run).
- Question files hold questions only; results stay git-ignored. Neutral wording; scan the diff before every push.

## Review Focus
1. Default weights reproduce the current ranking for every query shape: plain words, a lone symbol, a symbol in backticks, empty (Task 2).
2. A symbol question ("what does the `&` key do?") still puts the exact-key section first after re-weighting (Task 2, 3).
3. The evidence gate: weights change score scale; a refusal-set run must stay 60/60 (Task 4).
4. The tuner cannot touch a sealed question file (Task 3).

---

### Task 1: A second sealed question set
**Files:** Create `evals/data/heldout2.jsonl`; Test `tests/evals/test_heldout2_set.py`.
- [ ] **Step 1:** Failing test: loads; 90 or more questions; ids `k-`... use prefix `g-` (`g-001`...); split `heldout`; answerable with gold page and heading; none equals any question in dev, synthetic, synthetic-checked, refusal or heldout (case-insensitive); no docs text.
- [ ] **Step 2:** Generate about 160 raw questions: `generate-questions --limit 80 --unanswerable 0 --exclude-from dev.jsonl synthetic.jsonl --data evals/data/heldout.jsonl --id-prefix g --split heldout` (Gemini, paced); check with Gemini (`evals.check_questions gemini`), then an independent blind Claude reader on the packets file; keep only both-pass (`keep`). Commit questions only.
- [ ] **Step 3:** Baseline: retrieval-only run of today's search on `heldout2` (`eval --modes hybrid --data evals/data/heldout2.jsonl --split heldout --out evals/results/h2-baseline.json`, no `--answer`). Record the right-page-in-top-5 numbers in the ledger and do not read the per-question failures.
- [ ] **Step 4:** Commit `feat: second sealed question set`.

### Task 2: Weighted fusion in the Searcher
**Files:** Modify `app/search.py`, `app/config.py`, `config/visidata.yaml`, `app/service.py` (pass weights), `app/cli.py` (eval pass weights); Test `tests/test_search.py`, `tests/test_config.py`.
**Interfaces:** `rrf(rankings, k=60, weights=None)` with `weights` a list the same length as `rankings` (default all 1.0); `Searcher(..., weights: SearchWeights | None)`; `SearchCfg.key_weight`, `bm25_weight`, `meaning_weight` (floats, 0 to 10, default 1.0). In hybrid mode the three lists fused are: exact-key sections (the first `KEY_FIRST` from `key_path`), BM25, meaning.
- [ ] **Step 1: Failing tests:** `test_default_weights_give_todays_ranking` (golden fixtures built before the change by running today's `Searcher` over a small piece set for queries: plain words, `&`, backticked `&`, empty; compare piece ids and scores to the new code with default weights: identical); `test_rrf_weights_scale_each_list`; `test_zero_bm25_weight_ignores_keyword_text_but_keeps_exact_key_first`; `test_a_lone_symbol_query_still_puts_the_defined_section_first_with_tuned_weights`; config: weights must be 0 to 10, strict keys.
- [ ] **Step 2-4:** Implement; run `.venv/bin/pytest -q && .venv/bin/ruff check .`.
- [ ] **Step 5:** Commit `feat: weighted fusion in the searcher (defaults unchanged)`.

### Task 3: The offline tuner
**Files:** Create `evals/search_tune.py`; Test `tests/evals/test_search_tune.py`.
**Interfaces:** `collect_legs(questions, searcher_factory) -> list[LegRankings]` (per question: key ids, BM25 ids, meaning ids at depth 30, calls the embedding once per question); `replay(legs, questions, pieces, weights, rrf_k) -> RankStats` (page-in-top-k for k in 1, 3, 5, 8, 10; page+section in top 5), pure; `grid(...) -> list[(weights, stats)]`; CLI `python -m evals.search_tune collect --out legs.json` and `grid --legs legs.json`. Refuses any question file whose path or ids match a sealed set (`heldout.jsonl`, `heldout2.jsonl`, `refusal.jsonl`).
- [ ] **Step 1: Failing tests:** replay with weights (1,1,1) equals `Searcher` hybrid ranks on fake legs; weighting changes order as expected; the sealed-file guard raises.
- [ ] **Step 2-4:** Implement and run tests.
- [ ] **Step 5:** Commit `feat: offline search tuner`.

### Task 4: Tune, choose, set the evidence gate
**Files:** Modify `config/visidata.yaml`; Test `tests/test_config.py`.
- [ ] **Step 1:** `collect` the legs for dev + synthetic-checked (48 questions, about 0 neurons); run `grid` over `bm25_weight` in {0, 0.25, 0.5, 0.75, 1}, `meaning_weight` in {1, 1.5, 2, 3}, `key_weight` in {1, 2, 3}. Print the table. Choose a simple setting that improves right-page-in-top-5 on both tuning sets separately without lowering dev's 17/19 or putting a symbol question's defined section out of the top 3. Write the chosen weights and the full table into the decision log.
- [ ] **Step 2:** Re-derive `search.evidence_threshold` with the existing `calibrate` command on dev (`threshold_table`); pick the value that keeps all 9 dev unanswerable refused and loses no answerable question.
- [ ] **Step 3:** Run the refusal set once with answers as a safety check (about 630 neurons; ask first if more than 2,000 are spent that day). It must stay 60/60; if not, stop and report (the refusal set is then spent and `/evals` says so).
- [ ] **Step 4:** Commit `feat: tuned search weights and evidence gate`.

### Task 5: The single confirm run, and the decision
- [ ] **Step 1:** Run `heldout2` once with answers (about 1,500 neurons; ask first if the day's spend would pass 8,000): `eval --modes hybrid --answer --data evals/data/heldout2.jsonl --split heldout --max-neurons 2200`. Compare with the Task 1 baseline: right page in top 5, answered, cited right page. Report whatever it shows. **No tuning after this.**
- [ ] **Step 2:** If the gain is below the goal, write the reranker decision (cost per question measured with one `@cf/baai/bge-reranker-base` probe on the tuning set) for the owner; do not build it unasked.

### Task 6: Docs, `/evals`, push
- [ ] **Step 1:** D31 (what changed, the table, the chosen weights, the before and after on `heldout2`, what the numbers do not show); update README numbers, `deploy.md` (the three weights and the gate), `CLAUDE.md`; add a before/after section to `/evals` (`evals/report_sets.py`, spec `evals/data/report-sets.json`) and rebuild `site/public/evals.html`.
- [ ] **Step 2:** Full suite with the database. **Stop and ask** before merging and pushing; scan the diff first. If the Pages deploy fails, delete the run's duplicate artifacts before re-running (lesson from 2026-11-12).
