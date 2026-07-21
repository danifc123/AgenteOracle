"""RELATÓRIO: Fluxo de Caixa Realizado (FINR01)

Tradução fiel do relatório ADVPL original (TOTVS Protheus), validada contra a
saída real (.prt). Filial/grupo e ano são parâmetros escolhidos pelo usuário
na tela (era fixo '0101'/'2023' na primeira versão).

A filial agora aceita seleção múltipla (o time financeiro pode ter acesso a
mais de uma filial e emitir o relatório de todas de uma vez). Como isso é
usado tanto pra filtrar quanto pra rotular as linhas de resumo do BLOCO 2, o
rótulo dessas linhas passou a mostrar as filiais escolhidas separadas por
vírgula, em vez de uma filial só.

Outros ajustes feitos em cima do SQL originalmente validado, pra bater com os
dados do banco de teste (testeIA):
- Filtro de "não deletado" (`d_e_l_e_t_ = ' '`) virou tolerante a NULL
  (`COALESCE(d_e_l_e_t_, ' ') = ' '`) — nesse banco de teste o campo vem NULL
  em vez de espaço em branco, e `NULL = ' '` nunca é verdadeiro em SQL.

Atenção: esta consulta usa sintaxe exclusiva do PostgreSQL (`FILTER (WHERE
...)` e casts `::tipo`) — só roda com DB_BACKEND=postgres. Pra rodar contra o
Oracle de produção, precisa ser reescrita (FILTER -> CASE WHEN, `::tipo` ->
CAST(... AS tipo)).
"""

from decimal import Decimal

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.db.connection import get_connection
from agente_oracle.relatorios import gerar_xlsx
from agente_oracle.server.auth.dependencia import exigir_usuario
from agente_oracle.server.cors import CORS_HEADERS, resposta_preflight
from agente_oracle.server.financeiro.relatorios.filtros_sql import clausula_in

