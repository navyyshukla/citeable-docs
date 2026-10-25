"""Post-deploy check of a live API: SMOKE_TOKEN=<token> python scripts/smoke.py URL

The token comes from the environment, not the command line: arguments end up in shell history
and the process list.

Makes two real /ask calls (a few Cloudflare neurons at most) and prints how long each step took,
so cold-start and warm times are measured, not guessed.
"""
import os
import sys
import time
from dataclasses import dataclass

import httpx

IN_DOCS = "How do I unhide a column that I hid in VisiData?"
OUT_OF_DOCS = "What is the capital of France?"


@dataclass
class Check:
    name: str
    ok: bool
    seconds: float
    detail: str = ""


def _timed(name: str, fn) -> Check:
    t0 = time.monotonic()
    try:
        ok, detail = fn()
    except httpx.HTTPError as e:
        ok, detail = False, f"{type(e).__name__}"
    return Check(name, ok, time.monotonic() - t0, detail)


def run_checks(client: httpx.Client, base: str, token: str, site: str) -> list[Check]:
    auth = {"Authorization": f"Bearer {token}"}

    def health():
        r = client.get(f"{base}/health")
        return r.status_code == 200, f"HTTP {r.status_code}"

    def version():
        r = client.get(f"{base}/version")
        return r.status_code == 200, f"HTTP {r.status_code}"

    def bad_token():
        r = client.post(f"{base}/ask", json={"question": "hi"},
                        headers={"Authorization": "Bearer not-a-real-token"})
        return r.status_code == 401, f"HTTP {r.status_code}"

    def in_docs():
        r = client.post(f"{base}/ask", json={"question": IN_DOCS}, headers=auth)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        body = r.json()
        urls = [c["url"] for c in body.get("citations", [])]
        ok = body.get("status") == "answered" and bool(urls) and all(
            u.startswith(site) for u in urls)
        return ok, f"status={body.get('status')} citations={len(urls)}"

    def out_of_docs():
        r = client.post(f"{base}/ask", json={"question": OUT_OF_DOCS}, headers=auth)
        return (r.status_code == 200 and r.json().get("status") == "abstained",
                f"HTTP {r.status_code} status={r.json().get('status') if r.status_code == 200 else '-'}")

    return [_timed("health (cold start shows here)", health), _timed("version", version),
            _timed("wrong token is refused", bad_token),
            _timed("in-docs question is answered with on-site citations", in_docs),
            _timed("out-of-docs question abstains", out_of_docs)]


def main(argv: list[str]) -> int:
    token = os.environ.get("SMOKE_TOKEN")
    if len(argv) != 2 or not token:
        print("usage: SMOKE_TOKEN=<token> python scripts/smoke.py URL", file=sys.stderr)
        return 2
    from app.config import load_config
    site = load_config("config/visidata.yaml").project.site_base_url
    checks = run_checks(httpx.Client(timeout=120), argv[1].rstrip("/"), token, site)
    for c in checks:
        print(f"{'PASS' if c.ok else 'FAIL'}  {c.seconds:6.1f}s  {c.name}  {c.detail}")
    return 0 if all(c.ok for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
