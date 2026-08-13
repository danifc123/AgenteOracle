"""RELATÓRIO: Extrato Bancário (FINR470)

Tradução do ADVPL (`FINR470.PRW`) — lista as movimentações de uma conta
bancária específica (banco+agência+conta) dentro de uma faixa de data de
disponibilidade, com saldo corrente linha a linha, igual a um extrato de
banco de verdade.

Migrado do Oracle transacional do Protheus (SE5010) para o STAGE
(SCIENCE_PROD, ETL/BI) — `STAGE.MOVIMENTACAOFINANCEIRA` no lugar de
`SE5010`. Ver `db/views/financeiro_science.sql`/README ("Views curadas do
Financeiro") pro modelo geral.

ACHADO IMPORTANTE ao validar — sinal do valor: `MOVIMENTACAOFINANCEIRA.VALOR`
já vem com sinal (confirmado numa conta real: 100% dos lançamentos
`PAGAR` são negativos, 100% dos `RECEBER` são positivos) — diferente do
`SE5010.E5_VALOR` original, que é sempre positivo/absoluto (a direção vinha
só de `E5_RECPAG`). A fórmula antiga (`SUM(valor_entrada - valor_saida)`,
ambos tratados como positivos) contava o sinal duas vezes com o novo dado —
testado numa conta real: saldo inflava de ~800 mil pra 1,8 bilhão ao longo
de um ano, claramente errado. Corrigido: o saldo corrente soma `VALOR`
direto (já sinalizado); as colunas de exibição `valor_entrada`/`valor_saida`
usam `ABS(VALOR)` pra aparecer como magnitude positiva nas duas.

O que ficou de fora nesta migração (não tinha equivalente confirmado no
STAGE):
- **Cheque avulso (`SEF010`)** — quando `E5_TIPODOC='CH'`, a versão anterior
  buscava o título vinculado numa tabela à parte. Sem equivalente no STAGE
  — nesse caso a coluna `titulo` cai no formato padrão
  (prefixo-número-parcela, que fica vazio/`-1` quando não há título
  vinculado ao lançamento).
- **Limite de crédito** no saldo — mesma limitação já documentada em
  `movimento_financeiro_diario.py` (sem coluna de limite em
  `STAGE.SALDOBANCARIO`).

O que TEM fidelidade real:
- Filtro de conta bancária exata (banco+agência+conta) + faixa de data de
  disponibilidade (obrigatória) + filtro de conciliação (`saldo_tipo`:
  1=Saldo Atual/todos, 2=só conciliados, 3=só não conciliados).
- Exclui os mesmos tipos de documento que não são movimentação bancária de
  verdade (`TIPODOCUMENTO NOT IN (...)`, valor zero) — mesma lista do
  ADVPL original.
- **Saldo corrente real**, calculado com `SUM() OVER (ORDER BY ...)`.
- **Saldo inicial reconstruído** a partir do próprio histórico de
  `MOVIMENTACAOFINANCEIRA` (soma de tudo antes da data inicial da faixa).

ATENÇÃO charset: comparações envolvendo colunas `NVARCHAR2`
(`RECONCILIADO`... — na verdade `RECONCILIADO` é `CHAR`, mas
`NUMEROCHEQUE`/`TIPOMOVIMENTACAO` são `NVARCHAR2`) contra literal solto
(`''`, `'RECEBER'`, `'PAGAR'`, `'SIM'`) dão `ORA-12704` — usar literal
nacional (`N''`, `N'RECEBER'`...). Mesmo problema documentado em
`financeiro_science.sql`/`relacao_baixas.py`.
"""

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.db.connection import get_connection
from agente_oracle.relatorios import gerar_xlsx
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.server.financeiro.relatorios import _comum
from agente_oracle.server.financeiro.relatorios.filtros_sql import clausula_in

_TIPODOC_EXCLUIDOS_IN = "('DC','JR','MT','CM','D2','J2','M2','V2','C2','CP','TL','BA','I2','EI','VA')"

