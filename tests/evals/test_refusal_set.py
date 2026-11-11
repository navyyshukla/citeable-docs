"""The refusal set: questions the docs do NOT answer, so the right behaviour is to refuse.

Six groups of ten by id: u-001..010 near-miss features the docs lack, 011..020 other tools and
comparisons, 021..030 off-topic, 031..040 attempts to override the rules, 041..050 vague or
incomplete, 051..060 code requests and gibberish. Labels are written by us and are checked after
a run: any question the system answers is read to decide whether the label was wrong.
"""
from evals.schema import load_questions

PATH = "evals/data/refusal.jsonl"
GROUPS = {"near-miss": (1, 10), "other tools": (11, 20), "off-topic": (21, 30),
          "override": (31, 40), "vague": (41, 50), "code and gibberish": (51, 60)}


def qs():
    return load_questions(PATH)


def test_sixty_unanswerable_heldout_questions_with_unique_ids():
    out = qs()
    assert len(out) >= 60
    assert all(not q.answerable and q.gold_page is None for q in out)
    assert all(q.split == "heldout" for q in out)
    ids = [q.id for q in out]
    assert len(set(ids)) == len(ids) and all(i.startswith("u-") for i in ids)
    assert {f"u-{n:03d}" for n in range(1, 61)} <= set(ids)


def test_every_group_has_ten_questions_and_the_right_source():
    by_id = {q.id: q for q in qs()}
    for name, (lo, hi) in GROUPS.items():
        group = [by_id[f"u-{n:03d}"] for n in range(lo, hi + 1)]
        assert len(group) == 10, name
        expected = "agent-made" if name in ("near-miss", "other tools") else "tricky"
        assert {q.source for q in group} == {expected}, name


def test_questions_fit_the_api_limit_and_are_not_duplicates_of_other_sets():
    out = qs()
    assert all(0 < len(q.question) <= 500 for q in out)
    own = [q.question.lower().strip() for q in out]
    assert len(set(own)) == len(own)
    other = {q.question.lower().strip() for f in ("dev", "synthetic")
             for q in load_questions(f"evals/data/{f}.jsonl")}
    assert not (set(own) & other)
