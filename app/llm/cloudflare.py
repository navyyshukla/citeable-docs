"""Cloudflare Workers AI: chat provider and embeddings."""
import time

import httpx

from app.llm.base import Completion, ProviderError, check_answer

# The embedding model silently cuts input at about 2,100 characters (spike S8).
EMBED_MAX_CHARS = 2000


class CloudflareClient:
    def __init__(self, account_id: str, api_token: str, client: httpx.Client | None = None):
        self.account_id, self.api_token = account_id, api_token
        self.client = client or httpx.Client(timeout=60)

    def run(self, model: str, payload: dict) -> dict:
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/{model}"
        try:
            r = self.client.post(url, headers={"Authorization": f"Bearer {self.api_token}"},
                                 json=payload)
        except httpx.HTTPError as e:
            raise ProviderError(f"network error: {type(e).__name__}") from e
        if r.status_code != 200:
            raise ProviderError(f"HTTP {r.status_code}", status=r.status_code)
        try:
            result = r.json()["result"]
        except (ValueError, KeyError, TypeError) as e:
            raise ProviderError("malformed response body") from e
        if not isinstance(result, dict):
            raise ProviderError("malformed response body")
        return result


def _parse_chat(result: dict) -> str:
    """Two shapes: OpenAI-style `choices` (gemma-4) and `response` (llama, no finish_reason)."""
    choices = result.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0]
        message = choice.get("message") if isinstance(choice, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        return check_answer(content, choice.get("finish_reason"))
    if "response" in result:
        return check_answer(result["response"], "stop")
    raise ProviderError("response missing text")


class CloudflareProvider:
    name = "cloudflare"

    def __init__(self, cf: CloudflareClient, model: str,
                 price: tuple[float, float] | None = None,
                 thinking: bool | None = None, max_tokens_cap: int | None = None):
        self.cf, self.model, self.price = cf, model, price
        self.thinking, self.max_tokens_cap = thinking, max_tokens_cap

    def complete(self, system: str, user: str, max_tokens: int) -> Completion:
        t0 = time.monotonic()
        if self.max_tokens_cap is not None:
            max_tokens = min(max_tokens, self.max_tokens_cap)
        payload: dict = {
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "max_tokens": max_tokens,
        }
        if self.thinking is not None:
            payload["chat_template_kwargs"] = {"enable_thinking": self.thinking}
        result = self.cf.run(self.model, payload)
        usage = result.get("usage") or {}
        tin, tout = usage.get("prompt_tokens"), usage.get("completion_tokens")
        neurons = usage.get("neurons")
        if neurons is None and self.price and tin is not None and tout is not None:
            neurons = tin / 1e6 * self.price[0] + tout / 1e6 * self.price[1]
        try:
            text = _parse_chat(result)
        except ProviderError as e:
            e.neurons = neurons  # a reply cut off at the token cap was still billed
            raise
        return Completion(text, self.name, self.model, tin, tout, neurons,
                          time.monotonic() - t0)


def embed_texts(cf: CloudflareClient, model: str, texts: list[str],
                batch: int) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), batch):
        chunk = [t[:EMBED_MAX_CHARS] for t in texts[i:i + batch]]
        data = cf.run(model, {"text": chunk}).get("data")
        if not isinstance(data, list) or len(data) != len(chunk):
            raise ProviderError("embedding response has wrong shape")
        out.extend(data)
    return out
