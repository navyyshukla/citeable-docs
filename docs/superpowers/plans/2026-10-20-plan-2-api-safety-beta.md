# Plan 2: API, Safety and Beta Backend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the offline engine into a deployed, safe, friends-only API that logs every question, and add the AI judge, so Plan 3 only has to build the web pages.

**Architecture:** A FastAPI app on Render (Ohio) in front of the existing `Searcher` + provider chain. Postgres (Neon) holds the pieces, invite tokens, the question log, feedback and the daily caps. A small connection pool sits between the app and Neon. The judge is an offline command that only reads eval-result files.

**Tech Stack:** Python ≥3.10, FastAPI, uvicorn, psycopg 3 + psycopg_pool, httpx, pydantic v2, pytest, ruff. Neon, Render free, Cloudflare Workers AI, Groq, Gemini (judge only).

**Spec:** `docs/superpowers/specs/2026-10-15-docs-assistant-design.md` (implements §5 request flow, §9 safety, §10 judge, §13 hosting). Rationale: `docs/decisions/decision-log.md` (D12-D18). Plan 1: `docs/superpowers/plans/2026-10-15-plan-1-spikes-and-core-engine.md`.

**Why the split with Plan 3:** friends will use the beta through the chat page, which is Plan 3 (about 3-4 days after this plan). So Plan 2 has no real user questions to tune on: the evidence threshold and caps are set from the Plan 1 dev set and are provisional. Plan 2 therefore logs every question from day one; those rows become the held-out set.

## Global Constraints

Copied from the spec and CLAUDE.md; every task includes these.

- Everything runs on free plans with no card. The assistant has no tools and no private data.
- Never commit copies of VisiData docs. Anything project-specific lives in `config/visidata.yaml`.
- Model calls per answered question: **1** (more only when a provider fails).
- Max question 500 chars, max answer tokens 400, global cap 150/day, per-visitor cap 10/day (config values; the per-visitor cap is per invite token).
- Users get Cloudflare `gemma-4-26b-a4b-it` -> Groq `openai/gpt-oss-20b` -> Cloudflare `llama-3.1-8b-instruct-fp8`; any failure moves to the next. Gemini is **tests and judge only, public data only: no user question ever goes to Gemini** (free tier trains on content).
- No raw IPs stored. Keys only in environment variables / Render secrets. Never print `.env` values.
- Cloudflare free allowance: 10,000 neurons/day, shared by users, evals and the fallback model.
- Raw HTML is never rendered (Plan 3), and the link stripper stays the injection defence: an answer is accepted only if it cites a piece we sent or is exactly the abstention marker.
- **Owner checkpoints (ask first):** any write to `DATABASE_URL` (production Neon), any run that spends Cloudflare neurons, every `git push`.

## Owner decisions for this plan (2026-10-20)

| Choice | Picked | Alternatives left |
|---|---|---|
| Who may call | Invite token per friend, only its SHA-256 hash stored | open + hashed IP; one shared password |
| DB access | `psycopg_pool` + retry on first connect | open per request + retry; load everything in memory |
| Caps and logs | Postgres tables | in-memory counters; Redis (rejected, D16) |
| Judge | Build now (Gemini, public data), calibrate by hand later | defer to Plan 3; skip |

The owner's one-sentence reason for each is still to be written into `docs/decisions/decision-log.md` as D19 (Task 24).

**My calls (not yet confirmed; change any):** (a) daily neuron budget of 8,000 as a third cap, because the real quota is neurons, not requests; (b) question-log retention 30 days, with a `purge` command; (c) a failed request (all providers down) is not counted against the caps, an abstained one is; (d) sync FastAPI endpoints (threadpool), no streaming, no exact-match cache until the beta shows repeats; (e) tokens are 32 random bytes, so a fast hash is enough (no password hashing).

## Review Focus

Conditions the spec implies but does not spell out. Each has a test in the owning task.

