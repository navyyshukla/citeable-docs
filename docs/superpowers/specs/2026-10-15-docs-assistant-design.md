# Citeable Docs — Design Spec

Status: DRAFT for review. Written 2026-10-15. No code exists yet.
Owner: the project owner. Code is written by Claude Code; the owner decides and must be able to explain every decision.

---

## 1. What we are building (one paragraph)

An **unofficial, free "Ask the docs" assistant** for the open-source tool **VisiData**. A visitor asks a question; the assistant finds the relevant pieces of VisiData's documentation, answers **only from those pieces**, shows **citations** (page + heading + docs version/date), and says **"I couldn't find this"** (plus the 3 closest pages) when the docs don't cover it. The project also publishes a **public scoreboard (/evals)** showing measured quality, a **failure browser**, and a **decision log**. It is built as a reusable **engine**; VisiData is the first (and in v1 only) project, defined by a config file.

## 2. Why this project (purpose and honest framing)

- **Primary purpose:** a live, measured, explainable product: a documentation assistant whose answer quality is measured and published.
- **Not the purpose:** novelty (RAG docs assistants and CI-failure explainers are both saturated), or large VisiData impact (its community Q&A is low-volume; newest Discussion seen was dated 2026-07-17).
- **What makes it stand out (if we execute):** real data, measured quality following the Claude docs "develop tests" principles, an honest public scoreboard, an incident log, and every decision written with alternatives.
- **Known limit:** RAG docs assistants are common, so the value is in the measured, published quality, not in the idea.

## 3. Users and where they use it

| Audience | What they do | Where |
|---|---|---|
| VisiData users (small, slow) | Ask "how do I…?" | Public web page |
| People the owner knows (5–10) | Try the beta, give thumbs up/down | Same page |
| Engineers reviewing the project | Try it, read /evals, the decision log, README | Same site + GitHub repo |
| Other OSS maintainers (LATER, not promised) | Copy the repo, point config at their docs | GitHub |

## 4. Scope

**In v1:** chat page; answers with citations; strict abstention + closest pages; daily caps; thumbs up/down; question logging; eval runner + CI gate; public /evals scoreboard (week 3); failure browser (week 3).

**Not in v1:** accounts/login; file uploads; any tool use/agents/actions; Discord/Slack bots; browser plugin; multiple live projects; custom domain; fine-tuning; paid services of any kind.

**Hard rules:**
1. Everything runs on free plans with no card. The only paid item is the owner's existing Claude subscription (used for Claude Code and subagent runs).
2. The assistant has **no tools and no private data**.
3. We **never commit copies of VisiData's docs** (GPLv3 project). Ingest from upstream; store text only in the database.
4. Anything specific to VisiData lives in `config/`, not in code.

## 5. Architecture

```
 VISITOR ──▶ Next.js static site (GitHub Pages)
                  │  question
                  ▼
        FastAPI app (Render free)
          1. input check + daily caps
          2. FIND pieces   (search mode is a setting: paste-all | keyword | meaning | hybrid)
          3. ASK model     (through our adapter: main + 2 fallbacks)
          4. output check  (only allowlisted citation links survive; no images)
          5. log row
                  │
                  ├──▶ Neon Postgres + pgvector (pieces, vectors, logs, feedback, eval results)
                  └──▶ AI providers via adapter: Cloudflare Workers AI (main), 2 fallbacks

 CI (GitHub Actions): lint + tests + dev-set eval (budget capped) → deploy → publish /evals
```

## 6. Components

| Component | Does | Depends on |
|---|---|---|
| `ingest/` | Fetch docs from VisiData **`stable` branch / release tag** → clean → cut by headings → embed → store | config, embeddings API, DB |
| `app/search` | Return top pieces for a question; modes: paste-all, keyword (symbol-safe), meaning, hybrid | DB |
| `app/llm` (adapter) | One interface to all providers; fallback order; neuron/token accounting; caps | provider keys |
| `app/safety` | Input limits, caps, prompt/format rules, output link allowlist | — |
| `app/answer` | Build prompt from pieces; abstain below evidence threshold; attach citations + version | search, llm, safety |
| `web/` | Next.js (App Router, TypeScript) static export: chat page, later /evals + failure browser | API |
| `evals/` | Dataset (JSONL), runner, judge prompt, results JSON | app, judge model |
| `config/visidata.yaml` | Source URL/branch, version, doc→URL mapping, caps, thresholds | — |
| `docs/decisions/` | One file per decision | — |

Core is **thin, hand-written Python**. Libraries only for commodity parts (Markdown parsing, Pydantic, pytest, HTTP client). LlamaIndex/LangChain are **not** used (see decisions).

## 7. Data and ingestion

