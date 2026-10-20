"""Run code-graded evals: retrieval hit rate, abstention, citation validity, calls, neurons."""
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.answer import answer_question, validate_question
from app.config import Config
from app.llm.base import Adapter, AllProvidersFailed, ProviderError
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
    error: str | None = None  # the search failed (e.g. the embedding call): counted as a miss


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
    cited_ids: list[str] = field(default_factory=list)  # pieces the answer cites
    cited_gold: bool | None = None  # answerable and answered: does a cited piece match the gold?
    error: str | None = None  # status "error": the question failed, the run went on


def run_retrieval(questions: list[EvalQuestion], searcher: Searcher,
                  pieces_by_id: dict[str, Piece], mode: str, k: int) -> list[RetrievalRow]:
    rows = []
    for q in questions:
        try:
            hits = searcher.search(mode, q.question, k)
        except ProviderError as e:  # not ValueError: that would hide a wrong mode as errors
            rows.append(RetrievalRow(q.id, mode, q.answerable, False if q.answerable else None,
                                     [], [], error=str(e)))
            continue
        hit = None
        if q.answerable:
            hit = any(is_hit(pieces_by_id[h.piece_id], q) for h in hits
                      if h.piece_id in pieces_by_id)
        rows.append(RetrievalRow(q.id, mode, q.answerable, hit,
                                 [h.piece_id for h in hits], [h.score for h in hits]))
    return rows


def _error_row(q: EvalQuestion, mode: str, e: Exception) -> AnswerRow:
    return AnswerRow(q.id, mode, q.answerable, "error", None, 0, 0, None, None, error=str(e))


def run_answers(questions: list[EvalQuestion], searcher: Searcher, pieces_by_id: dict[str, Piece],
                adapter: Adapter, cfg: Config, project_name: str, mode: str, k: int,
                max_neurons: float) -> tuple[list[AnswerRow], bool]:
    rows: list[AnswerRow] = []
    for q in questions:
        if adapter.total_neurons >= max_neurons:
            return rows, True
        # A bad question or a failed call becomes one "error" row and the run goes on (the
        # neurons already spent stay counted). A wrong mode is a setup bug and still raises.
        try:
            validate_question(q.question, cfg)  # before any search: no embedding call for it
        except ValueError as e:
            rows.append(_error_row(q, mode, e))
            continue
        try:
            hits = searcher.search(mode, q.question, k)
            a = answer_question(q.question, hits, pieces_by_id, adapter, cfg, project_name)
        except (AllProvidersFailed, ProviderError) as e:
            rows.append(_error_row(q, mode, e))
            continue
        abstained_ok = (a.status == "abstained") if not q.answerable else None
        kept = [pieces_by_id[h.piece_id] for h in hits if h.piece_id in pieces_by_id]
        cited = [kept[c.n - 1] for c in a.citations if 1 <= c.n <= len(kept)]
        cited_gold = (any(is_hit(p, q) for p in cited)
                      if a.status == "answered" and q.answerable else None)
        rows.append(AnswerRow(q.id, mode, q.answerable, a.status, abstained_ok,
                              len(a.invalid_citations), a.llm_calls, a.neurons, a.seconds,
                              [p.id for p in cited], cited_gold))
    return rows, False


def summarize_retrieval(rows: list[RetrievalRow]) -> dict:
    ans = [r for r in rows if r.answerable]
    hit = sum(1 for r in ans if r.hit)
    return {"n": len(rows), "answerable": len(ans), "hit": hit,
            "hit_rate": (hit / len(ans)) if ans else None,
            "errors": sum(1 for r in rows if r.error)}


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
        "answered_citing_gold": sum(1 for r in answered if r.cited_gold),
        "errors": sum(1 for r in rows if r.status == "error"),
        "answers_with_invalid_citations": sum(1 for r in answered if r.invalid_citations),
        "all_answers_used_one_call": (all(r.llm_calls == 1 for r in answered)
                                      if answered else None),
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
