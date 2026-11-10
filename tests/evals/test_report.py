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


def three_runs():
    """Same 4 answerable questions; answered 4, 3, 3 -> 'answered with a valid citation' 4/4, 3/4, 3/4."""
    def mk(abstain):
        rows = [arow(i, status="abstained" if i in abstain else "answered",
                     text=None if i in abstain else "x") for i in ("a1", "a2", "a3", "a4")]
        rows += [arow("u1", False, "abstained", text=None, abstained_correctly=True),
                 arow("u2", False, "abstained", text=None, abstained_correctly=True)]
        return run(rows, RETRIEVAL)
    return [mk(set()), mk({"a4"}), mk({"a3"})]


def test_headline_shows_the_range_across_dev_runs():
    rep = report(runs=three_runs(), labels={})
    s = stat(rep, "answerable answered with a valid citation")
    assert (s.k, s.n) == (3, 4)  # the latest run still gives the counts
    assert s.spread == (0.75, 1.0)  # lowest and highest rate over the three runs
    html = render_evals_html(rep, CFG)
    assert "across 3 runs: 75%–100%" in html


def test_single_run_headline_has_no_spread():
    rep = report()
    assert stat(rep, "unanswerable refused").spread is None
    assert "across" not in render_evals_html(rep, CFG).split("How much to trust")[0]


def test_synthetic_runs_never_enter_the_spread():
    synth = run([arow("s1"), arow("s2", status="abstained", text=None)],
                [rrow("s1", True), rrow("s2", True)])
    synth_q = [q("s1", source="synthetic"), q("s2", source="synthetic")]
    rep = report(runs=three_runs() + [synth], labels={}, questions=QUESTIONS + synth_q)
    s = stat(rep, "answerable answered with a valid citation")
    assert s.spread == (0.75, 1.0)


def test_multi_run_honesty_says_hand_grades_come_from_earlier_wording():
    rep = report(runs=three_runs(), labels={"a1": True})
    assert any("hand grades" in t.lower() and "earlier" in t.lower() for t in rep.honesty)
    assert not any("earlier" in t.lower() for t in report().honesty)


def test_identical_runs_say_same_in_every_run_not_a_zero_width_range():
    rep = report(runs=[run(ANSWERS, RETRIEVAL), run(ANSWERS, RETRIEVAL)], labels={})
    html = render_evals_html(rep, CFG)
    assert "same in all 2 runs" in html
    assert "100%–100%" not in html


def test_history_rows_are_numbered_within_their_group():
    rep = report(runs=three_runs(), labels={})
    assert [h.name.split(":")[0] for h in rep.history] == ["run 1", "run 2", "run 3"]


def test_hand_graded_line_says_earlier_run_when_there_are_several_runs():
    multi = report(runs=three_runs(), labels={"a1": True})
    assert stat(multi, "hand-graded correct").label == "hand-graded correct (from an earlier run)"
    assert "hand-graded correct (from an earlier run)" in render_evals_html(multi, CFG)
    assert stat(report(), "hand-graded correct").label == "hand-graded correct"  # one run: plain


def loose_setup():
    """4 answerable: a1 exact hit, a3 right page wrong section, a2 nothing, a4 a different page."""
    def r(id, hit, top):
        x = rrow(id, hit)
        x["top_ids"] = top
        return x
    retrieval = [r("a1", True, ["sort:1"]), r("a3", False, ["sort:1"]),
                 r("a2", False, []), r("a4", False, ["other:1"])]
    pieces = {"sort:1": piece("sort:1"),
              "other:1": Piece("other:1", "other", "Other", "https://www.visidata.org/docs/o/",
                               "", ("Other",), "t", "stable", None, None)}
    return retrieval, pieces


def test_page_level_hit_counts_right_page_even_with_the_wrong_section():
    retrieval, pieces = loose_setup()
    rep = report(retrieval=retrieval, pieces=pieces)
    assert stat(rep, "right page in top 5 (hybrid)") == Stat("right page in top 5 (hybrid)", 1, 4)
    loose = stat(rep, "right page (any section) in top 5 (hybrid)")
    assert (loose.k, loose.n) == (2, 4)


