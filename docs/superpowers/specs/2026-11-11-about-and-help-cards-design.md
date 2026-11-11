# About and help cards: design

Date: 2026-11-11. Status: draft for owner approval. Follows Plan 3c (the redesigned chat page is live). Marking: **(owner)** = said or chosen by the owner. **(call)** = my decision, to be checked. **(builder)** = left to whoever builds it.

## Why

The first live check with the real app (2026-11-11) showed that the questions a newcomer asks first are refused. "what is visidata" and "how do I use visidata" got "I couldn't find this in the docs", and "what else can I do?" got the same. The saved rows say why: the docs folder contains no sentence that says what VisiData is (that text is on the website's front page, which is not ingested), and broad questions score under the evidence gate (0.016 against 0.020), so the model is never asked. A friend who has never heard of VisiData would read those three refusals as "this thing is broken". **(owner)** The first reply to such a question should be a short, plain explanation with links, not a refusal.

## What it should do

When a question is really "what is VisiData?", "how do I get started?" or "what can you do / how do I use you?", the page shows a **fixed card written by us** instead of searching the docs. **(owner)** Two cards:

- **About card.** A short plain description of VisiData and where to learn more: links to the website, the intro video and the docs' Getting Started page (the same three links the refusal card already shows, from config). Labelled on the card as written by us, not taken from the docs. **(call)**
- **Help card.** What this assistant can and cannot do, with three example questions that fill the typing box when clicked (they do not send; same behaviour as the starter cards). **(owner)** asked for "what can you do" to be answerable; the content is my draft below.

Draft text, for the owner to rewrite. **(call)** Everything below lives in `config/visidata.yaml`, not in code.

- About: "VisiData is a free tool that runs in the terminal and works like a spreadsheet for data files such as CSV. You drive it with the keyboard and can explore a file quickly." (This is the wording of the old page intro, already approved in Plan 3a.) Then the three links.
- Help: "I answer how-to questions about VisiData using only its documentation, and I show you which pages I used. I don't remember your earlier question, so ask each one in full. I can't answer anything outside VisiData, and I can make mistakes: check the linked page." Then three example questions (the starters from config).

## How a question is recognised **(owner)**

**A small model call classifies every question** into `about`, `help` or `normal`, before the normal search. The owner chose this knowing the cost below, and against my recommendation, which was to run the classifier only on questions that would otherwise be refused (that version never delays or misroutes a question that already works).

```
 question ─► [classifier: one cheap model call] ─┬─ about  ─► About card (no search, no answer call)
                                                  ├─ help   ─► Help card
                                                  └─ normal ─► search ─► answer or refusal (unchanged)
```

Known costs, stated so the owner can check them after the build (estimates until measured):

- One extra model call per question: about 1 to 3 seconds of waiting and roughly 1 to 3 neurons, against about 400 neurons for a full answer (under 1%).
- A classifier can be wrong. The dangerous direction is a real how-to question sent to a card, which hides an answer the assistant could have given. That is why the evaluation below has a hard bar on it.
- Each call sends the visitor's question to the same providers as the answer path, so the privacy notice does not change.

**Failure rule. (call)** If the classifier call fails, times out, or returns anything other than exactly one of the three labels, the question is treated as `normal`. The visitor never sees a classifier error, and the cards are never shown on a guess.

## Page and API behaviour

- **API. (call)** A card reply has `status: "card"` and `kind: "about" | "help"`, and no text or links: the page already holds the card text, built from the same config, and shows it with `textContent` only. So no server text becomes HTML, and the answer renderer is not involved.
- **Logging. (call)** Card questions are saved like any other, with `status = "card"`, `answer_text = "card:about"` or `"card:help"`, their neurons and `llm_calls = 1`, and no retrieved pieces. They are not counted as answered or refused in any eval number.
- **Caps. (call)** A card reply counts against the visitor's daily cap and the shared request cap like any other question, and its neurons count toward the daily neuron budget. Reason: an uncounted card path would let one invite spend the free neuron budget by repeating "what can you do". Cost: a friend who explores the cards uses up some of their 10 daily questions. Raise the cap if that annoys people in the beta.
- **Page.** A card shows in the feed where an answer card would, with a small label ("About VisiData · written by us, not from the docs" and "What I can do"), no "Was this helpful?" block, no sources list. The page treats an unknown `kind` as an unexpected reply, exactly as it does today for an unknown status.
- **Rollout order. (call)** The API and the page ship from one push to `main`, but Render and GitHub Pages deploy separately. For a minute or two an old page could receive `status: "card"` and show "Something unexpected came back" for those two kinds of question. Accepted; nothing is stored wrongly.

## Evaluation (before the owner relies on it)

The classifier gets its own small test set, `evals/data/cards.jsonl`: questions only, no answers, public text.

- **`about` and `help` positives**, in many wordings, about 10 each ("what is visidata", "so what's this tool?", "how do I get started", "what can you do", "what are you for", "help").
- **`normal` negatives**, including the traps that sound broad but are real how-to questions: "what is a frequency table", "how do I use the join command", "what does the help key do", "how do I use visidata to sort", plus every answerable question in `evals/data/dev.jsonl` as controls.
- **Bar, set before the run:** zero of the dev-set how-to questions routed to a card; at least 90% of the positives routed to the right card; every classifier failure (error, junk output) falls through to `normal`.
- The run uses the production provider, so it spends neurons (about 2 each, so under 150 for about 60 questions). **The owner approves the run first.** A bad result means tuning the prompt, or falling back to the owner's alternatives (phrase lists, or classify only refusals), not shipping.

## Goals

- A newcomer's first question ("what is this?", "what can you do?") gets a useful, honest reply in seconds.
- A real how-to question is never sent to a card.
- Card text is easy to change without touching code.

## Non-goals

- Streaming, follow-up memory (Plan 3b), or answering "what is VisiData" with the model from the website. The owner dropped that in favour of fixed cards.
- Ingesting any new source. The "docs only" promise for model answers stays exactly as it is.
- Cards for other topics (pricing, contact, licences). Two cards only.

## Anti-goals (a failure even if it works)

- A card shown for a question that has a real docs answer.
- The classifier making the app noticeably slower or failing visibly.
- Anything that lets a visitor's text change which card text appears beyond choosing one of the two fixed cards (the question is data to the classifier, never instructions; only an exact label is accepted).

## Constraints (do not break)

- Page security rules stay as built: no inline scripts or styles, no third-party loads, `connect-src` is the API only; the answer renderer and its tests are not touched; the token handling is unchanged.
- Card text and links come from config and go through the existing escaping and the https-only link filter.
- Free tiers only; the daily neuron stop at 8,000 stays; the classifier uses the existing provider chain and counters (one adapter per request).
- Project specifics (card text, labels, classifier descriptions) live in `config/`, not in code.
- Tests first for every new rule; existing suites stay green; the real-database tests need `TEST_DATABASE_URL`.

## Left to the builder

The classifier prompt wording and its token limit (it must end on a normal "stop", or the call counts as failed); the label parsing (exact match after trimming and lowercasing); the config key names; where the card is built in the page; the `cards.jsonl` question wording within the categories above; how the `status` column and the cap queries learn the new value (the table has no check on `status`, and `usage.finish` has a fixed list).
