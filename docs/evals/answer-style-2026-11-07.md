# Answer style rounds (2026-11-07)

Dev set, 28 questions (19 answerable, 9 not), hybrid search, user chain (Cloudflare gemma, thinking off). One run per round,
so one question moving is noise. Raw results are git-ignored (`evals/results/answers-*.json`); the decision is D21.

| Round | Change | Neurons | Avg chars | Abstained correctly | Answerable but abstained | Invalid citations |
|---|---|---|---|---|---|---|
| original | old 5-rule prompt | 330 | 192 | 9/9 | 2 | 0 |
| r1 | newcomer rules (plain sentences, simplest first, no example data, explain terms) | 381 | 247 | 9/9 | 2 | 0 |
| r2 | + prefixed keys as separate steps | 387 | 207 | 9/9 | 3 (r-005) | 0 |
| r3 | prefix rule limited to `g`/`z`; chords stay whole | 396 | 210 | 9/9 | 2 | 0 |
| r4 (merged) | copy key sequences exactly; start with user's words | 406 | 242 | 9/9 | 3 (r-004) | 0 |

## What the owner's reading found
- Fixed: docs example leaking into the answer (d-003), hardest method first (d-004, mostly), bare fragment (k-003), jargon-first opening (d-005).
- Side effect found only by reading, not by tests: r2 turned `Shift+F` into "press Shift, then F" and `gs gzd` into five separate keys.
- Not fixable by prompt: d-001 (docs error, `[` and `]` swapped on the docs' sort page; source code `visidata/sort.py` has `[` = ascending), k-004 (vague docs excerpt), d-005 (the task itself is editing a JSON file).
- Traded away: the r-008 "press z, then Ctrl+S" wording.

## Hand grades and the judge
- Original answers: 15 correct, 2 wrong (d-001, k-004). New answers (r4): 14 correct, 2 wrong (same two); r-004 abstained so it was not graded.
- Gemini judge on the original answers: said correct for all 17; precision 0.88, recall 1.00, TN 0. It has never said "wrong", so it is UNCALIBRATED. The judge was not re-run on r4.
