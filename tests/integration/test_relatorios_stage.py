"""Smoke test dos relatórios fixos do Financeiro contra o banco de negócio/
RAG real (SCIENCE_PROD, schema STAGE) — complementa, não substitui, a suíte
determinística de `test_relatorio_customizado.py`/`test_previsao.py` (que
roda contra o Postgres de teste, com dado seedado e conhecido).

Substitui `test_relatorios_oracle_hml.py` (removido) — os relatórios fixos
deste módulo foram migrados de tabela crua do Protheus (`SE1010`/`SE2010`/
`SE5010`...) para o STAGE (`STAGE.CONTARECEBER`/`CONTAPAGAR`/
`MOVIMENTACAOFINANCEIRA`...), então o smoke test precisa apontar pra lá
também. Ver README ("Views curadas do Financeiro") e o topo de cada
`relatorios/*.py` migrado pro histórico dessa mudança.

`baixa_produtos.py` e `retencao_impostos.py` ficaram de fora desta suíte de
propósito — nenhum dos dois foi migrado pro STAGE (sem tabela/vínculo
equivalente confirmado; ver os próprios arquivos), então continuam
consultando tabela que não existe nem no STAGE nem no Postgres de teste
(removido) — rodar contra eles daria erro sempre, não é o tipo de bug que
este smoke test existe pra pegar.

Propósito bem específico: pegar erro de dialeto SQL/nome de tabela/coluna
que só aparece contra o Oracle real (ex: `ORA-12704` de charset em
comparação com coluna `NVARCHAR2`, `ORA-00904` de identificador depois de
`UNION ALL` — os dois tipos de bug que já apareceram validando cada
relatório manualmente durante a migração). Por isso as asserções aqui são
só "a consulta roda sem erro" — nunca sobre o valor/quantidade do
resultado, que depende do dado real do STAGE e muda com o tempo.

Pula a suíte inteira (em vez de falhar) se `DB_BACKEND` não estiver como
"oracle" ou se o Oracle configurado no `.env` não estiver acessível — assim
quem não tem rede/credencial pro STAGE continua rodando o resto da suíte
normalmente. Precisa também do Postgres de teste (mesma exigência global de
`conftest.py`), porque login/token de usuário são sempre nesse banco.
"""

import pytest

from agente_oracle.config import settings
from agente_oracle.db.connection import DatabaseError, get_connection

pytestmark = pytest.mark.integration

_FILIAL = "0101"


def _stage_disponivel() -> bool:
    if settings.db_backend != "oracle":
        return False
    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM STAGE.contareceber")
            cursor.fetchone()
        return True
    except DatabaseError:
        return False


@pytest.fixture(autouse=True)
def _requer_stage():
    if not _stage_disponivel():
        pytest.skip(
            "Banco de negócio/RAG (STAGE) não está acessível — configure DB_BACKEND=oracle e as "
            "credenciais ORACLE_* no .env, com um usuário que tenha SELECT no schema STAGE."
        )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_contas_receber_produto_roda_contra_stage_real(mcp_app, token_teste):
    resposta = mcp_app.get(
        "/api/financeiro/contas-receber-produto", params={"filial": _FILIAL}, headers=_auth(token_teste)
    )
    assert resposta.status_code == 200
    assert isinstance(resposta.json(), list)


def test_duplicata_mercantil_roda_contra_stage_real(mcp_app, token_teste):
    resposta = mcp_app.get(
        "/api/financeiro/duplicata-mercantil", params={"filial": _FILIAL}, headers=_auth(token_teste)
    )
    assert resposta.status_code == 200
    assert isinstance(resposta.json(), list)


def test_extrato_bancario_roda_contra_stage_real(mcp_app, token_teste):
    resposta = mcp_app.get(
        "/api/financeiro/extrato-bancario",
        params={
            "filial": _FILIAL,
            "conta_bancaria": "000000|0001|00000001",
            "data_ini": "20200101",
            "data_fim": "20201231",
        },
        headers=_auth(token_teste),
    )
    assert resposta.status_code == 200
    assert isinstance(resposta.json(), list)


def test_movimento_financeiro_diario_roda_contra_stage_real(mcp_app, token_teste):
    resposta = mcp_app.get(
        "/api/financeiro/movimento-financeiro-diario",
        params={"filial": _FILIAL, "data_ini": "20260101"},
        headers=_auth(token_teste),
    )
    assert resposta.status_code == 200
    assert isinstance(resposta.json(), list)


def test_posicao_titulos_roda_contra_stage_real(mcp_app, token_teste):
    resposta = mcp_app.get(
        "/api/financeiro/posicao-titulos", params={"filial": _FILIAL}, headers=_auth(token_teste)
    )
    assert resposta.status_code == 200
    assert isinstance(resposta.json(), list)


def test_posicao_titulos_pagar_roda_contra_stage_real(mcp_app, token_teste):
    resposta = mcp_app.get(
        "/api/financeiro/posicao-titulos-pagar", params={"filial": _FILIAL}, headers=_auth(token_teste)
    )
    assert resposta.status_code == 200
    assert isinstance(resposta.json(), list)


def test_posicao_titulos_vendedor_roda_contra_stage_real(mcp_app, token_teste):
    resposta = mcp_app.get(
        "/api/financeiro/posicao-titulos-vendedor", params={"filial": _FILIAL}, headers=_auth(token_teste)
    )
    assert resposta.status_code == 200
    assert isinstance(resposta.json(), list)


def test_relacao_baixas_roda_contra_stage_real(mcp_app, token_teste):
    resposta = mcp_app.get(
        "/api/financeiro/relacao-baixas",
        params={"filial": _FILIAL, "data_baixa_ini": "20200101", "data_baixa_fim": "20301231"},
        headers=_auth(token_teste),
    )
    assert resposta.status_code == 200
    assert isinstance(resposta.json(), list)


def test_fluxo_caixa_realizado_roda_contra_stage_real(mcp_app, token_teste):
    resposta = mcp_app.get(
        "/api/financeiro/fluxo-caixa-realizado",
        params={"filial": _FILIAL, "ano": "2024"},
        headers=_auth(token_teste),
    )
    assert resposta.status_code == 200
    assert isinstance(resposta.json(), list)


def test_cadastros_vendedores_roda_contra_stage_real(mcp_app, token_teste):
    resposta = mcp_app.get("/api/financeiro/vendedores", headers=_auth(token_teste))
    assert resposta.status_code == 200
    assert isinstance(resposta.json(), list)
