import tarfile
from pathlib import Path

import pytest

from app.search import Bm25, Hit, Searcher, key_path, rrf, tokenize_symbols, tokenize_words
from ingest.models import Piece
from ingest.pipeline import build_pieces


def mk(i, text, path=("P",)):
    return Piece(id=i, page_slug=i.split(":")[0], page_title="P", url="https://x/", anchor="",
                 heading_path=path, text=text, docs_ref="stable", docs_version=None,
                 last_updated=None)


PIECES = [
    mk("join:0", "How to join two datasets. Type `&` to open the join-chooser."),
    mk("cols:0", "Press `!` to pin the current column as a key column. Press `-` to hide a column."),
    mk("quit:0", "Press `Ctrl+Q` to quit at any time."),
]


def test_tokenizers():
    assert tokenize_words("Type & go") == ["type", "go"]
    assert tokenize_symbols("Type & go") == ["type", "&", "go"]


def test_symbol_query_finds_page_but_word_only_cannot():
    docs = {p.id: p.search_text for p in PIECES}
    assert Bm25(docs, tokenize_symbols).search("what does & do?", 1)[0][0] == "join:0"
    assert Bm25(docs, tokenize_words).search("&", 1) == []


def test_punctuation_only_question_returns_no_hits_not_error():
    s = Searcher(PIECES)
    assert s.search("keyword", "?", 5) == []
    assert s.search("keyword", "   ", 5) == []


def test_rrf_prefers_items_ranked_well_in_both_lists():
    fused = rrf([["a", "b", "c"], ["b", "a"]])
    assert [i for i, _ in fused][:2] in (["a", "b"], ["b", "a"])
    assert rrf([["a"], ["b"], ["b"]])[0][0] == "b"


def test_hybrid_combines_keyword_and_meaning():
    vec = lambda q: [1.0]  # noqa: E731
    vs = lambda e, k: [("cols:0", 0.9), ("join:0", 0.5)]  # noqa: E731
    s = Searcher(PIECES, embed_query=vec, vector_search=vs)
    out = s.search("hybrid", "what does & do", 2)
    assert {h.piece_id for h in out} == {"join:0", "cols:0"}
    assert all(isinstance(h, Hit) for h in out)


def test_meaning_mode_requires_embeddings_and_unknown_mode_fails():
    s = Searcher(PIECES)
    with pytest.raises(ValueError):
        s.search("meaning", "x", 3)
    with pytest.raises(ValueError):
        s.search("telepathy", "x", 3)


# --- exact backticked-key path (spike S2) ---

KEYS = {
    "join:0": "Join. Type `&` to open the join-chooser.",
    "cols:0": "Columns.\n\n`!`   pins the current column as a key column\n`(`   expands a column",
    "rows:0": "Rows. Use `!` to invert, and `(` to peek.",
    "calc:0": "Type `=` to make a derived column.",
    "bare:0": "Press & to join. Nothing here is in backticks.",
}


@pytest.mark.parametrize("query,first", [
    ("what does & do?", "join:0"),
    ("what does ! do?", "cols:0"),     # a definition row beats a plain mention (3x)
    ("what does ( do?", "cols:0"),
    ("how do I make a derived column with =", "calc:0"),
])
def test_key_path_puts_the_defining_section_first(query, first):
    assert key_path(KEYS, query)[0] == first


def test_key_path_ignores_a_symbol_that_is_in_no_backticks():
    assert key_path({"bare:0": KEYS["bare:0"]}, "what does & do?") == []


def test_key_path_has_nothing_for_question_marks_words_and_blanks():
    for q in ("what is a column?", "?", "", "what does ? do"):
        assert key_path(KEYS, q) == []


def test_key_path_does_not_match_a_symbol_inside_a_word_or_longer_key():
    assert key_path({"x:0": "Use `g!` and `a&b` here."}, "what does ! do?") == []


