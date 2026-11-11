"""Does the question classifier send the right questions to the fixed cards?

The test set is questions only (public text, no answers). The bar is set before any run:
no real how-to question may reach a card, and at least 90% of the about/help phrasings must
reach the right card. `run` spends neurons (one tiny model call per question); `score` is free.

    python -m evals.cards_eval run --out evals/results/cards-<date>.json
    python -m evals.cards_eval score --in evals/results/cards-<date>.json
"""
import argparse
import json
import os
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.classify import classify_question
from app.config import Config, load_config
from app.llm.base import Adapter
from evals.schema import load_questions

MAX_FALSE_CARDS = 0  # a real question sent to a card hides an answer: not allowed at all
MIN_POSITIVE_RATE = 0.9  # about/help phrasings that reach the right card
ROOT = Path(__file__).resolve().parents[1]


class CardQuestion(BaseModel):
    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    label: Literal["about", "help", "normal"]
    note: str | None = None


@dataclass(frozen=True)
class CardRow:
    id: str
    question: str
    label: str
    predicted: str
    neurons: float
    seconds: float
    provider: str | None = None  # who classified (after any fallback)
    model: str | None = None
    calls: int = 0  # more than 1 means a provider failed or timed out first


@dataclass(frozen=True)
class CardScore:
    n: int
    false_cards: int  # a "normal" question predicted as a card
    positives_total: int
    positives_right: int
    passes: bool


def load_card_questions(path: Path | str) -> list[CardQuestion]:
    out: list[CardQuestion] = []
    seen: set[str] = set()
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            q = CardQuestion.model_validate(json.loads(line))
        except (ValueError, ValidationError) as e:
            raise ValueError(f"{path} line {n}: {e}") from e
        if q.id in seen:
            raise ValueError(f"{path} line {n}: duplicate id {q.id!r}")
        seen.add(q.id)
        out.append(q)
    return out


def dev_negatives(path: Path | str) -> list[CardQuestion]:
    """Every answerable dev question must stay normal: they are the questions that work today."""
    return [CardQuestion(id=f"dev:{q.id}", question=q.question, label="normal",
                         note="answerable dev question")
            for q in load_questions(Path(path)) if q.answerable]


def run_cards(questions: list[CardQuestion], adapter_factory: Callable[[], Adapter],
              cfg: Config) -> list[CardRow]:
    rows = []
    for q in questions:
        adapter = adapter_factory()  # fresh per question, like a real request
        t0 = time.monotonic()
        predicted = classify_question(q.question, adapter, cfg)
        done = adapter.last_completion
        rows.append(CardRow(q.id, q.question, q.label, predicted, adapter.total_neurons,
                            time.monotonic() - t0, done.provider if done else None,
                            done.model if done else None, adapter.calls_made))
    return rows


def score_cards(rows: list[CardRow]) -> CardScore:
    false_cards = sum(r.label == "normal" and r.predicted != "normal" for r in rows)
    positives = [r for r in rows if r.label != "normal"]
    right = sum(r.predicted == r.label for r in positives)
    passes = (bool(positives) and false_cards <= MAX_FALSE_CARDS
              and right / len(positives) >= MIN_POSITIVE_RATE)
    return CardScore(len(rows), false_cards, len(positives), right, passes)


def confusion(rows: list[CardRow]) -> dict[str, int]:
    return {f"{k[0]} -> {k[1]}": v for k, v in sorted(Counter((r.label, r.predicted) for r in rows).items())}


def report_rows(rows: list[CardRow]) -> dict:
    s = score_cards(rows)
    secs = sorted(r.seconds for r in rows)
    return {"score": asdict(s), "confusion": confusion(rows),
            "misses": [{"id": r.id, "question": r.question, "label": r.label,
                        "predicted": r.predicted} for r in rows if r.predicted != r.label],
            "providers": dict(Counter(f"{r.provider}:{r.model}" for r in rows)),
            "fallback_rows": sum(r.calls > 1 for r in rows),
            "neurons_total": round(sum(r.neurons for r in rows), 2),
            "seconds_median": round(secs[len(secs) // 2], 2) if secs else None,
            "seconds_max": round(secs[-1], 2) if secs else None}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="cards_eval")
    p.add_argument("--config", default=str(ROOT / "config" / "visidata.yaml"))
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="classify every test question (spends neurons)")
    r.add_argument("--out", required=True)
    r.add_argument("--questions", default=str(ROOT / "evals/data/cards.jsonl"))
    r.add_argument("--dev", default=str(ROOT / "evals/data/dev.jsonl"))
    s = sub.add_parser("score", help="score a saved run (free)")
    s.add_argument("--in", dest="infile", required=True)
    args = p.parse_args(argv)
    if args.cmd == "run":
        from app.llm.build import build_adapter
        cfg = load_config(args.config)
        qs = load_card_questions(args.questions) + dev_negatives(args.dev)
        rows = run_cards(qs, lambda: build_adapter(cfg, os.environ), cfg)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps({"rows": [asdict(x) for x in rows],
                                              "report": report_rows(rows)}, indent=2), encoding="utf-8")
        print(json.dumps(report_rows(rows), indent=2))
    else:
        data = json.loads(Path(args.infile).read_text(encoding="utf-8"))
        rows = [CardRow(**x) for x in data["rows"]]
        print(json.dumps(report_rows(rows), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
