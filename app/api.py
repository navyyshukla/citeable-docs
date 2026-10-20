"""HTTP layer: JSON in, JSON out. All decisions live in AnswerService; this maps errors."""
import json
import os
from dataclasses import asdict
from typing import Literal

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StrictStr, ValidationError

from app.config import Config, load_config
from app.db import Db
from app.llm.build import build_adapter
from app.llm.cloudflare import CloudflareClient, embed_texts
from app.service import AnswerService, AskError, AskResult
from app.store import Store
from app.usage import Usage

MAX_BODY_BYTES = 4096


class AskIn(BaseModel):
    question: StrictStr


class FeedbackIn(BaseModel):
    request_id: StrictStr
    rating: Literal[1, -1]
    comment: StrictStr | None = None


def _token(request: Request) -> str:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AskError(401, "Missing invite token.", headers={"WWW-Authenticate": "Bearer"})
    return token.strip()


async def _json_body(request: Request) -> dict:
    """Read at most MAX_BODY_BYTES, whether or not the client declares a length."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise AskError(413, "Request too large.")
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > MAX_BODY_BYTES:
            raise AskError(413, "Request too large.")
    try:
        body = json.loads(bytes(data))
    except ValueError as e:
        raise AskError(400, "Body must be JSON.") from e
    if not isinstance(body, dict):
        raise AskError(422, "Body must be a JSON object.")
    return body


def _parse(model, body: dict):
    try:
        return model.model_validate(body)
    except ValidationError as e:
        # Say which fields are wrong, never echo their values back.
        fields = ", ".join(sorted({str(err["loc"][0]) for err in e.errors() if err["loc"]}))
        raise AskError(422, f"Invalid request: check {fields or 'the body'}.") from e


def _result_json(r: AskResult, notice: str) -> dict:
    return {"request_id": r.request_id, "status": r.status, "text": r.text,
            "citations": [asdict(c) for c in r.citations],
            "closest": [asdict(c) for c in r.closest],
            "docs_ref": r.docs_ref, "docs_version": r.docs_version,
            "last_updated": r.last_updated, "notice": notice}


def create_app(service: AnswerService, cfg: Config) -> FastAPI:
    app = FastAPI(title="Citeable Docs API", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=cfg.api.cors_origins,
                       allow_methods=["GET", "POST"],
                       allow_headers=["Authorization", "Content-Type"])

    @app.exception_handler(AskError)
    async def _ask_error(request: Request, e: AskError):
        return JSONResponse({"error": e.message}, status_code=e.status, headers=e.headers)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, e: Exception):
        # No detail on purpose: it could carry a question, a key or a stack trace.
        return JSONResponse({"error": "internal error"}, status_code=500)

    # Plain `def` endpoints run in a thread pool: the database and HTTP clients are blocking.
    @app.post("/ask")
    def ask(token: str = Depends(_token), body: dict = Depends(_json_body)):
        q = _parse(AskIn, body)
        return _result_json(service.ask(token, q.question), cfg.project.license_note)

    @app.post("/feedback")
    def feedback(token: str = Depends(_token), body: dict = Depends(_json_body)):
        f = _parse(FeedbackIn, body)
        service.feedback(token, f.request_id, f.rating, f.comment)
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"ok": True}  # no database, no token: Render's check must not wake Neon

    @app.get("/version")
    def version():
        return service.version()

    return app


def build_from_env() -> FastAPI:
    """uvicorn --factory app.api:build_from_env. Nothing connects until the first request."""
    cfg = load_config(os.environ.get("CONFIG_PATH", "config/visidata.yaml"))
    dsn = os.environ["DATABASE_URL"]
    client = httpx.Client(timeout=60)  # shared by all requests; httpx clients are thread-safe

    def make_adapter():
        return build_adapter(cfg, os.environ, client)

    make_adapter()  # fail at start-up, not at the first question, if a key is missing
    cf = CloudflareClient(os.environ["CF_ACCOUNT_ID"], os.environ["CF_API_TOKEN"], client)
    db = Db(dsn)
    service = AnswerService(
        cfg, Usage(db), Store(db, cfg.models.embedding_dim, vector_index=cfg.search.vector_index),
        make_adapter, lambda t: embed_texts(cf, cfg.models.embedding, [t], 1)[0])
    return create_app(service, cfg)
