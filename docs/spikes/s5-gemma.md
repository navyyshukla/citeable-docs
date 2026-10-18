# S5: Cloudflare gemma-4 quality check (2026-10-19, 05:21 IST)

Script `spikes/s5_gemma_check.py`; model `@cf/google/gemma-4-26b-a4b-it`; public `stable` docs only; top-3 sections retrieved with the S2 search (symbol-aware plus exact key path); `max_tokens` 1500; hard budget 1,500 neurons.

## Result
- **11/11 passed the automatic check**: 9 answerable questions cited a section from the right page; 2 unanswerable questions (collaboration server, Enterprise price) returned exactly `NOT_IN_DOCS`.
- **No empty answers**, all HTTP 200, `finish_reason` = stop on every call.
- **Cost: 216 neurons for 11 questions, about 20 per question** (range 10-41). That is about 500 questions per 10k neurons, better than the 282 estimate. Prompts were 300-1,100 tokens (not the 3,000 assumed), so treat 500 as optimistic; re-measure with 5 pieces.
- Latency 2-22 s per answer.

## Read by eye (not just the check)
- Spot-read answers matched the cited sections (`&` join-chooser and append, `-` to hide, `=` derived column, `random-rows`, `vd -p fn.vdj`). I did not verify every step against the docs.
- `what does ! do?` answered with two meanings (key column, and graph axis). Correct for the docs but not one clear answer; a product prompt may need to say "list each meaning separately".

## Caveats (do not overstate)
- **Tiny set, 11 questions, same 9 queries used to tune retrieval in S2.** The citation check proves the answer pointed at the right page, not that every claim is correct. Not a quality score.
- **Reasoning tokens are hidden in `completion_tokens`**: short answers used 200-1,300 tokens, and "how do I join two sheets?" used 1,292 of the 1,500 allowed. With a smaller cap this question would likely come back cut off or empty. **The adapter needs `max_tokens` of about 3,000 and must treat an empty or length-stopped answer as an error (fall back).**
- Not tested: prompt-injection text in sources, long questions, multi-turn.
