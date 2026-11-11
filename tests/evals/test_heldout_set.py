"""The sealed held-out set: answerable questions from docs pieces no earlier set used, kept only
when two independent checkers (Gemini and a Claude reader) both passed them. Questions only."""
from evals.schema import load_questions

PATH = "evals/data/heldout.jsonl"


def test_heldout_set_contract():
    qs = load_questions(PATH)
    assert len(qs) >= 90
    assert all(q.answerable and q.gold_page and q.gold_heading for q in qs)
    assert {q.split for q in qs} == {"heldout"} and {q.source for q in qs} == {"synthetic"}
    ids = [q.id for q in qs]
    assert len(set(ids)) == len(ids) and all(i.startswith("h-") for i in ids)
    assert all(0 < len(q.question) <= 500 for q in qs)


def test_heldout_shares_no_question_and_no_piece_with_any_other_set():
    held = load_questions(PATH)
    others = [q for f in ("dev", "synthetic", "synthetic-checked", "refusal")
              for q in load_questions(f"evals/data/{f}.jsonl")]
    assert not ({q.question.lower().strip() for q in held}
                & {q.question.lower().strip() for q in others})
    used = {(q.gold_page, q.gold_heading) for q in others if q.answerable}
    assert not {(q.gold_page, q.gold_heading) for q in held} & used
    assert not {q.id for q in held} & {q.id for q in others}


def test_heldout_file_holds_no_docs_text():
    text = open(PATH, encoding="utf-8").read()
    assert "reference_answer\": \"" not in text  # questions only, no copied answers
