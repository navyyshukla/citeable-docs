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
        self.model_ok, self.meta = True, None

    def check_ingest_meta(self, project, model):
        if not self.model_ok:
            raise ValueError("pieces were embedded with 'old' but the config says 'new'")

    def write_ingest_meta(self, project, model, dim, docs_ref):
        self.meta = (project, model, dim, docs_ref)

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


def test_ingest_writes_meta_after_replace(monkeypatch):
    store = FakeStore(stored=120)
    _wire(monkeypatch, store)
    monkeypatch.setattr("app.cli.build_pieces", lambda files, cfg, docs_ref=None: FAKE_PIECES)
    assert main(["ingest"]) == 0
    assert store.meta[0] == "visidata" and store.meta[3] == f"stable@{SHA[:10]}"


def test_ingest_refuses_changed_embedding_model(monkeypatch, capsys):
    store = FakeStore(stored=120)
    store.model_ok = False
    _wire(monkeypatch, store)
    monkeypatch.setattr("app.cli.build_pieces", lambda files, cfg, docs_ref=None: FAKE_PIECES)
    assert main(["ingest"]) == 1
    assert not store.replaced
    assert "embedded with" in capsys.readouterr().err


def test_allow_model_change_skips_the_check(monkeypatch):
    store = FakeStore(stored=120)
    store.model_ok = False
    _wire(monkeypatch, store)
    monkeypatch.setattr("app.cli.build_pieces", lambda files, cfg, docs_ref=None: FAKE_PIECES)
    assert main(["ingest", "--allow-model-change"]) == 0
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


def test_calibrate_prints_a_table_without_touching_network_or_database(tmp_path, capsys):
    import json
    rows = [{"id": "a", "mode": "hybrid", "answerable": True, "hit": True, "top_ids": ["x"],
             "top_scores": [0.033], "error": None},
            {"id": "b", "mode": "hybrid", "answerable": False, "hit": None, "top_ids": ["x"],
             "top_scores": [0.012], "error": None}]
    f = tmp_path / "r.json"
    f.write_text(json.dumps({"meta": {}, "retrieval": {"hybrid": rows}}))
    assert main(["calibrate", "--retrieval", str(f), "--mode", "hybrid"]) == 0
    out = capsys.readouterr().out
    assert "threshold" in out and "answered%" in out and "0.0330" in out


def test_calibrate_unknown_mode_fails_cleanly(tmp_path, capsys):
    import json
    f = tmp_path / "r.json"
    f.write_text(json.dumps({"meta": {}, "retrieval": {"hybrid": []}}))
    assert main(["calibrate", "--retrieval", str(f), "--mode", "nope"]) == 1
    assert "nope" in capsys.readouterr().err


class FakeUsage:
    def __init__(self):
        self.created, self.revoked, self.purged, self.schema = [], [], [], False
        self.active = {"ann"}

    def init_schema(self):
        self.schema = True

    def create_token(self, label):
        if label in self.active:
            raise ValueError(f"a token labelled {label!r} already exists")
        self.created.append(label)
        return "PLAIN-TOKEN-123"

    def revoke_token(self, label):
        self.revoked.append(label)
        return label in self.active

    def list_tokens(self):
        from datetime import datetime, timezone

        from app.usage import TokenInfo
        t = datetime(2026, 10, 20, tzinfo=timezone.utc)
        return [TokenInfo("ann", t, False, 3), TokenInfo("bob", t, True, 0)]

    def purge(self, older_than_days):
        self.purged.append(older_than_days)
        return 7


def _admin(monkeypatch):
    usage, store = FakeUsage(), FakeStore(stored=0)
    store.inited = False
    store.init_schema = lambda: setattr(store, "inited", True)
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setattr("app.cli.Usage", lambda db: usage)
    monkeypatch.setattr("app.cli.Store", lambda db, dim, **kw: store)
    return usage, store


def test_init_db_creates_every_table(monkeypatch):
    usage, store = _admin(monkeypatch)
    assert main(["init-db"]) == 0
    assert usage.schema and store.inited


def test_token_create_prints_plain_token_once(monkeypatch, capsys):
    usage, _ = _admin(monkeypatch)
    assert main(["token", "create", "carol"]) == 0
    out = capsys.readouterr().out
    # twice by design: on the token line and inside the invite link
    assert out.count("PLAIN-TOKEN-123") == 2 and "carol" in out and "not be shown again" in out
    assert usage.created == ["carol"]


def test_token_create_prints_invite_link_with_fragment(monkeypatch, capsys):
    from app.config import load_config

    _admin(monkeypatch)
    site = load_config("config/visidata.yaml").site
    assert main(["token", "create", "carol"]) == 0
    out = capsys.readouterr().out
    assert f"{site.url.rstrip('/')}/#t=PLAIN-TOKEN-123" in out
    assert "?t=" not in out


def test_token_create_duplicate_label_fails_cleanly(monkeypatch, capsys):
    _admin(monkeypatch)
    assert main(["token", "create", "ann"]) == 1
    assert "already exists" in capsys.readouterr().err


def test_token_revoke(monkeypatch, capsys):
    usage, _ = _admin(monkeypatch)
    assert main(["token", "revoke", "ann"]) == 0
    assert main(["token", "revoke", "zed"]) == 1
    assert "zed" in capsys.readouterr().err


def test_token_list_shows_labels_and_never_hashes(monkeypatch, capsys):
    _admin(monkeypatch)
    assert main(["token", "list"]) == 0
    out = capsys.readouterr().out
    assert "ann" in out and "bob" in out and "revoked" in out
    assert "hash" not in out.lower() and "PLAIN" not in out


