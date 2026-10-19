"""Build the answer chain from config: order and per-model settings live in the YAML."""
from collections.abc import Mapping

import httpx

from app.config import Config
from app.llm.base import Adapter, Provider
from app.llm.cloudflare import CloudflareClient, CloudflareProvider
from app.llm.groq import GroqProvider


def _need(env: Mapping[str, str], key: str) -> str:
    if not env.get(key):
        raise ValueError(f"{key} is not set")
    return env[key]


def build_adapter(cfg: Config, env: Mapping[str, str],
                  client: httpx.Client | None = None) -> Adapter:
    m, lim = cfg.models, cfg.limits
    providers: list[Provider] = []
    for entry in m.answer_order:
        kind, _, model = entry.partition(":")
        if kind == "cloudflare":
            thinking = m.thinking.get(model)
            if model in m.non_reasoning:
                cap = lim.max_answer_tokens
            elif thinking is False:
                cap = lim.max_completion_tokens_no_thinking
            else:
                cap = lim.max_completion_tokens
            cf = CloudflareClient(_need(env, "CF_ACCOUNT_ID"), _need(env, "CF_API_TOKEN"), client)
            providers.append(CloudflareProvider(cf, model, m.neurons_per_m_tokens.get(model),
                                                thinking, cap))
        elif kind == "groq":
            providers.append(GroqProvider(_need(env, "GROQ_API_KEY"), model, client))
        else:
            raise ValueError(f"provider {kind!r} is not implemented (entry {entry!r})")
    return Adapter(providers)
