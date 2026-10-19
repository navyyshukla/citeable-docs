"""Commands: ingest docs into the database; run evals."""
import argparse
import os
import sys
from collections import Counter
from pathlib import Path

import httpx

from app.config import load_config
from app.llm.build import build_adapter
from app.llm.cloudflare import CloudflareClient, embed_texts
from app.search import Searcher
from app.store import Store
from evals.runner import (run_answers, run_retrieval, summarize_answers, summarize_retrieval,
                          write_results)
from evals.schema import load_questions
from ingest.fetch import fetch_docs
from ingest.pipeline import build_pieces

MIN_PIECES = 100  # the real docs give about 230; fewer means a broken download or parse


def _store(cfg) -> Store:
    return Store(os.environ["DATABASE_URL"], cfg.models.embedding_dim,
                 vector_index=cfg.search.vector_index)


def cmd_ingest(args) -> int:
    cfg = load_config(args.config)
    files = fetch_docs(cfg.project.upstream_repo, cfg.project.ref, cfg.project.docs_path)
    pieces = build_pieces(files, cfg.project)
    per_page = Counter(p.page_slug for p in pieces)
    print(f"ref={cfg.project.ref}: {len(per_page)} pages, {len(pieces)} pieces")
    for slug, n in sorted(per_page.items()):
        print(f"  {slug}: {n}")
    if args.dry_run:
        return 0
    store = _store(cfg)
    store.init_schema()
    # An empty or tiny parse must never delete the stored pieces (cold review of Tasks 6-9).
    floor = max(MIN_PIECES, len(store.load_pieces(cfg.project.slug)) // 2)
    if len(pieces) < floor:
        print(f"refusing to replace: built {len(pieces)} pieces, expected at least {floor}",
              file=sys.stderr)
        return 1
    cf = CloudflareClient(os.environ["CF_ACCOUNT_ID"], os.environ["CF_API_TOKEN"],
                          httpx.Client(timeout=60))
    vectors = embed_texts(cf, cfg.models.embedding, [p.search_text for p in pieces],
                          cfg.models.embedding_batch)
    store.replace_project_pieces(cfg.project.slug, pieces, vectors)
    print(f"stored {len(pieces)} pieces for project {cfg.project.slug}")
    return 0


def cmd_eval(args) -> int:
    cfg = load_config(args.config)
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
    retrieval, answers, stopped = {}, {}, {}
    adapter = build_adapter(cfg, os.environ) if args.answer else None
    for mode in modes:
        retrieval[mode] = run_retrieval(questions, searcher, by_id, mode, cfg.search.top_k)
        print(mode, "retrieval:", summarize_retrieval(retrieval[mode]))
        if adapter:
            rows, early = run_answers(questions, searcher, by_id, adapter, cfg, cfg.project.name,
                                      mode, cfg.search.top_k, args.max_neurons)
            answers[mode], stopped[mode] = rows, early
            print(mode, "answers:", summarize_answers(rows), "stopped_early:", early)
    meta = {"split": args.split, "n_questions": len(questions), "ref": cfg.project.ref,
            "modes": modes, "answered": bool(adapter), "stopped_early": stopped,
            "total_neurons": adapter.total_neurons if adapter else 0.0,
            "embedding_model": cfg.models.embedding}
    write_results(Path(args.out), meta, retrieval, answers)
    print("wrote", args.out)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="app.cli")
    p.add_argument("--config", default="config/visidata.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("ingest")
    i.add_argument("--dry-run", action="store_true")
    i.add_argument("--config", default=argparse.SUPPRESS)
    e = sub.add_parser("eval")
    e.add_argument("--split", default="dev")
    e.add_argument("--modes", default="keyword,meaning,hybrid")
    e.add_argument("--data", default="evals/data/dev.jsonl")
    e.add_argument("--answer", action="store_true")
    e.add_argument("--max-neurons", type=float, default=1500.0)
    e.add_argument("--out", required=True)
    e.add_argument("--config", default=argparse.SUPPRESS)
    args = p.parse_args(argv)
    return cmd_ingest(args) if args.cmd == "ingest" else cmd_eval(args)


if __name__ == "__main__":
    sys.exit(main())
