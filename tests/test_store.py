import os

import psycopg
import pytest

from app.store import Store
from ingest.models import Piece

DSN = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")

PROJECTS = ("t", "a", "b", "atomic", "anchors")


@pytest.fixture(autouse=True)
def clean_rows():
    """Delete only this file's test projects, before and after. The table itself stays."""
    def wipe():
        with psycopg.connect(DSN) as c:
            exists = c.execute("SELECT to_regclass('public.pieces')").fetchone()[0]
            if exists:
                c.execute("DELETE FROM pieces WHERE project = ANY(%s)", (list(PROJECTS),))
            c.execute("DROP INDEX IF EXISTS pieces_embedding_hnsw")
    wipe()
    yield
    wipe()


def piece(i: str, text: str, **kw) -> Piece:
    return Piece(id=i, page_slug="p", page_title="P", url="https://x/p/", anchor="a",
                 heading_path=("P", "H"), text=text, docs_ref="stable",
                 docs_version="2.0", last_updated="2020-01-01", **kw)


def unit(dim: int, hot: int) -> list[float]:
    v = [0.0] * dim
    v[hot] = 1.0
    return v


def test_roundtrip_and_vector_search():
    store = Store(DSN, dim=4)
    store.init_schema()
    pieces = [piece("p:0", "alpha"), piece("p:1", "beta")]
    store.replace_project_pieces("t", pieces, [unit(4, 0), unit(4, 1)])
    loaded = {p.id: p for p in store.load_pieces("t")}
    assert loaded["p:0"].heading_path == ("P", "H")
    assert loaded["p:1"].docs_version == "2.0"
    best = store.vector_search("t", unit(4, 1), k=1)
    assert best[0][0] == "p:1" and best[0][1] > 0.99


def test_replace_is_idempotent_and_scoped_to_project():
    store = Store(DSN, dim=4)
    store.init_schema()
    store.replace_project_pieces("a", [piece("p:0", "x")], [unit(4, 0)])
    store.replace_project_pieces("b", [piece("p:0", "y")], [unit(4, 0)])
    store.replace_project_pieces("a", [piece("p:0", "x2")], [unit(4, 0)])
    assert [p.text for p in store.load_pieces("a")] == ["x2"]
    assert [p.text for p in store.load_pieces("b")] == ["y"]


def test_embedding_count_must_match_pieces():
    store = Store(DSN, dim=4)
    store.init_schema()
    with pytest.raises(ValueError):
        store.replace_project_pieces("t", [piece("p:0", "x")], [])


def test_anchor_explicit_survives_the_database_and_so_does_the_citation_url():
    # cold review of tasks 6-9: without the column every deep link becomes a page-only citation
    store = Store(DSN, dim=4)
    store.init_schema()
    deep = piece("p:0", "x", anchor_explicit=True)
    plain = piece("p:1", "y")
    store.replace_project_pieces("anchors", [deep, plain], [unit(4, 0), unit(4, 1)])
    loaded = {p.id: p for p in store.load_pieces("anchors")}
    assert loaded["p:0"].anchor_explicit is True
    assert loaded["p:0"].citation_url == deep.citation_url == "https://x/p/#a"
    assert loaded["p:1"].anchor_explicit is False
    assert loaded["p:1"].citation_url == "https://x/p/"


def test_a_failed_replace_keeps_the_old_pieces():
    store = Store(DSN, dim=4)
    store.init_schema()
    store.replace_project_pieces("atomic", [piece("p:0", "old")], [unit(4, 0)])
    with pytest.raises(psycopg.Error):  # second piece has the wrong vector length
        store.replace_project_pieces(
            "atomic", [piece("p:0", "new0"), piece("p:1", "new1")], [unit(4, 0), [1.0, 0.0]])
    assert [p.text for p in store.load_pieces("atomic")] == ["old"]


def test_duplicate_ids_in_one_replace_fail_and_keep_the_old_pieces():
    store = Store(DSN, dim=4)
    store.init_schema()
    store.replace_project_pieces("atomic", [piece("p:0", "old")], [unit(4, 0)])
    with pytest.raises(psycopg.Error):
        store.replace_project_pieces(
            "atomic", [piece("p:0", "n1"), piece("p:0", "n2")], [unit(4, 0), unit(4, 1)])
    assert [p.text for p in store.load_pieces("atomic")] == ["old"]


def test_vector_search_only_sees_its_own_project_and_respects_k():
    store = Store(DSN, dim=4)
    store.init_schema()
    store.replace_project_pieces("a", [piece("p:0", "a0"), piece("p:1", "a1")],
                                 [unit(4, 0), unit(4, 1)])
    store.replace_project_pieces("b", [piece("q:0", "b0")], [unit(4, 0)])
    hits = store.vector_search("a", unit(4, 0), k=5)
    assert [h[0] for h in hits] == ["p:0", "p:1"]
    assert len(store.vector_search("a", unit(4, 0), k=1)) == 1
    assert store.vector_search("nobody", unit(4, 0), k=3) == []


def test_unicode_and_empty_optional_fields_roundtrip():
    store = Store(DSN, dim=4)
    store.init_schema()
    p = Piece(id="p:0", page_slug="p", page_title="Té", url="https://x/p/", anchor="",
              heading_path=("Té", "Ünï › ‘q’"), text="naïve – “quotes” ✓", docs_ref="stable",
              docs_version=None, last_updated=None)
    store.replace_project_pieces("t", [p], [unit(4, 2)])
    assert store.load_pieces("t") == [p]


def test_init_schema_refuses_a_table_with_a_different_vector_size():
    Store(DSN, dim=4).init_schema()
    with pytest.raises(ValueError, match="dimension"):
        Store(DSN, dim=8).init_schema()


def _index_exists() -> bool:
    with psycopg.connect(DSN) as c:
        return c.execute(
            "SELECT 1 FROM pg_indexes WHERE indexname = 'pieces_embedding_hnsw'").fetchone() is not None


def test_hnsw_index_is_created_idempotently_and_dropped_when_switched_off():
    Store(DSN, dim=4, vector_index="hnsw").init_schema()
    Store(DSN, dim=4, vector_index="hnsw").init_schema()  # second run must not fail
    assert _index_exists()
    Store(DSN, dim=4, vector_index="none").init_schema()
    assert not _index_exists()


def test_search_with_an_hnsw_index_matches_exact_search():
    exact = Store(DSN, dim=4)
    exact.init_schema()
    pieces = [piece(f"p:{i}", f"t{i}") for i in range(6)]
    embs = [[1.0, 0.1 * i, 0.0, 0.0] for i in range(6)]
    exact.replace_project_pieces("a", pieces, embs)
    exact.replace_project_pieces("b", [piece("q:0", "other")], [[1.0, 0.0, 0.0, 0.0]])
    want = exact.vector_search("a", [1.0, 0.0, 0.0, 0.0], k=4)
    ann = Store(DSN, dim=4, vector_index="hnsw")
    ann.init_schema()
    got = ann.vector_search("a", [1.0, 0.0, 0.0, 0.0], k=4)  # runs the per-query index settings
    assert [i for i, _ in got] == [i for i, _ in want] and len(got) == 4


def test_unknown_index_kind_is_rejected():
    with pytest.raises(ValueError, match="vector_index"):
        Store(DSN, dim=4, vector_index="ivfflat")
