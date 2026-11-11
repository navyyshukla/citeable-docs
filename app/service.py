"""One question, start to finish: token -> checks -> caps -> search -> answer -> log."""
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from app.answer import Citation, answer_question, validate_question
from app.classify import classify_question
from app.config import Config
from app.db import DbUnavailable
from app.llm.base import Adapter, AllProvidersFailed, ProviderError
from app.search import Searcher
from app.store import Store
from app.usage import CapHit, Usage
from ingest.models import Piece


_DB_DOWN = "The database is waking up. Try again in a minute."


class AskError(Exception):
    """An error the caller should see: HTTP status plus a safe message (never a stack trace)."""

    def __init__(self, status: int, message: str, headers: dict | None = None,
                 log: str | None = None):
        super().__init__(message)
        self.status, self.message = status, message
        self.headers = headers or {}
        self.log = log or message  # the detail that goes into the question log


@dataclass
class AskResult:
    request_id: str
    status: str
    text: str
    citations: list[Citation] = field(default_factory=list)
    closest: list[Citation] = field(default_factory=list)
    docs_ref: str | None = None
    docs_version: str | None = None
    last_updated: str | None = None
    kind: str | None = None  # which fixed card, when status == "card"


@dataclass
class _Index:
    searcher: Searcher
    by_id: dict[str, Piece]
    docs_ref: str | None
    docs_version: str | None
    last_updated: str | None


