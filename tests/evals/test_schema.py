import json

import pytest
from pydantic import ValidationError

from evals.schema import EvalQuestion, load_questions


def line(**over):
    base = {"id": "q1", "question": "what does & do?", "answerable": True,
            "gold_page": "join", "gold_heading": None, "reference_answer": "joins",
            "source": "real", "source_url": "https://github.com/x/1", "split": "dev"}
    return json.dumps({**base, **over})


def test_load_questions_validates_each_line(tmp_path):
    p = tmp_path / "q.jsonl"
    p.write_text(line() + "\n\n", encoding="utf-8")
    qs = load_questions(p)
    assert len(qs) == 1 and qs[0].gold_page == "join"


def test_answerable_question_needs_a_gold_page():
    with pytest.raises(ValidationError):
        EvalQuestion(id="q", question="x", answerable=True, gold_page=None, source="real",
                     split="dev")


def test_unanswerable_question_needs_no_gold_page():
    q = EvalQuestion(id="q", question="x", answerable=False, source="tricky", split="dev")
    assert q.gold_page is None


@pytest.mark.parametrize("field,value", [("source", "guess"), ("split", "test"), ("question", "")])
def test_unknown_source_split_or_empty_question_is_rejected(field, value):
    with pytest.raises(ValidationError):
        EvalQuestion.model_validate(json.loads(line(**{field: value})))


def test_a_bad_line_error_names_the_line_number(tmp_path):
    p = tmp_path / "q.jsonl"
    p.write_text(line() + "\n{not json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 2"):
        load_questions(p)


def test_duplicate_ids_are_rejected(tmp_path):
    p = tmp_path / "q.jsonl"
    p.write_text(line() + "\n" + line() + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate id 'q1'"):
        load_questions(p)
