"""Clean one VisiData docs Markdown file: split front matter, drop noise (never inside code blocks)."""
import re
from dataclasses import dataclass

from ingest.fences import fence_mask

_FRONT = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.DOTALL)
_SCRIPT = re.compile(r"<script\b.*?</script>", re.DOTALL | re.IGNORECASE)
_PLAYER = re.compile(r"<asciinema-player\b.*?</asciinema-player>", re.DOTALL | re.IGNORECASE)
_BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)
# a whole list item that is only a placeholder, or a placeholder on its own line
_PLACEHOLDER_LINE = re.compile(
    r"^[ \t]*(?:(?:[-*+]|\d+[.)])[ \t]+)?\{help\.[^}\n]*\}[ \t]*(?:\n|\Z)", re.MULTILINE
)
_PLACEHOLDER = re.compile(r"\{help\.[^}\n]*\}")
# blocks that only hold a demo player: <div class="asciicast"> and <section id="hero">
_DEMO_OPEN = re.compile(
    r"<(div|section)\b[^>]*\b(?:class=[\"'][^\"']*\basciicast\b[^\"']*[\"']|id=[\"']hero[\"'])[^>]*>",
    re.IGNORECASE,
)
_RULE = re.compile(r"^[ \t]*---[ \t]*$")
_BLANKS = re.compile(r"\n{3,}")
_FRONT_KEY = re.compile(r"^[\w-]+\s*:")


@dataclass(frozen=True)
class CleanDoc:
    body: str
    last_updated: str | None
    docs_version: str | None
    title: str | None = None


def _front_value(block: str, key: str) -> str | None:
    m = re.search(rf"^\s*(?:{key})\s*:\s*(.+?)\s*$", block, re.MULTILINE | re.IGNORECASE)
    return m.group(1).strip().strip("'\"") if m else None


def _front_title(block: str) -> str | None:
    m = re.search(r"^eleventyNavigation\s*:\s*\n[ \t]+key\s*:\s*(.+?)\s*$", block, re.MULTILINE)
    return m.group(1).strip().strip("'\"") if m else _front_value(block, "title")


def _looks_like_front_matter(block: str) -> bool:
    """A real front-matter block starts with `key:` and has no Markdown headings.
    This keeps a leading horizontal rule from being read as the start of front matter."""
    lines = [ln for ln in block.splitlines() if ln.strip()]
    return bool(lines) and bool(_FRONT_KEY.match(lines[0])) and not any(
        ln.lstrip().startswith("#") for ln in lines
    )


def _drop_demo_blocks(text: str) -> str:
    """Remove each demo block through its matching close tag (counts nested tags of the same name).
    If the block never closes, only its opening tag is removed: never delete text we cannot bound."""
    while m := _DEMO_OPEN.search(text):
        tag, depth, pos = m.group(1).lower(), 1, m.end()
        tags = re.compile(rf"<(/?){tag}\b[^>]*>", re.IGNORECASE)
        while depth and (t := tags.search(text, pos)):
            if t.group(1):
                depth -= 1
            elif not t.group(0).endswith("/>"):  # a self-closing tag opens nothing
                depth += 1
            pos = t.end()
        text = text[: m.start()] + text[pos if depth == 0 else m.end():]
    return text


def _drop_rules(text: str) -> str:
    """Remove horizontal rules. A `---` directly under a text line is a setext heading underline: keep."""
    lines = text.split("\n")
    keep = [
        not (_RULE.match(ln) and (i == 0 or not lines[i - 1].strip()))
        for i, ln in enumerate(lines)
    ]
    return "\n".join(ln for ln, k in zip(lines, keep, strict=True) if k)


def _scrub(text: str) -> str:
    text = _SCRIPT.sub("", text)
    text = _drop_demo_blocks(text)
    text = _PLAYER.sub("", text)
    text = _BREAK.sub("", text)
    text = _PLACEHOLDER_LINE.sub("", text)
    text = _PLACEHOLDER.sub("", text)
    return _BLANKS.sub("\n\n", _drop_rules(text))


def clean_markdown(raw: str) -> CleanDoc:
    raw = raw.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    last_updated = docs_version = title = None
    m = _FRONT.match(raw)
    if m and _looks_like_front_matter(m.group(1)):
        last_updated = _front_value(m.group(1), "updated?|date")
        docs_version = _front_value(m.group(1), "version")
        title = _front_title(m.group(1))
        raw = raw[m.end():]
    lines = raw.split("\n")
    mask = fence_mask(lines)
    # group consecutive lines by code / not code; scrub only the non-code runs
    parts: list[str] = []
    i = 0
    while i < len(lines):
        j = i
        while j < len(lines) and mask[j] == mask[i]:
            j += 1
        chunk = "\n".join(lines[i:j])
        parts.append(chunk if mask[i] else _scrub(chunk))
        i = j
    body = "\n".join(parts).strip() + "\n"
    return CleanDoc(body, last_updated, docs_version, title)