class AnswerService:
    def __init__(self, cfg: Config, usage: Usage, store: Store,
                 make_adapter: Callable[[], Adapter], embed_query: Callable[[str], list[float]]):
        self.cfg, self.usage, self.store = cfg, usage, store
        self.make_adapter, self.embed_query = make_adapter, embed_query
        self._index: _Index | None = None
        self._lock = threading.Lock()

    def _load_index(self) -> _Index:
        """Built on the first request, not at start-up: the 0.1 CPU instance is slow to start."""
        with self._lock:
            if self._index is not None:
                return self._index
            slug = self.cfg.project.slug
            try:
                self.store.check_ingest_meta(slug, self.cfg.models.embedding, require=True)
                pieces = self.store.load_pieces(slug)
            except DbUnavailable as e:
                raise AskError(503, _DB_DOWN, log=str(e)) from e
            except ValueError as e:
                raise AskError(503, "The docs index is not ready.", log=str(e)) from e
            if not pieces:
                raise AskError(503, "The docs index is not ready.", log="no pieces stored")
            searcher = Searcher(
                pieces, embed_query=self.embed_query,
                vector_search=lambda v, k: self.store.vector_search(slug, v, k),
                rrf_k=self.cfg.search.rrf_k)
            first = pieces[0]
            self._index = _Index(searcher, {p.id: p for p in pieces}, first.docs_ref,
                                 first.docs_version, first.last_updated)
            return self._index

    def version(self) -> dict:
        """What is being served. Never touches the database: docs_ref is None until the first
        question has loaded the index."""
        return {"project": self.cfg.project.slug,
                "docs_ref": self._index.docs_ref if self._index else None,
                "models": self.cfg.models.answer_order}

    def _token_id(self, token: str) -> int:
        try:
            tid = self.usage.token_id_for(token)
        except DbUnavailable as e:
            raise AskError(503, _DB_DOWN) from e
        if tid is None:
            raise AskError(401, "Unknown or revoked invite link.")
        return tid

    def ask(self, token: str, question: str) -> AskResult:
        token_id = self._token_id(token)
        try:
            q = validate_question(question, self.cfg)
        except ValueError as e:
            raise AskError(400, str(e)) from e
        lim = self.cfg.limits
        try:
            res = self.usage.reserve(token_id, self.cfg.project.slug, q,
                                     lim.per_visitor_daily_cap, lim.global_daily_cap,
                                     lim.global_daily_neurons)
        except DbUnavailable as e:
            raise AskError(503, _DB_DOWN) from e
        if isinstance(res, CapHit):
            wait = max(1, int((res.resets_at - datetime.now(timezone.utc)).total_seconds()))
            what = ("You have used your questions for today"
                    if res.kind == "visitor" else "The assistant has reached its limit for today")
            raise AskError(429, f"{what}. Try again after {res.resets_at:%H:%M} UTC.",
                           headers={"Retry-After": str(wait)}, log=f"cap: {res.kind}")
        rid = res.request_id
        index = adapter = None
        try:
            # A new adapter per request: its call and neuron counters are per request, and
            # requests run in parallel threads. The classifier and the answer share it, so the
            # neuron total and the call count cover both.
            adapter = self.make_adapter()
            kind = classify_question(q, adapter, self.cfg)
            classifier_calls = adapter.calls_made
            if kind != "normal":  # a fixed card: no search, no answer call, no docs index needed
                return self._card_reply(rid, kind, adapter)
            index = self._load_index()
            hits = index.searcher.search("hybrid", q, self.cfg.search.top_k)
            a = answer_question(q, hits, index.by_id, adapter, self.cfg, self.cfg.project.name,
                                self.cfg.search.evidence_threshold)
        except AskError as e:
            self._log_error(rid, e.log, index, adapter)
            raise
        except (AllProvidersFailed, ProviderError) as e:
            self._log_error(rid, str(e), index, adapter)
            raise AskError(503, "The answer models are busy. Try again in a minute.") from e
        except DbUnavailable as e:
            self._log_error(rid, str(e), index, adapter)
            raise AskError(503, _DB_DOWN) from e
        except Exception as e:
            self._log_error(rid, f"{type(e).__name__}: {e}", index, adapter)
            raise
        try:
            # Neurons of the whole request, not only the answering call: a provider that failed
            # first (a cut-off reply) still burned quota, and the daily neuron cap must see it.
            self.usage.finish(
                rid, status=a.status, answer_text=a.text,
                citations=[asdict(c) for c in a.citations], top_score=a.top_score,
                provider=a.provider, model=a.model,
                neurons=adapter.total_neurons if adapter.calls_made else None,
                llm_calls=a.llm_calls + classifier_calls, seconds=a.seconds, docs_ref=index.docs_ref, error=None,
                retrieved_ids=[h.piece_id for h in hits])
        except DbUnavailable:
            pass  # the answer exists and its neurons are spent: return it; the row stays reserved
        return AskResult(rid, a.status, a.text, a.citations, a.closest, index.docs_ref,
                         index.docs_version, index.last_updated)

    def _card_reply(self, request_id: str, kind: str, adapter: Adapter) -> AskResult:
        try:
            self.usage.finish(
                request_id, status="card", answer_text=f"card:{kind}", citations=[],
                top_score=None, provider=None, model=None,
                neurons=adapter.total_neurons if adapter.calls_made else None,
                llm_calls=adapter.calls_made, seconds=None, docs_ref=None, error=None)
        except DbUnavailable:
            pass  # the reply is free of the database: return it; the row stays reserved
        return AskResult(request_id, "card", "", kind=kind)

    def _log_error(self, request_id: str, error: str, index: _Index | None,
                   adapter: Adapter | None) -> None:
        # Failed attempts can still burn quota (a cut-off reply): keep it for the neuron cap.
        try:
            self.usage.finish(
                request_id, status="error", answer_text=None, citations=[], top_score=None,
                provider=None, model=None, neurons=adapter.total_neurons if adapter else None,
                llm_calls=adapter.calls_made if adapter else 0, seconds=None,
                docs_ref=index.docs_ref if index else None, error=error[:500])
        except DbUnavailable:
            pass  # never let a failed log write hide the original error

    def feedback(self, token: str, request_id: str, rating: int, comment: str | None) -> None:
        token_id = self._token_id(token)
        try:
            ok = self.usage.add_feedback(token_id, request_id, rating, comment)
        except ValueError as e:
            raise AskError(400, str(e)) from e
        except DbUnavailable as e:
            raise AskError(503, _DB_DOWN) from e
        if not ok:
            raise AskError(404, "No such request.")
