"""Invite tokens, the question log, daily caps and feedback, all in Postgres.

Free tiers and a handful of friends: counting rows in one table is enough, survives Render
restarts, and the log doubles as the held-out question set (decision D16: no Redis).
"""
import hashlib
import json
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from psycopg import errors

from app.answer import BAD_CHARS
from app.db import Db

_LOCK_KEY = 7001  # advisory lock that serialises cap checks
# A 'reserved' row that never finished (the process died mid-request) stops counting after this.
_RESERVED_GRACE = "5 minutes"
# What counts against a cap: answered and abstained questions, questions still in flight, and
# failed questions that still burned neurons (else one visitor could drain the shared budget with
# prompts that overrun the token cap). A failed question that burned nothing is free.
_COUNTS = f"""(status IN ('answered', 'abstained')
               OR (status = 'reserved' AND created_at > now() - interval '{_RESERVED_GRACE}')
               OR (status = 'error' AND COALESCE(neurons, 0) > 0))"""
# The shared request cap stays friendlier: failed questions are free there.
_COUNTS_GLOBAL = f"""(status IN ('answered', 'abstained')
               OR (status = 'reserved' AND created_at > now() - interval '{_RESERVED_GRACE}'))"""
_TOKEN_SHAPE = re.compile(r"[A-Za-z0-9_-]{43}")  # what secrets.token_urlsafe(32) produces


def looks_like_token(token: str) -> bool:
    """Cheap check before any database call: junk tokens must not wake Neon."""
    return _TOKEN_SHAPE.fullmatch(token) is not None
_MAX_COMMENT = 500


