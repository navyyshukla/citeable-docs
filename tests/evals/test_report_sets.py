from app.config import load_config
from evals.report import JUDGE_WARNING, Report, render_evals_html
from evals.report_sets import heldout_section, models_section, refusal_section
from evals.schema import EvalQuestion
from ingest.models import Piece

CFG = load_config("config/visidata.yaml")


def piece(i, page="sort"):
    return Piece(id=f"{page}:{i}", page_slug=page, page_title=page.title(),
                 url=f"https://www.visidata.org/docs/{page}/", anchor="", heading_path=(page.title(),),
                 text="t", docs_ref="stable", docs_version=None, last_updated=None)


PIECES = {p.id: p for p in (piece(1), piece(2), piece(1, "join"))}


def arow(id, status="answered", answerable=True, cited=("sort:1",), invalid=0, correct_refusal=None):
    return {"id": id, "mode": "hybrid", "answerable": answerable, "status": status,
            "abstained_correctly": correct_refusal, "invalid_citations": invalid, "llm_calls": 1,
            "neurons": 1.0, "seconds": 1.0, "cited_ids": list(cited), "cited_gold": None,
            "error": None, "question": f"q {id}", "text": "t", "top_score": 0.03}


def rrow(id, top):
    return {"id": id, "mode": "hybrid", "answerable": True, "hit": False, "top_ids": top,
            "top_scores": [], "error": None}


def run(answers, retrieval=None):
    return {"meta": {"split": "heldout", "ref": "stable", "n_questions": len(answers),
                     "total_neurons": 10.0},
            "answers": {"hybrid": answers}, "retrieval": {"hybrid": retrieval or []}}


def refused(n=60, answered=0):
    rows = [arow(f"u-{i:03d}", "abstained", False, (), correct_refusal=True) for i in range(n - answered)]
    rows += [arow(f"u-{i:03d}", "answered", False, correct_refusal=False) for i in range(n - answered, n)]
    return run(rows)


def test_refusal_section_counts_runs_and_says_who_wrote_the_questions():
    s = refusal_section([refused(), refused(), refused()])
    st = {x.label: x for x in s.stats}
    r = st["unanswerable refused"]
    assert (r.k, r.n, r.runs) == (60, 60, 3) and r.spread == (1.0, 1.0)
    assert "written by us" in s.labelling.lower()
    assert any("no question was answered" in n.lower() for n in s.notes)


def test_refusal_section_flags_a_run_where_a_question_was_answered():
    s = refusal_section([refused(), refused(answered=2)])
    st = {x.label: x for x in s.stats}
    assert (st["unanswerable refused"].k, st["unanswerable refused"].n) == (58, 60)  # the latest run
    assert any("answered" in n and "read" in n for n in s.notes)  # audit instruction


QS = [EvalQuestion(id=f"h-{i:03d}", question=f"q{i}?", answerable=True, gold_page="sort",
                   gold_heading="H", source="synthetic", split="heldout") for i in range(1, 5)]


def held_run(cited_pages):
    rows, ret = [], []
    for q, c in zip(QS, cited_pages):
        if c is None:
            rows.append(arow(q.id, "abstained", True, ()))
            ret.append(rrow(q.id, []))
        else:
            rows.append(arow(q.id, "answered", True, (c,)))
            ret.append(rrow(q.id, [c]))
    return run(rows, ret)


def test_heldout_section_reports_answered_cited_page_and_retrieval():
    r = held_run(["sort:1", "join:1", None, "sort:2"])
    s = heldout_section([r, r], QS, {}, PIECES)
    st = {x.label: x for x in s.stats}
    assert (st["answered"].k, st["answered"].n) == (3, 4)
    page = st["of the answered, cited the right page (any section)"]
    assert (page.k, page.n) == (2, 3)
    top5 = st["right page (any section) in top 5"]
    assert (top5.k, top5.n) == (2, 4)  # q1 and q4 have a sort piece in the top 5; q2 has join, q3 none
    assert st["answered"].runs == 2
    assert "AI-checked only, not human-checked" in s.labelling


def test_heldout_section_states_the_sealing_rule_and_labels_the_judge():
    r = held_run(["sort:1", "sort:1", "sort:1", "sort:1"])
    verdicts = {q.id: {"correct": True} for q in QS}
    s = heldout_section([r], QS, verdicts, PIECES)
    assert any("not changed after" in n or "sealed" in n.lower() for n in s.notes)
    judge = [x for x in s.stats if "AI judge" in x.label]
    assert judge and JUDGE_WARNING in judge[0].label and (judge[0].k, judge[0].n) == (4, 4)
    assert not [x for x in heldout_section([r], QS, {}, PIECES).stats if "AI judge" in x.label]


def test_models_section_lists_each_model_and_says_single_runs():
    dev = run([arow("a1"), arow("a2", "abstained", True, ()), arow("u1", "abstained", False, (),
                                                                   correct_refusal=True)])
    ref = refused(10, answered=3)
    s = models_section({"gemma": {"dev": dev, "refusal": refused(10)}, "llama": {"dev": dev, "refusal": ref}})
    text = " ".join(s.lines)
    assert "gemma" in text and "llama" in text and "10/10" in text and "7/10" in text
    assert any("one run" in n.lower() for n in s.notes)
    assert any("removed" in n.lower() for n in s.notes)


def test_sections_render_between_trust_and_known_wrong_and_are_escaped():
    s = heldout_section([held_run(["sort:1"] * 4)], QS, {}, PIECES)
    from evals.report import Section
    evil = Section("<script>x</script> title", "label <b>", [], ["note & more"], [])
    rep = Report(headline=[], honesty=["h"], known_wrong=[], history=[], rows=[], sections=[s, evil])
    page = render_evals_html(rep, CFG)
    assert page.index("How much to trust") < page.index(s.title) < page.index("Known wrong answers")
    assert "<script>x" not in page and "&lt;script&gt;x" in page and "note &amp; more" in page
