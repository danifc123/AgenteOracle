"""Duas conexões relacionais, com propósitos fixos e independentes:

- `get_postgres_connection`: SEMPRE Postgres (configs `POSTGRES_*`) — estado
  do próprio sistema (usuários, trilha de auditoria de login, histórico de
  relatórios, layouts, cores de categoria). Nunca depende de `DB_BACKEND`.
- `get_connection`: dado de negócio/RAG financeiro (views do Protheus) —
  aponta pro banco escolhido em `DB_BACKEND` (Oracle em produção; Postgres
  localmente, contra views de teste, já que o Oracle real não é acessível
  fora de produção).
"""

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
_protheus_pool: oracledb.ConnectionPool | None = None
_oracle_client_inicializado = False


def eh_erro_coluna_invalida(erro: Exception) -> bool:
    """Detecta, de forma independente do banco, se o erro é uma referência a
    uma coluna que não existe (ORA-00904 no Oracle, sqlstate 42703 no Postgres)."""
    if isinstance(erro, psycopg.Error):
        return getattr(erro, "sqlstate", None) == "42703"
    return "ORA-00904" in str(erro)


def eh_erro_valor_duplicado(erro: Exception) -> bool:
    """Detecta, de forma independente do banco, se o erro é uma violação de
    constraint única/chave duplicada (ORA-00001 no Oracle, sqlstate 23505 no
    Postgres)."""
    if isinstance(erro, psycopg.Error):
        return getattr(erro, "sqlstate", None) == "23505"
    return "ORA-00001" in str(erro)


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


@contextmanager
def get_postgres_connection():
    pool = _get_postgres_pool()
    with pool.connection() as connection:
        yield _ConnectionAdapter(connection, "postgres")


@contextmanager
def get_protheus_connection():
    """Conexão só-leitura e independente com o Oracle do Protheus (login/
    auditoria de usuário — `tools/ti/protheus_login.py`), separada da
    conexão de negócio (`get_connection`, que fala com o STAGE/BI) — pool
    próprio, nunca compartilha nada com o STAGE. Só chamar depois de
    conferir `protheus_configurado()`."""
    pool = _get_protheus_pool()
    connection = pool.acquire()
    try:
        yield _ConnectionAdapter(connection, "oracle")
    finally:
        pool.release(connection)


def protheus_configurado() -> bool:
    """`False` quando `PROTHEUS_DSN` não foi definido no `.env` — quem
    chama trata isso como "sem essa fonte de dado disponível", nunca como
    erro (ver `tools/ti/protheus_login.py`)."""
    return bool(settings.protheus_dsn)


class _ConnectionAdapter:
    def __init__(self, connection, backend: str):
        self._connection = connection
        self._backend = backend

    def cursor(self) -> "_CursorAdapter":
        return _CursorAdapter(self._connection.cursor(), self._backend)

    @property
    def call_timeout(self):
        return getattr(self._connection, "call_timeout", None)

    @call_timeout.setter
    def call_timeout(self, milissegundos: int):
        if self._backend == "postgres":
            # SET não aceita bind parameter no Postgres (precisa ser um literal na
            # própria instrução) — seguro fazer format direto aqui porque o valor
            # vem sempre de uma constante interna (TIMEOUT_MS), nunca de entrada
            # do usuário/IA.
            with self._connection.cursor() as cursor:
                cursor.execute(f"SET statement_timeout = {int(milissegundos)}")
        else:
            self._connection.call_timeout = milissegundos


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

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount


def _garantir_oracle_client_inicializado() -> None:
    """`oracledb.init_oracle_client` só pode ser chamado uma vez por
    processo — como `_get_oracle_pool` e `_get_protheus_pool` são dois
    pools independentes que podem precisar dele, essa checagem evita
    chamar duas vezes (o que derrubaria o segundo pool com erro)."""
    global _oracle_client_inicializado
    if _oracle_client_inicializado or not settings.oracle_client_lib_dir:
        return
    oracledb.init_oracle_client(lib_dir=settings.oracle_client_lib_dir)
    _oracle_client_inicializado = True


def _get_oracle_pool() -> oracledb.ConnectionPool:
    global _oracle_pool
    if _oracle_pool is None:
        _garantir_oracle_client_inicializado()
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


def _get_protheus_pool() -> oracledb.ConnectionPool:
    global _protheus_pool
    if _protheus_pool is None:
        _garantir_oracle_client_inicializado()
        _protheus_pool = oracledb.create_pool(
            user=settings.protheus_user,
            password=settings.protheus_password,
            dsn=settings.protheus_dsn,
            min=settings.protheus_pool_min,
            max=settings.protheus_pool_max,
            increment=settings.protheus_pool_increment,
        )
    return _protheus_pool