def test_purge_defaults_to_the_configured_retention(monkeypatch, capsys):
    usage, _ = _admin(monkeypatch)
    assert main(["purge"]) == 0
    assert main(["purge", "--days", "7"]) == 0
    assert usage.purged == [30, 7]
    assert "7" in capsys.readouterr().out


def test_serve_runs_the_factory_without_an_access_log(monkeypatch):
    calls = {}
    monkeypatch.setattr("uvicorn.run", lambda app, **kw: calls.update(app=app, **kw))
    assert main(["serve", "--port", "9000"]) == 0
    assert calls["app"] == "app.api:build_from_env" and calls["factory"] is True
    assert calls["access_log"] is False and calls["port"] == 9000


def _judge_files(tmp_path, answers_row=None):
    import json
    q = tmp_path / "q.jsonl"
    q.write_text(json.dumps({"id": "a", "question": "a public paraphrase", "answerable": True,
                             "gold_page": "join", "source": "synthetic", "split": "dev",
                             "reference_answer": "ref"}) + "\n")
    row = answers_row or {"id": "a", "status": "answered", "text": "It joins [1].",
                          "cited_ids": ["join:0"], "question": "a public paraphrase"}
    res = tmp_path / "res.json"
    res.write_text(json.dumps({"meta": {"split": "dev"}, "answers": {"hybrid": [row]}}))
    return q, res


def test_judge_writes_verdicts_and_says_uncalibrated(monkeypatch, tmp_path, capsys):
    import json

    from app.llm.base import Completion
    q, res = _judge_files(tmp_path)
    store = FakeStore(stored=1)
    store.load_pieces = lambda project: [SimpleNamespace(id="join:0", text="Type & to join.")]
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr("app.cli.Store", lambda db, dim, **kw: store)

    class G:
        def __init__(self, key, json_output=False):
            assert json_output is True

        def complete(self, s, u, n):
            assert "Type & to join." in u
            return Completion('{"grounded": true, "correct": true, "reason": "ok"}', "gemini",
                              "m", 1, 1, None, 0.1)

    monkeypatch.setattr("app.cli.GeminiProvider", G)
    out = tmp_path / "v.json"
    assert main(["judge", "--results", str(res), "--data", str(q), "--mode", "hybrid",
                 "--out", str(out)]) == 0
    verdicts = json.loads(out.read_text())
    assert verdicts[0]["question_id"] == "a" and verdicts[0]["correct"] is True
    assert "uncalibrated" in capsys.readouterr().out.lower()


def test_judge_refuses_results_with_questions_outside_the_curated_file(monkeypatch, tmp_path,
                                                                       capsys):
    q, res = _judge_files(tmp_path, {"id": "zzz", "status": "answered", "text": "t",
                                     "cited_ids": [], "question": "typed by a visitor"})
    store = FakeStore(stored=1)
    store.load_pieces = lambda project: []
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr("app.cli.Store", lambda db, dim, **kw: store)
    assert main(["judge", "--results", str(res), "--data", str(q), "--out",
                 str(tmp_path / "v.json")]) == 1
    assert "zzz" in capsys.readouterr().err


def test_judge_agreement_prints_precision_and_recall(tmp_path, capsys):
    import json
    v = tmp_path / "v.json"
    v.write_text(json.dumps([{"question_id": "1", "grounded": True, "correct": True,
                              "reason": "", "error": None}]))
    lab = tmp_path / "l.jsonl"
    lab.write_text(json.dumps({"question_id": "1", "correct": True}) + "\n")
    assert main(["judge-agreement", "--verdicts", str(v), "--labels", str(lab)]) == 0
    out = capsys.readouterr().out
    assert "precision" in out and "recall" in out and "1.00" in out


def test_generate_questions_writes_a_loadable_file_and_sheet_without_network(
        monkeypatch, tmp_path, capsys):
    import json as _json

    from app.llm.base import Completion
    from evals.schema import load_questions
    from ingest.models import Piece

    def mk(i):
        return Piece(id=f"pg{i}:0", page_slug=f"pg{i}", page_title=f"Page {i}", url="https://x/",
                     anchor="a", heading_path=(f"Page {i}", "H"), text="body text " * 40,
                     docs_ref="stable@abc", docs_version="3", last_updated="2026-01-01")

    class FakeStore:
        def load_pieces(self, project):
            return [mk(i) for i in range(6)]

    class FakeGemini:
        calls = 0

        def __init__(self, key, **kw):
            assert kw.get("json_output") is True

        def complete(self, system, user, max_tokens):
            FakeGemini.calls += 1
            return Completion(_json.dumps({"questions": [f"generated {FakeGemini.calls} a?",
                                                         f"generated {FakeGemini.calls} b?"]}),
                              "gemini", "m", 1, 1, None, 0.1)

    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr("app.cli._store", lambda cfg: FakeStore())
    monkeypatch.setattr("app.cli.GeminiProvider", FakeGemini)
    monkeypatch.setattr("evals.generate.time.sleep", lambda s: None)
    out, sheet = tmp_path / "syn.jsonl", tmp_path / "sheet.md"
    assert main(["generate-questions", "--out", str(out), "--limit", "3", "--unanswerable", "2",
                 "--sheet", str(sheet)]) == 0
    qs = load_questions(out)
    assert FakeGemini.calls == 4  # 3 pieces + 1 unanswerable call
    assert sum(q.answerable for q in qs) == 6 and sum(not q.answerable for q in qs) == 2
    assert sheet.exists() and "body text" not in out.read_text() + sheet.read_text()
    assert main(["generate-questions", "--out", str(out)]) == 1  # refuses to overwrite
    assert "already exists" in capsys.readouterr().err
