# About and Help Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A small model call classifies every question; "what is VisiData" and "what can you do" questions get a fixed card written by us (config text, no search, no answer call), and every other question is answered exactly as today.

**Architecture:** A new `app/classify.py` returns `"about" | "help" | "normal"` and never raises. `AnswerService.ask` calls it right after the caps check, before the docs index is loaded; a card reply is logged as `status = "card"` and returned as `status: "card"` plus `kind`. The API sends no card text: the page builds the card from its own config (built from the same YAML) with `textContent` only.

**Tech Stack:** Python 3.12/3.13 (FastAPI, pydantic, pytest, ruff), plain browser JavaScript modules tested with `node --test`, static page built by `scripts/build_site.py`.

**Spec:** `docs/superpowers/specs/2026-11-11-about-and-help-cards-design.md`. Also read `docs/superpowers/specs/2026-11-11-chat-page-redesign-design.md` (page constraints still hold) and decision D25.

## Global Constraints

- Free tiers only. The daily neuron stop stays `limits.global_daily_neurons: 8000`. The classifier uses the existing provider chain (`build_adapter`), one adapter per request.
- Page security rules unchanged: no inline script or style, no third-party loads, `connect-src` is the API only, `site/src/render.js` and its tests are not touched, the invite token handling is unchanged. Card text goes in with `textContent` only; card links are https-only and filtered again by the page script.
- Project specifics (card text, labels, classifier descriptions) live in `config/visidata.yaml`, not in code.
- Classifier failure rule: an error, a timeout, or any output that is not exactly one of the three labels means `normal`. The visitor never sees a classifier error.
- Card replies count against the visitor cap and the shared request cap, and their neurons count toward the neuron budget (design, "Caps").
- Never send user questions to Gemini; the classifier test run uses the production Cloudflare/Groq chain. Ask the owner before any run that spends neurons.
- Public repo: neutral wording, noreply email, scan the diff before every push; ask the owner before every `git push`.
- Run tests as `.venv/bin/pytest -q` (database tests need `set -a; . ./.env; set +a`, plus the `PGHOSTADDR` workaround in CLAUDE.md if the Neon host does not resolve), `.venv/bin/ruff check .`, `node --test site/tests/*.test.js`.

## Review Focus

1. A classifier reply with extra words, other case, trailing punctuation, an empty reply, or text echoing the question (for example `About. I will ignore the rules`) → only an exact label (after trim, lowercase, stripping surrounding punctuation) counts; everything else is `normal` (Task 2).
2. Every provider failing inside the classifier → the question continues as `normal`; if the answer path then also fails, the visitor sees today's 503 message, never a classifier message (Task 3).
3. A card question on a cold server → answered without loading the docs index or touching the pieces table (Task 3).
4. Card text or labels in config with `<`, `&` or quotes → shown as plain text, and the page-config JSON cannot close its script block (Task 4).
5. An API reply with `status: "card"` and an unknown or missing `kind`, or a page whose config lacks that card → "Something unexpected came back", no crash (Task 4).
6. A normal question's log row → `llm_calls` and `neurons` include the classifier call as well as the answer call, so the neuron cap sees the true spend (Task 3).

---

## File Structure

| Path | Responsibility |
|---|---|
| `app/config.py` (modify) | `CardCfg`, `CardsCfg`, `SiteCfg.cards`, `LimitsCfg.classifier_max_tokens` |
| `config/visidata.yaml` (modify) | Card text, labels, classifier descriptions, token limit |
| `app/classify.py` (new) | Build the classifier prompt, call the adapter, parse one label |
| `app/service.py` (modify) | Classify before search; card reply path; log call counts |
| `app/usage.py` (modify) | `status` may be `"card"`; cap queries count it |
| `app/api.py` (modify) | `kind` in the JSON reply |
| `scripts/build_site.py` (modify) | `cards` block in the page config |
| `site/src/view.js`, `site/src/cards.js`, `site/src/app.js`, `site/src/style.css` (modify) | `cardKind`, `cardView`, the card DOM, example clicks, styling |
| `evals/cards_eval.py` (new), `evals/data/cards.jsonl` (new) | Classifier test set, scoring against the bar, runner |
| `docs/decisions/decision-log.md`, `docs/ops/deploy.md`, `CLAUDE.md` (modify) | D26, rollout note, state |

---

### Task 1: Config keys for the cards and the classifier

