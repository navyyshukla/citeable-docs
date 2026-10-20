import json

from app.config import load_config
from app.llm.base import Adapter, Completion, ProviderError
from app.search import Searcher
from evals.runner import (AnswerRow, is_hit, run_answers, run_retrieval, summarize_answers,
                          summarize_retrieval, write_results)
from evals.schema import EvalQuestion
from ingest.models import Piece

CFG = load_config("config/visidata.yaml")


def mk(i, text, path):
    return Piece(id=i, page_slug=i.split(":")[0], page_title="T", url=f"https://x/{i}/",
                 anchor="", heading_path=path, text=text, docs_ref="stable", docs_version=None,
                 last_updated=None)


PIECES = [mk("join:0", "Type `&` to open the join-chooser.", ("Join", "How to join")),
          mk("cols:0", "Press `!` to pin a key column.", ("Columns", "Key columns"))]
BY_ID = {p.id: p for p in PIECES}
SEARCH = Searcher(PIECES)


def q(i, text, answerable=True, page=None, heading=None):
    return EvalQuestion(id=i, question=text, answerable=answerable, gold_page=page,
                        gold_heading=heading, source="synthetic", split="dev")


class Fake:
    name = "fake"

    def __init__(self, text="Use it [1].", neurons=10.0):
        self.text, self.neurons = text, neurons

    def complete(self, system, user, max_tokens):
        return Completion(self.text, "fake", "m", 1, 1, self.neurons, 0.01)


def test_is_hit_matches_page_and_optional_heading():
    p = PIECES[0]
    assert is_hit(p, q("a", "x", page="join"))
    assert is_hit(p, q("a", "x", page="join", heading="how to join"))
    assert not is_hit(p, q("a", "x", page="join", heading="sorting"))
    assert not is_hit(p, q("a", "x", page="columns"))


def test_retrieval_rows_and_summary():
    qs = [q("1", "what does & do?", page="join"),
          q("2", "what does ! do?", page="cols"),
          q("3", "unanswerable thing", answerable=False)]
    rows = run_retrieval(qs, SEARCH, BY_ID, "keyword", 3)
    assert [r.hit for r in rows] == [True, True, None]
    s = summarize_retrieval(rows)
    assert s["answerable"] == 2 and s["hit"] == 2 and s["hit_rate"] == 1.0


def test_a_miss_is_false_and_only_the_top_k_count():
    rows = run_retrieval([q("1", "what does & do?", page="cols")], SEARCH, BY_ID, "keyword", 1)
    assert rows[0].hit is False and rows[0].top_ids == ["join:0"]
    s = summarize_retrieval(rows)
    assert s["hit"] == 0 and s["hit_rate"] == 0.0


def test_hit_rate_is_none_when_nothing_is_answerable():
    rows = run_retrieval([q("1", "x", answerable=False)], SEARCH, BY_ID, "keyword", 3)
    assert summarize_retrieval(rows)["hit_rate"] is None


def test_answer_rows_abstention_and_calls():
    qs = [q("1", "what does & do?", page="join"),
          q("2", "zzzz nothing matches", answerable=False)]
    rows, stopped = run_answers(qs, SEARCH, BY_ID, Adapter([Fake()]), CFG, "VisiData",
                                "keyword", 3, max_neurons=1000)
    assert not stopped
    assert rows[0].status == "answered" and rows[0].llm_calls == 1
    assert rows[1].status == "abstained" and rows[1].abstained_correctly is True
    s = summarize_answers(rows)
    assert s["all_answers_used_one_call"] is True


def test_an_unanswerable_question_that_gets_an_answer_is_marked_wrong():
    rows, _ = run_answers([q("1", "what does & do?", answerable=False)], SEARCH, BY_ID,
                          Adapter([Fake()]), CFG, "VisiData", "keyword", 3, max_neurons=1000)
    assert rows[0].status == "answered" and rows[0].abstained_correctly is False
    s = summarize_answers(rows)
    assert s["unanswerable"] == 1 and s["abstained_correctly"] == 0


def test_an_answerable_question_that_abstains_is_counted_in_the_summary():
    rows, _ = run_answers([q("1", "what does & do?", page="join")], SEARCH, BY_ID,
                          Adapter([Fake("NOT_FOUND")]), CFG, "VisiData", "keyword", 3,
                          max_neurons=1000)
    assert rows[0].abstained_correctly is None
    assert summarize_answers(rows)["answerable_but_abstained"] == 1


