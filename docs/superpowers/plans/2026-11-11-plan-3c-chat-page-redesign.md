# Chat Page Redesign (Plan 3c) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the chat page as a warm-paper AI chat for computer and phone, with light and dark themes, links to VisiData's site and an intro video, and a chat-style feed, without touching the API, the answer renderer or the privacy rules.

**Architecture:** Pure, node-testable logic goes in small ES modules (`theme.js`, `input.js`, additions to `view.js`); a tiny classic script in `<head>` applies a stored theme before paint; the page text comes from new config keys through `scripts/build_site.py`; `app.js` only wires the DOM. One stylesheet drives light, dark (device setting or a `data-theme` attribute) and the three page states via `body[data-state]`.

**Tech Stack:** plain HTML/CSS/ES modules (no build tools, no dependencies), Python 3.12 + pydantic config, `node --test`, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-11-11-chat-page-redesign-design.md` (visual reference: `docs/superpowers/specs/assets/chat-page-redesign-mockup.html`; where they disagree on spacing or colour, the mockup wins). **Branch:** cut `plan-3c` from `main` after Plan 3a is merged. Run JS tests as `node --test site/tests/*.test.js`.

## Global Constraints

- The content-security meta is exactly `default-src 'none'; script-src 'self'; style-src 'self'; connect-src <site.api_base_url>; img-src 'self'; base-uri 'none'; form-action 'none'` (unchanged; `tests/test_build_site.py::test_csp_meta_is_exact` must pass untouched).
- No inline scripts (except the one `application/json` config block), no inline `style=` attributes in markup, no third-party loads: no web fonts, icon fonts, analytics or embeds. System font stacks (Georgia-style serif for the greeting); icons are plain characters or inline SVG. Setting `element.style.height` from JS is allowed by this policy (CSSOM, not markup); confirm no CSP errors in the live check.
- `site/src/render.js` and `site/tests/render.test.js` are not modified. Server text goes in with `textContent`; the only `innerHTML` is the renderer's output.
- Token handling (`site/src/token.js`), the 500-character rule (`questionState`), the 90 s request timeout and `describeError` messages are unchanged.
- Theme choice is stored in `localStorage` under the key `theme` with every access in try/catch; the page works with storage blocked. The stored theme is applied before paint by an external classic script in `<head>`.
- All config text is HTML-escaped by the build; new URL keys must be `https://` with no whitespace or `"'<>` characters.
- Accessibility: text contrast at least WCAG AA (4.5:1) in both themes; visible keyboard focus; tap targets at least 44 px tall; feed `role="log"`, banner `role="status"`; honour `prefers-reduced-motion`.
- Every existing test keeps passing (at the time of writing 65 JavaScript, 491 Python, ruff clean).

## Review Focus

1. Config text or URLs with `<`, `&`, quotes, or `javascript:` in `brand`, `greeting`, `tagline`, `about_url`, `intro_video_url` → escaped or rejected at load (Task 2).
2. Stored theme that is garbage (`"evil"`, `""`, `null`) or storage that throws → falls back to the device setting, no crash, no flash of a wrong theme (Task 1).
3. Enter while composing (IME), Shift+Enter, Ctrl/Cmd+Enter, and touch devices → the right send/newline behaviour (Task 1).
4. No invite, cut-off invite, "Forget this device", first question failing → correct page state and the banner kinds still visible (Tasks 1, 4).
5. `/evals` opened with a dark device setting, and with the new stylesheet → readable, none of the chat-only rules leak into it (Task 3).

---

## File Structure

| Path | Responsibility |
|---|---|
| `site/src/theme.js` (new) | Pure theme logic: parse, resolve, toggle, storage |
| `site/src/theme-init.js` (new) | Classic head script: apply stored theme to `<html data-theme>` |
| `site/src/input.js` (new) | Pure input logic: Enter handling, box growth, scroll behaviour, touch test |
| `site/src/view.js` (modify) | Add `pageState` |
| `site/src/cards.js` (new) | DOM builders moved out of `app.js`: `el`, `link`, `buildUserBubble`, `buildAnswerCard` |
| `site/src/app.js` (modify) | Wiring only |
| `site/template.html`, `site/src/style.css` | New page structure and stylesheet |
| `app/config.py`, `config/visidata.yaml`, `scripts/build_site.py` | New config keys and build values |
| `tests/test_build_site.py`, `tests/test_config.py`, `tests/test_site_css.py` (new), `site/tests/{theme,theme-init,input,view}.test.js` | Tests |

---

### Task 1: Pure logic modules

**Files:** Create `site/src/theme.js`, `site/src/theme-init.js`, `site/src/input.js`; Modify `site/src/view.js`; Test `site/tests/theme.test.js`, `site/tests/theme-init.test.js`, `site/tests/input.test.js`, `site/tests/view.test.js`.

**Interfaces:**
- Produces (`theme.js`): `THEME_KEY = "theme"`; `parseTheme(value: unknown): "light" | "dark" | null` (only the exact strings); `effectiveTheme(stored: unknown, systemDark: boolean): "light" | "dark"`; `nextTheme(stored: unknown, systemDark: boolean): "light" | "dark"` (the opposite of the effective one); `readTheme(storage: Storage | null): "light" | "dark" | null`; `saveTheme(storage: Storage | null, theme: "light" | "dark"): boolean`.
- Produces (`input.js`): `enterAction(e: {key, shiftKey, ctrlKey, metaKey, isComposing}, isTouch: boolean): "send" | "default"`; `growHeight(scrollHeight: number, minPx: number, maxPx: number): number` (clamped); `scrollBehavior(prefersReducedMotion: boolean): "auto" | "smooth"`; `isTouchDevice(matchMedia: Function | undefined): boolean` (true when `matchMedia("(pointer: coarse)").matches`).
- Produces (`view.js`): `pageState(s: {hasToken: boolean, started: boolean}): "invite" | "welcome" | "chatting"`.
- Consumed by Task 4.

- [ ] **Step 1: Write the failing tests.**
  - `theme.test.js`: `parseTheme` accepts only `"light"`/`"dark"`, returns `null` for `"Dark"`, `""`, `"evil"`, `null`, `undefined`, `5`; `effectiveTheme("dark", false) === "dark"`, `effectiveTheme(null, true) === "dark"`, `effectiveTheme("garbage", false) === "light"`; `nextTheme(null, true) === "light"`, `nextTheme("light", true) === "dark"`; `readTheme` returns `null` for `null` storage and for a storage whose `getItem` throws; `saveTheme` returns `false` when `setItem` throws or storage is `null`, `true` and stores under `"theme"` otherwise.
  - `theme-init.test.js`: load `site/src/theme-init.js` with `node:vm` against a fake `document.documentElement.dataset` and `localStorage`: stored `"dark"` sets `dataset.theme === "dark"`; stored `"evil"` leaves it unset; a throwing `localStorage` getter leaves it unset and does not throw.
  - `input.test.js`: `enterAction` table: plain Enter on a computer → `"send"`; Shift+Enter → `"default"`; Ctrl+Enter and Meta+Enter → `"send"` even on touch; plain Enter with `isTouch` true → `"default"`; `isComposing: true` → `"default"`; any other key → `"default"`. `growHeight(10, 24, 192) === 24`, `growHeight(500, 24, 192) === 192`, `growHeight(100, 24, 192) === 100`. `scrollBehavior(true) === "auto"`, `scrollBehavior(false) === "smooth"`. `isTouchDevice(undefined) === false`, and with a fake `matchMedia` returning `{matches: true}` for `"(pointer: coarse)"` → `true`.
  - `view.test.js` (append): `pageState({hasToken:false, started:false}) === "invite"`; `{hasToken:false, started:true}` → `"invite"` (a forgotten device never shows a stale conversation); `{hasToken:true, started:false}` → `"welcome"`; `{hasToken:true, started:true}` → `"chatting"`.
- [ ] **Step 2: Run and see them fail:** `node --test site/tests/*.test.js`. Expected: the four new test files fail on missing modules and missing `pageState`.
- [ ] **Step 3: Implement** the modules to the signatures above. `theme-init.js` is a classic script (no `import`/`export`): inside try/catch read `localStorage.getItem("theme")` and, only for the exact strings `light`/`dark`, set `document.documentElement.dataset.theme`.
- [ ] **Step 4: Run all JS tests.** Expected: all pass (65 existing plus the new ones).
- [ ] **Step 5: Commit** `feat: theme, input and page-state logic with tests`.

---

### Task 2: Config keys, page structure and build

**Files:** Modify `app/config.py`, `config/visidata.yaml`, `scripts/build_site.py`, `site/template.html`; Test `tests/test_config.py`, `tests/test_build_site.py`.

**Interfaces:**
- Produces (`SiteCfg`): required `brand: str`, `greeting: str`, `tagline: str` (each non-empty); required `about_url: str`; optional `intro_video_url: str | None = None`; both URLs validated as `https://` with no whitespace or `"'<>` characters. The `intro` key is removed. Shipped values: `brand: Ask VisiData`; `greeting: Hi, ask me about VisiData`; `tagline` (one plain sentence: VisiData is a free keyboard tool for exploring data files like spreadsheets, and every answer comes from its docs, with links); `about_url: https://www.visidata.org`; `intro_video_url` left out until the owner supplies one.
- Produces (page DOM, used by Tasks 3-4): `<body class="chat" data-state="welcome">`; `<script src="src/theme-init.js">` (no `async`/`defer`/`type`) in `<head>` before `<body`; `<header class="bar">` with `.brand`, `.links.links-top` and `<button id="theme" type="button" class="btn icon">`; `<section class="hero">` with `<h1 class="greeting">`, `<p class="tagline">`, `.links.links-hero`, and `<div class="starters">` holding the first three starter buttons (`.starter`, `data-question`); `<p id="invite-missing" class="notice" hidden>`; `<section id="answers" role="log" aria-label="Conversation">`; `<div class="dock">` holding `<p id="banner" role="status" hidden>` and `<form id="ask-form">` with a visually hidden `<label for="question">`, `<textarea id="question" rows="1">` and `<span id="counter">`, `<button id="ask" type="submit" aria-label="Send">`, then `<p class="dock-note">Answers only from the VisiData docs · can make mistakes</p>`; then the evals link; `<footer>` with the licence note, `#docs-info`, privacy text and `#forget`. Both link containers use the same anchors: "What is VisiData? ↗" (`about_url`) and, only when `intro_video_url` is set, "▶ Intro video"; every external anchor has `target="_blank"` and `rel="noopener noreferrer"`. The build shows the first three starters only (`STARTERS_SHOWN = 3`).

- [ ] **Step 1: Write the failing tests.**
  - `test_config.py`: `test_new_site_keys_are_required_and_non_empty` (each missing → `ValidationError`); `test_site_urls_must_be_https_without_unsafe_characters` parametrised over `javascript:alert(1)`, `http://x.example`, `https://x.example/a b`, `https://x.example/"onclick=`, for both URL keys; `test_intro_video_url_is_optional`; `test_intro_key_is_gone` (adding `intro:` to the yaml raises, since the model is strict).
  - `test_build_site.py` (update and add): `test_page_has_config_text` asserts brand, greeting, tagline, starters, privacy notice and licence note instead of `intro`; `test_hostile_config_text_is_escaped` puts hostile text in `brand`, `greeting`, `tagline` (and keeps the title/starters/privacy cases); `test_only_three_starters_are_shown` with a config of five; `test_links_open_safely` (about link present with `rel="noopener noreferrer"` and `target="_blank"`; video link present only when set; with it unset, "Intro video" is absent); `test_theme_init_script_is_external_and_in_the_head` (a `<script src="src/theme-init.js">` with no `async`/`defer`/`type="module"`, appearing before `<body`; the only inline script is still the JSON block); `test_no_third_party_hosts_in_the_page` updated to allow exactly the API host, the `about_url` host and the `intro_video_url` host (links only); `test_evals_page_is_linked_and_files_copied` adds `theme.js`, `theme-init.js`, `input.js`, `cards.js`; `test_page_state_starts_as_welcome` (`data-state="welcome"`, body class `chat`).
- [ ] **Step 2: Run and see them fail:** `.venv/bin/pytest tests/test_config.py tests/test_build_site.py -q`. Expected: failures on the new keys and structure.
- [ ] **Step 3: Implement** `SiteCfg` and the URL validator in `app/config.py`; update `config/visidata.yaml`; in `scripts/build_site.py` add the placeholders to the `values` map (escape every value; build `links` HTML once and use it for both containers; slice starters with `STARTERS_SHOWN`); restructure `site/template.html` to the DOM above. `cards.js` is created in Task 4 (the file-copy test lists it, so add an empty placeholder module with a one-line comment now and fill it in Task 4). The old `app.js` refers to DOM ids this task removes (for example `ask-section`), so the built page is not usable between Tasks 2 and 4; that is accepted because nothing is deployed from this branch until it merges, and Task 4 restores it.
- [ ] **Step 4: Run tests and ruff:** `.venv/bin/pytest tests/test_config.py tests/test_build_site.py -q && .venv/bin/ruff check .`. Expected: pass.
- [ ] **Step 5: Commit** `feat: site config keys and chat page structure`.

---

### Task 3: Stylesheet

**Files:** Modify `site/src/style.css`; Test `tests/test_site_css.py` (new).

**Interfaces:**
- Consumes: the DOM from Task 2.
- Produces: colour tokens `--bg --card --text --muted --accent --accent-text --ok --warn --bad --line --soft`. Light tokens in `:root`; dark tokens in two places that must be identical: `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { … } }` and `:root[data-theme="dark"] { … }`. Starting palette from the mockup: light `bg #f5f1e8, card #fffdf8, line #e0d8c6, soft #e9e2d0, text #2b2723, muted #6b645a, accent #c4623c`; dark `bg #262320, card #2e2a26, line #4a443c, soft #38332d, text #ece6da, muted #a89f90, accent #d97757` (adjust to meet 4.5:1 where a pair fails). Everything after the marker comment `/* ---- chat page (scoped to body.chat) ---- */` has selectors starting with `.chat` or `body.chat`, so `/evals` (which has no `chat` class) gets only the palette and base typography above the marker.
- Behaviours in CSS: `body[data-state="welcome"]` shows the hero, hides `#invite-missing`; `"chatting"` hides the hero and shows `.links-top` on phones; `"invite"` hides starters and the dock and shows `#invite-missing`. Computer (min-width about 720 px): centred column 720 px, `.links-top` visible in the bar, `.links-hero` hidden; phone: one column, `.links-hero` visible only in `welcome`, `.links-top` visible only in `chatting`. One `.btn` recipe (32 px visual height, 16 px radius, same text size, hit area padded to 44 px); starter cards equal height in a three-column grid (one column on phone); composer about 64 px tall with 15–16 px text and a 42 px send button on computer (48 px and 32 px on phone), centred with the same width as the cards; user bubble on the right, answer card on the left; `.sr-only` for the hidden label; the `#counter` sits quietly inside the composer (muted, turning `--bad` with `.over`); the evals link and footer are small and muted; `@media (prefers-reduced-motion: reduce)` removes transitions.

