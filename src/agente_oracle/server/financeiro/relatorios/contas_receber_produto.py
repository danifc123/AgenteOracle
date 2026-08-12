"""RELATÓRIO: Contas a Receber com Descrição do Produto

Tradução original a partir de uma consulta SQL enviada pelo desenvolvedor
sênior de ADVPL da empresa (SC5010/SC6010, com `statusped` calculado por uma
árvore de CASE replicando `c5_liberok`/`c5_nota`/`c5_blq`).

Migrado do Oracle transacional do Protheus para o STAGE (SCIENCE_PROD,
ETL/BI) — grande simplificação aqui: `STAGE.PEDIDOVENDA` já entrega
`STATUSPEDIDO` e `QUANTIDADESALDO` prontos, calculados pelo próprio ETL
(mesma árvore de status, só que já resolvida) — não precisamos mais das
subconsultas correlacionadas (`c6sqtdven`/`c6sqtdent`) nem da árvore de CASE
gigante. Ver `db/views/financeiro_science.sql`/README ("Views curadas do
Financeiro") pro modelo geral de PESSOA/SOURCETABLE.

O que ficou de fora nesta migração (não tinha equivalente confirmado no
STAGE):
- Filtro "Entrega" (`C5_DATA1`, data de entrega prevista do pedido) — não
  achamos coluna equivalente em `STAGE.PEDIDOVENDA`.
- Conversão de moeda (`mult_vlr`/`C5_TXMOEDA`) — `PEDIDOVENDA.TAXA` existe e
  varia de fato (não é sempre 1), mas não confirmamos se
  `VALORUNITARIO`/`VALORTOTAL` já vêm convertidos pelo ETL ou ainda em
  moeda estrangeira crua. Os valores aqui são usados como estão, sem
  multiplicar por `TAXA` — precisa validar com um pedido real em moeda
  estrangeira antes de confiar nos totais desse caso.
- "Data de entrega" à parte da emissão — mesmo motivo do primeiro item.

O que continua igual:
- Totais por pedido e por cliente+safra via `SUM(...) OVER (PARTITION BY
  ...)`, calculados depois do filtro de status/saldo pendente (mesma ordem
  de avaliação do SQL original).
- Filtro final: `status_pedido NOT IN ('CANCELADO', 'DEVOLUCAO -
  ENCERRADO', 'ELIMINADO RESIDUO', 'FATURADO TOTAL')` e
  `quantidade_saldo <> 0` — só traz o que ainda está pendente de
  entrega/faturamento.

Filtros opcionais usam `:bind IS NULL OR :bind = ''` (não `:bind = ''`
puro) — ver o "ACHADO IMPORTANTE" no topo de `_comum.py`.
"""

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
-- RELATORIO: Contas a Receber com Descricao do Produto
-- versao STAGE (status_pedido/quantidade_saldo ja vem prontos do ETL)
-- =====================================================================
WITH itens AS (
    SELECT
        TRIM(pv.codigoempresa)              AS filial,
        TRIM(pv.codigocliente)              AS cliente_codigo,
        p.nome                              AS cliente_nome,
        p.nomefantasia                      AS cliente_nome_reduzido,
        p.telefone                          AS cliente_telefone,
        p.cpfcnpj                           AS cliente_cnpj_cpf,
        p.rginscricaoestadual               AS cliente_inscricao_estadual,
        m.descricao                         AS cliente_municipio,
        m.codigoestado                      AS cliente_uf,
        p.email                             AS cliente_email,
        TRIM(pv.codigosafra)                AS codigo_safra,
        CAST(pv.dataemissao AS DATE)        AS data_emissao,
        TRIM(pv.tipo)                       AS tipo_pedido,
        TRIM(pv.numero)                     AS numero_pedido,
        pv.sequencialitem                   AS item,
        TRIM(pv.codigoproduto)              AS produto_codigo,
        prod.descricao                      AS produto_descricao,
        pv.quantidade                       AS quantidade_pedida,
        pv.valorunitario                    AS preco_unitario,
        pv.valortotal                       AS valor_total,
        pv.quantidadeentregue               AS quantidade_entregue,
        pv.quantidadesaldo                  AS quantidade_saldo,
        (pv.quantidadeentregue * pv.valorunitario) AS valor_entregue,
        (pv.quantidadesaldo * pv.valorunitario)    AS valor_a_entregar,
        pv.statuspedido                     AS status_pedido
    FROM STAGE.pedidovenda pv
    LEFT JOIN STAGE.pessoa p ON p.codigo = pv.codigocliente AND p.sourcetable = 'SA1010'
    LEFT JOIN STAGE.municipio m ON m.codigo = p.codigomunicipio
    LEFT JOIN STAGE.produto prod ON prod.codigo = pv.codigoproduto
    WHERE pv.excluido = 0
      AND TRIM(pv.codigoempresa) IN __FILIAL_IN__
      AND (:cliente_lista IS NULL OR :cliente_lista = '' OR pv.codigocliente IN __CLIENTE_IN__)
      AND (
            :emissao_ini IS NULL OR :emissao_ini = '' OR :emissao_fim IS NULL OR :emissao_fim = ''
         OR pv.dataemissao BETWEEN TO_DATE(NULLIF(:emissao_ini, ''), 'YYYYMMDD') AND TO_DATE(NULLIF(:emissao_fim, ''), 'YYYYMMDD')
      )
      AND (:naturezas IS NULL OR :naturezas = '' OR __NATUREZAS_PERTENCE_LISTA__)
      AND pv.statuspedido NOT IN ('CANCELADO', 'DEVOLUCAO - ENCERRADO', 'ELIMINADO RESIDUO', 'FATURADO TOTAL')
      AND pv.quantidadesaldo <> 0
)
SELECT
    i.*,
    SUM(i.quantidade_pedida) OVER (PARTITION BY i.cliente_codigo, i.filial, i.codigo_safra, i.numero_pedido) AS total_pedido_quantidade,
    SUM(i.valor_total) OVER (PARTITION BY i.cliente_codigo, i.filial, i.codigo_safra, i.numero_pedido) AS total_pedido_valor,
    SUM(i.quantidade_entregue) OVER (PARTITION BY i.cliente_codigo, i.filial, i.codigo_safra, i.numero_pedido) AS total_pedido_entregue,
    SUM(i.quantidade_saldo) OVER (PARTITION BY i.cliente_codigo, i.filial, i.codigo_safra, i.numero_pedido) AS total_pedido_saldo,
    SUM(i.quantidade_pedida) OVER (PARTITION BY i.cliente_codigo, i.filial, i.codigo_safra) AS total_safra_quantidade,
    SUM(i.valor_total) OVER (PARTITION BY i.cliente_codigo, i.filial, i.codigo_safra) AS total_safra_valor,
    SUM(i.quantidade_entregue) OVER (PARTITION BY i.cliente_codigo, i.filial, i.codigo_safra) AS total_safra_entregue,
    SUM(i.quantidade_saldo) OVER (PARTITION BY i.cliente_codigo, i.filial, i.codigo_safra) AS total_safra_saldo
