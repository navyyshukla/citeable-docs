import re
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


def test_urls_are_percent_encoded_and_empty_stems_skipped():
    pieces = build_pieces({"My Doc.md": "## T\n\ntext\n", ".md": "## T\n\ntext\n"}, CFG)
    assert [p.page_slug for p in pieces] == ["My Doc"]
    assert pieces[0].url == "https://www.visidata.org/docs/My%20Doc/"


def test_page_title_comes_from_front_matter_when_present():
    files = {"join.md": "---\neleventyNavigation:\n  key: Combining datasets\n---\n## A\n\ntext\n",
             "save-restore.md": "## A\n\ntext\n"}
    by_slug = {p.page_slug: p for p in build_pieces(files, CFG)}
    assert by_slug["join"].page_title == "Combining datasets"
    assert by_slug["join"].heading_path[0] == "Combining datasets"
    assert by_slug["save-restore"].page_title == "Save Restore"


def test_skip_list_and_piece_size_come_from_config():
    cfg = CFG.model_copy(update={"skip_files": ["skipme.md"], "max_piece_chars": 60})
    files = {"skipme.md": "## A\n\ntext\n", "README.md": "## R\n\nkept now\n",
             "big.md": "## B\n\n" + "\n\n".join(["word " * 8] * 6) + "\n"}
    pieces = build_pieces(files, cfg)
    assert {p.page_slug for p in pieces} == {"README", "big"}
    assert len([p for p in pieces if p.page_slug == "big"]) > 1


def test_relative_links_become_absolute_and_images_are_dropped():
    text = ("See [customize](/docs/customize) and [other](other-page) and [sec](#sec) and "
            "[ext](https://example.org/x). ![](assets/a.png) ![alt words](assets/b.png)\n")
    (p,) = build_pieces({"join.md": "## A\n\n" + text}, CFG)
    assert "(https://www.visidata.org/docs/customize)" in p.text
    assert "(https://www.visidata.org/docs/join/other-page)" in p.text
    assert "(https://www.visidata.org/docs/join/#sec)" in p.text
    assert "(https://example.org/x)" in p.text
    assert "assets/a.png" not in p.text and "assets/b.png" not in p.text and "alt words" in p.text


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
    shape = re.compile(r"^https://www\.visidata\.org/docs/([A-Za-z0-9._~%-]+/)?(#[A-Za-z0-9_-]+)?$")
    assert all(shape.match(p.citation_url) for p in pieces)
    assert {p.docs_ref for p in pieces} == {"stable"}
