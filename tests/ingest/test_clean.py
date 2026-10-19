import tarfile
from pathlib import Path

import pytest

from ingest.clean import clean_markdown

RAW = """---
eleventyNavigation:
  key: Combining datasets
Update: 2020-10-27
Version: VisiData 2.0.1
---


## How to join two datasets

1. Open them.

{help.commands.columns_all}

<div class="asciicast">
    <div id="player-types"></div>
    <script type="text/javascript">AsciinemaPlayer.create('x')</script>
</div>

---

## Second
text
"""


def test_extracts_front_matter_values():
    d = clean_markdown(RAW)
    assert d.last_updated == "2020-10-27"
    assert d.docs_version == "VisiData 2.0.1"


def test_removes_noise_but_keeps_content():
    body = clean_markdown(RAW).body
    assert "help.commands" not in body
    assert "AsciinemaPlayer" not in body
    assert "\n---\n" not in body
    assert "## How to join two datasets" in body
    assert "## Second" in body


def test_nested_asciicast_div_leaves_no_stray_closing_tag():
    assert "</div>" not in clean_markdown(RAW).body


def test_file_with_only_front_matter_gives_empty_body():
    d = clean_markdown("---\nUpdate: 2021-01-01\n---\n")
    assert d.body.strip() == ""
    assert d.last_updated == "2021-01-01"


def test_empty_file_and_no_front_matter():
    assert clean_markdown("").body.strip() == ""
    d = clean_markdown("## Title\ntext\n")
    assert d.last_updated is None and "## Title" in d.body


def test_list_item_placeholder_is_removed_with_its_bullet():
    # real case: docs/group.md line 43 (spike S1: placeholders also sit inside list items)
    raw = "Aggregators:\n\n- {help.options.color_aggregator}\n1. {help.commands.macro-record}\n- keep me\n"
    body = clean_markdown(raw).body
    assert "help." not in body
    assert "- \n" not in body and "1. \n" not in body
    assert "- keep me" in body and "Aggregators:" in body


def test_placeholder_inside_a_sentence_is_removed():
    body = clean_markdown("Press {help.commands.x} to go.\n").body
    assert "help." not in body and "to go." in body


def test_hero_section_with_player_is_removed():
    # real case: docs/graph.md and docs/save-restore.md
    raw = (
        "## Title\n\n"
        '<section id="hero">\n'
        '    <asciinema-player id="player" poster="npt:0:30" rows=27 src="../casts/x.cast">'
        "</asciinema-player>\n"
        '    <script type="text/javascript" src="/asciinema-player.js"></script>\n'
        "</section>\n\nreal text\n"
    )
    body = clean_markdown(raw).body
    assert "asciinema" not in body and "<section" not in body and "</section>" not in body
    assert "real text" in body and "## Title" in body


def test_line_break_tags_are_removed():
    # real case: docs/gmail.md
    body = clean_markdown("one\n\n<br/>\n\ntwo\n").body
    assert "<br" not in body and "one" in body and "two" in body


def test_markdown_table_separator_row_is_kept():
    table = "| a | b |\n|---|---|\n| 1 | 2 |\n"
    assert "|---|---|" in clean_markdown(table).body


STABLE = Path(__file__).resolve().parents[2] / "spikes" / ".cache" / "stable.tar.gz"


@pytest.mark.skipif(not STABLE.exists(), reason="docs cache not present (it is gitignored)")
def test_real_docs_have_no_noise_left_after_cleaning():
    left = []
    with tarfile.open(STABLE) as tf:
        for m in tf:
            parts = m.name.split("/", 2)
            ok = m.isfile() and len(parts) == 3 and parts[1] == "docs" and parts[2].endswith(".md")
            if not ok or "/" in parts[2]:
                continue
            body = clean_markdown(tf.extractfile(m).read().decode("utf-8", "replace")).body
            for bad in ("{help.", "<script", "<asciinema", "<section", "</div>", "<br"):
                if bad in body:
                    left.append((parts[2], bad))
    assert left == []