- [ ] **Step 1: Write the failing tests** in `tests/test_site_css.py` (parse `site/src/style.css` with a small brace-depth parser, no dependencies): `test_dark_tokens_are_identical_in_both_places`; `test_every_token_defined_in_light_and_dark`; `test_text_contrast_meets_aa_in_both_themes` for `text/bg`, `text/card`, `muted/bg`, `muted/card`, `accent-text/accent`, `accent/bg` (link text), `ok/card`, `warn/card`, `bad/card` (each ≥ 4.5, relative-luminance formula); `test_chat_rules_are_scoped` (after the marker, every selector in every rule starts with `.chat` or `body.chat`); `test_no_external_urls_or_imports_in_css` (no `url(` with a scheme, no `@import`); `test_reduced_motion_rule_exists`.
- [ ] **Step 2: Run and see them fail:** `.venv/bin/pytest tests/test_site_css.py -q`. Expected: failures (old palette, no dark attribute block, no marker).
- [ ] **Step 3: Implement** the stylesheet to the interface above, using the mockup file as the visual reference.
- [ ] **Step 4: Run** `.venv/bin/pytest tests/test_site_css.py tests/test_build_site.py -q && .venv/bin/ruff check .`. Expected: pass. Then build the page and `/evals` (`python scripts/build_site.py page --out _site` and copy `site/public/evals.html` into it) and open both in a browser with the device set to light and then dark: the chat page layout is not yet wired (Task 4), but the palette and the `/evals` page must be readable in both.
- [ ] **Step 5: Commit** `feat: warm paper stylesheet with light and dark themes`.

