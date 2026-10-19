"""Guard: cleaning and chunking the real docs may drop only known noise words, never real text.

The allowed words are demo-player markup, cast file names, placeholder and heading-id tokens
(checked by hand against docs/*.md in the cold review of tasks 6-9). Anything new fails this test.
"""
import re
import tarfile
from pathlib import Path

import pytest

from ingest.chunk import chunk_markdown
from ingest.clean import clean_markdown

STABLE = Path(__file__).resolve().parents[2] / "spikes" / ".cache" / "stable.tar.gz"
FRONT = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
ALLOWED = {
    "asciicast", "asciinema", "attrs", "cast", "casts", "class", "color", "div", "help", "hero",
    "javascript", "npt", "options", "pivot", "player", "poster", "rows", "script", "section",
    "src", "text", "type",
}


def _words(text: str) -> set[str]:
    return set(re.findall(r"[A-Za-z]{3,}", text.lower()))


@pytest.mark.skipif(not STABLE.exists(), reason="docs cache not present (it is gitignored)")
def test_real_docs_lose_only_known_noise_words():
    lost: dict[str, list[str]] = {}
    with tarfile.open(STABLE) as tf:
        for m in tf:
            parts = m.name.split("/", 2)
            ok = m.isfile() and len(parts) == 3 and parts[1] == "docs" and parts[2].endswith(".md")
            if not ok or "/" in parts[2] or parts[2] == "README.md":
                continue
            raw = tf.extractfile(m).read().decode("utf-8", "replace")
            out: set[str] = set()
            for p in chunk_markdown(clean_markdown(raw).body, parts[2][:-3]):
                out |= _words(p.text) | _words(" ".join(p.heading_path))
            for w in _words(FRONT.sub("", raw)) - out:
                lost.setdefault(w, []).append(parts[2])
    unexpected = {w: pages for w, pages in lost.items() if w not in ALLOWED}
    assert unexpected == {}, unexpected
