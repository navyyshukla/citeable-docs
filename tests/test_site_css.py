"""Checks on site/src/style.css with a tiny brace-depth parser (no dependencies)."""
import re
from pathlib import Path

import pytest

CSS = (Path(__file__).resolve().parents[1] / "site" / "src" / "style.css").read_text("utf-8")
MARKER = "/* ---- chat page (scoped to body.chat) ---- */"
TOKENS = ["bg", "card", "text", "muted", "accent", "accent-text", "ok", "warn", "bad", "line", "soft"]
DARK_MEDIA = '@media (prefers-color-scheme: dark)'


def strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)


def blocks(css: str):
    """Yield (prelude, body) for each top-level { } block, honouring nesting."""
    css = strip_comments(css)
    depth, start, prelude_start = 0, 0, 0
    for i, ch in enumerate(css):
        if ch == "{":
            if depth == 0:
                prelude, start = css[prelude_start:i].strip(), i + 1
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                yield prelude, css[start:i]
                prelude_start = i + 1
        elif ch == ";" and depth == 0:
            prelude_start = i + 1


def declarations(body: str) -> dict[str, str]:
    return {k.strip(): v.strip() for k, v in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", body)}


def light_tokens() -> dict[str, str]:
    for prelude, body in blocks(CSS):
        if prelude == ":root":
            return declarations(body)
    raise AssertionError("no :root block")


def dark_tokens_media() -> dict[str, str]:
    for prelude, body in blocks(CSS):
        if prelude == DARK_MEDIA:
            for inner_prelude, inner_body in blocks(body):
                if inner_prelude == ':root:not([data-theme="light"])':
                    return declarations(inner_body)
    raise AssertionError("no dark block inside the prefers-color-scheme media query")


def dark_tokens_attr() -> dict[str, str]:
    for prelude, body in blocks(CSS):
        if prelude == ':root[data-theme="dark"]':
            return declarations(body)
    raise AssertionError('no :root[data-theme="dark"] block')


def lum(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_dark_tokens_are_identical_in_both_places():
    assert dark_tokens_media() == dark_tokens_attr()


def test_every_token_defined_in_light_and_dark():
    for name, tokens in (("light", light_tokens()), ("dark-media", dark_tokens_media()),
                         ("dark-attr", dark_tokens_attr())):
        missing = [t for t in TOKENS if f"--{t}" not in tokens]
        assert not missing, (name, missing)


PAIRS = [("text", "bg"), ("text", "card"), ("muted", "bg"), ("muted", "card"),
         ("accent-text", "accent"), ("accent", "bg"), ("ok", "card"), ("warn", "card"),
         ("bad", "card")]


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("fg,bg", PAIRS)
def test_text_contrast_meets_aa_in_both_themes(theme, fg, bg):
    tokens = light_tokens() if theme == "light" else dark_tokens_attr()
    ratio = contrast(tokens[f"--{fg}"], tokens[f"--{bg}"])
    assert ratio >= 4.5, f"{theme}: {fg} on {bg} is {ratio:.2f}"


def test_chat_rules_are_scoped():
    assert MARKER in CSS, "marker comment missing"
    after = CSS.split(MARKER, 1)[1]
    seen = 0
    for prelude, body in blocks(after):
        rules = ([(p, b) for p, b in blocks(body)] if prelude.startswith("@media") else [(prelude, body)])
        for sel, _ in rules:
            if sel.startswith("@"):
                continue
            for one in (s.strip() for s in sel.split(",")):
                seen += 1
                assert one.startswith((".chat", "body.chat")), one
    assert seen > 10, "expected many chat rules after the marker"


def test_no_external_urls_or_imports_in_css():
    css = strip_comments(CSS)
    assert "@import" not in css
    assert not re.search(r"url\(\s*['\"]?\s*[a-zA-Z][a-zA-Z0-9+.-]*:", css)
    assert "//" not in re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)


def test_reduced_motion_rule_exists():
    css = strip_comments(CSS)
    assert "@media (prefers-reduced-motion: reduce)" in css
    m = re.search(r"@media \(prefers-reduced-motion: reduce\)\s*\{(.*)", css, re.DOTALL)
    assert "transition" in m.group(1) or "animation" in m.group(1)
