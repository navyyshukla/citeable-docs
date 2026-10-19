"""Groq chat provider (OpenAI-compatible API)."""
import time

import httpx

from app.llm.base import Completion, ProviderError, check_answer

URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqProvider:
    name = "groq"

    def __init__(self, api_key: str, model: str, client: httpx.Client | None = None,
                 reasoning_effort: str = "low"):
        self.api_key, self.model, self.reasoning_effort = api_key, model, reasoning_effort
        self.client = client or httpx.Client(timeout=60)

    def complete(self, system: str, user: str, max_tokens: int) -> Completion:
        t0 = time.monotonic()
        try:
            r = self.client.post(URL, headers={"Authorization": f"Bearer {self.api_key}"}, json={
                "model": self.model,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "max_completion_tokens": max_tokens,
                "reasoning_effort": self.reasoning_effort,
            })
        except httpx.HTTPError as e:
            raise ProviderError(f"network error: {type(e).__name__}") from e
        if r.status_code != 200:
            raise ProviderError(f"HTTP {r.status_code}", status=r.status_code)
        try:
            body = r.json()
            choice = body["choices"][0]
            content = choice["message"].get("content")
            finish = choice.get("finish_reason")
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as e:
            raise ProviderError("malformed response body") from e
        text = check_answer(content, finish)
        usage = body.get("usage") or {}
        return Completion(text, self.name, self.model, usage.get("prompt_tokens"),
                          usage.get("completion_tokens"), None, time.monotonic() - t0)
