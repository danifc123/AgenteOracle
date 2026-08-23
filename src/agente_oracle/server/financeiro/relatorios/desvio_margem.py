"""RELATÓRIO: Desvio de Margem — não é tradução de relatório legado
(sem código FINRxxx equivalente), item novo da planilha de demandas de
IA do Financeiro ("Analisador de Desvio de Margem").

Mesmo espírito de `agent/financeiro/projecoes.py` ("100% cálculo
estatístico, sem IA"): margem é conta objetiva a partir de dado real
(`valor_total`/`custo` já existem em `vw_faturamento`), não julgamento
— então fica fora do agente de IA, puro SQL, número nunca depende do
Ollama estar no ar.

Usa a view curada `vw_faturamento` (`agent/financeiro/schema.py`) em vez
das tabelas brutas do STAGE que o resto de `relatorios/*.py` usa — não
há relatório ADVPL original pra manter fidelidade against, então não há
motivo pra pagar a complexidade das tabelas brutas."""

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
-- RELATORIO: Desvio de Margem (novo — sem FINRxxx equivalente)
-- =====================================================================
WITH linhas AS (
    SELECT
        filial, nota_fiscal, serie, item_nota, cliente_nome, vendedor_nome,
        produto_codigo, produto_descricao, data_emissao, valor_total, custo
    FROM vw_faturamento
    WHERE filial IN __FILIAL_IN__
      AND data_emissao BETWEEN TO_DATE(:emissao_ini, 'YYYYMMDD') AND TO_DATE(:emissao_fim, 'YYYYMMDD')
      AND __FILTRO_PRODUTO__
      AND valor_total > 0
)
SELECT
    filial,
    nota_fiscal,
    serie,
    item_nota,
    cliente_nome,
    vendedor_nome,
    produto_codigo,
    produto_descricao,
    data_emissao,
    valor_total,
    custo,
    ROUND((valor_total - custo) / valor_total * 100, 2) AS margem_percentual,
    ROUND(AVG((valor_total - custo) / valor_total * 100) OVER (PARTITION BY produto_codigo), 2)
        AS margem_media_produto,
    ROUND(
        ((valor_total - custo) / valor_total * 100)
        - AVG((valor_total - custo) / valor_total * 100) OVER (PARTITION BY produto_codigo),
        2
    ) AS desvio_percentual
FROM linhas
ORDER BY desvio_percentual ASC
"""

_CAMPOS_OPCIONAIS = ("emissao_ini", "emissao_fim", "produto")


def _buscar_desvios(filiais: list[str], opcionais: dict[str, str]) -> tuple[list[str], list[tuple]]:
    clausula_filial, binds_filial = clausula_in("filial", filiais)

    # `_comum.texto_coluna(":produto")` no primeiro uso, não `filtro_vazio()`
    # puro: contra Postgres, `:produto IS NULL OR :produto = ''` sozinho não
    # dá pro Postgres inferir o tipo do bind em modo prepared statement
    # (`AmbiguousParameter`/`could not determine data type`), mesmo com
    # `produto_codigo = :produto` mais adiante na mesma cláusula — precisa
    # de um CAST explícito em algum ponto pra resolver (confirmado rodando
    # de verdade contra o Postgres de teste). CAST(texto AS TEXT/VARCHAR2)
    # não muda o valor, só dá o tipo que faltava.
    filtro_produto = (
        f"({_comum.texto_coluna(':produto')} IS NULL OR :produto = '' OR produto_codigo = :produto)"
    )
    sql = _QUERY.replace("__FILIAL_IN__", clausula_filial).replace("__FILTRO_PRODUTO__", filtro_produto)

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

    opcionais = _comum.parametros_opcionais(request, _CAMPOS_OPCIONAIS)
    if not opcionais.get("emissao_ini") or not opcionais.get("emissao_fim"):
        return None

    return filiais, opcionais


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/desvio-margem/exportar", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def exportar_desvio_margem_route(request: Request, usuario: dict) -> Response:
        """RELATÓRIO: Desvio de Margem — exportação em Excel."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse(
                {"erro": "Informe filial e o período de emissão."}, status_code=400, headers=CORS_HEADERS
            )

        colunas, linhas = _buscar_desvios(*parametros)
        _comum.registrar_acesso(usuario, "desvio_margem:exportar", len(linhas))
        conteudo_xlsx = gerar_xlsx(colunas, linhas, titulo="Desvio de Margem")
        return Response(
            content=conteudo_xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="desvio_margem.xlsx"',
                **CORS_HEADERS,
            },
        )

    @mcp.custom_route("/api/financeiro/desvio-margem", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def listar_desvio_margem_route(request: Request, usuario: dict) -> JSONResponse:
        """RELATÓRIO: Desvio de Margem — endpoint JSON usado pela tela."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse(
                {"erro": "Informe filial e o período de emissão."}, status_code=400, headers=CORS_HEADERS
            )

        colunas, linhas = _buscar_desvios(*parametros)
        _comum.registrar_acesso(usuario, "desvio_margem:listar", len(linhas))
        dados = [
            dict(zip(colunas, (_comum.serializar(valor) for valor in linha), strict=True)) for linha in linhas
        ]
        return JSONResponse(dados, headers=CORS_HEADERS)
