# Plan 3a: Chat Page, Feedback, Eval Pages and Stronger Test Numbers — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the friends' chat page (static, on GitHub Pages) and the public `/evals` page, store what search retrieved for each question, and grow and repeat the eval runs before the beta opens.

**Architecture:** A static site (`site/`, plain JS modules, no framework, no third-party scripts) calls the existing Render API with the invite token. A Python build script renders the page from `config/visidata.yaml` and builds `evals.html` offline from local, git-ignored result files; the generated `evals.html` is committed after the owner reviews it. A GitHub Actions workflow deploys `_site/` to Pages. Eval code gains interval maths and a question generator.

**Tech Stack:** Python 3.12 (FastAPI, pydantic, pytest, ruff), plain ES modules tested with `node --test` (Node 22 in CI), GitHub Actions Pages.

**Spec:** `docs/superpowers/specs/2026-11-08-plan-3-chat-page-design.md` (decisions 1 to 4, 6, 7, 9, 10 and "Calls made after the builder check"). Multi-turn, follow-up rewriting and failure triage are **Plan 3b**, not here. Earlier plans: `docs/superpowers/plans/2026-10-20-plan-2-api-safety-beta.md`.

## Global Constraints

- Free tiers only. Cloudflare 10,000 neurons/day (API stops at 8,000; about 2,000 left for evals). Groq 1,000 requests/day, 8,000 tokens/minute. Gemini Flash-Lite 500 requests/day, **public data only: no user question ever goes to Gemini**.
- The assistant has no tools and no private data. Never commit copies of VisiData docs. VisiData specifics live in `config/visidata.yaml`.
- The page never renders raw HTML or a link that is not in the response's `citations`. Escape first, then put back only: paragraphs, bold, inline code, lists, `[n]` links.
- Invite link: `https://navyyshukla.github.io/citeable-docs/#t=<token>`; the token is never in the path or query. Production API `https://citeable-docs-api.onrender.com`; cold start measured 22.9 s, so request timeout is above 30 s (use 45 s).
- Max question 500 characters. Privacy notice says questions are kept `limits.retention_days` (30) days and names Cloudflare, Groq, Render and Neon.
- `/evals`: every number is a fraction with its n and a 95% Wilson range; real/paraphrased, synthetic and held-out sets are reported separately, never blended; judge numbers are labelled a rough filter (D23). The 24- and 28-question sets both exist: each run states its set.
- Ask the owner before every `git push`, every Gemini or Cloudflare run, enabling GitHub Pages, and anything outward-facing. Committed text stays neutral: it describes the project, never the author's circumstances; scan the diff before every push. Never print `.env` values.
- `evals/results/` is git-ignored: tests that read it must skip when absent.

## Review Focus

1. Answer text with `<script>`, `<img onerror>`, `[x](javascript:...)`, `&lt;` entities, or `[99]` with no such citation → nothing executable or linkable; unknown `[n]` stays plain text (Task 5).
2. Invite link missing, truncated, in the query string instead of the fragment, or storage unavailable (private window) → clear message, no crash (Task 6).
3. Server asleep 25 s, then 401, 429 or 503 → plain-language message, input kept, button re-enabled (Tasks 6, 7).
4. Question empty, whitespace only, exactly 500, 501 characters → button and counter behave (Task 7).
5. `/evals` with zero runs, n = 0, a run with errored rows, labels missing → no division by zero, no crash, honest "no data" (Tasks 3, 8).
6. Config text containing `<`, `&`, quotes → escaped in the built page (Task 7).

## File Structure