1. **Parallel requests at the cap edge** (cap 10, 12 at once) → exactly 10 pass, 2 get 429; no double-spend (Task 17).
2. **Neon asleep / unreachable**: first connect fails then succeeds → the request succeeds; still down after the retry window → 503 with a clear message, never a hang (Task 16).
3. **Missing, malformed, unknown or revoked token** → 401, nothing logged, token never appears in logs or errors (Tasks 17, 20).
4. **Bad body**: not JSON, no `question`, 600 chars, only whitespace, huge body, odd unicode → 4xx before any search or model call (Tasks 19, 20).
5. **All providers fail** → 503, the reservation is refunded, the log row says `error`; and one request's `llm_calls` is never polluted by another request's (shared `Adapter` counters are not thread-safe) (Task 19).
6. **Changed embedding model, same vector size** → ingest and API startup refuse (Task 16).
7. **Browser call from a site not on the allowlist** → no CORS headers granted (Task 20).

## File Structure

```
config/visidata.yaml      + limits.global_daily_neurons, limits.retention_days, api.cors_origins
app/config.py             + ApiCfg; two new LimitsCfg fields
app/db.py          (new)  Db: lazy pool, retrying first connect, conn() context manager
app/store.py              Store takes a Db; adds ingest_meta read/write + check
app/usage.py       (new)  Usage: invite tokens, question log, cap reservation, feedback, purge
app/answer.py             evidence-threshold gate (no model call below the threshold)
app/service.py     (new)  AnswerService.ask(): auth -> validate -> reserve -> search -> answer -> log
app/api.py         (new)  FastAPI app: /ask /feedback /health /version, CORS, error mapping
app/cli.py                + serve, init-db, token create|revoke|list, purge, judge, calibrate
app/llm/gemini.py  (new)  GeminiProvider (judge/tests only)
evals/runner.py           AnswerRow also stores question text, answer text, top_score
evals/judge.py     (new)  rubric, judge_answer(), agreement metrics vs hand labels
evals/threshold.py (new)  threshold_table() from saved retrieval results (no model calls)
render.yaml        (new)  Render blueprint (Ohio, Python pin, no access log)
scripts/smoke.py   (new)  post-deploy check against a live URL
tests/...                 one test file per new module
```

---

### Task 16: Connection pool, ingest_meta, config fields

**Files:**
- Create: `app/db.py`, `tests/test_db.py`
- Modify: `app/store.py`, `app/config.py`, `config/visidata.yaml`, `app/cli.py` (ingest), `pyproject.toml` (add `fastapi`, `uvicorn`, `psycopg_pool`; dev: `httpx` already present)
- Test: `tests/test_db.py`, `tests/test_config.py`, `tests/test_store.py` (store tests need `TEST_DATABASE_URL`)

**Interfaces:**
- Produces: `class Db: __init__(self, dsn: str, min_size: int = 1, max_size: int = 4, connect_retries: int = 4, retry_delay: float = 5.0)`; `Db.conn() -> ContextManager[psycopg.Connection]` (borrows from the pool, opens the pool lazily on first use); `Db.close() -> None`. `Store.__init__(self, db: Db, dim: int, vector_index: str = "none")` replaces the `dsn` argument. `Store.write_ingest_meta(project: str, embedding_model: str, dim: int, docs_ref: str) -> None`; `Store.check_ingest_meta(project: str, embedding_model: str) -> None` (raises `ValueError` when the stored model differs; passes when there is no row yet).
- Produces config: `LimitsCfg.global_daily_neurons: float = 8000`, `LimitsCfg.retention_days: int = 30`, `ApiCfg(cors_origins: list[str])`, `Config.api: ApiCfg`.
- Consumes: existing `Store` methods keep their names and results.

