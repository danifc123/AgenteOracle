"""RELATÓRIO: Posição dos Títulos a Receber por Vendedor (FINR137)

Tradução do ADVPL (`FINR137.PRX`) — parente do FINR130/"Posição dos Títulos"
(`posicao_titulos.py`), organizado por vendedor. Na versão Protheus
original, um mesmo título podia aparecer uma vez para CADA vendedor
preenchido nele (`E1_VEND1` até `E1_VEND5`, explosão em até 5 linhas).

Migrado do Oracle transacional do Protheus (SE1010/SE5010) para o STAGE
(SCIENCE_PROD, ETL/BI) — `STAGE.CONTARECEBER` no lugar de `SE1010`. Ver
`db/views/financeiro_science.sql`/README ("Views curadas do Financeiro")
pro modelo geral de PESSOA/SOURCETABLE.

MUDANÇA DE COMPORTAMENTO nesta migração: `STAGE.CONTARECEBER` só tem UM
campo de vendedor (`VENDEDOR`), não os 5 slots do Protheus cru — a
explosão por vendedor (`UNION ALL` x5 da versão anterior) foi removida.
Cada título agora aparece **no máximo uma vez**, com o vendedor único que o
STAGE carrega (na prática, o que seria `E1_VEND1`). Perde a visão de
"vendedor 2 a 5" que a versão anterior simulava.

ACHADO ao validar: código de vendedor **não é uma chave única** em
`STAGE.PESSOA` (`SOURCETABLE='SA3010'`) — existem códigos genéricos de
"vendedor da loja" reaproveitados entre filiais diferentes (ex: código
'000000' aparece 7 vezes, com nomes diferentes). `PESSOA` não tem coluna de
filial pra desambiguar. `nome_vendedor` usa `ROW_NUMBER()` (menor
`IDENTIFICATOR`) só pra ser determinístico entre execuções — não é garantia
de ser o nome "certo" para códigos genéricos duplicados.

O que ficou de fora nesta migração (não tinha equivalente confirmado no
STAGE, mesma limitação estrutural documentada em `posicao_titulos.py`):
- **Cadeia de liquidação** (título liquidado apontando pro vendedor do
  título original) — sem dado pra validar, já estava fora da versão
  anterior também.
- **Juros/multa calculados por taxa** e **Valor Acessório** — mesma
  limitação de `posicao_titulos.py`: sempre 0/falso.
- **Filtro "Loja"** — mesma limitação estrutural documentada em
  `cadastros.py`.

O que TEM fidelidade real:
- Filtros em faixa (cliente, emissão, vencimento, vendedor) + tipos a
  considerar/não considerar (`;`-separados) + filial multi-select.
- Títulos de tipo abatimento (`AB|FA`) sempre excluídos, sem opção pra
  desligar — igual à versão anterior.
- Saldo do título: atual (`CONTARECEBER.SALDO`) OU **retroativo**, mesma
  lógica de `posicao_titulos.py` (CTE pré-agregada, não correlacionada).
- Dias de atraso, natureza (nome via `STAGE.NATUREZA`), título liquidado
  (`NUMEROLIQUIDACAO` cru).

Filtros opcionais usam `:bind IS NULL OR :bind = ''` (não `:bind = ''`
puro) — ver o "ACHADO IMPORTANTE" no topo de `_comum.py`.
"""

from datetime import date

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.db.connection import get_connection
from agente_oracle.relatorios import gerar_xlsx
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.auth.dependencia import exigir_modulo_financeiro
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.server.financeiro.relatorios import _comum
from agente_oracle.server.financeiro.relatorios.filtros_sql import clausula_in

