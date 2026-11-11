# Test Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (native). Steps use checkbox syntax.

**Goal:** A refusal set, fallback-model answer measurements, repeat runs and a sealed held-out answerable set, reported with ranges on `/evals`.

**Architecture:** Reuse `python -m app.cli eval/judge/generate-questions` and the `/evals` builder; add `eval --provider`, `generate-questions --exclude-from`, two question files and a short written audit of the answered-refusals.

**Tech Stack:** Python (pydantic, pytest, ruff), existing eval runner and report builder.

**Spec:** `docs/superpowers/specs/2026-11-12-test-expansion-design.md`.

## Global Constraints
- Free tiers only; stay under 10,000 neurons a day with 1,000 spare; Gemini under 500 calls a day; Groq paced (3 s between calls). The owner authorised testing spend for today and tomorrow ("don't worry about neurons and tokens"); stop and ask before any push and before anything outside testing.
- Question files hold questions only; results stay in git-ignored `evals/results/`; never commit docs text; never send user questions to Gemini.
- Real-database commands need `set -a; . ./.env; set +a` and the `PGHOSTADDR` workaround in CLAUDE.md. Public repo: neutral wording, scan the diff before every push.

## Review Focus
1. A refusal question the system answers is audited by reading the cited pages: label error vs real guess, both counts reported (Task 3).
2. `--exclude-from` must skip every piece whose page and heading appear in earlier question files, so the held-out set shares no piece with dev or synthetic (Task 4).
3. `--provider` must reject an entry not in `models.answer_order` and must not change the answer path for any other command (Task 1).
4. `/evals` must say how each set was labelled and show ranges across runs, never a single run as a headline (Task 5).

---

### Task 1: Force one provider in `eval`
**Files:** Modify `app/cli.py`; Test `tests/test_cli.py`.
**Interfaces:** `eval --provider ENTRY` (an entry of `models.answer_order`); uses `evals.cards_eval.with_provider(cfg, entry)` (move it to `app/config.py` as `Config.with_chain(entry)` or import it; builder's choice).
- [ ] **Step 1:** Failing tests: `test_eval_provider_must_be_in_the_chain`; `test_eval_without_provider_uses_the_whole_chain`; parser accepts `--provider`.
- [ ] **Step 2-4:** Implement; run `.venv/bin/pytest -q tests/test_cli.py && .venv/bin/ruff check .`.
- [ ] **Step 5:** Commit `feat: eval can force one provider`.

### Task 2: The refusal set
**Files:** Create `evals/data/refusal.jsonl`; Test `tests/evals/test_refusal_set.py`.
- [ ] **Step 1:** Failing tests: file loads with `load_questions`; at least 60 questions; all `answerable: false`, `split: "heldout"`, unique ids prefixed `u-`; each of the six groups has at least 6 questions (group named in `source_url`-free field: use the id range, documented in the test); no question over 500 characters; no duplicates of dev or synthetic questions.
- [ ] **Step 2-4:** Write the 60 questions; run the tests and ruff.
- [ ] **Step 5:** Commit `feat: refusal question set`.

### Task 3: Runs A, B and C (spends neurons; authorised within the budget)
**Files:** none committed (results are git-ignored); a short audit note goes into the decision log in Task 6.
- [ ] **Step 1:** Run A once: `.venv/bin/python -m app.cli eval --data evals/data/refusal.jsonl --split heldout --modes hybrid --answer --out evals/results/refusal-1.json`. List every question the system answered (not refused); read each with its cited pages and decide label error or guess. Report both counts.
- [ ] **Step 2 (B):** Dev set with each fallback alone: `... eval --provider "groq:openai/gpt-oss-20b" ...` and `--provider "cloudflare:@cf/meta/llama-3.1-8b-instruct-fp8"`; also the refusal set with each. Compare refusals, answered, invalid citations with the main model.
- [ ] **Step 3 (C):** Dev set 4 more times (5 total) and the refusal set 2 more times (3 total) with the normal chain.
- [ ] **Step 4:** Summarise with `python -m evals.report` helpers: per set, per model, count, range across runs, exact-count interval.

### Task 4: The sealed held-out answerable set (Gemini; spends calls)
**Files:** Modify `app/cli.py` (and `evals/generate.py` if needed); Create `evals/data/heldout.jsonl`; Test `tests/test_cli.py`, `tests/evals/test_generate.py`.
**Interfaces:** `generate-questions --exclude-from FILE...` skips pieces whose (page, heading) appear in those files.
- [ ] **Step 1:** Failing tests: excluded pieces are never chosen; a missing file is an error.
- [ ] **Step 2-4:** Implement; run tests and ruff.
- [ ] **Step 5:** Commit `feat: generate-questions can skip earlier pieces`.
- [ ] **Step 6:** Generate about 150 raw questions (Gemini, paced), Gemini-check them, then an independent Claude subagent checks them blind; keep those both pass; write `evals/data/heldout.jsonl` (about 100, `split: "heldout"`, `source: "synthetic"`). Commit questions only.
- [ ] **Step 7:** Run it 3 times (about 1,500 neurons each), judge with Gemini as a rough filter, record ranges. **Do not change any prompt or rule after this** (sealed).

### Task 5: Show it on `/evals`
**Files:** Modify `evals/report.py`, `scripts/build_site.py` if needed; Test `tests/evals/test_report.py`, `tests/test_build_site.py`; rebuild `site/public/evals.html`.
- [ ] **Step 1:** Failing tests: new sections for the refusal set, the fallback models and the held-out set; each shows k/n, a range across runs and the labelling text ("hand-written by us, answered cases audited", "AI-checked only, not human-checked"); no single run is a headline when more than one exists.
- [ ] **Step 2-4:** Implement; build `evals.html` from the saved runs; open it in light and dark.
- [ ] **Step 5:** Commit `feat: evals page shows the larger sets and ranges`.

### Task 6: Decision, docs and push (owner-gated)
- [ ] **Step 1:** D28 in the decision log (what was measured, ranges, the audit of answered refusals, label errors found, the fallback comparison, what the numbers do not show); update README numbers and `CLAUDE.md`.
- [ ] **Step 2:** Full suite, then **stop and ask** before pushing; scan the diff for personal wording.
