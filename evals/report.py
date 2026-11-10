"""The public /evals page: numbers with their n and range, what they miss, every answer in full.

Nothing here calls a model or the network. It takes saved result files, hand labels, judge
verdicts and the pieces, and builds one static HTML page. Every rate shows k/n and a 95% range
(evals.stats), and the page says in plain words what a number cannot see.
"""
import html
from dataclasses import dataclass, field

from app.config import Config
from evals.schema import EvalQuestion
from evals.stats import fraction_text, spread
from ingest.models import Piece

DEV = "dev"
SYNTHETIC = "synthetic"
GROUP_NOTE = {
    DEV: "Questions written from real forum and issue posts and from the docs.",
    SYNTHETIC: "Generated questions. AI-checked only, not human-checked.",
}
JUDGE_WARNING = "rough filter, misses docs errors and unhelpful answers"


@dataclass(frozen=True)
class Stat:
    label: str
    k: int
    n: int
    # (lowest, highest) rate across repeated dev runs; None when there is only one run
    spread: tuple[float, float] | None = None
    runs: int = 0  # how many runs the spread covers


@dataclass(frozen=True)
class RunRow:
    group: str
    name: str
    n_questions: int
    refused: Stat
    valid_citation: Stat
    errors: int


@dataclass(frozen=True)
class QuestionRow:
    group: str
    id: str
    question: str
    answerable: bool
    status: str
    text: str | None
    sources: list[tuple[str, str]]  # (title, url)
    label: bool | None  # hand grade
    judge: bool | None  # AI judge, a rough filter
    note: str | None  # known-wrong note


@dataclass(frozen=True)
class Report:
    headline: list[Stat]
    honesty: list[str]
    known_wrong: list[tuple[str, str]]
    history: list[RunRow]
    rows: list[QuestionRow]
    generated: list[Stat] = field(default_factory=list)  # stats for the generated-question runs


def _answer_rows(run: dict) -> list[dict]:
    answers = run.get("answers") or {}
    mode = "hybrid" if "hybrid" in answers else next(iter(answers), None)
    return list(answers[mode]) if mode else []


def _group(run: dict, by_id: dict[str, EvalQuestion]) -> str:
    ids = [r["id"] for r in _answer_rows(run)]
    if not ids:
        ids = [r["id"] for rows in (run.get("retrieval") or {}).values() for r in rows]
    synth = sum(1 for i in ids if i in by_id and by_id[i].source == "synthetic")
    return SYNTHETIC if ids and synth * 2 > len(ids) else DEV


def _counts(rows: list[dict]) -> dict:
    """Error rows are counted apart: they are never an answer, a refusal or a miss."""
    ok = [r for r in rows if r["status"] != "error"]
    answerable = [r for r in ok if r["answerable"]]
    unanswerable = [r for r in ok if not r["answerable"]]
    answered = [r for r in ok if r["status"] == "answered"]
    return {
        "errors": len(rows) - len(ok), "answerable": answerable, "answered": answered,
        "refused": sum(1 for r in unanswerable if r.get("abstained_correctly")),
        "unanswerable_n": len(unanswerable),
        "valid": sum(1 for r in answerable
                     if r["status"] == "answered" and not r["invalid_citations"]),
        "invalid": sum(1 for r in answered if r["invalid_citations"]),
    }


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _headline(run: dict, labels: dict[str, bool], by_id: dict[str, EvalQuestion],
              pieces: dict[str, Piece]) -> list[Stat]:
    c = _counts(_answer_rows(run))
    graded = [labels[r["id"]] for r in c["answered"] if r["id"] in labels]
    stats = [
        Stat("unanswerable refused", c["refused"], c["unanswerable_n"]),
        Stat("answerable answered with a valid citation", c["valid"], len(c["answerable"])),
        Stat("invalid citations", c["invalid"], len(c["answered"])),
        Stat("hand-graded correct", sum(graded), len(graded)),
    ]
    for mode, rrows in (run.get("retrieval") or {}).items():
        ans = [r for r in rrows if r["answerable"]]
        stats.append(Stat(f"right page in top 5 ({mode})",
                          sum(1 for r in ans if r["hit"]), len(ans)))
        stats.append(Stat(f"right page (any section) in top 5 ({mode})",
                          sum(1 for r in ans if _page_hit(r, by_id, pieces)), len(ans)))
    return stats


def _page_hit(row: dict, by_id: dict[str, EvalQuestion], pieces: dict[str, Piece]) -> bool:
    """Looser than the exact hit: any piece of a gold page counts, whatever its heading."""
    q = by_id.get(row["id"])
    if q is None or q.gold_page is None:
        return False
    wanted = {q.gold_page, *q.also_gold_pages}
    return any(pieces[i].page_slug in wanted for i in row.get("top_ids") or [] if i in pieces)


