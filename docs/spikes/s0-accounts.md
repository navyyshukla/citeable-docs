# S0: accounts and Cloudflare probe

Status: probe done (2026-10-15). Context window, exhaustion test, and Gemini/Groq limits still to do.

## Measured: Cloudflare Workers AI response shapes

Probe: `spikes/s0_cloudflare_probe.py`. Both calls returned HTTP 200.

### Embedding: `@cf/baai/bge-base-en-v1.5`
- Request: `{"text": ["..."]}`
- Top-level keys: `result`, `success`, `errors`, `messages`
- `result` keys: `data`, `shape`, `pooling`, `usage`
- Vectors are at `result.data[i]`
- **`embedding_dim` = 768** (matches `config/visidata.yaml` draft value)

### Chat: `@cf/meta/llama-3.1-8b-instruct-fp8-fast`
- Request: `{"messages": [...], "max_tokens": N}`
- `result` has both an OpenAI-style `choices[0].message.content` and a flat `response` string.
- `result.usage` is present (token counts; use it for per-question neuron estimates).
- Answer text: `result.response` (same text as `choices[0].message.content`).
- Note: the `model` field in the reply said `@cf/meta/llama-3.1-8b-fast-v2`, not the id we requested. Cloudflare may route this id to a newer build. To keep in mind when comparing results across days.

## Measured: chat model id is deprecated (Step 5)

- Cloudflare's docs page for `@cf/meta/llama-3.1-8b-instruct-fp8-fast` says "deprecated, removed, or not found" (screenshot 2026-10-15).
- The model catalog API (`GET /accounts/{id}/ai/models/search?task=Text Generation`, 36 models) does **not** list it. It lists `@cf/meta/llama-3.1-8b-instruct-fp8` (no `-fast`).
- The API still answers calls to the old id and reports `model: @cf/meta/llama-3.1-8b-fast-v2`. So it is an alias that Cloudflare can change or remove. **Do not rely on it.**
- Context window of the aliased model: **not verified**. Nearest documented sibling, `llama-3.1-8b-instruct-fp8`, is 32,000 tokens, below the 40,000 decision-rule threshold.

Context windows from the catalog (tokens; catalog also gives USD per M tokens):

| Model | Context |
|---|---|
| `@cf/meta/llama-3.1-8b-instruct-fp8` | 32,000 |
| `@cf/openai/gpt-oss-20b` | 128,000 |
| `@cf/openai/gpt-oss-120b` | 128,000 |
| `@cf/meta/llama-4-scout-17b-16e-instruct` | 131,000 |
| `@cf/google/gemma-4-26b-a4b-it` | 256,000 |

Decision rule outcome: the paste-all baseline (about 35k tokens of docs) cannot run on a ~32k model. A 128k Cloudflare model can run it, so Gemini may not be needed for this. The answering model choice is for the Task 5 review gate.

## Measured: candidate answer models (2026-10-15)

Prices from the Cloudflare pricing page (updated Oct 9, 2026). 1,000 neurons = $0.011; free allocation 10,000 neurons/day. Cost per question is an **estimate** at 3,000 tokens in and 300 out, the spec's own assumption.

| Model | Neurons per M in / out | Est. neurons per question | Questions per 10k | Context | Paste-all (35k) fits? |
|---|---|---|---|---|---|
| `llama-3.1-8b-instruct-fp8-fast` (alias, deprecated) | 4,119 / 34,868 | 23 | 438 | unverified | unknown |
| `llama-3.1-8b-instruct-fp8` | 13,778 / 26,128 | 49 | 203 | 32,000 | no |
| `gemma-4-26b-a4b-it` | 9,091 / 27,273 | 36 | 282 | 256,000 | yes (about 326) |
| `gpt-oss-20b` | 18,182 / 27,273 | 63 | 159 | 128,000 | yes (about 645) |
| `qwen3-30b-a3b-fp8` | 4,625 / 30,475 | 23 | 435 | 32,768 | no |
| `llama-4-scout-17b-16e` | 24,545 / 77,273 | 97 | 103 | 131,000 | yes |
| `mistral-small-3.1-24b` | 31,876 / 50,488 | 111 | 90 | 128,000 | yes |

The global daily cap in the plan is 150 questions/day. Rows under 150 per 10k (scout, mistral-small, 70B and 120B models) cannot meet it.

Tiny probe (about 13 neurons total, one short question, `max_tokens` 120):

- All four models answered with HTTP 200 on the free plan (none is paid-gated).
- **`gemma-4`, `gpt-oss-20b` and `qwen3-30b` are reasoning models. They spent the whole 120 tokens thinking and returned EMPTY answer text.** Only `llama-3.1-8b-instruct-fp8` returned a normal answer.
- The API reports real cost in `result.usage.neurons`. The adapter should log it instead of estimating.
- Unverified: whether reasoning can be turned off or kept short for the three reasoning models, and how they behave with `max_tokens` 400 and a real 3,000-token prompt.

### Reasoning-off test (2026-10-15, about 26 neurons)

One run per setting, a 2-sentence context and a trivial question, `max_tokens` 300. This shows what the settings do, not answer quality.

| Model | Setting | Output tokens | Neurons | Reasoning text | Answer |
|---|---|---|---|---|---|
| `gemma-4-26b-a4b-it` | none | 174 | 5.35 | 611 chars | correct |
| `gemma-4-26b-a4b-it` | `chat_template_kwargs: {enable_thinking: false}` | **11** | **0.93** | none | correct |
| `gemma-4-26b-a4b-it` | `reasoning_effort: low` | 155 | 4.84 | 510 chars | correct |
| `gpt-oss-20b` | none | 142 | 6.09 | 525 chars | correct |
| `gpt-oss-20b` | `reasoning: {effort: low}` | 109 | 5.19 | 390 chars | correct |
| `gpt-oss-20b` | `reasoning_effort: low` | 33 | 3.12 | 34 chars | correct |
| `qwen3-30b-a3b-fp8` | `enable_thinking: false` | 21 | 0.95 | 90 chars | **empty** (text landed in the reasoning field) |

