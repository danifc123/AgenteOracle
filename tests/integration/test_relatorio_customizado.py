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
            "Views curadas (vwia_titulos_pagar etc.) não existem no banco de negócio/RAG "
            "configurado — rode db/views/financeiro_science.sql (Oracle) ou confira o Postgres de teste."
        )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_gera_relatorio_com_colunas_de_uma_view(mcp_app, token_teste):
    resposta = mcp_app.get(
        "/api/financeiro/relatorio-customizado",
        params={"filial": _FILIAL, "colunas": "vwia_titulos_pagar.filial,vwia_titulos_pagar.valor_original"},
        headers=_auth(token_teste),
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert isinstance(corpo, list)
    if corpo:
        assert set(corpo[0].keys()) == {"vwia_titulos_pagar.filial", "vwia_titulos_pagar.valor_original"}


def test_gera_relatorio_com_join_automatico_entre_views_relacionadas(mcp_app, token_teste):
    resposta = mcp_app.get(
        "/api/financeiro/relatorio-customizado",
        params={
            "filial": _FILIAL,
            "colunas": "vwia_titulos_pagar.filial,vwia_titulos_pagar.valor_original,vwia_fornecedores.nome",
        },
        headers=_auth(token_teste),
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert isinstance(corpo, list)
    if corpo:
        assert "vwia_fornecedores.nome" in corpo[0]


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
        params={"colunas": "vwia_titulos_pagar.filial"},
        headers=_auth(token_teste),
    )
    assert resposta.status_code == 400


def test_sem_token_e_nao_autorizado(mcp_app):
    resposta = mcp_app.get(
        "/api/financeiro/relatorio-customizado",
        params={"filial": _FILIAL, "colunas": "vwia_titulos_pagar.filial"},
    )
    assert resposta.status_code == 401


class TestOpcoesColuna:
    """`/api/financeiro/relatorio/opcoes-coluna` aceita várias colunas numa
    chamada só (`colunas=view.col1,view.col2,...`) — antes era uma coluna
    por requisição, e a tela "Criar Relatório" chamava em loop ao aplicar
    um layout salvo com várias colunas de texto."""

    def test_devolve_opcoes_de_varias_colunas_numa_chamada_so(self, mcp_app, token_teste):
        resposta = mcp_app.get(
            "/api/financeiro/relatorio/opcoes-coluna",
            params={"colunas": "vwia_clientes.nome,vwia_titulos_pagar.fornecedor_nome"},
            headers=_auth(token_teste),
        )
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert set(corpo.keys()) == {"vwia_clientes.nome", "vwia_titulos_pagar.fornecedor_nome"}
        assert isinstance(corpo["vwia_clientes.nome"], list)

    def test_rejeita_coluna_sem_filtro_por_lista_de_valores(self, mcp_app, token_teste):
        # "valor_original" é tipo "numero" (só faixa min/máx) — não tem modo lista.
        resposta = mcp_app.get(
            "/api/financeiro/relatorio/opcoes-coluna",
            params={"colunas": "vwia_titulos_pagar.valor_original"},
            headers=_auth(token_teste),
        )
        assert resposta.status_code == 400

    def test_uma_coluna_invalida_rejeita_o_lote_inteiro(self, mcp_app, token_teste):
        resposta = mcp_app.get(
            "/api/financeiro/relatorio/opcoes-coluna",
            params={"colunas": "vwia_clientes.nome,view_que_nao_existe.coluna"},
            headers=_auth(token_teste),
        )
        assert resposta.status_code == 400

    def test_sem_colunas_e_rejeitado(self, mcp_app, token_teste):
        resposta = mcp_app.get(
            "/api/financeiro/relatorio/opcoes-coluna",
            params={"colunas": ""},
            headers=_auth(token_teste),
        )
        assert resposta.status_code == 400

    def test_sem_token_e_nao_autorizado(self, mcp_app):
        resposta = mcp_app.get(
            "/api/financeiro/relatorio/opcoes-coluna", params={"colunas": "vwia_clientes.nome"}
        )
        assert resposta.status_code == 401
