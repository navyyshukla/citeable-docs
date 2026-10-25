# Citeable Docs (VisiData docs assistant) — project instructions

Project name: **citeable-docs** (GitHub repo, Neon project, Python package, Render services, Google project). Display name: Citeable Docs. Folder on disk: `Citeable-docs Project`.

Free tiers only (no card). Claude Code writes code; the owner decides and must be able to explain every decision.

## Read first
1. `docs/superpowers/plans/2026-10-15-plan-1-spikes-and-core-engine.md` — Plan 1 (spikes first, then core engine). Execution state = its checkboxes.
2. `docs/superpowers/specs/2026-10-15-docs-assistant-design.md` — the design spec
3. `docs/decisions/decision-log.md` — why each decision beat its alternatives (read only if needed)

## Current state (2026-10-20, session 4)
Execution: **native** (skill `superpowers:executing-plans`), one task at a time. Helper scripts: `~/.claude/plugins/cache/claude-plugins-official/superpowers/7.0.0/skills/executing-plans/scripts/` (`task-start PLAN N`, `task-done PLAN N BASE -- <test cmd>`). Ledger: `.superpowers/sdd/<plan-name>/progress.md` (git-ignored; if lost, trust `git log` and the plan's checkboxes).

**Done:** Plan 1 (engine, evals, baseline; merged and pushed). **Plan 2** (`docs/superpowers/plans/2026-10-20-plan-2-api-safety-beta.md`) is built on branch `plan-2-api` (NOT pushed, NOT merged; `main` auto-deploys on Render): Tasks 16-22 done, Task 23 done offline (render.yaml, scripts/smoke.py, docs/ops/deploy.md), Task 24 cold review done (0 Critical, 4 Important and 5 owner-approved minors fixed with tests; the other minors were consciously skipped, listed in the ledger). 365 tests offline, plus 36 real-database tests (`set -a; . ./.env; set +a; .venv/bin/pytest tests/test_store.py tests/test_usage.py -q`, about 6 minutes), ruff clean. Decisions D19, D20 in the decision log (D19: all four owner reasons written).
**Live demo done (2026-10-20, owner approved):** production `init-db` + `ingest` (229 pieces, `stable@6c4c5a4f24`, `ingest_meta` row present, token `owner-test` exists), API run locally and smoke-tested 5/5, dev-set answers eval 329.6 neurons (9/9 abstained, 17/17 answered citing gold, 2 answerable abstained), first Gemini judge run (a numbering bug in the judge input was found and fixed; run 2: 17/17, still UNCALIBRATED). Report: `docs/evals/live-demo-2026-10-20.md`. Verified: the Gemini request shape works.
**Waiting on the owner (each needs approval first):** (1) create the Render service in Ohio from `render.yaml` and paste 4 secrets (render.yaml must be on GitHub first: merge `plan-2-api` to `main` and push, then create the Blueprint; nothing deploys until the service exists), (2) pick/override `search.evidence_threshold` (provisional 0.020), (3) hand-grade about 25 answers to calibrate the judge (`judge-agreement`), (4) first cold-start timing on Render (`SMOKE_TOKEN=... python scripts/smoke.py URL`).
**Next:** after the deploy checks, write Plan 3 (chat page with safe markdown and no raw HTML, thumbs up/down, privacy notice, /evals, failure browser, invite-link format). Friends' questions arrive after Plan 3; the `questions` table is the held-out set. Still open from the review (owner agreed to skip for now): scheduled `purge` (needs a GitHub secret, owner's call), neuron-cap overshoot under parallel load (2,000 headroom), stale index until restart after ingest (documented in deploy.md). Plan 3 must add a localhost CORS origin for local page development and remove it before the beta.
Free-tier reality: Cloudflare 10,000 neurons/day (resets 05:30 IST); the API stops at 8,000 (config `limits.global_daily_neurons`) to leave room for evals.

