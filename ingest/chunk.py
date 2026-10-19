"""Cut cleaned Markdown into pieces by heading, keeping the heading path."""
import re
from dataclasses import dataclass

_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$")
_CUSTOM_ID = re.compile(r"\s*\{#([A-Za-z0-9_-]+)\}\s*$")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_BOLD = re.compile(r"(\*\*|__)(.+?)\1")
_TABLE_RULE = re.compile(r"^[ \t]*\|?[ \t]*:?-{3,}:?[ \t]*(\|[ \t]*:?-{3,}:?[ \t]*)*\|?[ \t]*$")
_FENCE = re.compile(r"^[ \t]*(```|~~~)")


@dataclass(frozen=True)
class RawPiece:
    heading_path: tuple[str, ...]
    anchor: str
    text: str
    anchor_explicit: bool = False  # heading had its own {#id}; only those exist on the site


def slugify(title: str) -> str:
    s = re.sub(r"[^\w\s-]", "", title.lower())
    return re.sub(r"[\s]+", "-", s.strip())


def parse_heading(raw: str) -> tuple[str, str]:
    """Return (clean title, anchor id) for the text after the #'s."""
    anchor = ""
    m = _CUSTOM_ID.search(raw)
    if m:
        anchor = m.group(1)
        raw = raw[: m.start()]
    title = _BOLD.sub(r"\2", _MD_LINK.sub(r"\1", raw)).strip()
    return title, anchor or slugify(title)


def _split_paragraphs(body: str) -> list[str]:
    return [p for p in re.split(r"\n\s*\n", body.strip()) if p.strip()]


def _split_wide_table(paragraph: str, max_chars: int) -> list[str]:
    """Split an oversized pipe table into row groups, repeating the header on each part.
    Anything that is not a pipe table, or already fits, is returned unchanged."""
    lines = paragraph.splitlines()
    is_table = len(lines) > 2 and lines[0].lstrip().startswith("|") and _TABLE_RULE.match(lines[1])
    if len(paragraph) <= max_chars or not is_table:
        return [paragraph]
    header = "\n".join(lines[:2])
    parts: list[str] = []
    cur: list[str] = []
    for row in lines[2:]:
        if cur and len(header) + 1 + len("\n".join(cur)) + 1 + len(row) > max_chars:
            parts.append(header + "\n" + "\n".join(cur))
            cur = []
        cur.append(row)
    if cur:
        parts.append(header + "\n" + "\n".join(cur))
    return parts


def _pack(paragraphs: list[str], max_chars: int) -> list[str]:
    """Pack whole paragraphs into groups <= max_chars. Never splits a paragraph,
    so a table (no blank lines inside) always stays whole with its header."""
    groups: list[str] = []
    cur = ""
    for p in (part for para in paragraphs for part in _split_wide_table(para, max_chars)):
        if cur and len(cur) + 2 + len(p) > max_chars:
            groups.append(cur)
            cur = p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur:
        groups.append(cur)
    return groups


def chunk_markdown(doc: str, page_title: str, max_chars: int = 1500) -> list[RawPiece]:
    sections: list[tuple[tuple[str, ...], str, bool, list[str]]] = []
    stack: list[tuple[int, str]] = []
    path: tuple[str, ...] = (page_title,)
    anchor = ""
    explicit = False
    buf: list[str] = []
    in_fence = False

    def flush() -> None:
        if "".join(buf).strip():
            sections.append((path, anchor, explicit, buf.copy()))
        buf.clear()

    for line in doc.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
        m = None if in_fence else _HEADING.match(line)
        if m:
            flush()
            level = len(m.group(1))
            title, anchor = parse_heading(m.group(2))
            explicit = bool(_CUSTOM_ID.search(m.group(2)))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            path = (page_title, *[t for _, t in stack])
        else:
            buf.append(line)
    flush()

    pieces: list[RawPiece] = []
    for sec_path, sec_anchor, sec_explicit, lines in sections:
        for group in _pack(_split_paragraphs("\n".join(lines)), max_chars):
            pieces.append(RawPiece(sec_path, sec_anchor, group, sec_explicit))
    return pieces