def test_also_gold_pages_count_for_the_page_level_hit():
    retrieval, pieces = loose_setup()
    qs = [x if x.id != "a4" else EvalQuestion(id="a4", question="q?", answerable=True,
                                              gold_page="sort", also_gold_pages=["other"],
                                              source="real", split="dev")
          for x in QUESTIONS]
    rep = report(retrieval=retrieval, pieces=pieces, questions=qs)
    assert stat(rep, "right page (any section) in top 5 (hybrid)").k == 3


def test_generated_group_gets_its_own_stats_with_the_range_and_a_label():
    retrieval, pieces = loose_setup()
    synth_q = [q("s1", source="synthetic"), q("s2", source="synthetic")]
    def srun(hits):
        rows = [rrow("s1", hits[0]), rrow("s2", hits[1])]
        for x in rows:
            x["top_ids"] = ["sort:1"]
        return run([arow("s1"), arow("s2", status="abstained", text=None)], rows)
    rep = report(runs=[run(ANSWERS, RETRIEVAL), srun([True, False]), srun([True, True])],
                 questions=QUESTIONS + synth_q, pieces=pieces, labels={})
    by = {s.label: s for s in rep.generated}
    assert by["right page in top 5 (hybrid)"].spread == (0.5, 1.0)
    assert by["right page (any section) in top 5 (hybrid)"].spread == (1.0, 1.0)
    assert not any(s.label.startswith("hand-graded") for s in rep.generated)
    html = render_evals_html(rep, CFG)
    synthetic_part = html.split("<h3>synthetic</h3>")[1].split("<h2>Every answer</h2>")[0]
    assert "AI-checked only, not human-checked" in synthetic_part
    assert synthetic_part.index("AI-checked only") < synthetic_part.index(
        "right page (any section) in top 5 (hybrid)")
    assert "across 2 runs: 50%–100%" in synthetic_part
    # the dev headline is untouched by generated runs
    assert stat(rep, "unanswerable refused").n == 2


def test_no_generated_runs_means_no_generated_stats():
    assert report().generated == []


def test_spread_pairs_stats_by_label_not_by_position():
    """An earlier run with two modes, the latest with hybrid only: hybrid's range must use only hybrid."""
    two = run(ANSWERS, RETRIEVAL, modes=("keyword", "hybrid"))
    two["retrieval"]["keyword"] = [rrow(r["id"], False, r["answerable"], "keyword")
                                   for r in RETRIEVAL]  # keyword finds nothing
    one = run(ANSWERS, RETRIEVAL, modes=("hybrid",))
    rep = report(runs=[two, one], labels={})
    hybrid = stat(rep, "right page in top 5 (hybrid)")
    assert (hybrid.k, hybrid.n) == (3, 4)
    assert hybrid.spread == (0.75, 0.75)  # not dragged to 0% by the keyword rate
    assert hybrid.runs == 2


def test_spread_does_not_crash_when_the_latest_run_has_more_modes():
    two = run(ANSWERS, RETRIEVAL, modes=("keyword", "hybrid"))
    one = run(ANSWERS, RETRIEVAL, modes=("hybrid",))
    rep = report(runs=[one, two], labels={})  # latest has the extra mode
    keyword = stat(rep, "right page in top 5 (keyword)")
    assert keyword.spread is None and keyword.runs == 0  # only one run has it: no range
    assert stat(rep, "right page in top 5 (hybrid)").runs == 2


def test_a_run_with_no_data_for_a_stat_is_not_counted_in_its_range():
    empty = run([], [])
    rep = report(runs=[empty, run(ANSWERS, RETRIEVAL), run(ANSWERS, RETRIEVAL)], labels={})
    assert stat(rep, "unanswerable refused").runs == 2