def test_invalid_citations_and_fallback_calls_show_in_the_summary():
    class Boom:
        name = "boom"

        def complete(self, *a):
            raise ProviderError("429", 429)

    rows, _ = run_answers([q("1", "what does & do?", page="join")], SEARCH, BY_ID,
                          Adapter([Boom(), Fake("Yes [1] and [9].")]), CFG, "VisiData",
                          "keyword", 3, max_neurons=1000)
    assert rows[0].invalid_citations == 1 and rows[0].llm_calls == 2
    s = summarize_answers(rows)
    assert s["answers_with_invalid_citations"] == 1 and s["all_answers_used_one_call"] is False


def test_neuron_budget_stops_the_run_early():
    qs = [q(str(i), "what does & do?", page="join") for i in range(5)]
    rows, stopped = run_answers(qs, SEARCH, BY_ID, Adapter([Fake(neurons=40.0)]), CFG,
                                "VisiData", "keyword", 3, max_neurons=100)
    assert stopped and 1 <= len(rows) < 5


def test_finishing_under_budget_is_not_stopped():
    qs = [q("1", "what does & do?", page="join")]
    rows, stopped = run_answers(qs, SEARCH, BY_ID, Adapter([Fake(neurons=40.0)]), CFG,
                                "VisiData", "keyword", 3, max_neurons=100)
    assert len(rows) == 1 and not stopped


def test_summarize_answers_with_no_neurons_reported():
    row = AnswerRow("1", "keyword", True, "answered", None, 0, 1, None, 0.1)
    assert summarize_answers([row])["mean_neurons"] is None


def test_write_results_is_valid_json(tmp_path):
    rows = run_retrieval([q("1", "what does & do?", page="join")], SEARCH, BY_ID, "keyword", 3)
    out = tmp_path / "r.json"
    write_results(out, {"split": "dev"}, {"keyword": rows}, {})
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["meta"]["split"] == "dev" and data["retrieval"]["keyword"][0]["hit"] is True


# --- cold review #2: errors do not abort a run; citations are checked against the gold page ---

class Always429:
    name = "boom"

    def complete(self, *a):
        raise ProviderError("429", 429)


def test_a_failed_answer_is_recorded_and_the_run_continues():
    qs = [q("1", "what does & do?", page="join"), q("2", "x" * 501, page="join"),
          q("3", "what does & do?", page="join")]
    adapter = Adapter([Always429()])
    rows, stopped = run_answers(qs, SEARCH, BY_ID, adapter, CFG, "VisiData", "keyword", 3, 1000)
    assert [r.status for r in rows] == ["error", "error", "error"] and not stopped
    assert "429" in rows[0].error and "longer" in rows[1].error
    s = summarize_answers(rows)
    assert s["errors"] == 3 and s["answered"] == 0


def test_a_failed_embedding_is_recorded_as_a_retrieval_miss_and_the_run_continues():
    def embed(t):
        raise ProviderError("embedding down", 500)

    s = Searcher(PIECES, embed_query=embed, vector_search=lambda v, k: [])
    rows = run_retrieval([q("1", "what does & do?", page="join")], s, BY_ID, "meaning", 3)
    assert rows[0].hit is False and "embedding down" in rows[0].error
    assert summarize_retrieval(rows)["errors"] == 1


def test_rows_record_which_pieces_were_cited_and_whether_one_is_the_gold_page():
    good, _ = run_answers([q("1", "what does & do?", page="join")], SEARCH, BY_ID,
                          Adapter([Fake("Use it [1].")]), CFG, "VisiData", "keyword", 3, 1000)
    wrong, _ = run_answers([q("2", "what does & do?", page="cols")], SEARCH, BY_ID,
                           Adapter([Fake("Use it [1].")]), CFG, "VisiData", "keyword", 3, 1000)
    assert good[0].cited_ids == ["join:0"] and good[0].cited_gold is True
    assert wrong[0].cited_ids == ["join:0"] and wrong[0].cited_gold is False
    s = summarize_answers(good + wrong)
    assert s["answered"] == 2 and s["answered_citing_gold"] == 1


def test_all_answers_used_one_call_is_none_when_nothing_was_answered():
    row = AnswerRow("1", "keyword", False, "abstained", True, 0, 1, None, 0.1)
    assert summarize_answers([row])["all_answers_used_one_call"] is None
