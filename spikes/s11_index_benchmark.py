"""Spike S11: exact vector search vs an HNSW index, at 1k / 5k / 14k pieces per project (20k rows in total).

Synthetic, clustered vectors generated inside Postgres (768 dimensions, like bge-base). Scratch table
`bench_pieces` on the TEST database only; dropped at the end. Latency is the server-side execution time
from EXPLAIN ANALYZE (no network). Recall is measured against the exact answer taken before the index exists.
"""
import json
import os
import statistics
import sys
import time

import numpy as np
import psycopg

# Neon's pooler shares backend sessions (temp tables and SET leak between users of the pool), so the
# benchmark needs the direct endpoint: the same host without "-pooler".
DSN = os.environ["TEST_DATABASE_URL"].replace("-pooler", "", 1)
DIM, K, NQ = 768, 10, 20
SIZES = {"bench_s": 1000, "bench_m": 5000, "bench_l": 14000}
if len(sys.argv) > 1 and sys.argv[1] == "tiny":
    SIZES = {"bench_s": 100, "bench_m": 200, "bench_l": 300}


def vec(a) -> str:
    return "[" + ",".join(f"{x:.5f}" for x in a) + "]"


def timed(label, fn):
    t = time.time()
    out = fn()
    print(f"{label}: {time.time() - t:.1f}s", flush=True)
    return out


SEARCH = ("SELECT id FROM bench_pieces WHERE project = %s "
          "ORDER BY embedding <=> %s::vector LIMIT %s")


def run_queries(c, queries, project):
    ids, ms, plan = [], [], ""
    for n, q in enumerate(queries[project]):
        ids.append([r[0] for r in c.execute(SEARCH, (project, vec(q), K)).fetchall()])
        if n < 5:  # timing on 5 queries per setting keeps the number of round trips small
            js = c.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + SEARCH, (project, vec(q), K)).fetchone()[0]
            ms.append(js[0]["Execution Time"])
            plan = plan or json.dumps(js[0]["Plan"])
    node = "Index Scan using bench_hnsw" if "bench_hnsw" in plan else (
        "Index Scan (primary key)" if "Index Scan" in plan else "Seq Scan / other")
    return ids, statistics.median(ms), node


def recall(found, truth):
    return statistics.mean(len(set(f) & set(t)) / K for f, t in zip(found, truth, strict=True))


with psycopg.connect(DSN, connect_timeout=60, autocommit=True) as c:
    c.execute("DROP TABLE IF EXISTS bench_pieces")
    before = c.execute("select pg_database_size(current_database())").fetchone()[0]
    try:
        c.execute(f"CREATE TABLE bench_pieces (project text NOT NULL, id text NOT NULL, "
                  f"embedding vector({DIM}) NOT NULL, PRIMARY KEY (project, id))")
        c.execute(f"""CREATE TEMP TABLE centers AS
            SELECT cid, (SELECT array_agg((random()-0.5)::float4 ORDER BY d)::vector({DIM})
                         FROM generate_series(1,{DIM}) d WHERE cid >= 0) AS v
            FROM generate_series(0,99) cid""")
        for proj, n in SIZES.items():
            timed(f"generate {proj} ({n} rows)", lambda: c.execute(
                f"""INSERT INTO bench_pieces
                    SELECT %s, 'p:' || g,
                           ce.v + (SELECT array_agg(((random()-0.5)*0.35)::float4)::vector({DIM})
                                   FROM generate_series(1,{DIM}) d WHERE g >= 0)
                    FROM generate_series(1,%s) g JOIN centers ce ON ce.cid = g %% 100""", (proj, n)))
        c.execute("ANALYZE bench_pieces")
        rng = np.random.default_rng(7)
        queries = {}
        for proj in SIZES:
            rows = c.execute("SELECT embedding::text FROM bench_pieces WHERE project=%s "
                             "ORDER BY random() LIMIT %s", (proj, NQ)).fetchall()
            base = np.array([json.loads(r[0]) for r in rows])
            queries[proj] = base + rng.normal(0, 0.05, base.shape)
        table_mb = c.execute("select pg_relation_size('bench_pieces')/1048576.0").fetchone()[0]
        print(f"table size {table_mb:.0f} MB (without index), rows {sum(SIZES.values())}")

        truth, exact = {}, {}
        for proj in SIZES:
            truth[proj], ms, node = run_queries(c, queries, proj)
            exact[proj] = (ms, node)

        c.execute("SET maintenance_work_mem = '512MB'")
        t = time.time()
        c.execute("CREATE INDEX bench_hnsw ON bench_pieces USING hnsw (embedding vector_cosine_ops)")
        build_s = time.time() - t
        idx_mb = c.execute("select pg_relation_size('bench_hnsw')/1048576.0").fetchone()[0]
        print(f"HNSW build {build_s:.0f}s, index size {idx_mb:.0f} MB (m=16, ef_construction=64)")

        print(f"\n{'project':9}{'rows':>7} | {'setting':26}{'median ms':>10}{'recall@10':>10}{'rows back':>10}  plan")
        for proj, n in SIZES.items():
            ms, node = exact[proj]
            print(f"{proj:9}{n:7d} | {'exact (before the index)':26}{ms:10.1f}{1.0:10.2f}{K:10d}  {node}")
            for label, sets in (("HNSW ef_search=40", ["hnsw.ef_search = 40"]),
                                ("HNSW ef_search=100", ["hnsw.ef_search = 100"]),
                                ("HNSW 40 + iterative scan", ["hnsw.ef_search = 40",
                                                              "hnsw.iterative_scan = relaxed_order"])):
                c.execute("RESET hnsw.iterative_scan")
                for s in sets:
                    c.execute("SET " + s)
                found, ms, node = run_queries(c, queries, proj)
                back = statistics.mean(len(f) for f in found)
                print(f"{'':9}{'':7} | {label:26}{ms:10.1f}{recall(found, truth[proj]):10.2f}{back:10.1f}  {node}")
    finally:
        c.execute("DROP TABLE IF EXISTS bench_pieces")
        after = c.execute("select pg_database_size(current_database())").fetchone()[0]
        print(f"\ncleanup done; database size before {before/1048576:.0f} MB, after {after/1048576:.0f} MB")
