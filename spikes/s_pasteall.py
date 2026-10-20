"""Task 15 Step 9: paste-all baseline. Sends ALL docs pieces (about 35k tokens) with each question
to ONE Cloudflare model (no fallback chain). Costs about 320 neurons per question: run on at most
5 questions, once. Usage: python spikes/s_pasteall.py ID [ID ...]"""
import json
import os
import sys
from pathlib import Path

from app.answer import answer_paste_all
from app.config import load_config
from app.llm.base import Adapter
from app.llm.build import build_adapter
from app.store import Store
from evals.schema import load_questions

ids = sys.argv[1:]
assert 0 < len(ids) <= 5, "paste-all runs on at most 5 questions"
cfg = load_config("config/visidata.yaml")
store = Store(os.environ["DATABASE_URL"], cfg.models.embedding_dim)
pieces = store.load_pieces(cfg.project.slug)
# one provider only: the first Cloudflare model of the user chain
first = cfg.model_copy(update={"models": cfg.models.model_copy(
    update={"answer_order": [cfg.models.answer_order[0]]})})
adapter: Adapter = build_adapter(first, os.environ)
assert len(adapter.providers) == 1
qs = {q.id: q for q in load_questions(Path("evals/data/dev.jsonl"))}
out = []
for i in ids:
    before = adapter.total_neurons
    a = answer_paste_all(qs[i].question, pieces, adapter, first, cfg.project.name)
    row = {"id": i, "answerable": qs[i].answerable, "status": a.status, "text": a.text,
           "citations": [str(c) for c in a.citations], "invalid_citations": a.invalid_citations,
           "neurons": adapter.total_neurons - before, "seconds": a.seconds,
           "model": cfg.models.answer_order[0], "pieces_sent": len(pieces)}
    print(i, a.status, round(row["neurons"], 1), "neurons", round(a.seconds, 1), "s", flush=True)
    out.append(row)
    assert row["neurons"] < 500, "far above the 320 estimate: stop and check the dashboard"
Path("docs/evals/baseline-pasteall.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print("total neurons", round(adapter.total_neurons, 1))
