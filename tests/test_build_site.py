import html as htmllib
import importlib.util
import re
from pathlib import Path

import pytest

from app.config import load_config

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "visidata.yaml"


def load_builder():
    spec = importlib.util.spec_from_file_location("build_site", ROOT / "scripts" / "build_site.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    index = load_builder().build_page(load_config(CONFIG), out)
    return out, index, index.read_text(encoding="utf-8")


def test_page_has_config_text(built):
    _, _, html = built
    cfg = load_config(CONFIG)
    text = htmllib.unescape(html)  # browsers decode &#x27; and friends, so compare decoded text
    assert cfg.site.title in text
    for t in (cfg.site.brand, cfg.site.greeting, cfg.site.tagline):
        assert t in text
    for q in cfg.site.starter_questions[:3]:  # the page shows the first three
        assert q in text
    assert cfg.site.privacy_notice.strip() in text
    assert cfg.project.license_note in text


def test_no_unfilled_placeholders(built):
    assert "{{" not in built[2] and "}}" not in built[2]


def test_hostile_config_text_is_escaped(tmp_path):
    cfg = load_config(CONFIG)
    cfg.site.title = "a <b>&"
    cfg.site.brand = "<i>brand</i>"
    cfg.site.greeting = '<img src=x onerror="1"> & "quotes"'
    cfg.site.tagline = "<u>tag</u>"
    cfg.site.starter_questions = ["x <script>alert(1)</script>?"]
    cfg.site.privacy_notice = "p </script><script>evil()</script>"
    html = load_builder().build_page(cfg, tmp_path).read_text(encoding="utf-8")
    assert "a &lt;b&gt;&amp;" in html
    assert "<i>brand" not in html and "<u>tag" not in html
    assert "<img" not in html and "<script>alert" not in html and "<script>evil" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_csp_meta_is_exact(built):
    cfg = load_config(CONFIG)
    expect = ("default-src 'none'; script-src 'self'; style-src 'self'; "
              f"connect-src {cfg.site.api_base_url}; img-src 'self'; base-uri 'none'; "
              "form-action 'none'")
    m = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]*)"', built[2])
    assert m and htmllib.unescape(m.group(1)) == expect


def test_every_script_is_external_except_one_json_block(built):
    tags = re.findall(r"<script\b([^>]*)>", built[2])
    inline = [t for t in tags if "src=" not in t]
    assert len(inline) == 1 and 'type="application/json"' in inline[0]
    assert tags and all(("src=" in t) or t is inline[0] for t in tags)


def test_json_block_cannot_close_the_script_early(tmp_path):
    cfg = load_config(CONFIG)
    cfg.site.api_base_url = "https://api.example/</script><script>evil()</script>"
    html = load_builder().build_page(cfg, tmp_path).read_text(encoding="utf-8")
    assert "</script><script>evil" not in html


def test_evals_page_is_linked_and_files_copied(built):
    out, _, html = built
    assert 'href="evals.html"' in html
    for name in ("render.js", "token.js", "api.js", "view.js", "app.js", "style.css", "theme.js",
                 "theme-init.js", "input.js", "cards.js"):
        assert (out / "src" / name).is_file(), name


def test_page_config_carries_the_limit_and_api_base(built):
    import json
    m = re.search(r'<script type="application/json" id="page-config">(.*?)</script>', built[2],
                  re.DOTALL)
    data = json.loads(m.group(1))
    cfg = load_config(CONFIG)
    assert data["api_base_url"] == cfg.site.api_base_url
    assert data["max_question_chars"] == cfg.limits.max_question_chars


def test_no_third_party_hosts_in_the_page(built):
    cfg = load_config(CONFIG)
    hosts = set(re.findall(r"https?://([^/\"'\s<>;]+)", built[2]))
    allowed = {cfg.site.api_base_url.split("//")[1], cfg.site.about_url.split("//")[1].split("/")[0]}
    if cfg.site.intro_video_url:
        allowed.add(cfg.site.intro_video_url.split("//")[1].split("/")[0])
    assert hosts <= allowed, hosts


def test_only_three_starters_are_shown(tmp_path):
    cfg = load_config(CONFIG)
    cfg.site.starter_questions = [f"Question number {i}?" for i in range(5)]
    html = load_builder().build_page(cfg, tmp_path).read_text(encoding="utf-8")
    assert html.count('class="starter"') == 3
    assert "Question number 2?" in html and "Question number 3?" not in html


