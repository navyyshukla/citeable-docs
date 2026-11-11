"""Read what the help reply says. Not a pass/fail number: a person reads every reply.

Each question goes through the classifier (to see where it would land) and then through the help
reply regardless of the label (the worst case: the classifier said help). Automatic red flags mark
the obvious problems (a link, how-to steps, a claimed ability the fact sheet does not state); the
owner and I read all replies before anything ships. `run` spends neurons (two small calls each).

    python -m evals.help_eval run --out evals/results/help-<date>.json
"""
import argparse
import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from app.classify import classify_question
from app.config import Config, load_config
from app.help_reply import answer_help
from app.llm.base import Adapter

ROOT = Path(__file__).resolve().parents[1]
_HOWTO = re.compile(r"\b(?:press|type|hit|click|select|enter)\s+\S", re.IGNORECASE)
_CLAIM = re.compile(r"\bI\s+(?:can|will|could)\s+(?:open|run|access|browse|read|see|write|execute|"
                    r"remember|look at|check)\b", re.IGNORECASE)


class HelpQuestion(BaseModel):
    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    note: str | None = None


@dataclass(frozen=True)
class HelpRow:
    id: str
    question: str
    label: str  # what the classifier said
    reply: str | None  # None = the fixed Help card would show
    fixed_card: bool
    neurons: float
    seconds: float


def load_help_questions(path: Path | str) -> list[HelpQuestion]:
    out: list[HelpQuestion] = []
    seen: set[str] = set()
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            q = HelpQuestion.model_validate(json.loads(line))
        except (ValueError, ValidationError) as e:
            raise ValueError(f"{path} line {n}: {e}") from e
        if q.id in seen:
            raise ValueError(f"{path} line {n}: duplicate id {q.id!r}")
        seen.add(q.id)
        out.append(q)
    return out


def red_flags(row: HelpRow) -> list[str]:
    if row.reply is None:
        return []
    flags = []
    low = row.reply.lower()
    if "http" in low or "www." in low or "//" in low:
        flags.append("link")
    if _HOWTO.search(row.reply):
        flags.append("how-to")
    if _CLAIM.search(row.reply):
        flags.append("capability")
    return flags


def run_help(questions: list[HelpQuestion], adapter_factory: Callable[[], Adapter],
             cfg: Config) -> list[HelpRow]:
    rows = []
    for q in questions:
        adapter = adapter_factory()  # fresh per question, like a real request
        t0 = time.monotonic()
        label = classify_question(q.question, adapter, cfg)
        reply = answer_help(q.question, adapter, cfg)  # asked even if the label was not help
        rows.append(HelpRow(q.id, q.question, label, reply, reply is None, adapter.total_neurons,
                            time.monotonic() - t0))
    return rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="help_eval")
    p.add_argument("--config", default=str(ROOT / "config" / "visidata.yaml"))
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="classify and reply to every question (spends neurons)")
    r.add_argument("--out", required=True)
    r.add_argument("--questions", default=str(ROOT / "evals/data/help_questions.jsonl"))
    args = p.parse_args(argv)
    from app.llm.build import build_adapter
    cfg = load_config(args.config)
    rows = run_help(load_help_questions(args.questions),
                    lambda: build_adapter(cfg, os.environ), cfg)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps([asdict(x) for x in rows], indent=2), encoding="utf-8")
    for x in rows:
        print(f"[{x.id}] {x.question}\n   classifier: {x.label}\n   reply: "
              f"{x.reply if x.reply else '[fixed card]'}\n   flags: {red_flags(x) or 'none'}")
    print(f"neurons {sum(x.neurons for x in rows):.1f}; "
          f"median {sorted(x.seconds for x in rows)[len(rows) // 2]:.1f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
