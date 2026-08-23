"""RELATÓRIO: Fluxo de Caixa Realizado (FINR01)

Tradução original do relatório ADVPL (TOTVS Protheus), validada contra a
saída real (.prt). Filial/grupo e ano são parâmetros escolhidos pelo
usuário na tela.

Migrado do Postgres de teste (`vwpr_extrban`/`SE8010`/`SA6010`/`SED010`)
para o STAGE (SCIENCE_PROD, ETL/BI) — esta consulta nunca tinha rodado
contra Oracle antes (o arquivo já dizia "só roda com DB_BACKEND=postgres,
sintaxe exclusiva do PostgreSQL — precisa ser reescrita" desde antes desta
migração), então a reescrita aqui não perde fidelidade em relação a uma
versão Oracle anterior — não existia uma. `FILTER (WHERE ...)` virou `CASE
WHEN`, `::tipo` virou `CAST(... AS tipo)`, `SUBSTR` sobre texto YYYYMMDD
virou `EXTRACT`/`TO_CHAR` sobre `TIMESTAMP` real.

Mapeamento de tabela:
- `vwpr_extrban` (agrupava `SE5010` por natureza+mês) → agregação direta em
  `STAGE.MOVIMENTACAOFINANCEIRA`, sem precisar de uma view auxiliar — os
  meses já vêm de `EXTRACT(MONTH FROM ...)` sobre `DATAMOVIMENTACAO`
  (`TIMESTAMP` de verdade no STAGE, sem `TO_DATE`/YYYYMMDD).
- `SED010` (natureza, hierárquico por prefixo de código, `ED_COND`
  1=Entrada/2=Saída) → `STAGE.NATUREZA`: `TIPOMOVIMENTO` já vem como texto
  ('RECEITA'/'DESPESA'), mapeado pra '1'/'2' pra manter a mesma convenção
  numérica do relatório original. A hierarquia por prefixo de código
  (`SUBSTR`) continua igual — os códigos de natureza no STAGE têm o mesmo
  formato hierárquico (1, 1001, 100101...).
- `SA6010`+`SE8010` (contas bancárias + snapshot diário de saldo) →
  `STAGE.SALDOBANCARIO`, que já tem histórico diário real — mesmo padrão
  de `movimento_financeiro_diario.py` (contas bancárias são escopadas por
  "grupo de filiais" de 2 dígitos, não pela filial de 4 dígitos — ver
  `STAGE.EMPRESA.GRUPOLOJA`).

ACHADO de dado (não é bug de query): alguns códigos de natureza no STAGE
vêm com aspas literais dentro do valor (ex: `"20010404"`, com as aspas
fazendo parte da string) — mesma anomalia já vista em `NATUREZA` ao migrar
`retencao_impostos.py`/`IMPOSTORETIDO`. Não tentamos limpar isso (poderia
esconder um problema de origem maior) — o relatório trata como veio.

Regra preservada de propósito (já era assim antes desta migração): o mês
"ant" (saldo bancário inicial do período) busca o saldo de dezembro do
MESMO ano informado, não do ano anterior — réplica fiel do comportamento
original do ADVPL, mantida pra bater com o legado mesmo não parecendo
intuitiva.

ACHADO ao validar — RESUMO duplicado: `STAGE.NATUREZA` tem **4** códigos de
nível 1 (1 caractere), não 2 — além de `1`=ENTRADAS e `2`=SAIDAS, existem
`3`=CONCILIACAO BANCARIA-ORIGEM e `4`=CONCILIACAO BANCARIA-DESTINO (também
nível 1). O filtro original das linhas de RESUMO
(`ed_cond = X AND LENGTH(codigo) = 1`) pegava as duas naturezas de cada
lado sem querer, duplicando "ENTRADAS"/"SAIDAS" no Bloco 2 com números
diferentes. Corrigido pra filtrar pelo código exato (`codigo_naturezas =
'1'`/`'2'`) — as naturezas de conciliação bancária continuam aparecendo
normalmente no Bloco 1 (detalhe), só não entram mais no resumo.

ATENÇÃO charset: em `UNION ALL`, quando uma coluna vem de uma coluna
`NVARCHAR2` (`STAGE.NATUREZA.DESCRICAO`/`CODIGO`) num `SELECT` do bloco e
de um literal solto (`'ENTRADAS'`, `'1'`...) noutro, Oracle exige que os
literais sejam `N'...'` (nacional) — senão dá `ORA-12704`. Mesmo problema
já documentado em `relacao_baixas.py`/`extrato_bancario.py`, mas
manifestando de um jeito novo (só aparece combinando os branches do
`UNION`, não numa query isolada).

ATENÇÃO ORDER BY: `ORDER BY ordem_bloco, ordem_grupo, ordem_item` (por
nome de alias) devolvia `ORA-00904: "ORDEM_BLOCO": invalid identifier`
depois do `UNION ALL` — motivo não totalmente claro (suspeita: interação
com o alias entre aspas `"set"`, palavra reservada, no meio da lista de
colunas do primeiro `SELECT`). `ORDER BY 1, 2, 3` (posicional) resolve e é
equivalente.

ATENÇÃO portabilidade Postgres (achado populando o banco fictício, este
relatório nunca tinha rodado contra Oracle OU Postgres antes de verdade):
`FROM DUAL` (pseudo-tabela pra linha "solta" na CTE `meses`) e
`TO_NUMBER(coluna)`/`CAST(... AS NUMBER)` são sintaxe **exclusiva do
Oracle** — Postgres não tem `dual` nem o tipo `NUMBER`. Trocados por
`_comum.origem_linha_unica()` e `_comum.numero_coluna()`.

Outro achado: `EXTRACT(YEAR FROM mf.datamovimentacao) = :ano` comparava um
número (resultado de `EXTRACT`) direto contra o bind `:ano` (sempre texto,
vem da tela) — Oracle converte implicitamente texto<->número numa
comparação assim, Postgres não (`operator does not exist: text = numeric`).
Trocado por `_comum.numero_bind()` — só que num bind SEPARADO
(`:ano_numero`, mesmo valor de `:ano`, passado duas vezes em
`cursor.execute()`), não reaproveitando `:ano`: o Postgres unifica o tipo
de um bind pelo NOME em toda a query (não por ocorrência individual) — se
o mesmo `:ano` aparecesse castado pra número num lugar e comparado a texto
(`TO_CHAR(...) = :ano`) noutro, o Postgres tentava aplicar o tipo
numérico também nessa segunda comparação e quebrava do mesmo jeito
(confirmado rodando: o erro geral um `$N` só de tipo ambíguo entre
ocorrências, mesma raiz da "pegadinha irmã" de `filtro_vazio()`, mas na
direção oposta — aqui não falta tipo, tem tipo DEMAIS/conflitante).

Ver "Oracle vs Postgres" em `MAPA_BANCOS_LOCAL.md` pra lista completa
dessas pegadinhas.
"""

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.db.connection import get_connection
from agente_oracle.relatorios import gerar_xlsx
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.server.financeiro.relatorios import _comum
from agente_oracle.server.financeiro.relatorios.filtros_sql import clausula_in

