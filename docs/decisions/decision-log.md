# Decision Log

Format per entry: choice, alternatives rejected, why, what would change our mind, evidence status.
Dates: decided 2026-10-13 to 2026-10-15. To be split into one file per decision when the repo is created.

## D1. Backend: Python + FastAPI
- Alternatives: TypeScript + Next.js full-stack; Python + Streamlit/Gradio.
- Why: richest AI ecosystem; Python in ~82% of AI-engineer postings and FastAPI ~11% (one JD analysis, small/unknown sample). Streamlit hides the engineering there is to explain.
- Change our mind if: we find we cannot review Python comfortably and a TS-only stack is clearly faster.

## D2. Target project: VisiData (unofficial)
- Alternatives: jrnl (tiny docs ~76 KB, retrieval hard to justify), tmuxp/harlequin/jc (fewer questions).
- Why: ~141 KB docs, in-repo Markdown, no AI assistant found, real community, rich question types; eval ground truth can come from past maintainer answers.
- Honest note: fresh Q&A volume is low (newest Discussion seen 2026-07-17). Value = engineering evidence, not VisiData impact.
- Change our mind if: spike (c) shows too few clear maintainer answers for an eval set.

## D3. Scope: reusable engine, VisiData first
- Alternatives: VisiData hard-coded; multi-project hosted platform.
- Why: small extra work, honest "others could reuse it" answer, forces project specifics into config. Hosted platform = accounts, abuse, quota risk.

## D4. AI models: adapter, 1 main + 2 fallbacks + 1 separate-family judge, cloud-only evals
- Alternatives: single provider; 1 main + 4-5 fallbacks; local model for tests.
- Why: free limits change (Gemini Pro left free tier Apr 2026 per a roundup); every answering model must be scored (5 models = 5x eval cost); a local model measures a different model than users get; judge from another family avoids self-preference bias.
- Facts: Cloudflare Workers AI 10,000 neurons/day free (verified); OpenRouter :free 20 req/min, 50/day under $10 credits (verified, excluded); Gemini/Groq limits visible only in account.
- Unverified: Cloudflare behavior when allocation is exhausted (still unknown after S0; see D14, D15).

## D5. Launch: public unofficial beta in week 2 with caps
- Alternatives: public only after polish; beta week 1.
- Why: real usage history and incident log should exist before the public launch is promoted; tests and users must draw from different provider buckets.

## D6. Hosting: Render free + Neon + GitHub Pages
- Alternatives: all-Cloudflare (Python Workers unverified); Supabase (pauses after 1 week idle); HF Spaces (Docker/Gradio need paid plan); Render free Postgres (expires in 30 days).
- Why: verified free terms, no card. Weakness: ~1 min cold start after 15 min idle; UI "waking up" state first, keep-alive only if justified.

## D7. Ingestion and search
- Alternatives: fixed-size chunks; AI-written chunk summaries; develop branch; docs-only vs also command reference.
- Why: real files showed heading structure, keystroke-heavy content, template placeholders, develop ahead of published site, stale 2020-2021 pages. Hence: stable branch/tag, clean, cut by headings with path, tables kept with header, symbol-safe keyword path, version/date shown.
- Search: paste-all baseline vs keyword vs meaning vs hybrid, measured, winner kept. Free quota math favors retrieval (paste-all ~155 neurons vs ~23).
- Pending spikes: stable vs published; symbol queries; command reference location.

## D8. Evals: Mixed
- Alternatives: light (code checks only); heavy (judge + human on all).
- Why: follows the Claude docs develop-tests principles; code checks first, calibrated judge, ~25 hand-graded answers, dev vs held-out, CI gate, public scoreboard, counts shown with noise caveat.
- Deviations from the doc (deliberate): volume capped by free quota; small human set kept to calibrate the judge.

## D9. Answer behavior and safety
- Alternatives: strict only; lenient with hedging.
- Why: strict + 3 closest pages avoids confident wrong answers while staying useful. No tools and no private data removes the "lethal trifecta". Output link allowlist stops exfiltration via links/images.