def _across_runs(runs: list[dict], labels, by_id, pieces) -> list[Stat]:
    """Latest run's counts, with the range over all the given runs when there are several."""
    per_run = [_headline(r, labels, by_id, pieces) for r in runs]
    if len(runs) == 1:
        return per_run[0]
    return [Stat(s.label, s.k, s.n, _rate_spread([p[i] for p in per_run]), len(per_run))
            for i, s in enumerate(per_run[-1])]


def _rate_spread(stats: list[Stat]) -> tuple[float, float] | None:
    rates = [s.k / s.n for s in stats if s.n]
    return spread(rates) if rates else None


def build_report(runs: list[dict], labels: dict[str, bool], verdicts: dict[str, dict],
                 trap: dict | None, questions: list[EvalQuestion], pieces: dict[str, Piece],
                 known_wrong: dict[str, str]) -> Report:
    by_id = {x.id: x for x in questions}
    grouped = [(_group(r, by_id), r) for r in runs]
    latest: dict[str, dict] = {}  # last run given for each group: its rows are shown in full
    for g, r in grouped:
        latest[g] = r

    history = []
    seen_in_group: dict[str, int] = {}
    for g, r in grouped:
        c = _counts(_answer_rows(r))
        seen_in_group[g] = seen_in_group.get(g, 0) + 1
        history.append(RunRow(
            g, f"run {seen_in_group[g]}: {r['meta'].get('ref', '?')}, "
               f"{r['meta'].get('n_questions', '?')} questions",
            r["meta"].get("n_questions", 0),
            Stat("unanswerable refused", c["refused"], c["unanswerable_n"]),
            Stat("answerable answered with a valid citation", c["valid"], len(c["answerable"])),
            c["errors"]))

    dev_runs = [r for g, r in grouped if g == DEV]  # generated questions never feed the headline
    head = dev_runs[-1] if dev_runs else None
    rows_head = _answer_rows(head) if head else []
    c = _counts(rows_head)
    headline = _across_runs(dev_runs, labels, by_id, pieces) if dev_runs else _headline(
        {"answers": {}}, labels, by_id, pieces)
    if len(dev_runs) > 1:
        headline = [Stat("hand-graded correct (from an earlier run)", s.k, s.n)
                    if s.label.startswith("hand-graded") else s for s in headline]
    synth_runs = [r for g, r in grouped if g == SYNTHETIC]
    generated = [s for s in _across_runs(synth_runs, {}, by_id, pieces)
                 if not s.label.startswith("hand-graded")] if synth_runs else []

    n = len(c["answerable"])
    honesty = [f"This is {n} answerable and {c['unanswerable_n']} unanswerable questions, a small "
               "set: every rate shows its count and a 95% range."]
    if n:
        honesty.append(f"With {n} answerable questions, one question moves a rate by about "
                       f"{round(100 / n)} points.")
    if c["errors"]:
        honesty.append(f"{_plural(c['errors'], 'question')} errored in the latest run (not "
                       "counted as answers, refusals or misses).")
    if len(dev_runs) > 1:
        honesty.append(f"The numbers above are the latest of {len(dev_runs)} runs on the same "
                       "questions; the range shows how much they moved between runs. Hand grades "
                       "were made on earlier wording: an answer worded differently in a later run "
                       "was not graded again.")
    judged = [verdicts[r["id"]]["correct"] for r in c["answered"]
              if isinstance(verdicts.get(r["id"], {}).get("correct"), bool)]
    if judged:
        honesty.append(f"The AI judge ({JUDGE_WARNING}) said correct for {sum(judged)}/"
                       f"{len(judged)} answered questions. Hand grades above are the quality check.")
    if trap:
        honesty.append(f"Judge trap test: caught {trap['trap_caught']}/{trap['trap_total']} "
                       f"deliberately broken answers, {trap['false_alarms']} false alarms "
                       f"({JUDGE_WARNING}).")

    rows = []
    for g in (DEV, SYNTHETIC):
        r = latest.get(g)
        if not r:
            continue
        for a in _answer_rows(r):
            q = by_id.get(a["id"])
            sources = [(p.page_title, p.citation_url) for pid in a.get("cited_ids") or []
                       if (p := pieces.get(pid))]
            v = verdicts.get(a["id"], {}).get("correct")
            rows.append(QuestionRow(
                g, a["id"], q.question if q else a.get("question", ""), a["answerable"],
                a["status"], None if a["status"] == "error" else a.get("text"), sources,
                labels.get(a["id"]), v if isinstance(v, bool) else None,
                known_wrong.get(a["id"])))

    return Report(headline, honesty, sorted(known_wrong.items()), history, rows, generated)