**Files:** Modify `app/config.py`, `config/visidata.yaml`; Test `tests/test_config.py`.

**Interfaces:**
- Produces: `CardCfg(label: str, description: str, paragraphs: list[str], links: bool = False, examples: bool = False)` (label, description non-empty; `paragraphs` has 1 to 4 non-empty items); `CardsCfg(about: CardCfg, help: CardCfg)`; `SiteCfg.cards: CardsCfg` (required); `LimitsCfg.classifier_max_tokens: int = 16`. All strict (extra keys rejected), like the rest of the config.
- Shipped YAML values: `about.label: "About VisiData · written by us, not from the docs"`, `about.description: "asks what VisiData is, or how to get started with it"`, `about.paragraphs: ["VisiData is a free tool that runs in the terminal and works like a spreadsheet for data files such as CSV. You drive it with the keyboard and can explore a file quickly."]`, `about.links: true`; `help.label: "What I can do"`, `help.description: "asks what this assistant can do, or how to use the assistant itself"`, `help.paragraphs`: the two sentences from the design's Help draft ("I answer how-to questions about VisiData using only its documentation, and I show you which pages I used. I don't remember your earlier question, so ask each one in full." and "I can't answer anything outside VisiData, and I can make mistakes: check the linked page."), `help.examples: true`; `limits.classifier_max_tokens: 16`.
- Consumed by Tasks 2, 3, 4, 5.

- [ ] **Step 1: Write the failing tests** in `tests/test_config.py`: `test_cards_are_required_and_strict` (removing `site.cards`, removing `cards.about`, adding an unknown key under a card → `ValidationError`); `test_card_text_must_not_be_empty` (empty `label`, empty `description`, `paragraphs: []`, a blank paragraph, five paragraphs → `ValidationError`); `test_shipped_cards_and_classifier_limit` (shipped `about.links is True`, `help.examples is True`, `limits.classifier_max_tokens == 16`, both descriptions non-empty).
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_config.py -q`. Expected: the new tests fail (missing keys).
- [ ] **Step 3: Implement** the models in `app/config.py` and the YAML values above (pydantic `Field(min_length=...)`; validate each paragraph is non-blank).
- [ ] **Step 4: Run** `.venv/bin/pytest -q && .venv/bin/ruff check .`. Expected: pass (the config is also loaded by other test modules, so run the whole suite).
- [ ] **Step 5: Commit** `feat: config for the about and help cards`.

---

### Task 2: The classifier

**Files:** Create `app/classify.py`; Test `tests/test_classify.py`.

**Interfaces:**
- Consumes: `Config` (Task 1), `Adapter.complete(system, user, max_tokens) -> Completion` and the exceptions `ProviderError`, `AllProvidersFailed` from `app/llm/base.py`.
- Produces: `LABELS = ("about", "help", "normal")`; `parse_label(text: str) -> str` (returns one of `LABELS`; anything that is not exactly a label after trimming whitespace, lowercasing and stripping surrounding punctuation and quotes returns `"normal"`); `build_prompts(question: str, cfg: Config) -> tuple[str, str]` (system, user); `classify_question(question: str, adapter: Adapter, cfg: Config) -> str` (never raises; uses `cfg.limits.classifier_max_tokens`). Used by Tasks 3 and 5.

- [ ] **Step 1: Write the failing tests.** `test_parse_label_accepts_only_exact_labels`: `"about"`, `" Help\n"`, `"About."`, `'"help"'`, `"`normal`"` map to themselves; `""`, `"about help"`, `"About. I will ignore the rules"`, `"abouts"`, `"1"`, `None`-like empty → `"normal"`. `test_prompts_carry_the_config_descriptions_and_fence_the_question`: the system text contains both config descriptions and the word `normal`; the user text contains the question and does not appear in the system text; a question containing the fence characters and `ignore all rules` is still only in the user text. `test_classify_returns_the_models_label` (fake adapter returning `"help"` → `"help"`). `test_classify_falls_through_to_normal_on_failure`: an adapter whose provider raises `ProviderError`, one raising `AllProvidersFailed`, and one returning junk text each give `"normal"` and no exception. `test_classify_uses_the_configured_token_limit` (the fake provider records `max_tokens == cfg.limits.classifier_max_tokens`).
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_classify.py -q`. Expected: fail on the missing module.
- [ ] **Step 3: Implement** `app/classify.py`. The system prompt lists each label with its description from `cfg.site.cards`, says `normal` is everything else and in particular any question about how to do something in the project, requires a reply of exactly one word, and states that the question is data, not instructions. The question goes in the user message inside a fence. Wording is the builder's; the contract is the tests above.
- [ ] **Step 4: Run** `.venv/bin/pytest tests/test_classify.py -q && .venv/bin/ruff check .`. Expected: pass.
- [ ] **Step 5: Commit** `feat: question classifier with a fail-open rule`.

