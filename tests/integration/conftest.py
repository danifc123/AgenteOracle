"""Fixtures dos testes de integração — exigem o Postgres de teste local
(`DB_BACKEND=postgres`, configurado no `.env`) rodando de verdade.

Toda a pasta `tests/integration/` pula automaticamente (em vez de falhar) se
esse banco não estiver acessível, para o resto da suíte continuar utilizável
sem depender de infraestrutura externa.
"""

import psycopg
import pytest

from agente_oracle.config import settings


def _postgres_disponivel() -> bool:
    if settings.db_backend != "postgres":
        return False
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


@pytest.fixture(autouse=True)
def _requer_postgres_de_teste():
    if not _postgres_disponivel():
        pytest.skip("Postgres de teste não está acessível — configure DB_BACKEND=postgres no .env e suba o banco.")


@pytest.fixture
def mcp_app():
    """Cliente HTTP contra o app Starlette real (mesmas rotas de produção)."""
    from starlette.testclient import TestClient

    from agente_oracle.server.app import mcp

    app = mcp.streamable_http_app()
    return TestClient(app)
