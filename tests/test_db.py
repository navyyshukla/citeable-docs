import threading
from contextlib import contextmanager

import psycopg
import pytest
from psycopg_pool import PoolTimeout

from app.db import Db, DbUnavailable


class FakePool:
    """Stands in for a psycopg pool: each open() pops one flag from `fail_opens`: True means it times out."""

    def __init__(self, log: list, fail_opens: list[bool]):
        self.log, self.fail_opens, self.closed = log, fail_opens, False
        self.fail_connection: Exception | None = None
        self.gate: threading.Event | None = None

    def open(self, wait: bool, timeout: float) -> None:
        self.log.append("open")
        if self.gate:
            self.gate.wait(5)
        if self.fail_opens and self.fail_opens.pop(0):
            raise PoolTimeout("down")

    @contextmanager
    def connection(self):
        if self.fail_connection:
            raise self.fail_connection
        yield "conn"

    def close(self) -> None:
        self.closed = True


def make_db(failures: list[bool], retries: int = 4, gate=None, clock=None):
    log: list = []
    sleeps: list[float] = []
    pools: list[FakePool] = []

    def factory(dsn, min_size, max_size):
        pool = FakePool(log, failures)
        pool.gate = gate
        pools.append(pool)
        return pool

    extra = {"clock": clock} if clock else {}
    db = Db("postgresql://x", connect_retries=retries, retry_delay=5.0,
            pool_factory=factory, sleep=sleeps.append, **extra)
    return db, log, sleeps, pools


def test_pool_is_not_opened_until_first_use():
    db, log, _, pools = make_db([])
    assert log == [] and pools == []
    db.close()  # closing a never-used Db is fine


def test_first_connect_retries_then_succeeds():
    db, log, sleeps, pools = make_db([True, True, False])
    with db.conn() as c:
        assert c == "conn"
    assert log == ["open"] * 3
    assert sleeps == [5.0, 5.0]
    assert [p.closed for p in pools] == [True, True, False]  # failed pools are not leaked


def test_gives_up_after_retries():
    db, log, sleeps, _ = make_db([True] * 4, retries=4)
    with pytest.raises(DbUnavailable), db.conn():
        pass
    assert len(log) == 4 and len(sleeps) == 3  # no sleep after the last attempt


def test_opened_pool_is_reused():
    db, log, _, _ = make_db([False])
    with db.conn(), db.conn():
        pass
    assert log == ["open"]


def test_a_failed_open_makes_later_callers_fail_fast_until_the_pause_ends():
    now = [100.0]
    db, log, _, _ = make_db([True] * 4 + [False], retries=4, clock=lambda: now[0])
    with pytest.raises(DbUnavailable), db.conn():
        pass
    assert len(log) == 4
    with pytest.raises(DbUnavailable), db.conn():  # still inside the pause: no new attempts
        pass
    assert len(log) == 4
    now[0] += 31
    with db.conn() as c:  # pause over: one more try, which now works
        assert c == "conn"
    assert len(log) == 5


def test_requests_waiting_on_a_down_database_do_not_each_run_their_own_retry_cycle():
    gate = threading.Event()
    db, log, _, _ = make_db([True] * 4, retries=4, gate=gate)
    errors: list[Exception] = []

    def call():
        try:
            with db.conn():
                pass
        except DbUnavailable as e:
            errors.append(e)

    threads = [threading.Thread(target=call) for _ in range(3)]
    for t in threads:
        t.start()
    gate.set()
    for t in threads:
        t.join(10)
    assert len(errors) == 3 and len(log) == 4  # one retry cycle served all three


def test_pool_timeout_after_the_pool_is_open_becomes_db_unavailable():
    db, _, _, pools = make_db([False])
    with db.conn():
        pass
    pools[0].fail_connection = PoolTimeout("no connection in 30 s")
    with pytest.raises(DbUnavailable), db.conn():
        pass


def test_connection_lost_mid_query_becomes_db_unavailable():
    db, *_ = make_db([False])
    with pytest.raises(DbUnavailable), db.conn():
        raise psycopg.OperationalError("server closed the connection")


def test_other_database_errors_are_not_disguised():
    db, *_ = make_db([False])
    with pytest.raises(psycopg.errors.UniqueViolation), db.conn():
        raise psycopg.errors.UniqueViolation("dup")