_QUERY = """
-- =====================================================================
-- RELATORIO: Extrato Bancario (FINR470) — versao STAGE
-- (sem cheque avulso/limite de credito; VALOR ja vem com sinal no STAGE)
-- =====================================================================
WITH saldo_inicial AS (
    SELECT COALESCE(SUM(mf.valor), 0) AS valor
    FROM STAGE.movimentacaofinanceira mf
    WHERE mf.banco = :banco AND mf.agencia = :agencia AND mf.conta = :conta
      AND mf.excluido = 0
      AND TRIM(mf.filialorigem) IN __FILIAL_IN__
      AND mf.datadisponibilizacao < TO_DATE(:data_ini, 'YYYYMMDD')
      AND mf.valor <> 0
      AND mf.tipodocumento NOT IN __TIPODOC_EXCLUIDOS__
      AND (:saldo_tipo <> '2' OR mf.reconciliado = 'SIM')
      AND (:saldo_tipo <> '3' OR mf.reconciliado <> 'SIM')
),
movimentos AS (
    SELECT
        mf.identificator,
        mf.datadisponibilizacao, mf.historico, mf.documento, mf.numerocheque,
        mf.prefixo, mf.numero, mf.parcela, mf.valor,
        (CASE WHEN mf.reconciliado = N'SIM' THEN 1 ELSE 0 END) AS conciliado,
        (CASE WHEN mf.tipomovimentacao = N'RECEBER' THEN mf.valor ELSE 0 END) AS valor_entrada,
        (CASE WHEN mf.tipomovimentacao = N'PAGAR' THEN ABS(mf.valor) ELSE 0 END) AS valor_saida
    FROM STAGE.movimentacaofinanceira mf
    WHERE mf.banco = :banco AND mf.agencia = :agencia AND mf.conta = :conta
      AND mf.excluido = 0
      AND TRIM(mf.filialorigem) IN __FILIAL_IN__
      AND mf.datadisponibilizacao BETWEEN TO_DATE(:data_ini, 'YYYYMMDD') AND TO_DATE(:data_fim, 'YYYYMMDD')
      AND mf.valor <> 0
      AND mf.tipodocumento NOT IN __TIPODOC_EXCLUIDOS__
      AND (:saldo_tipo <> '2' OR mf.reconciliado = 'SIM')
      AND (:saldo_tipo <> '3' OR mf.reconciliado <> 'SIM')
)
SELECT
    m.datadisponibilizacao AS data_disponivel,
    m.historico,
    COALESCE(NULLIF(TRIM(m.numerocheque), N''), TRIM(m.documento)) AS documento,
    (TRIM(m.prefixo) || '-' || TRIM(m.numero) || '-' || TRIM(m.parcela)) AS titulo,
    m.valor_entrada,
    m.valor_saida,
    (
        (SELECT valor FROM saldo_inicial)
        + SUM(m.valor) OVER (ORDER BY m.datadisponibilizacao, m.identificator ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
    ) AS saldo_atual,
    m.conciliado
FROM movimentos m
ORDER BY m.datadisponibilizacao, m.identificator
"""

_CAMPOS_OPCIONAIS = ("banco", "agencia", "conta", "data_ini", "data_fim", "saldo_tipo")


def _buscar_extrato(filiais: list[str], opcionais: dict[str, str]) -> tuple[list[str], list[tuple]]:
    clausula_filial, binds_filial = clausula_in("filial", filiais)

    opcionais.setdefault("saldo_tipo", "1")

    sql = _QUERY.replace("__FILIAL_IN__", clausula_filial).replace(
        "__TIPODOC_EXCLUIDOS__", _TIPODOC_EXCLUIDOS_IN
    )

    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, **opcionais, **binds_filial)
        colunas = [descricao[0] for descricao in cursor.description]
        linhas = cursor.fetchall()
    return colunas, linhas


def _parametros_da_query(request: Request) -> tuple[list[str], dict[str, str]] | None:
    filiais = _comum.filiais_da_query(request)
    if filiais is None:
        return None

    conta_bancaria = request.query_params.get("conta_bancaria", "").strip()
    partes = conta_bancaria.split("|")
    if len(partes) != 3 or not all(partes):
        return None

    opcionais = {
        chave: request.query_params.get(chave, "").strip()
        for chave in _CAMPOS_OPCIONAIS
        if chave not in ("banco", "agencia", "conta")
    }
    opcionais["banco"], opcionais["agencia"], opcionais["conta"] = partes

    if not opcionais.get("data_ini") or not opcionais.get("data_fim"):
        return None

    return filiais, opcionais


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/extrato-bancario/exportar", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def exportar_extrato_bancario_route(request: Request, usuario: dict) -> Response:
        """RELATÓRIO: Extrato Bancário (FINR470) — exportação em Excel."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse(
                {"erro": "Informe filial, conta bancária e a faixa de data."},
                status_code=400,
                headers=CORS_HEADERS,
            )

        colunas, linhas = _buscar_extrato(*parametros)
        conteudo_xlsx = gerar_xlsx(colunas, linhas, titulo="Extrato Bancário")
        return Response(
            content=conteudo_xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="extrato_bancario.xlsx"',
                **CORS_HEADERS,
            },
        )

    @mcp.custom_route("/api/financeiro/extrato-bancario", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def listar_extrato_bancario_route(request: Request, usuario: dict) -> JSONResponse:
        """RELATÓRIO: Extrato Bancário (FINR470) — endpoint JSON usado pela tela."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse(
                {"erro": "Informe filial, conta bancária e a faixa de data."},
                status_code=400,
                headers=CORS_HEADERS,
            )

        colunas, linhas = _buscar_extrato(*parametros)
        dados = [
            dict(zip(colunas, (_comum.serializar(valor) for valor in linha), strict=True)) for linha in linhas
        ]
        return JSONResponse(dados, headers=CORS_HEADERS)
