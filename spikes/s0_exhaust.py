"""Spike S0b: find out what happens when the free daily allocation runs out.
Run ONCE, deliberately. It stops at the first non-200 response.

Uses the stable model, not the deprecated `-fast` alias (see docs/spikes/s0-accounts.md)."""
import os
import time

import httpx

ACCT, TOKEN = os.environ["CF_ACCOUNT_ID"], os.environ["CF_API_TOKEN"]
URL = (f"https://api.cloudflare.com/client/v4/accounts/{ACCT}/ai/run/"
       "@cf/meta/llama-3.1-8b-instruct-fp8")
BODY = {"messages": [{"role": "user", "content": "Write 400 words about rivers."}],
        "max_tokens": 700}
n = 0
while True:
    r = httpx.post(URL, headers={"Authorization": f"Bearer {TOKEN}"}, json=BODY, timeout=120)
    n += 1
    if r.status_code != 200:
        print("call", n, "status", r.status_code)
        print(r.text[:1000])
        break
    if n % 20 == 0:
        print("call", n, "ok")
    time.sleep(0.2)
