"""Fixtures dos testes de integração — exigem o Postgres de teste local
(configs `POSTGRES_*` do `.env`) rodando de verdade. Independente de
`DB_BACKEND`: login/token de usuário (`token_teste`/`usuario_teste` abaixo)
sempre passam por `get_postgres_connection()` (ver `db/connection.py`), que
nunca depende desse valor — só a query de dado de negócio/RAG depende, e é
isso que `test_relatorios_oracle_hml.py` verifica à parte.

Toda a pasta `tests/integration/` pula automaticamente (em vez de falhar) se
o Postgres de teste não estiver acessível, para o resto da suíte continuar
utilizável sem depender de infraestrutura externa.
"""

import uuid

import psycopg
import pytest

from agente_oracle.config import settings
from agente_oracle.db.connection import DatabaseError, get_connection, get_postgres_connection

# Tabelas de trilha de auditoria — nunca expiram por design (ver docstrings
# de `tools/auth/eventos_seguranca.py`/`tools/auditoria/historico.py`), então
# nenhum código de produção tem uma função de apagar linha. A grande maioria
# dos testes de integração passa por login de verdade (fixtures `token_teste`/
# `token_dev` abaixo) ou aciona rotas do módulo de Auditoria, e cada um desses
# grava uma linha real nessas tabelas — como é o MESMO Postgres que a
# aplicação de verdade usa pra esse estado (`get_postgres_connection` não
# depende de `DB_BACKEND`), sem limpeza esse "lixo de teste" ficava pra
# sempre visível nas telas reais (log de segurança, Auditoria). Ver
# `_limpar_trilhas_de_auditoria` abaixo.
_TABELAS_TRILHA_AUDITORIA = (
    "eventos_seguranca",
    "auditoria_historico",
    "auditoria_dispensados",
    "ti_acessos_dados",
    "ti_seguranca_historico",
)


def _postgres_disponivel() -> bool:
    try:
        with psycopg.connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            dbname=settings.postgres_db,
            user=settings.postgres_user,
            password=settings.postgres_password,
            connect_timeout=2,
        ):
            return True
    except psycopg.Error:
        return False


def views_curadas_disponiveis() -> bool:
    """As views curadas (`vw_titulos_pagar` etc.) existem no banco de
    negócio/RAG configurado em `DB_BACKEND`? No Postgres de teste elas já
    existem (criadas manualmente); no Oracle, dependem do DBA rodar
    `db/views/financeiro_science.sql` — ver `test_relatorios_oracle_hml.py`, que
    testa os relatórios fixos (raw tables) à parte disso."""
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM vw_titulos_pagar")
            cursor.fetchone()
        return True
    except DatabaseError:
        return False


@pytest.fixture(autouse=True)
def _requer_postgres_de_teste():
    if not _postgres_disponivel():
        pytest.skip(
            "Postgres de teste não está acessível — configure DB_BACKEND=postgres no .env e suba o banco."
        )


def _garantir_tabelas_trilha_auditoria() -> None:
    """Chama as próprias funções de consulta de cada módulo (que já fazem
    `CREATE TABLE IF NOT EXISTS` sozinhas) pra garantir que as tabelas
    existem antes do checkpoint — evita duplicar essa criação aqui, e evita
    o `SELECT MAX(id)` do checkpoint falhar com "tabela não existe" na
    primeira vez que a suíte roda contra um Postgres novo."""
    from agente_oracle.tools.auditoria import dispensados, historico
    from agente_oracle.tools.auth import eventos_seguranca
    from agente_oracle.tools.ti import acessos_dados, historico_seguranca

    eventos_seguranca.listar(limite=1)
    historico.achados_ativos(["financeiro"])
    dispensados.listar_dispensados("_")
    acessos_dados.perfil_acessos(dias=1)
    historico_seguranca.achados_ativos()


@pytest.fixture(autouse=True)
def _limpar_trilhas_de_auditoria(_requer_postgres_de_teste):
    """Apaga, no fim de CADA teste, só as linhas de `_TABELAS_TRILHA_AUDITORIA`
    inseridas DURANTE esse teste (por id, comparado com um checkpoint tirado
    antes) — nunca o que já existia. Roda mesmo se o teste falhar (o teardown
    de uma fixture com `yield` sempre executa), que é justamente o cenário
    que motivou isso: um teste falhar DEPOIS de já ter gravado o evento/achado,
    deixando lixo pra trás sem ninguém perceber."""
    _garantir_tabelas_trilha_auditoria()

    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        checkpoints = {}
        for tabela in _TABELAS_TRILHA_AUDITORIA:
            cursor.execute(f"SELECT COALESCE(MAX(id), 0) FROM {tabela}")
            checkpoints[tabela] = cursor.fetchone()[0]

    yield

    with get_postgres_connection() as connection:
        cursor = connection.cursor()
        for tabela, checkpoint in checkpoints.items():
            cursor.execute(f"DELETE FROM {tabela} WHERE id > :id", id=checkpoint)


@pytest.fixture
def mcp_app():
    """Cliente HTTP contra o app Starlette real (mesmas rotas de produção)."""
    from starlette.testclient import TestClient

    from agente_oracle.server.app import mcp

    app = mcp.streamable_http_app()
    return TestClient(app)


@pytest.fixture
def usuario_teste():
    """Cria um usuário com papel `financeiro` no banco de teste, com login
    aleatório (não colide com contas reais), e apaga no fim do teste."""
    from agente_oracle.tools.auth import usuarios as usuarios_tools

    login = f"teste_{uuid.uuid4().hex[:12]}"
    senha = "SenhaDeTeste!123"
    criado = usuarios_tools.criar_usuario(login, senha, "Usuário de Teste (integração)", ["financeiro"])

    yield {"usuario": login, "senha": senha, "id": criado["id"]}

    usuarios_tools.deletar_usuario(criado["id"])


@pytest.fixture
def token_teste(mcp_app, usuario_teste):
    """Token JWT válido para `usuario_teste`, via login real (mesma rota que o frontend usa)."""
    resposta = mcp_app.post(
        "/api/auth/login", json={"usuario": usuario_teste["usuario"], "senha": usuario_teste["senha"]}
    )
    assert resposta.status_code == 200
    return resposta.json()["token"]


@pytest.fixture
def usuario_dev():
    """Mesma ideia de `usuario_teste`, mas com papel `desenvolvedor` (time de
    TI) — usado pra testar ações restritas a esse papel, como desbloquear
    uma conta travada."""
    from agente_oracle.tools.auth import usuarios as usuarios_tools

    login = f"teste_dev_{uuid.uuid4().hex[:12]}"
    senha = "SenhaDeTeste!123"
    criado = usuarios_tools.criar_usuario(login, senha, "Dev de Teste (integração)", ["desenvolvedor"])

    yield {"usuario": login, "senha": senha, "id": criado["id"]}

    usuarios_tools.deletar_usuario(criado["id"])


@pytest.fixture
def token_dev(mcp_app, usuario_dev):
    """Token JWT válido para `usuario_dev`."""
    resposta = mcp_app.post(
        "/api/auth/login", json={"usuario": usuario_dev["usuario"], "senha": usuario_dev["senha"]}
    )
    assert resposta.status_code == 200
    return resposta.json()["token"]
