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


def test_animations_move_only_transform_and_opacity():
    """Smooth on a phone: only compositor-friendly properties are animated."""
    css = strip_comments(CSS)
    frames = re.findall(r"@keyframes\s+[\w-]+\s*\{(.*?\})\s*\}", css, re.DOTALL)
    assert frames, "expected at least one @keyframes (the thinking dots)"
    for body in frames:
        props = set(re.findall(r"([\w-]+)\s*:", re.sub(r"\{[^}]*\}", lambda m: m.group(0), body)))
        used = {p for p in props if p not in {"from", "to"} and not p.endswith("%")}
        assert used <= {"transform", "opacity"}, used


def chat_rules():
    """(selector, declarations, in_phone_media) for every rule after the marker."""
    after = CSS.split(MARKER, 1)[1]
    for prelude, body in blocks(after):
        if prelude.startswith("@media"):
            phone = "max-width" in prelude
            for sel, inner in blocks(body):
                yield sel, inner, phone
        elif not prelude.startswith("@"):
            yield prelude, body, False


def rules_for(fragment):
    return [(sel, body, phone) for sel, body, phone in chat_rules() if fragment in sel]


def test_hero_is_hidden_only_while_chatting():
    """No invite, a cut-off link and Forget this device all keep the greeting and links."""
    hiding = [sel for sel, body, _ in rules_for(".hero") if re.search(r"display\s*:\s*none", body)
              and ".links-hero" not in sel]
    assert hiding, "expected a rule that hides the hero once chatting"
    assert all('[data-state="chatting"]' in sel for sel in hiding), hiding
    assert not any(re.search(r"display\s*:\s*none", b) for sel, b, _ in chat_rules()
                   if sel.strip() == ".chat .hero"), "the hero must not be hidden by default"


def test_phone_links_show_on_the_welcome_and_invite_screens():
    shown = [sel for sel, body, phone in rules_for(".links-hero") if phone
             and re.search(r"display\s*:\s*flex", body)]
    assert shown and all('[data-state="chatting"]' in sel and ":not(" in sel for sel in shown), shown


def test_small_buttons_have_a_44px_tap_area():
    for frag in (".chat #ask::after", ".chat .feedback button::after"):
        found = [b for sel, b, _ in chat_rules() if frag in sel]
        assert found and re.search(r"inset\s*:\s*-[56]px", found[0]), frag


def test_phone_bar_wraps_so_the_links_get_their_own_row():
    bar = [b for sel, b, phone in rules_for(".bar") if phone and sel.strip() == ".chat .bar"]
    assert bar and re.search(r"flex-wrap\s*:\s*wrap", bar[0])
    row = [b for sel, b, phone in rules_for(".links-top") if phone and "chatting" in sel]
    assert row and re.search(r"flex-basis\s*:\s*100%", row[0])
    assert re.search(r"order\s*:\s*3", row[0]), "the name and the theme button must share the first row"


def test_card_paragraphs_wrap_long_words():
    """Card text can now be model text: a long unbroken word must not widen the page."""
    found = [b for sel, b, _ in chat_rules() if sel.strip() == ".chat .card-info p"]
    assert found and re.search(r"overflow-wrap\s*:\s*anywhere", found[0])
