# Citeable Docs (VisiData docs assistant) — project instructions

Project name: **citeable-docs** (GitHub repo, Neon project, Python package, Render services, Google project). Display name: Citeable Docs. Folder on disk: `Citeable-docs Project`.

Free tiers only (no card). Claude Code writes code; the owner decides and must be able to explain every decision.

## Read first
1. `docs/superpowers/plans/2026-10-15-plan-1-spikes-and-core-engine.md` — Plan 1 (spikes first, then core engine). Execution state = its checkboxes.
2. `docs/superpowers/specs/2026-10-15-docs-assistant-design.md` — the design spec
3. `docs/decisions/decision-log.md` — why each decision beat its alternatives (read only if needed)

## Current state
Execution method chosen by the owner: **native** (skill `superpowers:executing-plans`), with an independent cold review after Task 9 and after Task 15. Plans 2 (API/safety/beta) and 3 (web, /evals) are written AFTER Plan 1 Task 5 (spike review gate). Do not write product code before Task 5 sign-off; spikes only.

Progress (2026-10-19): Tasks 0-4 done; Task 5 gate approved by the owner 2026-10-19 (D15 recorded; spikes S5, S5b, S5c, S6 added: gemma-4 main, hybrid search required in Task 12, link-allowlist output check in Task 13). Task 6 done (scaffold, typed config, CI; 3 tests pass, ruff clean; CI not yet seen running on GitHub, needs a push). Task 7 done (cleaner, 11 tests incl. all real docs; CI green on GitHub for Task 6). Task 8 done (chunker; 26 tests). Task 9 done (fetch + pieces; 39 tests; S7: generated anchors do not exist on the published site, only explicit {#id} ones). Cold review #1 (Tasks 6-9) done: 0 Critical, 6 Important and all 15 Minor fixed (68 tests; word-loss guard on the real docs; spikes S7, S8). Task 10 done (Postgres + pgvector store, 9 store tests on the Neon test branch; S9: about 1.5 s per new connection from the laptop, Render region unknown). Next: Task 11 (LLM adapter and embeddings), on the owner's go. Task 0 Step 6 (exhaustion test) attempted 3 times; quota wall NOT reached (Cloudflare was slow, ~0.15 calls/s, not exhausted); recorded in `docs/spikes/s0-accounts.md`. Task 4 (Render cold start): cold #1 24.2 s, #2 21.8 s, memory 72 MB; cold #3 21.8 s, done (proceed). Repo: https://github.com/navyyshukla/citeable-docs (public, `main`). Decisions D12-D15 in the decision log. Execution state = the plan's checkboxes. Findings live in `docs/spikes/`.

Key findings so far (details in `docs/spikes/s0-accounts.md`, `s1-sources.md`): the plan's chat model id `@cf/meta/llama-3.1-8b-instruct-fp8-fast` is deprecated (aliased, not in the catalog); 3 of 4 candidate Cloudflare models are reasoning models that can return empty text; user fallback = Groq `gpt-oss-20b`; tests/judge = Gemini `gemini-3.5-flash-lite` on public data only (Gemini free tier trains on content, so never send user questions); answering model is chosen at Task 5. `.env` values must be single-quoted (URLs contain `&`).

## Standing rules
- Simple language and text diagrams; every study link says what it is for and what to read/skip, and is verified before sharing.
- For every architectural choice: how, 2-3 alternatives with trade-offs, recommendation, what to study. Owner picks and gives one sentence why.
- Push back with reasoning when the owner's choice looks wrong; do not just agree. Separate verified facts from estimates.
- Hard rules: everything free; assistant has no tools and no private data; never commit copies of VisiData docs; project specifics live in `config/`; tests run on a different provider bucket than users.
- Do not use the Context MCP (`mcp__context__*`): its free quota is exhausted. Use WebSearch, WebFetch, exa, GitHub tools.
- After every task (and spike): report in simple language with text diagrams: what the task was, what is next, where we stand, and what needs a second opinion, another run or another test (even if nothing).
- Outward-facing actions (posting, emailing, contacting maintainers) only with explicit owner approval.
- Usage economy: one focused task per session, reference files by path, avoid broad research fan-out, spawn subagents only when asked or clearly worth it.
