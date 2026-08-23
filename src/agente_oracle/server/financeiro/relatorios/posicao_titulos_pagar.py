"""RELATÓRIO: Posição dos Títulos a Pagar (FINR150)

Tradução do ADVPL (`FINR150.PRX`) — é o espelho, para contas a pagar, do
FINR130/"Posição dos Títulos" (`posicao_titulos.py`, contas a receber).
Gestão Corporativa, GEM, multi-moeda e retenção de impostos na baixa ficaram
de fora (mesmo motivo do FINR130).

Migrado do Oracle transacional do Protheus (SE2010/SE5010) para o STAGE
(SCIENCE_PROD, ETL/BI) — `STAGE.CONTAPAGAR` no lugar de `SE2010`,
`STAGE.MOVIMENTACAOFINANCEIRA` no lugar de `SE5010`. Mesmas limitações já
documentadas em `posicao_titulos.py` (mesma família de relatório, mesmo
banco de origem):
- **Filtro "Banco" e "Loja"** — sem coluna equivalente em
  `STAGE.CONTAPAGAR`.
- **Juros/permanência** — o FINR150 original já não tinha campo de taxa por
  título (calculava via `Fa080Juros()`, função externa) — continua fora,
  sem mudança em relação à versão anterior.
- **Abatimento**, **reconstrução de títulos excluídos** (`FJU010`) e
  **Valor Acessório** (`FK1`/`FK2`/`FK6`/`FK7`) — mesma limitação
  estrutural do STAGE já documentada em `posicao_titulos.py`/
  `relacao_baixas.py`: sempre 0/falso.

O que TEM fidelidade real:
- Filtros em faixa (fornecedor, prefixo, título, natureza, vencimento,
  emissão) + filial multi-select.
- Saldo do título: atual (`CONTAPAGAR.SALDO`) OU **retroativo**,
  reconstruído somando as baixas reais em `MOVIMENTACAOFINANCEIRA`
  (`TIPOMOVIMENTACAO='PAGAR'`) até a data-base — mesma otimização de
  `posicao_titulos.py` (CTE pré-agregada em vez de subconsulta
  correlacionada, ~10s pro conjunto inteiro sem filtro).
- Split vencido/a vencer com base em `DATAVENCIMENTO`/`DATAVENCIMENTOREAL`
  vs a data-base.

Datas em `CONTAPAGAR`/`MOVIMENTACAOFINANCEIRA` já são `TIMESTAMP` de verdade
no STAGE (não precisa de `TO_DATE`/YYYYMMDD).

Filtros opcionais usam `:bind IS NULL OR :bind = ''` (não `:bind = ''`
puro) — ver o "ACHADO IMPORTANTE" no topo de `_comum.py`. Contra Postgres
esse padrão sozinho não basta (`AmbiguousParameter`) — a query passa por
`_comum.aplicar_cast_binds_opcionais()` antes de rodar.
"""

from datetime import date

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.db.connection import get_connection
from agente_oracle.relatorios import gerar_xlsx
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.server.financeiro.relatorios import _comum
from agente_oracle.server.financeiro.relatorios.filtros_sql import clausula_in

_ORDENS = {
    "fornecedor": "t.fornecedor_codigo",
    "numero": "t.numero, t.prefixo, t.parcela",
    "vencimento": "t.data_vencimento_real",
    "natureza": "t.codigonatureza",
}

