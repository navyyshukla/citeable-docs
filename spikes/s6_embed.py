"""Spike S6: does meaning search (bge-base) find the right page for messy questions? Public docs only."""
import os

import httpx
import numpy as np

from s2_symbols import QUERIES, SYM, bm25, key_path, load_sections

ACCT = os.environ["CF_ACCOUNT_ID"]; TOKEN = os.environ["CF_API_TOKEN"]
URL = f"https://api.cloudflare.com/client/v4/accounts/{ACCT}/ai/run/@cf/baai/bge-base-en-v1.5"
H = {"Authorization": f"Bearer {TOKEN}"}
BUDGET = 1000
MESSY = [
 ("So I've got two CSV files, one is customers and one is orders, and my boss wants me to figure out which customers never ordered anything, I tried opening both and I think there's something about keys but I honestly don't remember, so basically how would I do this properly in VisiData and what are the steps?", {"join"}),
 ("how 2 hide colum pls, it showing too many and i cant see", {"columns"}),
 ("i opened big file n its slow how do i get only some rows random like sample", {"rows"}),
 ("my sheet has key thing with ! what is that n how i undo it", {"columns"}),
]
spent = 0.0


def embed(texts):
    global spent
    out = []
    for i in range(0, len(texts), 50):
        r = httpx.post(URL, headers=H, json={"text": texts[i:i + 50]}, timeout=180)
        assert r.status_code == 200, (r.status_code, r.text[:200])
        res = r.json()["result"]; spent += (res.get("usage") or {}).get("neurons") or 0
        out += res["data"]
        print(f"embedded {len(out)}/{len(texts)} neurons_so_far={spent:.1f}", flush=True)
        assert spent < BUDGET, "budget"
    return np.array(out)


docs = load_sections(); ids = list(docs)
bm = bm25(docs, SYM)
M = embed([docs[i][:1500] for i in ids])
M /= np.linalg.norm(M, axis=1, keepdims=True)


def meaning(q, k=5):
    v = embed([q])[0]; v /= np.linalg.norm(v)
    return [ids[j] for j in np.argsort(-(M @ v))[:k]]


def rrf(*lists, k=5):
    sc = {}
    for L in lists:
        for r, i in enumerate(L):
            sc[i] = sc.get(i, 0) + 1 / (60 + r)
    return sorted(sc, key=sc.get, reverse=True)[:k]


tot = {"keyword": 0, "meaning": 0, "hybrid": 0}
allq = [(q, w, "S2") for q, w in QUERIES] + [(q, w, "messy") for q, w in MESSY]
for q, want, tag in allq:
    kw = list(dict.fromkeys(key_path(docs, q)[:2] + bm(q, 5)))[:5]
    me = meaning(q)
    hy = rrf(kw, me)
    hit = lambda L: any(i.split(":")[0] in want for i in L)  # noqa: E731
    for n, L in (("keyword", kw), ("meaning", me), ("hybrid", hy)):
        tot[n] += hit(L)
    print(f"[{tag}] {q[:60]!r}\n   keyword={hit(kw)} {kw}\n   meaning={hit(me)} {me}\n   hybrid ={hit(hy)} {hy}")
print(f"\nhit@5 of {len(allq)}: {tot}   neurons_spent={spent:.1f}")