- **Source:** VisiData repo, `stable` branch or release tag. **Not `develop`** (develop was observed ahead of the published site).
- **Cleaning:** strip front-matter, HTML/JS blocks (demo players), template placeholders (e.g. `{help.commands.…}`); keep tables together with their header row.
- **Cutting:** by headings, keeping the heading path ("Columns › How to format columns › …"); very long sections get a second split.
- **Per piece we store:** text, page URL, heading path + anchor, docs version, "last updated", embedding.
- **Anchors:** some headings have custom ids (`{#expand}`); anchor generation must handle both.
- **Staleness:** pages show their last-updated/version; answers display it and flag old pages (e.g. written for v2.x while current is v3.4).
- **Open item:** the command reference ("man page") may hold many "what does key X do" answers. v1 = docs only; revisit after the first eval run.

## 8. Search

- Four modes behind one switch; **measured, then the winner is kept**: paste-all baseline (~35k tokens, run once and cached), keyword, meaning (embeddings), hybrid (fusion).
- **Symbol-safe keyword path required:** single-key commands (`&`, `!`, `(`, `=`) must be findable; default tokenizers/full-text search probably drop punctuation (unverified → spike).
- Embedding model chosen by a **retrieval-only test** (does the right piece appear in the top 5?), not by price. Model name lives in config; changing it means re-embedding (cheap here).

## 9. Answer behavior and safety

**Behavior contract:** answer only from retrieved pieces; every claim cited; show docs version/date; if evidence is below threshold → "I couldn't find this in the VisiData docs" + 3 closest pages + link to VisiData GitHub issues.

**"Enough evidence" = a rule on the search score**, tuned on the dev set (a dial: answers more vs wrong more). /evals reports both "answered %" and "wrong when answered %".

| Risk | Defence |
|---|---|
| Prompt injection (user text or docs text) | No tools, no private data, retrieved text treated as data |
| Link/image exfiltration | Output check: only links from retrieved pieces survive; images stripped; frontend renders markdown with a safe renderer, never raw HTML |
| Burning the free quota | Max question length, max answer length, per-visitor and global daily caps (illustrative: ~150–200/day global, ~10/visitor; set after measuring real cost) |
| Others calling our API | CORS allowlist for our site + caps |
| Leaked keys | Keys only in Render/GitHub secrets; secret scanning |
| Privacy | Notice on page, no accounts, no raw IPs stored, short retention |
| Harmful advice | Docs link next to every command; note for save/overwrite commands |

Privacy and licensing notes are practical, not legal advice.

## 10. AI models

