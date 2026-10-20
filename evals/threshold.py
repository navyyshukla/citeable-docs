"""The evidence threshold is a dial: answer more, or be wrong less. This prints both sides.

It reads saved retrieval results, so it makes no model or embedding call (no neurons).
"""
from dataclasses import dataclass

from evals.runner import RetrievalRow


@dataclass(frozen=True)
class ThresholdRow:
    threshold: float
    answered_pct: float
    wrong_when_answered_pct: float | None  # None when nothing is answered
    correctly_abstained_pct: float | None  # of the unanswerable questions; None if there are none


def _best(r: RetrievalRow) -> float:
    return max(r.top_scores, default=float("-inf"))  # an error or empty search finds nothing


def threshold_table(rows: list[RetrievalRow], thresholds: list[float]) -> list[ThresholdRow]:
    """"Answered" = best score >= threshold. "Wrong" = answered, but the question is
    unanswerable or none of the top pieces matches the gold page (a proxy: the real check is
    whether the final answer cites a gold piece)."""
    if not rows:
        return []
    out = []
    unanswerable = [r for r in rows if not r.answerable]
    for t in thresholds:
        answered = [r for r in rows if _best(r) >= t]
        wrong = [r for r in answered if not r.answerable or not r.hit]
        abstained_ok = [r for r in unanswerable if _best(r) < t]
        out.append(ThresholdRow(
            t, 100.0 * len(answered) / len(rows),
            100.0 * len(wrong) / len(answered) if answered else None,
            100.0 * len(abstained_ok) / len(unanswerable) if unanswerable else None))
    return out
