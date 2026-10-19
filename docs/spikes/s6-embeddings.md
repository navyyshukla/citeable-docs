# S6: meaning search vs keyword vs hybrid on messy questions (2026-10-19)

Script `spikes/s6_embed.py`; `@cf/baai/bge-base-en-v1.5` on all 218 `stable` pieces (first 1,500 characters each); 13 questions (the 9 from S2 plus the 4 messy ones from S5c); hit = the right PAGE appears in the top 5. Hybrid = rank fusion (RRF) of keyword (with exact key path) and meaning.

| Search | hit@5 (of 13) |
|---|---|
| keyword (symbol-aware + exact key path) | 11 |
| meaning only | 12 |
| **hybrid (fused)** | **13** |

## Where they differ
- **Keyword missed the two hardest messy questions** (rambling customers/orders; "how 2 hide colum pls"). Meaning found the right pieces for both (`join:1`; `columns:3`).
- **Meaning missed `what does & do?`** (symbol questions are keyword's strength) and, on "key thing with ! ... undo", found the right page only by luck (`columns:4`); the key-column piece `columns:1` came from keyword. Hybrid had it.
- Each method covers the other's blind spot, which is the case for hybrid, as the spec's four-mode plan expected.

## Caveats (do not overstate)
- **13 queries, 4 of them messy, and the S2 queries were used to tune keyword.** A direction, not a score.
- **Page-level hit is lenient.** Piece-level: meaning found the gold piece for 3 of the 4 messy questions; hybrid for all 4.
- **In hybrid, junk still sits in the top 5** (e.g. `customize:3`, `usage:2`), so gemma sees noise. Gemma tolerated this in S5; a re-ranking cut-off could be tested.
- **Neuron cost:** the embedding response has no `usage` field, so the script counted 0. The Cloudflare dashboard (screenshot, owner, 2026-10-19) shows **278.62 neurons** for `bge-base-en-v1.5` (218 pieces plus 13 query calls). Embedding all pieces is a one-time cost per ingest; each question adds one small call.
- Pieces were truncated to 1,500 characters; long pieces lose their tails. Real chunking is Task 8.
- No answer-quality check here; retrieval only.
