import os
import threading
from datetime import datetime, timedelta, timezone

import pytest

from app.db import Db
from app.usage import CapHit, Reservation, Usage, hash_token

DSN = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")

BIG = 10_000  # a cap nobody reaches


@pytest.fixture(scope="module")
def shared():
    u = Usage(Db(DSN))  # one pool for the file: a new Neon connection costs seconds
    u.init_schema()
    yield u
    u.db.close()


@pytest.fixture
def usage(shared):
    def wipe():
        # The test branch holds no real data: clear the whole usage tables, not just our rows.
        with shared.db.conn() as c:
            c.execute("TRUNCATE feedback, questions, invite_tokens RESTART IDENTITY CASCADE")
    wipe()
    yield shared
    wipe()


def reserve(u: Usage, token_id: int, per_visitor=BIG, global_cap=BIG, neurons=1e9):
    return u.reserve(token_id, "visidata", "how do I join?", per_visitor, global_cap, neurons)


def finish(u: Usage, request_id: str, status="answered", neurons=None, answer="ok"):
    u.finish(request_id, status=status, answer_text=answer, citations=[], top_score=0.03,
             provider="p", model="m", neurons=neurons, llm_calls=1, seconds=1.0,
             docs_ref="stable@abc", error=None)


def test_token_roundtrip_stores_only_hash(usage):
    token = usage.create_token("t-ann")
    assert usage.token_id_for(token) is not None
    with usage.db.conn() as c:
        rows = c.execute("SELECT label, token_hash FROM invite_tokens").fetchall()
    assert rows == [("t-ann", hash_token(token))]
    assert token not in rows[0][1]
    assert usage.token_id_for("not-a-token") is None


def test_revoked_token_unknown(usage):
    token = usage.create_token("t-ann")
    assert usage.revoke_token("t-ann") is True
    assert usage.token_id_for(token) is None
    assert usage.revoke_token("t-nobody") is False


def test_duplicate_label_is_rejected(usage):
    usage.create_token("t-ann")
    with pytest.raises(ValueError, match="t-ann"):
        usage.create_token("t-ann")


def test_per_visitor_cap_blocks_the_eleventh(usage):
    tid = usage.token_id_for(usage.create_token("t-ann"))
    for _ in range(10):
        assert isinstance(reserve(usage, tid, per_visitor=10), Reservation)
    hit = reserve(usage, tid, per_visitor=10)
    assert isinstance(hit, CapHit) and hit.kind == "visitor"
    assert hit.resets_at > datetime.now(timezone.utc)
    assert hit.resets_at - datetime.now(timezone.utc) <= timedelta(days=1)


def test_global_cap(usage):
    a = usage.token_id_for(usage.create_token("t-a"))
    b = usage.token_id_for(usage.create_token("t-b"))
    assert isinstance(reserve(usage, a, global_cap=2), Reservation)
    assert isinstance(reserve(usage, b, global_cap=2), Reservation)
    hit = reserve(usage, a, global_cap=2)
    assert isinstance(hit, CapHit) and hit.kind == "global"


def test_neuron_budget_cap(usage):
    tid = usage.token_id_for(usage.create_token("t-ann"))
    for n in (5000.0, 3500.0):
        r = reserve(usage, tid, neurons=8000)
        finish(usage, r.request_id, neurons=n)
    hit = reserve(usage, tid, neurons=8000)
    assert isinstance(hit, CapHit) and hit.kind == "neurons"


def test_error_rows_do_not_count_against_request_caps(usage):
    tid = usage.token_id_for(usage.create_token("t-ann"))
    r = reserve(usage, tid, per_visitor=1)
    finish(usage, r.request_id, status="error", answer=None)
    assert isinstance(reserve(usage, tid, per_visitor=1), Reservation)


def test_abstained_rows_count(usage):
    tid = usage.token_id_for(usage.create_token("t-ann"))
    r = reserve(usage, tid, per_visitor=1)
    finish(usage, r.request_id, status="abstained")
    assert isinstance(reserve(usage, tid, per_visitor=1), CapHit)


