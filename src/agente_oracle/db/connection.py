"""Duas conexões relacionais, com propósitos fixos e independentes:

- `get_postgres_connection`: SEMPRE Postgres (configs `POSTGRES_*`) — estado
  do próprio sistema (usuários, trilha de auditoria de login, histórico de
  relatórios, layouts, cores de categoria). Nunca depende de `DB_BACKEND`.
- `get_connection`: dado de negócio/RAG financeiro (views do Protheus) —
  aponta pro banco escolhido em `DB_BACKEND` (Oracle em produção; Postgres
  localmente, contra views de teste, já que o Oracle real não é acessível
  fora de produção).

IMPORTANTE — por que ter `vw_titulos_receber` (e as outras 6 views curadas
do Financeiro) em DOIS bancos ao mesmo tempo NÃO causa consulta indo pro
lugar errado: `get_connection` decide o POOL (Oracle ou Postgres) uma vez,
ANTES de qualquer SQL ser executado — é uma decisão por `DB_BACKEND`
(`.env`), nunca pelo texto da query. Cada pool já é uma conexão de rede
comprometida com UM servidor só (o DSN do Oracle, ou o host do Postgres);
o nome da view só é resolvido pelo servidor do outro lado daquele socket
específico — Oracle nunca "vê" a cópia do Postgres, e vice-versa. O nome
repetido é só rótulo (mesma tabela mental, propositalmente com o mesmo
nome pra facilitar o desenvolvedor), não um vínculo real entre os bancos.

Essas 7 views de teste no Postgres (`vw_titulos_pagar`, `vw_titulos_receber`,
`vw_clientes`, `vw_fornecedores`, `vw_faturamento`, `vw_lancamentos_contabeis`,
`vw_safra_cliente`) existem DE PROPÓSITO, mantidas mesmo com `DB_BACKEND=
oracle` em uso — servem pra desenvolver/testar sem depender do Oracle real
estar acessível (VPN, credencial, etc.), e pros testes de integração
(`tests/integration/conftest.py::views_curadas_disponiveis`) rodarem
localmente. Não precisam ser apagadas nem geram risco de mistura — só
ficam inertes enquanto `DB_BACKEND=oracle`.

IMPORTANTE (achado em 2026-08, verificado direto no banco): essas views NÃO
vêm de `db/views/financeiro_science.sql` — aquele arquivo é sintaxe Oracle
(`TRIM(x)`, `CAST(x AS DATE)`) e cria as views reais no schema Oracle. As
views de teste no Postgres são outra definição, em sintaxe Postgres
(`TRIM(BOTH FROM x)`, `x::date`), contra um schema `stage.*` próprio criado
ali dentro do Postgres — e o SQL que criou esse schema/views de teste **não
está versionado neste repositório** (procurei: só existem dois `.sql` no
projeto, `financeiro_science.sql` e `protheus/login_seguranca.sql`, nenhum
dos dois é isso). Ou seja, se essas 7 views forem apagadas algum dia, NÃO
dá pra recriar só rodando um arquivo existente — precisaria escrever a
versão Postgres de novo (ou achar onde esse setup original foi feito, fora
do git). Enquanto elas continuarem existindo como estão, sem problema
nenhum — só documentando esse risco pra quem for mexer nisso no futuro."""

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
