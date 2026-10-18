"""Spike S3: find closed issues that look like questions and have a maintainer reply.
Needs GITHUB_TOKEN (public read access is enough) to avoid the 60/hour limit."""
import json
import os
import re
from pathlib import Path

import httpx

REPO = "saulpw/visidata"
OUT = Path(__file__).parent / ".cache" / "s3_candidates.jsonl"
OUT.parent.mkdir(exist_ok=True)
H = {"Accept": "application/vnd.github+json"}
if os.getenv("GITHUB_TOKEN"):
    H["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
QUESTIONY = re.compile(r"\b(how (do|can|to)|is it possible|can i|is there a way|what does)\b", re.I)
MAINTAINER = {"OWNER", "MEMBER", "COLLABORATOR"}
MAX_PAGES = 10


def get(url, **params):
    r = httpx.get(url, headers=H, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def main() -> None:
    labels = [x["name"] for x in get(f"https://api.github.com/repos/{REPO}/labels", per_page=100)]
    print("labels:", labels)
    candidates, seen = [], 0
    for page in range(1, MAX_PAGES + 1):
        batch = get(f"https://api.github.com/repos/{REPO}/issues",
                    state="closed", per_page=100, page=page, sort="created", direction="desc")
        if not batch:
            break
        for it in batch:
            if "pull_request" in it or it["comments"] == 0:
                continue
            seen += 1
            if not QUESTIONY.search(it["title"]):
                continue
            comments = get(it["comments_url"], per_page=30)
            maint = [c for c in comments if c["author_association"] in MAINTAINER]
            candidates.append({
                "number": it["number"], "title": it["title"], "url": it["html_url"],
                "created": it["created_at"][:10], "has_maintainer_reply": bool(maint),
                "n_comments": it["comments"],
            })
    OUT.write_text("\n".join(json.dumps(c) for c in candidates), encoding="utf-8")
    good = [c for c in candidates if c["has_maintainer_reply"]]
    print(f"closed issues with comments scanned: {seen}")
    print(f"question-like titles: {len(candidates)}   with maintainer reply: {len(good)}")
    by_year: dict[str, int] = {}
    for c in good:
        by_year[c["created"][:4]] = by_year.get(c["created"][:4], 0) + 1
    print("with maintainer reply, by year:", dict(sorted(by_year.items())))
    for c in good[:10]:
        print(" -", c["created"], c["title"], c["url"])


if __name__ == "__main__":
    main()
