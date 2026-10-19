"""Postgres + pgvector storage for pieces."""
import psycopg

from ingest.models import Piece


def _vec(v: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in v) + "]"


_INDEX_NAME = "pieces_embedding_hnsw"
_VECTOR_INDEXES = ("none", "hnsw")


class Store:
    def __init__(self, dsn: str, dim: int, vector_index: str = "none"):
        if vector_index not in _VECTOR_INDEXES:
            raise ValueError(f"vector_index must be one of {_VECTOR_INDEXES}, got {vector_index!r}")
        self.dsn, self.dim, self.vector_index = dsn, dim, vector_index

    def _conn(self) -> psycopg.Connection:
        # Neon free suspends after idle time; the first connection can take a while to wake it
        return psycopg.connect(self.dsn, connect_timeout=60)

    def init_schema(self) -> None:
        with self._conn() as c:
            c.execute("CREATE EXTENSION IF NOT EXISTS vector")
            c.execute(f"""
                CREATE TABLE IF NOT EXISTS pieces (
                    project TEXT NOT NULL,
                    id TEXT NOT NULL,
                    page_slug TEXT NOT NULL,
                    page_title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    anchor TEXT NOT NULL,
                    anchor_explicit BOOLEAN NOT NULL DEFAULT FALSE,
                    heading_path TEXT[] NOT NULL,
                    text TEXT NOT NULL,
                    docs_ref TEXT NOT NULL,
                    docs_version TEXT,
                    last_updated TEXT,
                    embedding vector({self.dim}) NOT NULL,
                    PRIMARY KEY (project, id)
                )""")
            # CREATE TABLE IF NOT EXISTS keeps an old table as it is: a changed embedding size
            # in the config must be an error, not a silent mismatch.
            (have,) = c.execute(
                """SELECT atttypmod FROM pg_attribute
                   WHERE attrelid = 'pieces'::regclass AND attname = 'embedding'""").fetchone()
            if have != self.dim:
                raise ValueError(
                    f"pieces.embedding has dimension {have} but the config says {self.dim}; "
                    "re-create the table to change the embedding size")
            # The configured setting is the wanted state: create the index, or drop it when off.
            if self.vector_index == "hnsw":
                c.execute(f"CREATE INDEX IF NOT EXISTS {_INDEX_NAME} "
                          "ON pieces USING hnsw (embedding vector_cosine_ops)")
            else:
                c.execute(f"DROP INDEX IF EXISTS {_INDEX_NAME}")

    def replace_project_pieces(self, project: str, pieces: list[Piece],
                               embeddings: list[list[float]]) -> None:
        if len(pieces) != len(embeddings):
            raise ValueError(f"{len(pieces)} pieces but {len(embeddings)} embeddings")
        # One transaction: if any insert fails, the delete is rolled back and the old pieces stay.
        with self._conn() as c:
            c.execute("DELETE FROM pieces WHERE project = %s", (project,))
            with c.cursor() as cur:
                cur.executemany(
                    """INSERT INTO pieces (project, id, page_slug, page_title, url, anchor,
                           anchor_explicit, heading_path, text, docs_ref, docs_version,
                           last_updated, embedding)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)""",
                    [(project, p.id, p.page_slug, p.page_title, p.url, p.anchor,
                      p.anchor_explicit, list(p.heading_path), p.text, p.docs_ref,
                      p.docs_version, p.last_updated, _vec(e))
                     for p, e in zip(pieces, embeddings, strict=True)],
                )

    def load_pieces(self, project: str) -> list[Piece]:
        with self._conn() as c:
            rows = c.execute(
                """SELECT id, page_slug, page_title, url, anchor, anchor_explicit, heading_path,
                          text, docs_ref, docs_version, last_updated
                   FROM pieces WHERE project = %s ORDER BY id""", (project,)).fetchall()
        return [Piece(id=r[0], page_slug=r[1], page_title=r[2], url=r[3], anchor=r[4],
                      anchor_explicit=r[5], heading_path=tuple(r[6]), text=r[7], docs_ref=r[8],
                      docs_version=r[9], last_updated=r[10]) for r in rows]

    def vector_search(self, project: str, embedding: list[float], k: int) -> list[tuple[str, float]]:
        with self._conn() as c, c.transaction():
            if self.vector_index == "hnsw":
                # Per-query index settings must be SET LOCAL inside this transaction: Neon's pooler
                # shares sessions, so a plain SET could leak to, or vanish from, another query.
                # Without these, a project filter on the index can return fewer than k rows (S11).
                c.execute("SET LOCAL hnsw.ef_search = 100")
                c.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
            rows = c.execute(
                """SELECT id, 1 - (embedding <=> %s::vector) AS sim
                   FROM pieces WHERE project = %s
                   ORDER BY embedding <=> %s::vector LIMIT %s""",
                (_vec(embedding), project, _vec(embedding), k)).fetchall()
        return [(r[0], float(r[1])) for r in rows]
