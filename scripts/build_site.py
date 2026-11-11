"""Build the static site from config/visidata.yaml: python scripts/build_site.py page --out _site

The page text never depends on the API being awake: it is rendered into the HTML here.
"""
import argparse
import html
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import Config, load_config  # noqa: E402

SITE = ROOT / "site"
STARTERS_SHOWN = 3  # the welcome screen has room for three; the rest stay in config


def _csp(api_base_url: str) -> str:
    return ("default-src 'none'; script-src 'self'; style-src 'self'; "
            f"connect-src {api_base_url}; img-src 'self'; base-uri 'none'; form-action 'none'")


def _json_for_script(data: dict) -> str:
    # '<' as < so no text can ever close the <script> block or start a new one.
    return json.dumps(data).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def build_page(cfg: Config, out_dir: Path) -> Path:
    """Write index.html and copy site/src/*; returns the index path."""
    esc = html.escape
    starters = "\n".join(
        f'      <button type="button" class="starter" data-question="{esc(q)}">{esc(q)}</button>'
        for q in cfg.site.starter_questions[:STARTERS_SHOWN])
    link = '<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>'
    links = link.format(esc(cfg.site.about_url), "What is VisiData? ↗")
    if cfg.site.intro_video_url:
        links += link.format(esc(cfg.site.intro_video_url), "▶ Intro video")
    values = {
        "title": esc(cfg.site.title),
        "brand": esc(cfg.site.brand),
        "greeting": esc(cfg.site.greeting),
        "tagline": esc(" ".join(cfg.site.tagline.split())),
        "links": links,
        "starters": starters,
        "privacy_notice": esc(cfg.site.privacy_notice.strip()),
        "license_note": esc(cfg.project.license_note),
        # esc() on the CSP too: it is placed inside an attribute value
        "csp": esc(_csp(cfg.site.api_base_url)),
        "config_json": _json_for_script({
            "api_base_url": cfg.site.api_base_url,
            "max_question_chars": cfg.limits.max_question_chars,
        }),
    }
    page = (SITE / "template.html").read_text(encoding="utf-8")
    for key, value in values.items():
        page = page.replace("{{" + key + "}}", value)
    out_dir = Path(out_dir)
    (out_dir / "src").mkdir(parents=True, exist_ok=True)
    for f in (SITE / "src").iterdir():
        if f.is_file():
            shutil.copy2(f, out_dir / "src" / f.name)
    index = out_dir / "index.html"
    index.write_text(page, encoding="utf-8")
    return index


def build_evals(cfg: Config, run_paths, labels_path, verdicts_path, trap, question_paths,
                pieces, out: Path) -> Path:
    """Write the public /evals page from saved files. `trap` is a (traps, verdicts) pair or None."""
    from evals.judge_traps import _load_traps, load_verdicts, score
    from evals.report import build_report, render_evals_html
    from evals.schema import load_questions

    runs = [json.loads(Path(p).read_text(encoding="utf-8")) for p in run_paths]
    labels = {d["question_id"]: bool(d["correct"]) for d in map(
        json.loads, Path(labels_path).read_text(encoding="utf-8").splitlines()) if d}
    verdicts = load_verdicts(Path(verdicts_path))
    questions, seen = [], set()
    for path in question_paths:  # first file wins when an id repeats (raw vs checked sets)
        for q in load_questions(Path(path)):
            if q.id not in seen:
                seen.add(q.id)
                questions.append(q)
    trap_score = score(_load_traps(str(trap[0])), load_verdicts(Path(trap[1]))) if trap else None
    report = build_report(runs, labels, verdicts, trap_score, questions, pieces,
                          cfg.site.known_wrong)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_evals_html(report, cfg), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="build_site")
    p.add_argument("--config", default=str(ROOT / "config" / "visidata.yaml"))
    sub = p.add_subparsers(dest="cmd", required=True)
    page = sub.add_parser("page")
    page.add_argument("--out", required=True)
    ev = sub.add_parser("evals")
    ev.add_argument("--run", action="append", required=True, help="saved results file; repeat")
    ev.add_argument("--labels", required=True)
    ev.add_argument("--verdicts", required=True)
    ev.add_argument("--trap", help="traps file from `evals.judge_traps build`")
    ev.add_argument("--trap-verdicts", help="judge verdicts for the traps file")
    ev.add_argument("--questions", action="append",
                    default=None, help="question files (default: dev.jsonl and synthetic.jsonl)")
    ev.add_argument("--out", required=True)
    args = p.parse_args(argv)
    cfg = load_config(args.config)
    if args.cmd == "page":
        print(build_page(cfg, Path(args.out)))
    elif args.cmd == "evals":
        if bool(args.trap) != bool(args.trap_verdicts):
            p.error("--trap and --trap-verdicts go together")
        from app.cli import _store  # needs DATABASE_URL; read-only
        pieces = {x.id: x for x in _store(cfg).load_pieces(cfg.project.slug)}
        qfiles = args.questions or [str(ROOT / "evals/data/dev.jsonl")] + [
            str(f) for f in [ROOT / "evals/data/synthetic.jsonl"] if f.exists()]
        trap = (args.trap, args.trap_verdicts) if args.trap else None
        print(build_evals(cfg, args.run, args.labels, args.verdicts, trap, qfiles, pieces,
                          Path(args.out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
