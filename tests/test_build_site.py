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
    assert cfg.site.intro.strip() in text
    for q in cfg.site.starter_questions:
        assert q in text
    assert cfg.site.privacy_notice.strip() in text
    assert cfg.project.license_note in text


def test_no_unfilled_placeholders(built):
    assert "{{" not in built[2] and "}}" not in built[2]


def test_hostile_config_text_is_escaped(tmp_path):
    cfg = load_config(CONFIG)
    cfg.site.title = "a <b>&"
    cfg.site.intro = '<img src=x onerror="1"> & "quotes"'
    cfg.site.starter_questions = ["x <script>alert(1)</script>?"]
    cfg.site.privacy_notice = "p </script><script>evil()</script>"
    html = load_builder().build_page(cfg, tmp_path).read_text(encoding="utf-8")
    assert "a &lt;b&gt;&amp;" in html
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
    for name in ("render.js", "token.js", "api.js", "view.js", "app.js", "style.css"):
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
    assert hosts <= {cfg.site.api_base_url.split("//")[1]}, hosts
