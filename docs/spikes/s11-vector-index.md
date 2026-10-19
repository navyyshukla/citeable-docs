# S11: exact vector search vs an HNSW index (2026-10-19)

Script `spikes/s11_index_benchmark.py`. Synthetic, clustered vectors (100 cluster centres plus noise, 768 dimensions like bge-base), generated inside Postgres, in a scratch table `bench_pieces` on the Neon **test** database only (dropped afterwards; database size 8 MB before and after). Three projects in one table, as the template allows: 1,000, 5,000 and 14,000 rows (20,000 in total). 20 queries per project; latency is server-side time from `EXPLAIN ANALYZE` (median of 5), so it leaves out the network. Recall@10 is measured against the exact answer taken before the index existed. HNSW defaults: m=16, ef_construction=64. pgvector 0.8.6.

| Rows in the project | Exact | HNSW, default (`ef_search` 40) | HNSW, `ef_search` 100 | HNSW + iterative scan | Plan chosen |
|---|---|---|---|---|---|
| 1,000 | 2.6 ms | 2.5 ms, recall 1.00 | 2.5 ms, 1.00 | 2.7 ms, 1.00 | exact via primary key (index ignored) |
| 5,000 | 12.4 ms | 0.3 ms, recall **0.93**, **9.2 rows back of 10** | 0.4 ms, 1.00 | 0.4 ms, 1.00 | index |
| 14,000 | 34.8 ms | 0.3 ms, 1.00 | 0.4 ms, 1.00 | 0.3 ms, 1.00 | index |

Index build: 5 s; index size **78 MB for 20,000 rows** (about as large as the data itself).

## Findings
1. **Exact search grows linearly and is already fast**: under 1 ms at the real 229 pieces (tiny run: 0.6 ms at 200 rows), 35 ms at 14,000. A line through the 14k point reaches 100 ms at roughly 40,000 pieces per project (an extrapolation, not measured). Answer generation takes seconds, so the index is irrelevant for VisiData and matters only for much larger docs sets.
2. **An index is about 100x faster at 5k+ rows** (0.3 ms), and the planner chose correctly by itself: exact path for the 1k project, index for 5k and 14k. Having the index does not slow small projects.
3. **A project filter on an HNSW index can return fewer than k rows.** With default settings, the 5k project returned 9.2 rows on average with recall 0.93. `ef_search` 100 or iterative scan fixed it here. This is the multi-project gotcha for a template; the store sets both per query.
4. **Neon's pooler shares backend sessions**: a temp table from an earlier run was still visible, so session-level `SET` is unreliable through it. The benchmark uses the direct endpoint (host without `-pooler`); the store sets `hnsw.*` with `SET LOCAL` inside a transaction.
5. **Cost is storage**: about 3.9 KB of index per row on a free tier with limited storage.

## What shipped
- `search.vector_index: none | hnsw` in `config/visidata.yaml` (default `none`, strict values).
- `Store(dsn, dim, vector_index="none")`: `init_schema()` creates the index when `hnsw`, drops it when `none`; `vector_search` sets `ef_search` 100 and iterative scan with `SET LOCAL` when `hnsw`.
- 4 new tests (index created, idempotent, dropped; search with the index matches exact search; unknown kind rejected; config rejects unknown kinds).

## Caveats (do not overstate)
- **Synthetic clustered data**, not real text embeddings. Real recall can be higher or lower; re-run on a real corpus before claiming recall numbers.
- 20 queries per project, one run, Neon free compute (shared), server-side times only; round trips from Render add to every query.
- The store tests use tiny tables where the planner scans instead of using the index, so they check that the index path and settings run and agree with exact search, not that the index is chosen.
- Not measured: index build time and size at 100k+ rows, writes while the index exists, `ivfflat` (rejected for now: needs training data and retuning as data changes).
