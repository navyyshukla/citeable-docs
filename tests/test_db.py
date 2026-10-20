import pytest
from psycopg_pool import PoolTimeout

from app.db import Db, DbUnavailable


class FakePool:
    """Stands in for a psycopg pool: each open() pops one flag from `fail_opens`: True means it times out."""

    def __init__(self, log: list, fail_opens: list[bool]):
        self.log, self.fail_opens, self.closed = log, fail_opens, False

    def open(self, wait: bool, timeout: float) -> None:
        self.log.append("open")
        if self.fail_opens and self.fail_opens.pop(0):
            raise PoolTimeout("down")

    def connection(self):
        return "conn-context"

    def close(self) -> None:
        self.closed = True


def make_db(failures: list[bool], retries: int = 4):
    log: list = []
    sleeps: list[float] = []
    pools: list[FakePool] = []

    def factory(dsn, min_size, max_size):
        pool = FakePool(log, failures)
        pools.append(pool)
        return pool

    db = Db("postgresql://x", connect_retries=retries, retry_delay=5.0,
            pool_factory=factory, sleep=sleeps.append)
    return db, log, sleeps, pools


def test_pool_is_not_opened_until_first_use():
    db, log, _, pools = make_db([])
    assert log == [] and pools == []
    db.close()  # closing a never-used Db is fine


def test_first_connect_retries_then_succeeds():
    db, log, sleeps, pools = make_db([True, True, False])
    assert db.conn() == "conn-context"
    assert log == ["open"] * 3
    assert sleeps == [5.0, 5.0]
    assert [p.closed for p in pools] == [True, True, False]  # failed pools are not leaked


def test_gives_up_after_retries():
    db, log, sleeps, _ = make_db([True] * 4, retries=4)
    with pytest.raises(DbUnavailable):
        db.conn()
    assert len(log) == 4 and len(sleeps) == 3  # no sleep after the last attempt


def test_opened_pool_is_reused():
    db, log, _, _ = make_db([False])
    db.conn()
    db.conn()
    assert log == ["open"]
