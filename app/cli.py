"""Commands: ingest docs into the database; run evals."""
import argparse
import json
from dataclasses import asdict
import os
import sys
from collections import Counter
from pathlib import Path

import httpx

from app.config import load_config, with_provider
from app.db import Db
from app.llm.build import build_adapter
from app.llm.base import ProviderError
from app.llm.cloudflare import CloudflareClient, embed_texts
from app.llm.gemini import GeminiProvider
from app.search import Searcher
from app.store import Store
from app.usage import Usage
from evals.runner import (RetrievalRow, run_answers, run_retrieval, summarize_answers, summarize_retrieval,
                          write_results)
from evals.judge import (JudgeVerdict, agreement, items_from_results, judge_answer,
                         load_labels)
from evals.generate import (build_unanswerable_prompt, generate, parse_unanswerable,
                            write_check_sheet)
from evals.schema import load_questions
from evals.threshold import threshold_table
from ingest.fetch import fetch_docs_and_commit
from ingest.pipeline import build_pieces

MIN_PIECE_CHARS_FOR_QUESTIONS = 300  # shorter pieces rarely hold a question's answer
MIN_PIECES = 100  # the real docs give about 230; fewer means a broken download or parse


def _store(cfg) -> Store:
    return Store(Db(os.environ["DATABASE_URL"]), cfg.models.embedding_dim,
                 vector_index=cfg.search.vector_index)