---

### Task 4: Wiring

**Files:** Create `site/src/cards.js` (fill the Task 2 placeholder); Modify `site/src/app.js`.

**Interfaces:**
- Consumes: `theme.js`, `input.js`, `view.js` (`pageState`, `resultView`, `questionState`, `createBannerState`), `api.js`, `token.js`, the DOM from Task 2.
- Produces (`cards.js`): `el(tag, className?, text?)`, `link(url, text)`, `buildUserBubble(question: string): HTMLElement` (right-aligned `<div class="msg-user">`, `textContent` only), `buildAnswerCard(result, deps: {api, getToken}): HTMLElement` (an `<article class="card">` with the small status label, renderer output in `.body`, "Sources in the docs" list, "Closest pages in the docs" list on refusals, and the feedback block with its optional comment box on "No"; no "You asked:" line). Behaviour moved from today's `app.js` unchanged.

- [ ] **Step 1: Move** `el`, `link`, `feedbackBlock` and the card building from `app.js` into `cards.js` with no behaviour change; run `node --test site/tests/*.test.js` (Expected: still all pass, since these were never unit-tested) and `.venv/bin/pytest tests/test_build_site.py -q`.
- [ ] **Step 2: Wire `app.js`** to this behaviour (each point is checked in Step 4):
  - `setState()` sets `document.body.dataset.state = pageState({hasToken: !!token, started})`; `started` becomes true when the first answer card (answered or refused) is added, not when a question is sent; call `setState()` at start-up, after the first card, in `showNoInvite` and in the "Forget this device" handler (which also sets `started = false`).
  - Feed is chronological: for each question append `buildUserBubble` then `buildAnswerCard` to `#answers`, then `card.scrollIntoView({behavior: scrollBehavior(prefersReducedMotion), block: "start"})`; focus stays in the box.
  - Keydown: `enterAction(e, isTouchDevice(window.matchMedia))`; on `"send"` call `preventDefault()` and `requestSubmit()`.
  - Auto-grow: on `input` and after clearing or filling the box, set `box.style.height = "auto"` then `growHeight(box.scrollHeight, 24, 192) + "px"`.
  - Theme button `#theme`: on click compute `nextTheme(readTheme(storage), matchMedia("(prefers-color-scheme: dark)").matches)`, set `document.documentElement.dataset.theme`, call `saveTheme`, and update the button's character (🌙 when the page is light, ☀️ when dark) and `aria-label`; set the initial character at start-up from `effectiveTheme`.
  - Everything else is unchanged: banner kinds (`info`, `warn`, `error`), the cold-start banner, `#docs-info`, the starters filling the box, token loading and the invite messages.