_QUERY = """
-- =====================================================================
-- RELATORIO: Fluxo de Caixa Realizado (FINR01) — versao STAGE
-- Parametros: __FILIAL_IN__ = filial(is) (grupo), :ano = ano
-- =====================================================================

WITH mensal AS (
    -- Movimento agrupado por natureza e mes (antes vinha de vwpr_extrban)
    SELECT
        TRIM(mf.codigonatureza) AS natureza,
        SUM(CASE WHEN EXTRACT(MONTH FROM mf.datamovimentacao) = 1 THEN mf.valor ELSE 0 END) AS jan_,
        SUM(CASE WHEN EXTRACT(MONTH FROM mf.datamovimentacao) = 2 THEN mf.valor ELSE 0 END) AS fev_,
        SUM(CASE WHEN EXTRACT(MONTH FROM mf.datamovimentacao) = 3 THEN mf.valor ELSE 0 END) AS mar_,
        SUM(CASE WHEN EXTRACT(MONTH FROM mf.datamovimentacao) = 4 THEN mf.valor ELSE 0 END) AS abr_,
        SUM(CASE WHEN EXTRACT(MONTH FROM mf.datamovimentacao) = 5 THEN mf.valor ELSE 0 END) AS mai_,
        SUM(CASE WHEN EXTRACT(MONTH FROM mf.datamovimentacao) = 6 THEN mf.valor ELSE 0 END) AS jun_,
        SUM(CASE WHEN EXTRACT(MONTH FROM mf.datamovimentacao) = 7 THEN mf.valor ELSE 0 END) AS jul_,
        SUM(CASE WHEN EXTRACT(MONTH FROM mf.datamovimentacao) = 8 THEN mf.valor ELSE 0 END) AS ago_,
        SUM(CASE WHEN EXTRACT(MONTH FROM mf.datamovimentacao) = 9 THEN mf.valor ELSE 0 END) AS set_,
        SUM(CASE WHEN EXTRACT(MONTH FROM mf.datamovimentacao) = 10 THEN mf.valor ELSE 0 END) AS out_,
        SUM(CASE WHEN EXTRACT(MONTH FROM mf.datamovimentacao) = 11 THEN mf.valor ELSE 0 END) AS nov_,
        SUM(CASE WHEN EXTRACT(MONTH FROM mf.datamovimentacao) = 12 THEN mf.valor ELSE 0 END) AS dez_,
        SUM(mf.valor) AS tot_
    FROM STAGE.movimentacaofinanceira mf
    WHERE mf.excluido = 0
      AND TRIM(mf.filialorigem) IN __FILIAL_IN__
      AND EXTRACT(YEAR FROM mf.datamovimentacao) = __NUMERO_ANO__
    GROUP BY mf.codigonatureza
),

detalhe AS (
    -- Linhas de natureza (hierarquicas: 1, 1001, 100101 ...)
    -- TIPOMOVIMENTO: RECEITA -> '1' (Entradas) / DESPESA -> '2' (Saidas)
    SELECT
        :filiais_label AS filial,
        n.codigo AS codigo_naturezas,
        n.descricao AS naturezas_sinteticas,
        (CASE WHEN n.tipomovimento = N'RECEITA' THEN '1' ELSE '2' END) AS ed_cond,
        LENGTH(TRIM(n.codigo)) AS nivel,
        COALESCE(SUM(m.jan_), 0) AS jan,
        COALESCE(SUM(m.fev_), 0) AS fev,
        COALESCE(SUM(m.mar_), 0) AS mar,
        COALESCE(SUM(m.abr_), 0) AS abr,
        COALESCE(SUM(m.mai_), 0) AS mai,
        COALESCE(SUM(m.jun_), 0) AS jun,
        COALESCE(SUM(m.jul_), 0) AS jul,
        COALESCE(SUM(m.ago_), 0) AS ago,
        COALESCE(SUM(m.set_), 0) AS set_,
        COALESCE(SUM(m.out_), 0) AS out,
        COALESCE(SUM(m.nov_), 0) AS nov,
        COALESCE(SUM(m.dez_), 0) AS dez,
        COALESCE(SUM(m.tot_), 0) AS total
    FROM STAGE.natureza n
    LEFT JOIN mensal m
        ON SUBSTR(TRIM(n.codigo), 1, LENGTH(TRIM(n.codigo)))
         = SUBSTR(m.natureza, 1, LENGTH(TRIM(n.codigo)))
    WHERE n.excluido = 0
    GROUP BY n.codigo, n.descricao, n.tipomovimento
),

grupos AS (
    SELECT DISTINCT grupoloja FROM STAGE.empresa WHERE excluido = 0 AND TRIM(codigo) IN __FILIAL_IN__
),

contas AS (
    SELECT DISTINCT sb.codigobanco, sb.codigoagencia, sb.codigoconta
    FROM STAGE.saldobancario sb
    JOIN grupos g ON TRIM(sb.codigoempresa) = g.grupoloja
    WHERE sb.excluido = 0
),

-- Replica fiel da regra original: "ant" busca mes=12 do MESMO ano informado
-- (nao do ano anterior). Mantido assim de proposito para bater com o legado.
meses AS (
    SELECT '12' mes_num, 'ant' mes_label__ORIGEM_LINHA_UNICA__ UNION ALL
    SELECT '01', 'jan'__ORIGEM_LINHA_UNICA__ UNION ALL
    SELECT '02', 'fev'__ORIGEM_LINHA_UNICA__ UNION ALL
    SELECT '03', 'mar'__ORIGEM_LINHA_UNICA__ UNION ALL
    SELECT '04', 'abr'__ORIGEM_LINHA_UNICA__ UNION ALL
    SELECT '05', 'mai'__ORIGEM_LINHA_UNICA__ UNION ALL
    SELECT '06', 'jun'__ORIGEM_LINHA_UNICA__ UNION ALL
    SELECT '07', 'jul'__ORIGEM_LINHA_UNICA__ UNION ALL
    SELECT '08', 'ago'__ORIGEM_LINHA_UNICA__ UNION ALL
    SELECT '09', 'set'__ORIGEM_LINHA_UNICA__ UNION ALL
    SELECT '10', 'out'__ORIGEM_LINHA_UNICA__ UNION ALL
    SELECT '11', 'nov'__ORIGEM_LINHA_UNICA__ UNION ALL
    SELECT '12', 'dez'__ORIGEM_LINHA_UNICA__
),

datas_ref AS (
    SELECT
        c.codigobanco, c.codigoagencia, c.codigoconta, me.mes_label,
        (SELECT MAX(sb2.datasaldoatual)
         FROM STAGE.saldobancario sb2
         WHERE sb2.excluido = 0
           AND sb2.codigobanco = c.codigobanco AND sb2.codigoagencia = c.codigoagencia AND sb2.codigoconta = c.codigoconta
           AND TO_CHAR(sb2.datasaldoatual, 'MM') = me.mes_num
           AND TO_CHAR(sb2.datasaldoatual, 'YYYY') = :ano
        ) AS data_final
    FROM contas c
    CROSS JOIN meses me
),

saldos AS (
    SELECT
        dr.mes_label,
        COALESCE((
            SELECT __NUMERO_SALDO__ FROM STAGE.saldobancario sb3
            WHERE sb3.excluido = 0
              AND sb3.codigobanco = dr.codigobanco AND sb3.codigoagencia = dr.codigoagencia AND sb3.codigoconta = dr.codigoconta
              AND sb3.datasaldoatual = dr.data_final
        ), 0) AS saldo
    FROM datas_ref dr
),

saldo_banco AS (
    SELECT
        :filiais_label AS filial,
        SUM(CASE WHEN mes_label = 'ant' THEN saldo ELSE 0 END) AS sldfn_ant,
        SUM(CASE WHEN mes_label = 'jan' THEN saldo ELSE 0 END) AS sldfn_jan,
        SUM(CASE WHEN mes_label = 'fev' THEN saldo ELSE 0 END) AS sldfn_fev,
        SUM(CASE WHEN mes_label = 'mar' THEN saldo ELSE 0 END) AS sldfn_mar,
        SUM(CASE WHEN mes_label = 'abr' THEN saldo ELSE 0 END) AS sldfn_abr,
        SUM(CASE WHEN mes_label = 'mai' THEN saldo ELSE 0 END) AS sldfn_mai,
        SUM(CASE WHEN mes_label = 'jun' THEN saldo ELSE 0 END) AS sldfn_jun,
        SUM(CASE WHEN mes_label = 'jul' THEN saldo ELSE 0 END) AS sldfn_jul,
        SUM(CASE WHEN mes_label = 'ago' THEN saldo ELSE 0 END) AS sldfn_ago,
        SUM(CASE WHEN mes_label = 'set' THEN saldo ELSE 0 END) AS sldfn_set,
        SUM(CASE WHEN mes_label = 'out' THEN saldo ELSE 0 END) AS sldfn_out,
        SUM(CASE WHEN mes_label = 'nov' THEN saldo ELSE 0 END) AS sldfn_nov,
        SUM(CASE WHEN mes_label = 'dez' THEN saldo ELSE 0 END) AS sldfn_dez
    FROM saldos
)

-- =====================================================================
-- BLOCO 1: Detalhe das naturezas (corpo do relatorio)
-- =====================================================================
SELECT
    1 AS ordem_bloco,
    __NUMERO_ED_COND__ AS ordem_grupo,
    d.codigo_naturezas AS ordem_item,
    d.filial,
    d.codigo_naturezas,
    d.naturezas_sinteticas,
    d.jan, d.fev, d.mar, d.abr, d.mai, d.jun,
    d.jul, d.ago, d.set_ AS "set", d.out, d.nov, d.dez,
    d.total
FROM detalhe d

UNION ALL

-- =====================================================================
-- BLOCO 2: RESUMO — Saldo Bancario Inicial do Periodo
-- =====================================================================
SELECT
    2, 0, N'1',
    sb.filial,
    NULL,
    N'SALDO BANCARIO INICIAL DO PERIODO',
    sb.sldfn_ant, sb.sldfn_jan, sb.sldfn_fev, sb.sldfn_mar, sb.sldfn_abr,
    sb.sldfn_mai, sb.sldfn_jun, sb.sldfn_jul, sb.sldfn_ago, sb.sldfn_set,
    sb.sldfn_out, sb.sldfn_nov,
    0
FROM saldo_banco sb

UNION ALL

-- =====================================================================
-- BLOCO 2: RESUMO — Entradas (linha do detalhe com codigo_naturezas='1')
-- =====================================================================
SELECT
    2, 1, N'2',
    :filiais_label, NULL, N'ENTRADAS',
    d.jan, d.fev, d.mar, d.abr, d.mai, d.jun,
    d.jul, d.ago, d.set_, d.out, d.nov, d.dez,
    d.total
FROM detalhe d
WHERE TRIM(d.codigo_naturezas) = '1'

UNION ALL

-- =====================================================================
-- BLOCO 2: RESUMO — Saidas (linha do detalhe com codigo_naturezas='2')
-- =====================================================================
SELECT
    2, 2, N'3',
    :filiais_label, NULL, N'SAIDAS',
    d.jan, d.fev, d.mar, d.abr, d.mai, d.jun,
    d.jul, d.ago, d.set_, d.out, d.nov, d.dez,
    d.total
FROM detalhe d
WHERE TRIM(d.codigo_naturezas) = '2'

UNION ALL

-- =====================================================================
-- BLOCO 2: RESUMO — Saldo Bancario Final do Periodo
-- =====================================================================
SELECT
    2, 3, N'4',
    sb.filial, NULL,
    N'SALDO BANCARIO FINAL DO PERIODO',
    sb.sldfn_jan, sb.sldfn_fev, sb.sldfn_mar, sb.sldfn_abr, sb.sldfn_mai,
    sb.sldfn_jun, sb.sldfn_jul, sb.sldfn_ago, sb.sldfn_set, sb.sldfn_out,
    sb.sldfn_nov, sb.sldfn_dez,
    0
FROM saldo_banco sb

-- ORDER BY posicional (1, 2, 3), nao por nome (ordem_bloco, ordem_grupo,
-- ordem_item) -- por algum motivo Oracle devolve "ORDEM_BLOCO: invalid
-- identifier" ordenando por alias depois de um UNION ALL com a coluna
-- "set" entre aspas (reservada) no meio da lista de colunas do primeiro
-- SELECT; ordenar por posicao evita o problema e e equivalente.
ORDER BY 1, 2, 3
"""