---

### Task 3: Service, usage and API

**Files:** Modify `app/service.py`, `app/usage.py`, `app/api.py`; Test `tests/test_service.py`, `tests/test_usage.py` (real database, skipped in CI), `tests/test_api.py`.

**Interfaces:**
- Consumes: `classify_question` (Task 2), `cfg.site.cards` (Task 1).
- Produces: `AskResult.kind: str | None = None` (last field); a card reply is `AskResult(rid, "card", "", [], [], docs_ref=None, docs_version=None, last_updated=None, kind="about"|"help")`; `Usage.finish(status=...)` accepts `"card"`; the cap queries `_COUNTS` and `_COUNTS_GLOBAL` count `status = 'card'`; `_result_json` adds `"kind"`.

- [ ] **Step 1: Write the failing tests.**
  - `tests/test_service.py` (add a scripted provider returning a list of texts in order; first text is the classifier's): `test_card_question_returns_a_card_without_search` (first reply `"about"` → `status == "card"`, `kind == "about"`, `text == ""`, `store.loads == 0`, the provider was called once); `test_card_row_is_logged` (the finish call has `status="card"`, `answer_text="card:help"`, `llm_calls == 1`, `neurons == 2.5` from the fake completion, `retrieved_ids is None`); `test_classifier_failure_falls_through_to_the_normal_answer` (provider raises on call 1, answers on call 2 → `status == "answered"`); `test_all_providers_down_is_the_usual_503` (the existing `Down` provider → `AskError` 503 with today's message, and the logged error row); `test_normal_question_logs_classifier_and_answer_together` (replies `"normal"` then the answer: logged `llm_calls == 2` and `neurons == 5.0`); `test_card_counts_against_the_cap_path` (reserve is called before classify: with a `CapHit` the 429 is raised and the provider is never called).
  - `tests/test_usage.py` (real database, mirror the existing cap tests): `test_card_status_counts_against_visitor_and_global_caps`.
  - `tests/test_api.py`: the fake service returns a card result; assert the JSON has `status == "card"`, `kind == "about"`, `text == ""`, and that an answered reply still has `kind` null.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_service.py tests/test_api.py -q`. Expected: the new tests fail.
- [ ] **Step 3: Implement.** In `AnswerService.ask`: create the adapter (`self.make_adapter()`) before `_load_index`, inside the existing `try`; call `classify_question(q, adapter, self.cfg)`; for `"about"`/`"help"` call `usage.finish(rid, status="card", answer_text=f"card:{kind}", citations=[], top_score=None, provider=None, model=None, neurons=adapter.total_neurons if adapter.calls_made else None, llm_calls=adapter.calls_made, seconds=None, docs_ref=None, error=None)` and return the card result without loading the index. For `"normal"`, continue as today but log `llm_calls = a.llm_calls + classifier_calls`, where `classifier_calls = adapter.calls_made` read right after classifying. A `DbUnavailable` on the card finish is swallowed exactly as in the answer path. Update the `Literal` in `usage.finish`, the two cap SQL fragments in `usage.py`, `AskResult`, and `_result_json`.
- [ ] **Step 4: Run** the three test files, then the whole suite with the database: `set -a; . ./.env; set +a; .venv/bin/pytest -q && .venv/bin/ruff check .`. Expected: pass, 0 failures (about 39 database tests now run).
- [ ] **Step 5: Commit** `feat: card replies in the service, usage caps and API`.

---

### Task 4: The page

**Files:** Modify `scripts/build_site.py`, `site/src/view.js`, `site/src/cards.js`, `site/src/app.js`, `site/src/style.css`; Test `site/tests/view.test.js`, `tests/test_build_site.py`, `tests/test_site_css.py`.

**Interfaces:**
- Consumes: `cfg.site.cards` (Task 1), the API reply `{status: "card", kind}` (Task 3).
- Produces (page config): `cards: {about: {label, paragraphs: [str], links: [{text, url}], examples: [str]}, help: {...}}`; `links` is `start_links` when the card's `links` flag is true, else `[]`; `examples` is the first `STARTERS_SHOWN` starter questions when the card's `examples` flag is true, else `[]`.
- Produces (`view.js`): `cardKind(result: unknown): "about" | "help" | null` (non-null only when `result.status === "card"` and `kind` is one of those two strings); `cardView(kind: string, cards: unknown): {label: string, paragraphs: string[], links: {text,url}[], examples: string[]} | null` (null for an unknown kind, a missing card, an empty label or no paragraphs; links go through `startLinks`; examples keep only non-empty strings).
- Produces (`cards.js`): `buildAnswerCard(result, deps)` where `deps` also carries `cards` (the page-config block). A recognised card renders an `<article class="card card-info">` with a `.card-label`, one `<p>` per paragraph, a `links links-card` row, and an `.examples` column of `<button type="button" class="starter" data-question="…">`, all via `textContent`; no sources list and no feedback block. An unknown kind or missing card falls through to today's "Something unexpected came back" card.

- [ ] **Step 1: Write the failing tests.**
  - `site/tests/view.test.js`: `cardKind` returns the kind for `{status:"card", kind:"about"}` and `"help"`, and `null` for `{status:"card"}`, `{status:"card", kind:"x"}`, `{status:"answered", kind:"about"}`, `null`, a string; `cardView` returns the label, paragraphs, https-only links and non-empty examples for a good block, hostile text (`<img onerror=x>`, `&`) unchanged as plain strings, and `null` for an unknown kind, missing `cards`, an empty label, empty paragraphs.
  - `tests/test_build_site.py`: `test_page_config_carries_the_cards` (both cards present; about has the three start links and no examples; help has three examples equal to the first three starters and no links); `test_hostile_card_text_cannot_close_the_script_block` (put `</script><script>evil()</script>` and `<b>` in a card label and paragraph; the built page has no `</script><script>evil` and the JSON still parses back to the same strings).
  - `tests/test_site_css.py`: nothing new needed beyond the existing scoping test, which must keep passing for the new `.chat .card-label`, `.chat .examples` rules.
- [ ] **Step 2: Run** `node --test site/tests/*.test.js && .venv/bin/pytest tests/test_build_site.py -q`. Expected: the new tests fail.
- [ ] **Step 3: Implement** the page-config block in `build_site.py` (reuse the existing `start_links` list and `STARTERS_SHOWN`), `cardKind` and `cardView` in `view.js`, the card branch in `cards.js`, in `app.js` pass `cards: config.cards` in the `buildAnswerCard` deps and add one delegated click handler on `#answers` for `[data-question]` that does what the starter handler does (fill the box, resize it, focus it, do not send; share the code). Style: label small and muted like `.status`, examples as a column of the existing `.starter` look with `height: auto; min-height: 44px`, all selectors scoped under `.chat`.
- [ ] **Step 4: Run** `node --test site/tests/*.test.js && .venv/bin/pytest -q && .venv/bin/ruff check .`. Expected: pass. Then build (`python scripts/build_site.py page --out _site`), serve it with a no-cache header on a fresh port, and in a browser check both cards on a wide window and a 320 px frame, light and dark, with the console open (no CSP errors). A tiny local fake API that returns `{status:"card", kind:"about"}` and `{... "help"}` is enough; no real calls. Click an example: it fills the box and does not send.
- [ ] **Step 5: Commit** `feat: about and help cards on the page`.

---

### Task 5: Classifier test set and the owner-gated run

**Files:** Create `evals/cards_eval.py`, `evals/data/cards.jsonl`; Test `tests/evals/test_cards_eval.py`.

**Interfaces:**
- Consumes: `classify_question` (Task 2), `build_adapter` (`app/llm/build.py`), `evals/data/dev.jsonl` via `evals.schema.load_questions`.
- Produces: `CardQuestion(id: str, question: str, label: Literal["about","help","normal"], note: str | None)`; `load_card_questions(path) -> list[CardQuestion]` (rejects duplicate ids, unknown labels, empty text); `dev_negatives(path) -> list[CardQuestion]` (every `answerable` dev question as a `normal` control, ids prefixed `dev:`); `run_cards(questions, adapter_factory, cfg) -> list[CardRow]` where `CardRow(id, question, label, predicted, neurons, seconds)`; `score_cards(rows) -> CardScore(n, false_cards, positives_total, positives_right, passes: bool)` with `MAX_FALSE_CARDS = 0` and `MIN_POSITIVE_RATE = 0.9` (a false card is a `normal` question predicted `about` or `help`); CLI `python -m evals.cards_eval run --out evals/results/cards-<date>.json` and `... score --in <file>`.

- [ ] **Step 1: Write the failing tests** (`tests/evals/test_cards_eval.py`, no network, a fake adapter factory): `test_load_rejects_bad_rows` (duplicate id, label `"other"`, empty question); `test_dev_negatives_are_the_answerable_dev_questions_as_normal`; `test_score_counts_false_cards_and_positive_rate` (a hand-made row list: one `normal` predicted `about` → `false_cards == 1`, `passes is False`; 9 of 10 positives right and no false cards → `passes is True`; 8 of 10 → `passes is False`); `test_shipped_card_questions_cover_the_traps` (the shipped file has at least 10 `about`, 10 `help`, 15 `normal`, and the `normal` set includes these exact traps: "what is a frequency table", "how do I use the join command", "what does the help key do", "how do I use visidata to sort a column"); `test_run_uses_a_fresh_adapter_per_question_and_reports_neurons`.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/evals/test_cards_eval.py -q`. Expected: fail on the missing module and file.
- [ ] **Step 3: Implement** `evals/cards_eval.py` and write `evals/data/cards.jsonl` (questions only, public text, no answers): about 12 `about` and 12 `help` phrasings in varied wording (including very short ones such as "help" and "what is this"), and at least 15 `normal` questions, the four traps above among them. The runner takes questions from `cards.jsonl` plus `dev_negatives`, builds an adapter per question with `build_adapter(cfg, os.environ)`, and writes one JSON file with the rows, the score and the total neurons.
- [ ] **Step 4: Run** `.venv/bin/pytest -q && .venv/bin/ruff check .`. Expected: pass (no network used).
- [ ] **Step 5: Commit** `feat: classifier test set and scoring`.
- [ ] **Step 6: Owner-gated run (stop and ask first; it spends about 2 neurons per question, under 150 in total).** After the owner agrees, run `set -a; . ./.env; set +a; .venv/bin/python -m evals.cards_eval run --out evals/results/cards-<date>.json` (set `PGHOSTADDR` only if a database is needed; this run needs none), then `score`. Expected: `passes` is true. Report the confusion table, the neurons and the seconds per call. If it fails: do not ship; list the misrouted questions, tune the classifier prompt in `app/classify.py` test-first, and ask the owner before a second run. If it still fails, stop and put the owner's alternatives (phrase lists, or classify only refusals) to them.
- [ ] **Step 7: Commit** the results file only if the owner wants it kept (it is git-ignored under `evals/results/` by default).

---

### Task 6: Docs, rollout note and whole-suite check

**Files:** Modify `docs/decisions/decision-log.md` (add **D26**), `docs/ops/deploy.md`, `CLAUDE.md`.

- [ ] **Step 1: Run the whole suite with the database:** `set -a; . ./.env; set +a; node --test site/tests/*.test.js && .venv/bin/ruff check . && .venv/bin/pytest -q`. Expected: all pass.
- [ ] **Step 2: Write the docs.** D26: the cards decision with the owner's reasons from the design, the owner's choice of a model on every question against the recommendation (refusals only), the measured classifier result from Task 5 (neurons and seconds per call, the confusion table, the bar), the cap choice, and the open points. `deploy.md`: the new `site.cards` and `limits.classifier_max_tokens` keys; how to edit card text; the rollout order (API and page ship from one push, an old page may show "Something unexpected came back" for card questions for a minute or two); the new log status `card`. `CLAUDE.md`: state after this plan.
- [ ] **Step 3: Live check (stop and ask the owner first; it sends real questions).** As in Plan 3c: a local API with `DEV_CORS_ORIGIN`, a temporary config whose `site.api_base_url` points at it, a throwaway token written only to a git-ignored file, the owner asks "what is visidata", "what can you do", a normal how-to question and an off-topic one. Verify the log rows (`status` card, answered, abstained; neuron and call counts), revoke the token, stop the servers, delete the files.
- [ ] **Step 4: Commit** `docs: Plan 4 decision and state`. **Stop and ask the owner** before pushing; scan the whole diff for personal or circumstance wording first.
