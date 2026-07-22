"""RELATÓRIO: Baixa por Produtos (CAG06R04)

Tradução do ADVPL (GetZB4/BeginSql) — os filtros originais eram Filial
De/Até, Título De/Até (na verdade filtra ZB4_NUM, não o título inteiro),
Produto De/Até e Data da Baixa De/Até. Igual aos demais relatórios, a filial
virou seleção múltipla (em vez de faixa De/Até) para manter o mesmo padrão de
tela; título e produto continuam como faixa (De/Até).

ZB4 (baixa por produto) e ZB2 (tipo de produto comercial) não existiam no
banco de teste — foram criadas com dados de exemplo ligados às baixas/títulos
que já existiam em SE5010/SE1010 (veja o script de seed que gerei na
conversa). B1_XTPRCOM (tipo comercial do produto) também estava vazio em
SB1010 e foi populado nesse mesmo seed.

O vendedor no ADVPL original (getVend()) tinha um fallback: se o título não
tivesse E1_VEND1 preenchido, buscava o vendedor pela nota fiscal de saída de
origem (SD1+SF2). SD1 não existe nesse banco de teste, então aqui só usamos
E1_VEND1 direto — igual à simplificação já feita no FINR04 (Duplicata
Mercantil).

A "Categoria Cliente" (SA1010.A1_XCDCAT, decodificada via uma tabela genérica
"ZX" no ADVPL original) fica vazia aqui: a coluna está sempre NULL nesse
banco de teste e não existe uma tabela genérica equivalente — mantido assim
por não haver dado real pra decodificar.

Atenção: só roda com DB_BACKEND=postgres (cast ::tipo). E5_DATA nesse banco
de teste é VARCHAR (formato "YYYYMMDD"), por isso precisa do ::date antes de
comparar com os limites do período.
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
-- RELATORIO: Baixa por Produtos (CAG06R04) — Tradução do ADVPL (GetZB4)
-- =====================================================================
SELECT
    zb4.zb4_filial,
    zb4.zb4_prefix,
    zb4.zb4_num,
    zb4.zb4_parcel,
    zb4.zb4_tipo,
    sa1.a1_cod                 AS cod_cliente,
    sa1.a1_nome                AS nome_cliente,
    sa1.a1_nreduz               AS nome_fazenda,
    sa1.a1_xcdcat               AS categoria_cliente,
    sa3.a3_nome                AS nome_vendedor,
    sb1.b1_xtprcom || '-' || COALESCE(zb2.zb2_nome, '') AS tipo_produto,
    zb4.zb4_produt,
    sb1.b1_desc                AS descricao_produto,
    CASE WHEN zb4.zb4_tpmov = 'B' THEN 'Baixa' ELSE 'Estorno' END AS tipo_movimento,
    zb4.zb4_prunit,
    zb4.zb4_quant,
    zb4.zb4_valor,
    zb4.zb4_descon,
    zb4.zb4_juros,
    zb4.zb4_multa,
    zb4.zb4_recebi,
    se5.e5_motbx,
    se5.e5_documen,
    se5.e5_banco,
    se5.e5_seq,
    se5.e5_data
FROM zb4 zb4
INNER JOIN (
    SELECT
        e5_filial, e5_prefixo, e5_numero, e5_parcela, e5_tipo, e5_seq,
        e5_documen, e5_motbx, e5_banco, e5_clifor, e5_loja, e5_data
    FROM se5010
    WHERE COALESCE(d_e_l_e_t_, ' ') = ' '
      AND (
            :data_baixa_ini = '' OR :data_baixa_fim = ''
         OR e5_data::date BETWEEN NULLIF(:data_baixa_ini, '')::date AND NULLIF(:data_baixa_fim, '')::date
      )
    GROUP BY e5_filial, e5_prefixo, e5_numero, e5_parcela, e5_tipo, e5_seq,
             e5_documen, e5_motbx, e5_banco, e5_clifor, e5_loja, e5_data
) se5
    ON zb4.zb4_filial = se5.e5_filial
   AND zb4.zb4_prefix = se5.e5_prefixo
   AND zb4.zb4_num = se5.e5_numero
   AND zb4.zb4_parcel = se5.e5_parcela
   AND zb4.zb4_seq = se5.e5_seq
INNER JOIN sb1010 sb1
    ON COALESCE(sb1.d_e_l_e_t_, ' ') = ' '
   AND sb1.b1_cod = zb4.zb4_produt
LEFT JOIN zb2 zb2
    ON COALESCE(zb2.d_e_l_e_t_, ' ') = ' '
   AND zb2.zb2_filial = zb4.zb4_filial
   AND sb1.b1_xtprcom = zb2.zb2_cod
LEFT JOIN sa1010 sa1
    ON sa1.a1_cod = se5.e5_clifor
   AND sa1.a1_loja = se5.e5_loja
LEFT JOIN se1010 se1
    ON se1.e1_filial = zb4.zb4_filial
   AND se1.e1_prefixo = zb4.zb4_prefix
   AND se1.e1_num = zb4.zb4_num
   AND se1.e1_parcela = zb4.zb4_parcel
   AND se1.e1_tipo = zb4.zb4_tipo
LEFT JOIN sa3 sa3
    ON sa3.a3_cod = se1.e1_vend1
WHERE COALESCE(zb4.d_e_l_e_t_, ' ') = ' '
  AND TRIM(zb4.zb4_filial) IN __FILIAL_IN__
  AND (:titulo_ini = '' OR zb4.zb4_num >= :titulo_ini)
  AND (:titulo_fim = '' OR zb4.zb4_num <= :titulo_fim)
  AND (:produto_ini = '' OR zb4.zb4_produt >= :produto_ini)
  AND (:produto_fim = '' OR zb4.zb4_produt <= :produto_fim)
ORDER BY zb4.zb4_filial, zb4.zb4_num, zb4.zb4_parcel, zb4.zb4_tipo, zb4.zb4_produt
"""

