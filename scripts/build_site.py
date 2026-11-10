"""Build the static site from config/visidata.yaml: python scripts/build_site.py page --out _site

The page text never depends on the API being awake: it is rendered into the HTML here.
"""
import argparse
import html
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import Config, load_config  # noqa: E402

SITE = ROOT / "site"


def _csp(api_base_url: str) -> str:
    return ("default-src 'none'; script-src 'self'; style-src 'self'; "
            f"connect-src {api_base_url}; img-src 'self'; base-uri 'none'; form-action 'none'")


def _json_for_script(data: dict) -> str:
    # '<' as < so no text can ever close the <script> block or start a new one.
    return json.dumps(data).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def build_page(cfg: Config, out_dir: Path) -> Path:
    """Write index.html and copy site/src/*; returns the index path."""
    esc = html.escape
    starters = "\n".join(
        f'      <button type="button" class="starter" data-question="{esc(q)}">{esc(q)}</button>'
        for q in cfg.site.starter_questions)
    values = {
        "title": esc(cfg.site.title),
        "intro": esc(cfg.site.intro.strip()),
        "starters": starters,
        "privacy_notice": esc(cfg.site.privacy_notice.strip()),
        "license_note": esc(cfg.project.license_note),
        # esc() on the CSP too: it is placed inside an attribute value
        "csp": esc(_csp(cfg.site.api_base_url)),
        "config_json": _json_for_script({
            "api_base_url": cfg.site.api_base_url,
            "max_question_chars": cfg.limits.max_question_chars,
        }),
    }
    page = (SITE / "template.html").read_text(encoding="utf-8")
    for key, value in values.items():
        page = page.replace("{{" + key + "}}", value)
    out_dir = Path(out_dir)
    (out_dir / "src").mkdir(parents=True, exist_ok=True)
    for f in (SITE / "src").iterdir():
        if f.is_file():
            shutil.copy2(f, out_dir / "src" / f.name)
    index = out_dir / "index.html"
    index.write_text(page, encoding="utf-8")
    return index


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="build_site")
    p.add_argument("--config", default=str(ROOT / "config" / "visidata.yaml"))
    sub = p.add_subparsers(dest="cmd", required=True)
    page = sub.add_parser("page")
    page.add_argument("--out", required=True)
    args = p.parse_args(argv)
    cfg = load_config(args.config)
    if args.cmd == "page":
        print(build_page(cfg, Path(args.out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
