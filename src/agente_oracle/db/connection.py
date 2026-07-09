from contextlib import contextmanager

import oracledb

from agente_oracle.config import settings

_pool: oracledb.ConnectionPool | None = None


def get_pool() -> oracledb.ConnectionPool:
    global _pool
    if _pool is None:
        _pool = oracledb.create_pool(
            user=settings.oracle_user,
            password=settings.oracle_password,
            dsn=settings.oracle_dsn,
            min=settings.oracle_pool_min,
            max=settings.oracle_pool_max,
            increment=settings.oracle_pool_increment,
        )
    return _pool


@contextmanager
def get_connection():
    pool = get_pool()
    connection = pool.acquire()
    try:
        yield connection
    finally:
        pool.release(connection)
