"""Testa `/api/financeiro/relatorio-customizado/exportar-linhas` — gera o
.xlsx a partir das linhas que a TELA manda no corpo (já carregadas via
"Carregar mais"), sem reconsultar o banco. Por isso, ao contrário de
`test_relatorio_customizado.py`, não depende das views curadas
(`vw_titulos_pagar` etc.) existirem no banco de negócio/RAG — não faz
nenhuma consulta lá, só monta a planilha a partir do que recebe."""

import pytest

pytestmark = pytest.mark.integration

_ROTA = "/api/financeiro/relatorio-customizado/exportar-linhas"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_exportar_devolve_xlsx(mcp_app, token_teste):
    resposta = mcp_app.post(
        _ROTA,
        json={"colunas": ["filial", "valor_original"], "linhas": [["0101", 100], ["0101", 200]]},
        headers=_auth(token_teste),
    )
    assert resposta.status_code == 200
    assert (
        resposta.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def test_rejeita_linha_com_tamanho_diferente_das_colunas(mcp_app, token_teste):
    resposta = mcp_app.post(
        _ROTA,
        json={"colunas": ["filial", "valor_original"], "linhas": [["0101"]]},
        headers=_auth(token_teste),
    )
    assert resposta.status_code == 400


def test_sem_colunas_e_rejeitado(mcp_app, token_teste):
    resposta = mcp_app.post(_ROTA, json={"colunas": [], "linhas": []}, headers=_auth(token_teste))
    assert resposta.status_code == 400


def test_sem_token_e_nao_autorizado(mcp_app):
    resposta = mcp_app.post(_ROTA, json={"colunas": ["filial"], "linhas": [["0101"]]})
    assert resposta.status_code == 401
