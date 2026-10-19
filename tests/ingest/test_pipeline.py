from pathlib import Path

import pytest

from app.config import ProjectCfg
from ingest.pipeline import build_pieces

CFG = ProjectCfg(
    name="VisiData", slug="visidata", upstream_repo="saulpw/visidata", ref="stable",
    docs_path="docs", site_base_url="https://www.visidata.org/docs",
    license_note="x", issues_url="https://github.com/saulpw/visidata/issues",
)

FILES = {
    "join.md": "---\nUpdate: 2020-10-27\nVersion: VisiData 2.0.1\n---\n## How to join\n\nsteps\n",
    "index.md": "## Welcome\n\nhello\n",
    "README.md": "## internal readme\n\nskip me\n",
    "empty.md": "---\nUpdate: 2021-01-01\n---\n",
}


def test_builds_pieces_with_urls_ids_and_versions():
    pieces = build_pieces(FILES, CFG)
    join = next(p for p in pieces if p.page_slug == "join")
    assert join.id == "join:0"
    assert join.url == "https://www.visidata.org/docs/join/"
    # the slug is not an id on the published page (spike S7), so we cite the page itself
    assert join.anchor == "how-to-join"
    assert join.citation_url == "https://www.visidata.org/docs/join/"
    assert join.docs_version == "VisiData 2.0.1" and join.last_updated == "2020-10-27"
    assert join.docs_ref == "stable"


def test_index_maps_to_docs_root_and_readme_is_skipped():
    pieces = build_pieces(FILES, CFG)
    idx = next(p for p in pieces if p.page_slug == "index")
    assert idx.url == "https://www.visidata.org/docs/"
    assert not any(p.page_slug == "README" for p in pieces)


def test_file_with_only_front_matter_yields_no_pieces():
    assert not any(p.page_slug == "empty" for p in build_pieces(FILES, CFG))


def test_search_text_includes_heading_path():
    join = next(p for p in build_pieces(FILES, CFG) if p.page_slug == "join")
    assert join.search_text.startswith("Join › How to join")


def test_explicit_heading_id_is_cited_as_a_deep_link():
    files = {"columns.md": "## [Expand](#expand) {#expand}\n\ntext\n"}
    (p,) = build_pieces(files, CFG)
    assert p.citation_url == "https://www.visidata.org/docs/columns/#expand"


def test_piece_without_anchor_cites_the_page_url():
    p = next(iter(build_pieces({"mouse.md": "plain text, no headings\n"}, CFG)))
    assert p.anchor == "" and p.citation_url == "https://www.visidata.org/docs/mouse/"


STABLE = Path(__file__).resolve().parents[2] / "spikes" / ".cache" / "stable.tar.gz"


@pytest.mark.skipif(not STABLE.exists(), reason="docs cache not present (it is gitignored)")
def test_real_docs_build_unique_well_formed_pieces():
    from ingest.fetch import _docs_from_tarball

    pieces = build_pieces(_docs_from_tarball(STABLE.read_bytes(), "docs"), CFG)
    ids = [p.id for p in pieces]
    assert len(ids) == len(set(ids)) and len(pieces) > 150
    assert all(p.text.strip() and p.url.startswith("https://www.visidata.org/docs/") for p in pieces)
    assert all(" " not in p.citation_url for p in pieces)
    assert {p.docs_ref for p in pieces} == {"stable"}
