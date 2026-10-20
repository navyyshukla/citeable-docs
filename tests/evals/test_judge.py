import ast
import json
from pathlib import Path

import pytest

from app.llm.base import Completion, ProviderError
from evals.judge import (HumanLabel, JudgeItem, JudgeVerdict, agreement, items_from_results,
                         judge_answer)
from evals.schema import EvalQuestion


class FakeGemini:
    name = "gemini"

    def __init__(self, text=None, error=None):
        self.text, self.error, self.seen = text, error, None

    def complete(self, system, user, max_tokens):
        self.seen = (system, user, max_tokens)
        if self.error:
            raise self.error
        return Completion(self.text, "gemini", "m", 10, 5, None, 0.1)


ITEM = JudgeItem("r-001", "How do I unhide one column?", "Press gv or set its width.",
                 "Open the Columns sheet and set its width [1].",
                 ["Unhide: open Shift+C and set width to a positive number."])


def test_judge_parses_json_verdict_even_inside_code_fences():
    g = FakeGemini('```json\n{"grounded": true, "correct": false, "reason": "misses gv"}\n```')
    v = judge_answer(ITEM, g)
    assert v == JudgeVerdict("r-001", True, False, "misses gv", None)


@pytest.mark.parametrize("text", ["I think it is fine", '{"grounded": "yes", "correct": true}',
                                  '{"grounded": true}', "[]", ""])
def test_judge_bad_output_is_an_error_never_a_guess(text):
    v = judge_answer(ITEM, FakeGemini(text))
    assert v.grounded is None and v.correct is None and v.error


def test_judge_provider_failure_is_an_error_verdict():
    v = judge_answer(ITEM, FakeGemini(error=ProviderError("HTTP 429", 429)))
    assert v.error and "429" in v.error and v.correct is None


def test_judge_prompt_contains_question_reference_answer_and_cited_text():
    g = FakeGemini('{"grounded": true, "correct": true, "reason": "ok"}')
    judge_answer(ITEM, g)
    system, user, _ = g.seen
    assert "JSON" in system
    for needle in ("How do I unhide one column?", "Press gv or set its width.",
                   "Open the Columns sheet", "Shift+C and set width"):
        assert needle in user


def q(i, text="a public paraphrase"):
    return EvalQuestion(id=i, question=text, answerable=True, gold_page="p", source="synthetic",
                        split="dev", reference_answer="ref")


def results(rows, retrieval=None):
    out = {"meta": {"split": "dev"}, "answers": {"hybrid": rows}}
    if retrieval is not None:
        out["retrieval"] = {"hybrid": retrieval}
    return out


def row(i, status="answered", text="An answer [1].", cited=("p:0",)):
    return {"id": i, "status": status, "text": text, "cited_ids": list(cited), "question": "x"}


def test_items_come_from_answered_rows_with_text_only():
    rows = [row("a"), row("b", status="abstained"), row("c", text=None)]
    items, skipped = items_from_results(results(rows), [q("a"), q("b"), q("c")], "hybrid",
                                        {"p:0": "piece text"})
    assert [i.question_id for i in items] == ["a"] and skipped == 2
    assert items[0].excerpts == ["piece text"] and items[0].reference_answer == "ref"
    assert items[0].question == "a public paraphrase"  # the question comes from the curated file


def test_excerpts_are_numbered_as_the_answerer_saw_them_not_renumbered_from_the_citations():
    # The model got 3 excerpts and cited only [3]. The judge must show all 3 in that order,
    # or "[3]" points at nothing (a live run marked correct answers "not grounded" for this).
    texts = {"a:0": "first", "b:0": "second", "c:0": "third"}
    retrieval = [{"id": "a", "top_ids": ["a:0", "b:0", "c:0"], "top_scores": [3, 2, 1]}]
    items, _ = items_from_results(results([row("a", cited=("c:0",))], retrieval), [q("a")],
                                  "hybrid", texts)
    assert items[0].excerpts == ["first", "second", "third"]


def test_without_saved_retrieval_it_falls_back_to_the_cited_pieces():
    items, _ = items_from_results(results([row("a", cited=("p:0",))]), [q("a")], "hybrid",
                                  {"p:0": "piece text"})
    assert items[0].excerpts == ["piece text"]


def test_a_row_whose_question_is_not_in_the_curated_file_is_refused():
    with pytest.raises(ValueError, match="zzz"):
        items_from_results(results([row("zzz")]), [q("a")], "hybrid", {"p:0": "t"})


def test_agreement_precision_and_recall_on_correct():
    v = [JudgeVerdict("1", True, True, "", None), JudgeVerdict("2", True, True, "", None),
         JudgeVerdict("3", True, False, "", None), JudgeVerdict("4", True, False, "", None),
         JudgeVerdict("5", None, None, "", "boom")]
    labels = [HumanLabel("1", True), HumanLabel("2", False), HumanLabel("3", True),
              HumanLabel("4", False), HumanLabel("5", True), HumanLabel("6", True)]
    a = agreement(v, labels)
    # judge says correct: 1, 2. Human says correct: 1, 3 (5 and 6 have no usable verdict).
    # TP = 1 (id 1); FP = 1 (id 2); FN = 1 (id 3)
    assert a["precision"] == pytest.approx(0.5) and a["recall"] == pytest.approx(0.5)
    assert a["compared"] == 4 and a["skipped_errors"] == 1 and a["missing_verdicts"] == 1


def test_agreement_with_nothing_comparable_does_not_divide_by_zero():
    a = agreement([], [HumanLabel("1", True)])
    assert a["precision"] is None and a["recall"] is None and a["compared"] == 0


@pytest.mark.parametrize("path", ["evals/judge.py", "app/llm/gemini.py"])
def test_judge_code_cannot_reach_the_user_question_log(path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
    assert not {n for n in names if n.startswith(("app.usage", "app.service", "app.api"))}


def test_label_file_roundtrip(tmp_path):
    from evals.judge import load_labels
    p = tmp_path / "labels.jsonl"
    p.write_text(json.dumps({"question_id": "1", "correct": True}) + "\n")
    assert load_labels(p) == [HumanLabel("1", True)]
