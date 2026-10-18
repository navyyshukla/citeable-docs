"""Spike S3 extension: the plan script (s3_questions.py) filters by title and stops after
10 pages, so it undercounts. This counts closed issues labelled `question` and answered
Q&A Discussions. Needs GITHUB_TOKEN (fine-grained, public read-only). Counts only; it does
not judge answer quality or whether the answer is still true on `stable`."""
import collections
import os

import httpx

REPO = "saulpw/visidata"
AUTH = {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"}
H = {"Accept": "application/vnd.github+json", **AUTH}
MAINTAINER = {"OWNER", "MEMBER", "COLLABORATOR"}


def get(url, **params):
    r = httpx.get(url, headers=H, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def issues_with_question_label() -> None:
    qs = []
    for page in range(1, 30):
        batch = get(f"https://api.github.com/repos/{REPO}/issues",
                    state="closed", labels="question", per_page=100, page=page)
        if not batch:
            break
        qs += [i for i in batch if "pull_request" not in i]
    withc = [i for i in qs if i["comments"] > 0]
    print("closed issues labelled `question`:", len(qs), "| with >=1 comment:", len(withc))
    years: dict[str, int] = {}
    good = 0
    for i in withc:
        comments = get(i["comments_url"], per_page=30)
        if any(c["author_association"] in MAINTAINER for c in comments):
            good += 1
            years[i["created_at"][:4]] = years.get(i["created_at"][:4], 0) + 1
    print("`question` issues with a maintainer reply:", good,
          "| by year:", dict(sorted(years.items())))


def answered_discussions() -> None:
    query = """query($after:String){repository(owner:"saulpw",name:"visidata"){
      discussions(first:100,after:$after){nodes{createdAt category{name} answer{id}}
      pageInfo{hasNextPage endCursor}}}}"""
    after, nodes = None, []
    while True:
        r = httpx.post("https://api.github.com/graphql", headers=AUTH, timeout=60,
                       json={"query": query, "variables": {"after": after}})
        d = r.json()["data"]["repository"]["discussions"]
        nodes += d["nodes"]
        if not d["pageInfo"]["hasNextPage"]:
            break
        after = d["pageInfo"]["endCursor"]
    cats = sorted({n["category"]["name"] for n in nodes})
    print("discussions:", len(nodes))
    print("by category (total/answered):", {
        c: (sum(1 for n in nodes if n["category"]["name"] == c),
            sum(1 for n in nodes if n["category"]["name"] == c and n["answer"])) for c in cats})
    answered = [n for n in nodes if n["answer"]]
    print("answered:", len(answered), "| by year:",
          dict(sorted(collections.Counter(n["createdAt"][:4] for n in answered).items())))


if __name__ == "__main__":
    issues_with_question_label()
    answered_discussions()
