# S2: can search find single-key commands like `&`?

Run 2026-10-18 with `spikes/s2_symbols.py` on the cached `stable` docs (218 sections, cut by heading). A "hit" means the right page is in the top 3 results.

## Results (9 queries)

| Search | hit@3 | hit@5 |
|---|---|---|
| word-only (letters and digits) | 8/9 | 8/9 |
| symbol-aware (symbols are tokens too) | 7/9 | 8/9 |
| symbol-aware + exact key path | **9/9** | **9/9** |

The four symbol queries are where the methods differ:

| Query | word-only | symbol-aware | + exact key path |
|---|---|---|---|
| what does & do? | MISS | HIT | HIT (`join:2`, `join:1` first) |
| what does ! do? | HIT (luck) | MISS | HIT (`columns:1` first) |
| what does ( do? | HIT (luck) | MISS | HIT (`columns:15` first) |
| derived column with = | HIT | HIT | HIT |

## How to read this honestly
- **word-only hits on `!` and `(` are luck.** The tokenizer drops the symbol, so the query becomes "what does do" and returns the same three sections for `&`, `!` and `(` (`README:1`, `formats:9`, `columns:12`). `columns:12` happens to be a section of the right page. Nothing was found on purpose. On `&`, the headline case, word-only misses.
- **Plain symbol-aware search is not enough.** Symbols like `!` and `(` appear in many sections, so they carry little weight next to "what/does/do". It fixed `&` but broke `!` and `(`.
- **The decision rule says it fails:** symbol-aware must be at least as good as word-only on every query and reach 5/6. It scored 4/6 on the original six. So per the plan we add an exact path for backticked keys.
- **The exact path** looks for the symbol in backticks. A table row that starts with the key (a definition such as ``!  pins the current column ... as a key column``) counts three times, so definitions beat mere mentions.
  - `&` appears in backticks in only 2 sections (both `join`).
  - `!` appears in 6 sections: `columns:1` defines it; `graph`, `rows`, `group` and `join` only use it. Count alone ranked `graph` first and missed `columns`. The definition-row boost fixed that.
  - `(` appears in 9 sections; `=` in 3.

## Caveats (do not overstate)
- **Small and partly tuned.** Nine queries, only four with symbols. I designed the exact path and the definition-row boost after seeing the misses on the first six, so those results are not independent. The three extra queries (random subset of rows, append two datasets, save and replay a session) were added after, each checked against a real heading, and none of the methods was tuned on them.
- **Lenient metric.** "Right page in top 3" counts any section of that page, not the exact answer section.
- **Ground truth** for the first six queries came from the plan, grounded in `join.md` and `columns.md`. `(` going to `columns` is plausible (it expands a column) but I did not verify the sentence.
- Not tested: queries with two symbols, symbols inside words (`g[`, `gj`), or a symbol that appears in no backticks.

## Decision
- Task 12 ships the **symbol-aware tokenizer plus an exact backticked-key path** (with the definition-row boost). Neither alone is enough.
- A note is added to Task 12 in the plan. The prototype is `key_path()` in `spikes/s2_symbols.py`. It must be written as its own step with unit tests before it ships.
- The exact path returns candidates; fusing with the meaning (embedding) search and letting the model read the top 5 pieces is what ranks them in the product. Not measured here.
