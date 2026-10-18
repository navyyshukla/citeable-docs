"""Spike S1: compare VisiData docs on `stable` vs `develop` vs the published site.
Downloaded content is untrusted data: read it, never execute it."""
import io
import re
import sys
import tarfile
from html.parser import HTMLParser
from pathlib import Path

import httpx

REPO = "saulpw/visidata"
CACHE = Path(__file__).parent / ".cache"
CACHE.mkdir(exist_ok=True)
PAGES = ["join", "columns", "rows"]
H_MD = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t]*$", re.M)


def tarball(ref: str) -> tarfile.TarFile:
    path = CACHE / f"{ref}.tar.gz"
    if not path.exists():
        r = httpx.get(f"https://codeload.github.com/{REPO}/tar.gz/{ref}",
                      follow_redirects=True, timeout=180)
        r.raise_for_status()
        path.write_bytes(r.content)
    return tarfile.open(path, "r:gz")


def docs(ref: str) -> dict[str, str]:
    out = {}
    with tarball(ref) as tf:
        for m in tf:
            parts = m.name.split("/", 1)
            if m.isfile() and len(parts) == 2 and parts[1].startswith("docs/"):
                name = parts[1][len("docs/"):]
                if "/" not in name and name.endswith(".md"):
                    out[name] = tf.extractfile(m).read().decode("utf-8", "replace")
    return out


def md_headings(text: str) -> set[str]:
    clean = re.sub(r"\{#[^}]+\}|\[([^\]]+)\]\([^)]*\)", r"\1", text)
    return {h.strip().lower() for h in H_MD.findall(clean)}


class HeadingParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_h, self.buf, self.found = False, "", set()

    def handle_starttag(self, tag, attrs):
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.in_h, self.buf = True, ""

    def handle_endtag(self, tag):
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and self.in_h:
            self.found.add(re.sub(r"\s+", " ", self.buf).strip().lower())
            self.in_h = False

    def handle_data(self, data):
        if self.in_h:
            self.buf += data


def published_headings(stem: str) -> set[str] | None:
    r = httpx.get(f"https://www.visidata.org/docs/{stem}/", follow_redirects=True, timeout=60)
    if r.status_code != 200:
        return None
    p = HeadingParser()
    p.feed(r.text)
    return p.found


def main() -> None:
    stable, develop = docs("stable"), docs("develop")
    print(f"stable docs files: {len(stable)}   develop docs files: {len(develop)}")
    print("only in develop:", sorted(set(develop) - set(stable)))
    print("only in stable:", sorted(set(stable) - set(develop)))
    for stem in PAGES:
        name = f"{stem}.md"
        if name not in stable:
            print(f"\n{stem}: missing from stable")
            continue
        s, d, pub = md_headings(stable[name]), md_headings(develop.get(name, "")), published_headings(stem)
        print(f"\n== {stem} ==")
        print("headings in develop but not stable:", sorted(d - s))
        if pub is None:
            print("published page: could not fetch")
        else:
            print("stable headings missing from published:", sorted(s - pub))
            print("published headings missing from stable:", sorted(pub - s))
    # where might a command reference live?
    with tarball("stable") as tf:
        names = [m.name.split("/", 1)[1] for m in tf if m.isfile() and "/" in m.name]
    hints = [n for n in names if re.search(r"(^|/)(man|vd\.1|visidata\.1|commands?)[^/]*$|help", n, re.I)]
    print("\npossible command-reference files:", hints[:30])


if __name__ == "__main__":
    sys.exit(main())