def test_parallel_reserve_never_overshoots(usage):
    tid = usage.token_id_for(usage.create_token("t-ann"))
    results: list = []

    def go():
        results.append(reserve(usage, tid, per_visitor=10))

    threads = [threading.Thread(target=go) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(isinstance(r, Reservation) for r in results) == 10
    assert sum(isinstance(r, CapHit) for r in results) == 2


def test_finish_stores_the_answer(usage):
    tid = usage.token_id_for(usage.create_token("t-ann"))
    r = reserve(usage, tid)
    finish(usage, r.request_id, neurons=12.5, answer="use gv")
    with usage.db.conn() as c:
        row = c.execute("SELECT status, answer_text, neurons, docs_ref FROM questions").fetchone()
    assert row == ("answered", "use gv", 12.5, "stable@abc")


def _retrieved(u: Usage, rid: str):
    with u.db.conn() as c:
        return c.execute("SELECT retrieved_ids FROM questions WHERE id = %s", (rid,)).fetchone()[0]


def test_finish_stores_retrieved_ids(usage):
    tid = usage.token_id_for(usage.create_token("t-ann"))
    rid = reserve(usage, tid).request_id
    usage.finish(rid, status="answered", answer_text="ok", citations=[], top_score=0.03,
                 provider="p", model="m", neurons=None, llm_calls=1, seconds=1.0,
                 docs_ref="stable@abc", error=None, retrieved_ids=["a:1", "b:2"])
    assert _retrieved(usage, rid) == ["a:1", "b:2"]


def test_finish_without_retrieved_ids_leaves_null(usage):
    tid = usage.token_id_for(usage.create_token("t-ann"))
    rid = reserve(usage, tid).request_id
    finish(usage, rid)
    assert _retrieved(usage, rid) is None


def test_init_schema_adds_column_to_an_existing_table(usage):
    tid = usage.token_id_for(usage.create_token("t-ann"))
    rid = reserve(usage, tid).request_id
    with usage.db.conn() as c:
        c.execute("ALTER TABLE questions DROP COLUMN retrieved_ids")
    usage.init_schema()  # an old table, as production has it today
    usage.finish(rid, status="answered", answer_text="ok", citations=[], top_score=0.03,
                 provider="p", model="m", neurons=None, llm_calls=1, seconds=1.0,
                 docs_ref="stable@abc", error=None, retrieved_ids=["a:1", "b:2"])
    assert _retrieved(usage, rid) == ["a:1", "b:2"]


def test_feedback_only_for_own_request(usage):
    a = usage.token_id_for(usage.create_token("t-a"))
    b = usage.token_id_for(usage.create_token("t-b"))
    r = reserve(usage, a)
    assert usage.add_feedback(b, r.request_id, 1, None) is False
    assert usage.add_feedback(a, r.request_id, -1, "wrong key") is True
    assert usage.add_feedback(a, "not-a-uuid", 1, None) is False
    assert usage.add_feedback(a, "00000000-0000-0000-0000-000000000000", 1, None) is False


def test_feedback_can_be_changed_not_duplicated(usage):
    a = usage.token_id_for(usage.create_token("t-a"))
    r = reserve(usage, a)
    usage.add_feedback(a, r.request_id, 1, None)
    usage.add_feedback(a, r.request_id, -1, None)
    with usage.db.conn() as c:
        assert c.execute("SELECT rating FROM feedback").fetchall() == [(-1,)]


def test_feedback_comment_too_long(usage):
    a = usage.token_id_for(usage.create_token("t-a"))
    r = reserve(usage, a)
    with pytest.raises(ValueError, match="500"):
        usage.add_feedback(a, r.request_id, 1, "x" * 501)


def test_feedback_rating_must_be_plus_or_minus_one(usage):
    a = usage.token_id_for(usage.create_token("t-a"))
    r = reserve(usage, a)
    with pytest.raises(ValueError, match="rating"):
        usage.add_feedback(a, r.request_id, 5, None)


def test_purge_deletes_old_rows_and_their_feedback(usage):
    a = usage.token_id_for(usage.create_token("t-a"))
    old, new = reserve(usage, a), reserve(usage, a)
    usage.add_feedback(a, old.request_id, 1, None)
    with usage.db.conn() as c:
        c.execute("UPDATE questions SET created_at = now() - interval '40 days' WHERE id = %s",
                  (old.request_id,))
    assert usage.purge(older_than_days=30) == 1
    with usage.db.conn() as c:
        assert c.execute("SELECT count(*) FROM questions").fetchone() == (1,)
        assert c.execute("SELECT count(*) FROM feedback").fetchone() == (0,)
    assert new.request_id


def test_list_tokens_shows_labels_and_counts_never_hashes(usage):
    token = usage.create_token("t-ann")
    usage.create_token("t-bob")
    usage.revoke_token("t-bob")
    tid = usage.token_id_for(token)
    reserve(usage, tid)
    infos = {i.label: i for i in usage.list_tokens()}
    assert infos["t-ann"].questions_today == 1 and infos["t-ann"].revoked is False
    assert infos["t-bob"].revoked is True
    assert not any(hasattr(i, "token_hash") for i in infos.values())


def test_no_ip_column(usage):
    with usage.db.conn() as c:
        cols = [r[0] for r in c.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name IN ('questions','feedback','invite_tokens')").fetchall()]
    assert not [x for x in cols if "ip" in x.split("_") or "address" in x or "remote" in x]


def test_an_old_orphan_reserved_row_stops_counting_but_a_fresh_one_still_does(usage):
    tid = usage.token_id_for(usage.create_token("t-ann"))
    old = reserve(usage, tid, per_visitor=1)
    with usage.db.conn() as c:  # a restart mid-request left this row 'reserved' for ever
        c.execute("UPDATE questions SET created_at = now() - interval '10 minutes' WHERE id = %s",
                  (old.request_id,))
    fresh = reserve(usage, tid, per_visitor=1)
    assert isinstance(fresh, Reservation)  # the orphan did not use the visitor's only slot
    assert isinstance(reserve(usage, tid, per_visitor=1), CapHit)  # the fresh one does


def test_failed_questions_that_burned_neurons_count_for_that_visitor(usage):
    a = usage.token_id_for(usage.create_token("t-a"))
    b = usage.token_id_for(usage.create_token("t-b"))
    r = reserve(usage, a, per_visitor=1)
    finish(usage, r.request_id, status="error", neurons=40.0, answer=None)
    hit = reserve(usage, a, per_visitor=1)
    assert isinstance(hit, CapHit) and hit.kind == "visitor"
    assert isinstance(reserve(usage, b, per_visitor=1), Reservation)  # others are unaffected


def test_failed_questions_that_burned_nothing_stay_free(usage):
    a = usage.token_id_for(usage.create_token("t-a"))
    for neurons in (None, 0.0):
        r = reserve(usage, a, per_visitor=1)
        assert isinstance(r, Reservation)
        finish(usage, r.request_id, status="error", neurons=neurons, answer=None)
