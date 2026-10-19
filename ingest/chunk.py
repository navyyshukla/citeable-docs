"""Cut cleaned Markdown into pieces by heading, keeping the heading path."""
import re
from dataclasses import dataclass

from ingest.fences import fence_mask

_HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.+?)[ \t]*$")
_SETEXT_UNDERLINE = re.compile(r"^ {0,3}(=+|-{2,})[ \t]*$")
_CLOSING_HASHES = re.compile(r"[ \t]+#+[ \t]*$")
_CUSTOM_ID = re.compile(r"\s*\{#([A-Za-z0-9_-]+)\}\s*$")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_BOLD = re.compile(r"(\*\*|__)(.+?)\1")
_TABLE_RULE = re.compile(r"^[ \t]*\|?[ \t]*:?-{3,}:?[ \t]*(\|[ \t]*:?-{3,}:?[ \t]*)*\|?[ \t]*$")
_NOT_A_SETEXT_TEXT = re.compile(r"^\s*(#|[-*+>|]|\d+[.)]|<)")


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
    raw = _CLOSING_HASHES.sub("", raw)
    m = _CUSTOM_ID.search(raw)
    if m:
        anchor = m.group(1)
        raw = raw[: m.start()]
    title = _BOLD.sub(r"\2", _MD_LINK.sub(r"\1", raw)).strip()
    return title, anchor or slugify(title)


def _setext_to_atx(lines: list[str]) -> list[str]:
    """Turn `Title` over `=====` or `-----` into `# Title` / `## Title` (outside code blocks)."""
    mask = fence_mask(lines)
    out: list[str] = []
    i = 0
    while i < len(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        is_text = lines[i].strip() and not _NOT_A_SETEXT_TEXT.match(lines[i])
        starts_paragraph = i == 0 or not lines[i - 1].strip()
        underline = _SETEXT_UNDERLINE.match(nxt)
        if (is_text and starts_paragraph and underline and not mask[i] and not mask[i + 1]
                and "|" not in lines[i]):  # a pipe in the line above means a table header
            out.append(("# " if underline.group(1).startswith("=") else "## ") + lines[i].strip())
            i += 2
        else:
            out.append(lines[i])
            i += 1
    return out


def _split_paragraphs(body: str) -> list[str]:
    """Split on blank lines, except inside fenced code (a code block is one paragraph)."""
    lines = body.strip().split("\n")
    paragraphs: list[str] = []
    cur: list[str] = []
    for line, in_code in zip(lines, fence_mask(lines), strict=True):
        if not in_code and not line.strip():
            if cur:
                paragraphs.append("\n".join(cur))
                cur = []
        else:
            cur.append(line)
    if cur:
        paragraphs.append("\n".join(cur))
    return [p for p in paragraphs if p.strip()]


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
    lines = _setext_to_atx(doc.splitlines())
    mask = fence_mask(lines)
    sections: list[tuple[tuple[str, ...], str, bool, list[str]]] = []
    stack: list[tuple[int, str]] = []
    path: tuple[str, ...] = (page_title,)
    anchor = ""
    explicit = False
    buf: list[str] = []
    last_heading: tuple[int, str] | None = None  # (level, original line) of the latest heading
    carried: list[str] = []  # headings with no body, kept as the first lines of the next piece

    def flush() -> None:
        if "".join(buf).strip():
            sections.append((path, anchor, explicit, [*carried, *([""] if carried else []), *buf]))
            carried.clear()
        buf.clear()

    for line, in_code in zip(lines, mask, strict=True):
        m = None if in_code else _HEADING.match(line)
        if m:
            level = len(m.group(1))
            had_body = bool("".join(buf).strip())
            if not had_body and last_heading and last_heading[0] >= level:
                carried.append(last_heading[1])  # empty heading above a sibling or a higher one
            flush()
            title, anchor = parse_heading(m.group(2))
            explicit = bool(_CUSTOM_ID.search(_CLOSING_HASHES.sub("", m.group(2))))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            path = (page_title, *[t for _, t in stack])
            last_heading = (level, line.strip())
        else:
            buf.append(line)
    flush()

    pieces: list[RawPiece] = []
    for sec_path, sec_anchor, sec_explicit, sec_lines in sections:
        for group in _pack(_split_paragraphs("\n".join(sec_lines)), max_chars):
            pieces.append(RawPiece(sec_path, sec_anchor, group, sec_explicit))
    return pieces
