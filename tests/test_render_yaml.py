import importlib.util
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
SECRETS = {"DATABASE_URL", "CF_ACCOUNT_ID", "CF_API_TOKEN", "GROQ_API_KEY"}


def service() -> dict:
    data = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    assert len(data["services"]) == 1
    return data["services"][0]


def test_service_is_free_web_in_ohio_next_to_neon():
    s = service()
    assert s["type"] == "web" and s["plan"] == "free" and s["region"] == "ohio"
    assert s["branch"] == "main" and s["healthCheckPath"] == "/health"


def test_python_is_pinned_to_the_ci_minor_version():
    env = {e["key"]: e for e in service()["envVars"]}
    assert env["PYTHON_VERSION"]["value"].startswith("3.12.")  # CI tests on 3.12; Render defaults to 3.14


def test_start_command_uses_the_factory_and_keeps_no_access_log():
    cmd = service()["startCommand"]
    assert "--factory app.api:build_from_env" in cmd and "--no-access-log" in cmd
    assert "--port $PORT" in cmd and "--host 0.0.0.0" in cmd


def test_secrets_are_declared_but_never_hold_a_value():
    env = {e["key"]: e for e in service()["envVars"]}
    for key in SECRETS:
        assert env[key].get("sync") is False and "value" not in env[key], key
    plain = {k for k, e in env.items() if "value" in e}
    assert plain <= {"PYTHON_VERSION", "CONFIG_PATH"}, plain


def load_smoke():
    spec = importlib.util.spec_from_file_location("smoke", ROOT / "scripts" / "smoke.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def handler(req: httpx.Request) -> httpx.Response:
    auth = req.headers.get("authorization", "")
    if req.url.path == "/health":
        return httpx.Response(200, json={"ok": True})
    if req.url.path == "/version":
        return httpx.Response(200, json={"docs_ref": "stable@abc", "project": "visidata"})
    if auth != "Bearer good":
        return httpx.Response(401, json={"error": "Unknown or revoked invite link."})
    if b"France" in req.content:
        return httpx.Response(200, json={"status": "abstained", "text": "not found",
                                         "citations": []})
    cite = {"n": 1, "url": "https://www.visidata.org/docs/columns/#hide"}
    return httpx.Response(200, json={"status": "answered", "text": "x [1]", "citations": [cite]})


def test_smoke_passes_against_a_healthy_service():
    smoke = load_smoke()
    client = httpx.Client(transport=httpx.MockTransport(handler))
    checks = smoke.run_checks(client, "https://api.example", "good", "https://www.visidata.org/docs")
    assert [c.ok for c in checks] == [True] * len(checks) and len(checks) >= 5


def test_smoke_fails_when_the_answer_cites_a_foreign_site():
    smoke = load_smoke()

    def bad(req):
        r = handler(req)
        if req.url.path == "/ask" and b"France" not in req.content and \
                req.headers.get("authorization") == "Bearer good":
            return httpx.Response(200, json={"status": "answered", "text": "x [1]",
                                             "citations": [{"n": 1, "url": "https://evil.example/"}]})
        return r

    checks = smoke.run_checks(httpx.Client(transport=httpx.MockTransport(bad)),
                              "https://api.example", "good", "https://www.visidata.org/docs")
    assert not all(c.ok for c in checks)
