"""RELATÓRIO: Posição dos Títulos a Receber (FINR130)

Tradução do ADVPL (`FINR130.PRW`, ~3.500 linhas) — o relatório real do
Protheus é, de longe, o mais complexo que já traduzimos. Gestão Corporativa,
GEM, multi-moeda e retenção de IR/PIS/COFINS/CSLL na baixa ficaram de fora
(dependem de parametrização/módulos que não dá pra confirmar).

Migrado do Oracle transacional do Protheus (SE1010/SE5010) para o STAGE
(SCIENCE_PROD, ETL/BI) — `STAGE.CONTARECEBER` no lugar de `SE1010`,
`STAGE.MOVIMENTACAOFINANCEIRA` no lugar de `SE5010`. Ver
`db/views/financeiro_science.sql`/README ("Views curadas do Financeiro")
pro modelo geral de PESSOA/SOURCETABLE.

O que ficou de fora nesta migração (não tinha equivalente confirmado no
STAGE):
- **Filtro "Banco" e "Loja"** — `STAGE.CONTARECEBER` não tem coluna de
  banco portador (equivalente a `E1_PORTADO`) nem loja separada do código
  da pessoa (mesma limitação estrutural documentada em `cadastros.py`).
- **Juros/multa calculados por taxa** — a versão anterior calculava juros e
  multa em tempo real a partir de `E1_PORCJUR`/`E1_VALJUR`/`E1_MULTA` (taxas
  configuradas no título). `STAGE.CONTARECEBER` só tem `VALORJUROS`/
  `VALORMULTA` como valores já realizados (tipicamente 0 num título ainda
  aberto) — expostos como estão, sem recalcular, porque não temos mais os
  campos de taxa pra fazer a conta.
- **Abatimento** e **reconstrução de títulos excluídos** (`FJU010`) — mesma
  limitação já documentada em `relacao_baixas.py`/`retencao_impostos.py`:
  sem coluna de título-pai nem tabela equivalente a `FJU010` no STAGE.
  `abatimento` fica sempre 0; a reconstrução de excluídos foi removida (o
  filtro `considerar_excluidos` não existe mais).
- **Valor Acessório (VA)** — mesma limitação de `relacao_baixas.py`
  (`FK1`/`FK2`/`FK6`, sem equivalente): `tem_valor_acessorio` e
  `valor_acessorio` ficam sempre 0/falso.

O que TEM fidelidade real:
- Filtros em faixa (cliente, prefixo, título, natureza, vencimento,
  emissão) + filial multi-select.
- Saldo do título: atual (`CONTARECEBER.SALDO`, já calculado pelo ETL) OU
  **retroativo**, reconstruído somando as baixas reais em
  `MOVIMENTACAOFINANCEIRA` até a data-base — pré-agregado numa CTE (`JOIN`
  em vez de subconsulta correlacionada por linha) porque a versão
  correlacionada, sem filtro de cliente, chegou a estourar 2 minutos contra
  o volume real do STAGE (36 mil títulos × 155 mil movimentações); a versão
  agregada roda em ~9s pro conjunto inteiro, sem filtro nenhum.
- Split vencido/a vencer com base em `DATAVENCIMENTO`/`DATAVENCIMENTOREAL`
  vs a data-base.

Datas em `CONTARECEBER`/`MOVIMENTACAOFINANCEIRA` já são `TIMESTAMP` de
verdade no STAGE (não precisa de `TO_DATE`/YYYYMMDD).

Filtros opcionais usam `:bind IS NULL OR :bind = ''` (não `:bind = ''`
puro) — ver o "ACHADO IMPORTANTE" no topo de `_comum.py`.
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
    "cliente": "t.cliente_codigo",
    "numero": "t.numero, t.prefixo, t.parcela",
    "vencimento": "t.data_vencimento_real",
    "natureza": "t.codigonatureza",
}

_QUERY = """
-- =====================================================================
-- RELATORIO: Posicao dos Titulos a Receber (FINR130) — versao STAGE
-- (abatimento/valor acessorio/titulos excluidos sem fonte confirmada)
-- =====================================================================
WITH titulos AS (
    SELECT
        TRIM(cr.codigoempresa) AS filial, TRIM(cr.prefixo) AS prefixo, TRIM(cr.numero) AS numero,
        TRIM(cr.parcela) AS parcela, TRIM(cr.tipo) AS tipo, TRIM(cr.codigopessoa) AS cliente_codigo,
        TRIM(cr.codigonatureza) AS codigonatureza,
        CAST(cr.dataemissao AS DATE) AS data_emissao,
        CAST(cr.datavencimento AS DATE) AS data_vencimento,
        CAST(cr.datavencimentoreal AS DATE) AS data_vencimento_real,
        cr.valortotal AS valor_original,
        cr.saldo,
        cr.valormulta, cr.valorjuros,
        cr.historico
    FROM STAGE.contareceber cr
    WHERE cr.excluido = 0
      AND TRIM(cr.codigoempresa) IN __FILIAL_IN__
      AND (:cliente_ini IS NULL OR :cliente_ini = '' OR cr.codigopessoa >= :cliente_ini)
      AND (:cliente_fim IS NULL OR :cliente_fim = '' OR cr.codigopessoa <= :cliente_fim)
      AND (:prefixo_ini IS NULL OR :prefixo_ini = '' OR TRIM(cr.prefixo) >= :prefixo_ini)
      AND (:prefixo_fim IS NULL OR :prefixo_fim = '' OR TRIM(cr.prefixo) <= :prefixo_fim)
      AND (:titulo_ini IS NULL OR :titulo_ini = '' OR TRIM(cr.numero) >= :titulo_ini)
      AND (:titulo_fim IS NULL OR :titulo_fim = '' OR TRIM(cr.numero) <= :titulo_fim)
      AND (:natureza_ini IS NULL OR :natureza_ini = '' OR cr.codigonatureza >= :natureza_ini)
      AND (:natureza_fim IS NULL OR :natureza_fim = '' OR cr.codigonatureza <= :natureza_fim)
      AND (
            :vencimento_ini IS NULL OR :vencimento_ini = '' OR :vencimento_fim IS NULL OR :vencimento_fim = ''
         OR cr.datavencimentoreal BETWEEN TO_DATE(NULLIF(:vencimento_ini, ''), 'YYYYMMDD') AND TO_DATE(NULLIF(:vencimento_fim, ''), 'YYYYMMDD')
      )
      AND (
            :emissao_ini IS NULL OR :emissao_ini = '' OR :emissao_fim IS NULL OR :emissao_fim = ''
         OR cr.dataemissao BETWEEN TO_DATE(NULLIF(:emissao_ini, ''), 'YYYYMMDD') AND TO_DATE(NULLIF(:emissao_fim, ''), 'YYYYMMDD')
      )
),
baixado_ate_data_base AS (
    -- Pré-agregado (JOIN) em vez de subconsulta correlacionada por título —
    -- ver docstring do módulo (correlacionada estourava 2 min sem filtro).
    SELECT TRIM(mf.filialorigem) AS filial, TRIM(mf.prefixo) AS prefixo, TRIM(mf.numero) AS numero,
           TRIM(mf.parcela) AS parcela, TRIM(mf.tipo) AS tipo, TRIM(mf.codigopessoa) AS cliente_codigo,
           SUM(mf.valor) AS valor_baixado
    FROM STAGE.movimentacaofinanceira mf
    WHERE mf.excluido = 0 AND mf.tipomovimentacao = 'RECEBER'
      AND mf.datamovimentacao <= TO_DATE(:data_base, 'YYYYMMDD')
    GROUP BY mf.filialorigem, mf.prefixo, mf.numero, mf.parcela, mf.tipo, mf.codigopessoa
)
SELECT
    t.filial,
    t.prefixo,
    t.numero,
    t.parcela,
    t.tipo,
    t.cliente_codigo,
    p.nome AS nome_cliente,
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
    t.valormulta,
    t.valorjuros,
    t.historico,
    0 AS titulo_reconstituido,
    0 AS tem_valor_acessorio,
    0 AS valor_acessorio
