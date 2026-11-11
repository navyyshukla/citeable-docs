"""Extra /evals sections: the refusal set, the sealed held-out set, and the models side by side.

Pure functions over saved run dicts (same shape as evals.report): nothing here calls a model.
Every rate carries its count; repeated runs of the same questions show a range, and the text says
what each set's labels are (written by us, or AI-checked only).
"""
from evals.report import (JUDGE_WARNING, Section, Stat, _answer_rows, _counts, _page_hit,
                          _rate_spread)
from evals.schema import EvalQuestion
from evals.stats import fraction_text
from ingest.models import Piece


def _series(label: str, per_run: list[tuple[int, int]], shown: int = -1) -> Stat:
    """One run's count (the latest by default; `shown=0` for a sealed set's reported first run),
    with the spread over all runs that have data."""
    k, n = per_run[shown]
    usable = [Stat(label, a, b) for a, b in per_run if b]
    spread = _rate_spread(usable) if len(usable) > 1 else None
    return Stat(label, k, n, spread, len(usable) if spread else 0)


def refusal_section(runs: list[dict]) -> Section:
    per_run, answered_any, errors = [], 0, 0
    for r in runs:
        c = _counts(_answer_rows(r))
        per_run.append((c["refused"], c["unanswerable_n"]))
        answered_any += sum(1 for x in _answer_rows(r)
                            if not x["answerable"] and x["status"] == "answered")
        errors += c["errors"]
    notes = [f"{len(runs)} run{'s' if len(runs) != 1 else ''} of the same questions: the range shows "
             "run-to-run wobble, not performance on new questions.",
             "These questions go straight to the answer step. In the live assistant a question "
             "like 'what is VisiData?' or 'what can you do?' is caught earlier by a classifier and "
             "shown a fixed card, which this test does not include."]
    if answered_any:
        notes.append(f"{answered_any} question(s) the docs are not meant to cover were answered in at "
                     "least one run. Each answer is read together with its cited pages to decide "
                     "whether our label was wrong or the system guessed.")
    else:
        notes.append("No question was answered in any run, so there was no label to audit.")
    if errors:
        notes.append(f"{errors} question(s) errored (not counted as answers or refusals).")
    return Section(
        "Refusal test: questions the docs do not answer",
        "Written by us in six groups: near-miss VisiData features, other tools, off-topic, "
        "attempts to override the rules, vague or incomplete, code requests and gibberish. "
        "'The docs do not answer this' is our judgement, not an AI check.",
        [_series("unanswerable refused", per_run)], notes, [])


def _cited_page(row: dict, q: EvalQuestion | None, pieces: dict[str, Piece]) -> bool:
    if q is None or q.gold_page is None:
        return False
    wanted = {q.gold_page, *q.also_gold_pages}
    return any(pieces[i].page_slug in wanted for i in row.get("cited_ids") or [] if i in pieces)


def heldout_section(runs: list[dict], questions: list[EvalQuestion], verdicts: dict[str, dict],
                    pieces: dict[str, Piece]) -> Section:
    by_id = {q.id: q for q in questions}
    series: dict[str, list[tuple[int, int]]] = {k: [] for k in (
        "answered", "page", "section", "invalid", "top5_page", "top5_section")}
    for r in runs:
        rows = [x for x in _answer_rows(r) if x["status"] != "error"]
        ans = [x for x in rows if x["status"] == "answered"]
        series["answered"].append((len(ans), len(rows)))
        series["page"].append((sum(_cited_page(x, by_id.get(x["id"]), pieces) for x in ans), len(ans)))
        series["section"].append((sum(bool(x.get("cited_gold")) for x in ans), len(ans)))
        series["invalid"].append((sum(1 for x in ans if x["invalid_citations"]), len(ans)))
        ret = [x for x in (r.get("retrieval") or {}).get("hybrid", []) if x["answerable"]]
        series["top5_page"].append((sum(_page_hit(x, by_id, pieces) for x in ret), len(ret)))
        series["top5_section"].append((sum(1 for x in ret if x["hit"]), len(ret)))
    stats = [
        _series("answered", series["answered"], 0),
        _series("of the answered, cited the right page (any section)", series["page"], 0),
        _series("of the answered, cited the right page and section", series["section"], 0),
        _series("answers with an invalid citation", series["invalid"], 0),
        _series("right page (any section) in top 5", series["top5_page"], 0),
        _series("right page and section in top 5", series["top5_section"], 0),
    ]
    first = [x for x in _answer_rows(runs[0]) if x["status"] == "answered"] if runs else []
    judged = [verdicts[x["id"]]["correct"] for x in first
              if isinstance(verdicts.get(x["id"], {}).get("correct"), bool)]
    if judged:
        stats.append(Stat(f"AI judge says correct, run 1 ({JUDGE_WARNING})", sum(judged), len(judged)))
    notes = [
        "Sealed: these questions were never used to tune a prompt or a rule, and nothing was "
        "changed after reading their failures. Run 1 is the reported result; the other runs "
        "show how much it moves.",
        "Two independent readers (Gemini and a Claude agent) each checked every question against "
        "the page it was written from; only questions both passed were kept. No human has graded "
        "the answers.",
        "The questions were written in deliberately plain, non-docs wording ('backup shade'), "
        "which probably makes them harder than real questions.",
        f"{len(runs)} run{'s' if len(runs) != 1 else ''} of the same questions: the range is "
        "run-to-run wobble, not performance on new questions.",
    ]
    return Section("Held-out test: answerable questions nobody tuned for",
                   "Generated questions. AI-checked only, not human-checked.", stats, notes, [])


def models_section(model_runs: dict[str, dict[str, dict]]) -> Section:
    lines = []
    for name, runs in model_runs.items():
        ref = _counts(_answer_rows(runs["refusal"]))
        dev = _counts(_answer_rows(runs["dev"]))
        gold = sum(1 for x in dev["answered"] if x["answerable"] and x.get("cited_gold"))
        lines.append(
            f"{name}: refusal test, refused {fraction_text(ref['refused'], ref['unanswerable_n'])}; "
            f"dev set, unanswerable refused {fraction_text(dev['refused'], dev['unanswerable_n'])}; "
            f"dev set, answerable answered citing the right page and section "
            f"{fraction_text(gold, len(dev['answerable']))}; errors {ref['errors'] + dev['errors']}")
    notes = ["Each model ran alone, one run each: indicative, not a range. The main model's "
             "repeated runs are in the sections above."]
    if any("llama" in n.lower() for n in model_runs):
        notes.append("llama-3.1-8b answered several questions the docs do not cover and was removed "
                     "from the answer chain on 2026-11-12 (decision D28).")
    return Section("The answer models side by side",
                   "Same questions, each model forced alone. Fallback models only answer when the "
                   "main model fails.", [], notes, lines)