def hash_token(token: str) -> str:
    """Tokens are 32 random bytes, so a fast hash is enough (no password hashing needed)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Reservation:
    request_id: str


@dataclass(frozen=True)
class CapHit:
    kind: Literal["visitor", "global", "neurons"]
    resets_at: datetime


@dataclass(frozen=True)
class TokenInfo:
    label: str
    created_at: datetime
    revoked: bool
    questions_today: int


def _day_start() -> datetime:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


class Usage:
    def __init__(self, db: Db):
        self.db = db

    def init_schema(self) -> None:
        with self.db.conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS invite_tokens (
                    id SERIAL PRIMARY KEY,
                    label TEXT NOT NULL UNIQUE,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    revoked_at TIMESTAMPTZ)""")
            c.execute("""
                CREATE TABLE IF NOT EXISTS questions (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    token_id INT NOT NULL REFERENCES invite_tokens(id),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    project TEXT NOT NULL,
                    question TEXT NOT NULL,
                    status TEXT NOT NULL,
                    answer_text TEXT,
                    citations JSONB,
                    top_score DOUBLE PRECISION,
                    provider TEXT,
                    model TEXT,
                    neurons DOUBLE PRECISION,
                    llm_calls INT,
                    seconds DOUBLE PRECISION,
                    docs_ref TEXT,
                    error TEXT)""")
            # Added in Plan 3a: an existing table (production) gets the column on the next run.
            c.execute("ALTER TABLE questions ADD COLUMN IF NOT EXISTS retrieved_ids JSONB")
            c.execute("CREATE INDEX IF NOT EXISTS questions_created_at ON questions (created_at)")
            c.execute("""
                CREATE TABLE IF NOT EXISTS feedback (
                    request_id UUID PRIMARY KEY REFERENCES questions(id) ON DELETE CASCADE,
                    rating SMALLINT NOT NULL,
                    comment TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")

    # ---- tokens ----
    def create_token(self, label: str) -> str:
        """Returns the plain token once; only its hash is stored."""
        token = secrets.token_urlsafe(32)
        try:
            with self.db.conn() as c:
                c.execute("INSERT INTO invite_tokens (label, token_hash) VALUES (%s, %s)",
                          (label, hash_token(token)))
        except errors.UniqueViolation as e:
            raise ValueError(f"a token labelled {label!r} already exists") from e
        return token

    def revoke_token(self, label: str) -> bool:
        with self.db.conn() as c:
            cur = c.execute("UPDATE invite_tokens SET revoked_at = now() "
                            "WHERE label = %s AND revoked_at IS NULL", (label,))
            return cur.rowcount == 1

    def token_id_for(self, token: str) -> int | None:
        with self.db.conn() as c:
            row = c.execute("SELECT id FROM invite_tokens "
                            "WHERE token_hash = %s AND revoked_at IS NULL",
                            (hash_token(token),)).fetchone()
        return row[0] if row else None

    def list_tokens(self) -> list[TokenInfo]:
        with self.db.conn() as c:
            rows = c.execute(
                """SELECT t.label, t.created_at, t.revoked_at IS NOT NULL, count(q.id)
                   FROM invite_tokens t
                   LEFT JOIN questions q ON q.token_id = t.id AND q.created_at >= %s
                   GROUP BY t.id ORDER BY t.id""", (_day_start(),)).fetchall()
        return [TokenInfo(*r) for r in rows]

    # ---- question log and caps ----
    def reserve(self, token_id: int, project: str, question: str, per_visitor: int,
                global_cap: int, neuron_budget: float) -> Reservation | CapHit:
        """Check the three daily caps and log the question as 'reserved', atomically."""
        start = _day_start()
        resets = start + timedelta(days=1)
        with self.db.conn() as c, c.transaction():
            c.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK_KEY,))
            (visitor,) = c.execute(
                f"SELECT count(*) FROM questions WHERE created_at >= %s AND token_id = %s "
                f"AND {_COUNTS}", (start, token_id)).fetchone()
            if visitor >= per_visitor:
                return CapHit("visitor", resets)
            (total,) = c.execute(
                f"SELECT count(*) FROM questions WHERE created_at >= %s AND {_COUNTS_GLOBAL}",
                (start,)).fetchone()
            if total >= global_cap:
                return CapHit("global", resets)
            # Neurons count from every row: a failed attempt can still burn quota.
            (spent,) = c.execute("SELECT COALESCE(sum(neurons), 0) FROM questions "
                                 "WHERE created_at >= %s", (start,)).fetchone()
            if spent >= neuron_budget:
                return CapHit("neurons", resets)
            (rid,) = c.execute(
                "INSERT INTO questions (token_id, project, question, status) "
                "VALUES (%s, %s, %s, 'reserved') RETURNING id", (token_id, project, question)
            ).fetchone()
        return Reservation(str(rid))

    def finish(self, request_id: str, *, status: Literal["answered", "abstained", "error"],
               answer_text: str | None, citations: list[dict], top_score: float | None,
               provider: str | None, model: str | None, neurons: float | None, llm_calls: int,
               seconds: float | None, docs_ref: str | None, error: str | None,
               retrieved_ids: list[str] | None = None) -> None:
        with self.db.conn() as c:
            c.execute(
                """UPDATE questions SET status = %s, answer_text = %s, citations = %s,
                       top_score = %s, provider = %s, model = %s, neurons = %s, llm_calls = %s,
                       seconds = %s, docs_ref = %s, error = %s, retrieved_ids = %s
                       WHERE id = %s""",
                (status, answer_text, json.dumps(citations), top_score, provider, model,
                 neurons, llm_calls, seconds, docs_ref, error,
                 None if retrieved_ids is None else json.dumps(retrieved_ids), request_id))

    # ---- feedback ----
    def add_feedback(self, token_id: int, request_id: str, rating: int,
                     comment: str | None) -> bool:
        if rating not in (-1, 1):
            raise ValueError("rating must be 1 or -1")
        if comment is not None and len(comment) > _MAX_COMMENT:
            raise ValueError(f"comment longer than {_MAX_COMMENT} characters")
        if comment is not None and BAD_CHARS.search(comment):
            raise ValueError("comment contains characters that are not allowed")
        try:
            rid = str(uuid.UUID(request_id))
        except ValueError:
            return False
        with self.db.conn() as c:
            row = c.execute("SELECT token_id FROM questions WHERE id = %s", (rid,)).fetchone()
            if not row or row[0] != token_id:
                return False
            c.execute(
                """INSERT INTO feedback (request_id, rating, comment) VALUES (%s, %s, %s)
                   ON CONFLICT (request_id) DO UPDATE SET rating = EXCLUDED.rating,
                       comment = EXCLUDED.comment, created_at = now()""",
                (rid, rating, comment))
        return True

    # ---- retention ----
    def purge(self, older_than_days: int) -> int:
        with self.db.conn() as c:
            cur = c.execute("DELETE FROM questions WHERE created_at < now() - %s * interval "
                            "'1 day'", (older_than_days,))
            return cur.rowcount

