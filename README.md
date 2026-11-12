# citeable-docs

An unofficial, free "ask the docs" assistant for [VisiData](https://www.visidata.org/), a terminal tool for exploring data files like spreadsheets. It answers **only from VisiData's documentation**, shows a citation link for every answer, and says "I couldn't find this" (with the closest pages) when the docs do not cover the question.

**Not affiliated with VisiData.** This is an independent project. VisiData and its documentation are licensed under GPLv3 and belong to their authors; this repository does not contain copies of the documentation.

## Live state

| Part | Where | State |
|---|---|---|
| Chat page | https://navyyshukla.github.io/citeable-docs/ | live, **invite-only** (needs a personal invite link; a closed beta is planned) |
| Test results page | https://navyyshukla.github.io/citeable-docs/evals.html | live, public |
| API | `https://citeable-docs-api.onrender.com` (free tier, Ohio) | live; the first request after idle can take up to about 30 seconds |
| Docs indexed | VisiData `stable` docs, 229 pieces | live |

What a visitor gets:
- **A docs question** ("how do I rename a column?") gets a short answer with numbered source links to the docs page and section it came from.
- **"What is VisiData?"** shows a fixed card written by this project (labelled as not from the docs) with links to the website, an intro video and the docs' Getting Started page.
- **A question about the assistant itself** ("what can you do?", "why can't you answer outside VisiData?") gets a short model reply written only from a fact sheet in the config; if the fact sheet does not cover it, a fixed card is shown.
- **Anything the docs do not cover** is refused, never guessed.

## How it works

```
 visitor (static page on GitHub Pages, invite token in the link after '#')
        │  question
        ▼
 API on Render ──► check token and daily caps ──► classifier (one tiny model call)
        │                                              ├─ "what is VisiData"  ─► fixed About card
        │                                              ├─ about the assistant ─► Help card (+ model reply from a fact sheet)
        │                                              └─ anything else
        ▼
 search the docs (keyword + exact key path + meaning search, rank-fused) ─► enough evidence?
        │ no ─► "I couldn't find this" + closest pages (no model call)
        ▼ yes
 answer model (Cloudflare Workers AI, with Groq as the fallback; if both fail, an honest "busy" message)
        ▼
 output rules enforced: must cite a piece it was given, links limited to the docs' own pages
        ▼
 page shows it through a safe renderer (no HTML from the model is ever inserted)
```

- **Docs are ingested at deploy time**, chunked by heading, embedded and stored in Postgres with pgvector (Neon). They are never committed here.
- **Free tiers only, no card:** GitHub Pages, Render, Neon, Cloudflare Workers AI (about 10,000 neurons a day, the API stops at 8,000), Groq. Gemini's free tier is used only to grade test answers, and only with public test questions: user questions are never sent to it.
- **Privacy:** questions and answers are kept for 30 days and then deleted by a daily scheduled job (with a safety net in the API that purges once a day when it gets a question); invite tokens are stored only as hashes; the server's access log is off. The page's privacy notice lists every provider a question is sent to.
- **Safety:** the page has a strict content-security policy (no third-party loads, no inline scripts); model text is shown as plain text or through a renderer that only allows citation links to the docs; the assistant has no tools and no private data.

## Does it work? (read `/evals` before trusting any number)

The `/evals` page shows every measured result with its count, range and caveats. In short:
- **It refuses what the docs do not cover:** 60 of 60 hand-written questions the docs do not answer (near-miss features, other tools, off-topic, attempts to override its rules, vague questions, code requests) were refused in each of 3 runs, plus 9 of 9 on the development set in each of 5 runs. Nothing was answered by guessing.
- **On 98 questions nobody tuned for** (a sealed set, generated from docs pieces no earlier test used and kept only when two independent AI readers agreed): it answered 74 (76%, 95% range 66 to 83%) and cited the right docs page in 66 of those 74; 24 got "not found", mostly because the right page was not found by search. No invalid citations in any run.
- **Classifier and cards:** 62 of 62 test questions routed correctly with the main model, with no real how-to question sent to a card.
- **The backup models were measured too** and one was removed: a smaller model answered 9 of 60 questions the docs do not cover, so the answer chain is now the main model and Groq, then an honest "busy" message.

These sets are small: one question moves a rate by about 5 points. The held-out labels are AI-checked only and no human has graded those answers yet; the AI judge used for part of the checking is a rough filter that cannot see docs errors; and the docs contain at least one error the assistant repeats (the sort page's `[` and `]` keys). Friends' questions in the beta are the next held-out check.

Known limits: no memory between questions (follow-up questions like "what else?" cannot be answered yet); free-tier cold starts; search misses some plainly worded questions; answer quality depends on what the docs say.

## Repository map

| Path | What is in it |
|---|---|
| `app/` | the API: config, search, answer rules, classifier, help reply, usage caps, providers |
| `ingest/` | fetch, clean, chunk and embed the docs |
| `evals/` | question sets (questions only), runners, the judge, the `/evals` report builder |
| `site/` | the static chat page (plain JavaScript modules), its styles and template |
| `config/visidata.yaml` | everything specific to VisiData: models, limits, page text, cards, fact sheet |
| `scripts/` | page build, smoke test |
| `tests/`, `site/tests/` | Python and JavaScript tests |
| `docs/decisions/decision-log.md` | why each decision beat its alternatives (D1 to D27) |
| `docs/superpowers/specs/`, `plans/` | the written designs and implementation plans |
| `docs/ops/deploy.md` | deploying, running the page locally, editing the cards and fact sheet |

Project-specific text lives in `config/`, so the code could be pointed at another project's docs by changing the config and re-ingesting.

## Run it yourself

Needs Python 3.12 or newer (tested on 3.12 and 3.13), Node (for the page tests), a Neon Postgres database with pgvector, and free accounts at Cloudflare and Groq.

```
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

Create a `.env` file (single-quoted values, never committed) with: `DATABASE_URL`, `CF_ACCOUNT_ID`, `CF_API_TOKEN`, `GROQ_API_KEY`; `GEMINI_API_KEY` for the judge; `TEST_DATABASE_URL` for the database tests.

```
python -m app.cli init-db                  # create the tables
python -m app.cli ingest                   # fetch, embed and store the docs (spends Cloudflare neurons)
python -m app.cli token create <label>     # prints a personal invite link, once
uvicorn --factory app.api:build_from_env   # run the API locally
python scripts/build_site.py page --out _site && python -m http.server -d _site 8080
```

Tests and checks: `.venv/bin/pytest -q` (database tests are skipped without `TEST_DATABASE_URL`), `node --test site/tests/*.test.js`, `.venv/bin/ruff check .`. Deployment, local page development with a local API, and the evals are described in [`docs/ops/deploy.md`](docs/ops/deploy.md).

## About this repository

Developed with an AI coding assistant, with every design decision, trade-off and measured result recorded in the decision log and the written specs and plans. Measurement scripts from the early design phase are kept in `spikes/` (throwaway, not linted).

## License

Code: MIT (see `LICENSE`).