def _stat_li(s: Stat) -> str:
    rng = ""
    if s.spread:
        lo, hi = round(s.spread[0] * 100), round(s.spread[1] * 100)
        rng = (f" <small>same in all {s.runs} runs</small>" if lo == hi
               else f" <small>across {s.runs} runs: {lo}%–{hi}%</small>")
    return (f"<li><span>{html.escape(s.label)}</span> "
            f"<strong>{fraction_text(s.k, s.n)}</strong>{rng}</li>")


def _link(title: str, url: str) -> str:
    t = html.escape(title)
    if url.startswith(("https://", "http://")):
        return f'<a href="{html.escape(url, quote=True)}" rel="noopener noreferrer">{t}</a>'
    return t  # never a clickable javascript: or data: URL


def _row_html(r: QuestionRow) -> str:
    esc = html.escape
    if r.status == "error":
        body = "<p><em>This question errored; it is not counted as an answer.</em></p>"
    elif r.text is None:
        body = f"<p><em>{'Declined to answer' if r.status == 'abstained' else esc(r.status)}.</em></p>"
    else:
        body = f'<p class="answer">{esc(r.text)}</p>'
    bits = [f"<strong>{esc(r.id)}</strong> {esc(r.question)}"]
    meta = ["answerable" if r.answerable else "unanswerable", esc(r.status)]
    if r.label is not None:
        meta.append("hand-graded: " + ("correct" if r.label else "wrong"))
    if r.judge is not None:
        meta.append(f"AI judge ({JUDGE_WARNING}): " + ("correct" if r.judge else "wrong"))
    srcs = ", ".join(_link(t, u) for t, u in r.sources)
    note = f'<p class="note">Known problem: {esc(r.note)}</p>' if r.note else ""
    return (f"<details><summary>{bits[0]} <small>({'; '.join(meta)})</small></summary>{body}"
            f"{'<p>Sources: ' + srcs + '</p>' if srcs else ''}{note}</details>")


def render_evals_html(report: Report, cfg: Config) -> str:
    esc = html.escape
    title = f"How good are the answers? {cfg.site.title}"
    out = [
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; "
        "style-src 'self'; base-uri 'none'; form-action 'none'\">",
        '<meta name="referrer" content="no-referrer">',
        f'<title>{esc(title)}</title><link rel="stylesheet" href="src/style.css"></head>',
        f"<body><main><h1>{esc(title)}</h1>",
    ]
    if not report.history:
        out.append("<p>No runs yet.</p>")
    out.append("<section><h2>Headline</h2><ul>"
               + "".join(_stat_li(s) for s in report.headline) + "</ul></section>")
    out.append("<section><h2>How much to trust these numbers</h2><ul>"
               + "".join(f"<li>{esc(t)}</li>" for t in report.honesty) + "</ul></section>")
    out.append("<section><h2>Known wrong answers</h2>")
    if report.known_wrong:
        out.append("<ul>" + "".join(f"<li><strong>{esc(i)}</strong>: {esc(t)}</li>"
                                    for i, t in report.known_wrong) + "</ul>")
    else:
        out.append("<p>None recorded.</p>")
    out.append("</section><section><h2>Run history</h2>")
    for g in (DEV, SYNTHETIC):
        hs = [h for h in report.history if h.group == g]
        if hs:
            out.append(f"<h3>{esc(g)}</h3><p>{esc(GROUP_NOTE[g])}</p>")
            if g == SYNTHETIC and report.generated:
                out.append("<ul>" + "".join(_stat_li(s) for s in report.generated) + "</ul>")
            out.append("<ul>")
            for h in hs:
                out.append(f"<li>{esc(h.name)}: {fraction_text(h.refused.k, h.refused.n)} refused; "
                           f"{fraction_text(h.valid_citation.k, h.valid_citation.n)} cited; "
                           f"{_plural(h.errors, 'error')}</li>")
            out.append("</ul>")
    out.append("</section><section><h2>Every answer</h2>")
    for g in (DEV, SYNTHETIC):
        rs = [r for r in report.rows if r.group == g]
        if rs:
            out.append(f"<h3>{esc(g)}</h3><p>{esc(GROUP_NOTE[g])}</p>")
            out.extend(_row_html(r) for r in rs)
    out.append("</section></main></body></html>")
    return "\n".join(out)