def test_keyword_mode_lists_exact_key_sections_before_bm25():
    pieces = [mk(i, t) for i, t in KEYS.items()]
    out = [h.piece_id for h in Searcher(pieces).search("keyword", "what does ! do?", 5)]
    assert out[0] == "cols:0" and out.index("rows:0") < len(out)
    assert len(out) == len(set(out))


def test_hybrid_finds_the_key_section_even_when_meaning_misses_it():
    pieces = [mk(i, t) for i, t in KEYS.items()]
    vs = lambda e, k: [("rows:0", 0.4), ("calc:0", 0.3)]  # noqa: E731
    s = Searcher(pieces, embed_query=lambda q: [1.0], vector_search=vs)
    assert "join:0" in [h.piece_id for h in s.search("hybrid", "what does & do?", 5)]


def test_hybrid_survives_a_chatty_question_where_keyword_finds_nothing():
    vs = lambda e, k: [("cols:0", 0.8)]  # noqa: E731
    s = Searcher(PIECES, embed_query=lambda q: [1.0], vector_search=vs)
    out = s.search("hybrid", "zzz qqq xxx", 3)
    assert [h.piece_id for h in out] == ["cols:0"]


def test_vector_search_gets_at_least_twenty_candidates_for_small_k():
    seen = []

    def vs(e, k):
        seen.append(k)
        return []

    Searcher(PIECES, embed_query=lambda q: [1.0], vector_search=vs).search("meaning", "x", 3)
    assert seen == [20]


# --- real docs (skipped when the gitignored cache is absent) ---

STABLE = Path(__file__).resolve().parents[1] / "spikes" / ".cache" / "stable.tar.gz"


def _real_pieces():
    from app.config import load_config
    cfg = load_config("config/visidata.yaml")
    files = {}
    with tarfile.open(STABLE) as tf:
        for m in tf:
            parts = m.name.split("/", 2)
            if m.isfile() and len(parts) == 3 and parts[1] == "docs" and parts[2].endswith(".md") \
                    and "/" not in parts[2]:
                files[parts[2]] = tf.extractfile(m).read().decode("utf-8", "replace")
    return build_pieces(files, cfg.project)


@pytest.mark.skipif(not STABLE.exists(), reason="docs cache not present (it is gitignored)")
@pytest.mark.parametrize("query,pages", [
    ("what does & do?", {"join"}),
    ("what does ! do?", {"columns"}),
    ("what does ( do?", {"columns"}),
    ("how do I join two sheets?", {"join"}),
    ("how do I hide a column?", {"columns"}),
    ("how do I append two datasets?", {"join"}),
    ("my sheet has key thing with ! what is that n how i undo it", {"columns"}),
])
def test_real_docs_keyword_search_finds_the_right_page_in_top_5(query, pages):
    s = Searcher(_real_pieces())
    got = [h.piece_id.split(":")[0] for h in s.search("keyword", query, 5)]
    assert pages & set(got), got


# --- cold review #2: quoted keys, junk questions in every mode ---

@pytest.mark.parametrize("query", ["what does `&` do?", 'what does "&" do?', "what does '&' do?",
                                   "what does `&`", "(`&`) what is it"])
def test_key_path_reads_the_key_inside_backticks_or_quotes(query):
    assert key_path(KEYS, query)[0] == "join:0"


def test_a_quoted_double_quote_key_is_still_the_key():
    assert key_path({"d:0": "`\"`   duplicates the selected rows"}, "what does `\"` do?") == ["d:0"]


@pytest.mark.parametrize("mode", ["keyword", "meaning", "hybrid"])
@pytest.mark.parametrize("junk", ["?", "??", "  ?  "])
def test_junk_question_returns_no_hits_and_embeds_nothing_in_every_mode(mode, junk):
    calls = []

    def embed(t):
        calls.append(t)
        return [0.0]

    s = Searcher(PIECES, embed_query=embed, vector_search=lambda v, k: [("quit:0", 1.0)])
    assert s.search(mode, junk, 5) == []
    assert calls == []
