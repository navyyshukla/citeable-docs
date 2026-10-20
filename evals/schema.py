import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator


class EvalQuestion(BaseModel):
    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    answerable: bool
    gold_page: str | None = None
    gold_heading: str | None = None
    # Other pages that also answer the question (any piece of them counts as a hit).
    also_gold_pages: list[str] = Field(default_factory=list)
    reference_answer: str | None = None
    source: Literal["real", "doc-based", "agent-made", "synthetic", "tricky"]
    source_url: str | None = None
    split: Literal["dev", "heldout"]

    @model_validator(mode="after")
    def _answerable_needs_gold(self) -> "EvalQuestion":
        if self.answerable and not self.gold_page:
            raise ValueError("answerable questions need gold_page")
        return self


def load_questions(path: Path) -> list[EvalQuestion]:
    out: list[EvalQuestion] = []
    seen: set[str] = set()
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            q = EvalQuestion.model_validate(json.loads(line))
        except (ValueError, ValidationError) as e:  # ValidationError is a ValueError too
            raise ValueError(f"{path} line {n}: {e}") from e
        if q.id in seen:
            raise ValueError(f"{path} line {n}: duplicate id {q.id!r}")
        seen.add(q.id)
        out.append(q)
    return out