_QUERY = """
-- =====================================================================
-- RELATORIO: Posicao dos Titulos a Receber por Vendedor (FINR137) — STAGE
-- (sem explosao multi-vendedor/cadeia de liquidacao/valor acessorio)
-- =====================================================================
WITH vendedores_dedup AS (
    -- ROW_NUMBER so pra ser deterministico -- codigo de vendedor tem
    -- duplicata real no STAGE (ver docstring do modulo).
    SELECT codigo, nome, ROW_NUMBER() OVER (PARTITION BY codigo ORDER BY identificator) AS posicao
    FROM STAGE.pessoa WHERE sourcetable = 'SA3010'
),
titulos AS (
    SELECT
        TRIM(cr.codigoempresa) AS filial, TRIM(cr.prefixo) AS prefixo, TRIM(cr.numero) AS numero,
        TRIM(cr.parcela) AS parcela, TRIM(cr.tipo) AS tipo, TRIM(cr.codigopessoa) AS cliente_codigo,
        TRIM(cr.codigonatureza) AS codigonatureza,
        CAST(cr.dataemissao AS DATE) AS data_emissao,
        CAST(cr.datavencimento AS DATE) AS data_vencimento,
        cr.valortotal AS valor_original,
        cr.saldo,
        TRIM(cr.vendedor) AS vendedor_codigo,
        TRIM(cr.numeroliquidacao) AS titulo_liquidado
    FROM STAGE.contareceber cr
    WHERE cr.excluido = 0
      AND TRIM(cr.codigoempresa) IN __FILIAL_IN__
      AND cr.vendedor IS NOT NULL
      AND NOT (__TIPOS_ABATIMENTO_PERTENCE__)
      AND (:cliente_ini IS NULL OR :cliente_ini = '' OR cr.codigopessoa >= :cliente_ini)
      AND (:cliente_fim IS NULL OR :cliente_fim = '' OR cr.codigopessoa <= :cliente_fim)
      AND (:vendedor_ini IS NULL OR :vendedor_ini = '' OR TRIM(cr.vendedor) >= :vendedor_ini)
      AND (:vendedor_fim IS NULL OR :vendedor_fim = '' OR TRIM(cr.vendedor) <= :vendedor_fim)
      AND (
            :emissao_ini IS NULL OR :emissao_ini = '' OR :emissao_fim IS NULL OR :emissao_fim = ''
         OR cr.dataemissao BETWEEN TO_DATE(NULLIF(:emissao_ini, ''), 'YYYYMMDD') AND TO_DATE(NULLIF(:emissao_fim, ''), 'YYYYMMDD')
      )
      AND (
            :vencimento_ini IS NULL OR :vencimento_ini = '' OR :vencimento_fim IS NULL OR :vencimento_fim = ''
         OR cr.datavencimento BETWEEN TO_DATE(NULLIF(:vencimento_ini, ''), 'YYYYMMDD') AND TO_DATE(NULLIF(:vencimento_fim, ''), 'YYYYMMDD')
      )
      AND (:tipos_incluir IS NULL OR :tipos_incluir = '' OR __TIPOS_INCLUIR_PERTENCE__)
      AND (:tipos_excluir IS NULL OR :tipos_excluir = '' OR NOT (__TIPOS_EXCLUIR_PERTENCE__))
),
baixado_ate_data_base AS (
    SELECT TRIM(mf.filialorigem) AS filial, TRIM(mf.prefixo) AS prefixo, TRIM(mf.numero) AS numero,
           TRIM(mf.parcela) AS parcela, TRIM(mf.tipo) AS tipo, TRIM(mf.codigopessoa) AS cliente_codigo,
           SUM(mf.valor) AS valor_baixado
    FROM STAGE.movimentacaofinanceira mf
    WHERE mf.excluido = 0 AND mf.tipomovimentacao = 'RECEBER'
      AND mf.datamovimentacao <= TO_DATE(:data_base, 'YYYYMMDD')
    GROUP BY mf.filialorigem, mf.prefixo, mf.numero, mf.parcela, mf.tipo, mf.codigopessoa
)
SELECT
    t.vendedor_codigo,
    v.nome AS nome_vendedor,
    t.filial,
    t.prefixo,
    t.numero,
    t.parcela,
    t.tipo,
    t.cliente_codigo,
    p.nome AS nome_cliente,
    t.data_emissao,
    t.data_vencimento,
    t.valor_original,
    (
        CASE WHEN :saldo_retroativo = '1' THEN
            GREATEST(0, t.valor_original - COALESCE(bx.valor_baixado, 0))
        ELSE t.saldo
        END
    ) AS saldo,
    t.codigonatureza,
    n.descricao AS nome_natureza,
    t.titulo_liquidado,
    (TO_DATE(:data_base, 'YYYYMMDD') - t.data_vencimento) AS dias_atraso,
    0 AS tem_valor_acessorio,
    0 AS valor_acessorio
FROM titulos t
LEFT JOIN baixado_ate_data_base bx
    ON bx.filial = t.filial AND bx.prefixo = t.prefixo AND bx.numero = t.numero
   AND bx.parcela = t.parcela AND bx.tipo = t.tipo AND bx.cliente_codigo = t.cliente_codigo
LEFT JOIN vendedores_dedup v ON v.codigo = t.vendedor_codigo AND v.posicao = 1
LEFT JOIN STAGE.pessoa p ON p.codigo = t.cliente_codigo AND p.sourcetable = 'SA1010'
LEFT JOIN STAGE.natureza n ON n.codigo = t.codigonatureza
ORDER BY t.vendedor_codigo, t.prefixo, t.numero, t.parcela, t.tipo
"""

