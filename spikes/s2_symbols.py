"""Spike S2: does a symbol-aware tokenizer find single-key commands?"""
import math
import re
import tarfile
from collections import Counter
from pathlib import Path

CACHE = Path(__file__).parent / ".cache" / "stable.tar.gz"
WORD = re.compile(r"[A-Za-z0-9_]+")
SYM = re.compile(r"[A-Za-z0-9_]+|[^\sA-Za-z0-9_]")
FRONT = re.compile(r"\A---\n.*?\n---\n", re.S)
HEAD = re.compile(r"^#{1,6}[ \t]+", re.M)

# (query, acceptable page stems). Grounded in pages we read: join.md and columns.md.
QUERIES = [
    ("what does & do?", {"join"}),
    ("what does ! do?", {"columns"}),
    ("how do I hide a column?", {"columns"}),
    ("what does ( do?", {"columns"}),
    ("how do I make a derived column with =", {"columns"}),
    ("how do I join two sheets?", {"join"}),
    # extra pairs, each verified against a real heading on `stable` (see docs/spikes/s2-symbols.md)
    ("how do I filter a random subset of rows?", {"rows"}),
    ("how do I append two datasets?", {"join"}),
    ("how do I save and replay a session?", {"save-restore"}),
]
LONE_SYMBOL = re.compile(r"(?<![A-Za-z0-9_])([^\sA-Za-z0-9_?])(?![A-Za-z0-9_])")


def load_sections() -> dict[str, str]:
    sections: dict[str, str] = {}
    with tarfile.open(CACHE, "r:gz") as tf:
        for m in tf:
            parts = m.name.split("/", 1)
            if not (m.isfile() and len(parts) == 2 and parts[1].startswith("docs/")):
                continue
            name = parts[1][len("docs/"):]
            if "/" in name or not name.endswith(".md"):
                continue
            text = FRONT.sub("", tf.extractfile(m).read().decode("utf-8", "replace"))
            for i, chunk in enumerate(HEAD.split(text)):
                if chunk.strip():
                    sections[f"{name[:-3]}:{i}"] = chunk
    return sections


def bm25(docs: dict[str, str], pattern: re.Pattern):
    tok = lambda s: [t.lower() for t in pattern.findall(s)]  # noqa: E731
    tf = {i: Counter(tok(t)) for i, t in docs.items()}
    ln = {i: sum(c.values()) for i, c in tf.items()}
    avg = sum(ln.values()) / len(ln)
    df = Counter()
    for c in tf.values():
        df.update(c.keys())
    n = len(docs)
    idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def search(q: str, k: int = 3):
        qt = [t for t in tok(q.strip().rstrip("?")) if t in idf]
        scored = []
        for i, c in tf.items():
            s = sum(idf[t] * c[t] * 2.5 / (c[t] + 1.5 * (0.25 + 0.75 * ln[i] / avg))
                    for t in qt if c.get(t))
            if s > 0:
                scored.append((s, i))
        return [i for _, i in sorted(scored, reverse=True)[:k]]

    return search


def key_path(docs: dict[str, str], q: str) -> list[str]:
    """Exact path for a lone symbol in the query (`&`, `!`, `(`, `=`): sections that show
    the key in backticks. A table row that starts with the key (a definition) counts 3x."""
    m = LONE_SYMBOL.search(q)
    if not m:
        return []
    key = re.escape(m.group(1))
    anywhere = re.compile(r"`\s*" + key + r"\s*`")
    defined = re.compile(r"^\s*`\s*" + key + r"\s*`\s{2,}\S", re.M)
    scored = [(len(anywhere.findall(t)) + 3 * len(defined.findall(t)), i)
              for i, t in docs.items() if anywhere.search(t)]
    return [i for _, i in sorted(scored, reverse=True)]


def main() -> None:
    docs = load_sections()
    print(f"{len(docs)} sections")
    word, sym = bm25(docs, WORD), bm25(docs, SYM)
    modes = {
        "word-only": lambda q, k: word(q, k),
        "symbol-aware": lambda q, k: sym(q, k),
        "symbol-aware + exact key path": lambda q, k: (
            key_path(docs, q)[:2] + [x for x in sym(q, k) if x not in key_path(docs, q)[:2]])[:k],
    }
    for label, fn in modes.items():
        h3 = h5 = 0
        print(f"\n--- {label} ---")
        for q, want in QUERIES:
            g3, g5 = fn(q, 3), fn(q, 5)
            ok3 = any(g.split(":")[0] in want for g in g3)
            ok5 = any(g.split(":")[0] in want for g in g5)
            h3 += ok3
            h5 += ok5
            print(("HIT  " if ok3 else "MISS ") + q, "->", g3)
        print(f"hit@3: {h3}/{len(QUERIES)}   hit@5: {h5}/{len(QUERIES)}")


if __name__ == "__main__":
    main()
