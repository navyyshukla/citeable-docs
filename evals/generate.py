"""Generated eval questions, and a small sheet to hand-check them.

Questions are written by Gemini from PUBLIC docs text only (never from user questions). The
output holds questions and gold page names, no copy of the docs text.
"""
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from app.llm.base import Completion, ProviderError
from evals.schema import EvalQuestion
from ingest.models import Piece

MAX_QUESTION_CHARS = 500  # the same limit the API enforces


class _Provider(Protocol):
    def complete(self, system: str, user: str, max_tokens: int) -> Completion: ...


_ANSWERABLE_SYSTEM = (
    "You write test questions for a documentation assistant. You are a newcomer who has never "
    "seen the documentation and does not know its vocabulary. Read the excerpt, then write 2 "
    "short questions a newcomer might ask whose answer is in the excerpt. Do not use the words "
    "of the heading, and do not copy phrases from the excerpt: describe the goal in plain "
    "everyday words. Each question must make sense on its own. "
    'Return JSON only: {"questions": ["...", "..."]}'
)

_UNANSWERABLE_SYSTEM = (
    "You write test questions for a documentation assistant. Write questions a newcomer might "
    "plausibly ask about the tool that are NOT covered by its documentation: features it does "
    "not have, comparisons with other products, or requests outside its scope. Each question "
    "must make sense on its own. "
    'Return JSON only: {"questions": ["...", "..."]}'
)


def build_prompt(piece: Piece) -> tuple[str, str]:
    heading = " › ".join(piece.heading_path)
    user = f"Heading (do not reuse its words): {heading}\n\nExcerpt:\n{piece.text}"
    return _ANSWERABLE_SYSTEM, user


def build_unanswerable_prompt(page_titles: list[str], n: int) -> tuple[str, str]:
    user = (f"Write {n} questions. The documentation has these pages: "
            f"{', '.join(page_titles)}. The questions must fall outside them.")
    return _UNANSWERABLE_SYSTEM, user


def _clean(text: str, existing: set[str]) -> list[str]:
    """Question strings from the model's JSON; drops anything unusable. Updates `existing`."""
    try:
        items = json.loads(text).get("questions")
    except (ValueError, AttributeError):
        return []
    if not isinstance(items, list):
        return []
    taken = {e.lower() for e in existing}
    out = []
    for item in items:
        if not isinstance(item, str):
            continue
        q = item.strip()
        if not q or len(q) > MAX_QUESTION_CHARS or q.lower() in taken:
            continue
        taken.add(q.lower())
        existing.add(q.lower())
        out.append(q)
    return out


def parse_questions(text: str, piece: Piece, next_id: int, existing: set[str]
                    ) -> list[EvalQuestion]:
    """`existing` holds lower-cased questions already taken; it is extended in place."""
    return [EvalQuestion(id=f"s-{next_id + i:03d}", question=q, answerable=True,
                         gold_page=piece.page_slug, gold_heading=piece.heading_path[-1],
                         source="synthetic", split="dev")
            for i, q in enumerate(_clean(text, existing))]


def parse_unanswerable(text: str, next_id: int, existing: set[str]) -> list[EvalQuestion]:
    return [EvalQuestion(id=f"s-{next_id + i:03d}", question=q, answerable=False,
                         source="synthetic", split="dev")
            for i, q in enumerate(_clean(text, existing))]


def generate(pieces: list[Piece], provider: _Provider, *, limit: int, pause: float = 6.0,
             existing: set[str], start_id: int = 1,
             sleep: Callable[[float], None] | None = None) -> list[EvalQuestion]:
    """One provider call per piece, at most `limit` calls. A failed call is skipped.
    The pause keeps under the free tier's per-minute limit."""
    sleep = sleep or time.sleep  # looked up at call time so tests can replace it
    out: list[EvalQuestion] = []
    seen = set(existing)
    for n, piece in enumerate(pieces[:limit]):
        if n:
            sleep(pause)
        system, user = build_prompt(piece)
        try:
            c = provider.complete(system, user, 600)
        except ProviderError:
            continue
        out += parse_questions(c.text, piece, start_id + len(out), seen)
    return out


def write_check_sheet(questions: list[EvalQuestion], path: Path, every: int = 5) -> int:
    """A markdown checklist of every `every`-th question for the owner to read: is it a real,
    sensible question, and is the gold page right? Returns the rows written."""
    rows = questions[::every]
    lines = ["# Hand-check sheet", "",
             "For each row: is it a sensible question a newcomer would ask, and does the gold "
             "page really answer it? Mark `ok` or `bad` and say why.", ""]
    for q in rows:
        gold = f"{q.gold_page} › {q.gold_heading}" if q.answerable else "(none: should abstain)"
        lines += [f"- [ ] **{q.id}** {q.question}", f"  - gold: {gold}", "  - verdict: "]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(rows)
