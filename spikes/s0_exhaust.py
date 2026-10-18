"""Spike S0b: find out what happens when the free daily allocation runs out.
Run ONCE, deliberately. It stops at the first non-200 response, with a hard cap on calls.

Uses the stable model, not the deprecated `-fast` alias (see docs/spikes/s0-accounts.md).
Several workers run in parallel so the test takes minutes, not an hour. The API reports the
real cost of each call in `usage.neurons`; the script adds them up."""
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

ACCT, TOKEN = os.environ["CF_ACCOUNT_ID"], os.environ["CF_API_TOKEN"]
BASE = f"https://api.cloudflare.com/client/v4/accounts/{ACCT}/ai/run/"
H = {"Authorization": f"Bearer {TOKEN}"}
CHAT = "@cf/meta/llama-3.1-8b-instruct-fp8"
BODY = {"messages": [{"role": "user", "content": "Write 400 words about rivers."}],
        "max_tokens": 700}
WORKERS, MAX_CALLS, MAX_SECONDS = 4, 1500, 60 * 60
# Safety: if this many neurons are spent in ONE run without any error, stop and check the dashboard
# for charges (the free allowance is 10,000 neurons/day).
NEURON_STOP = 5000
MAX_NETWORK_ERRORS = 12

lock = threading.Lock()
stop = threading.Event()
state = {"calls": 0, "neurons": 0.0, "errors": [], "network_errors": 0, "stopped_by": ""}
started = time.time()


def worker() -> None:
    while not stop.is_set():
        with lock:
            if state["calls"] >= MAX_CALLS or time.time() - started > MAX_SECONDS:
                stop.set()
                return
            state["calls"] += 1
        try:
            r = httpx.post(BASE + CHAT, headers=H, json=BODY, timeout=240)
        except httpx.HTTPError as e:
            # A timeout is not a quota error: retry, and only stop if it keeps happening.
            with lock:
                state["network_errors"] += 1
                state["calls"] -= 1
                too_many = state["network_errors"] >= MAX_NETWORK_ERRORS
                if too_many:
                    state["errors"].append(("network", repr(e)[:200], {}))
                    state["stopped_by"] = "repeated network errors"
            if too_many:
                stop.set()
                return
            time.sleep(5)
            continue
        if r.status_code == 200:
            used = (r.json().get("result") or {}).get("usage", {}).get("neurons") or 0
            with lock:
                state["neurons"] += used
                if state["neurons"] >= NEURON_STOP:
                    state["stopped_by"] = "neuron safety stop reached with no error"
                    stop.set()
                if state["calls"] % 20 == 0:
                    print(f"call {state['calls']} ok, neurons so far {state['neurons']:.0f}", flush=True)
        else:
            hdr = {k: v for k, v in r.headers.items() if "limit" in k.lower() or "retry" in k.lower()}
            with lock:
                state["errors"].append((r.status_code, r.text[:600], hdr))
                state["stopped_by"] = state["stopped_by"] or "non-200 response"
            stop.set()
        time.sleep(0.2)


with ThreadPoolExecutor(WORKERS) as pool:
    for _ in range(WORKERS):
        pool.submit(worker)

print("\n=== stopped after", state["calls"], "calls; neurons counted:", round(state["neurons"]),
      "; seconds:", round(time.time() - started), "; network errors retried:", state["network_errors"],
      "; stopped by:", state["stopped_by"] or "call or time cap")
for status, text, hdr in state["errors"][:4]:
    print("first non-200:", status, "|", text, "|", hdr)

print("\n=== afterwards: what still works?")
checks = [
    ("chat, same model", CHAT, {"messages": [{"role": "user", "content": "Say ok"}], "max_tokens": 5}),
    ("embedding", "@cf/baai/bge-base-en-v1.5", {"text": ["hello"]}),
    ("chat, other model", "@cf/google/gemma-4-26b-a4b-it",
     {"messages": [{"role": "user", "content": "Say ok"}], "max_tokens": 20,
      "chat_template_kwargs": {"enable_thinking": False}}),
]
for label, model, body in checks:
    r = httpx.post(BASE + model, headers=H, json=body, timeout=60)
    print(f"{label}: http {r.status_code} | {r.text[:300]}")
