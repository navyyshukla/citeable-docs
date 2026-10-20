"""A small connection pool in front of Neon.

Neon free suspends after idle time: the first connect can fail for up to a minute, and a new
connection costs about 1.5 s (spike S9). So the pool opens lazily, retries the first connect,
and checks a connection before handing it out (idle ones may have been dropped by the pooler).

Every way of not reaching the database, at open time or later, surfaces as DbUnavailable, so the
API can answer 503 instead of crashing.
"""
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager

import psycopg
from psycopg_pool import ConnectionPool, PoolTimeout

PAUSE_AFTER_FAILURE = 30.0  # seconds callers fail fast after a whole retry cycle has failed


class DbUnavailable(Exception):
    """The database did not answer within the retry window."""


def _real_pool(dsn: str, min_size: int, max_size: int) -> ConnectionPool:
    return ConnectionPool(dsn, min_size=min_size, max_size=max_size, open=False,
                          check=ConnectionPool.check_connection,
                          kwargs={"connect_timeout": 15})


class Db:
    def __init__(self, dsn: str, min_size: int = 1, max_size: int = 4,
                 connect_retries: int = 4, retry_delay: float = 5.0,
                 pool_factory: Callable = _real_pool, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self.dsn, self.min_size, self.max_size = dsn, min_size, max_size
        self.connect_retries, self.retry_delay = connect_retries, retry_delay
        self._factory, self._sleep, self._clock = pool_factory, sleep, clock
        self._pool = None
        self._down_until = 0.0
        self._lock = threading.Lock()

    def _open(self):
        for attempt in range(1, self.connect_retries + 1):
            pool = self._factory(self.dsn, self.min_size, self.max_size)
            try:
                pool.open(wait=True, timeout=15)
                return pool
            except PoolTimeout:
                pool.close()  # a failed pool cannot be reopened: build a fresh one next time
                if attempt < self.connect_retries:
                    self._sleep(self.retry_delay)
        raise DbUnavailable(f"database did not answer after {self.connect_retries} attempts")

    def _get_pool(self):
        with self._lock:
            if self._pool is None:
                # Callers that queued behind a failing retry cycle must not each start their own
                # (that would make the Nth caller wait N cycles): they fail fast instead.
                if self._clock() < self._down_until:
                    raise DbUnavailable("database is unavailable (recent attempts failed)")
                try:
                    self._pool = self._open()
                except DbUnavailable:
                    self._down_until = self._clock() + PAUSE_AFTER_FAILURE
                    raise
            return self._pool

    @contextmanager
    def conn(self):
        """Use as `with db.conn() as c:`; the connection goes back to the pool afterwards."""
        pool = self._get_pool()
        try:
            with pool.connection() as c:
                yield c
        except (PoolTimeout, psycopg.OperationalError) as e:
            raise DbUnavailable(f"database connection failed: {type(e).__name__}") from e

    def close(self) -> None:
        with self._lock:
            if self._pool is not None:
                self._pool.close()
                self._pool = None