_QUERY = """
-- =====================================================================
-- RELATORIO: Fluxo de Caixa Realizado (FINR01)
-- Tradução fiel do ADVPL original, validada contra a saída real (.prt)
-- Parâmetros: __FILIAL_IN__ = filial(is) (grupo), :ano = ano
-- =====================================================================

WITH mensal AS (
    -- Movimento agrupado por natureza e mês (equivalente à VWPR_EXTRBAN)
    SELECT
        e5_naturez,
        SUM(e5_valor) FILTER (WHERE mes = '01') AS jan_,
        SUM(e5_valor) FILTER (WHERE mes = '02') AS fev_,
        SUM(e5_valor) FILTER (WHERE mes = '03') AS mar_,
        SUM(e5_valor) FILTER (WHERE mes = '04') AS abr_,
        SUM(e5_valor) FILTER (WHERE mes = '05') AS mai_,
        SUM(e5_valor) FILTER (WHERE mes = '06') AS jun_,
        SUM(e5_valor) FILTER (WHERE mes = '07') AS jul_,
        SUM(e5_valor) FILTER (WHERE mes = '08') AS ago_,
        SUM(e5_valor) FILTER (WHERE mes = '09') AS set_,
        SUM(e5_valor) FILTER (WHERE mes = '10') AS out_,
        SUM(e5_valor) FILTER (WHERE mes = '11') AS nov_,
        SUM(e5_valor) FILTER (WHERE mes = '12') AS dez_,
        SUM(e5_valor)                            AS tot_
    FROM vwpr_extrban
    WHERE grupo IN __FILIAL_IN__ AND ano = :ano
    GROUP BY e5_naturez
),

detalhe AS (
    -- Linhas de natureza (hierárquicas: 1, 1001, 100101 ...)
    -- ED_COND: '1' = Entradas / '2' = Saídas -> define ordenação/bloco
    SELECT
        :filiais_label::varchar      AS filial,
        sed.ed_codigo               AS codigo_naturezas,
        sed.ed_descric              AS naturezas_sinteticas,
        sed.ed_cond,
        LENGTH(TRIM(sed.ed_codigo)) AS nivel,
        COALESCE(SUM(m.jan_), 0)    AS jan,
        COALESCE(SUM(m.fev_), 0)    AS fev,
        COALESCE(SUM(m.mar_), 0)    AS mar,
        COALESCE(SUM(m.abr_), 0)    AS abr,
        COALESCE(SUM(m.mai_), 0)    AS mai,
        COALESCE(SUM(m.jun_), 0)    AS jun,
        COALESCE(SUM(m.jul_), 0)    AS jul,
        COALESCE(SUM(m.ago_), 0)    AS ago,
        COALESCE(SUM(m.set_), 0)    AS set_,
        COALESCE(SUM(m.out_), 0)    AS out,
        COALESCE(SUM(m.nov_), 0)    AS nov,
        COALESCE(SUM(m.dez_), 0)    AS dez,
        COALESCE(SUM(m.tot_), 0)    AS total
    FROM sed010 sed
    LEFT JOIN mensal m
        ON SUBSTR(sed.ed_codigo, 1, LENGTH(TRIM(sed.ed_codigo)))
         = SUBSTR(m.e5_naturez,  1, LENGTH(TRIM(sed.ed_codigo)))
    WHERE COALESCE(sed.d_e_l_e_t_, ' ') = ' '
    GROUP BY sed.ed_codigo, sed.ed_descric, sed.ed_cond
),

contas AS (
    SELECT a6_filial, a6_agencia, a6_numcon
    FROM sa6010
    WHERE COALESCE(d_e_l_e_t_, ' ') = ' ' AND a6_filial IN __FILIAL_IN__
),

-- Réplica fiel da regra original: "ant" busca mês=12 do MESMO ano informado
-- (não do ano anterior). Mantido assim de propósito para bater com o legado.
meses AS (
    SELECT * FROM (VALUES
        ('12','ant'), ('01','jan'), ('02','fev'), ('03','mar'),
        ('04','abr'), ('05','mai'), ('06','jun'), ('07','jul'),
        ('08','ago'), ('09','set'), ('10','out'), ('11','nov'),
        ('12','dez')
    ) AS m(mes_num, mes_label)
),

datas_ref AS (
    SELECT
        c.a6_filial, c.a6_agencia, c.a6_numcon, me.mes_label,
        (SELECT MAX(se8.e8_dtsalat)
         FROM se8010 se8
         WHERE COALESCE(se8.d_e_l_e_t_, ' ') = ' '
           AND se8.e8_filial  = c.a6_filial
           AND se8.e8_agencia = c.a6_agencia
           AND se8.e8_conta   = c.a6_numcon
           AND SUBSTR(se8.e8_dtsalat,5,2) = me.mes_num
           AND SUBSTR(se8.e8_dtsalat,1,4) = :ano
        ) AS data_final
    FROM contas c
    CROSS JOIN meses me
),

saldos AS (
    SELECT
        dr.a6_filial, dr.mes_label,
        COALESCE((
            SELECT se8.e8_salatua FROM se8010 se8
            WHERE COALESCE(se8.d_e_l_e_t_, ' ') = ' '
              AND se8.e8_filial  = dr.a6_filial
              AND se8.e8_agencia = dr.a6_agencia
              AND se8.e8_conta   = dr.a6_numcon
              AND se8.e8_dtsalat = dr.data_final
        ), 0) AS saldo
    FROM datas_ref dr
),

saldo_banco AS (
    SELECT
        :filiais_label::varchar AS filial,
        SUM(saldo) FILTER (WHERE mes_label = 'ant') AS sldfn_ant,
        SUM(saldo) FILTER (WHERE mes_label = 'jan') AS sldfn_jan,
        SUM(saldo) FILTER (WHERE mes_label = 'fev') AS sldfn_fev,
        SUM(saldo) FILTER (WHERE mes_label = 'mar') AS sldfn_mar,
        SUM(saldo) FILTER (WHERE mes_label = 'abr') AS sldfn_abr,
        SUM(saldo) FILTER (WHERE mes_label = 'mai') AS sldfn_mai,
        SUM(saldo) FILTER (WHERE mes_label = 'jun') AS sldfn_jun,
        SUM(saldo) FILTER (WHERE mes_label = 'jul') AS sldfn_jul,
        SUM(saldo) FILTER (WHERE mes_label = 'ago') AS sldfn_ago,
        SUM(saldo) FILTER (WHERE mes_label = 'set') AS sldfn_set,
        SUM(saldo) FILTER (WHERE mes_label = 'out') AS sldfn_out,
        SUM(saldo) FILTER (WHERE mes_label = 'nov') AS sldfn_nov,
        SUM(saldo) FILTER (WHERE mes_label = 'dez') AS sldfn_dez
    FROM saldos
)

-- =====================================================================
-- BLOCO 1: Detalhe das naturezas (corpo do relatório)
-- =====================================================================
SELECT
    1                          AS ordem_bloco,
    d.ed_cond::int              AS ordem_grupo,
    d.codigo_naturezas          AS ordem_item,
    d.filial,
    d.codigo_naturezas,
    d.naturezas_sinteticas,
    d.jan, d.fev, d.mar, d.abr, d.mai, d.jun,
    d.jul, d.ago, d.set_ AS "set", d.out, d.nov, d.dez,
    d.total
FROM detalhe d

UNION ALL

-- =====================================================================
-- BLOCO 2: RESUMO — Saldo Bancário Inicial do Período
-- =====================================================================
SELECT
    2, 0, '1',
    sb.filial,
    NULL,
    'SALDO BANCARIO INICIAL DO PERIODO',
    sb.sldfn_ant, sb.sldfn_jan, sb.sldfn_fev, sb.sldfn_mar, sb.sldfn_abr,
    sb.sldfn_mai, sb.sldfn_jun, sb.sldfn_jul, sb.sldfn_ago, sb.sldfn_set,
    sb.sldfn_out, sb.sldfn_nov,
    0
FROM saldo_banco sb

UNION ALL

-- =====================================================================
-- BLOCO 2: RESUMO — Entradas (mesma linha do detalhe onde ED_COND='1')
-- =====================================================================
SELECT
    2, 1, '2',
    :filiais_label::varchar, NULL, 'ENTRADAS',
    d.jan, d.fev, d.mar, d.abr, d.mai, d.jun,
    d.jul, d.ago, d.set_, d.out, d.nov, d.dez,
    d.total
FROM detalhe d
WHERE d.ed_cond = '1' AND LENGTH(TRIM(d.codigo_naturezas)) = 1

UNION ALL

-- =====================================================================
-- BLOCO 2: RESUMO — Saídas (mesma linha do detalhe onde ED_COND='2')
-- =====================================================================
SELECT
    2, 2, '3',
    :filiais_label::varchar, NULL, 'SAIDAS',
    d.jan, d.fev, d.mar, d.abr, d.mai, d.jun,
    d.jul, d.ago, d.set_, d.out, d.nov, d.dez,
    d.total
FROM detalhe d
WHERE d.ed_cond = '2' AND LENGTH(TRIM(d.codigo_naturezas)) = 1

UNION ALL

-- =====================================================================
-- BLOCO 2: RESUMO — Saldo Bancário Final do Período
-- =====================================================================
SELECT
    2, 3, '4',
    sb.filial, NULL,
    'SALDO BANCARIO FINAL DO PERIODO',
    sb.sldfn_jan, sb.sldfn_fev, sb.sldfn_mar, sb.sldfn_abr, sb.sldfn_mai,
    sb.sldfn_jun, sb.sldfn_jul, sb.sldfn_ago, sb.sldfn_set, sb.sldfn_out,
    sb.sldfn_nov, sb.sldfn_dez,
    0
FROM saldo_banco sb

ORDER BY ordem_bloco, ordem_grupo, ordem_item
"""


