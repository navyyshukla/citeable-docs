# Citeable Docs (VisiData docs assistant) — project instructions

Project name: **citeable-docs** (GitHub repo, Neon project, Python package, Render services, Google project). Display name: Citeable Docs. Folder on disk: `Citeable-docs Project`.

Free tiers only (no card). Claude Code writes code; the owner decides and must be able to explain every decision.

## Read first
1. `docs/superpowers/plans/2026-10-15-plan-1-spikes-and-core-engine.md` — Plan 1 (spikes first, then core engine). Execution state = its checkboxes.
2. `docs/superpowers/specs/2026-10-15-docs-assistant-design.md` — the design spec
3. `docs/decisions/decision-log.md` — why each decision beat its alternatives (read only if needed)

## Current state (2026-10-19, end of session 2)
Execution: **native** (skill `superpowers:executing-plans`), one task at a time, an independent cold review after Task 9 (done) and after Task 15. Task helper scripts live in `~/.claude/plugins/cache/claude-plugins-official/superpowers/7.0.0/skills/executing-plans/scripts/` (`task-start PLAN N`, `task-done PLAN N BASE -- <test cmd>`). The ledger is `.superpowers/sdd/2026-10-15-plan-1-spikes-and-core-engine/progress.md` (git-ignored, local; if it is lost, trust `git log` and the plan's checkboxes).

**Done:** spikes S0-S11 and the Task 5 gate (D15); Tasks 6-10 and cold review #1; optional vector index (D16); Tasks 11-14 (LLM adapter + Groq + embeddings, hybrid search, answer pipeline with citation rule and link allowlist, eval harness). 177 tests without the store tests, ruff clean. Repo: https://github.com/navyyshukla/citeable-docs (public, `main`).
**Next:** Task 15 (CLI + first ingest into the production Neon branch + dev set + baseline report), then cold review #2. Read the new "Note from Tasks 11-14" block at the top of Task 15 first: no Gemini in Task 15 (owner decided; baseline answers use the user chain under `--max-neurons`; Gemini is the Plan 2 judge), paste-all is about 320 neurons per question so run it on at most 5 questions, and tell the owner before the first write to `DATABASE_URL`. Dev-set curation needs the owner (real 2023-onward questions, see `docs/spikes/s3-questions.md`). Plans 2 (API/safety/beta) and 3 (web, /evals) are written after Plan 1.
**Code map:** `app/config.py` (strict typed config), `app/store.py` (Postgres + pgvector), `app/llm/{base,cloudflare,groq,build}.py` (provider chain), `app/search.py` (BM25 + key path + hybrid), `app/answer.py`, `evals/{schema,runner}.py`, `ingest/{clean,chunk,fences,fetch,pipeline,models}.py`, `tests/`, `config/visidata.yaml`, `spikes/` (throwaway, not linted).
**How to run:** `.venv/bin/pytest -q` (store tests need `TEST_DATABASE_URL`, take about 3 minutes, are skipped in CI: `set -a; . ./.env; set +a; .venv/bin/pytest -q`), `.venv/bin/ruff check .`. Python 3.13 locally, 3.12 in CI. `.env` values must be single-quoted; never print them. `.env` has `CF_ACCOUNT_ID`, `CF_API_TOKEN`, `DATABASE_URL` (production Neon branch, untouched so far), `TEST_DATABASE_URL`, `GITHUB_TOKEN`, `GEMINI_API_KEY`, `GROQ_API_KEY`.

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
