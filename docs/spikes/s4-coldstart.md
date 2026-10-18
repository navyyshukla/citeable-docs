# S4: Render free cold start and memory with our dependencies

Status: **partial**. Two cold measurements done (2026-10-18: 24.2 s and 21.8 s). The plan asks for 3 on different occasions; the third is still to do.

## Setup (as deployed)
- Service `citeable-docs-spike`, Render **Free** instance, no card, no environment variables.
- Root directory `spikes/s4_coldstart`; app imports `fastapi, httpx, psycopg, pydantic, pyyaml` and serves `/health` (uptime and peak memory).
- Instance (read from the owner's Render dashboard): **0.1 CPU, 512 MB RAM**.
- Python: Render default **3.14.8** (local venv is 3.13.0; CI will use 3.12). All packages installed from prebuilt wheels.

## Measured

| Measurement | Result |
|---|---|
| Build and deploy, total (dashboard) | 1 min 04 s (pip install itself about 5 s) |
| Process start to "Application startup complete" (log) | about 10 s on 0.1 CPU |
| Warm response (3 requests, from the owner's machine region via Claude's shell) | 1.16 s (first, with connection set-up), then 0.39 s and 0.35 s |
| **Peak memory** | **72 MB** of 512 MB (14%) |
| **Cold request #1** (after about 24 min idle) | **24.2 s**; the reply showed `uptime_s` 2.3, so it was a fresh process |
| Request right after the cold one | 1.0 s |
| **Cold request #2** (run by the owner from their own machine, after a long idle) | **21.8 s**; `uptime_s` 1.9 (fresh process), peak memory 71.7 MB |
| Cold request #3 | not yet measured (owner to run tomorrow morning) |

Render's dashboard banner says a free instance "will spin down with inactivity, which can delay requests by 50 seconds or more". Our one sample came in at 24 s, well under that.

## Decision rule
Proceed if cold start is at most about 75 s and peak memory is at most about 60% of the RAM (about 307 MB). On the evidence so far: **meets both with wide margin (cold 24.2 s and 21.8 s; memory 72 MB of 512 MB).** Final call waits for sample 3 on a different occasion.

## Caveats (do not overstate)
- **One cold sample.** Cold time varies with Render's capacity; the banner's 50 s or more is a warning that real wake-ups can be longer.
- **This app is tiny.** It has no document index, no database connection, and no embedding or model calls. Real memory and startup will be higher. The 72 MB is the floor for our dependencies, not the app's cost.
- **0.1 CPU is the bigger limit than 512 MB RAM.** Anything we compute at start-up (for example building a keyword index from all pieces) runs on a tenth of a core. Prefer loading lazily or reading a prebuilt index.
- **Neon adds its own wake-up.** The database suspends after about 5 minutes idle, so the first question after a long gap can pay for both Render's and Neon's wake-up. Not measured here.
- **Python 3.14.8 on Render** is newer than what we test on. Before the real API deploys, pin Python on Render (for example to match CI at 3.12) with the `PYTHON_VERSION` setting.
- Measurements were taken from the Claude shell, not from a visitor's browser.

## To finish
- [x] Cold request #2.
- [ ] Cold request #3 on a different occasion (idle 20 min or more, then one `curl` to `/health`).
- [ ] Final decision: proceed with a "waking up" state in the UI, or trim.