| Path | Responsibility |
|---|---|
| `app/usage.py`, `app/service.py` | Store retrieved piece ids per question (Task 1) |
| `app/config.py`, `config/visidata.yaml`, `app/api.py`, `app/cli.py` | `site:` config, dev CORS env var, invite-link printing (Task 2) |
| `evals/stats.py` | Wilson range, fraction formatting, min/max across runs (Task 3) |
| `evals/generate.py` | Generated question sets and the hand-check sheet (Task 4) |
| `site/src/render.js` | Safe answer renderer (Task 5) |
| `site/src/token.js`, `site/src/api.js`, `site/src/view.js` | Token handling, API client with error text, result view model (Tasks 6, 7) |
| `site/template.html`, `site/src/app.js`, `site/src/style.css`, `scripts/build_site.py` | Page and build (Task 7); `evals` subcommand (Task 8) |
| `evals/report.py` | `/evals` numbers and HTML (Task 8) |
| `site/public/evals.html` | Generated, reviewed, committed (Task 10) |
| `.github/workflows/{ci,pages}.yml`, `docs/ops/deploy.md`, `docs/decisions/decision-log.md`, `CLAUDE.md` | CI, deploy, docs (Task 9) |

---

### Task 1: Store the retrieved piece ids with each question

**Files:** Modify `app/usage.py`, `app/service.py`; Test `tests/test_service.py`, `tests/test_usage.py` (real database, skipped without `TEST_DATABASE_URL`).

**Interfaces:**
- Produces: `questions.retrieved_ids JSONB` (list of piece ids in rank order, nullable); `Usage.finish(..., retrieved_ids: list[str] | None = None)` (new keyword, default `None`, so existing callers keep working).