FROM itens i
ORDER BY i.filial, i.cliente_codigo, i.numero_pedido, i.item
"""

_CAMPOS_OPCIONAIS = ("emissao_ini", "emissao_fim", "naturezas")


def _buscar_pedidos(
    filiais: list[str], clientes: list[str], opcionais: dict[str, str]
) -> tuple[list[str], list[tuple]]:
    clausula_filial, binds_filial = clausula_in("filial", filiais)
    clausula_cliente, binds_cliente = clausula_in("cliente", clientes) if clientes else ("('')", {})

    opcionais["cliente_lista"] = ",".join(clientes)

    sql = (
        _QUERY.replace("__FILIAL_IN__", clausula_filial)
        .replace("__CLIENTE_IN__", clausula_cliente)
        .replace(
            "__NATUREZAS_PERTENCE_LISTA__", _comum.pertence_lista("TRIM(pv.codigonatureza)", "naturezas", ";")
        )
    )

    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, **opcionais, **binds_filial, **binds_cliente)
        colunas = [descricao[0] for descricao in cursor.description]
        linhas = cursor.fetchall()
    return colunas, linhas


def _parametros_da_query(request: Request) -> tuple[list[str], list[str], dict[str, str]] | None:
    filiais = _comum.filiais_da_query(request)
    if filiais is None:
        return None

    cliente_bruto = request.query_params.get("cliente", "").strip()
    clientes = [item.strip() for item in cliente_bruto.split(",") if item.strip()]

    return filiais, clientes, _comum.parametros_opcionais(request, _CAMPOS_OPCIONAIS)


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/contas-receber-produto/exportar", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_financeiro)
    async def exportar_contas_receber_produto_route(request: Request, usuario: dict) -> Response:
        """RELATÓRIO: Contas a Receber com Descrição do Produto — exportação em Excel."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS
            )

        colunas, linhas = _buscar_pedidos(*parametros)
        conteudo_xlsx = gerar_xlsx(colunas, linhas, titulo="Contas a Receber com Descrição do Produto")
        return Response(
            content=conteudo_xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="contas_receber_produto.xlsx"',
                **CORS_HEADERS,
            },
        )

    @mcp.custom_route("/api/financeiro/contas-receber-produto", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=exigir_modulo_financeiro)
    async def listar_contas_receber_produto_route(request: Request, usuario: dict) -> JSONResponse:
        """RELATÓRIO: Contas a Receber com Descrição do Produto — endpoint JSON usado pela tela."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS
            )

        colunas, linhas = _buscar_pedidos(*parametros)
        dados = [
            dict(zip(colunas, (_comum.serializar(valor) for valor in linha), strict=True)) for linha in linhas
        ]
        return JSONResponse(dados, headers=CORS_HEADERS)
