# S9: database latency from this machine (2026-10-19, Task 10)

Measured with `psycopg` against the Neon test endpoint (us-east-2, Ohio, through Neon's pooler), from the owner's laptop via Claude's shell.

| What | Time |
|---|---|
| New connection (TLS and login) | about 1.4 to 1.7 s |
| One query round trip on an open connection | about 0.25 s |
| 50 inserts in one batch (`executemany`) | about 0.5 s |

Effect on the test suite: the 9 store tests take about 130 s, almost all of it connection set-up (they run only with `TEST_DATABASE_URL` set; CI skips them).

## What it means for Plan 2 (estimates, not production measurements)
- `Store` opens a new connection per call. That is fine for ingest (one replace) and for tests, but per question it would add the connection cost to every answer. Plan 2 needs a **connection pool** (reuse open connections) and should keep the number of database round trips per question small (one vector search, one piece load at start-up).
- Round-trip time depends on distance. **Render's region is not recorded anywhere.** If it is not Ohio (US East), every query pays more than here. Check the Render dashboard and, if needed, create the real API service in Ohio.
- Neon suspends after 5 minutes idle, so the first connection after a gap can be slower than the numbers above (not measured here).
- The whole piece list (229 rows) can be loaded once at start-up, so only the vector search runs per question.

## Caveats
- Four samples, one machine, one afternoon. The Render-to-Neon path is untested.
