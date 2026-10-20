"""A small connection pool in front of Neon.

Neon free suspends after idle time: the first connect can fail for up to a minute, and a new
connection costs about 1.5 s (spike S9). So the pool opens lazily, retries the first connect,
and checks a connection before handing it out (idle ones may have been dropped by the pooler).
"""
import threading
import time
from collections.abc import Callable

from psycopg_pool import ConnectionPool, PoolTimeout


class DbUnavailable(Exception):
    """The database did not answer within the retry window."""


def _real_pool(dsn: str, min_size: int, max_size: int) -> ConnectionPool:
    return ConnectionPool(dsn, min_size=min_size, max_size=max_size, open=False,
                          check=ConnectionPool.check_connection,
                          kwargs={"connect_timeout": 15})


class Db:
    def __init__(self, dsn: str, min_size: int = 1, max_size: int = 4,
                 connect_retries: int = 4, retry_delay: float = 5.0,
                 pool_factory: Callable = _real_pool, sleep: Callable[[float], None] = time.sleep):
        self.dsn, self.min_size, self.max_size = dsn, min_size, max_size
        self.connect_retries, self.retry_delay = connect_retries, retry_delay
        self._factory, self._sleep = pool_factory, sleep
        self._pool = None
        self._lock = threading.Lock()

    def _open(self):
        for attempt in range(1, self.connect_retries + 1):
            pool = self._factory(self.dsn, self.min_size, self.max_size)
            try:
                pool.open(wait=True, timeout=20)
                return pool
            except PoolTimeout:
                pool.close()  # a failed pool cannot be reopened: build a fresh one next time
                if attempt < self.connect_retries:
                    self._sleep(self.retry_delay)
        raise DbUnavailable(f"database did not answer after {self.connect_retries} attempts")

    def conn(self):
        """Use as `with db.conn() as c:`; the connection goes back to the pool afterwards."""
        with self._lock:
            if self._pool is None:
                self._pool = self._open()
        return self._pool.connection()

    def close(self) -> None:
        with self._lock:
            if self._pool is not None:
                self._pool.close()
                self._pool = None