## D10. Frontend and framework
- Frontend: Next.js (App Router, TS) static export on GitHub Pages. Alternative: plain HTML/JS (recommended by Claude; user chose Next.js for a finished-product look). Cost: a second language to maintain, so beta = one chat page.
- Framework: thin hand-written core, no LlamaIndex. Alternative considered: LlamaIndex (29 direct deps, default answer mode may issue multiple LLM calls = 2-5x neuron use, no confirmed Cloudflare integration, weaker explainability). User chose thin core after impact analysis.
- Logging: own Postgres tables v1; Langfuse Hobby (50k units/mo, 30-day retention) later. CI: GitHub Actions (free for public repos). License MIT. Never commit copies of VisiData docs.

## D11. First users: evidence-first
- Alternatives: community-first; big launch (Show HN + Reddit).
- Why: the community is quiet and real usage data comes first; one-shot launches on a free backend are risky. Nothing posts without the user's say-so. Beta goal: >=30 real questions from >=5 people, >=3 documented failures with fixes in 3 weeks (suggested number).

## D12. Project name: citeable-docs
- Alternatives: `citeable` (16 GitHub repos and 3 similar accounts already use it, some in the same AI-citation space); `docsmith` (88 repos; "smith" suggests a docs generator, our tool answers questions from docs).
- Why (owner): "explains all our work". Evidence: `citeable-docs` has 0 GitHub repos, 0 accounts, and is free on PyPI (checked 2026-10-15).
- Used everywhere: repo, Neon project, package, Render services, Google project. Not reserved anywhere yet. Weakness: free until someone takes it.

## D13. Execution method: native with cold reviews
- Alternatives: subagent-driven per task (more cost, more context re-derivation on a Claude Pro plan).
- Why (owner): sequential tasks suit one continuous session. An independent cold review after Task 9 and after Task 15 catches what the author misses.