def _serializar(valor):
    return float(valor) if isinstance(valor, Decimal) else valor


def _buscar_fluxo_caixa_realizado(filiais: list[str], ano: str) -> tuple[list[str], list[tuple]]:
    clausula_filial, binds_filial = clausula_in("filial", filiais)
    sql = _QUERY.replace("__FILIAL_IN__", clausula_filial)

    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, ano=ano, filiais_label=", ".join(filiais), **binds_filial)
        colunas = [descricao[0] for descricao in cursor.description]
        linhas = cursor.fetchall()
    return colunas, linhas


def _parametros_da_query(request: Request) -> tuple[list[str], str] | None:
    filial_bruto = request.query_params.get("filial", "").strip()
    ano = request.query_params.get("ano", "").strip()
    filiais = [item.strip() for item in filial_bruto.split(",") if item.strip()]
    if not filiais or not ano:
        return None
    return filiais, ano


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/fluxo-caixa-realizado", methods=["GET", "OPTIONS"])
    async def listar_fluxo_caixa_realizado_route(request: Request) -> JSONResponse:
        """RELATÓRIO: Fluxo de Caixa Realizado (FINR01) — endpoint JSON usado pela tela."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial e o ano."}, status_code=400, headers=CORS_HEADERS
            )

        colunas, linhas = _buscar_fluxo_caixa_realizado(*parametros)
        dados = [dict(zip(colunas, (_serializar(valor) for valor in linha))) for linha in linhas]
        return JSONResponse(dados, headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/fluxo-caixa-realizado/exportar", methods=["GET", "OPTIONS"])
    async def exportar_fluxo_caixa_realizado_route(request: Request) -> Response:
        """RELATÓRIO: Fluxo de Caixa Realizado (FINR01) — exportação em Excel."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial e o ano."}, status_code=400, headers=CORS_HEADERS
            )

        colunas, linhas = _buscar_fluxo_caixa_realizado(*parametros)
        conteudo_xlsx = gerar_xlsx(colunas, linhas, titulo="Fluxo de Caixa Realizado")
        return Response(
            content=conteudo_xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="fluxo_caixa_realizado.xlsx"',
                **CORS_HEADERS,
            },
        )
