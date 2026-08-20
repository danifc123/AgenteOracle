"""Testa `/api/financeiro/relatorio-customizado` de ponta a ponta: monta o
SELECT dinâmico (com JOIN automático entre views relacionadas) e roda contra
o Postgres de teste de verdade."""

import pytest

from tests.integration.conftest import views_curadas_disponiveis

pytestmark = pytest.mark.integration

_FILIAL = "0101"


@pytest.fixture(autouse=True)
def _requer_views_curadas():
    if not views_curadas_disponiveis():
        pytest.skip(
            "Views curadas (vw_titulos_pagar etc.) não existem no banco de negócio/RAG "
            "configurado — rode db/views/financeiro_science.sql (Oracle) ou confira o Postgres de teste."
        )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_gera_relatorio_com_colunas_de_uma_view(mcp_app, token_teste):
    resposta = mcp_app.get(
        "/api/financeiro/relatorio-customizado",
        params={"filial": _FILIAL, "colunas": "vw_titulos_pagar.filial,vw_titulos_pagar.valor_original"},
        headers=_auth(token_teste),
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert isinstance(corpo, list)
    if corpo:
        assert set(corpo[0].keys()) == {"vw_titulos_pagar.filial", "vw_titulos_pagar.valor_original"}


def test_gera_relatorio_com_join_automatico_entre_views_relacionadas(mcp_app, token_teste):
    resposta = mcp_app.get(
        "/api/financeiro/relatorio-customizado",
        params={
            "filial": _FILIAL,
            "colunas": "vw_titulos_pagar.filial,vw_titulos_pagar.valor_original,vw_fornecedores.nome",
        },
        headers=_auth(token_teste),
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert isinstance(corpo, list)
    if corpo:
        assert "vw_fornecedores.nome" in corpo[0]


def test_rejeita_coluna_fora_do_formato_view_ponto_coluna(mcp_app, token_teste):
    resposta = mcp_app.get(
        "/api/financeiro/relatorio-customizado",
        params={"filial": _FILIAL, "colunas": "coluna_sem_view"},
        headers=_auth(token_teste),
    )
    assert resposta.status_code == 400


def test_rejeita_view_inexistente(mcp_app, token_teste):
    resposta = mcp_app.get(
        "/api/financeiro/relatorio-customizado",
        params={"filial": _FILIAL, "colunas": "view_que_nao_existe.coluna"},
        headers=_auth(token_teste),
    )
    assert resposta.status_code == 400


def test_sem_filial_e_rejeitado(mcp_app, token_teste):
    resposta = mcp_app.get(
        "/api/financeiro/relatorio-customizado",
        params={"colunas": "vw_titulos_pagar.filial"},
        headers=_auth(token_teste),
    )
    assert resposta.status_code == 400


def test_sem_token_e_nao_autorizado(mcp_app):
    resposta = mcp_app.get(
        "/api/financeiro/relatorio-customizado",
        params={"filial": _FILIAL, "colunas": "vw_titulos_pagar.filial"},
    )
    assert resposta.status_code == 401


def test_exportar_devolve_xlsx(mcp_app, token_teste):
    resposta = mcp_app.get(
        "/api/financeiro/relatorio-customizado/exportar",
        params={"filial": _FILIAL, "colunas": "vw_titulos_pagar.filial,vw_titulos_pagar.valor_original"},
        headers=_auth(token_teste),
    )
    assert resposta.status_code == 200
    assert (
        resposta.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
