# Spike results (Plan 1)

Status: DRAFT for the Task 5 review gate, waiting for owner sign-off. Details are in the linked files; this table is the one-line view.

| Spike | Result (one line) | Decision taken |
|---|---|---|
| [S0 accounts](s0-accounts.md) | Cloudflare chat and embedding work on the free plan; the plan's chat model id is deprecated; 3 of 4 candidate models are reasoning models that can return empty text; the free-quota wall was not reached in 3 attempts (throughput was the limit, about 0.15 calls/s); dashboard showed 7.16k of 10k neurons used and no charge | fallback models: Groq `gpt-oss-20b` for users, Gemini `gemini-3.5-flash-lite` for tests and judge (public data only); embedding_dim: 768; context window: aliased model unverified (nearest sibling 32k), so paste-all needs a 128k model; exhaustion: error code unknown, so the adapter treats any non-200 as "try the next provider"; answering model: Cloudflare `gemma-4-26b-a4b-it` (S5: 11/11 on a tiny set, about 20 neurons/question), fallback 2 `llama-3.1-8b-instruct-fp8` (D15) |
| [S1 sources](s1-sources.md) | `stable` matches the published headings on 2 of 3 pages; `stable` and `develop` differ in 13 of 32 files; inline `{help.*}` placeholders exist | ref: `stable`; command reference: no ready-made file, candidates listed in S1 (c), docs only for v1; carry-overs: inline placeholders (Task 7), emphasis in headings (Task 8), anchors may be missing on the published page (Task 9) |
| [S2 symbols](s2-symbols.md) | Word-only 8/9, symbol-aware 7/9, symbol-aware plus exact backticked-key path 9/9 (small, partly tuned set of 9 queries) | tokenizer: symbol-aware plus an exact backticked-key path with a definition-row boost, as its own tested step in Task 12 |
| [S3 questions](s3-questions.md) | The plan's script found 11 (shallow scan); the extended count found 115 labelled issues with a maintainer reply and 164 answered Q&A discussions (counts, not quality) | real questions available: yes, viable; use 2023-onward items first, verify every answer against `stable`, keep candidate text out of git |
| [S4 cold start](s4-coldstart.md) | Three cold requests: 24.2 s, 21.8 s, 21.8 s; peak memory 72 MB of 512 MB (floor for our dependencies only); instance is 0.1 CPU | proceed: UI shows a "waking up" state; pin the Python version on Render; load lazily because of the 0.1 CPU |
| [S5-S5c gemma](s5-gemma.md) | gemma-4: 11/11 short questions, long answers fine, obeyed a hidden link, failed rambling and follow-up questions because of keyword search | link allowlist in Task 13; hybrid search in Task 12; single-question v1 |
| [S6 embeddings](s6-embeddings.md) | hit@5 on 13 queries: keyword 11, meaning 12, hybrid 13 | hybrid is the default search |
| [S7 anchors](s7-anchors.md) | explicit `{#id}` anchors exist on the site (32/32); generated ones do not (0/173) | cite `#anchor` only for explicit ids |
| [S8 truncation](s8-truncation.md) | the embedding model silently cuts input at about 2,100 to 2,300 characters | embed `search_text[:2000]` |
| [S9 latency](s9-neon-latency.md) | new Neon connection about 1.5 s, query about 0.25 s from the laptop | connection pool, Ohio region for the API |
| [S10 thinking](s10-thinking.md) | thinking off: 57% fewer neurons, 5x faster, 15/15 against 13/15; but follows "ignore the rules" in a user question | thinking off plus a citation-required output rule (D17) |
