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
- Owner's reason (2026-10-19): keep it simple, and change a choice only if the numbers say otherwise.

## D17. gemma-4 runs with thinking off by default (spike S10, 2026-10-19)
- Thinking off: 15/15 on the check against 13/15, 57% fewer neurons (205 against 475), 5x faster in total (48 s against 247 s), no empty or cut-off answers. Setting: `chat_template_kwargs.enable_thinking: false` (Cloudflare schema).
- Cost: easier to talk out of the rules by the user's own question (3/3 followed against 0/3). Defence in code, not in the model: an answer is accepted only if it cites a piece we sent or is exactly `NOT_IN_DOCS` (Task 13). The hidden-link weakness exists in both modes and is covered by the link allowlist.
- Alternatives: thinking on (default; slower, costlier, more empty answers); thinking on only as a fallback after a failure.
- **Confirmed by the owner (2026-10-19):** thinking off is the default because the numbers back it ("if the tests show thinking off is better then yes it should be the default as it is backed by the numbers"). Condition kept: the numbers come from 15 questions, so the Task 15 dev set re-checks quality, and the default flips back if it shows worse answers.

## D18. Task 15 baseline answers use the user chain, not Gemini (2026-10-19)
- Decision (owner): no Gemini in Task 15. The baseline answers run on the user chain (Cloudflare gemma, then Groq, then Cloudflare llama) under `--max-neurons`, before any beta traffic.
- Why (assistant's reasoning, owner gave no separate reason): the baseline should measure the answers users get; Gemini answers would describe Gemini. Resolves the open item in D14/D15 for Task 15. Gemini stays for the AI judge in Plan 2, on public data only.
- Alternative rejected: build a Gemini provider and run the baseline there (more code, measures the wrong model).
- Cost if wrong: the baseline spends up to 1,500 neurons of the 10,000/day free allocation.

## D19. Plan 2 backend choices (2026-10-20)
- **Access:** invite token per friend, only its SHA-256 hash stored (32 random bytes, so a fast hash is enough). Alternatives: open API with hashed IP (shared IPs share a cap; strangers can burn the global cap); one shared password (no per-person cap; one leak ends the beta).
- **Database access:** `psycopg_pool` with a lazy open and a retried first connect; every failure to reach Neon (at open or later) becomes `DbUnavailable` -> HTTP 503; after a failed retry cycle callers fail fast for 30 s so queued requests do not each wait a full cycle. Alternatives: connection per request + retry (+1.5 s per question); load all pieces in memory (stale until restart, no growth path).
- **Caps and logs:** Postgres tables, caps counted under an advisory lock so parallel requests cannot overshoot. Alternatives: in-memory counters (reset by every Render restart); Redis (rejected, D16).
- **Judge:** built now (Gemini, public data only, reads saved eval results plus the curated question file, never the question log), calibrated later against about 25 hand-graded answers. Alternatives: defer to Plan 3; skip the judge.
- **Owner's reasons (2026-10-20):**
  - Access, invite token per friend: "In the beta an invite token per friend tells us who is using it, rather than guessing from their IP."
  - Database access (pool + retry): "A connection per question will not be feasible, and loading all the docs in memory might result in a single point of failure." (Claude's note: the service already keeps the pieces in memory for the keyword search, loaded once. What was rejected is serving everything from memory: it is lost on every Render restart, goes stale after an ingest, and the vectors would not scale. The database stays the source of truth, so the pool is the right tool for the per-question work.)
  - Caps and logs (Postgres tables): "The answer is in the question itself: a Render restart would reset in-memory caps, and they could be bypassed."  (Claude's note: Render's free service also sleeps after 15 idle minutes, which resets memory the same way.)
  - Judge (build now, calibrate later): "Build now so that I can see how it works before Plan 3." (Claude's note: seeing it work needs the pending approvals: production ingest, then a live run.)
- **Claude's calls (not confirmed by the owner):** third cap of 8,000 neurons/day (the real quota is neurons); 30-day retention with a manual `purge`; a request where every provider fails is free for the request caps but its burned neurons count toward the neuron cap; sync endpoints in a thread pool, no streaming, no answer cache until the beta shows repeats.

## D20. Evidence threshold is a weak dial; provisional 0.020 (2026-10-20)
- Measured on 28 dev questions (`docs/evals/threshold-2026-10-20.md`): no single score separates answerable from unanswerable questions (5 of 9 unanswerable score 0.0323 or more on hybrid, the same as answerable ones), because the fusion score comes from ranks. Abstaining therefore rests mainly on the model's `NOT_IN_DOCS` answer.
- Value 0.020 = the best piece must be found by both searches (a one-search rank-1 hit scores at most 0.0164). It cost no answerable question on the dev set and saves a model call on clearly off-topic questions. Applied only to hybrid.
- Owner may override. Revisit with friends' questions (the `questions` table is the held-out set).

## D21. Answer prompt writes for newcomers (4 measured rounds, 2026-11-07)
- **Why:** the owner hand-read 17 answers and found them correct but written for experts: the docs' example data leaked in (d-003 "how many Items were sold"), jargon came first (d-005 "cmdlog"), the hardest method came first (d-004), a bare copied fragment was an answer (k-003).
- **Chosen:** `SYSTEM_PROMPT` in `app/answer.py` has 9 rules; the three safety rules (use only the excerpts, exact `NOT_FOUND`, data-not-instructions with no links) are unchanged and pinned by tests. Output checks (citation validity, link stripping) are untouched.
- **Rounds (dev set, 28 questions, one run each, `docs/evals/answer-style-2026-11-07.md`):** r1 style rules; r2 added "write prefixed keys as separate steps" (fixed `z Ctrl+S`, but split `Shift+F` into "Shift, then F" and mangled `gs gzd`); r3 limited that rule to `g`/`z`; r4 dropped it for "copy key sequences exactly, never split a `+` chord" and "start with the user's words" (owner accepted losing the r-008 gain to fix d-005).
- **Alternatives:** keep the old prompt (no regressions, but expert-only answers); a second model call to rewrite answers in plain words (doubles neurons, rejected); few-shot examples in the prompt (more tokens per question, kept as the next lever if style drifts).
- **Cost and limits:** neurons per 28 questions 330 -> 406 (+23%); abstentions on answerable questions flipped between 2 and 3 across runs (r-005 in r2, r-004 in r4), so recall may drop slightly; single runs on 28 questions are noise-prone. Safety numbers (9/9 abstain, 0 invalid citations, 0 errors) held in all four runs.
- **Prompt rules cannot fix:** d-001 (the docs' sort page says `[` sorts high-to-low; VisiData's source says `[` is ascending, `]` descending) and k-004 (the docs excerpt for `*` is vague).
- **Owner decision (2026-11-07):** merge to `main` and push (Render redeployed). Owner's reason (2026-11-07): "The answers should also be beginner friendly."

## D22. Human labels mean "true in the real app"; the judge is not trustworthy yet (2026-11-07)
- **Rule chosen by the owner:** `correct` = true in VisiData itself, not merely faithful to the docs text. So d-001 is `wrong` (the answer copies a docs error) and k-004 is `wrong` (too vague to help a newcomer). Owner's reason (2026-11-07): "Docs can be misleading and incorrect, very rarely, and while building we found that, so it is better to give the correct answer if we know it." (Claude's note: this goes beyond grading. If the assistant should give the correct answer, it needs a way to override a wrong docs excerpt, which today rule 1 of the prompt forbids. The safe form is a small hand-written, source-verified correction list in `config/` (each entry: the docs claim, the verified truth, the source checked such as the VisiData file and date), injected as a labelled excerpt so it is cited like any piece. Risks: our own correction can be wrong, so each needs a source and a test; keep the list short; never a copy of docs text. Not built yet; owner to approve.)
- **Result:** Gemini judge said "correct" for all 17 answers; humans marked 2 wrong, so precision 0.88, recall 1.00, with zero cases of the judge ever saying "wrong". A judge that only sees docs excerpts cannot catch a docs error. Treat its "17 of 17" as a rough filter, not a quality score; human grading is the quality check until the judge is tested on known-bad answers.
- **Owner grading slip to remember:** in the v2 round the owner first graded d-001 `correct` (from the docs text) and, when asked, changed it to `wrong`. Labels must be checked against the real app, not the sheet's docs text.
- **Open:** a judge test with deliberately wrong answers; a hand-written correction note in `config/` for the `[`/`]` error (or an upstream report, owner's call); tokens `render-smoke`, `render-smoke2` still active in production.
- **Final decision (2026-11-07, owner):** no correction list for now; the assistant sticks to what the docs say. d-001 stays a known wrong answer (the docs' `[`/`]` error) and is kept honest in the labels, not hidden. Reopen if friends hit it in the beta or the docs are fixed upstream.

## D23. The Gemini judge passes a trap test, but only as a rough filter (2026-11-07)
- **Why:** D22 left one open question: the judge had never said "wrong", so we did not know if it could. Built `evals/judge_traps.py`: 43 items from the 17 hand-graded answers, wrong by construction, so no human grading is needed to know the right verdict.
- **The 43 items:** 15 unchanged good answers (controls), 11 hand-written breaks (near-miss key, flipped side, flipped object, swapped flags, swapped variants, wrong sheet, negation flip, invented key, invented option, one poisoned step, injection note), 8 good answers pasted under another question, 7 vague non-answers, 2 real wrong answers (d-001, k-004; informational, outside the bar).
- **Bar, set before the run:** at least 80% of the 26 traps marked `correct=false`, at most 1 false alarm on the 15 controls, zero judge errors.
- **Gemini (`gemini-3.5-flash-lite`), two full runs:** both identical on all 43 verdicts. 25 of 26 traps caught (96%), 0 false alarms, 3 of 3 invented-content traps flagged ungrounded, injection note ignored. PASS. Missed: `vague:r-009` (a menu-only answer to the theme question).
- **Subagent second opinion (Claude Sonnet, blind: shuffled, no labels, one run):** 25 of 26 caught, 2 false alarms (r-004, d-003) so NOT PASSED on the 1-false-alarm bar. It caught `vague:r-009` but let `hand:10` through (it said the `Ctrl+R` step was invented, yet marked the answer correct). Different strengths, not interchangeable.
- **What it does not show:** both judges said "correct" for d-001 and k-004, so a judge that only reads docs excerpts cannot see a docs mistake or a true-but-unhelpful answer. 26 traps and one or two runs: one miss moves the rate about 4 points. The breaks are crude next to real model failures.
- **Chosen:** keep Gemini as the shipped judge. In Plan 3 `/evals`, label judge numbers as a rough filter for our own wrong or invented content, not a quality score. Human grading stays the quality check.
- **Alternatives:** use the subagent as the judge (rejected: a different model than the one we ship, and it is stricter by about 2 controls); judge only with the subagent plus Gemini agreement (not tried; a possible later tightening); write the traps with an LLM (rejected: the same model family would write and judge).
- **Gotchas found:** the free tier rate-limits calls per minute, so the first unpaced run returned 26 `HTTP 429` errors; `run-gemini` now pauses 6 s between calls and `--resume` redoes only errored items. Errors are never counted as catches.
- **Open:** the subagent's extra disagreements suggest our own labels for r-004 (reference says `g Ctrl+S` to a `.vds` file; the answer describes cmdlog replay) and d-003 (frequency table explained with an unrelated example) may be too generous. Owner to re-check against the real app; if either becomes `wrong`, D22's "15 of 17 correct" changes. Optional: rerun the subagent once to see if its d-003 and r-004 calls repeat.
- **Owner decision:** approved the plan (hand breaks plus script breaks, Gemini plus a subagent). Owner's reason (2026-11-07): "Gemini gives a 3rd perspective because we are not using that model as main or fallback, and for the subagent, since I have a Claude Pro plan it is free and also provides a different perspective as the judge." (Claude's note: the subagent costs no extra money but draws on the Pro plan's usage allowance, about 120k tokens for one run, so it is not unlimited. Gemini being outside the answer chain also keeps the judge from sharing the answerer's blind spots; both points hold.)

## D24. Plan 3 design: a static chat page, public `/evals`, local failure browser (2026-11-08)
- **Design doc:** `docs/superpowers/specs/2026-11-08-plan-3-chat-page-design.md` (10 decisions); Plan 3a (page, feedback, `/evals`, invite links, stored retrieved piece ids) is `docs/superpowers/plans/2026-11-08-plan-3a-chat-page-and-eval-pages.md`; Plan 3b (multi-turn API, follow-up rewriting, failure triage) comes after the beta opens.
- **Shape:** the chat page is a separate static site on GitHub Pages, so it opens instantly while the free API wakes up (cold start measured at 22.9 s). The invite token rides after `#` in the link, so it never reaches a server log. The page has its own safe answer renderer (no HTML from the model is ever inserted). `/evals` is static and public; the failure browser, which shows real questions, stays a local page.
- **`/evals` honesty rules:** every rate shows k/n and a 95% Wilson range; the headline uses the real-question set only; generated questions are a separate group labelled "AI-checked only, not human-checked"; judge numbers are labelled "rough filter, misses docs errors and unhelpful answers" (D23); known wrong answers (D22) are listed, not hidden. Hand grades come from `human-labels-v2.jsonl` (owner, 2026-11-11).
- **Departure from the plan:** local page development uses the `DEV_CORS_ORIGIN` environment variable instead of editing `api.cors_origins`, so the production list never changes and nothing has to be removed before the beta.
- **Alternatives:** host the page on Render with the API (cold start blocks the page itself); a single public eval page that includes friends' questions (rejected on privacy); a model-written `/evals` summary (rejected: numbers must come from code).
- **Open:** Pages must be enabled by the owner (Settings -> Pages -> Source: GitHub Actions); live check of the page against the API is partly done.

## D25. Chat page redesign: warm paper, chat-style feed, a link instead of an embedded video (2026-11-11)
- **Design doc:** `docs/superpowers/specs/2026-11-11-chat-page-redesign-design.md` (mockup beside it); built as Plan 3c (`docs/superpowers/plans/2026-11-11-plan-3c-chat-page-redesign.md`, 5 tasks, native execution on branch `plan-3c`).
- **Why:** the live check showed the page worked but looked like a plain form. Friends who have never heard of VisiData open it on a phone or laptop and it has to feel like the chat apps they know (owner, 2026-11-11: it should say "a nice, fun chatbot, built for VisiData, answers only about VisiData", with a place to learn what VisiData is).
- **Owner's choices:** warm paper look; a dark mode; both computer and phone layouts designed; even buttons (one recipe) and equal-size starter cards; a bigger, centred typing box; links to visidata.org and to an intro video; the line "Answers only from the VisiData docs".
- **Calls (builder, owner can override):**
  - Dark mode starts from the device setting; a moon/sun button flips it and remembers the choice on that device (`localStorage`, wrapped so blocked storage still works). A tiny external script in `<head>` applies it before first paint, so no inline script is needed and the content-security rules stay exactly as built.
  - `/evals` follows the device setting only (no script, no button); a visitor who picked light on the chat page may see a dark `/evals`. Accepted.
  - The video is a link, never an embedded player: an embed loads third-party code, which would break the no-third-party rule. `intro_video_url` is optional config; no official URL is confirmed yet, so the button is left out until the owner supplies one.
  - Chronological feed with the visitor's bubble on the right; Enter sends on a computer, Shift+Enter adds a line, on touch Enter adds a line; Ctrl/Cmd+Enter always sends; the box grows to about 8 lines.
  - The light accent is `#a8472a`, not the mockup's `#c4623c`: the mockup colour is 3.7:1 as link text and fails the 4.5:1 reading bar. Every text pair is tested in both themes.
- **Alternatives:** an embedded video player (rejected: third-party code); a theme button only, with no device setting (rejected: a dark-mode device would flash light); a single shared stylesheet scope (rejected: chat rules are all scoped to `body.chat` so `/evals` gets only the palette).
- **Unchanged on purpose:** the answer renderer and its hostile-input tests, token handling, banner kinds, request timeout, API and stored data.
- **After the live check (owner, 2026-11-11):** the owner tried it for real: one specific question answered well, but broad ones ("how do I use visidata", "what is visidata") and a follow-up ("what else can I do?") were refused. Saved rows showed why: "how do I use" scored 0.016, under the 0.020 gate (no model call); "what is visidata" passed the gate but the docs folder holds no sentence that says what VisiData is (that text is on the website's front page, which is not ingested); a follow-up has no memory (Plan 3b). **Done on this branch:** a "New to VisiData? Start here" row (website, intro video, the docs' Getting Started page) under every refused question, the video set to the demo the docs' own Getting Started page links (`https://youtu.be/N1CBDTgGtOU`, owner's choice), and an in-feed "thinking" line (pulsing dots, honest label, moves only `transform` and `opacity`) instead of a banner box. **Not done, owner's call:** feeding the website's front page to the model so broad questions get a real answer (needs a second ingest source and changes the 'only from the docs' promise; see the open question in CLAUDE.md).
- **Open:** the website-as-source question above; the cold-start banner still unseen against a sleeping server.

## D26. About and Help cards: a model classifies every question (2026-11-11)
- **Design and plan:** `docs/superpowers/specs/2026-11-11-about-and-help-cards-design.md`, `docs/superpowers/plans/2026-11-11-plan-4-about-and-help-cards.md` (6 tasks, native execution on branch `plan-cards`).
- **Why:** the first live check showed that newcomers' first questions ("what is visidata", "how do I use visidata", "what can you do") were refused: the docs folder has no sentence that says what VisiData is, and broad questions score under the evidence gate. Owner's wish (2026-11-11): "a short plain explanation with links" for those, written by us, plus an answer to "what can you do".
- **What it does:** a small model call labels every question `about`, `help` or `normal` before the normal search. `about` and `help` show a fixed card whose text lives in `config/visidata.yaml` (`site.cards`); `normal` goes through search and answer exactly as before. Cards are labelled "written by us, not from the docs", so the docs-only promise for model answers is unchanged. A card reply skips the docs search, so it works even when the server has just woken up.
- **Owner's choice, against my recommendation:** the model classifies **every** question. I recommended classifying only questions that would otherwise be refused (no extra delay or risk for answers that already work). The owner chose every question; the cost is one extra short model call per question.
- **Fail-open rule:** a classifier error, timeout or any reply that is not exactly one label means `normal`. A failing classifier never shows an error to the visitor and never shows a card on a guess.
- **Caps (my call):** card replies count against the visitor cap and the shared request cap, and their neurons count toward the daily neuron budget. Reason: an uncounted card path would let one invite spend the free budget by repeating "what can you do". Cost: exploring the cards uses some of a friend's 10 daily questions.
- **Logging:** card rows are saved with `status = "card"`, `answer_text = "card:about"` or `"card:help"`, their neurons and call count, and no retrieved pieces. A normal question's `llm_calls` and `neurons` now include the classifier call, so the neuron cap sees the true spend.
- **Test result (2026-11-11, production chain, Cloudflare gemma, 62 questions):** 62 of 62 routed correctly: 12/12 about, 12/12 help, 38/38 normal (19 hand-written, including traps like "what is a frequency table" and "what does the help key do", plus the 19 answerable dev questions). 0 real questions sent to a card (bar: 0); 24/24 phrasings reached the right card (bar: 90%). Cost: 85.95 neurons for 62 calls (about 1.4 each, against about 400 for a full answer). Time: median 0.61 s per call, but one call took 14.7 s.
- **What this does not show:** the test set was written by the same person who wrote the prompt, so it is friendlier than real friends' wording; 62 questions is small; one slow call shows the delay can occasionally be long, and the classifier has no shorter timeout than the answer call. Real friends' questions in the beta are the held-out check: add any misrouted question to `evals/data/cards.jsonl` and rerun (about 90 neurons).
- **Alternatives (not built):** phrase lists in config (free, instant, misses unusual wording); classify only refused questions (no risk to working answers; recommended, not chosen); matching in the browser (fast, but those questions are never logged).
- **Open:** whether the occasional slow classifier call matters in practice (a per-call timeout on the classifier would fix it); the website-front-page-as-a-source idea is dropped in favour of fixed cards.

