from app.config import ProjectCfg
from ingest.chunk import chunk_markdown
from ingest.clean import clean_markdown
from ingest.models import Piece

SKIP = {"README.md"}


def page_title(stem: str) -> str:
    return stem.replace("_", " ").replace("-", " ").title()


def build_pieces(files: dict[str, str], cfg: ProjectCfg) -> list[Piece]:
    base = cfg.site_base_url.rstrip("/")
    pieces: list[Piece] = []
    for name in sorted(files):
        if name in SKIP or not name.endswith(".md"):
            continue
        stem = name[:-3]
        doc = clean_markdown(files[name])
        title = page_title(stem)
        url = f"{base}/" if stem == "index" else f"{base}/{stem}/"
        for n, raw in enumerate(chunk_markdown(doc.body, title)):
            pieces.append(Piece(
                id=f"{stem}:{n}", page_slug=stem, page_title=title, url=url,
                anchor=raw.anchor, heading_path=raw.heading_path, text=raw.text,
                docs_ref=cfg.ref, docs_version=doc.docs_version, last_updated=doc.last_updated,
                anchor_explicit=raw.anchor_explicit,
            ))
    return pieces