Findings:
- `gemma-4`: `enable_thinking=false` works. Reasoning off, 11 tokens, under 1 neuron.
- `gpt-oss-20b`: top-level `reasoning_effort: low` works best. The nested `reasoning` form barely helps.
- `qwen3-30b`: still returns an empty answer field. Not usable without more work.
- Still unverified: behaviour with a real 3,000-token prompt, and answer quality. Also check that a model whose answer lands in the reasoning field is detected (adapter must treat an empty answer as an error, not a result).

## Measured: fallback providers (2026-10-17, from official pages; fetched by Claude)

### Groq free plan
Source: https://console.groq.com/docs/rate-limits ("high level summary, there may be exceptions"; your account's Limits page is the exact source).

| Model | RPM | RPD | TPM | TPD |
|---|---|---|---|---|
| `openai/gpt-oss-20b` | 30 | 1,000 | 8,000 | 200,000 |
| `openai/gpt-oss-120b` | 30 | 1,000 | 8,000 | 200,000 |
| `qwen/qwen3.8-27b` | 30 | 1,000 | 8,000 | 200,000 |

- 8,000 tokens per minute means the 35k-token paste-all baseline **cannot run on Groq free**.
- 200,000 tokens per day is about 55 questions/day at about 3,500 tokens each (estimate, before reasoning tokens). A full eval run likely does not fit in one day.
- Data: Groq does not retain inference inputs or outputs by default. It may log them for up to 30 days only to troubleshoot errors or investigate abuse (https://console.groq.com/docs/your-data). Opt-out is in Data Controls.

### Gemini free tier
- The public docs say limits are per model and per project and are shown in AI Studio (https://aistudio.google.com/rate-limit). Exact per-model RPM/RPD/TPD are **not** on the public page. Owner to copy them (pending).
- Many Gemini models show "Not available" on the free tier. Which ones are free must be read from the pricing page or AI Studio.
- **Terms (https://ai.google.dev/gemini-api/terms): on the unpaid quota, Google uses submitted content and responses to improve its products, and human reviewers may read them.** The paid tier does not. So **never send user questions to Gemini free.** Use it only for our own tests and judge calls on public data.

### Measured with the owner's keys (2026-10-18)

**Groq** (`openai/gpt-oss-20b`, one call with `reasoning_effort: low`, HTTP 200): response headers on the owner's account show **1,000 requests/day and 8,000 tokens/min**. This matches the table above. Tokens/day (200K) is not in the headers, so it is from the docs table only.

**Gemini 3.8 Flash** (`gemini-3.8-flash`), checked from several sources:
- Official pricing page (updated 2026-10-16): Free Tier = "Free of charge" for input and output; "Used to improve our products: Yes".
- Official changelog: 3.8 Flash GA on 2026-09-02. `gemini-3.7-flash` and `gemini-3.5-flash` are deprecated and auto-routed. Gemini 2.5 models are "not deprecated" but access is limited to users who have already used them, so new projects should use 3.5 Flash-Lite or 3.8 Flash.
- Our own call with the free key (no billing set up, AI Studio shows "Free tier") returned HTTP 200.
- **Daily cap is low.** A Google forum post (2026-09-03, confirmed by a second user on 2026-10-16) reports **20 requests/day** for 3.8 Flash on the free tier, against **500/day for Flash-Lite**. Unofficial. Google publishes no table; the owner's AI Studio Rate Limit page is the authority (the limit columns were cut off in the owner's PDF).
- Default thinking is on (`medium`): the first test spent 112 of 128 tokens on thinking and returned 4 visible tokens. With `thinkingConfig.thinkingLevel: "low"` the answer came back normally. `minimal` is not supported.
- `gemini-3.5-flash-lite` also works on the free key (HTTP 200, 48 output tokens, no thinking tokens).

### Consequences for the plan
- User traffic: Cloudflare first, Groq as fallback (no training use by default).
- Tests and judge: Gemini free (public eval data only) or Groq. Groq's 200k tokens/day limits eval run size.

### Owner decision (2026-10-18): fallback and test models

| Job | Model | Provider |
|---|---|---|
| User fallback (after Cloudflare) | `openai/gpt-oss-20b`, `reasoning_effort: low` | Groq |
| Tests and judge (public data only) | `gemini-3.5-flash-lite` | Google AI Studio (free) |
| Rare quality spot-checks | `gemini-3.8-flash`, `thinkingLevel: low` | Google AI Studio (free) |

Owner reasoning: 3.5 Flash-Lite is the better choice for tests. Claude's evidence: the forum-reported free daily cap is about 500 requests for Flash-Lite against about 20 for 3.8 Flash, and Flash-Lite spent no thinking tokens in the probe. **Confirmed on the owner's AI Studio Rate Limit page (2026-10-18):**

| Model | Requests/min | Tokens/min | Requests/day |
|---|---|---|---|
| `gemini-3.5-flash-lite` | 15 | 250,000 | 500 |
| `gemini-3.8-flash` | 5 | not read | 20 |

So the forum reports were right. A run of 100 questions with one answer call and one judge call each is 200 requests, inside 500/day, and at 15/min takes about 14 minutes.

Rule that follows: Gemini free content is used by Google to improve its products, so nothing from real users is ever sent to Gemini.

## Still to record
- [x] Context window of the chat model (Step 5), see above
- [ ] Exhaustion behavior (Step 6)
- [ ] Gemini and Groq limits, two fallback models, training-use terms (Step 7)
