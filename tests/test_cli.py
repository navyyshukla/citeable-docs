from types import SimpleNamespace

import pytest

from app.cli import main

SHA = "abcdef0123456789abcdef0123456789abcdef01"
DOCS = {"join.md": "## How to join\n\nsteps\n", "rows.md": "## Rows\n\nsort\n"}


def test_ingest_dry_run_prints_counts_without_network(monkeypatch, capsys):
    monkeypatch.setattr("app.cli.fetch_docs_and_commit", lambda repo, ref, path: (DOCS, SHA))
    assert main(["ingest", "--dry-run", "--config", "config/visidata.yaml"]) == 0
    out = capsys.readouterr().out
    assert "2 pages" in out and "2 pieces" in out and "ref=stable" in out


class FakeStore:
    """Stands in for Store; records whether the replace was attempted."""
    def __init__(self, stored: int, pages: tuple = ("p",)):
        self.stored, self.pages, self.replaced = stored, pages, False

    def init_schema(self):
        pass

    def load_pieces(self, project):
        return [SimpleNamespace(page_slug=self.pages[i % len(self.pages)])
                for i in range(self.stored)]

    def replace_project_pieces(self, project, pieces, vectors):
        self.replaced, self.pieces = True, pieces


FAKE_PIECES = [SimpleNamespace(page_slug="p", search_text="t")] * 150


def _wire(monkeypatch, store):
    monkeypatch.setenv("CF_ACCOUNT_ID", "a")
    monkeypatch.setenv("CF_API_TOKEN", "t")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setattr("app.cli.fetch_docs_and_commit", lambda repo, ref, path: (DOCS, SHA))
    monkeypatch.setattr("app.cli.embed_texts", lambda cf, m, texts, b: [[0.0]] * len(texts))
    monkeypatch.setattr("app.cli.Store", lambda dsn, dim, **kw: store)


def test_ingest_refuses_to_replace_with_far_fewer_pieces(monkeypatch, capsys):
    store = FakeStore(stored=230)
    _wire(monkeypatch, store)
    assert main(["ingest"]) == 1
    assert not store.replaced
    assert "refusing" in capsys.readouterr().err


def test_ingest_refuses_tiny_result_even_when_database_is_empty(monkeypatch):
    store = FakeStore(stored=0)
    _wire(monkeypatch, store)
    assert main(["ingest"]) == 1  # minimum is 100 pieces
    assert not store.replaced


def test_ingest_replaces_when_count_is_plausible(monkeypatch):
    store = FakeStore(stored=120)
    _wire(monkeypatch, store)
    monkeypatch.setattr("app.cli.build_pieces", lambda files, cfg, docs_ref=None: FAKE_PIECES)
    assert main(["ingest"]) == 0
    assert store.replaced


def test_eval_without_pieces_fails_cleanly(monkeypatch, capsys):
    store = FakeStore(stored=0)
    _wire(monkeypatch, store)
    assert main(["eval", "--out", "x.json"]) == 1
    assert "ingest" in capsys.readouterr().err


def test_eval_writes_partial_results_when_a_later_mode_crashes(monkeypatch, tmp_path):
    from ingest.models import Piece
    piece = Piece(id="join:0", page_slug="join", page_title="J", url="https://x/", anchor="",
                  heading_path=("Join",), text="Type `&` to join.", docs_ref="stable",
                  docs_version=None, last_updated=None)
    store = FakeStore(stored=1)
    store.load_pieces = lambda project: [piece]
    store.vector_search = lambda *a: []
    _wire(monkeypatch, store)
    q = tmp_path / "q.jsonl"
    q.write_text('{"id":"a","question":"what does & do?","answerable":true,"gold_page":"join",'
                 '"source":"synthetic","split":"dev"}\n')

    def boom(*a, **k):
        raise RuntimeError("quota gone")

    monkeypatch.setattr("app.cli.embed_texts", boom)
    out = tmp_path / "r.json"
    with pytest.raises(RuntimeError):
        main(["eval", "--modes", "keyword,hybrid", "--data", str(q), "--out", str(out)])
    import json
    data = json.loads(out.read_text())
    assert list(data["retrieval"]) == ["keyword"] and data["meta"]["crashed"] == "quota gone"


def test_ingest_refuses_when_stored_pages_vanish_unless_allowed(monkeypatch, capsys):
    store = FakeStore(stored=150, pages=("a", "b"))
    _wire(monkeypatch, store)
    monkeypatch.setattr("app.cli.build_pieces", lambda files, cfg, docs_ref=None: FAKE_PIECES)
    assert main(["ingest"]) == 1 and not store.replaced
    assert "b" in capsys.readouterr().err
    assert main(["ingest", "--allow-shrink"]) == 0 and store.replaced


def test_pieces_are_stored_with_the_docs_commit_in_docs_ref(monkeypatch):
    store = FakeStore(stored=120)
    _wire(monkeypatch, store)
    seen = {}

    def build(files, cfg, docs_ref=None):
        seen["ref"] = docs_ref
        return FAKE_PIECES

    monkeypatch.setattr("app.cli.build_pieces", build)
    assert main(["ingest"]) == 0
    assert seen["ref"] == "stable@abcdef0123"
