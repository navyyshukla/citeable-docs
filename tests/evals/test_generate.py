import json

from app.llm.base import Completion, ProviderError
from evals.generate import (build_prompt, build_unanswerable_prompt, generate, parse_questions,
                            parse_unanswerable, write_check_sheet)
from evals.schema import load_questions
from ingest.models import Piece

SECRET = "SECRET-PIECE-BODY-TEXT"


def piece(i=0, slug="join", heading="How to join"):
    return Piece(id=f"{slug}:{i}", page_slug=slug, page_title=slug.title(), url="https://x/y/",
                 anchor="a", heading_path=(slug.title(), heading), text=SECRET,
                 docs_ref="stable@abc", docs_version="3.0", last_updated="2026-01-01")


def reply(*qs):
    return json.dumps({"questions": list(qs)})


class FakeGemini:
    name = "gemini"

    def __init__(self, replies=None, fail_on=()):
        self.replies, self.fail_on, self.calls = list(replies or []), set(fail_on), 0

    def complete(self, system, user, max_tokens):
        self.calls += 1
        if self.calls in self.fail_on:
            raise ProviderError("HTTP 429", status=429)
        text = self.replies.pop(0) if self.replies else reply(f"question number {self.calls}?")
        return Completion(text, "gemini", "m", 1, 1, None, 0.1)


def test_prompt_asks_for_newcomer_wording_without_heading_words_as_json():
    system, user = build_prompt(piece())
    low = system.lower()
    assert "never seen" in low and "newcomer" in low
    assert "do not use" in low and "heading" in low
    assert '"questions"' in system and "json" in low
    assert "How to join" in user  # the heading is shown so the model knows what to avoid
    assert SECRET in user  # the public docs text is what the question must be answerable from


def test_parse_questions_sets_gold_and_continues_ids():
    qs = parse_questions(reply("How do I stack two files?", "Can I merge files?"), piece(),
                         next_id=7, existing=set())
    assert [q.id for q in qs] == ["s-007", "s-008"]
    q = qs[0]
    assert (q.source, q.split, q.answerable) == ("synthetic", "dev", True)
    assert q.gold_page == "join" and q.gold_heading == "How to join"


def test_parse_questions_drops_bad_items():
    long = "x" * 501
    text = reply("ok one?", "", "   ", long, "OK ONE?", "Already there?", 5, None, "fine two?")
    qs = parse_questions(text, piece(), next_id=1, existing={"already there?"})
    assert [q.question for q in qs] == ["ok one?", "fine two?"]


def test_parse_questions_survives_malformed_json_and_wrong_shapes():
    for bad in ["not json", "", "[]", '{"questions": "text"}', '{"other": []}', "null"]:
        assert parse_questions(bad, piece(), next_id=1, existing=set()) == []


def test_exactly_500_characters_is_kept():
    q = "x" * 500
    assert len(parse_questions(reply(q), piece(), 1, set())) == 1


def test_unanswerable_prompt_and_parse():
    system, user = build_unanswerable_prompt(["Join", "Sorting"], 3)
    assert "3" in user and "Join" in user and "not covered" in system.lower()
    qs = parse_unanswerable(reply("Does it have a dark mode?"), next_id=40, existing=set())
    assert qs[0].id == "s-040" and qs[0].answerable is False
    assert qs[0].gold_page is None and qs[0].gold_heading is None
    assert parse_unanswerable("not json", 1, set()) == []


def test_generate_calls_the_provider_at_most_limit_times_and_pauses_between():
    sleeps = []
    prov = FakeGemini()
    pieces = [piece(i, slug=f"p{i}") for i in range(10)]
    out = generate(pieces, prov, limit=3, pause=6.0, existing=set(), sleep=sleeps.append)
    assert prov.calls == 3 and len(out) == 3
    assert sleeps == [6.0, 6.0]  # between calls, not after the last
    assert [q.id for q in out] == ["s-001", "s-002", "s-003"]


def test_generate_skips_a_failed_call_and_keeps_going():
    prov = FakeGemini(fail_on={1})
    out = generate([piece(0), piece(1)], prov, limit=2, pause=0, existing=set(),
                   sleep=lambda s: None)
    assert prov.calls == 2 and len(out) == 1


def test_generate_never_repeats_a_question_across_pieces():
    prov = FakeGemini(replies=[reply("same?"), reply("Same?"), reply("other?")])
    out = generate([piece(0), piece(1), piece(2)], prov, limit=3, pause=0, existing=set(),
                   sleep=lambda s: None)
    assert [q.question for q in out] == ["same?", "other?"]


def test_check_sheet_has_every_fifth_question_and_no_piece_text(tmp_path):
    qs = []
    for i in range(10):
        qs += parse_questions(reply(f"question {i}?"), piece(i, slug=f"p{i}"), len(qs) + 1, set())
    path = tmp_path / "sheet.md"
    assert write_check_sheet(qs, path, every=5) == 2
    text = path.read_text(encoding="utf-8")
    assert "question 0?" in text and "question 5?" in text and "question 1?" not in text
    assert SECRET not in text
    assert write_check_sheet(qs, path, every=1) == 10
    assert write_check_sheet([], path) == 0


def test_a_written_jsonl_loads_back_and_holds_no_piece_text(tmp_path):
    qs = parse_questions(reply("a?", "b?"), piece(), 1, set())
    f = tmp_path / "s.jsonl"
    f.write_text("\n".join(q.model_dump_json() for q in qs) + "\n", encoding="utf-8")
    assert [q.id for q in load_questions(f)] == ["s-001", "s-002"]
    assert SECRET not in f.read_text(encoding="utf-8")
