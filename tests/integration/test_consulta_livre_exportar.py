"""Testa `/api/financeiro/relatorio/exportar` (exportação em Excel da "consulta
livre", usada pelo chat com IA) de ponta a ponta — em especial que o exploit de
junção por vírgula (`FROM a, b`) corrigido nesta sessão continua bloqueado
quando chamado via HTTP direto, sem precisar da IA gerar o SQL."""

import pytest

from tests.integration.conftest import views_curadas_disponiveis

pytestmark = pytest.mark.integration

_URL = "/api/financeiro/relatorio/exportar"


@pytest.fixture(autouse=True)
def _requer_views_curadas():
    if not views_curadas_disponiveis():
        pytest.skip(
            "Views curadas (vw_titulos_pagar etc.) não existem no banco de negócio/RAG "
            "configurado — rode db/views/financeiro_science.sql (Oracle) ou confira o Postgres de teste."
        )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_sql_valido_devolve_xlsx(mcp_app, token_teste):
    resposta = mcp_app.post(
        _URL,
        json={"sql": "SELECT filial, valor_original FROM vw_titulos_pagar"},
        headers=_auth(token_teste),
    )
    assert resposta.status_code == 200
    assert (
        resposta.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def test_juncao_por_virgula_continua_bloqueada(mcp_app, token_teste):
    """O exploit real encontrado na auditoria desta sessão: `FROM a, b` deixava
    a whitelist de tabelas enxergar só a primeira, permitindo ler qualquer
    tabela do banco (ex: `usuarios`, com hash de senha) via a segunda."""
    resposta = mcp_app.post(
        _URL,
        json={"sql": "SELECT u.usuario, u.senha_hash FROM vw_titulos_pagar t, usuarios u"},
        headers=_auth(token_teste),
    )
    assert resposta.status_code == 400
    assert "JOIN" in resposta.json()["erro"]


def test_tabela_fora_do_escopo_e_bloqueada(mcp_app, token_teste):
    resposta = mcp_app.post(_URL, json={"sql": "SELECT * FROM usuarios"}, headers=_auth(token_teste))
    assert resposta.status_code == 400


def test_sem_token_e_nao_autorizado(mcp_app):
    resposta = mcp_app.post(_URL, json={"sql": "SELECT * FROM vw_titulos_pagar"})
    assert resposta.status_code == 401
