import json

import pytest

from app.llm.base import Completion, ProviderError
from evals.check_questions import (build_check_prompt, keep_both, parse_check, passes,
                                   run_checks, write_packets)
from evals.schema import EvalQuestion, load_questions
from ingest.models import Piece

BODY = "SECRET-PAGE-BODY"


def piece(page="join", i=0, heading="How to join"):
    return Piece(id=f"{page}:{i}", page_slug=page, page_title=page.title(), url="https://x/y/",
                 anchor="a", heading_path=(page.title(), heading), text=f"{BODY} {page} {i}",
                 docs_ref="stable@abc", docs_version="3.0", last_updated="2026-01-01")


def q(i, page="join"):
    return EvalQuestion(id=f"h-{i:03d}", question=f"how do I join {i}?", answerable=True,
                        gold_page=page, gold_heading="How to join", source="synthetic",
                        split="heldout")


GOOD = {"answerable": True, "sensible": True, "better_page": None, "reason": "ok"}


def test_prompt_holds_the_question_and_the_page_text_and_asks_for_json():
    system, user = build_check_prompt("how do I join?", "PAGE TEXT HERE")
    assert "how do I join?" in user and "PAGE TEXT HERE" in user
    assert "JSON" in system and "answerable" in system and "better_page" in system


@pytest.mark.parametrize("text,ok", [
    (json.dumps(GOOD), True),
    (json.dumps({**GOOD, "better_page": "rows"}), True),   # parsed fine; passes() decides
    ("not json", False), (json.dumps({"answerable": True}), False),
    (json.dumps({**GOOD, "answerable": "yes"}), False), (json.dumps([GOOD]), False),
])
def test_parse_check_validates_the_shape(text, ok):
    assert (parse_check(text) is not None) is ok


def test_passes_needs_answerable_sensible_and_no_better_page():
    assert passes(GOOD)
    assert not passes({**GOOD, "answerable": False})
    assert not passes({**GOOD, "sensible": False})
    assert not passes({**GOOD, "better_page": "rows"})
    assert not passes(None)


class FakeGemini:
    name = "gemini"

    def __init__(self, replies):
        self.replies, self.calls, self.prompts = list(replies), 0, []

    def complete(self, system, user, max_tokens):
        self.calls += 1
        self.prompts.append(user)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return Completion(r, "gemini", "m", 1, 1, None, 0.1)


def test_run_checks_sends_the_gold_page_and_records_errors_as_failures():
    pieces = [piece("join", 0), piece("join", 1), piece("rows", 0)]
    gem = FakeGemini([json.dumps(GOOD), ProviderError("HTTP 429", status=429), "garbage"])
    out = run_checks([q(1), q(2), q(3, "rows")], pieces, gem, pause=0, sleep=lambda s: None)
    assert [r["id"] for r in out] == ["h-001", "h-002", "h-003"]
    assert out[0]["check"] == GOOD and out[1]["check"] is None and out[2]["check"] is None
    assert "join 0" in gem.prompts[0] and "join 1" in gem.prompts[0] and "rows 0" not in gem.prompts[0]


def test_keep_both_needs_both_checkers_to_pass(tmp_path):
    qs = [q(1), q(2), q(3)]
    g = [{"id": "h-001", "check": GOOD}, {"id": "h-002", "check": GOOD},
         {"id": "h-003", "check": {**GOOD, "answerable": False}}]
    c = [{"id": "h-001", "check": GOOD}, {"id": "h-002", "check": {**GOOD, "sensible": False}},
         {"id": "h-003", "check": GOOD}]
    kept, split = keep_both(qs, g, c)
    assert [x.id for x in kept] == ["h-001"]
    assert split == {"h-002", "h-003"}  # one passed, one failed


def test_packets_hold_page_text_but_only_in_the_file_asked_for(tmp_path):
    pieces = [piece("join", 0)]
    f = write_packets([q(1)], pieces, tmp_path / "packets.md")
    text = f.read_text(encoding="utf-8")
    assert "h-001" in text and "how do I join 1?" in text and BODY in text
    # the committed question file never holds page text
    qf = tmp_path / "q.jsonl"
    qf.write_text(q(1).model_dump_json() + "\n", encoding="utf-8")
    assert BODY not in qf.read_text(encoding="utf-8") and load_questions(qf)
