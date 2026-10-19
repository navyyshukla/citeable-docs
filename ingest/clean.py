"""Clean one VisiData docs Markdown file: split front matter, drop noise."""
import re
from dataclasses import dataclass

_FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_SCRIPT = re.compile(r"<script\b.*?</script>", re.DOTALL | re.IGNORECASE)
_PLAYER = re.compile(r"<asciinema-player\b.*?</asciinema-player>", re.DOTALL | re.IGNORECASE)
_BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)
# a whole list item that is only a placeholder, or a placeholder on its own line
_PLACEHOLDER_LINE = re.compile(
    r"^[ \t]*(?:(?:[-*+]|\d+[.)])[ \t]+)?\{help\.[^}\n]*\}[ \t]*(?:\n|\Z)", re.MULTILINE
)
_PLACEHOLDER = re.compile(r"\{help\.[^}\n]*\}")
# blocks that only hold a demo player: <div class="asciicast"> and <section id="hero">
_DEMO_OPEN = re.compile(r"<(div|section)\b[^>]*\b(?:class=\"asciicast\"|id=\"hero\")[^>]*>", re.IGNORECASE)
_RULE = re.compile(r"^[ \t]*---[ \t]*$", re.MULTILINE)
_BLANKS = re.compile(r"\n{3,}")


@dataclass(frozen=True)
class CleanDoc:
    body: str
    last_updated: str | None
    docs_version: str | None


def _front_value(block: str, key: str) -> str | None:
    m = re.search(rf"^\s*(?:{key})\s*:\s*(.+?)\s*$", block, re.MULTILINE | re.IGNORECASE)
    return m.group(1).strip().strip("'\"") if m else None


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


def clean_markdown(raw: str) -> CleanDoc:
    last_updated = docs_version = None
    m = _FRONT.match(raw)
    if m:
        last_updated = _front_value(m.group(1), "updated?|date")
        docs_version = _front_value(m.group(1), "version")
        raw = raw[m.end():]
    raw = _SCRIPT.sub("", raw)
    raw = _drop_demo_blocks(raw)
    raw = _PLAYER.sub("", raw)
    raw = _BREAK.sub("", raw)
    raw = _PLACEHOLDER_LINE.sub("", raw)
    raw = _PLACEHOLDER.sub("", raw)
    raw = _RULE.sub("", raw)
    raw = _BLANKS.sub("\n\n", raw).strip() + "\n"
    return CleanDoc(raw, last_updated, docs_version)