_CAMPOS_OPCIONAIS = (
    "cliente_ini",
    "cliente_fim",
    "emissao_ini",
    "emissao_fim",
    "vencimento_ini",
    "vencimento_fim",
    "vendedor_ini",
    "vendedor_fim",
    "tipos_incluir",
    "tipos_excluir",
    "saldo_retroativo",
)

_TIPOS_ABATIMENTO_PADRAO = "AB|FA"


def _buscar_titulos(filiais: list[str], opcionais: dict[str, str]) -> tuple[list[str], list[tuple]]:
    clausula_filial, binds_filial = clausula_in("filial", filiais)

    opcionais["tipos_abatimento"] = _TIPOS_ABATIMENTO_PADRAO
    opcionais.setdefault("data_base", date.today().strftime("%Y%m%d"))

    sql = (
        _QUERY.replace("__FILIAL_IN__", clausula_filial)
        .replace("__TIPOS_ABATIMENTO_PERTENCE__", _comum.pertence_lista("TRIM(cr.tipo)", "tipos_abatimento"))
        .replace("__TIPOS_INCLUIR_PERTENCE__", _comum.pertence_lista("TRIM(cr.tipo)", "tipos_incluir", ";"))
        .replace("__TIPOS_EXCLUIR_PERTENCE__", _comum.pertence_lista("TRIM(cr.tipo)", "tipos_excluir", ";"))
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

    return filiais, _comum.parametros_opcionais(request, _CAMPOS_OPCIONAIS)


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/posicao-titulos-vendedor/exportar", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_financeiro)
    async def exportar_posicao_titulos_vendedor_route(request: Request, usuario: dict) -> Response:
        """RELATÓRIO: Posição dos Títulos a Receber por Vendedor (FINR137) — exportação em Excel."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS
            )

        colunas, linhas = _buscar_titulos(*parametros)
        conteudo_xlsx = gerar_xlsx(colunas, linhas, titulo="Posição dos Títulos a Receber por Vendedor")
        return Response(
            content=conteudo_xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="posicao_titulos_vendedor.xlsx"',
                **CORS_HEADERS,
            },
        )

    @mcp.custom_route("/api/financeiro/posicao-titulos-vendedor", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_financeiro)
    async def listar_posicao_titulos_vendedor_route(request: Request, usuario: dict) -> JSONResponse:
        """RELATÓRIO: Posição dos Títulos a Receber por Vendedor (FINR137) — endpoint JSON usado pela tela."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS
            )

        colunas, linhas = _buscar_titulos(*parametros)
        dados = [
            dict(zip(colunas, (_comum.serializar(valor) for valor in linha), strict=True)) for linha in linhas
        ]
        return JSONResponse(dados, headers=CORS_HEADERS)