## D14. Fallback and test models (decided at S0, 2026-10-18)
- User fallback after Cloudflare: Groq `openai/gpt-oss-20b` (reasoning effort low). Groq does not keep inputs or outputs by default. Measured on the owner's account: 1,000 requests/day, 8,000 tokens/min.
- Tests and judge, public data only: Gemini `gemini-3.5-flash-lite` (15/min, 250K tokens/min, 500/day, read from the owner's AI Studio). Rare spot-checks: `gemini-3.8-flash` (5/min, 20/day).
- Alternative rejected: Gemini 3.8 Flash for tests (20/day too low for an eval run).
- Rule: Gemini free tier lets Google use content to improve products, so no real user question goes to Gemini.
- Open: eval answers on Gemini describe Gemini's answers, not Cloudflare's. Decide in Plan 2.
- Open: the answering model for users (planned id is deprecated). Decide at Task 5.

## Owner understanding checks (2026-10-19)
- **Neuron:** Cloudflare's billing unit for compute, not a token. Tokens in and out are converted to neurons at a per-model rate. Free allowance 10,000 neurons/day; the model choice sets how many questions fit.
- **Exhaustion test:** its purpose is to learn what happens when the allowance runs out (error code, message, any charge, whether other models still work) so the adapter falls back safely. Attempted 3 times; the wall was not reached because Cloudflare's speed limited us first. The adapter treats any non-200 as "fall back".
- **Why ingest `stable`:** it matched the published headings on 2 of 3 pages and is what released VisiData ships with; `develop` has unreleased features that users may not have. The published site is slightly ahead of `stable`; pinning a tag stays open for Task 5.

## D15. Answering model and second fallback (decided at the Task 5 gate, 2026-10-19)
- Main: Cloudflare `gemma-4-26b-a4b-it` (256k context, so paste-all can run; S5: 11/11 on a tiny set, about 20 neurons/question short, about 38 with 5 full pieces; S5b found it obeyed an instruction hidden in a doc piece, so the output check must block non-allowlisted links). Fallback 1: Groq `openai/gpt-oss-20b` (D14). Fallback 2: Cloudflare `llama-3.1-8b-instruct-fp8`.
- Alternatives for fallback 2: another Groq model (same provider as fallback 1, separate bucket unconfirmed); no second fallback.
- Owner's reason: it is not a thinking model, so it does not hit the empty-answer problem that gemma can hit; when gemma returns no answer the chain moves on and still gets one.
- Claude's note: the fallback re-answers the same question from scratch, it does not continue gemma's output. It shares Cloudflare's neuron pool, so it covers a gemma failure but not a quota-out; Groq is the quota-out safety net. Its 32k context is enough for the real pipeline (about 3k tokens in) but not for paste-all.
- Adapter rules from S5: `max_tokens` about 3,000 because reasoning tokens count toward it; an empty or length-stopped answer counts as a failure and moves to the next provider; any non-200 moves on.
- Open: the answering model's quality is only checked on 11 questions; the real dev set in Task 15 is the real test. Eval answers on Gemini describe Gemini, not Cloudflare (decide in Plan 2).

## D16. Scale, region and caching choices (2026-10-19)
- **Vector index: optional, with a benchmark. Done (S11):** exact search takes 35 ms at 14,000 pieces and under 1 ms at 229; an index is about 100x faster from 5,000 up, costs about 3.9 KB per row, and needs `ef_search` 100 plus iterative scan because a project filter can return fewer than k rows. Default stays `none`. Original decision: Config switch `vector_index: none | hnsw`, default exact search (229 pieces). A benchmark on about 20,000 synthetic vectors on the test branch shows where an index starts to pay off. Alternatives: always create the index (likely slower or no better at this size, and approximate); never (no story for large docs sets). The `project` column already lets one database hold several docs sets.
- **Render region: Ohio** for the real API (Plan 2), next to Neon (us-east-2). The spike service is in Oregon (read from the owner's dashboard); Oregon to Ohio is an estimated 50-70 ms per round trip, small next to the 22 s cold start and multi-second answers. Alternatives: move the database to Oregon; leave it.
- **Speed and token savings:** provider prompt caching is not worth building (spike S10 maths: input is 15-25% of a question's neurons and only the 60-token system prompt is identical across questions). The levers are answer-side: thinking off (D17), then an exact-match answer cache in Postgres and streaming in Plan 2 once the beta shows repeat rates. Semantic cache rejected for v1 (can return a wrong answer to a different question).
- **Kafka and Redis: rejected.** Nothing streams (one service, about 150 questions a day, ingest by hand) and one instance needs no shared memory; rate limits and the answer cache fit in Postgres. Trigger to revisit Redis: several API instances that must share rate limits or cache, or Postgres counters becoming a bottleneck. Trigger for Kafka: ingest becomes an event stream from many sources with replay and many consumers.
- Owner's reasons: picked the recommended option for each; one-sentence reasons still to be given.

## D17. gemma-4 runs with thinking off by default (spike S10, 2026-10-19)
- Thinking off: 15/15 on the check against 13/15, 57% fewer neurons (205 against 475), 5x faster in total (48 s against 247 s), no empty or cut-off answers. Setting: `chat_template_kwargs.enable_thinking: false` (Cloudflare schema).
- Cost: easier to talk out of the rules by the user's own question (3/3 followed against 0/3). Defence in code, not in the model: an answer is accepted only if it cites a piece we sent or is exactly `NOT_IN_DOCS` (Task 13). The hidden-link weakness exists in both modes and is covered by the link allowlist.
- Alternatives: thinking on (default; slower, costlier, more empty answers); thinking on only as a fallback after a failure.
- **Confirmed by the owner (2026-10-19):** thinking off is the default because the numbers back it ("if the tests show thinking off is better then yes it should be the default as it is backed by the numbers"). Condition kept: the numbers come from 15 questions, so the Task 15 dev set re-checks quality, and the default flips back if it shows worse answers.
