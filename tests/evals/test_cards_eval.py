import json

import pytest

from app.config import load_config
from app.llm.base import Adapter, Completion
from evals.cards_eval import (
    MAX_FALSE_CARDS, MIN_POSITIVE_RATE, CardRow, CardQuestion, dev_negatives, load_card_questions,
    run_cards, score_cards,
)

CFG = load_config("config/visidata.yaml")


def write(tmp_path, rows):
    p = tmp_path / "c.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


@pytest.mark.parametrize("rows", [
    [{"id": "a", "question": "q", "label": "about"}, {"id": "a", "question": "r", "label": "help"}],
    [{"id": "a", "question": "q", "label": "other"}],
    [{"id": "a", "question": "", "label": "about"}],
])
def test_load_rejects_bad_rows(tmp_path, rows):
    with pytest.raises(ValueError):
        load_card_questions(write(tmp_path, rows))


def test_dev_negatives_are_the_answerable_dev_questions_as_normal():
    negs = dev_negatives("evals/data/dev.jsonl")
    assert len(negs) == 19  # the answerable questions in the dev set
    assert all(n.label == "normal" and n.id.startswith("dev:") for n in negs)


def row(label, predicted):
    return CardRow("x", "q", label, predicted, 2.0, 0.5)


def test_score_counts_false_cards_and_positive_rate():
    bad = score_cards([row("normal", "about")] + [row("about", "about")] * 10)
    assert bad.false_cards == 1 and bad.passes is False
    nine = score_cards([row("normal", "normal")] * 5 + [row("about", "about")] * 9
                       + [row("help", "normal")])
    assert nine.false_cards == 0 and nine.positives_total == 10 and nine.positives_right == 9
    assert nine.passes is True
    eight = score_cards([row("about", "about")] * 8 + [row("help", "normal")] * 2)
    assert eight.passes is False
    assert (MAX_FALSE_CARDS, MIN_POSITIVE_RATE) == (0, 0.9)
    assert score_cards([]).passes is False  # nothing measured is not a pass


def test_a_wrong_card_for_a_positive_is_not_a_false_card_but_is_not_right_either():
    s = score_cards([row("about", "help")] * 10)
    assert s.false_cards == 0 and s.positives_right == 0 and s.passes is False


def test_shipped_card_questions_cover_the_traps():
    qs = load_card_questions("evals/data/cards.jsonl")
    by = {lab: [q.question.lower() for q in qs if q.label == lab] for lab in ("about", "help", "normal")}
    assert len(by["about"]) >= 10 and len(by["help"]) >= 10 and len(by["normal"]) >= 15
    for trap in ("what is a frequency table", "how do I use the join command",
                 "what does the help key do", "how do I use visidata to sort a column"):
        assert trap.lower() in by["normal"], trap


class Say:
    name = "say"

    def __init__(self, text):
        self.text = text

    def complete(self, system, user, max_tokens):
        return Completion(self.text, "say", "m", 10, 1, 2.0, 0.1)


def test_run_uses_a_fresh_adapter_per_question_and_reports_neurons():
    made = []

    def factory():
        made.append(1)
        return Adapter([Say("about")])

    qs = [CardQuestion(id="a", question="what is visidata", label="about"),
          CardQuestion(id="b", question="how do I sort", label="normal")]
    rows = run_cards(qs, factory, CFG)
    assert len(made) == 2
    assert [r.predicted for r in rows] == ["about", "about"]
    assert [r.neurons for r in rows] == [2.0, 2.0]
    assert score_cards(rows).false_cards == 1  # the model said about for a normal question
