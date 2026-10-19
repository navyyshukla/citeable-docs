"""Keyword search (BM25) that keeps single-key symbols, rank fusion, and search modes."""
import math
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from ingest.models import Piece

_TOKEN = re.compile(r"[A-Za-z0-9_]+|[^\sA-Za-z0-9_]")
_WORD = re.compile(r"[A-Za-z0-9_]+")
# One symbol standing alone in the question (`&`, `!`, `(`, `=`). `?` is the question mark.
_LONE_SYMBOL = re.compile(r"(?<![A-Za-z0-9_])([^\sA-Za-z0-9_?])(?![A-Za-z0-9_])")
# How many candidates each search gives to the fusion, and how many exact-key pieces go first.
POOL = 20
KEY_FIRST = 2


def tokenize_words(text: str) -> list[str]:
    return [t.lower() for t in _WORD.findall(text)]


def tokenize_symbols(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text)]


class Bm25:
    def __init__(self, docs: dict[str, str], tokenize=tokenize_symbols, k1=1.5, b=0.75):
        self.tokenize, self.k1, self.b = tokenize, k1, b
        self.tf = {i: Counter(tokenize(t)) for i, t in docs.items()}
        self.len = {i: sum(c.values()) for i, c in self.tf.items()}
        self.avg = (sum(self.len.values()) / len(docs)) if docs else 0.0
        df: Counter = Counter()
        for c in self.tf.values():
            df.update(c.keys())
        n = len(docs)
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def search(self, query: str, k: int = 5) -> list[tuple[str, float]]:
        q = [t for t in self.tokenize(query.strip().rstrip("?")) if t in self.idf]
        scored = []
        for i, c in self.tf.items():
            s = 0.0
            for t in q:
                f = c.get(t, 0)
                if f:
                    denom = f + self.k1 * (1 - self.b + self.b * self.len[i] / (self.avg or 1))
                    s += self.idf[t] * f * (self.k1 + 1) / denom
            if s > 0:
                scored.append((i, s))
        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored[:k]


def key_path(docs: dict[str, str], query: str) -> list[str]:
    """Sections that show the query's lone symbol in backticks, best first.

    A table row that starts with the key (a definition such as "`!`   pins the column")
    counts 3x, so a definition beats a mere mention (spike S2). No lone symbol, or the
    symbol in no backticks: empty list.
    """
    m = _LONE_SYMBOL.search(query)
    if not m:
        return []
    key = re.escape(m.group(1))
    anywhere = re.compile(r"`\s*" + key + r"\s*`")
    defined = re.compile(r"^\s*`\s*" + key + r"\s*`\s{2,}\S", re.MULTILINE)
    scored = [(len(anywhere.findall(t)) + 3 * len(defined.findall(t)), i)
              for i, t in docs.items() if anywhere.search(t)]
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [i for _, i in scored]


def rrf(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, pid in enumerate(ranking, start=1):
            scores[pid] = scores.get(pid, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: (-x[1], x[0]))


@dataclass(frozen=True)
class Hit:
    piece_id: str
    score: float


class Searcher:
    def __init__(self, pieces: list[Piece],
                 embed_query: Callable[[str], list[float]] | None = None,
                 vector_search: Callable[[list[float], int], list[tuple[str, float]]] | None = None,
                 rrf_k: int = 60):
        self._docs = {p.id: p.search_text for p in pieces}
        self._bm25 = Bm25(self._docs)
        self._embed, self._vsearch, self._rrf_k = embed_query, vector_search, rrf_k

    def _keyword(self, query: str, k: int) -> list[tuple[str, float]]:
        """Exact-key sections first, then BM25. Scores here are only for ordering."""
        keys = key_path(self._docs, query)[:KEY_FIRST]
        rest = [(i, s) for i, s in self._bm25.search(query, k) if i not in keys]
        top = [(i, float(len(keys) - n + max((s for _, s in rest), default=0.0)))
               for n, i in enumerate(keys)]
        return (top + rest)[:k]

    def search(self, mode: str, query: str, k: int = 5) -> list[Hit]:
        if mode not in {"keyword", "meaning", "hybrid"}:
            raise ValueError(f"unknown search mode {mode!r}")
        query = query.strip()
        if mode == "keyword":
            return [Hit(i, s) for i, s in self._keyword(query, k)] if query else []
        if self._embed is None or self._vsearch is None:
            raise ValueError("meaning/hybrid search needs embeddings")
        if not query:
            return []
        vhits = self._vsearch(self._embed(query), max(k, POOL))
        if mode == "meaning":
            return [Hit(i, s) for i, s in vhits[:k]]
        kw = self._keyword(query, max(k, POOL))
        fused = rrf([[i for i, _ in kw], [i for i, _ in vhits]], self._rrf_k)
        return [Hit(i, s) for i, s in fused[:k]]