**Code map:** `app/config.py` (strict typed config), `app/db.py` (pool + retry), `app/store.py` (Postgres + pgvector), `app/usage.py` (tokens, question log, caps, feedback), `app/service.py` (one question end to end), `app/api.py` (FastAPI), `app/llm/gemini.py` + `evals/judge.py` + `evals/threshold.py`, `app/llm/{base,cloudflare,groq,build}.py` (provider chain), `app/search.py` (BM25 + key path + hybrid), `app/answer.py`, `evals/{schema,runner}.py`, `ingest/{clean,chunk,fences,fetch,pipeline,models}.py`, `tests/`, `config/visidata.yaml`, `spikes/` (throwaway, not linted).
**How to run:** `.venv/bin/pytest -q` (store tests need `TEST_DATABASE_URL`, take about 3 minutes, are skipped in CI: `set -a; . ./.env; set +a; .venv/bin/pytest -q`), `.venv/bin/ruff check .`. Python 3.13 locally, 3.12 in CI. `.env` values must be single-quoted; never print them. `.env` has `CF_ACCOUNT_ID`, `CF_API_TOKEN`, `DATABASE_URL` (production Neon branch: now holds the 229 pieces and the usage tables), `TEST_DATABASE_URL`, `GITHUB_TOKEN`, `GEMINI_API_KEY`, `GROQ_API_KEY`.

**Decisions that shape the remaining tasks** (details: `docs/decisions/decision-log.md` D12-D17, `docs/spikes/README.md`; the plan's per-task "Note from ..." blocks hold the exact requirements):
- Models (D14, D15): users get Cloudflare `gemma-4-26b-a4b-it` -> Groq `openai/gpt-oss-20b` (`reasoning_effort: low`) -> Cloudflare `llama-3.1-8b-instruct-fp8`; any failure (non-200, empty, `finish_reason` != stop) moves to the next. Tests and judge: Gemini `gemini-3.5-flash-lite` on public data only (free tier trains on content: never send user questions).
- Thinking OFF for gemma (D17, S10): `chat_template_kwargs: {"enable_thinking": false}`; 57% fewer neurons, 5x faster; owner confirmed, re-check on the Task 15 dev set. Cost: easier to talk out of the rules, so Task 13 must accept an answer only if it cites a piece we sent or is exactly the abstention marker, and must strip any link not on the docs' own pages (S5b, S10).
- Search (S2, S6): hybrid (symbol-aware keyword + exact backticked-key path + meaning search, rank fusion) is the default; no question-rewriting model call. Embed `search_text[:2000]` (the embedding model silently cuts at about 2,100 chars, S8). Embedding responses carry no usage field.
- Citations (S7): `#anchor` only for headings with their own `{#id}`; otherwise the page URL. Ingest makes relative links absolute and drops images.
- Database (S9, S11): Neon is in us-east-2 behind a pooler: use `SET LOCAL` inside a transaction for per-query settings; a new connection costs about 1.5 s from the laptop, so Plan 2 needs a pool; real API goes on Render in **Ohio** (the spike service is in Oregon). `search.vector_index: none` by default (exact search 35 ms at 14k pieces); `hnsw` is optional.
- Rejected (D16): provider prompt caching, semantic cache, Kafka, Redis (triggers to revisit are in D16). Exact-match answer cache and streaming are Plan 2, after the beta shows repeat rates.
- Free-tier facts: Cloudflare 10,000 neurons/day (resets 05:30 IST), slow under load; Groq 1,000 requests/day, 8k tokens/min; Gemini Flash-Lite 500/day.
- Weak spots to keep honest: most evidence is small (15 to 30 questions, synthetic benchmark data); real quality comes from the Task 15 dev set (`docs/spikes/s3-questions.md`: curate from 2023-onward Q&A, keep candidate text out of git).

## Standing rules
- Simple language and a text diagram in EVERY response and every post-task report (owner reminder, 2026-10-19); every study link says what it is for and what to read/skip, and is verified before sharing.
- For every architectural choice: how, 2-3 alternatives with trade-offs, recommendation, what to study. Owner picks and gives one sentence why.
- Push back with reasoning when the owner's choice looks wrong; do not just agree. Separate verified facts from estimates.
- Hard rules: everything free; assistant has no tools and no private data; never commit copies of VisiData docs; project specifics live in `config/`; tests run on a different provider bucket than users.
- Do not use the Context MCP (`mcp__context__*`): its free quota is exhausted. Use WebSearch, WebFetch, exa, GitHub tools.
- After every task (and spike): report in simple language with text diagrams: what the task was, what is next, where we stand, and what needs a second opinion, another run or another test (even if nothing).
- Outward-facing actions (posting, emailing, contacting maintainers) only with explicit owner approval. Ask before every `git push`; the owner approves pushes case by case.
- Usage economy: one focused task per session, reference files by path, avoid broad research fan-out, spawn subagents only when asked or clearly worth it.
