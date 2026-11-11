# Deploying the API (Render, Ohio)

The service is defined in `render.yaml`. Secrets are set in the Render dashboard, never in git.

## One-time setup (owner, in the Render dashboard)

1. New -> Blueprint -> pick the `citeable-docs` repo, branch `main`. Render reads `render.yaml`
   and proposes one service, `citeable-docs-api`, free plan, region **Ohio**.
2. When it asks for the four secrets, paste them from your local `.env`:
   `DATABASE_URL`, `CF_ACCOUNT_ID`, `CF_API_TOKEN`, `GROQ_API_KEY`. Do not paste them anywhere else.
3. Check the build log's first lines show **Python 3.12.x**. `PYTHON_VERSION` is pinned to
   `3.12.11` in `render.yaml`; if Render says that version does not exist, change the value to the
   newest 3.12 it lists and commit (unverified until the first build).
4. Open `https://<service>.onrender.com/health`: expect `{"ok": true}` (the first call after
   idle takes about 20 s: that is the cold start).

## First deploy order (production database)

1. `python -m app.cli init-db` (creates the usage tables; pieces already exist).
2. `python -m app.cli ingest` (required: the API refuses to serve until the `ingest_meta` row exists; re-embeds about 229 pieces, spends Cloudflare neurons, writes
   `ingest_meta` and the new `docs_ref`). Ask before running.
3. `python -m app.cli token create owner-test` and copy the token once.
4. `SMOKE_TOKEN=<token> python scripts/smoke.py https://<service>.onrender.com`; paste the timings below. (The token is read from the environment so it stays out of shell history. The two smoke questions are written to the question log and count against that token's cap.)

## Measured on first deploy (2026-10-25, laptop to Render Ohio, smoke 5/5 pass)

Build log: Python 3.12.11 via `PYTHON_VERSION`. The service was already warm (a `/health` call minutes
earlier), so the cold-start row is still to be measured after 15+ minutes idle.

| Step | Seconds |
|---|---|
| health after idle (cold start) | not measured yet (Render says 50 s or more) |
| health (warm) | 0.3 |
| first /ask (loads the index) | 2.8 |
| out-of-docs /ask (abstains, no model call) | 0.6 |

## Day to day

- Invite a friend: `python -m app.cli token create <name>`; send them the token (shown once).
- Remove a friend: `python -m app.cli token revoke <name>`.
- See who is active: `python -m app.cli token list` (labels and counts only).
- Delete old questions: `python -m app.cli purge` (default 30 days).
- Roll back: Render dashboard -> the service -> Events -> pick the earlier deploy -> Rollback.
- Logs: Render dashboard -> Logs. The app logs no tokens, and the access log is off, so client IPs
  are not written by us (Render's own infrastructure may still keep connection data).

## Redeploy after re-ingesting docs

The running service keeps the pieces it loaded at its first question. After `ingest`, restart the
service (dashboard -> Manual Deploy -> Restart) so it reloads them.

## Local front-end development

`localhost` is not in the production CORS list (`api.cors_origins`). To try the page against a
local API, set one extra origin through the environment instead of editing the list:

```
DEV_CORS_ORIGIN=http://localhost:8080 .venv/bin/uvicorn app.api:app --factory
python scripts/build_site.py page --out _site && python -m http.server -d _site 8080
```

Build a copy of the page whose `site.api_base_url` points at the local API (a temporary config
file; never commit it). Create a throwaway invite with `token create --label <name>`, open the
printed link, and revoke the token afterwards. Production never sets `DEV_CORS_ORIGIN`.

### Page text and links (config keys)

The opening screen's text lives in `config/visidata.yaml` under `site:`: `brand` (top bar),
`greeting`, `tagline` (one plain sentence for newcomers) and `about_url` (the "What is VisiData?"
link) are required; `intro_video_url` is optional and the "Intro video" button is simply left out
when it is not set. `getting_started_url` (optional) is the docs' Getting Started page: it is
shown with the other two links under any question the assistant could not answer ("New to
VisiData? Start here"). Every URL here must start with `https://` and contain no spaces or quote characters
(the build refuses anything else). The welcome screen shows the first three `starter_questions`.
The old `intro` key is gone.

### About and Help cards, and the question classifier

`site.cards.about` and `site.cards.help` in `config/visidata.yaml` hold the two fixed cards: `label`,
`description` (tells the classifier which questions belong to it), `paragraphs` (1 to 4, plain text),
and two switches, `links` (show the start-here links) and `examples` (show the first three starter
questions as clickable examples). Edit the text there; no code change is needed. `limits.classifier_max_tokens`
(16) is the reply budget and `limits.classifier_timeout_seconds` (5) the longest wait for the one-word classifier call that runs on every question (applied to each connection phase separately, so a slow provider can take up to about 10 s, and a 3-provider chain up to about 30 s). The page
builds the cards from its own copy of this config, so a text change needs the page to be rebuilt
(a push to `main` does it). The API sends only `status: "card"` and `kind`.
Rollout: the API (Render) and the page (Pages) deploy separately from one push; for a minute or two
an old page may show "Something unexpected came back" for a card question. Card questions are logged
with status `card` and count against the daily caps. To re-check the classifier after changing
descriptions or the prompt: `python -m evals.cards_eval run --out evals/results/cards-<date>.json`
(about 90 neurons; read the score with `... score --in <file>`; the bar is 0 false cards and 90% right).

### Previewing the page and the themes

After `python scripts/build_site.py page --out _site`, serve `_site` as above and open it. Dark mode
follows the device setting; the moon/sun button in the top bar flips it and remembers the choice
in that browser only. To see both themes without changing the device setting, press the button, or
(in the browser console) set `document.documentElement.dataset.theme = "dark"` or `"light"`.
`/evals` follows the device setting only (no button). A browser may keep an old copy of the page's
script files while you iterate: use a private window or serve with a no-cache header.

## Enabling Pages (owner action, once)

The page is a static site on GitHub Pages, deployed by `.github/workflows/pages.yml` on pushes to
`main` that touch `site/**`, `config/visidata.yaml` or `scripts/build_site.py`. Before the first
deploy: repository Settings -> Pages -> Source: **GitHub Actions**. The workflow uses no secrets.
Check the live address matches `site.url` in `config/visidata.yaml` (invite links are built from it).

## Building and reviewing `evals.html`

The `/evals` page is built on the owner's machine from saved results, then committed as
`site/public/evals.html` (the Pages workflow copies `site/public/*` next to `index.html`):

```
python scripts/build_site.py evals --run evals/results/<run>.json \
  --labels evals/results/human-labels-v2.jsonl --verdicts evals/results/<verdicts>.json \
  --out site/public/evals.html
```

It reads the pieces from the database read-only (`DATABASE_URL`) and spends no neurons or Gemini
calls. Add `--run` once per saved run, `--trap <traps.json> --trap-verdicts <verdicts.json>` for the
judge trap summary. Before committing, open the file and check: every rate shows k/n and a range;
the judge is labelled "rough filter"; generated questions appear apart, as "AI-checked only,
not human-checked"; the judge verdicts file matches the run shown. The page contains only
paraphrased eval questions and the assistant's own answers, never friends' questions.
