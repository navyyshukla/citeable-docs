"""Run code-graded evals: retrieval hit rate, abstention, citation validity, calls, neurons."""
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from app.answer import answer_question
from app.config import Config
from app.llm.base import Adapter
from app.search import Searcher
from evals.schema import EvalQuestion
from ingest.models import Piece


def is_hit(piece: Piece, q: EvalQuestion) -> bool:
    if q.gold_page is None or piece.page_slug != q.gold_page:
        return False
    if q.gold_heading is None:
        return True
    want = q.gold_heading.lower()
    return any(want in h.lower() for h in piece.heading_path)


@dataclass(frozen=True)
class RetrievalRow:
    id: str
    mode: str
    answerable: bool
    hit: bool | None
    top_ids: list[str]
    top_scores: list[float]


@dataclass(frozen=True)
class AnswerRow:
    id: str
    mode: str
    answerable: bool
    status: str
    abstained_correctly: bool | None
    invalid_citations: int
    llm_calls: int
    neurons: float | None
    seconds: float | None


def run_retrieval(questions: list[EvalQuestion], searcher: Searcher,
                  pieces_by_id: dict[str, Piece], mode: str, k: int) -> list[RetrievalRow]:
    rows = []
    for q in questions:
        hits = searcher.search(mode, q.question, k)
        hit = None
        if q.answerable:
            hit = any(is_hit(pieces_by_id[h.piece_id], q) for h in hits
                      if h.piece_id in pieces_by_id)
        rows.append(RetrievalRow(q.id, mode, q.answerable, hit,
                                 [h.piece_id for h in hits], [h.score for h in hits]))
    return rows


def run_answers(questions: list[EvalQuestion], searcher: Searcher, pieces_by_id: dict[str, Piece],
                adapter: Adapter, cfg: Config, project_name: str, mode: str, k: int,
                max_neurons: float) -> tuple[list[AnswerRow], bool]:
    rows: list[AnswerRow] = []
    for q in questions:
        if adapter.total_neurons >= max_neurons:
            return rows, True
        hits = searcher.search(mode, q.question, k)
        a = answer_question(q.question, hits, pieces_by_id, adapter, cfg, project_name)
        abstained_ok = (a.status == "abstained") if not q.answerable else None
        rows.append(AnswerRow(q.id, mode, q.answerable, a.status, abstained_ok,
                              len(a.invalid_citations), a.llm_calls, a.neurons, a.seconds))
    return rows, False


def summarize_retrieval(rows: list[RetrievalRow]) -> dict:
    ans = [r for r in rows if r.answerable]
    hit = sum(1 for r in ans if r.hit)
    return {"n": len(rows), "answerable": len(ans), "hit": hit,
            "hit_rate": (hit / len(ans)) if ans else None}


def summarize_answers(rows: list[AnswerRow]) -> dict:
    unans = [r for r in rows if not r.answerable]
    answered = [r for r in rows if r.status == "answered"]
    neurons = [r.neurons for r in rows if r.neurons is not None]
    return {
        "n": len(rows),
        "unanswerable": len(unans),
        "abstained_correctly": sum(1 for r in unans if r.abstained_correctly),
        "answerable_but_abstained": sum(1 for r in rows if r.answerable and r.status == "abstained"),
        "answered": len(answered),
        "answers_with_invalid_citations": sum(1 for r in answered if r.invalid_citations),
        "all_answers_used_one_call": all(r.llm_calls == 1 for r in answered),
        "mean_neurons": (sum(neurons) / len(neurons)) if neurons else None,
    }


def write_results(path: Path, meta: dict, retrieval: dict[str, list[RetrievalRow]],
                  answers: dict[str, list[AnswerRow]]) -> None:
    data = {
        "meta": meta,
        "retrieval": {m: [asdict(r) for r in rows] for m, rows in retrieval.items()},
        "answers": {m: [asdict(r) for r in rows] for m, rows in answers.items()},
    }
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