_QUERY = """
-- =====================================================================
-- RELATORIO: Posicao dos Titulos a Pagar (FINR150) — versao STAGE
-- (abatimento/valor acessorio/titulos excluidos sem fonte confirmada)
-- =====================================================================
WITH titulos AS (
    SELECT
        TRIM(cp.codigoempresa) AS filial, TRIM(cp.prefixo) AS prefixo, TRIM(cp.numero) AS numero,
        TRIM(cp.parcela) AS parcela, TRIM(cp.tipo) AS tipo, TRIM(cp.codigopessoa) AS fornecedor_codigo,
        TRIM(cp.codigonatureza) AS codigonatureza,
        CAST(cp.dataemissao AS DATE) AS data_emissao,
        CAST(cp.datavencimento AS DATE) AS data_vencimento,
        CAST(cp.datavencimentoreal AS DATE) AS data_vencimento_real,
        cp.valortotal AS valor_original,
        cp.saldo,
        cp.historico
    FROM STAGE.contapagar cp
    WHERE cp.excluido = 0
      AND TRIM(cp.codigoempresa) IN __FILIAL_IN__
      AND (:fornecedor_ini IS NULL OR :fornecedor_ini = '' OR cp.codigopessoa >= :fornecedor_ini)
      AND (:fornecedor_fim IS NULL OR :fornecedor_fim = '' OR cp.codigopessoa <= :fornecedor_fim)
      AND (:prefixo_ini IS NULL OR :prefixo_ini = '' OR TRIM(cp.prefixo) >= :prefixo_ini)
      AND (:prefixo_fim IS NULL OR :prefixo_fim = '' OR TRIM(cp.prefixo) <= :prefixo_fim)
      AND (:titulo_ini IS NULL OR :titulo_ini = '' OR TRIM(cp.numero) >= :titulo_ini)
      AND (:titulo_fim IS NULL OR :titulo_fim = '' OR TRIM(cp.numero) <= :titulo_fim)
      AND (:natureza_ini IS NULL OR :natureza_ini = '' OR cp.codigonatureza >= :natureza_ini)
      AND (:natureza_fim IS NULL OR :natureza_fim = '' OR cp.codigonatureza <= :natureza_fim)
      AND (
            :vencimento_ini IS NULL OR :vencimento_ini = '' OR :vencimento_fim IS NULL OR :vencimento_fim = ''
         OR cp.datavencimentoreal BETWEEN TO_DATE(NULLIF(:vencimento_ini, ''), 'YYYYMMDD') AND TO_DATE(NULLIF(:vencimento_fim, ''), 'YYYYMMDD')
      )
      AND (
            :emissao_ini IS NULL OR :emissao_ini = '' OR :emissao_fim IS NULL OR :emissao_fim = ''
         OR cp.dataemissao BETWEEN TO_DATE(NULLIF(:emissao_ini, ''), 'YYYYMMDD') AND TO_DATE(NULLIF(:emissao_fim, ''), 'YYYYMMDD')
      )
),
baixado_ate_data_base AS (
    -- Pré-agregado (JOIN) em vez de subconsulta correlacionada por título —
    -- ver posicao_titulos.py (correlacionada estourava 2 min sem filtro).
    SELECT TRIM(mf.filialorigem) AS filial, TRIM(mf.prefixo) AS prefixo, TRIM(mf.numero) AS numero,
           TRIM(mf.parcela) AS parcela, TRIM(mf.tipo) AS tipo, TRIM(mf.codigopessoa) AS fornecedor_codigo,
           SUM(mf.valor) AS valor_baixado
    FROM STAGE.movimentacaofinanceira mf
    WHERE mf.excluido = 0 AND mf.tipomovimentacao = 'PAGAR'
      AND mf.datamovimentacao <= TO_DATE(:data_base, 'YYYYMMDD')
    GROUP BY mf.filialorigem, mf.prefixo, mf.numero, mf.parcela, mf.tipo, mf.codigopessoa
)
SELECT
    t.filial,
    t.prefixo,
    t.numero,
    t.parcela,
    t.tipo,
    t.fornecedor_codigo,
    p.nome AS nome_fornecedor,
    t.codigonatureza,
    n.descricao AS nome_natureza,
    t.data_emissao,
    t.data_vencimento,
    t.data_vencimento_real,
    t.valor_original,
    (
        CASE WHEN :saldo_retroativo = '1' THEN
            GREATEST(0, t.valor_original - COALESCE(bx.valor_baixado, 0))
        ELSE t.saldo
        END
    ) AS saldo,
    0 AS abatimento,
    (TO_DATE(:data_base, 'YYYYMMDD') - t.data_vencimento) AS dias_atraso,
    (CASE WHEN TO_DATE(:data_base, 'YYYYMMDD') > t.data_vencimento_real THEN 1 ELSE 0 END) AS vencido,
    t.historico,
    0 AS titulo_reconstituido,
    0 AS tem_valor_acessorio,
    0 AS valor_acessorio
FROM titulos t
LEFT JOIN baixado_ate_data_base bx
    ON bx.filial = t.filial AND bx.prefixo = t.prefixo AND bx.numero = t.numero
   AND bx.parcela = t.parcela AND bx.tipo = t.tipo AND bx.fornecedor_codigo = t.fornecedor_codigo
LEFT JOIN STAGE.pessoa p ON p.codigo = t.fornecedor_codigo AND p.sourcetable = 'SA2010'
LEFT JOIN STAGE.natureza n ON n.codigo = t.codigonatureza
ORDER BY __ORDEM__
"""

_CAMPOS_OPCIONAIS = (
    "fornecedor_ini",
    "fornecedor_fim",
    "prefixo_ini",
    "prefixo_fim",
    "titulo_ini",
    "titulo_fim",
    "natureza_ini",
    "natureza_fim",
    "vencimento_ini",
    "vencimento_fim",
    "emissao_ini",
    "emissao_fim",
    "saldo_retroativo",
    "ordenar_por",
)


def _buscar_titulos(filiais: list[str], opcionais: dict[str, str]) -> tuple[list[str], list[tuple]]:
    clausula_filial, binds_filial = clausula_in("filial", filiais)

    ordenar_por = opcionais.pop("ordenar_por", "") or "fornecedor"
    ordem_sql = _ORDENS.get(ordenar_por, _ORDENS["fornecedor"])

    opcionais.setdefault("data_base", date.today().strftime("%Y%m%d"))

    sql = _QUERY.replace("__FILIAL_IN__", clausula_filial).replace("__ORDEM__", ordem_sql)
    sql = _comum.aplicar_cast_binds_opcionais(sql)

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

    return filiais, _comum.parametros_opcionais(request, _CAMPOS_OPCIONAIS)


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/posicao-titulos-pagar/exportar", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def exportar_posicao_titulos_pagar_route(request: Request, usuario: dict) -> Response:
        """RELATÓRIO: Posição dos Títulos a Pagar (FINR150) — exportação em Excel."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS
            )

        colunas, linhas = _buscar_titulos(*parametros)
        _comum.registrar_acesso(usuario, "posicao_titulos_pagar:exportar", len(linhas))
        conteudo_xlsx = gerar_xlsx(colunas, linhas, titulo="Posição dos Títulos a Pagar")
        return Response(
            content=conteudo_xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="posicao_titulos_pagar.xlsx"',
                **CORS_HEADERS,
            },
        )

    @mcp.custom_route("/api/financeiro/posicao-titulos-pagar", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def listar_posicao_titulos_pagar_route(request: Request, usuario: dict) -> JSONResponse:
        """RELATÓRIO: Posição dos Títulos a Pagar (FINR150) — endpoint JSON usado pela tela."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS
            )

        colunas, linhas = _buscar_titulos(*parametros)
        _comum.registrar_acesso(usuario, "posicao_titulos_pagar:listar", len(linhas))
        dados = [
            dict(zip(colunas, (_comum.serializar(valor) for valor in linha), strict=True)) for linha in linhas
        ]
        return JSONResponse(dados, headers=CORS_HEADERS)