- [ ] **Step 3: Run** `node --test site/tests/*.test.js && .venv/bin/pytest tests/test_build_site.py -q && .venv/bin/ruff check .`. Expected: pass.
- [ ] **Step 4: Check in a browser** (no model calls needed for items 1-4): build with `python scripts/build_site.py page --out _site` and serve it locally. Verify with the console open: 1) opening screen on a wide window and a phone-width window, light and dark, matches the mockup; 2) the theme button flips and the choice survives a reload; 3) no invite → notice, no dock; 4) typing: box grows to about 8 lines, Enter / Shift+Enter / Ctrl+Enter behave as in the spec; 5) no CSP errors in the console (including the `style.height` changes). Questions that call the API are covered by the live check in Task 5.
- [ ] **Step 5: Commit** `feat: wire the new chat page`.

---

### Task 5: Docs, `/evals` check and live check (owner-gated)

**Files:** Modify `docs/ops/deploy.md`, `docs/decisions/decision-log.md` (add **D25**), `CLAUDE.md`.

- [ ] **Step 1: Run the whole suite:** `node --test site/tests/*.test.js && .venv/bin/ruff check . && .venv/bin/pytest -q` (set `PGHOSTADDR` first if the database host does not resolve; see CLAUDE.md). Expected: all pass.
- [ ] **Step 2: Docs.** `deploy.md`: the new config keys and that `intro_video_url` is optional; how to preview the page and switch themes. D25: the redesign decisions (warm paper, device-setting dark mode with a remembered button, chat-style feed, link instead of an embedded video and why, `/evals` follows the device setting only) with the owner's reasons from the design document. `CLAUDE.md`: state after Plan 3c.
- [ ] **Step 3: `/evals` check.** Open the built `/evals` in light and dark; every number and label is readable; nothing from the chat layout appears.
- [ ] **Step 4: Live check (stop and ask the owner first; it sends real questions to production).** Run a local API with `DEV_CORS_ORIGIN=http://localhost:8080` and a copy of the page whose `site.api_base_url` points at it; create a throwaway invite (`token create live-check-3c`) written to a git-ignored file, never printed, and open the link for the owner. The owner asks a normal question, an off-topic one, presses Yes and No (with a comment), switches theme, and tries a phone-width window. Then verify the rows in the database, revoke the token, stop the servers and delete the file.
- [ ] **Step 5: Commit** `docs: Plan 3c decision and state`. **Stop and ask the owner** before pushing; run the neutral-wording scan on the whole diff first.
