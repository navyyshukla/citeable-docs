"""Spike S8: does bge-base silently truncate long input? Embed S[:n] and S[:n+500] for growing n;
once both are past the model's limit the vectors become identical (cosine 1.0). Public docs only."""
import os
from pathlib import Path

import httpx
import numpy as np

from app.config import load_config
from ingest.fetch import _docs_from_tarball
from ingest.pipeline import build_pieces

ACCT, TOKEN = os.environ["CF_ACCOUNT_ID"], os.environ["CF_API_TOKEN"]
URL = f"https://api.cloudflare.com/client/v4/accounts/{ACCT}/ai/run/@cf/baai/bge-base-en-v1.5"
cfg = load_config(Path(__file__).resolve().parents[1] / "config" / "visidata.yaml").project
files = _docs_from_tarball((Path(__file__).parent / ".cache" / "stable.tar.gz").read_bytes(), "docs")
S = "\n\n".join(p.text for p in build_pieces(files, cfg)[:30])[:6000]


def emb(texts):
    r = httpx.post(URL, headers={"Authorization": f"Bearer {TOKEN}"}, json={"text": texts}, timeout=120)
    assert r.status_code == 200, r.text[:200]
    v = np.array(r.json()["result"]["data"])
    return v / np.linalg.norm(v, axis=1, keepdims=True)


print("chars  cos(S[:n], S[:n+500])   (1.0000 = the extra 500 chars were ignored)")
for n in (500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 5000):
    a, b = emb([S[:n], S[: n + 500]])
    print(f"{n:5d}  {float(a @ b):.5f}")
