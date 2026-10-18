# S3: how many past questions have a clear maintainer answer?

Run 2026-10-18 on `saulpw/visidata` with a fine-grained, public read-only token. Candidate lists with third-party text stay in `spikes/.cache/` (gitignored). This file has counts only.

## Result: viable. There is plenty of material.

### 1. The plan's script (`spikes/s3_questions.py`): 11, and that undercounts
- Scanned 428 closed issues that have comments.
- 12 had a question-like title; **11 had a maintainer reply** (2023: 3, 2024: 5, 2025: 2, 2026: 1).
- Under the plan's literal rule this is the 10 to 24 band ("lean on doc-based and agent-made questions").
- **But the scan is shallow.** It stops after 10 pages, which only reaches back to 2023-08-25, and more pages exist. It also filters on a title regex, so it misses questions with other titles. The repo has a `question` label that the script never used.

### 2. Extension (`spikes/s3_extended.py`): the real count

| Source | Count |
|---|---|
| Closed issues labelled `question` | 123 (122 with at least one comment) |
| ...with a maintainer reply | **115** (2018: 1, 2019: 8, 2020: 28, 2021: 22, 2022: 20, 2023: 12, 2024: 17, 2025: 4, 2026: 3) |
| Discussions in total | 435 |
| Q&A discussions with a marked answer | **164 of 283** (2021: 21, 2022: 34, 2023: 43, 2024: 34, 2025: 27, 2026: 5) |

- Since 2023: **36** labelled issues with a maintainer reply and **109** answered Q&A discussions.
- GraphQL works with the fine-grained public read-only token, so no wider permission is needed.

### Decision rule
At least 25 question-like items with a maintainer answer means the "real questions" part of the eval set is viable, target about 40. **Viable.** The plan's own script said otherwise because of how it searches, not because the material is missing. I recorded the conflict so the choice of method is visible.

## Caveats (do not overstate)
- **Counts, not quality.** I did not read the replies. "Maintainer replied" is not "a clear, correct answer". "Marked answer" in Discussions can be from any member of the community.
- **Staleness.** Many items are from 2019 to 2022. VisiData v3 changed things (guides, menus), so an old answer can contradict the current `stable` docs. Plan to use items from 2023 onward first and check every answer against `stable` before it becomes ground truth.
- **Many of these questions may not be answerable from the docs** (feature requests, bugs, install problems). The eval set needs a manual pass to keep only those the docs can answer. That ratio is unmeasured.
- The `question` label count depends on how the maintainer labels issues, and can change.

## For Task 15
- Curate the dev set mostly from 2023-onward Q&A discussions and `question` issues.
- Each ground-truth answer comes from the maintainer or marked answer (not from Claude), verified against `stable`.
- Candidate files are third-party text: keep them out of git and out of the public repo.