def test_links_open_safely(tmp_path):
    cfg = load_config(CONFIG)
    cfg.site.intro_video_url = None
    html = load_builder().build_page(cfg, tmp_path / "a").read_text(encoding="utf-8")
    assert "Intro video" not in html
    about = re.findall(r'<a [^>]*href="%s"[^>]*>' % re.escape(cfg.site.about_url), html)
    assert len(about) == 2  # top bar and hero
    for tag in about:
        assert 'rel="noopener noreferrer"' in tag and 'target="_blank"' in tag
    cfg.site.intro_video_url = "https://video.example/watch"
    html = load_builder().build_page(cfg, tmp_path / "b").read_text(encoding="utf-8")
    vid = re.findall(r'<a [^>]*href="https://video\.example/watch"[^>]*>', html)
    assert len(vid) == 2
    for tag in vid:
        assert 'rel="noopener noreferrer"' in tag and 'target="_blank"' in tag
    assert html.count(">▶ Intro video</a>") == 2  # top bar and hero (the JSON config has the text too)


def test_theme_init_script_is_external_and_in_the_head(built):
    html = built[2]
    m = re.search(r'<script\b([^>]*)\bsrc="src/theme-init\.js"([^>]*)>', html)
    assert m, "theme-init.js must be loaded"
    attrs = m.group(1) + m.group(2)
    assert not re.search(r"\b(async|defer|type)\b", attrs)
    assert m.start() < html.index("<body")
    inline = [t for t in re.findall(r"<script\b([^>]*)>", html) if "src=" not in t]
    assert len(inline) == 1 and 'type="application/json"' in inline[0]


def test_page_state_starts_as_welcome(built):
    assert re.search(r'<body class="chat" data-state="welcome">', built[2])


def test_evals_subcommand_writes_the_page_from_files(tmp_path):
    import json
    run = {"meta": {"split": "dev", "ref": "stable", "n_questions": 1},
           "retrieval": {"hybrid": [{"id": "r-001", "mode": "hybrid", "answerable": True,
                                     "hit": True, "top_ids": [], "top_scores": [], "error": None}]},
           "answers": {"hybrid": [{"id": "r-001", "mode": "hybrid", "answerable": True,
                                   "status": "answered", "abstained_correctly": None,
                                   "invalid_citations": 0, "llm_calls": 1, "neurons": 1.0,
                                   "seconds": 1.0, "cited_ids": ["sort:1"], "cited_gold": True,
                                   "error": None, "question": "q", "text": "Use <b>.", "top_score": 0.03}]}}
    (tmp_path / "run.json").write_text(json.dumps(run), encoding="utf-8")
    (tmp_path / "labels.jsonl").write_text('{"question_id": "r-001", "correct": true}\n',
                                           encoding="utf-8")
    (tmp_path / "verdicts.json").write_text("[]", encoding="utf-8")
    (tmp_path / "q.jsonl").write_text(
        json.dumps({"id": "r-001", "question": "How do I sort?", "answerable": True,
                    "gold_page": "sort", "source": "real", "split": "dev"}) + "\n",
        encoding="utf-8")
    from ingest.models import Piece
    pieces = {"sort:1": Piece("sort:1", "sort", "Sort rows", "https://www.visidata.org/docs/sort/",
                              "", ("Sort rows",), "t", "stable", None, None)}
    out = tmp_path / "evals.html"
    load_builder().build_evals(
        load_config(CONFIG), [tmp_path / "run.json"], tmp_path / "labels.jsonl",
        tmp_path / "verdicts.json", None, [tmp_path / "q.jsonl"], pieces, out)
    page = out.read_text(encoding="utf-8")
    assert "How do I sort?" in page and "Use &lt;b&gt;." in page and "1/1" in page


def test_page_config_carries_the_start_links(tmp_path):
    import json
    cfg = load_config(CONFIG)
    cfg.site.intro_video_url = None
    cfg.site.getting_started_url = None
    page = load_builder().build_page(cfg, tmp_path / "a").read_text(encoding="utf-8")
    data = json.loads(re.search(r'id="page-config">(.*?)</script>', page, re.DOTALL).group(1))
    assert [x["url"] for x in data["start_links"]] == [cfg.site.about_url]
    cfg = load_config(CONFIG)
    page = load_builder().build_page(cfg, tmp_path / "b").read_text(encoding="utf-8")
    data = json.loads(re.search(r'id="page-config">(.*?)</script>', page, re.DOTALL).group(1))
    assert [x["url"] for x in data["start_links"]] == [
        cfg.site.about_url, cfg.site.intro_video_url, cfg.site.getting_started_url]
    assert all(x["url"].startswith("https://") and x["text"] for x in data["start_links"])
