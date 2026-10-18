"""Spike S5: does Cloudflare gemma-4 answer from retrieved docs, cite, and refuse? Public docs only.
Hard neuron budget; stops on any non-200."""
import os
import sys
import time

import httpx

from s2_symbols import QUERIES, SYM, bm25, key_path, load_sections

ACCT = os.environ["CF_ACCOUNT_ID"]
TOKEN = os.environ["CF_API_TOKEN"]
MODEL = "@cf/google/gemma-4-26b-a4b-it"
URL = f"https://api.cloudflare.com/client/v4/accounts/{ACCT}/ai/run/{MODEL}"
BUDGET = 1500
MAX_TOKENS = 1500
UNANSWERABLE = [
    "Does VisiData have a built-in real-time multi-user collaboration server?",
    "What is the price of a VisiData Enterprise licence?",
]
SYSTEM = (
    "You answer questions about VisiData using ONLY the numbered doc sections given. "
    "Cite the section id in square brackets after each claim, like [columns:3]. "
    "If the sections do not contain the answer, reply with exactly: NOT_IN_DOCS"
)

docs = load_sections()
search = bm25(docs, SYM)
spent = 0.0
rows = []
for q, want in [(q, w) for q, w in QUERIES] + [(q, None) for q in UNANSWERABLE]:
    ids = list(dict.fromkeys(key_path(docs, q)[:2] + search(q, 5)))[:3]
    ctx = "\n\n".join(f"[{i}]\n{docs[i][:2500]}" for i in ids)
    body = {"messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": f"Sections:\n{ctx}\n\nQuestion: {q}"}],
            "max_tokens": MAX_TOKENS}
    t0 = time.time()
    r = httpx.post(URL, headers={"Authorization": f"Bearer {TOKEN}"}, json=body, timeout=180)
    if r.status_code != 200:
        print("STOP non-200:", r.status_code, r.text[:300]); break
    res = r.json()["result"]
    ch = (res.get("choices") or [{}])[0]
    text = (res.get("response") or (ch.get("message") or {}).get("content") or "").strip()
    n = res.get("usage", {}).get("neurons") or 0
    spent += n
    if want is None:
        ok = "NOT_IN_DOCS" in text
    else:
        ok = bool(text) and any(f"[{i}]" in text for i in ids if i.split(":")[0] in want)
    rows.append((q, ok))
    print(f"\n### {q}\nretrieved={ids} ok={ok} empty={not text} finish={ch.get('finish_reason')} "
          f"neurons={n} tokens={res.get('usage')} {time.time()-t0:.0f}s\n{text[:700]}")
    if spent > BUDGET:
        print("STOP budget"); break
print(f"\nPASS {sum(o for _, o in rows)}/{len(rows)}  neurons_spent={spent:.0f}")
