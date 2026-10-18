"""Spike S0: confirm Cloudflare Workers AI response shapes. Uses ~2 neurons."""
import json
import os

import httpx

ACCT = os.environ["CF_ACCOUNT_ID"]
TOKEN = os.environ["CF_API_TOKEN"]
BASE = f"https://api.cloudflare.com/client/v4/accounts/{ACCT}/ai/run"
EMBED_MODEL = "@cf/baai/bge-base-en-v1.5"
CHAT_MODEL = "@cf/meta/llama-3.1-8b-instruct-fp8-fast"
H = {"Authorization": f"Bearer {TOKEN}"}


def call(model: str, body: dict) -> dict:
    r = httpx.post(f"{BASE}/{model}", headers=H, json=body, timeout=60)
    print(model, "->", r.status_code)
    return r.json()


emb = call(EMBED_MODEL, {"text": ["what does & do?"]})
print("embedding top-level keys:", list(emb.keys()))
print("result keys:", list(emb.get("result", {}).keys()))
vec = emb["result"]["data"][0]
print("EMBEDDING DIM:", len(vec))

chat = call(CHAT_MODEL, {
    "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
    "max_tokens": 5,
})
print("chat result keys:", list(chat.get("result", {}).keys()))
print("chat result:", json.dumps(chat.get("result"), indent=2)[:800])
