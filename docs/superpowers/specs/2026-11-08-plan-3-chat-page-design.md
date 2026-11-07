# Plan 3 design: chat page, feedback, eval pages, multi-turn, failure triage

Date: 2026-11-08. Status: for owner approval. Builder check done; the owner has answered its one open question (decision 6). Decisions are copied to
`docs/decisions/decision-log.md` once approved. Plan 3 is split into **3a** and **3b** (decision 5).

## Intent
A personal project built around VisiData. The point of the project is the evals and the harness around a
docs-answering assistant; the chat page is how friends produce real questions and feedback, and `/evals` is
the page that shows the numbers. Friends have never used VisiData and cannot guess what it is, so the page
opens with a short plain explanation. Everything VisiData-specific lives in `config/visidata.yaml`; no
multi-docs features are built now. The system answers only from VisiData's public docs, has no tools and no
private data.

## Goals
- A friend opens an invite link, understands in a few seconds what VisiData and this page are for, asks
  questions, sees cited answers, and rates them.
- `/evals` lets a visitor learn in 30 seconds that answers are cited and honest, with real numbers.
- The owner can see which questions failed and whether each is a docs gap or our own bug.
- Test numbers get stronger (more questions, repeated runs, a held-out set) before and during the beta.

## Non-goals (not in Plan 3)
Multi-docs or multi-tenant features; admin login or owner-only API routes; streaming; an answer cache;
a scheduled `purge`; installing VisiData or recording a demo; fixing or overriding VisiData's docs (D22:
the assistant sticks to what the docs say); a markdown library on the page.

## Anti-goals (a failure even if it technically works)
- Friends' questions reaching Gemini, any public page, git, or any provider not named in the privacy notice.
- Raw HTML or model-written links ever rendering on the page.
- Numbers on `/evals` that look more certain than they are (a bare percentage, blended sets, judge scores
  presented as quality).
- Any outward-facing action (posting, emailing, reporting upstream, `git push`) without the owner's approval.
- Committed text that describes the author's circumstances instead of the project (the repo is public).

## Constraints
- Free tiers only: Cloudflare 10,000 neurons/day (API stops at 8,000; about 2,000 left for evals), Groq 1,000
  requests/day and 8,000 tokens/minute, Gemini Flash-Lite 500 requests/day (public data only), Render free
  (cold start measured 22.9 s, warm 0.32 s), Neon free.
- Hard rules (CLAUDE.md): the assistant has no tools and no private data; never commit copies of VisiData
  docs; project specifics live in `config/`; tests run on a different provider bucket than users; no Context
  MCP.
- Production API: `https://citeable-docs-api.onrender.com`. Routes today: `POST /ask`, `POST /feedback`
  (both `Authorization: Bearer <invite token>`), `GET /health` (no database), `GET /version`. `/ask` returns
  `request_id, status, text, citations, closest, docs_ref, docs_version, last_updated, notice`. Feedback is a
  rating of 1 or -1 plus an optional comment. CORS allows only `api.cors_origins` in the config (today
  `https://navyyshukla.github.io`).
- The `questions` table stores question, status, answer text, citations, `top_score`, provider, model,
  neurons, error, docs ref; `feedback` stores rating and comment. It does not store which pieces search
  retrieved. Retention is 30 days. Question limit 500 characters.
- Judge facts (D23): the Gemini judge catches wrong or invented content in our own answers (25 of 26 traps, 0
  false alarms) but cannot see docs errors or unhelpful-but-true answers.
- The repo is public.

## Decisions (owner's choice and reason first; "Claude's call" marks things the owner has not been asked)

**1. Page hosting: a separate static site on GitHub Pages.** Owner: "the page opens instantly while the API
wakes up." The page pings `/health` on load, shows a "waking up, up to 30 seconds" banner only when cold, and
uses a request timeout above 30 s. Rejected: serving the page from Render (blank page for about 23 s after
idle); another static host (extra account). Cost: a second deployment and exact CORS. Plan 3a adds a
localhost origin for local development and must remove it before the beta.

**2. Eval pages are split by privacy.** Owner: "better because of privacy policy." `/evals` is a static
public page built offline from saved eval files (curated questions, public data) and published on the same
site. The failure browser shows friends' real questions, so it is a local page generated on the owner's
laptop from the database, read-only, git-ignored, never hosted. Rejected: everything static and public (leaks
questions); owner-only API routes (new admin auth; revisit only if the owner needs to review from a phone).