- Adapter with ordered providers: **1 main + 2 fallbacks** for answering, plus **1 judge from a different model family** that never answers users.
- **Every model that can answer users is scored** on the same test set.
- Main candidate: Cloudflare Workers AI. Fallback candidates: Gemini free, Groq free (limits visible only in the user's account; not guaranteed). Specific models set after checking the accounts.
- **Free quota facts (verified from official pages, 2026-10-14/15):** Cloudflare Workers AI 10,000 neurons/day free, resets 00:00 UTC; OpenRouter `:free` = 20 req/min, 50/day (1,000/day only after buying ≥$10 credits → excluded); Gemini and Groq free limits not published in docs.
- **Estimates (not measurements):** ~23 neurons/question for an 8B model with 3k tokens in / 300 out → ~430 questions/day; paste-all ≈ 155 neurons. Log **model calls per question** and fail CI if ≠ 1.
- **Unverified:** behavior when the Cloudflare free allocation is exhausted (error vs charge) — confirm before the first large test run.
- Stay on Free plans; add no payment method.
- Cloud-only evals (a local model measures a different model than users get). A local model is optional for "does it run" smoke tests only.

## 11. Evaluation (roadmap: Claude docs "Define success criteria and build evaluations")

Principles adopted: task-specific, automate when possible, prioritize volume over quality, code > LLM > human grading, rubric + constrained output + reasoning, different model for grading.

| Criterion (doc category) | Measure | Grader |
|---|---|---|
| Relevance | Right piece in top 5 (hit@5) | code |
| Context utilization / grounding | Claims supported by retrieved pieces | LLM judge |
| Task fidelity | Answer matches reference | LLM judge |
| Citation validity | Every cited link ∈ retrieved set | code |
| Abstention | Says "I don't know" on unanswerable | code + rule |
| Consistency | Same answer across paraphrases (small set) | code/embedding similarity |
| Latency | seconds incl. cold-start note | code |
| Price | neurons/answer, calls/question | code |
| Privacy | no personal data persisted (basic) | code review |
| Tone/style | skipped in v1 | — |

**Test set (~100, source-labeled):** ~40 real (from past issues/Discussions with maintainer answers), ~30 doc-based (synthetic, easy), ~20 unanswerable, ~10 tricky/off-topic. Each: question, gold page+heading, short reference answer, answerable flag, source link or "synthetic"/"agent-made". Mix is a suggestion; real-question availability needs a mining spike.
**Splits:** dev (~30, tuned against) vs held-out (~70, never tuned against).
**Judge calibration:** owner hand-grades ~25 answers; judge is trusted only if precision/recall against those labels is acceptable (threshold set at calibration time). Agent-generated questions are labeled and reported separately.
**Targets:** defined as numbers after the first baseline run and before tuning (not invented now).
**Reporting rules:** show counts (87/100) not just %; differences smaller than the noise (~±7 pts on 100, ~±12 on 30, rough normal approximation) are not claimed as improvements.
**CI:** dev set on every PR with a hard neuron-budget stop; full set nightly/manual (scheduled-run behavior on inactive public repos to be checked).
**Views:** /evals scoreboard (per search mode and per model, trend over runs) and a failure browser (question, found pieces, answer, judge reason).

## 12. Frontend

Next.js (App Router, TypeScript), **static export** (`output: 'export'`) hosted on GitHub Pages (project-site `basePath` config). Unsupported in static export: server actions, cookies, rewrites/redirects/headers config, default image optimization, ISR. Vercel Hobby (free, non-commercial) is a fallback host if server rendering is ever needed. Beta = one chat page with "waking up…" state, thumbs up/down, version/date display. /evals and failure browser follow in week 3. Raw HTML rendering is banned.

## 13. Hosting and operations

| Part | Choice | Verified terms | Weakness |
|---|---|---|---|
| API | Render free web service | spins down after 15 min idle, ~1 min wake, 750 free hrs/mo; no card → suspended not billed | cold start |
| DB | Neon free | 1 GB, 100 CU-hrs, suspends after 5 min idle, pgvector included, no card | idle latency |
| Frontend | GitHub Pages | free | — |
| CI | GitHub Actions | free for public repos | eval runs use AI quota |
| Tracing | own Postgres tables (v1); Langfuse Hobby optional later | Hobby: 50k units/mo, 30-day retention, 2 users | 30-day history |

Rejected: Hugging Face Spaces (Docker/Gradio need a paid plan), Render free Postgres (expires after 30 days), Supabase free (pauses after 1 week idle; pgvector unconfirmed).
Cold start handling: friendly UI state first; a keep-alive ping (~720 of 750 hrs) only if real use justifies it.

## 14. Repo layout and licensing

```
docs-assistant/
├─ app/  ingest/  evals/  web/  config/  docs/decisions/  .github/workflows/  README.md
```
Our code: **MIT**. No copies of VisiData docs committed. Decision log: one file per decision (context, options, choice, why, what would change our mind). The project folder is currently **not a git repository**; `git init` is needed before commits.

## 15. Working agreement with Claude Code (how the owner stays the driver)

1. Before any implementation task, Claude states: approach, 2–3 alternatives with trade-offs, recommendation, and what the owner should study. Owner picks and writes one sentence why → decision log.
2. The owner writes (or approves line by line) acceptance criteria and the eval questions; Claude does not define "correct" alone.
3. Claude must show evidence for claims (a failing/passing test, a measured number), not assertions.
4. Owner override list: cost/quota, data/privacy, security, irreversible actions, anything the owner can't explain back.
5. Owner may accept without long debate: boilerplate, formatting, conventional library usage.
6. Independent checks: fresh-context subagents as (a) new-user tester, (b) cold reviewer of spec/README/code, (c) red team. They are dev-time only (they use the owner's Claude plan, cannot run in public CI), share Claude's blind spots, and their output is a second opinion, not proof.
7. Standing rules: simple language, text diagrams, study links with purpose, push back with reasoning.

## 16. Milestones (target; cut scope before dates)

| When | Deliverable |
|---|---|
| Week 0 | Spikes (see §17) and account checks (Cloudflare exhaustion behavior, Gemini/Groq limits) |
| Week 1 | Ingestion; paste-all baseline; keyword + meaning + hybrid; adapter; first eval run on dev set; judge calibration begins |
| Week 2 | API with safety + caps; Next.js chat page; deploy; **public "unofficial beta" launched** with daily cap |
| Week 3 | /evals scoreboard; failure browser; feedback; incident log; first build-log post |
| Week 4+ | Second model scoreboard; Langfuse (optional); second project via config (optional); React/other polish |

**Beta quality bar (minimum):** every answer shows a valid citation; abstains on unanswerable questions at an acceptable rate (set after baseline); caps work; no raw HTML rendering.
**Beta usage goal (suggested):** ≥30 real questions from ≥5 people and ≥3 documented failures with fixes in the first 3 weeks.

## 17. Open items, spikes and risks

Spikes (before locking §7/§8):
1. Compare `stable` Markdown vs published pages for 3 pages; locate the command reference.
2. Symbol queries ("what does & do?") under each search mode.
3. Mine past issues/Discussions: how many have a clear maintainer answer?
4. Cold-start and memory on Render free with our dependencies.

Risks (in order): getting any real usage; judge reliability; free-tier changes; capacity (TypeScript + Python + evals); stale or incomplete docs; Cloudflare quota-exhaustion behavior unverified.

Open decisions: which two fallback models; embedding model (by retrieval test); evidence threshold (by dev set); exact caps; retention period.