- [ ] **Step 1: Write failing tests** in `tests/test_db.py` with a fake connect function injected into `Db` (add a keyword `connect=` for tests): `test_first_connect_retries_then_succeeds` (fails twice with `psycopg.OperationalError`, then works; assert 3 attempts and a sleep between them via an injected `sleep`), `test_gives_up_after_retries` (raises `DbUnavailable`, a new exception in `app/db.py`, after `connect_retries` attempts), `test_pool_is_not_opened_until_first_use` (constructing `Db` makes no connection). In `tests/test_store.py` add `test_ingest_meta_blocks_changed_model` (write meta with model A, `check_ingest_meta(..., model B)` raises `ValueError` naming both models) and `test_ingest_meta_passes_when_empty`. In `tests/test_config.py` add a test that `config/visidata.yaml` loads with `api.cors_origins` and the two new limits.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_db.py tests/test_config.py -q`. Expected: FAIL (module or fields missing).
- [ ] **Step 3: Implement `Db`** in `app/db.py` on `psycopg_pool.ConnectionPool(open=False)`; open on first `conn()` under a lock; each connect attempt uses `connect_timeout=15`; retries only `psycopg.OperationalError`; after the last failure raise `DbUnavailable`. Pool connections must not hold a transaction between uses. Study: Neon's pooler is transaction-mode, so keep using `SET LOCAL` inside `with c.transaction()` (S9, S11).
- [ ] **Step 4: Rewire `Store`** to borrow connections from `Db.conn()`; add the `ingest_meta` table (`project TEXT PRIMARY KEY, embedding_model TEXT, dim INT, docs_ref TEXT, ingested_at TIMESTAMPTZ`) in `init_schema`. In `cmd_ingest` call `check_ingest_meta` before embedding (refuse on mismatch unless `--allow-model-change`, which re-embeds everything) and `write_ingest_meta` inside the same run after a successful replace.
- [ ] **Step 5: Run** `.venv/bin/pytest -q` and `.venv/bin/ruff check .`; then, with the owner's approval for the test branch only, `set -a; . ./.env; set +a; .venv/bin/pytest tests/test_store.py -q`. Expected: all pass. **Do not run ingest against `DATABASE_URL` in this task.**
- [ ] **Step 6: Commit** `feat: connection pool with retry, ingest_meta model guard, api config fields`.

### Task 17: Usage store (tokens, question log, caps, feedback)

**Files:**
- Create: `app/usage.py`, `tests/test_usage.py` (DB tests, skipped without `TEST_DATABASE_URL`, same marker pattern as `tests/test_store.py`)
- Test: `tests/test_usage.py`

**Interfaces:**
- Consumes: `Db` (Task 16).
- Produces:
  - `hash_token(token: str) -> str` (hex SHA-256).
  - `class Usage: __init__(self, db: Db)`; `init_schema() -> None` creates `invite_tokens(id, label, token_hash UNIQUE, created_at, revoked_at)`, `questions(id UUID PK, token_id, created_at, project, question, status, answer_text, citations JSONB, top_score, provider, model, neurons, llm_calls, seconds, docs_ref, error)`, `feedback(request_id UUID PK REFERENCES questions ON DELETE CASCADE, rating SMALLINT, comment TEXT, created_at)`.
  - `create_token(label: str) -> str` (returns the plain token once; only the hash is stored); `revoke_token(label: str) -> bool`; `list_tokens() -> list[TokenInfo]` (label, created_at, revoked, questions today).
  - `token_id_for(token: str) -> int | None` (None if unknown or revoked).
  - `reserve(token_id: int, project: str, question: str, per_visitor: int, global_cap: int, neuron_budget: float) -> Reservation | CapHit` where `Reservation(request_id: str)` and `CapHit(kind: Literal["visitor","global","neurons"], resets_at: datetime)`. Counts rows from today (UTC) whose status is `reserved`, `answered` or `abstained`; runs under `pg_advisory_xact_lock` so parallel calls cannot overshoot.
  - `finish(request_id: str, *, status: Literal["answered","abstained","error"], answer_text: str | None, citations: list[dict], top_score: float | None, provider: str | None, model: str | None, neurons: float | None, llm_calls: int, seconds: float | None, docs_ref: str | None, error: str | None) -> None`.
  - `add_feedback(token_id: int, request_id: str, rating: int, comment: str | None) -> bool` (False if the request is not that token's; `rating` is -1 or 1; comment ≤ 500 chars, else `ValueError`).
  - `purge(older_than_days: int) -> int` (rows deleted).
- Notes: `error` status rows are **not** counted against caps (my call c). A `reserved` row left by a crash counts until midnight UTC (conservative).

- [ ] **Step 1: Write failing tests**: `test_token_roundtrip_stores_only_hash` (the plain token is not in any column), `test_revoked_token_unknown`, `test_per_visitor_cap_blocks_the_eleventh` (cap 10 → `CapHit(kind="visitor")`), `test_global_cap`, `test_neuron_budget_cap` (finish rows with neurons summing past the budget → `CapHit(kind="neurons")`), `test_error_rows_do_not_count`, `test_parallel_reserve_never_overshoots` (12 threads, cap 10 → exactly 10 `Reservation`s), `test_feedback_only_for_own_request`, `test_feedback_comment_too_long`, `test_purge_deletes_old_rows_and_their_feedback`, `test_no_ip_column` (assert `questions` columns contain nothing named `ip`/`address`).
- [ ] **Step 2: Run** `set -a; . ./.env; set +a; TEST_DATABASE_URL=$TEST_DATABASE_URL .venv/bin/pytest tests/test_usage.py -q`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement `Usage`** with the signatures above; each test file wipes only its own rows by label prefix `t-` (as `tests/test_store.py` does for projects).
- [ ] **Step 4: Run** the same command. Expected: PASS. Run `.venv/bin/pytest -q` (the DB tests skip) and `.venv/bin/ruff check .`.
- [ ] **Step 5: Commit** `feat: usage store with invite tokens, question log, atomic caps, feedback`.

### Task 18: Evidence threshold and its calibration table

**Files:**
- Create: `evals/threshold.py`, `tests/evals/test_threshold.py`
- Modify: `app/answer.py` (`answer_question`), `evals/runner.py` (`AnswerRow` gains `question: str`, `text: str | None`, `top_score: float | None`), `tests/test_answer.py`, `tests/evals/test_runner.py`, `.gitignore` (add `evals/results/`)

**Interfaces:**
- Produces: `answer_question(..., threshold: float | None = None)`: when the best hit's score is below `threshold` it returns `Answer("abstained", NOT_FOUND_TEXT, closest=<top 3 citations>, llm_calls=0, top_score=<score>)` **without a model call**. `threshold_table(rows: list[RetrievalRow], thresholds: list[float]) -> list[ThresholdRow]` where `ThresholdRow(threshold, answered_pct, wrong_when_answered_pct, correctly_abstained_pct)` computed from the best score of each question: "answered" = best score ≥ threshold; "wrong" = answerable but no gold hit, or unanswerable.
- Consumes: `RetrievalRow` fields from `evals/runner.py` (use the real field names; it records hit flag, piece ids and scores per question).
- Note: hybrid scores are rank-fusion scores (top possible about 0.033 with `rrf_k` 60), not similarities, so the table is the tool; no value is guessed in advance. The owner picks the dial from the table.

- [ ] **Step 1: Write failing tests**: `test_below_threshold_abstains_with_no_model_call` (fake adapter whose `complete` raises if called), `test_at_threshold_goes_to_model`, `test_none_threshold_keeps_old_behaviour`; `test_threshold_table_counts` on 6 hand-made rows (assert each percentage); `test_answer_row_keeps_text_and_score`.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_answer.py tests/evals -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the gate in `answer_question` (before `_answer_from`), the new `AnswerRow` fields filled in `run_answers`, and `threshold_table`. Add CLI `calibrate --retrieval PATH --mode hybrid` printing the table (reads the saved JSON, makes **no** model or embedding call, spends no neurons).
- [ ] **Step 4: Run** `.venv/bin/pytest -q` and ruff. Then run `.venv/bin/python -m app.cli calibrate --retrieval docs/evals/retrieval-2026-10-20b.json --mode hybrid` and put the table in `docs/evals/threshold-2026-10-20.md`.
- [ ] **Step 5: Owner picks the threshold** from the table (write the value and the one-sentence reason into `config/visidata.yaml` `search.evidence_threshold`, and into D19). Mark it provisional until friends' questions exist.
- [ ] **Step 6: Commit** `feat: evidence threshold gate and calibration table`.

### Task 19: Answer service

**Files:**
- Create: `app/service.py`, `tests/test_service.py`
- Test: `tests/test_service.py` (fakes for `Usage`, `Store`, embeddings and adapter; no network)

**Interfaces:**
- Consumes: `Usage` (17), `Store`/`Db` (16), `Searcher`, `answer_question`, `validate_question`, `build_adapter`.
- Produces:
  - `class AskError(Exception)` with `status: int`, `message: str`, optional `headers: dict`.
  - `AskResult` dataclass: `request_id: str, status: str, text: str, citations: list[Citation], closest: list[Citation], docs_ref: str | None, docs_version: str | None, last_updated: str | None`.
  - `class AnswerService: __init__(self, cfg: Config, usage: Usage, store: Store, make_adapter: Callable[[], Adapter], embed_query: Callable[[str], list[float]])`; `ask(token: str, question: str) -> AskResult`; `feedback(token: str, request_id: str, rating: int, comment: str | None) -> None`.
- Flow in `ask`: `token_id_for` (else `AskError(401)`) -> `validate_question` (else `AskError(400)`, nothing logged) -> `usage.reserve` (else `AskError(429)` naming the cap and when it resets) -> search -> `answer_question(..., threshold=cfg.search.evidence_threshold)` -> `usage.finish`. On `AllProvidersFailed`/`ProviderError`: `finish(status="error")` (not counted) and `AskError(503)`. On any other exception: `finish(status="error")` and re-raise (becomes a 500 without detail).
- Rules: pieces, BM25 and the `Searcher` are built **lazily on first request** and reused (the 0.1 CPU instance is slow at start-up; cold start is already about 22 s); `make_adapter()` is called **per request**, so `llm_calls` and neurons are never shared across threads. On startup of the lazy load, run `store.check_ingest_meta` and refuse to serve (503 "index not ready") on a mismatch.

- [ ] **Step 1: Write failing tests**: `test_unknown_token_is_401_and_logs_nothing`, `test_empty_and_long_question_are_400_before_reserve`, `test_cap_hit_is_429_with_reset_time`, `test_happy_path_logs_answer_and_citations`, `test_below_threshold_abstains_without_adapter_call`, `test_all_providers_failed_is_503_and_logged_as_error`, `test_each_request_gets_its_own_adapter` (counts `make_adapter` calls), `test_index_loaded_once_across_requests`, `test_model_mismatch_refuses_to_serve`, `test_feedback_for_other_tokens_request_is_404`.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_service.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement `AnswerService`** per the flow and rules above (the lazy index guarded by a lock).
- [ ] **Step 4: Run** `.venv/bin/pytest -q` and ruff. Expected: PASS.
- [ ] **Step 5: Commit** `feat: answer service (auth, caps, search, answer, log)`.

### Task 20: FastAPI app

**Files:**
- Create: `app/api.py`, `tests/test_api.py`
- Test: `tests/test_api.py` using `fastapi.testclient.TestClient` and a fake `AnswerService`

**Interfaces:**
- Consumes: `AnswerService`, `AskError`, `AskResult` (19), `Config`.
- Produces: `create_app(service: AnswerService, cfg: Config) -> FastAPI`; module-level `app = create_app_from_env()` is **not** created at import (tests import the module); `app/api.py` exposes `def build_from_env() -> FastAPI` used by `uvicorn --factory app.api:build_from_env`.
- Endpoints (all JSON): `POST /ask` body `{"question": str}`, header `Authorization: Bearer <token>` -> `AskResult` as JSON plus `notice` (the `license_note` from config); `POST /feedback` body `{"request_id": str, "rating": 1|-1, "comment": str|null}` -> `{"ok": true}`; `GET /health` -> `{"ok": true}` (no DB, no token, so Render's health check never wakes Neon); `GET /version` -> `{"docs_ref", "project", "models": answer_order}` (from the lazy index; 503 until loaded is fine).
- Rules: CORS allowlist = `cfg.api.cors_origins` only, methods POST/GET, headers `Authorization, Content-Type`; request body larger than 4 KB -> 413; `AskError` -> its status with `{"error": message}`; unexpected exception -> 500 `{"error": "internal error"}` (no stack, no token); the `Authorization` header is never logged; uvicorn runs with the access log off.

- [ ] **Step 1: Write failing tests**: `test_ask_requires_bearer_token` (missing, `Basic x`, empty -> 401), `test_ask_happy_path_shape`, `test_ask_non_json_and_missing_field_are_4xx`, `test_body_over_4kb_is_413`, `test_cors_allows_listed_origin_only` (preflight from a listed and an unlisted origin), `test_ask_error_maps_status_and_message`, `test_unexpected_error_hides_detail`, `test_health_needs_no_service_call`, `test_feedback_rating_must_be_1_or_minus_1`.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_api.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement `create_app` and `build_from_env`** (`build_from_env` reads `DATABASE_URL`, `CF_*`, `GROQ_API_KEY` from the environment, builds one `Db`, one shared `httpx.Client`, and the service; nothing connects until the first request). Endpoints are plain `def` (threadpool), not `async def`, because the DB and HTTP clients are synchronous.
- [ ] **Step 4: Run** `.venv/bin/pytest -q` and ruff. Expected: PASS.
- [ ] **Step 5: Local run against the test branch** (owner approves first; it spends no neurons for `/health` and few for one `/ask`): `TEST_DB` in `DATABASE_URL`, `uvicorn --factory app.api:build_from_env --no-access-log`, then `curl` health, an `/ask` with a token created in Task 21, a bad token, and a 600-char question. Record the outputs in the ledger.
- [ ] **Step 6: Commit** `feat: FastAPI app with auth, CORS and error mapping`.

### Task 21: Admin commands

**Files:**
- Modify: `app/cli.py`, `tests/test_cli.py`
- Test: `tests/test_cli.py` (parsing and printing with a fake `Usage`; no DB)

**Interfaces:**
- Consumes: `Usage` (17), `Db` (16).
- Produces CLI commands: `init-db` (creates pieces/ingest_meta/usage tables), `token create LABEL` (prints the plain token and the ready-to-send chat link once, never again), `token revoke LABEL`, `token list`, `purge [--days N]` (default `limits.retention_days`), `serve` (runs uvicorn with the factory, `--no-access-log`).
- Rule: `token list` and all logs show labels, never tokens or hashes.

- [ ] **Step 1: Write failing tests** for argument parsing and output of each command with a fake `Usage`, including `test_token_create_prints_plain_token_once` and `test_token_list_never_prints_hashes`.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_cli.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the commands. Keep `cmd_ingest`/`cmd_eval` unchanged apart from Task 16's `Db` wiring.
- [ ] **Step 4: Run** `.venv/bin/pytest -q` and ruff. Expected: PASS.
- [ ] **Step 5: Commit** `feat: admin commands for tokens, schema, purge, serve`.

### Task 22: Gemini provider and AI judge

**Files:**
- Create: `app/llm/gemini.py`, `evals/judge.py`, `tests/llm/test_gemini.py`, `tests/evals/test_judge.py`
- Modify: `app/cli.py` (`judge` command), `.env.example` (already has `GEMINI_API_KEY`)
- Test: both test files (fake HTTP transport, as in `tests/llm/test_groq.py`)

**Interfaces:**
- Produces: `GeminiProvider(api_key: str, model: str = "gemini-3.5-flash-lite", client: httpx.Client | None = None)` with `.name = "gemini"` and `complete(system, user, max_tokens) -> Completion` (same failure rules as the other providers: non-200, empty, not finished -> `ProviderError`). **It is not in `answer_order`, and `build_adapter` rejects it there** (test this).
- `JudgeItem(question_id: str, question: str, reference_answer: str | None, answer: str, cited_texts: list[str])` built **only** from an eval-results file plus `evals/data/*.jsonl`. `judge_answer(item: JudgeItem, provider: GeminiProvider) -> JudgeVerdict(grounded: bool, correct: bool, reason: str)` using a fixed rubric prompt that asks for JSON only; unparsable output -> `JudgeVerdict` with `error` set, never a guess.
- `agreement(verdicts: list[JudgeVerdict], labels: list[HumanLabel]) -> dict` with precision and recall of `correct` against hand labels, and the count of items skipped for errors.
- CLI: `judge --results PATH --data evals/data/dev.jsonl --mode hybrid --out PATH` and `judge-agreement --verdicts PATH --labels PATH`.
- Privacy guard: the `judge` command takes no database argument and `JudgeItem` has no code path from `Usage`/the `questions` table; test that `evals/judge.py` does not import `app.usage`.

- [ ] **Step 1: Write failing tests**: `test_gemini_non_200_is_provider_error`, `test_gemini_empty_is_provider_error`, `test_build_adapter_rejects_gemini_in_answer_order`, `test_judge_parses_json_verdict`, `test_judge_bad_json_is_error_not_guess`, `test_judge_prompt_contains_reference_and_cited_text`, `test_agreement_precision_recall` (hand-made 6 verdicts and labels, assert exact numbers), `test_judge_module_does_not_import_usage`.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/llm/test_gemini.py tests/evals/test_judge.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the provider and judge. Study: LLM-as-judge pitfalls (position/verbosity bias, self-preference), and why the judge is a different model family from the answerer.
- [ ] **Step 4: Run** `.venv/bin/pytest -q` and ruff. Expected: PASS.
- [ ] **Step 5: One real judge run (owner approves; spends Gemini free quota, no Cloudflare neurons)** on `docs/evals/baseline-answers.json` only if that file holds answer text; otherwise the first run waits for a results file produced with Task 18's new `AnswerRow` fields (a user-chain eval run that spends neurons, so ask first). Hand-grading about 25 answers (spec §11) is the owner's task; the judge stays labelled "uncalibrated" in every report until `judge-agreement` has been run on those labels.
- [ ] **Step 6: Commit** `feat: Gemini provider (judge only) and AI judge with agreement metrics`.

### Task 23: Deploy to Render (Ohio) and smoke test

**Files:**
- Create: `render.yaml`, `scripts/smoke.py`, `docs/ops/deploy.md`
- Modify: `.github/workflows/ci.yml` (no deploy step; Render auto-deploys from `main`), `.env.example` (add `CORS_ORIGINS` only if it is env-driven; otherwise leave)
- Test: `scripts/smoke.py` run by hand; `tests/test_render_yaml.py` (parses `render.yaml`, asserts region `ohio`, free plan, Python version pinned, `--no-access-log` in the start command, and no secret values present)

**Interfaces:**
- `render.yaml`: one web service `citeable-docs-api`, `plan: free`, `region: ohio`, `PYTHON_VERSION` pinned to a 3.12.x, build `pip install .`, start `uvicorn --factory app.api:build_from_env --host 0.0.0.0 --port $PORT --no-access-log`, health check `/health`, env vars declared with `sync: false` for `DATABASE_URL`, `CF_ACCOUNT_ID`, `CF_API_TOKEN`, `GROQ_API_KEY`.
- `scripts/smoke.py URL TOKEN`: checks `/health`, `/ask` with a known in-docs question (answered, at least one citation whose URL is on the docs site) and an out-of-docs question (abstained), a wrong token (401), and prints wall-clock time of each so cold start is measured.

- [ ] **Step 1: Write the failing `tests/test_render_yaml.py`**, run it (FAIL), write `render.yaml`, run again (PASS).
- [ ] **Step 2: Write `docs/ops/deploy.md`**: the owner's dashboard steps (connect the GitHub repo, create the service in Ohio from the blueprint, paste the four secrets, set the Python version), how to roll back, how to read logs without tokens.
- [ ] **Step 3: Owner checkpoint — production database.** With the owner's explicit approval, run `.venv/bin/python -m app.cli init-db` and `.venv/bin/python -m app.cli ingest` against `DATABASE_URL` (the ingest re-embeds 229 pieces and spends Cloudflare neurons; it also writes `ingest_meta` and the new `docs_ref`). State the write and the estimated neurons before running.
- [ ] **Step 4: Owner creates the service; create the first token** (`token create owner-test`) and run `.venv/bin/python scripts/smoke.py <url> <token>`. Expected: all checks pass; record the cold-start time and the warm `/ask` time in `docs/ops/deploy.md`.
- [ ] **Step 5: Commit** `feat: Render blueprint, smoke script and deploy notes`. **Ask before pushing** (a push to `main` triggers the deploy).

### Task 24: Cold review, decision log, handoff

**Files:**
- Modify: `docs/decisions/decision-log.md` (D19: the four picks with the owner's one-sentence reasons and my calls a-e; D20: threshold value), `CLAUDE.md` (state after Plan 2, next = Plan 3), `docs/spikes/README.md` only if a spike-like finding appears.

- [ ] **Step 1: Cold review (independent, fresh context)** of the whole Plan 2 diff against this plan's Review Focus and the spec's §9 table. Fix Important findings; list deferred minors in the ledger.
- [ ] **Step 2: Neuron accounting.** From the question log and eval results, state the real neurons per question, and how many friend-questions per day the 8,000 budget allows. Mark estimates as estimates.
- [ ] **Step 3: Update the decision log and CLAUDE.md.** Owner writes the one-sentence reasons for D19.
- [ ] **Step 4: Pre-push scan** for secrets, job-hunt wording and copied docs text (per `public-repo-neutral-wording`); **ask before pushing.**

---

## Self-review

- **Spec coverage:** §5 flow (Tasks 19, 20); §9 table: injection and link defences stay from Task 13 and are exercised again in Task 22/23 smoke, burning quota (caps, Task 17), others calling the API (tokens + CORS, 17, 20), leaked keys (Render secrets, 23), privacy (no IP, retention, 17, 20, 21), harmful advice (Plan 3 UI); §10 judge (22); §13 Ohio, pool, cold start (16, 19, 23); Plan 2 requirements from CLAUDE.md: pool + first-connect retry (16), `ingest_meta` (16), `evidence_threshold` (18), judge (22).
- **Not in this plan, on purpose:** exact-match answer cache and streaming (wait for beta repeat rates, D16); chat page, /evals, failure browser, safe markdown rendering and the privacy notice (Plan 3); keep-alive pings.
- **Known weak spots to say out loud:** threshold and caps are tuned on 28 dev questions, not on friends' questions; the judge is uncalibrated until about 25 hand-graded answers exist; no load test beyond the parallel-cap test.
- **Type consistency:** `Db`/`DbUnavailable` (16) used by `Usage` (17) and `Store` (16); `Reservation`/`CapHit` (17) consumed by `AnswerService` (19); `AskError.status` mapped in `app/api.py` (20); `AnswerRow` new fields (18) consumed by `JudgeItem` (22).