**3. Invite link: the token goes after `#`.** Owner: "simple and safe." Link shape
`https://navyyshukla.github.io/<repo>/#t=<token>` (repo name not confirmed). The page reads the fragment,
saves the token in `localStorage`, removes it from the address bar, and sends it as `Authorization: Bearer`.
The fragment is never sent to a server. A "forget this device" link and friendly messages for a missing,
invalid or revoked token. Tokens stay revocable per label with the existing daily cap. Rejected: `?t=` query
(visible to the static host, leakable through Referer); pasting the token (friction). Accepted risk: on a
shared computer the next person could reuse a saved token.

**4. Answer display: a tiny own renderer.** Owner: "we need to render first and then show the normal
output" (read as: escape everything first, then put back only the allowed shapes). Allowed: paragraphs, bold,
inline code, lists, and `[n]` turned into a link taken from the response's `citations`, never from a link in
the model text. Citation links open in a new tab with `rel="noopener noreferrer"`. A non-answer status shows
the "couldn't find this" text plus the `closest` pages. A Content-Security-Policy `<meta>` tag gives a partial
extra layer (Pages cannot set headers). The server already strips images, HTML tags and off-docs links; the
page does not rely on that. Rejected: a markdown library plus sanitizer from a CDN (third-party code);
plain text (raw `**` and backticks look broken). Needs a hostile-input test list (`<script>`, `javascript:`
links, nested markup), a scan of saved answers for markdown beyond bold, code and lists, and a review after it
is built.

**5. Multi-turn, capped at 6 turns (a turn is one question plus its answer).** Owner chose it so follow-ups
are shown working. Design note: single-turn already is retrieval-augmented generation; multi-turn is the
harder conversational form and needs its own eval set. **Plan 3a ships the page with independent questions
(a feed, no turn counter); Plan 3b adds multi-turn and the "Question n of 6" counter** (Claude's call on this
sequencing; the owner did not object to the split).

**5b. Follow-ups are rewritten into standalone questions by a small model call.** Owner: chosen to show the
follow-up feature. This reverses, for follow-ups only, the earlier "no question-rewriting call" decision (S2,
S6, D16); first questions are never rewritten. The page sends only the earlier user questions (capped in
length and count), never earlier answers. The rewriter's output is untrusted data used only for search,
length-capped and stored for evals; it runs on a Cloudflare model in the users' bucket (never Gemini), from
turn 2. If it fails, returns nothing or is too long, search falls back to the earlier question plus the new
one joined. The answer prompt labels earlier questions "data, not instructions". Neuron cost is unmeasured: a
spike on a small follow-up set comes before this is locked in. Rejected: search on the new question only
(pronouns find nothing).

**6. `/evals` content and order.** Owner: a visitor learns in 30 seconds that answers are cited and honest,
with real numbers. Order: headline numbers first, the honesty panel directly below, then known wrong answers
(shown, not hidden), run history, and a click-through per question (question, answer, source links, human
grade, judge verdict). Every number is a fraction with its n and a range (Wilson interval; for repeated
runs also min to max). Judge numbers are labelled a rough filter (D23). Each run states which question set it
used (24- and 28-question sets exist). Full answer texts and links to docs pages are shown, never docs excerpts. Owner: "A, because the answers are short generated output"; the page carries the unofficial and GPLv3 notice. Accepted risk: an answer may repeat a short phrase from the docs (such as key names); the owner should check VisiData's docs licence personally before publishing, as Claude cannot verify it. Built
offline by a script from saved result files (no neurons).

