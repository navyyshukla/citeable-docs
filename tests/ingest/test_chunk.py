import tarfile
from pathlib import Path

import pytest

from ingest.chunk import chunk_markdown, parse_heading

DOC = """## How to format columns

intro text

###### How to format a numeric column

1. step one
2. step two

## How to specify column types

Command    Type
--------- --------
` ~`      string
` #`      int

~~~
## not a heading
~~~
"""


def test_parse_heading_custom_id_and_link():
    assert parse_heading(
        "[How to expand columns that contain nested data](#expand) {#expand}"
    ) == ("How to expand columns that contain nested data", "expand")


def test_parse_heading_slug_fallback():
    assert parse_heading("How to hide (remove) columns") == (
        "How to hide (remove) columns", "how-to-hide-remove-columns")


def test_parse_heading_strips_bold_markup():
    # real case (spike S1): columns.md has bold markup inside a heading
    assert parse_heading("How to format **month/day/year** dates") == (
        "How to format month/day/year dates", "how-to-format-monthdayyear-dates")


def test_only_explicit_ids_are_marked_explicit():
    # the published site has ids only on headings written with {#id} (spike S7)
    doc = "## Plain heading\n\ntext\n\n## [Expand](#expand) {#expand}\n\nmore\n"
    plain, custom = chunk_markdown(doc, "Columns")
    assert (plain.anchor, plain.anchor_explicit) == ("plain-heading", False)
    assert (custom.anchor, custom.anchor_explicit) == ("expand", True)


def test_paths_and_nesting():
    paths = [p.heading_path for p in chunk_markdown(DOC, "Columns", max_chars=60)]
    assert ("Columns", "How to format columns") in paths
    assert ("Columns", "How to format columns", "How to format a numeric column") in paths


def test_table_stays_whole_with_its_header_row():
    pieces = chunk_markdown(DOC, "Columns", max_chars=60)
    table = next(p for p in pieces if "string" in p.text)
    assert "Command    Type" in table.text and "int" in table.text


def test_fenced_heading_does_not_split():
    pieces = chunk_markdown(DOC, "Columns", max_chars=60)
    assert any("## not a heading" in p.text for p in pieces)


def test_no_headings_gives_one_piece_with_page_title_path():
    pieces = chunk_markdown("just some text\n\nmore text\n", "Mouse")
    assert len(pieces) == 1 and pieces[0].heading_path == ("Mouse",)


def test_empty_and_whitespace_documents_give_no_pieces():
    assert chunk_markdown("", "Empty") == []
    assert chunk_markdown("\n\n   \n", "Empty") == []


def test_heading_with_empty_body_is_skipped():
    assert chunk_markdown("## Only a heading\n", "P") == []


def _wide_table(rows: int) -> str:
    head = "| filetype | format |\n|---|---|\n"
    return head + "\n".join(f"| type{i:02d} | {'x' * 90} |" for i in range(rows)) + "\n"


def test_oversized_pipe_table_is_split_by_rows_with_header_repeated():
    pieces = chunk_markdown("## Formats\n\n" + _wide_table(40), "formats", max_chars=1500)
    assert len(pieces) > 1
    for p in pieces:
        assert p.text.startswith("| filetype | format |\n|---|---|\n")
        assert len(p.text) <= 1500
    body_rows = [ln for p in pieces for ln in p.text.splitlines()[2:]]
    assert body_rows == [f"| type{i:02d} | {'x' * 90} |" for i in range(40)]


def test_small_pipe_table_stays_one_piece():
    assert len(chunk_markdown("## F\n\n" + _wide_table(3), "f", max_chars=1500)) == 1


STABLE = Path(__file__).resolve().parents[2] / "spikes" / ".cache" / "stable.tar.gz"


@pytest.mark.skipif(not STABLE.exists(), reason="docs cache not present (it is gitignored)")
def test_real_docs_give_sane_pieces():
    from ingest.clean import clean_markdown

    problems, total, max_len = [], 0, 0
    with tarfile.open(STABLE) as tf:
        for m in tf:
            parts = m.name.split("/", 2)
            ok = m.isfile() and len(parts) == 3 and parts[1] == "docs" and parts[2].endswith(".md")
            if not ok or "/" in parts[2]:
                continue
            stem = parts[2][:-3]
            body = clean_markdown(tf.extractfile(m).read().decode("utf-8", "replace")).body
            for p in chunk_markdown(body, stem):
                total += 1
                max_len = max(max_len, len(p.text))
                if not p.text.strip():
                    problems.append((stem, "blank piece"))
                if p.heading_path[0] != stem:
                    problems.append((stem, "path does not start with page"))
                if any("**" in t or "](" in t for t in p.heading_path):
                    problems.append((stem, "markup left in a heading", p.heading_path))
                if len(p.heading_path) > 1 and not p.anchor:
                    problems.append((stem, "no anchor", p.heading_path))
    assert total > 100 and problems == []
    assert max_len <= 3000, max_len
