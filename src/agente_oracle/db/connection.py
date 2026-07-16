import re
from contextlib import contextmanager

import oracledb
import psycopg
from psycopg_pool import ConnectionPool as PostgresPool

from agente_oracle.config import settings

# O lookbehind negativo evita casar o segundo ":" de um cast Postgres
# ("::varchar", "::int"), que senão seria confundido com um bind novo.
_BIND_REGEX = re.compile(r"(?<!:):(\w+)\b")

DatabaseError = (oracledb.DatabaseError, psycopg.Error)

_oracle_pool: oracledb.ConnectionPool | None = None
_postgres_pool: PostgresPool | None = None


def eh_erro_coluna_invalida(erro: Exception) -> bool:
    """Detecta, de forma independente do banco, se o erro é uma referência a
    uma coluna que não existe (ORA-00904 no Oracle, sqlstate 42703 no Postgres)."""
    if isinstance(erro, psycopg.Error):
        return getattr(erro, "sqlstate", None) == "42703"
    return "ORA-00904" in str(erro)


class _CursorAdapter:
    """Uniformiza a chamada `cursor.execute(sql, **binds)` (estilo oracledb,
    com binds nomeados `:nome`) para os dois bancos: no Oracle passa direto;
    no Postgres reescreve `:nome` para `%(nome)s` e envia os binds como dict."""

    def __init__(self, cursor, backend: str):
        self._cursor = cursor
        self._backend = backend

    def execute(self, sql: str, **binds):
        if self._backend == "postgres" and binds:
            sql = _BIND_REGEX.sub(r"%(\1)s", sql)
            self._cursor.execute(sql, binds)
        else:
            self._cursor.execute(sql, **binds)
        return self

    def fetchall(self):
        return self._cursor.fetchall()

    def fetchone(self):
        return self._cursor.fetchone()

    @property
    def description(self):
        return self._cursor.description


class _ConnectionAdapter:
    def __init__(self, connection, backend: str):
        self._connection = connection
        self._backend = backend

    def cursor(self) -> _CursorAdapter:
        return _CursorAdapter(self._connection.cursor(), self._backend)

    @property
    def call_timeout(self):
        return getattr(self._connection, "call_timeout", None)

    @call_timeout.setter
    def call_timeout(self, milissegundos: int):
        if self._backend == "postgres":
            with self._connection.cursor() as cursor:
                cursor.execute("SET statement_timeout = %s", (milissegundos,))
        else:
            self._connection.call_timeout = milissegundos


def _get_oracle_pool() -> oracledb.ConnectionPool:
    global _oracle_pool
    if _oracle_pool is None:
        if settings.oracle_client_lib_dir:
            oracledb.init_oracle_client(lib_dir=settings.oracle_client_lib_dir)
        _oracle_pool = oracledb.create_pool(
            user=settings.oracle_user,
            password=settings.oracle_password,
            dsn=settings.oracle_dsn,
            min=settings.oracle_pool_min,
            max=settings.oracle_pool_max,
            increment=settings.oracle_pool_increment,
        )
    return _oracle_pool


def _get_postgres_pool() -> PostgresPool:
    global _postgres_pool
    if _postgres_pool is None:
        conninfo = (
            f"host={settings.postgres_host} port={settings.postgres_port} "
            f"dbname={settings.postgres_db} user={settings.postgres_user} "
            f"password={settings.postgres_password}"
        )
        _postgres_pool = PostgresPool(
            conninfo,
            min_size=settings.postgres_pool_min,
            max_size=settings.postgres_pool_max,
            open=True,
        )
    return _postgres_pool


@contextmanager
def get_connection():
    if settings.db_backend == "postgres":
        pool = _get_postgres_pool()
        with pool.connection() as connection:
            yield _ConnectionAdapter(connection, "postgres")
    else:
        pool = _get_oracle_pool()
        connection = pool.acquire()
        try:
            yield _ConnectionAdapter(connection, "oracle")
        finally:
            pool.release(connection)