def _buscar_fluxo_caixa_realizado(filiais: list[str], ano: str) -> tuple[list[str], list[tuple]]:
    clausula_filial, binds_filial = clausula_in("filial", filiais)
    sql = (
        _QUERY.replace("__FILIAL_IN__", clausula_filial)
        .replace("__ORIGEM_LINHA_UNICA__", _comum.origem_linha_unica())
        .replace("__NUMERO_SALDO__", _comum.numero_coluna("sb3.valorsaldoatual"))
        .replace("__NUMERO_ED_COND__", _comum.numero_coluna("d.ed_cond"))
        .replace("__NUMERO_ANO__", _comum.numero_bind("ano_numero"))
    )

    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, ano=ano, ano_numero=ano, filiais_label=", ".join(filiais), **binds_filial)
        colunas = [descricao[0] for descricao in cursor.description]
        linhas = cursor.fetchall()
    return colunas, linhas


def _parametros_da_query(request: Request) -> tuple[list[str], str] | None:
    filiais = _comum.filiais_da_query(request)
    ano = request.query_params.get("ano", "").strip()
    if filiais is None or not ano:
        return None
    return filiais, ano


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/fluxo-caixa-realizado/exportar", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def exportar_fluxo_caixa_realizado_route(request: Request, usuario: dict) -> Response:
        """RELATÓRIO: Fluxo de Caixa Realizado (FINR01) — exportação em Excel."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial e o ano."}, status_code=400, headers=CORS_HEADERS
            )

        colunas, linhas = _buscar_fluxo_caixa_realizado(*parametros)
        _comum.registrar_acesso(usuario, "fluxo_caixa_realizado:exportar", len(linhas))
        conteudo_xlsx = gerar_xlsx(colunas, linhas, titulo="Fluxo de Caixa Realizado")
        return Response(
            content=conteudo_xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="fluxo_caixa_realizado.xlsx"',
                **CORS_HEADERS,
            },
        )

    @mcp.custom_route("/api/financeiro/fluxo-caixa-realizado", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def listar_fluxo_caixa_realizado_route(request: Request, usuario: dict) -> JSONResponse:
        """RELATÓRIO: Fluxo de Caixa Realizado (FINR01) — endpoint JSON usado pela tela."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial e o ano."}, status_code=400, headers=CORS_HEADERS
            )

        colunas, linhas = _buscar_fluxo_caixa_realizado(*parametros)
        _comum.registrar_acesso(usuario, "fluxo_caixa_realizado:listar", len(linhas))
        dados = [
            dict(zip(colunas, (_comum.serializar(valor) for valor in linha), strict=True)) for linha in linhas
        ]
        return JSONResponse(dados, headers=CORS_HEADERS)