_CAMPOS_OPCIONAIS = ("titulo_ini", "titulo_fim", "produto_ini", "produto_fim", "data_baixa_ini", "data_baixa_fim")


def _serializar(valor):
    return float(valor) if isinstance(valor, Decimal) else valor


def _buscar_baixas(filiais: list[str], opcionais: dict[str, str]) -> tuple[list[str], list[tuple]]:
    clausula_filial, binds_filial = clausula_in("filial", filiais)
    sql = _QUERY.replace("__FILIAL_IN__", clausula_filial)

    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, **opcionais, **binds_filial)
        colunas = [descricao[0] for descricao in cursor.description]
        linhas = cursor.fetchall()
    return colunas, linhas


def _parametros_da_query(request: Request) -> tuple[list[str], dict[str, str]] | None:
    filial_bruto = request.query_params.get("filial", "").strip()
    filiais = [item.strip() for item in filial_bruto.split(",") if item.strip()]
    if not filiais:
        return None

    opcionais = {chave: request.query_params.get(chave, "").strip() for chave in _CAMPOS_OPCIONAIS}
    return filiais, opcionais


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/baixa-produtos", methods=["GET", "OPTIONS"])
    async def listar_baixa_produtos_route(request: Request) -> JSONResponse:
        """RELATÓRIO: Baixa por Produtos (CAG06R04) — endpoint JSON usado pela tela."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse({"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS)

        colunas, linhas = _buscar_baixas(*parametros)
        dados = [dict(zip(colunas, (_serializar(valor) for valor in linha))) for linha in linhas]
        return JSONResponse(dados, headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/baixa-produtos/exportar", methods=["GET", "OPTIONS"])
    async def exportar_baixa_produtos_route(request: Request) -> Response:
        """RELATÓRIO: Baixa por Produtos (CAG06R04) — exportação em Excel."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse({"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS)

        colunas, linhas = _buscar_baixas(*parametros)
        conteudo_xlsx = gerar_xlsx(colunas, linhas, titulo="Baixa por Produtos")
        return Response(
            content=conteudo_xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="baixa_por_produtos.xlsx"',
                **CORS_HEADERS,
            },
        )
