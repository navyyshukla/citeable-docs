import pytest
from fastapi.testclient import TestClient

from app.answer import Citation
from app.api import build_from_env, create_app
from app.config import load_config
from app.service import AskError, AskResult

CFG = load_config("config/visidata.yaml")
GOOD = "https://navyyshukla.github.io"
BAD = "https://evil.example"


class FakeService:
    def __init__(self):
        self.asked, self.feedbacks = [], []
        self.raises: Exception | None = None

    def ask(self, token, question):
        self.asked.append((token, question))
        if self.raises:
            raise self.raises
        c = Citation(1, "Join › How", "https://www.visidata.org/docs/join/", "3.0", "2026-01-01")
        return AskResult("rid-1", "answered", "It joins [1].", [c], [c], "stable@abc", "3.0",
                         "2026-01-01")

    def feedback(self, token, request_id, rating, comment):
        self.feedbacks.append((token, request_id, rating, comment))

    def version(self):
        return {"project": "visidata", "docs_ref": "stable@abc", "models": ["m1"]}


@pytest.fixture
def svc():
    return FakeService()


@pytest.fixture
def client(svc):
    return TestClient(create_app(svc, CFG), raise_server_exceptions=False)


def auth(token="good"):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Basic abc"},
                                     {"Authorization": "Bearer "}, {"Authorization": "Bearer"}])
def test_ask_requires_bearer_token(client, svc, headers):
    r = client.post("/ask", json={"question": "hi"}, headers=headers)
    assert r.status_code == 401 and svc.asked == []


def test_ask_happy_path_shape(client, svc):
    r = client.post("/ask", json={"question": "what does & do?"}, headers=auth())
    assert r.status_code == 200
    body = r.json()
    assert body["request_id"] == "rid-1" and body["status"] == "answered"
    assert body["citations"][0] == {"n": 1, "title": "Join › How",
                                    "url": "https://www.visidata.org/docs/join/",
                                    "docs_version": "3.0", "last_updated": "2026-01-01"}
    assert body["docs_ref"] == "stable@abc" and body["notice"] == CFG.project.license_note
    assert svc.asked == [("good", "what does & do?")]


@pytest.mark.parametrize("kwargs", [
    {"content": b"not json", "headers": {"Content-Type": "application/json"}},
    {"json": {"q": "x"}},
    {"json": {"question": 5}},
    {"json": ["question"]},
])
def test_ask_bad_body_is_4xx_and_never_reaches_the_service(client, svc, kwargs):
    headers = {**auth(), **kwargs.pop("headers", {})}
    r = client.post("/ask", headers=headers, **kwargs)
    assert 400 <= r.status_code < 500 and svc.asked == []
    assert "good" not in r.text  # the token is never echoed


def test_body_over_4kb_is_413(client, svc):
    r = client.post("/ask", json={"question": "x" * 5000}, headers=auth())
    assert r.status_code == 413 and svc.asked == []


def test_body_over_4kb_without_content_length_is_413(client, svc):
    def chunks():
        yield b'{"question": "'
        yield b"x" * 5000
        yield b'"}'
    r = client.post("/ask", content=chunks(), headers={**auth(), "Content-Type": "application/json"})
    assert r.status_code == 413 and svc.asked == []


def test_cors_allows_listed_origin_only(client):
    ok = client.options("/ask", headers={"Origin": GOOD, "Access-Control-Request-Method": "POST",
                                         "Access-Control-Request-Headers": "authorization"})
    assert ok.headers.get("access-control-allow-origin") == GOOD
    no = client.options("/ask", headers={"Origin": BAD, "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in no.headers
    post = client.post("/ask", json={"question": "hi"}, headers={**auth(), "Origin": BAD})
    assert "access-control-allow-origin" not in post.headers


def test_ask_error_maps_status_headers_and_message(client, svc):
    svc.raises = AskError(429, "limit reached", headers={"Retry-After": "60"})
    r = client.post("/ask", json={"question": "hi"}, headers=auth())
    assert r.status_code == 429 and r.json() == {"error": "limit reached"}
    assert r.headers["retry-after"] == "60"


def test_unexpected_error_hides_detail(client, svc):
    svc.raises = RuntimeError("password=hunter2 stack detail")
    r = client.post("/ask", json={"question": "hi"}, headers=auth())
    assert r.status_code == 500 and r.json() == {"error": "internal error"}
    assert "hunter2" not in r.text


def test_health_needs_no_service_call(svc):
    svc.ask = svc.feedback = svc.version = None  # any call would raise TypeError
    assert TestClient(create_app(svc, CFG)).get("/health").json() == {"ok": True}


def test_version(client):
    assert client.get("/version").json()["docs_ref"] == "stable@abc"


def test_feedback_happy_path(client, svc):
    r = client.post("/feedback", headers=auth(),
                    json={"request_id": "rid-1", "rating": -1, "comment": "wrong key"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert svc.feedbacks == [("good", "rid-1", -1, "wrong key")]


@pytest.mark.parametrize("rating", [0, 2, "up", None])
def test_feedback_rating_must_be_1_or_minus_1(client, svc, rating):
    r = client.post("/feedback", headers=auth(), json={"request_id": "rid-1", "rating": rating})
    assert r.status_code == 422 and svc.feedbacks == []


def test_feedback_requires_token(client, svc):
    r = client.post("/feedback", json={"request_id": "rid-1", "rating": 1})
    assert r.status_code == 401 and svc.feedbacks == []


def test_build_from_env_connects_to_nothing_at_start(monkeypatch):
    for k, v in {"DATABASE_URL": "postgresql://nobody@127.0.0.1:1/none", "CF_ACCOUNT_ID": "a",
                 "CF_API_TOKEN": "t", "GROQ_API_KEY": "g"}.items():
        monkeypatch.setenv(k, v)
    assert TestClient(build_from_env()).get("/health").status_code == 200


def test_build_from_env_fails_fast_on_a_missing_key(monkeypatch):
    for k in ("DATABASE_URL", "CF_ACCOUNT_ID", "CF_API_TOKEN", "GROQ_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises((ValueError, KeyError)):
        build_from_env()
