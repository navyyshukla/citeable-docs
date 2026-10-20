"""Task 15 dev set: list 2023-onward answered Q&A discussions and maintainer-answered
`question` issues for the owner to pick from. Output goes to spikes/.cache (gitignored):
it is third-party text and must not enter git. Read-only; needs GITHUB_TOKEN."""
import json
import os
from pathlib import Path

import httpx

REPO = "saulpw/visidata"
AUTH = {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"}
MAINTAINER = {"OWNER", "MEMBER", "COLLABORATOR"}
SINCE = "2023-01-01"
OUT = Path("spikes/.cache/dev_candidates.json")


def discussions() -> list[dict]:
    q = """query($after:String){repository(owner:"saulpw",name:"visidata"){
      discussions(first:50,after:$after){nodes{number title url createdAt body
      category{name} answer{body author{login}}} pageInfo{hasNextPage endCursor}}}}"""
    after, out = None, []
    while True:
        r = httpx.post("https://api.github.com/graphql", headers=AUTH, timeout=90,
                       json={"query": q, "variables": {"after": after}})
        d = r.json()["data"]["repository"]["discussions"]
        for n in d["nodes"]:
            if n["answer"] and n["createdAt"] >= SINCE and n["category"]["name"] == "Q&A":
                out.append({"kind": "discussion", "title": n["title"], "url": n["url"],
                            "date": n["createdAt"][:10], "question": n["body"],
                            "answer": n["answer"]["body"]})
        if not d["pageInfo"]["hasNextPage"]:
            return out
        after = d["pageInfo"]["endCursor"]


def issues() -> list[dict]:
    H = {"Accept": "application/vnd.github+json", **AUTH}
    out = []
    for page in range(1, 10):
        batch = httpx.get(f"https://api.github.com/repos/{REPO}/issues", headers=H, timeout=60,
                          params={"state": "closed", "labels": "question", "per_page": 100,
                                  "page": page, "since": SINCE}).json()
        if not batch:
            break
        for i in batch:
            if "pull_request" in i or i["comments"] == 0 or i["created_at"] < SINCE:
                continue
            cs = httpx.get(i["comments_url"], headers=H, params={"per_page": 30}, timeout=60).json()
            m = [c for c in cs if c["author_association"] in MAINTAINER]
            if m:
                out.append({"kind": "issue", "title": i["title"], "url": i["html_url"],
                            "date": i["created_at"][:10], "question": i["body"] or "",
                            "answer": m[0]["body"]})
    return out


if __name__ == "__main__":
    items = sorted(discussions() + issues(), key=lambda x: x["date"], reverse=True)
    OUT.write_text(json.dumps(items, indent=1), encoding="utf-8")
    print(len(items), "candidates ->", OUT)
