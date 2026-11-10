# Chat page redesign: design

Date: 2026-11-11. Status: draft for owner approval. Follows Plan 3a (the chat page works; this changes how it looks and feels). Builds as **Plan 3c**, after Plan 3a merges.

Marking: **(owner)** = said or chosen by the owner. **(call)** = my decision, to be checked. **(builder)** = left to whoever builds it.

## Why

The live check (2026-11-11) showed the page works end to end (answer, citations, refusal, saved feedback) but looks like a plain form. Friends who have never heard of VisiData will open it on a phone or a laptop, and it has to feel like the chat apps they already use, or they will not try it. **(owner)** The first five seconds should say: this is a nice, fun chatbot, built for VisiData, answers only about VisiData, and here is where to learn what VisiData is.

## What it should look like

Visual reference: `docs/superpowers/specs/assets/chat-page-redesign-mockup.html` (open it in a browser; it has a light/dark switch). The mockup is the visual spec; where this document and the mockup disagree on spacing or colour, the mockup wins.

- **Look: "warm paper". (owner)** Cream background, soft panels, a serif greeting, a terracotta accent, calm and friendly. Not a copy of any product: no logos, no borrowed names.
- **Dark mode. (owner)** A warm charcoal-brown palette (not pure black) that feels like the same product.
  - **(call)** It starts from the device setting. A 🌙/☀️ button in the top bar flips it and remembers the choice on that device only.
- **Computer and phone. (owner)** Both are designed, not one stretched into the other.
  - Computer: a centred column about 720 px wide; the top bar has the name on the left and the links on the right; the typing box is docked at the bottom, centred, the same width as the starter cards above it, about 64 px tall with 15–16 px text and a 42 px send button.
  - Phone: one column; the top bar holds the name and the theme button; the two links sit side by side, equal width, under the starter questions.
- **Even buttons. (owner)** One button recipe everywhere: same height, same corner radius, same text size. The starter questions are cards of equal size in a grid (three across on a computer, one column on a phone).
- **Opening screen:** the greeting, one plain sentence saying what VisiData is, three starter question cards, the two links, the typing box and the line "Answers only from the VisiData docs · can make mistakes".
- **After a question:** the visitor's message on the right, the answer on the left as a clean card with numbered source links, "Was this helpful? Yes / No" under it; the opening content collapses so the conversation fills the column. **(call)** Each question stays independent (no follow-up memory; that is Plan 3b); the page shows a feed of question and answer pairs.

## Links

