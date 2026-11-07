import json
from pathlib import Path

import pytest

from evals.judge_traps import (HAND_BREAKS, Trap, _apply, blind_export, build_traps,
                               format_report, good_answers, load_verdicts, score)
from evals.schema import load_questions

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "evals/results/answers-hybrid-2026-10-20.json"
LABELS = ROOT / "evals/results/human-labels.jsonl"
DATA = ROOT / "evals/data/dev.jsonl"


@pytest.fixture(scope="module")
def traps():
    # evals/results/ is git-ignored, so a clean checkout (CI) has no saved answers: skip, like the
    # real-database tests do.
    if not (RESULTS.exists() and LABELS.exists()):
        pytest.skip("saved eval answers and labels are git-ignored and absent here")
    results = json.loads(RESULTS.read_text(encoding="utf-8"))
    labels = {d["question_id"]: d["correct"] for d in map(json.loads, LABELS.read_text(
        encoding="utf-8").splitlines()) if d}
    return build_traps(good_answers(results, load_questions(DATA), labels, "hybrid"))


def test_groups_and_sizes(traps):
    count = {g: sum(t.group == g for t in traps) for g in ("control", "hand", "swap", "vague",
                                                          "real")}
    assert count == {"control": 15, "hand": 11, "swap": 8, "vague": 7, "real": 2}
    assert len({t.id for t in traps}) == len(traps)


def test_every_hand_break_changes_its_answer(traps):
    base = {t.base_id: t.answer for t in traps if t.group == "control"}
    hand = [t for t in traps if t.group == "hand"]
    assert len(hand) == len(HAND_BREAKS)
    assert all(t.answer != base[t.base_id] for t in hand)
    assert all(t.expect_correct is False for t in traps if t.group not in ("control",))


def test_swap_uses_the_target_question_and_its_own_excerpts(traps):
    for t in (t for t in traps if t.group == "swap"):
        answer_of, target = t.id.split(":")[1].split("@")
        assert answer_of != target
        assert t.base_id == answer_of
        assert t.excerpt_ids == next(c.excerpt_ids for c in traps
                                     if c.group == "control" and c.base_id == target)


def test_edit_must_match_exactly_once():
    with pytest.raises(ValueError):
        _apply("abc", {"edits": [("zzz", "y")]})
    with pytest.raises(ValueError):
        _apply("aa", {"edits": [("a", "b")]})
    assert _apply("aa", {"edits": [("a", "b", 2)], "append": "!"}) == "bb!"


def test_blind_export_has_no_labels_and_shuffles(traps):
    out = blind_export(traps, {})
    text = json.dumps(out)
    assert len(out["items"]) == len(traps)
    assert not any(w in text for w in ('"group"', "control:", "hand:", "swap:", "expect"))
    assert [i["id"] for i in out["items"]] == sorted(i["id"] for i in out["items"])
    assert len({t.blind_id for t in traps}) == len(traps)


def _t(id_, group, blind, expect_correct=False, ungrounded=False):
    return Trap(id_, group, "k", "b", "q", None, "a", [], expect_correct, ungrounded, blind)


def test_score_pass_and_fail_and_errors():
    traps = ([_t(f"control:{i}", "control", f"c{i}", True) for i in range(4)]
             + [_t(f"hand:{i}", "hand", f"h{i}", ungrounded=i == 0) for i in range(5)])
    ok = {f"control:{i}": {"correct": True, "grounded": True} for i in range(4)}
    ok.update({f"hand:{i}": {"correct": False, "grounded": i != 0} for i in range(4)})
    ok["hand:4"] = {"correct": True, "grounded": True}  # one miss out of 5 = 80%
    s = score(traps, ok)
    assert (s["trap_caught"], s["trap_total"], s["false_alarms"]) == (4, 5, 0)
    assert s["pass"] is True and s["missed"] == ["hand:4"]
    assert s["ungrounded"] == {"n": 1, "caught": 1}

    ok["control:0"] = {"correct": False}
    ok["control:1"] = {"correct": False}
    assert score(traps, ok)["pass"] is False  # two false alarms

    ok["control:0"] = {"correct": True}
    ok["control:1"] = {"correct": True}
    ok["hand:3"] = {"error": "judge output was not the expected JSON", "correct": None}
    s = score(traps, ok)
    assert s["errors"] == 1 and s["pass"] is False  # an error is never a catch
    assert "NOT PASSED" in format_report(s)


def test_score_reads_blind_ids_and_both_verdict_file_shapes(tmp_path):
    traps = [_t("hand:1", "hand", "j01")]
    f = tmp_path / "v.json"
    f.write_text(json.dumps({"j01": {"correct": False, "grounded": True}}), encoding="utf-8")
    assert score(traps, load_verdicts(f))["trap_caught"] == 1
    f.write_text(json.dumps([{"question_id": "hand:1", "correct": False}]), encoding="utf-8")
    assert score(traps, load_verdicts(f))["trap_caught"] == 1
