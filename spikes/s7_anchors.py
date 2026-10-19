"""Spike S7: do our citation anchors exist on the published pages? Reads public pages only."""
import re
import time
from pathlib import Path

import httpx

from app.config import load_config
from ingest.fetch import _docs_from_tarball
from ingest.pipeline import build_pieces

cfg = load_config(Path(__file__).resolve().parents[1] / "config" / "visidata.yaml")
files = _docs_from_tarball((Path(__file__).parent / ".cache" / "stable.tar.gz").read_bytes(), "docs")
pieces = build_pieces(files, cfg.project)
by_page: dict[str, list] = {}
for p in pieces:
    if p.anchor:
        by_page.setdefault(p.page_slug, []).append(p)

ok = bad = 0
ex_ok = ex_bad = 0
ex_miss = []
misses: list[tuple[str, str, tuple]] = []
with httpx.Client(timeout=30, follow_redirects=True) as client:
    for slug, ps in sorted(by_page.items()):
        r = client.get(ps[0].url)
        ids = set(re.findall(r'\bid="([^"]+)"', r.text)) if r.status_code == 200 else set()
        if r.status_code != 200:
            print(f"{slug}: HTTP {r.status_code}")
        for p in ps:
            if p.anchor_explicit:
                if p.anchor in ids:
                    ex_ok += 1
                else:
                    ex_bad += 1
                    ex_miss.append((slug, p.anchor))
            if p.anchor in ids:
                ok += 1
            else:
                bad += 1
                misses.append((slug, p.anchor, p.heading_path[-1]))
        time.sleep(0.5)
print(f"anchors found {ok}, missing {bad} of {ok + bad} (pieces with an anchor, {len(by_page)} pages)")
for m in misses[:40]:
    print("  MISS", m)
print(f"explicit {{#id}} anchors: found {ex_ok}, missing {ex_bad}", ex_miss)
