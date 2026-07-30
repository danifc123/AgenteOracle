"""Testa `/api/financeiro/previsao/vendas` e `/api/financeiro/previsao/fluxo-caixa`
de ponta a ponta contra o Postgres de teste — a IA (Ollama) pode não estar
disponível no ambiente de CI, então a análise cai no fallback nesse caso, o
que já é o comportamento esperado (ver `agent/financeiro/projecoes.gerar_analise`)."""

import pytest

pytestmark = pytest.mark.integration

_FILIAL = "0101"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_previsao_vendas_devolve_historico_e_projecao(mcp_app, token_teste):
    resposta = mcp_app.get(
        "/api/financeiro/previsao/vendas", params={"filial": _FILIAL}, headers=_auth(token_teste)
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert isinstance(corpo["historico"], list)
    assert isinstance(corpo["projecao"], list)
    assert isinstance(corpo["analise"], str) and corpo["analise"]
    if corpo["historico"]:
        assert set(corpo["historico"][0].keys()) == {"mes", "valor"}


def test_previsao_vendas_sem_filial_e_rejeitado(mcp_app, token_teste):
    resposta = mcp_app.get("/api/financeiro/previsao/vendas", headers=_auth(token_teste))
    assert resposta.status_code == 400


def test_previsao_vendas_sem_token_e_nao_autorizado(mcp_app):
    resposta = mcp_app.get("/api/financeiro/previsao/vendas", params={"filial": _FILIAL})
    assert resposta.status_code == 401


def test_previsao_fluxo_caixa_devolve_meses_e_fatias(mcp_app, token_teste):
    resposta = mcp_app.get(
        "/api/financeiro/previsao/fluxo-caixa", params={"filial": _FILIAL}, headers=_auth(token_teste)
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["meses"][0]["mes"] == "vencido"
    assert len(corpo["meses"]) == 7  # vencido + 6 meses seguintes
    assert {item["nome"] for item in corpo["fatias_a_receber"]} == {"No período", "Fora do período"}
    assert corpo["total_a_receber"] == sum(item["valor"] for item in corpo["fatias_a_receber"])
    assert corpo["total_a_pagar"] == sum(item["valor"] for item in corpo["fatias_a_pagar"])


def test_previsao_fluxo_caixa_sem_filial_e_rejeitado(mcp_app, token_teste):
    resposta = mcp_app.get("/api/financeiro/previsao/fluxo-caixa", headers=_auth(token_teste))
    assert resposta.status_code == 400


def test_previsao_fluxo_caixa_sem_token_e_nao_autorizado(mcp_app):
    resposta = mcp_app.get("/api/financeiro/previsao/fluxo-caixa", params={"filial": _FILIAL})
    assert resposta.status_code == 401