FROM titulos t
LEFT JOIN baixado_ate_data_base bx
    ON bx.filial = t.filial AND bx.prefixo = t.prefixo AND bx.numero = t.numero
   AND bx.parcela = t.parcela AND bx.tipo = t.tipo AND bx.cliente_codigo = t.cliente_codigo
LEFT JOIN STAGE.pessoa p ON p.codigo = t.cliente_codigo AND p.sourcetable = 'SA1010'
LEFT JOIN STAGE.natureza n ON n.codigo = t.codigonatureza
ORDER BY __ORDEM__
"""

_CAMPOS_OPCIONAIS = (
    "cliente_ini",
    "cliente_fim",
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

    ordenar_por = opcionais.pop("ordenar_por", "") or "cliente"
    ordem_sql = _ORDENS.get(ordenar_por, _ORDENS["cliente"])

    opcionais.setdefault("data_base", date.today().strftime("%Y%m%d"))

    sql = _QUERY.replace("__FILIAL_IN__", clausula_filial).replace("__ORDEM__", ordem_sql)

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
    @mcp.custom_route("/api/financeiro/posicao-titulos/exportar", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def exportar_posicao_titulos_route(request: Request, usuario: dict) -> Response:
        """RELATÓRIO: Posição dos Títulos a Receber (FINR130) — exportação em Excel."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS
            )

        colunas, linhas = _buscar_titulos(*parametros)
        _comum.registrar_acesso(usuario, "posicao_titulos:exportar", len(linhas))
        conteudo_xlsx = gerar_xlsx(colunas, linhas, titulo="Posição dos Títulos a Receber")
        return Response(
            content=conteudo_xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="posicao_titulos.xlsx"',
                **CORS_HEADERS,
            },
        )

    @mcp.custom_route("/api/financeiro/posicao-titulos", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def listar_posicao_titulos_route(request: Request, usuario: dict) -> JSONResponse:
        """RELATÓRIO: Posição dos Títulos a Receber (FINR130) — endpoint JSON usado pela tela."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS
            )

        colunas, linhas = _buscar_titulos(*parametros)
        _comum.registrar_acesso(usuario, "posicao_titulos:listar", len(linhas))
        dados = [
            dict(zip(colunas, (_comum.serializar(valor) for valor in linha), strict=True)) for linha in linhas
        ]
        return JSONResponse(dados, headers=CORS_HEADERS)
