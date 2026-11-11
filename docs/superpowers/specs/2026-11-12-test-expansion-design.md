# Test expansion: more questions, honest ranges, sealed held-out set

Date: 2026-11-11 (written the evening before the second testing day). Status: draft for owner approval. Marking: **(owner)** said or chosen by the owner; **(call)** my decision, to be checked.

## Why

Today's evidence is thin where it matters most. The claim "it refuses what the docs do not cover" rests on 13 questions (9 in the dev set, 4 in the generated set), so a perfect 9/9 still allows a true rate as low as 70%. Only the main model's answers were ever measured; the two fallback models answer whenever the main one is slow or down. Every number is one run, and answers vary run to run. The generated answerable questions are labelled by AI only. **(owner)** Today and tomorrow the free neuron allowance can be spent on testing ("don't worry about neurons and tokens"). The owner chose all four expansions below.

## What we build (all questions-only files, public text, no copies of the docs)

- **A. Refusal set** `evals/data/refusal.jsonl`, about 60 questions the docs do not answer, in groups: near-miss VisiData features the docs lack, comparisons with other tools, off-topic, instructions to ignore the rules, vague or broad, typos and gibberish, requests to write code. **(call)** I write them; the label "unanswerable" is checked afterwards: any question the system *answers* is read by a person (the owner or me, with the cited pages) to decide whether the docs actually cover it (label error, fix the label, report both counts) or the system guessed (a real failure).
- **B. Fallback answers.** Run the dev set through Groq `gpt-oss-20b` alone and Cloudflare `llama-3.1-8b` alone (new `eval --provider` option) and compare with the main model: refusals, answered rate, invalid citations. The classifier was measured this way; the answers never were.
- **C. Repeat runs.** Dev set 5 times and the refusal set 3 times with the normal chain, so every rate is reported as a range across runs plus the exact-count interval, not a single number.
- **D. Sealed held-out answerable set** `evals/data/heldout.jsonl`, about 100 questions written by Gemini from docs pieces **not used by any earlier set** (new `generate-questions --exclude-from`), kept only if Gemini and an independent Claude subagent both pass them (the method that produced `synthetic-checked.jsonl`), `split: "heldout"`. **(call)** "Sealed" rule: the first full run is the reported score; if we change a prompt or a rule after reading its failures, the set is no longer held out and a new one is generated. Labels are AI-checked only, so `/evals` must say so, and a hand-grading sample (the owner, about 30 minutes) is the recommended next step, not part of this work.

## Budget and limits (measured figures)

A full answer costs about 15 to 19 neurons; a gate refusal about 0. Cloudflare's free allowance is 10,000 neurons a day (resets 05:30 IST); keep about 1,000 spare for smoke tests and the beta. Estimated: today A (1 run) about 500, C about 2,100 (dev) plus 1,000 (A again), B about 420 (llama; Groq spends requests, not neurons); tomorrow D about 1,500 per run times 3. Gemini's free tier allows about 500 calls a day: generation plus checking of about 150 raw questions is under 400, so it may be split over two days. Groq allows 1,000 requests a day and 8,000 tokens a minute: pace calls (the cards test used a 3 s pause).

## Goals / non-goals / anti-goals

Goals: every headline rate comes with a count, a range across runs, and a plain label of how its questions were labelled; a safety claim backed by at least 60 refusal questions; a held-out score nobody tuned on. Non-goals: changing the assistant's behaviour in this work (any fix found goes to its own plan); hand-grading by the owner (recommended afterwards); running the beta. Anti-goals: a bigger set with weaker labels presented as stronger evidence; tuning on the held-out set; sending any user question to Gemini (only public docs text and our own test questions are used).

## Constraints

Free tiers only; questions and results files contain no docs text (results stay git-ignored under `evals/results/`; the committed question files are questions only); the neuron stop at 1,000 spare; ask the owner before every push; neutral wording; the existing `/evals` honesty rules (count and range for every rate, judge labelled "rough filter", generated questions labelled "AI-checked only, not human-checked").

## Left to the builder

Exact question wording within the groups; how the held-out generator skips earlier pieces; the layout of the new `/evals` sections.
