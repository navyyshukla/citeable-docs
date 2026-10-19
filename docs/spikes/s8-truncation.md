# S8: does the embedding model truncate long input? (2026-10-19)

Script `spikes/s8_truncation.py`: embeds `S[:n]` and `S[:n+500]` (real doc text) for growing `n` on `@cf/baai/bge-base-en-v1.5`. If the extra 500 characters change nothing, the model ignored them.

| characters in | cosine (text, text + 500 more characters) |
|---|---|
| 500 / 1,000 / 1,500 | 0.946 / 0.987 / 0.983 (extra text matters) |
| 2,000 | 0.9996 (almost ignored) |
| 2,500 and above | 1.00000 (ignored completely) |

## Result
The model **silently cuts input at about 2,100 to 2,300 characters** (its 512-token window). Nothing in the response says so.

## What it means for us
- Only **1 of 229 pieces** has more than 2,000 characters of search text: `index:3`, a list of links (2,804). Keyword search still sees all of it. Negligible today.
- **Task 11/12 rule:** embed `search_text[:2000]` explicitly, so the cut is ours and visible, not silent. If a future docs version has many long pieces, lower `max_piece_chars` in `config/visidata.yaml`.

## Caveats
- One text mix; the cut is in tokens, so it moves a little with the text (symbols and code use more tokens per character). Treat 2,000 characters as the safe line, not an exact limit.