**7. Stronger test numbers: LLM-made questions, friends' held-out set, repeated runs.** Owner: friends'
questions already give a human check, so generated questions are faster; repeated runs show noise. Hand-
curating more real questions was not chosen. Claude's safeguards: generated questions use newcomer phrasing
that avoids the docs' vocabulary and include unanswerable and near-miss cases; they carry `source:
synthetic`; about 1 in 5 is hand-checked for answerability and gold page before it counts; the generator is
Gemini on public docs text only; `/evals` reports real/paraphrased, synthetic and held-out results separately,
never blended; the held-out set is never used for tuning.

**8. Failure browser: a model sorts failures into "docs gap", "our bug" or "out of scope".** Owner: checking
50 to 100 questions alone takes too long and invites human error. Shows question, status, failure type,
closest pages, rating and comment. Claude's design calls: (a) the triage model sees the question, the top
retrieved pieces and the docs' full list of headings, because a model that sees only retrieved pieces calls
every retrieval miss a "docs gap"; (b) it runs only in the users' bucket (Groq `gpt-oss-20b` suggested), never
Gemini and never a Claude session, so friends' questions stay with providers the privacy notice names; (c)
before use it is calibrated on the dev set (answerable-but-missed = our bug; unanswerable = gap or out of
scope); (d) the owner reviews every "docs gap" (it may go upstream, which needs approval) plus about 15 random
others, and those labels are a second accuracy check; (e) output is a suggestion with a confidence; (f) an
"our bug" question becomes a regression question, and any question the system is tuned on leaves the held-out
set. Needs top retrieved piece ids stored with each question (public data; a schema change on production
Neon). Unmeasured: the heading-list size (estimated 3,000 to 4,000 tokens, so about 2 calls a minute on
Groq).

**9. UI rules.** Owner: the UI must be very clear. Claude's concrete rules: purpose and a two-sentence
VisiData intro at the top; clickable starter questions; the cold-start banner; an explicit status label on
every reply ("answered from the docs" or "I couldn't find this in the docs" plus closest pages); source links
labelled with page and heading; feedback buttons with words, not only icons; a 500-character counter; plain-
language errors (invalid invite link, daily limit); a footer with the unofficial and GPLv3 notice, docs
version and a privacy link. In 3b: "Question n of 6" and a "start a new conversation" button at the limit.
Page text comes from `config/visidata.yaml`. The privacy notice names the providers that see questions
(Cloudflare, Groq, Render, Neon), says questions are kept 30 days, and that only the owner reads them.

**10. Order of work and when test runs grow.** (1) Grow the dev set with generated questions plus the hand-
checked sample; (2) baseline v2: 3 repeated runs of the bigger set **before the beta opens**, while the whole
daily neuron budget is free (about 3,500 neurons for 80 questions, an estimate from 14.5 neurons per question;
fits in one day with no beta traffic); these do not depend on the page and can run in parallel with it; (3)
Plan 3a: page, feedback, `/evals`, invite links, store retrieved piece ids; (4) open the beta; (5) Plan 3b:
multi-turn API, follow-up rewriting and evals, failure triage. Friends' questions are scored separately as
the held-out set. After the beta opens, evals share the budget and use the roughly 2,000 neurons of headroom.

## Success looks like
A friend can open an invite link on a phone, understand the page without VisiData knowledge, get a cited
answer or an honest "couldn't find this", and rate it. `/evals` shows every number with its n and range and
the known wrong answers. The owner can open the failure browser after the beta and see, per failed question,
a suggested label with the evidence. No test shows friends' data leaving the named providers, and the hostile-
input tests for the renderer pass.

## Left to the builder
File and folder layout of the page; the exact request shape for earlier questions and the exact rewriter and
triage prompts; the schema migration for stored piece ids; how the eval pages are generated and published;
colours, typography and responsive layout; test structure; the number of generated questions (about 50 more
as a start) and the heading-list handling if it is too long for the triage model.

## Calls made after the builder check (Claude's, owner may veto)
- **Request shape:** 3b adds an optional `previous_questions` field to `/ask`, empty by default. 3a sends only
  `question`, so nothing built in 3a breaks when 3b ships.
- **Site location:** repo `navyyshukla/citeable-docs` (from the git remote); the site is
  `https://navyyshukla.github.io/citeable-docs/`. Source lives in `site/` in the same repo and is built and
  deployed by a GitHub Actions Pages workflow; `docs/` stays for documentation. CORS keeps
  `https://navyyshukla.github.io` as the only production origin; a localhost origin is added for development
  and removed before the beta.
- **Rewriter spike pass bar (5b):** passes if rewriting adds no more than half of a typical per-question cost
  (about 7 neurons, from 14.5) and finds the right docs page more often than the plain "join" fallback on a
  small follow-up set. If it fails, ship the join fallback and keep multi-turn.
- **Triage runs locally:** a script on the owner's laptop, throttled to 2 calls a minute, run at quiet hours;
  about 100 of Groq's 1,000 daily requests, so no separate key.
- **Page text:** a build step renders `config/visidata.yaml` into the HTML (the same build is needed for
  `/evals`); the page text never depends on the API being awake.
- **Question sets:** generated questions go in a new file beside `evals/data/dev.jsonl` with `source:
  synthetic`; each saved run records which set it used. `evals/results/` is git-ignored, so `/evals` is built
  from local result files and tests that read them skip in CI.