def cmd_ingest(args) -> int:
    cfg = load_config(args.config)
    files, commit = fetch_docs_and_commit(cfg.project.upstream_repo, cfg.project.ref,
                                          cfg.project.docs_path)
    # `ref` is a moving branch: store the commit too, so a baseline can be reproduced.
    docs_ref = f"{cfg.project.ref}@{commit[:10]}" if commit else cfg.project.ref
    pieces = build_pieces(files, cfg.project, docs_ref=docs_ref)
    per_page = Counter(p.page_slug for p in pieces)
    print(f"ref={docs_ref}: {len(per_page)} pages, {len(pieces)} pieces")
    for slug, n in sorted(per_page.items()):
        print(f"  {slug}: {n}")
    if args.dry_run:
        return 0
    store = _store(cfg)
    store.init_schema()
    if not args.allow_model_change:
        try:
            store.check_ingest_meta(cfg.project.slug, cfg.models.embedding)
        except ValueError as e:
            print(f"refusing to replace: {e}", file=sys.stderr)
            return 1
    # An empty or tiny parse must never delete the stored pieces (cold review of Tasks 6-9),
    # and neither may a parse that lost whole pages (cold review #2).
    stored = store.load_pieces(cfg.project.slug)
    floor = max(MIN_PIECES, len(stored) // 2)
    if len(pieces) < floor:
        print(f"refusing to replace: built {len(pieces)} pieces, expected at least {floor}",
              file=sys.stderr)
        return 1
    gone = sorted({p.page_slug for p in stored} - set(per_page))
    if gone and not args.allow_shrink:
        print(f"refusing to replace: pages {gone} are stored but missing from this parse "
              "(use --allow-shrink if the docs really dropped them)", file=sys.stderr)
        return 1
    cf = CloudflareClient(os.environ["CF_ACCOUNT_ID"], os.environ["CF_API_TOKEN"],
                          httpx.Client(timeout=60))
    vectors = embed_texts(cf, cfg.models.embedding, [p.search_text for p in pieces],
                          cfg.models.embedding_batch)
    store.replace_project_pieces(cfg.project.slug, pieces, vectors)
    store.write_ingest_meta(cfg.project.slug, cfg.models.embedding, cfg.models.embedding_dim,
                            docs_ref)
    print(f"stored {len(pieces)} pieces for project {cfg.project.slug}")
    return 0


def cmd_eval(args) -> int:
    cfg = load_config(args.config)
    if args.provider:  # measure one model on its own (a fallback, for example)
        try:
            cfg = with_provider(cfg, args.provider)
        except ValueError as e:
            print(f"{e}", file=sys.stderr)
            return 1
    store = _store(cfg)
    pieces = store.load_pieces(cfg.project.slug)
    if not pieces:
        print("no pieces in the database; run `ingest` first", file=sys.stderr)
        return 1
    by_id = {p.id: p for p in pieces}
    questions = [q for q in load_questions(Path(args.data)) if q.split == args.split]
    cf = CloudflareClient(os.environ["CF_ACCOUNT_ID"], os.environ["CF_API_TOKEN"],
                          httpx.Client(timeout=60))
    searcher = Searcher(
        pieces,
        embed_query=lambda t: embed_texts(cf, cfg.models.embedding, [t], 1)[0],
        vector_search=lambda v, k: store.vector_search(cfg.project.slug, v, k),
        rrf_k=cfg.search.rrf_k,
    )
    modes = args.modes.split(",")
    retrieval: dict = {}
    answers: dict = {}
    stopped: dict = {}
    adapter = build_adapter(cfg, os.environ) if args.answer else None
    meta = {"split": args.split, "n_questions": len(questions), "ref": cfg.project.ref,
            "modes": modes, "answered": bool(adapter), "stopped_early": stopped,
            "total_neurons": 0.0, "embedding_model": cfg.models.embedding}
    # Results are written even if a later mode crashes: the neurons already spent are not lost.
    try:
        for mode in modes:
            retrieval[mode] = run_retrieval(questions, searcher, by_id, mode, cfg.search.top_k)
            print(mode, "retrieval:", summarize_retrieval(retrieval[mode]))
            if adapter:
                rows, early = run_answers(questions, searcher, by_id, adapter, cfg,
                                          cfg.project.name, mode, cfg.search.top_k,
                                          args.max_neurons, args.pause)
                answers[mode], stopped[mode] = rows, early
                print(mode, "answers:", summarize_answers(rows), "stopped_early:", early)
    except Exception as e:
        meta["crashed"] = str(e)
        raise
    finally:
        meta["total_neurons"] = adapter.total_neurons if adapter else 0.0
        write_results(Path(args.out), meta, retrieval, answers)
        print("wrote", args.out)
    return 0


def _db() -> Db:
    return Db(os.environ["DATABASE_URL"])


def cmd_init_db(args) -> int:
    cfg = load_config(args.config)
    db = Db(os.environ["DATABASE_URL"])
    Store(db, cfg.models.embedding_dim, vector_index=cfg.search.vector_index).init_schema()
    Usage(db).init_schema()
    print("tables ready: pieces, ingest_meta, invite_tokens, questions, feedback")
    return 0


def cmd_token(args) -> int:
    usage = Usage(_db())
    if args.action == "create":
        try:
            token = usage.create_token(args.label)
        except ValueError as e:
            print(e, file=sys.stderr)
            return 1
        print(f"token for {args.label}: {token}")
        print("Copy it now: it is stored only as a hash and will not be shown again.")
        # The token goes after '#': browsers never send the fragment to any server.
        site = load_config(args.config).site
        print(f"invite link: {site.url.rstrip('/')}/#t={token}")
        return 0
    if args.action == "revoke":
        if not usage.revoke_token(args.label):
            print(f"no active token labelled {args.label!r}", file=sys.stderr)
            return 1
        print(f"revoked {args.label}")
        return 0
    print(f"{'label':<20} {'created':<12} {'state':<8} questions today")
    for t in usage.list_tokens():
        state = "revoked" if t.revoked else "active"
        print(f"{t.label:<20} {t.created_at:%Y-%m-%d}   {state:<8} {t.questions_today}")
    return 0


def cmd_purge(args) -> int:
    cfg = load_config(args.config)
    days = args.days if args.days is not None else cfg.limits.retention_days
    n = Usage(_db()).purge(days)
    print(f"deleted {n} questions older than {days} days (feedback goes with them)")
    return 0


def cmd_serve(args) -> int:
    import uvicorn  # imported here: only the server needs it

    # access_log off: the access log would record client IPs, and we promise not to keep them.
    uvicorn.run("app.api:build_from_env", factory=True, host=args.host, port=args.port,
                access_log=False)
    return 0


def cmd_judge(args) -> int:
    """Score saved eval answers with Gemini. Reads the public docs pieces (read-only) and the
    curated question file; it never opens the user question log."""
    cfg = load_config(args.config)
    results = json.loads(Path(args.results).read_text(encoding="utf-8"))
    if args.mode not in results.get("answers", {}):
        print(f"mode {args.mode!r} has no answers in {args.results}", file=sys.stderr)
        return 1
    piece_text = {p.id: p.text for p in _store(cfg).load_pieces(cfg.project.slug)}
    try:
        items, skipped = items_from_results(results, load_questions(Path(args.data)), args.mode,
                                            piece_text)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    provider = GeminiProvider(os.environ["GEMINI_API_KEY"], json_output=True)
    verdicts = [judge_answer(i, provider) for i in items]
    Path(args.out).write_text(json.dumps([asdict(v) for v in verdicts], indent=2),
                              encoding="utf-8")
    errors = sum(1 for v in verdicts if v.error)
    print(f"judged {len(verdicts)} answers ({errors} judge errors, {skipped} rows skipped: "
          "not answered or no saved text). UNCALIBRATED until judge-agreement has been run "
          "against hand-graded labels.")
    return 0


def cmd_judge_agreement(args) -> int:
    verdicts = [JudgeVerdict(**v)
                for v in json.loads(Path(args.verdicts).read_text(encoding="utf-8"))]
    a = agreement(verdicts, load_labels(Path(args.labels)))

    def fmt(x):
        return "n/a" if x is None else f"{x:.2f}"
    print(f"compared {a['compared']} labelled answers "
          f"({a['skipped_errors']} judge errors, {a['missing_verdicts']} without a verdict)")
    print(f"precision {fmt(a['precision'])}  recall {fmt(a['recall'])}  "
          f"(TP {a['true_positive']} FP {a['false_positive']} FN {a['false_negative']} "
          f"TN {a['true_negative']})")
    return 0


def cmd_generate_questions(args) -> int:
    """Write synthetic eval questions with Gemini from the PUBLIC docs pieces (read-only).
    Makes up to --limit + 1 Gemini calls, so run it only when you mean to spend them."""
    cfg = load_config(args.config)
    out = Path(args.out)
    if out.exists():
        print(f"{out} already exists: move it or choose another --out", file=sys.stderr)
        return 1
    pieces = sorted((p for p in _store(cfg).load_pieces(cfg.project.slug)
                     if len(p.text) >= MIN_PIECE_CHARS_FOR_QUESTIONS), key=lambda p: p.id)
    if not pieces:
        print("no pieces long enough to write questions from; run ingest first", file=sys.stderr)
        return 1
    step = max(1, len(pieces) // max(1, args.limit))  # spread over the whole docs
    chosen = pieces[::step][:args.limit]
    existing = {q.question.lower() for q in load_questions(Path(args.data))}
    provider = GeminiProvider(os.environ["GEMINI_API_KEY"], json_output=True)
    questions = generate(chosen, provider, limit=args.limit, existing=existing)
    if args.unanswerable:
        titles = sorted({p.page_title for p in pieces})
        system, user = build_unanswerable_prompt(titles, args.unanswerable)
        try:
            c = provider.complete(system, user, 600)
            questions += parse_unanswerable(c.text, len(questions) + 1, existing | {
                q.question.lower() for q in questions})
        except ProviderError as e:
            print(f"unanswerable questions skipped: {e}", file=sys.stderr)
    out.write_text("".join(q.model_dump_json() + "\n" for q in questions), encoding="utf-8")
    rows = write_check_sheet(questions, Path(args.sheet)) if args.sheet else 0
    print(f"wrote {len(questions)} questions to {out}; {rows} rows in the hand-check sheet. "
          "Read the sheet before using these questions.")
    return 0


def cmd_calibrate(args) -> int:
    """Print what each evidence threshold would do. Reads a saved file: no network, no neurons."""
    data = json.loads(Path(args.retrieval).read_text(encoding="utf-8"))
    if args.mode not in data["retrieval"]:
        print(f"mode {args.mode!r} not in {args.retrieval} (has {sorted(data['retrieval'])})",
              file=sys.stderr)
        return 1
    rows = [RetrievalRow(**r) for r in data["retrieval"][args.mode]]
    # Candidate thresholds: each distinct best score seen, plus 0 (answer everything).
    best = sorted({max(r.top_scores) for r in rows if r.top_scores})
    table = threshold_table(rows, [0.0] + best)
    print(f"{'threshold':>10} {'answered%':>10} {'wrong%':>8} {'abstain_ok%':>12}")
    for t in table:
        def fmt(x):
            return "-" if x is None else f"{x:.0f}"
        print(f"{t.threshold:>10.4f} {t.answered_pct:>10.0f} {fmt(t.wrong_when_answered_pct):>8} "
              f"{fmt(t.correctly_abstained_pct):>12}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="app.cli")
    p.add_argument("--config", default="config/visidata.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("ingest")
    i.add_argument("--dry-run", action="store_true")
    i.add_argument("--allow-shrink", action="store_true")
    i.add_argument("--allow-model-change", action="store_true")
    i.add_argument("--config", default=argparse.SUPPRESS)
    e = sub.add_parser("eval")
    e.add_argument("--split", default="dev")
    e.add_argument("--modes", default="keyword,meaning,hybrid")
    e.add_argument("--data", default="evals/data/dev.jsonl")
    e.add_argument("--answer", action="store_true")
    e.add_argument("--max-neurons", type=float, default=1500.0)
    e.add_argument("--pause", type=float, default=0.0,
                   help="seconds between questions (Groq needs about 14)")
    e.add_argument("--provider", help="force one entry of models.answer_order, "
                                       "e.g. groq:openai/gpt-oss-20b")
    e.add_argument("--out", required=True)
    e.add_argument("--config", default=argparse.SUPPRESS)
    c = sub.add_parser("calibrate")
    c.add_argument("--retrieval", required=True)
    c.add_argument("--mode", default="hybrid")
    c.add_argument("--config", default=argparse.SUPPRESS)
    sub.add_parser("init-db").add_argument("--config", default=argparse.SUPPRESS)
    t = sub.add_parser("token")
    t.add_argument("action", choices=["create", "revoke", "list"])
    t.add_argument("label", nargs="?")
    t.add_argument("--config", default=argparse.SUPPRESS)
    u = sub.add_parser("purge")
    u.add_argument("--days", type=int, default=None)
    u.add_argument("--config", default=argparse.SUPPRESS)
    v = sub.add_parser("serve")
    v.add_argument("--host", default="127.0.0.1")
    v.add_argument("--port", type=int, default=8000)
    v.add_argument("--config", default=argparse.SUPPRESS)
    j = sub.add_parser("judge")
    j.add_argument("--results", required=True)
    j.add_argument("--data", default="evals/data/dev.jsonl")
    j.add_argument("--mode", default="hybrid")
    j.add_argument("--out", required=True)
    j.add_argument("--config", default=argparse.SUPPRESS)
    q = sub.add_parser("generate-questions")
    q.add_argument("--out", required=True)
    q.add_argument("--limit", type=int, default=25)
    q.add_argument("--unanswerable", type=int, default=5)
    q.add_argument("--sheet")
    q.add_argument("--data", default="evals/data/dev.jsonl")
    q.add_argument("--config", default=argparse.SUPPRESS)
    g = sub.add_parser("judge-agreement")
    g.add_argument("--verdicts", required=True)
    g.add_argument("--labels", required=True)
    args = p.parse_args(argv)
    if args.cmd == "token" and args.action != "list" and not args.label:
        p.error(f"token {args.action} needs a LABEL")
    return {"ingest": cmd_ingest, "eval": cmd_eval, "calibrate": cmd_calibrate,
            "init-db": cmd_init_db, "token": cmd_token, "purge": cmd_purge,
            "serve": cmd_serve, "judge": cmd_judge, "generate-questions": cmd_generate_questions,
            "judge-agreement": cmd_judge_agreement}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