- [ ] **Step 1: Write the failing tests.** `test_ask_logs_retrieved_piece_ids` in `tests/test_service.py` (use the file's existing fakes): after a successful `ask`, `FakeUsage.finished[0][1]["retrieved_ids"] == [h.piece_id for h in hits]` in order. `test_finish_stores_retrieved_ids` and `test_init_schema_adds_column_to_an_existing_table` in `tests/test_usage.py`: create the old table without the column, call `init_schema()`, then `finish(..., retrieved_ids=["a:1", "b:2"])` and read back `["a:1", "b:2"]`.
- [ ] **Step 2: Run and see them fail:** `.venv/bin/pytest tests/test_service.py tests/test_usage.py -q` (set `TEST_DATABASE_URL` via `set -a; . ./.env; set +a`). Expected: the new tests FAIL.
- [ ] **Step 3: Implement.** In `init_schema` add `ALTER TABLE questions ADD COLUMN IF NOT EXISTS retrieved_ids JSONB` after the `CREATE TABLE`; extend `finish` and its UPDATE; in `AnswerService.ask` pass `retrieved_ids=[h.piece_id for h in hits]` on the success path only.
- [ ] **Step 4: Run all tests and ruff:** `.venv/bin/pytest -q && .venv/bin/ruff check .` Expected: all pass.
- [ ] **Step 5: Commit** `feat: store retrieved piece ids with each question`. Note for the owner: production Neon gets the column on the next `init-db` run (idempotent); ask before running it against production.

### Task 2: Site config, dev CORS origin, invite-link printing

**Files:** Modify `app/config.py`, `config/visidata.yaml`, `app/api.py`, `app/cli.py`; Test `tests/test_config.py`, `tests/test_api.py`, `tests/test_cli.py`.

**Interfaces:**
- Produces: `SiteCfg(_Strict)` with `url: str`, `api_base_url: str`, `title: str`, `intro: str`, `starter_questions: list[str]` (1 to 6 items), `privacy_notice: str`, `known_wrong: dict[str, str] = {}`; `Config.site: SiteCfg` (required). Environment variable `DEV_CORS_ORIGIN` (optional) adds one origin in `build_from_env`. `token create` prints the invite link.
- Design note: the design said "add a localhost origin and remove it before the beta"; an environment variable that Render never sets replaces that step.

- [ ] **Step 1: Write the failing tests.** `test_site_section_is_required_and_strict` (missing `site` fails; an unknown key fails); `test_starter_questions_need_one_to_six`; `test_privacy_notice_names_the_providers_and_retention` (the shipped config's notice contains `Cloudflare`, `Groq`, `Render`, `Neon` and `str(cfg.limits.retention_days)`); `test_dev_cors_origin_env_adds_exactly_one_origin` and `test_cors_without_env_allows_only_configured_origins` in `tests/test_api.py` (monkeypatch the env; check `Access-Control-Allow-Origin` for `http://localhost:8080` and for `GOOD`); `test_token_create_prints_invite_link_with_fragment` in `tests/test_cli.py` (output contains `{site.url}#t={token}` and no `?t=`).
- [ ] **Step 2: Run and see them fail:** `.venv/bin/pytest tests/test_config.py tests/test_api.py tests/test_cli.py -q`.
- [ ] **Step 3: Implement.** Add `SiteCfg` and the `site:` block to `config/visidata.yaml` with: `url: https://navyyshukla.github.io/citeable-docs/`, `api_base_url: https://citeable-docs-api.onrender.com`, title `Ask the VisiData docs`, intro "VisiData is a free tool that runs in the terminal and works like a spreadsheet for data files such as CSV. You drive it with the keyboard and can explore a file quickly. Ask anything about using it; answers come only from its documentation, with links.", starters `How do I rename a column?`, `How can I convert a CSV file to another file type?`, `How do I make a frequency table of a column?`, `What does the ! key do to a column?`, a privacy notice naming the four providers and 30 days and "only the owner reads questions", and `known_wrong` notes for `d-001` (the docs' sort page and VisiData's source disagree on which of `[` and `]` sorts high-to-low) and `k-004` (the docs excerpt is too vague to help). In `build_from_env` append `os.environ["DEV_CORS_ORIGIN"]` when set. In `cmd_token` print `f"{cfg.site.url.rstrip('/')}/#t={token}"` as the invite link (load the config with the command's existing `--config` option).
- [ ] **Step 4: Run all tests and ruff.** Expected: pass.
- [ ] **Step 5: Commit** `feat: site config, dev CORS env var, invite link printing`.

### Task 3: Interval maths for the eval pages

**Files:** Create `evals/stats.py`; Test `tests/evals/test_stats.py`.

**Interfaces:**
- Produces: `wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]` (low, high as fractions; `n == 0` returns `(0.0, 1.0)`); `fraction_text(k: int, n: int) -> str`; `spread(values: list[float]) -> tuple[float, float]` (min, max; empty raises `ValueError`).

- [ ] **Step 1: Write the failing tests** with the figures computed in this project: `round_pair(wilson(15, 17)) == (0.66, 0.97)`; `wilson(9, 9)[0]` rounds to `0.70` and `[1] == 1.0`; `wilson(25, 26)` rounds to `(0.81, 0.99)`; `wilson(0, 0) == (0.0, 1.0)`; `wilson(0, 10)[0] == 0.0`; `fraction_text(15, 17) == "15/17 (66%–97%)"`; `fraction_text(0, 0) == "no data"`; `spread([3, 1, 2]) == (1, 3)`; `spread([])` raises. Raise `ValueError` for `k > n` or negatives.
- [ ] **Step 2: Run and see them fail.** `.venv/bin/pytest tests/evals/test_stats.py -q`.
- [ ] **Step 3: Implement** the Wilson score interval; no dependencies.
- [ ] **Step 4: Run tests and ruff.** Expected: pass.
- [ ] **Step 5: Commit** `feat: Wilson ranges for eval numbers`.

### Task 4: Question generator and hand-check sheet

**Files:** Create `evals/generate.py`; Modify `app/cli.py` (new `generate-questions` command); Test `tests/evals/test_generate.py`.

**Interfaces:**
- Consumes: `Piece` (`ingest/models.py`), `EvalQuestion` (`evals/schema.py`), a provider with `complete(system, user, max_tokens)` (the Gemini provider, `json_output=True`).
- Produces: `build_prompt(piece: Piece) -> tuple[str, str]`; `parse_questions(text: str, piece: Piece, next_id: int, existing: set[str]) -> list[EvalQuestion]` (`source="synthetic"`, `split="dev"`, `answerable=True`, `gold_page=piece.page_slug`, `gold_heading=piece.heading_path[-1]`, ids `s-001`…); `build_unanswerable_prompt(page_titles: list[str], n: int) -> tuple[str, str]`; `parse_unanswerable(text: str, next_id: int, existing: set[str]) -> list[EvalQuestion]` (`answerable=False`); `generate(pieces, provider, *, limit: int, pause: float = 6.0, existing: set[str]) -> list[EvalQuestion]`; `write_check_sheet(questions, path: Path, every: int = 5) -> int` (markdown, returns rows written).

- [ ] **Step 1: Write the failing tests** with a fake provider: the system prompt tells the model to write as a newcomer who has never seen the docs, to avoid the heading's words, and to return JSON `{"questions": [...]}` (assert those instructions appear); `parse_questions` drops malformed JSON, questions over 500 characters, empty ones, and duplicates of `existing` (case-insensitive); ids continue from `next_id`; `parse_unanswerable` sets `answerable=False` and no gold; `generate` calls the provider at most `limit` times and sleeps `pause` between calls (inject `sleep`); `write_check_sheet(qs, p, every=5)` writes every fifth question and returns that count; written files contain no piece text.
- [ ] **Step 2: Run and see them fail.** `.venv/bin/pytest tests/evals/test_generate.py -q`.
- [ ] **Step 3: Implement** the module and the CLI command `generate-questions --out evals/data/synthetic.jsonl --limit 25 --sheet <path>`; it loads pieces read-only, uses `GEMINI_API_KEY`, writes a JSONL that `load_questions` accepts.
- [ ] **Step 4: Run tests and ruff.** Expected: pass. (No Gemini call is made in this task.)
- [ ] **Step 5: Commit** `feat: generated eval questions with a hand-check sheet`.

### Task 5: Safe answer renderer

**Files:** Create `site/package.json` (`{"type": "module", "private": true}`), `site/src/render.js`; Test `site/tests/render.test.js` (`node --test site/tests/`).

**Interfaces:**
- Produces: `escapeHtml(s: string): string`; `renderAnswerHtml(text: string, citations: {n: number, title: string, url: string}[]): string`. Allowed output tags: `p`, `strong`, `code`, `ul`, `ol`, `li`, `a`, `br`.

- [ ] **Step 1: Write the failing tests** (hostile inputs are the point):
  - `'<script>alert(1)</script>'` → output has no `<script`; contains `&lt;script&gt;`.
  - `'<img src=x onerror=alert(1)>'` → no `<img`.
  - `'[click](javascript:alert(1))'` → no `javascript:` inside an `href`; no `<a` produced.
  - `'See [1].'` with `citations=[{n:1, title:'Join › How', url:'https://www.visidata.org/docs/join/'}]` → exactly one `<a href="https://www.visidata.org/docs/join/" target="_blank" rel="noopener noreferrer">`; link text contains `[1]`.
  - `'See [99].'` with no citation 99 → plain text `[99]`, no `<a`.
  - a citation whose url is `javascript:alert(1)` or `http://…` (not https) → rendered as plain text, no `<a`.
  - `'**bold** and `code`'` → `<strong>bold</strong>`, `<code>code</code>`; `'**<b>x</b>**'` → inner tag escaped.
  - `'- a\n- b'` → a `<ul>` with two `<li>`; `'1. a\n2. b'` → an `<ol>`; blank line separates paragraphs; `''` → `''`.
  - `'&lt;script&gt;'` (already-escaped input) → double-escaped (`&amp;lt;`), never decoded.
- [ ] **Step 2: Run and see them fail:** `node --test site/tests/`.
- [ ] **Step 3: Implement.** Escape the whole text first, then apply the small set of shapes with line-by-line parsing; `[n]` becomes a link only when `n` is in `citations` and the url starts with `https://`.
- [ ] **Step 4: Run tests.** Expected: pass.
- [ ] **Step 5: Commit** `feat: safe answer renderer with hostile-input tests`.

### Task 6: Token handling and API client

**Files:** Create `site/src/token.js`, `site/src/api.js`; Test `site/tests/token.test.js`, `site/tests/api.test.js`.

**Interfaces:**
- Produces (`token.js`): `readTokenFromHash(hash: string): string | null` (accepts only `#t=` + 43 characters of `[A-Za-z0-9_-]`, the shape `looks_like_token` in `app/usage.py` accepts; read that function and mirror it); `loadToken(storage, hash): {token: string | null, fromLink: boolean}`; `saveToken(storage, token): boolean`; `forgetToken(storage): void` (every storage call in try/catch).
- Produces (`api.js`): `createApi({baseUrl: string, fetchFn?: Function, timeoutMs?: number = 45000}): {health(): Promise<boolean>, ask(token, question): Promise<object>, feedback(token, requestId, rating, comment?): Promise<void>}`; `describeError(status: number | null, body: object | null): string`.

- [ ] **Step 1: Write the failing tests.** Token: a valid `#t=` fragment returns the token; `''`, `'#t='`, a 42- or 44-character token, `'?t=<token>'`, and `'#x=<token>'` return `null`; with a storage whose `getItem`/`setItem` throw, `loadToken` returns `{token: null, fromLink: false}` and `saveToken` returns `false` without throwing; a link token wins over a stored one; `forgetToken` removes it. API: `ask` sends `POST {baseUrl}/ask` with header `Authorization: Bearer <token>` and JSON `{question}`; `feedback` sends `{request_id, rating, comment}`; `describeError(401, …)` is "This invite link isn't valid or was withdrawn. Ask the person who sent it for a new one."; `describeError(429, {error: "You have used your questions for today. Try again after 00:00 UTC."})` returns that server text; `503` → "The assistant is busy. Try again in a minute."; `null` (network or timeout) → "Couldn't reach the server. Check your connection and try again."; `health()` resolves `false` when the fetch rejects, never throws; a fetch that never resolves is cut off at `timeoutMs` (fake timer).
- [ ] **Step 2: Run and see them fail:** `node --test site/tests/`.
- [ ] **Step 3: Implement** both modules (AbortController for the timeout).
- [ ] **Step 4: Run tests.** Expected: pass.
- [ ] **Step 5: Commit** `feat: invite token handling and API client`.

### Task 7: The page and its build

**Files:** Create `site/template.html`, `site/src/view.js`, `site/src/app.js`, `site/src/style.css`, `scripts/build_site.py`; Modify `.gitignore` (add `_site/`); Test `site/tests/view.test.js`, `tests/test_build_site.py`.

**Interfaces:**
- Consumes: `renderAnswerHtml` (Task 5), `createApi`, `loadToken`, `saveToken`, `forgetToken`, `describeError` (Task 6), `Config.site` (Task 2).
- Produces: `resultView(result: object): {label: string, bodyHtml: string, sources: {n, title, url}[], closest: {title, url}[], showFeedback: boolean}` (`site/src/view.js`); `build_page(cfg: Config, out_dir: Path) -> Path` in `scripts/build_site.py` (writes `index.html` plus copies of `site/src/*`; returns the index path).

- [ ] **Step 1: Write the failing tests.** `view.test.js`: status `answered` → label "Answered from the docs", `showFeedback` true, sources listed; status `abstained` → label "I couldn't find this in the docs", the `closest` pages listed, `showFeedback` false; an unknown status → a neutral error label, no crash. `test_build_site.py`: the built `index.html` contains the title, the intro, every starter question, the privacy notice; config text `"a <b>&"` appears escaped; no `{{` left; the CSP `<meta>` equals `default-src 'none'; script-src 'self'; style-src 'self'; connect-src <api_base_url>; img-src 'self'; base-uri 'none'; form-action 'none'`; every `<script>` tag has a `src` except one `type="application/json"` config block; `evals.html` is linked; the build copies `render.js`, `token.js`, `api.js`, `view.js`, `app.js`, `style.css`.
- [ ] **Step 2: Run and see them fail:** `node --test site/tests/ && .venv/bin/pytest tests/test_build_site.py -q`.
- [ ] **Step 3: Implement** the template (title, two-sentence intro, clickable starter questions, question box with a live `n/500` counter, Ask button disabled when empty, whitespace-only or over 500 characters, answers list with status label, source links labelled with page and heading, feedback buttons "Yes, helpful" / "No" and an optional comment box after "No", footer with the `license_note`, docs version, last-updated date and a privacy link), `app.js` wiring: read and save the token from the fragment then clear it with `history.replaceState`; no token → a clear "You need an invite link" message and the box disabled; ping `health()` on load and show "Waking the server up, up to 30 seconds…" only if it has not answered after 3 s; a "forget this device" link; plain-language errors from `describeError`, input kept and button re-enabled on error. No turn counter (Plan 3b). Styling: readable at phone width with a 16 px side gutter, light and dark colours.
- [ ] **Step 4: Run all tests and ruff.** Expected: pass. Then a manual check with the owner's approval (it sends one question to production): `python scripts/build_site.py page --out _site && python -m http.server -d _site 8080`, run the API locally or on Render with `DEV_CORS_ORIGIN=http://localhost:8080`, open `http://localhost:8080/#t=<owner-test token>`, and see: the cold banner (if asleep), one cited answer, a refusal for an off-topic question, a thumbs-down saved (check the database), and "invite link" message with no fragment.
- [ ] **Step 5: Commit** `feat: chat page and site build`.

### Task 8: The `/evals` page

**Files:** Create `evals/report.py`; Modify `scripts/build_site.py` (add `evals` subcommand); Test `tests/evals/test_report.py`.

**Interfaces:**
- Consumes: `fraction_text`, `wilson`, `spread` (Task 3); `Config.site.known_wrong` (Task 2); `Piece` (for source links).
- Produces: `build_report(runs: list[dict], labels: dict[str, bool], verdicts: dict[str, dict], trap: dict | None, questions: list[EvalQuestion], pieces: dict[str, Piece], known_wrong: dict[str, str]) -> Report` (frozen dataclass: `headline: list[Stat]`, `honesty: list[str]`, `known_wrong: list[tuple[str, str]]`, `history: list[RunRow]`, `rows: list[QuestionRow]`); `render_evals_html(report: Report, cfg: Config) -> str`. A `Stat` is `(label: str, k: int, n: int)`.

- [ ] **Step 1: Write the failing tests** with small hand-made result dicts shaped like the saved results (`meta`, `retrieval`, `answers`): headline stats are "unanswerable refused", "answerable answered with a valid citation", "invalid citations", "hand-graded correct" (from `labels`), "right page in top 5" per mode; in the HTML the headline block comes before the honesty panel, which comes before known wrong answers, which come before run history (`html.index(...)` ordering); the honesty text states n and "one question moves a rate by about N points" with `N = round(100 / answerable_n)`; judge numbers are labelled "rough filter"; known-wrong notes are shown; each question row shows the full answer text escaped (`<script>` in an answer appears as `&lt;script&gt;`) and its sources as links built from `pieces`; zero runs renders "No runs yet" and does not raise; `n = 0` stats render "no data"; labels missing for a run does not raise; a row with `status == "error"` is counted separately and never as an answer; synthetic and dev runs appear as separate groups.
- [ ] **Step 2: Run and see them fail:** `.venv/bin/pytest tests/evals/test_report.py -q`.
- [ ] **Step 3: Implement** the module, then `python scripts/build_site.py evals --run PATH [--run PATH …] --labels PATH --verdicts PATH [--trap PATH] --out site/public/evals.html` (loads questions and pieces read-only; pieces need `DATABASE_URL`).
- [ ] **Step 4: Run tests and ruff.** Expected: pass.
- [ ] **Step 5: Commit** `feat: public /evals page builder`.

### Task 9: CI, Pages deploy and docs

**Files:** Modify `.github/workflows/ci.yml`; Create `.github/workflows/pages.yml`; Modify `docs/ops/deploy.md`, `docs/decisions/decision-log.md`, `CLAUDE.md`; Test `tests/test_pages_workflow.py` (follow the pattern of `tests/test_render_yaml.py`).

**Interfaces:** `pages.yml` runs on push to `main` when `site/**`, `config/visidata.yaml` or `scripts/build_site.py` change; it builds `_site/` with `python scripts/build_site.py page --out _site`, copies `site/public/*` into it, uploads it and deploys with the Pages actions.

- [ ] **Step 1: Write the failing test.** Parse `pages.yml` with `yaml.safe_load`: `permissions` are exactly `contents: read`, `pages: write`, `id-token: write`; it contains no `secrets.` reference; it triggers on `push` to `main` only; `ci.yml` contains a `setup-node` step and a `node --test site/tests/` run.
- [ ] **Step 2: Run and see it fail:** `.venv/bin/pytest tests/test_pages_workflow.py -q`.
- [ ] **Step 3: Implement** the workflows and docs: `deploy.md` gets "Enabling Pages" (owner action: repository Settings → Pages → Source: GitHub Actions), `DEV_CORS_ORIGIN` for local page development, and how to build and review `evals.html`; add decision-log entry **D24** summarising the Plan 3 design with a link to the design doc, including the departure (env var instead of editing the CORS list); update the `CLAUDE.md` state.
- [ ] **Step 4: Run all tests and ruff:** `.venv/bin/pytest -q && .venv/bin/ruff check . && node --test site/tests/`. Expected: pass.
- [ ] **Step 5: Commit** `ci: Pages deploy and site tests`. **Stop and ask the owner** before pushing and before enabling Pages (outward-facing); run the neutral-wording scan on the whole diff first.

### Task 10: Pre-beta eval strengthening (owner-gated checklist)

**Files:** Create (git-ignored) generated sets and run results under `evals/`; Commit `evals/data/synthetic.jsonl` (questions only) and `site/public/evals.html`.

Each step that spends Gemini calls or neurons is a stop for the owner's approval.

- [ ] **Step 1: Generate questions.** Ask first. `set -a; . ./.env; set +a; .venv/bin/python -m app.cli generate-questions --out evals/data/synthetic.jsonl --limit 25 --sheet /tmp/check.md` (about 25 Gemini calls, public docs text only, 0 neurons). Expected: a JSONL that `load_questions` accepts and a check sheet with every fifth question.
- [ ] **Step 2: The owner hand-checks the sheet** (answerable? right page?). Drop failing questions from the file; if more than 1 in 4 of the sample fails, regenerate with a stricter prompt before using the set.
- [ ] **Step 3: Baseline v2 on the dev set.** Ask first (about 400 neurons per run). Run `.venv/bin/python -m app.cli eval --answer --modes hybrid --data evals/data/dev.jsonl --max-neurons 1500 --out evals/results/v2-dev-N.json` three times (N = 1 to 3); expected: three result files, `stopped_early: false`. Then the same three runs with `--data evals/data/synthetic.jsonl` and `--out evals/results/v2-synth-N.json` (reported separately). Estimate: about 3,500 neurons in total for about 80 questions, which fits in one day before the beta; split over two days if it does not.
- [ ] **Step 4: Run the judge** on each run (Gemini, paced) and re-run the trap test (`evals.judge_traps`) once; save verdict files.
- [ ] **Step 5: Build and review `/evals`.** `.venv/bin/python scripts/build_site.py evals --run … --labels evals/results/human-labels.jsonl --verdicts … --trap … --out site/public/evals.html`; the owner opens it and checks every number against the saved results, that the honesty panel sits directly under the headline numbers, and that no docs excerpt appears. Commit `evals.html` and `synthetic.jsonl`.
- [ ] **Step 6: Update `CLAUDE.md`** with the new run counts, ranges and the label re-check for `r-004` and `d-003` (open since D23). Report in simple words with a text diagram; name the single next step (open the beta after the owner approves the push and Pages).
