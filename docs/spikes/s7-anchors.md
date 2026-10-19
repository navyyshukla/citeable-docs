# S7: do our citation anchors exist on the published pages? (2026-10-19, Task 9)

Script `spikes/s7_anchors.py`: builds pieces from the cached `stable` docs, fetches each published page (29 pages with at least one anchor, one GET each, public pages only) and looks for `id="<anchor>"` in the HTML.

## Result
| Anchor kind | Found on the site | Missing |
|---|---|---|
| Heading written with its own id, `{#expand}` (32 pieces) | **32** | 0 |
| Generated from the heading text (`#how-to-hide-columns`, 173 pieces) | **0** | **173** |

The published site puts no `id` on ordinary headings. Only headings that carry an explicit `{#id}` in the Markdown get one. A link to a generated anchor still loads the page, but at the top, so the reader has to find the section.

## What we did (ruling in the Task 9 ledger)
`Piece.citation_url` adds `#anchor` only for explicit ids; every other piece cites its page URL. The generated slug is still stored (`anchor`), flagged with `anchor_explicit=False`.

## Options to improve this later (owner decision, not made)
| Option | For | Against |
|---|---|---|
| A. Page URL only (now) | Always works, nothing to maintain | Reader must find the section; the heading path is shown in the citation to help |
| B. Text fragment link `page/#:~:text=How%20to%20hide%20columns` | Scrolls to and highlights the heading, no ids needed | Newer browsers only (Chrome, Edge, Safari 16.1+, Firefox 131+); falls back to the page top elsewhere; heading text with odd characters needs care |
| C. Ask VisiData to add heading ids | Fixes it at the source | Outside our control and outreach needs the owner's approval; not planned |

Recommendation: A now, test B in Task 13 or Plan 2 where citations are built. This is an estimate of browser support, not tested here.

## Caveats
- One snapshot of the site on 2026-10-19. The site is built from something newer than `stable` (S1), so some `stable` headings may not exist there at all.
- Not checked: pages without any anchor, and whether the page `url` pattern is right for every page (only checked via the anchor fetches returning 200 for the 29 pages).