- A link to VisiData's own site, "What is VisiData? ↗". **(owner)** **(call)** It points to `https://www.visidata.org` (set in config as `site.about_url`).
- A link to a video explaining what VisiData is, "▶ Intro video". **(owner)** The owner thinks VisiData already has one. I could not confirm an official intro video URL (search found a 2018 case-study video by VisiData's creator and third-party videos, not one labelled "intro"). **The owner supplies the URL.** It is optional config (`site.intro_video_url`); if empty, the button is simply not shown.
- Both open in a new tab as plain links with `rel="noopener noreferrer"`. **(call)** The video is a link, never an embedded player: an embed loads third-party code on the page, which breaks the content-security rules below.

## Goals

- A newcomer understands in five seconds what this is and that it is only about VisiData, and can ask a first question with one click.
- It reads as a real chat app on both a laptop and a phone, in light and dark.
- It stays fast, free to host (GitHub Pages) and accessible.

## Non-goals

- Chat history, accounts, sidebars, settings pages, streaming answers, follow-up memory (Plan 3b), images or file upload.
- Changing the API, the answer text rules, or what is stored.
- Redesigning the `/evals` page content. (It shares the stylesheet, so it will pick up the palette; it must stay readable in both themes.)

## Anti-goals (a failure even if it technically works)

- It looks like it can answer anything. The "only about VisiData" message must be visible without scrolling.
- Anything that weakens the safety or privacy work below, even slightly, for the sake of looks.
- Pretty but unreadable: low-contrast text in either theme, or tiny tap targets.

## Constraints (do not break)

- **Content-security rules stay exactly as built:** no inline scripts or styles, no third-party loads (so **no web fonts, no icon fonts, no analytics, no embeds**; use system font stacks, with Georgia-style serif for the greeting, and inline SVG or plain characters for icons). `connect-src` stays the API only.
- **The answer renderer (`site/src/render.js`) and its hostile-input tests are not changed.** Answer text still goes through it, and nothing from the server is inserted as HTML any other way.
- **Token handling is unchanged:** the invite token after `#`, removed from the address bar, never in a URL query, never logged. The missing-invite, cut-off-invite, storage-blocked and server-asleep messages keep working and stay visible (the review found one such message being hidden; the new banner logic keeps its own kinds).
- Question box limits unchanged: empty and whitespace-only cannot be sent; 500 characters allowed, 501 not; the counter stays accurate.
- Request timeout and error messages unchanged (90 s; the "took too long" message).
- Theme choice is stored in `localStorage` wrapped in try/catch; the page must render correctly if storage is unavailable. To avoid a flash of the wrong theme, the theme is applied by a small external script loaded in `<head>` (allowed by `script-src 'self'`), not an inline one.
- All text that comes from config goes through the existing HTML escaping.
- Every existing test keeps passing; new logic that can be tested without a browser (theme choice, starter selection, banner kinds) gets unit tests first.
- Accessibility: text contrast at least WCAG AA in both themes; visible keyboard focus; buttons at least 44 px tall to tap (the visual button may be smaller if the tap area is padded); the answer area and banner keep `aria-live`; respect `prefers-reduced-motion`.

## Behaviour decisions

- **Sending:** **(call, check this)** On a computer, Enter sends and Shift+Enter adds a new line, like the chat apps people know. On a touch device Enter adds a new line and the send button sends. Today Ctrl/Cmd+Enter sends; keep that working too.
- **Typing box:** grows taller as the visitor types, up to about 8 lines, then scrolls. The "25/500" counter sits quietly inside the box area and turns warning-coloured over the limit. **(call)**
- **Starter questions:** fill the box and focus it; they do not send. (Unchanged.) The grid shows the first three starters from config. **(call)** Config currently has four; with a three-column grid, show three so rows are even (or trim config to three). **(builder)** may choose which, keeping the grid symmetrical.
- **Cold start:** the "waking up, up to 30 seconds" banner stays, restyled to fit.
- **Footer:** the licence note, docs version line, privacy text and "Forget this device" link stay on the page (below the conversation, small), restyled. The `/evals` link ("How well does this work?") stays visible but quiet.

## Settled after a builder check (all **(call)**: the owner reads and overrides)

- **Text comes from config.** Add `site.brand` (top bar, "Ask VisiData"), `site.greeting` ("Hi, ask me about VisiData") and `site.tagline` (one plain sentence about what VisiData is and that answers come only from its docs; the same text on computer and phone). `site.title` stays the browser-tab title. `site.intro` is dropped from the opening screen (the tagline replaces it) and may move to the footer. Update `tests/test_build_site.py` to expect the new keys, and keep the escaping test for hostile config text.
- **`/evals` and dark mode.** `/evals` follows only the device setting (CSS `prefers-color-scheme`); it has no theme script and its content-security meta gets no `script-src`. So the theme CSS has two triggers: the device setting, and a `data-theme` attribute set on the chat page by the head script. A visitor who chose light on the chat page may see a dark `/evals` if their device is dark; that is accepted.
- **After the first question.** The greeting, tagline and starter cards collapse. The two links stay reachable: on a computer they are already in the top bar; on a phone they appear as a thin row directly under the top bar once the conversation starts. The starters do not come back until the page is reloaded. Nothing about this is stored.
- **Feed order.** Chronological, chat-style: newest at the bottom; after each answer the newest card scrolls into view (smooth, or instant under `prefers-reduced-motion`) and focus stays in the typing box. The current "newest at the top" behaviour goes away.
- **No invite.** The greeting, tagline and links still show; the typing box is replaced by the existing invite message; the starter cards are hidden. Cut-off links and "Forget this device" use the same layout with their own message.
- **Answer card keeps everything it has today** except the "You asked:" line, which the visitor's right-hand bubble replaces: the status label ("Answered from the docs" / "I couldn't find this in the docs", shown small and quiet), the "Closest pages in the docs" list on refusals, and the optional comment box that opens on "No". Nothing stored or sent to the API changes.
- **Tests.** The acceptance line is "every existing test still passes" (at the time of writing 65 JavaScript and 491 Python, plus ruff clean), not a fixed count.

## Left to the builder

Exact colours (starting from the mockup palette, checking contrast), spacing scale, the SVG icons, animation (a short fade is fine; none is fine), how to structure the CSS (keep it one stylesheet), the build-script changes for the two new optional config keys, and how `/evals` adopts the palette.

## How we will know it is right

- The owner opens it on their own computer and phone, in light and dark, and says it looks like a proper chat app. **(owner decides)**
- The unit tests above pass; the full suite and ruff are clean; the built page's content-security meta is unchanged apart from nothing added.
- A fresh whole-branch review reads the diff with the focus: the renderer is untouched, no third-party request, token never exposed, banner messages not hidden.
- A second live check with a throwaway invite (the owner opens the link): ask, refuse, feedback, dark mode, a phone.

## Size

A project with a written design. Estimate: a small plan of about four tasks (theme and banner logic with tests; the new page structure and stylesheet; config keys and build; `/evals` palette plus live check).
