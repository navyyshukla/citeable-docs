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

## Measured on first deploy (fill in)

| Step | Seconds |
|---|---|
| health after idle (cold start) | |
| first /ask (loads the index) | |
| later /ask (warm) | |

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

`localhost` is not in the production CORS list (`api.cors_origins`). Plan 3 adds a local origin when
the chat page is developed, and removes it before the beta.
