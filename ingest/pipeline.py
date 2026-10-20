import re
from urllib.parse import quote, urljoin, urlsplit

from app.config import ProjectCfg
from ingest.chunk import chunk_markdown
from ingest.clean import clean_markdown
from ingest.models import Piece

_LINK = re.compile(r"(!?)\[([^\]]*)\]\(([^)\s]*)\)")
_HAS_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def page_title(stem: str) -> str:
    return stem.replace("_", " ").replace("-", " ").title()


def absolutize_links(text: str, page_url: str, site_root: str) -> str:
    """Make relative links absolute so every link in a piece can be checked against the docs'
    own URLs; images are dropped (the model cannot show them) and their alt text is kept."""

    def repl(m: re.Match) -> str:
        bang, label, href = m.groups()
        if bang:
            return label
        if _HAS_SCHEME.match(href):
            return m.group(0)
        if href.startswith("#"):
            target = page_url + href
        elif href.startswith("/"):
            target = site_root + href
        else:
            target = urljoin(page_url, href)
        return f"[{label}]({target})"

    return _LINK.sub(repl, text)


def build_pieces(files: dict[str, str], cfg: ProjectCfg,
                 docs_ref: str | None = None) -> list[Piece]:
    base = cfg.site_base_url.rstrip("/")
    parts = urlsplit(base)
    site_root = f"{parts.scheme}://{parts.netloc}"
    pieces: list[Piece] = []
    for name in sorted(files):
        stem = name[:-3]
        if name in cfg.skip_files or not name.endswith(".md") or not stem:
            continue
        doc = clean_markdown(files[name])
        title = doc.title or page_title(stem)
        url = f"{base}/" if stem == "index" else f"{base}/{quote(stem)}/"
        for n, raw in enumerate(chunk_markdown(doc.body, title, cfg.max_piece_chars)):
            text = absolutize_links(raw.text, url, site_root)
            if not text.strip():
                continue
            pieces.append(Piece(
                id=f"{stem}:{n}", page_slug=stem, page_title=title, url=url,
                anchor=raw.anchor, heading_path=raw.heading_path, text=text,
                docs_ref=docs_ref or cfg.ref, docs_version=doc.docs_version, last_updated=doc.last_updated,
                anchor_explicit=raw.anchor_explicit,
            ))
    return pieces
