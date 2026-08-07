"""Testa `/api/financeiro/previsao/vendas` e `/api/financeiro/previsao/fluxo-caixa`
de ponta a ponta contra o Postgres de teste. As duas rotas respondem em
NDJSON (uma linha de etapa por vez, terminando em `{"tipo": "resultado",
...}`) — `_parse_ndjson` reconstrói a lista de etapas e o corpo final. 100%
cálculo estatístico (sem IA/Ollama envolvido em nenhuma etapa)."""

import json

import pytest

pytestmark = pytest.mark.integration

_FILIAL = "0101"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _parse_ndjson(texto: str) -> tuple[list[str], dict]:
    etapas = []
    resultado = None
    for linha in texto.strip().splitlines():
        objeto = json.loads(linha)
        if objeto["tipo"] == "etapa":
            etapas.append(objeto["id"])
        elif objeto["tipo"] == "resultado":
            resultado = objeto["dados"]
    return etapas, resultado


def test_previsao_vendas_devolve_historico_e_projecao(mcp_app, token_teste):
    resposta = mcp_app.get(
        "/api/financeiro/previsao/vendas", params={"filial": _FILIAL}, headers=_auth(token_teste)
    )
    assert resposta.status_code == 200
    etapas, corpo = _parse_ndjson(resposta.text)
    assert etapas == ["historico", "projecao"]
    assert isinstance(corpo["historico"], list)
    assert isinstance(corpo["projecao"], list)
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
    etapas, corpo = _parse_ndjson(resposta.text)
    assert etapas == ["titulos_abertos", "prazo_medio", "projecao_futura"]

    assert corpo["meses"][0]["mes"] == "vencido"
    assert len(corpo["meses"]) == 7  # vencido + 6 meses seguintes
    assert {item["nome"] for item in corpo["fatias_a_receber"]} == {"No período", "Fora do período"}
    assert corpo["total_a_receber"] == sum(item["valor"] for item in corpo["fatias_a_receber"])
    assert corpo["total_a_pagar"] == sum(item["valor"] for item in corpo["fatias_a_pagar"])

    assert isinstance(corpo["prazo_medio_recebimento_dias"], (int, float))
    assert isinstance(corpo["prazo_medio_pagamento_dias"], (int, float))

    # O bucket "vencido" nunca recebe estimativa — estimado == confirmado ali.
    vencido = corpo["meses"][0]
    assert vencido["a_receber_estimado"] == vencido["a_receber"]
    assert vencido["a_pagar_estimado"] == vencido["a_pagar"]

    # Nos demais meses, o estimado nunca é menor que o confirmado (a
    # estimativa só soma, nunca subtrai).
    for item in corpo["meses"][1:]:
        assert item["a_receber_estimado"] >= item["a_receber"]
        assert item["a_pagar_estimado"] >= item["a_pagar"]


def test_previsao_fluxo_caixa_sem_filial_e_rejeitado(mcp_app, token_teste):
    resposta = mcp_app.get("/api/financeiro/previsao/fluxo-caixa", headers=_auth(token_teste))
    assert resposta.status_code == 400


def test_previsao_fluxo_caixa_sem_token_e_nao_autorizado(mcp_app):
    resposta = mcp_app.get("/api/financeiro/previsao/fluxo-caixa", params={"filial": _FILIAL})
    assert resposta.status_code == 401
