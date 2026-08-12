"""Confere que os middlewares novos (CORS restrito + headers de segurança,
`server/app.py:criar_app`) não quebram uma rota que responde em streaming
(NDJSON) — a fixture `mcp_app` compartilhada usa `mcp.streamable_http_app()`
puro, sem os middlewares de produção, então não serve pra flagrar esse tipo
de problema (`starlette.middleware.base.BaseHTTPMiddleware`, usado nos
headers de segurança, já teve versões antigas que bufferizavam a resposta
inteira antes de deixar passar, quebrando streaming de verdade)."""

import json

import pytest
from starlette.testclient import TestClient

from agente_oracle.server.app import criar_app
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


def test_rota_de_streaming_funciona_com_os_middlewares_de_producao(token_teste):
    cliente = TestClient(criar_app())

    resposta = cliente.get(
        "/api/financeiro/previsao/vendas",
        params={"filial": _FILIAL},
        headers={"Authorization": f"Bearer {token_teste}"},
    )

    assert resposta.status_code == 200
    linhas = [json.loads(linha) for linha in resposta.text.strip().splitlines()]
    assert linhas[-1]["tipo"] == "resultado"
    assert resposta.headers.get("x-content-type-options") == "nosniff"
