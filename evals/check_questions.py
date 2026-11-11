"""Check generated questions before they are trusted as test questions.

Two independent checkers read each question next to the docs page it was written from and say
whether the page really answers it. A question is kept only if BOTH pass. The page text is read
from the database and goes only to the checker (Gemini: public docs text and a test question, never
a user question) or to a local packet file; it is never written into a committed question file.

    python -m evals.check_questions gemini --data Q.jsonl --out RESULT.json
    python -m evals.check_questions packets --data Q.jsonl --out packets.md   (for the second reader)
    python -m evals.check_questions keep --data Q.jsonl --gemini A.json --other B.json --out KEPT.jsonl
"""
import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

from app.llm.base import ProviderError
from evals.schema import EvalQuestion, load_questions
from ingest.models import Piece

_SYSTEM = (
    "You check test questions for a documentation assistant. You are given a question and the "
    "text of the documentation page it was written from. Decide: is the question answerable "
    "from this page (answerable), would a newcomer plausibly ask it in plain words (sensible), "
    "and if a DIFFERENT page of the same documentation would clearly be the better place to find "
    "the answer, name it (better_page, else null). "
    'Return JSON only: {"answerable": true|false, "sensible": true|false, '
    '"better_page": null|"page name", "reason": "one short sentence"}'
)


def build_check_prompt(question: str, page_text: str) -> tuple[str, str]:
    return _SYSTEM, f"Question: {question}\n\nDocumentation page text:\n{page_text}"


def parse_check(text: str) -> dict | None:
    """The verdict if it has the right shape, else None."""
    try:
        d = json.loads(text)
    except (ValueError, TypeError):
        return None
    if (not isinstance(d, dict) or not isinstance(d.get("answerable"), bool)
            or not isinstance(d.get("sensible"), bool)):
        return None
    better = d.get("better_page")
    if better is not None and not isinstance(better, str):
        return None
    return {"answerable": d["answerable"], "sensible": d["sensible"],
            "better_page": better or None, "reason": str(d.get("reason", ""))[:300]}


def passes(check: dict | None) -> bool:
    return bool(check) and check["answerable"] and check["sensible"] and not check["better_page"]


def _page_text(page: str, pieces: list[Piece]) -> str:
    return "\n\n".join(p.text for p in pieces if p.page_slug == page)


def run_checks(questions: list[EvalQuestion], pieces: list[Piece], provider, *, pause: float = 6.0,
               sleep: Callable[[float], None] | None = None) -> list[dict]:
    """One provider call per question. A failed or unreadable reply is recorded as check=None
    (which counts as not passing)."""
    sleep = sleep or time.sleep
    out = []
    for n, q in enumerate(questions):
        if n and pause:
            sleep(pause)
        system, user = build_check_prompt(q.question, _page_text(q.gold_page or "", pieces))
        try:
            check = parse_check(provider.complete(system, user, 300).text)
        except ProviderError:
            check = None
        out.append({"id": q.id, "gold_page": q.gold_page, "question": q.question, "check": check})
    return out


def keep_both(questions: list[EvalQuestion], first: list[dict], second: list[dict]
              ) -> tuple[list[EvalQuestion], set[str]]:
    """Questions both checkers pass, and the ids on which they split (one pass, one fail)."""
    a = {r["id"]: passes(r.get("check")) for r in first}
    b = {r["id"]: passes(r.get("check")) for r in second}
    kept = [q for q in questions if a.get(q.id) and b.get(q.id)]
    split = {q.id for q in questions if a.get(q.id, False) != b.get(q.id, False)}
    return kept, split


def write_packets(questions: list[EvalQuestion], pieces: list[Piece], path: Path) -> Path:
    """A local text file for a second reader: each question next to its page. NOT committed."""
    lines = ["# Question check packets (local file: contains docs text, do not commit)", ""]
    for q in questions:
        lines += [f"## {q.id}", f"Question: {q.question}", f"Written from page: {q.gold_page}", "",
                  _page_text(q.gold_page or "", pieces), "", "---", ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    return Path(path)


def _pieces():
    from app.cli import _store
    from app.config import load_config
    cfg = load_config("config/visidata.yaml")
    return _store(cfg).load_pieces(cfg.project.slug)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="check_questions")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gemini")
    g.add_argument("--data", required=True)
    g.add_argument("--out", required=True)
    g.add_argument("--pause", type=float, default=6.0)
    k = sub.add_parser("packets")
    k.add_argument("--data", required=True)
    k.add_argument("--out", required=True)
    m = sub.add_parser("keep")
    m.add_argument("--data", required=True)
    m.add_argument("--gemini", required=True)
    m.add_argument("--other", required=True)
    m.add_argument("--out", required=True)
    args = p.parse_args(argv)
    questions = load_questions(Path(args.data))
    if args.cmd == "gemini":
        from app.llm.gemini import GeminiProvider
        provider = GeminiProvider(os.environ["GEMINI_API_KEY"], json_output=True)
        res = run_checks(questions, _pieces(), provider, pause=args.pause)
        Path(args.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
        print(f"{sum(passes(r['check']) for r in res)} of {len(res)} pass; wrote {args.out}")
    elif args.cmd == "packets":
        write_packets(questions, _pieces(), Path(args.out))
        print(f"wrote {args.out} (local, contains docs text)")
    else:
        first = json.loads(Path(args.gemini).read_text(encoding="utf-8"))
        second = json.loads(Path(args.other).read_text(encoding="utf-8"))
        kept, split = keep_both(questions, first, second)
        Path(args.out).write_text("".join(q.model_dump_json() + "\n" for q in kept), encoding="utf-8")
        print(f"kept {len(kept)} of {len(questions)}; {len(split)} split verdicts left out")
    return 0


if __name__ == "__main__":
    sys.exit(main())
