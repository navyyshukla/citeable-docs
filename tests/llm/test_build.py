import json

import httpx
import pytest

from app.config import load_config
from app.llm.build import build_adapter

ENV = {"CF_ACCOUNT_ID": "a", "CF_API_TOKEN": "t", "GROQ_API_KEY": "g"}
GEMMA_OK = {"result": {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                       "usage": {"prompt_tokens": 1, "completion_tokens": 1, "neurons": 1}}}


def test_chain_follows_config_order_with_per_model_settings():
    cfg = load_config("config/visidata.yaml")
    bodies = []

    def handler(req):
        bodies.append((req.url.host, json.loads(req.content)))
        return httpx.Response(500, json={})

    adapter = build_adapter(cfg, ENV, httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(Exception, match="gemma"):
        adapter.complete("s", "u", cfg.limits.max_completion_tokens)
    hosts = [h for h, _ in bodies]
    assert hosts == ["api.cloudflare.com", "api.groq.com", "api.cloudflare.com"]
    gemma, groq, llama = (b for _, b in bodies)
    assert gemma["chat_template_kwargs"] == {"enable_thinking": False}
    assert gemma["max_tokens"] == cfg.limits.max_completion_tokens_no_thinking
    assert groq["max_completion_tokens"] == cfg.limits.max_completion_tokens
    assert llama["max_tokens"] == cfg.limits.max_answer_tokens
    assert "chat_template_kwargs" not in llama


def test_first_provider_answers():
    cfg = load_config("config/visidata.yaml")
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=GEMMA_OK)))
    out = build_adapter(cfg, ENV, client).complete("s", "u", 10)
    assert out.provider == "cloudflare" and out.text == "ok"


def test_unknown_provider_and_missing_key_are_errors():
    cfg = load_config("config/visidata.yaml")
    bad = cfg.model_copy(update={"models": cfg.models.model_copy(
        update={"answer_order": ["gemini:flash"]})})
    with pytest.raises(ValueError, match="gemini"):
        build_adapter(bad, ENV)
    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        build_adapter(cfg, {"CF_ACCOUNT_ID": "a", "CF_API_TOKEN": "t"})
