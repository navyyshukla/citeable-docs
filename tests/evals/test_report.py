import pytest

from app.config import load_config
from evals.report import Stat, build_report, render_evals_html
from evals.schema import EvalQuestion
from ingest.models import Piece

CFG = load_config("config/visidata.yaml")


def q(id, answerable=True, source="real", question=None):
    return EvalQuestion(id=id, question=question or f"question {id}?", answerable=answerable,
                        gold_page="sort" if answerable else None, source=source, split="dev")


def piece(id, title="Sort rows", url="https://www.visidata.org/docs/sort/"):
    return Piece(id=id, page_slug="sort", page_title=title, url=url, anchor="", heading_path=(title,),
                 text="t", docs_ref="stable", docs_version=None, last_updated=None)


def arow(id, answerable=True, status="answered", invalid=0, text="Press `[`.", cited=("sort:1",),
         abstained_correctly=None, mode="hybrid", error=None):
    return {"id": id, "mode": mode, "answerable": answerable, "status": status,
            "abstained_correctly": abstained_correctly, "invalid_citations": invalid,
            "llm_calls": 1, "neurons": 1.0, "seconds": 1.0, "cited_ids": list(cited),
            "cited_gold": True, "error": error, "question": f"question {id}?", "text": text,
            "top_score": 0.03}


def rrow(id, hit, answerable=True, mode="hybrid"):
    return {"id": id, "mode": mode, "answerable": answerable,
            "hit": hit if answerable else None, "top_ids": [], "top_scores": [], "error": None}


def run(answers, retrieval=None, ref="stable", modes=("hybrid",)):
    return {"meta": {"split": "dev", "ref": ref, "n_questions": len(answers),
                     "total_neurons": 1.0},
            "retrieval": {m: retrieval or [] for m in modes},
            "answers": {"hybrid": answers}}


QUESTIONS = [q("a1"), q("a2"), q("a3"), q("a4"), q("u1", False), q("u2", False)]
PIECES = {"sort:1": piece("sort:1")}
ANSWERS = [
    arow("a1"), arow("a2"), arow("a3", invalid=1), arow("a4", status="abstained", text=None),
    arow("u1", False, "abstained", text=None, abstained_correctly=True),
    arow("u2", False, "answered", abstained_correctly=False),
]
RETRIEVAL = [rrow("a1", True), rrow("a2", True), rrow("a3", False), rrow("a4", True),
             rrow("u1", None, False), rrow("u2", None, False)]


def report(answers=ANSWERS, retrieval=RETRIEVAL, labels=None, verdicts=None, trap=None,
           known_wrong=None, runs=None, questions=QUESTIONS, pieces=PIECES):
    return build_report(runs if runs is not None else [run(answers, retrieval)],
                        labels if labels is not None else {"a1": True, "a2": False},
                        verdicts or {}, trap, questions, pieces, known_wrong or {})


def stat(rep, label_start):
    return next(s for s in rep.headline if s.label.startswith(label_start))


def test_headline_stats_come_from_the_run_rows():
    rep = report()
    assert stat(rep, "unanswerable refused") == Stat("unanswerable refused", 1, 2)
    # answerable and answered with no invalid citation: a1, a2 (a3 invalid, a4 abstained)
    assert stat(rep, "answerable answered with a valid citation") == Stat(
        "answerable answered with a valid citation", 2, 4)
    assert stat(rep, "invalid citations") == Stat("invalid citations", 1, 4)  # of 4 answered rows
    assert stat(rep, "hand-graded correct") == Stat("hand-graded correct", 1, 2)
    assert stat(rep, "right page in top 5 (hybrid)") == Stat("right page in top 5 (hybrid)", 3, 4)


def test_right_page_stat_for_every_retrieval_mode():
    r = run(ANSWERS, RETRIEVAL, modes=("keyword", "hybrid"))
    rep = report(runs=[r])
    assert stat(rep, "right page in top 5 (keyword)").n == 4
    assert stat(rep, "right page in top 5 (hybrid)").n == 4


def test_html_sections_come_in_the_promised_order():
    html = render_evals_html(report(known_wrong={"a3": "docs disagree"}), CFG)
    order = [html.index(s) for s in ("Headline", "How much to trust", "Known wrong answers",
                                     "Run history")]
    assert order == sorted(order)


