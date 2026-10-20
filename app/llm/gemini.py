"""Gemini provider. For our own tests and the AI judge on PUBLIC data only.

The free tier lets Google use submitted content to improve its products, so no user question
may ever reach this class: it is not accepted in `models.answer_order` (see build.py).
"""
import time

import httpx

from app.llm.base import Completion, ProviderError, check_answer

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-3.5-flash-lite",
                 client: httpx.Client | None = None, json_output: bool = False):
        self.api_key, self.model, self.json_output = api_key, model, json_output
        self.client = client or httpx.Client(timeout=60)

    def complete(self, system: str, user: str, max_tokens: int) -> Completion:
        t0 = time.monotonic()
        config: dict = {"maxOutputTokens": max_tokens}
        if self.json_output:
            config["responseMimeType"] = "application/json"
        try:
            # The key goes in a header, not the URL: URLs end up in logs.
            r = self.client.post(
                URL.format(model=self.model), headers={"x-goog-api-key": self.api_key},
                json={"systemInstruction": {"parts": [{"text": system}]},
                      "contents": [{"role": "user", "parts": [{"text": user}]}],
                      "generationConfig": config})
        except httpx.HTTPError as e:
            raise ProviderError(f"network error: {type(e).__name__}") from e
        if r.status_code != 200:
            raise ProviderError(f"HTTP {r.status_code}", status=r.status_code)
        try:
            body = r.json()
            cand = body["candidates"][0]
            content = "".join(p.get("text", "") for p in cand["content"]["parts"])
            finish = "stop" if cand.get("finishReason") == "STOP" else cand.get("finishReason")
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as e:
            raise ProviderError("malformed or blocked response body") from e
        text = check_answer(content, finish)
        usage = body.get("usageMetadata") or {}
        return Completion(text, self.name, self.model, usage.get("promptTokenCount"),
                          usage.get("candidatesTokenCount"), None, time.monotonic() - t0)