def test_honesty_text_states_n_and_point_size():
    rep = report()  # 4 answerable -> one question is 25 points
    text = " ".join(rep.honesty)
    assert "4 answerable" in text
    assert "one question moves a rate by about 25 points" in text


def test_judge_numbers_labelled_rough_filter():
    verdicts = {"a1": {"correct": True}, "a2": {"correct": True}}
    html = render_evals_html(report(verdicts=verdicts), CFG)
    assert "rough filter" in html
    assert "misses docs errors and unhelpful answers" in html


def test_trap_summary_is_shown_when_given():
    trap = {"trap_caught": 25, "trap_total": 26, "false_alarms": 0, "pass": True}
    html = render_evals_html(report(trap=trap), CFG)
    assert "25/26" in html


def test_known_wrong_notes_are_shown_and_escaped():
    html = render_evals_html(report(known_wrong={"a2": "docs say <b>x</b>"}), CFG)
    assert "docs say &lt;b&gt;x&lt;/b&gt;" in html
    assert "<b>x</b>" not in html


def test_each_row_shows_full_answer_escaped():
    answers = [arow("a1", text="<script>alert(1)</script> done")]
    html = render_evals_html(report(answers=answers, retrieval=[], labels={}), CFG)
    assert "&lt;script&gt;alert(1)&lt;/script&gt; done" in html
    assert "<script>alert" not in html


def test_sources_are_links_built_from_pieces():
    html = render_evals_html(report(), CFG)
    assert '<a href="https://www.visidata.org/docs/sort/"' in html
    assert "Sort rows" in html


def test_javascript_url_in_a_piece_is_never_linked():
    bad = {"sort:1": piece("sort:1", url="javascript:alert(1)")}
    html = render_evals_html(report(pieces=bad), CFG)
    assert "javascript:" not in html.replace("&quot;", "")


def test_zero_runs_renders_no_runs_yet():
    rep = report(runs=[])
    html = render_evals_html(rep, CFG)
    assert "No runs yet" in html
    assert rep.history == [] and rep.rows == []


def test_zero_n_stats_render_no_data():
    rep = report(answers=[], retrieval=[], labels={})
    assert stat(rep, "unanswerable refused").n == 0
    html = render_evals_html(rep, CFG)
    assert "no data" in html


def test_missing_labels_do_not_raise():
    rep = report(labels={})
    assert stat(rep, "hand-graded correct").n == 0


def test_error_rows_are_counted_apart_and_never_as_answers():
    answers = ANSWERS + [arow("a5", status="error", text=None, error="boom", cited=())]
    rep = report(answers=answers, questions=QUESTIONS + [q("a5")])
    assert stat(rep, "answerable answered with a valid citation") == Stat(
        "answerable answered with a valid citation", 2, 4)  # the error is not in n
    html = render_evals_html(rep, CFG)
    assert "1 question errored" in html
    row = next(r for r in rep.rows if r.id == "a5")
    assert row.text is None and row.status == "error"


def test_synthetic_and_dev_runs_are_separate_groups():
    synth_q = [q("s1", source="synthetic"), q("s2", source="synthetic")]
    synth_run = run([arow("s1"), arow("s2")], [rrow("s1", True), rrow("s2", True)])
    rep = report(runs=[run(ANSWERS, RETRIEVAL), synth_run], questions=QUESTIONS + synth_q)
    assert {h.group for h in rep.history} == {"dev", "synthetic"}
    assert {r.group for r in rep.rows} == {"dev", "synthetic"}
    # the headline uses the dev run only: synthetic questions never move it
    assert stat(rep, "unanswerable refused").n == 2
    html = render_evals_html(rep, CFG)
    assert "AI-checked only, not human-checked" in html


@pytest.mark.parametrize("n,points", [(1, 100), (3, 33), (28, 4)])
def test_point_size_rounds(n, points):
    answers = [arow(f"x{i}") for i in range(n)]
    qs = [q(f"x{i}") for i in range(n)]
    rep = report(answers=answers, retrieval=[], labels={}, questions=qs)
    assert f"about {points} points" in " ".join(rep.honesty)
