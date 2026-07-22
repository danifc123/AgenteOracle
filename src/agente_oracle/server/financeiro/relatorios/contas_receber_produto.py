"""RELATÓRIO: Contas a Receber com Descrição do Produto

Tradução direta de uma consulta SQL já pronta, enviada pelo desenvolvedor
sênior de ADVPL da empresa (não um `.prx`/`.prw` de tela como os outros
relatórios) — pega os itens de pedido de venda (SC6010) de pedidos "normais"
(SC5010, C5_TIPO='N'), com a descrição do produto (SB1010) e o status de
faturamento de cada pedido (`statusped`), calculado a partir da comparação
entre a quantidade vendida e a quantidade já entregue/faturada do pedido
inteiro (não só do item).

Nota de histórico: a primeira versão desse relatório foi feita em cima de
outra consulta (baseada em SE1010, títulos a receber) que o dev sênior tinha
mandado antes — depois foi confirmado que aquela consulta não era essa,
e sim a que está implementada aqui (SC5010/SC6010), então essa versão
substitui a anterior por completo.

Fidelidade ao SQL enviado:
- `c6sqtdven`/`c6sqtdent`: subconsultas correlacionadas que somam a
  quantidade vendida/entregue de TODOS os itens do mesmo pedido (não just
  do item da linha) — usadas pra decidir o status do pedido como um todo.
- `statusped`: réplica exata da árvore de CASE original — combina
  `c5_liberok`/`c5_nota`/`c5_blq` (liberação, nota gerada, bloqueio) com a
  comparação de quantidade vendida x entregue pra decidir entre
  "AGUARDANDO LIBERAÇÃO", "LIBERADO", "FATURADO TOTAL"/"PARCIAL",
  "CANCELADO", "DEVOLUÇÃO - ENCERRADO", "ELIMINADO RESÍDUO",
  "BLOQUEADO POR REGRA"/"POR VERBA".
- Conversão de moeda (`mult_vlr` = 1 se `C5_MOEDA='1'`, senão `C5_TXMOEDA`)
  aplicada em preço/valor/quantidade-entregue-valorizada, igual ao original.
- As somas `SUM(...) OVER(PARTITION BY ...)` (totais por pedido e por
  cliente+safra) são calculadas DEPOIS do filtro de `statusped`/`qtdaent`
  (mesma ordem de avaliação do SQL original: WHERE do bloco filtra as
  linhas antes das window functions do mesmo SELECT serem computadas) —
  ou seja, os totais somam só os itens ainda pendentes, não o pedido
  inteiro.
- Filtro final fixo, igual ao original: `statusped NOT IN ('CANCELADO',
  'DEVOLUÇÃO - ENCERRADO', 'ELIMINADO RESÍDUO', 'FATURADO TOTAL')` e
  `qtdaent <> 0` — ou seja, o relatório só traz o que ainda está pendente
  de entrega/faturamento.

Diferenças em relação à consulta literal enviada (generalização necessária
pra virar um relatório com filtro, não uma consulta com valor fixo):
- A consulta original veio com os filtros já resolvidos (`C5_EMISSAO
  BETWEEN ...`, `C5_DATA1 BETWEEN ...`, `C5_NATUREZ IN ('10010109')`) e uma
  sequência de `(1=1)` nos filtros que não estavam em uso naquela consulta
  específica (inclusive um que provavelmente seria filial/cliente). Viraram
  parâmetros: filial (seleção múltipla, igual aos outros relatórios),
  cliente (`A1_COD`, seleção múltipla), emissão (faixa de datas), entrega
  (faixa de datas sobre `C5_DATA1`) e natureza (texto com códigos separados
  por `;`, mesmo padrão já usado nos outros relatórios pra listas).
- `d_e_l_e_t_ = ' '` virou `COALESCE(d_e_l_e_t_, ' ') = ' '` em todos os
  JOINs/WHERE — mesmo ajuste já feito em todos os outros relatórios desse
  módulo, porque nesse banco de teste esse campo às vezes vem `NULL` em vez
  de espaço.

Atenção: só roda com DB_BACKEND=postgres (cast ::date). Datas em SC5010
nesse banco de teste são VARCHAR (formato "YYYYMMDD").

Particularidade do dado de teste: as tabelas SC5010/SC6010/SF4010 não
existiam no banco `testeIA` (só SA1010/SB1010, com todos os campos reais do
Protheus). Criei versões mínimas dessas 3 tabelas, só com as colunas usadas
nesta consulta, e populei com 3 pedidos de teste (dois pendentes de
faturamento — um parcial, um aguardando liberação — e um totalmente
faturado, pra validar que o filtro final de `statusped` exclui esse
último). Se um dia as tabelas completas forem importadas do Protheus real,
essas versões mínimas podem ser substituídas sem qualquer mudança no SQL
acima (os nomes de coluna são os mesmos).
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
-- RELATORIO: Contas a Receber com Descricao do Produto
-- (consulta enviada pronta pelo dev senior de ADVPL, generalizada em filtro)
-- =====================================================================
SELECT
    vw2.*,
    SUM(vw2.c6_qtdven) OVER (PARTITION BY vw2.a1_cod, vw2.a1_loja, vw2.c5_filial, vw2.c5_codsaf, vw2.c6_num) AS tpc6_qtdven,
    SUM(vw2.c6_prcven) OVER (PARTITION BY vw2.a1_cod, vw2.a1_loja, vw2.c5_filial, vw2.c5_codsaf, vw2.c6_num) AS tpc6_prcven,
    SUM(vw2.c6_valor) OVER (PARTITION BY vw2.a1_cod, vw2.a1_loja, vw2.c5_filial, vw2.c5_codsaf, vw2.c6_num) AS tpc6_valor,
    SUM(vw2.c6_qtdent) OVER (PARTITION BY vw2.a1_cod, vw2.a1_loja, vw2.c5_filial, vw2.c5_codsaf, vw2.c6_num) AS tpc6_qtdent,
    SUM(vw2.qtdaent) OVER (PARTITION BY vw2.a1_cod, vw2.a1_loja, vw2.c5_filial, vw2.c5_codsaf, vw2.c6_num) AS tpqtdaent,
    SUM(vw2.vlrent) OVER (PARTITION BY vw2.a1_cod, vw2.a1_loja, vw2.c5_filial, vw2.c5_codsaf, vw2.c6_num) AS tpvlrent,
    SUM(vw2.vlraent) OVER (PARTITION BY vw2.a1_cod, vw2.a1_loja, vw2.c5_filial, vw2.c5_codsaf, vw2.c6_num) AS tpvlraent,
    SUM(vw2.c6_qtdven) OVER (PARTITION BY vw2.a1_cod, vw2.a1_loja, vw2.c5_filial, vw2.c5_codsaf) AS tflc6_qtdven,
    SUM(vw2.c6_prcven) OVER (PARTITION BY vw2.a1_cod, vw2.a1_loja, vw2.c5_filial, vw2.c5_codsaf) AS tflc6_prcven,
    SUM(vw2.c6_valor) OVER (PARTITION BY vw2.a1_cod, vw2.a1_loja, vw2.c5_filial, vw2.c5_codsaf) AS tflc6_valor,
    SUM(vw2.c6_qtdent) OVER (PARTITION BY vw2.a1_cod, vw2.a1_loja, vw2.c5_filial, vw2.c5_codsaf) AS tflc6_qtdent,
    SUM(vw2.qtdaent) OVER (PARTITION BY vw2.a1_cod, vw2.a1_loja, vw2.c5_filial, vw2.c5_codsaf) AS tflqtdaent,
    SUM(vw2.vlrent) OVER (PARTITION BY vw2.a1_cod, vw2.a1_loja, vw2.c5_filial, vw2.c5_codsaf) AS tflvlrent,
    SUM(vw2.vlraent) OVER (PARTITION BY vw2.a1_cod, vw2.a1_loja, vw2.c5_filial, vw2.c5_codsaf) AS tflvlraent
FROM (
    SELECT
        vw.*
    FROM (
        SELECT
            base.*,
            CASE
                WHEN base.c5_liberok = ' ' AND base.c5_nota = ' ' AND base.c5_blq = ' ' THEN (
                    CASE
                        WHEN base.c6sqtdent = 0 THEN 'AGUARDANDO LIBERACAO'
                        WHEN base.c6sqtdent > 0 AND base.c6sqtdent = base.c6sqtdven THEN 'FATURADO TOTAL'
                        WHEN base.c6sqtdent > 0 AND base.c6sqtdent < base.c6sqtdven THEN 'FATURADO PARCIAL'
                        ELSE '*'
                    END
                )
                WHEN base.c5_nota <> ' ' OR (base.c5_liberok = 'E' AND base.c5_blq = ' ') THEN (
                    CASE
                        WHEN base.c6sqtdven = 0 AND base.c6sqtdent = 0 AND base.c5_tipo = 'D' THEN 'DEVOLUCAO - ENCERRADO'
                        WHEN base.c6sqtdven > 0 AND base.c6sqtdent > 0 AND base.c6sqtdent < base.c6sqtdven THEN 'ELIMINADO RESIDUO'
                        WHEN base.c6sqtdven > 0 AND base.c6sqtdent = 0 THEN 'CANCELADO'
                        WHEN base.c6sqtdent > 0 AND base.c6sqtdent = base.c6sqtdven THEN 'FATURADO TOTAL'
                        WHEN base.c6sqtdent > 0 AND base.c6sqtdent < base.c6sqtdven THEN 'FATURADO PARCIAL'
                        ELSE '**'
                    END
                )
                WHEN base.c5_liberok <> ' ' AND base.c5_nota = ' ' AND base.c5_blq = ' ' THEN (
                    CASE
                        WHEN base.c6sqtdent = 0 THEN 'LIBERADO'
                        WHEN base.c6sqtdent > 0 AND base.c6sqtdent = base.c6sqtdven THEN 'FATURADO TOTAL'
                        WHEN base.c6sqtdent > 0 AND base.c6sqtdent < base.c6sqtdven THEN 'FATURADO PARCIAL'
                        ELSE '*'
                    END
                )
                WHEN base.c5_blq = '1' THEN 'BLOQUEADO POR REGRA'
                WHEN base.c5_blq = '2' THEN 'BLOQUEADO POR VERBA'
                ELSE ' '
            END AS statusped
        FROM (
            SELECT
                sc5.c5_filial,
                sa1.a1_cod, sa1.a1_loja, sa1.a1_nome, sa1.a1_nreduz,
                sa1.a1_tel, sa1.a1_cgc, sa1.a1_inscr, sa1.a1_mun, sa1.a1_est, sa1.a1_email,
                sc5.c5_codsaf, sc5.c5_emissao, sc5.c5_data1, sc5.c5_naturez,
                sc5.c5_nota, sc5.c5_liberok, sc5.c5_blq, sc5.c5_tipo,
                sc5.c5_cliente, sc5.c5_lojacli,
                sc6.c6_cf, sc6.c6_num, sc6.c6_item, sc6.c6_produto,
                sb1.b1_cod, sb1.b1_desc,
                (
                    SELECT SUM(sc6b.c6_qtdven) FROM sc6010 sc6b
                    WHERE COALESCE(sc6b.d_e_l_e_t_, ' ') = ' '
                      AND sc6b.c6_filial = sc5.c5_filial AND sc6b.c6_num = sc5.c5_num
                ) AS c6sqtdven,
                (
                    SELECT SUM(sc6b.c6_qtdent) FROM sc6010 sc6b
                    WHERE COALESCE(sc6b.d_e_l_e_t_, ' ') = ' '
                      AND sc6b.c6_filial = sc5.c5_filial AND sc6b.c6_num = sc5.c5_num
                ) AS c6sqtdent,
                sc6.c6_qtdven,
                (sc6.c6_prcven * (CASE WHEN sc5.c5_moeda = '1' THEN 1 ELSE sc5.c5_txmoeda END)) AS c6_prcven,
                (sc6.c6_valor * (CASE WHEN sc5.c5_moeda = '1' THEN 1 ELSE sc5.c5_txmoeda END)) AS c6_valor,
                sc6.c6_qtdent,
                (sc6.c6_qtdven - sc6.c6_qtdent) AS qtdaent,
                (sc6.c6_qtdent * sc6.c6_prcven) * (CASE WHEN sc5.c5_moeda = '1' THEN 1 ELSE sc5.c5_txmoeda END) AS vlrent,
                ((sc6.c6_qtdven - sc6.c6_qtdent) * sc6.c6_prcven) * (CASE WHEN sc5.c5_moeda = '1' THEN 1 ELSE sc5.c5_txmoeda END) AS vlraent,
                sc5.c5_moeda,
                (CASE WHEN sc5.c5_moeda = '1' THEN 1 ELSE sc5.c5_txmoeda END) AS mult_vlr
            FROM sc5010 sc5
            JOIN sa1010 sa1
                ON COALESCE(sa1.d_e_l_e_t_, ' ') = ' ' AND sc5.c5_cliente = sa1.a1_cod AND sc5.c5_lojacli = sa1.a1_loja
            JOIN sc6010 sc6
                ON COALESCE(sc6.d_e_l_e_t_, ' ') = ' ' AND sc6.c6_filial = sc5.c5_filial AND sc6.c6_num = sc5.c5_num
            JOIN sb1010 sb1
                ON COALESCE(sb1.d_e_l_e_t_, ' ') = ' ' AND sb1.b1_cod = sc6.c6_produto
            JOIN sf4010 sf4
                ON COALESCE(sf4.d_e_l_e_t_, ' ') = ' '
               AND SUBSTR(sc6.c6_filial, 1, 2) = SUBSTR(sf4.f4_filial, 1, 2) AND sc6.c6_tes = sf4.f4_codigo
            WHERE COALESCE(sc5.d_e_l_e_t_, ' ') = ' '
              AND COALESCE(sc6.d_e_l_e_t_, ' ') = ' '
              AND sc5.c5_tipo = 'N'
              AND TRIM(sc5.c5_filial) IN __FILIAL_IN__
              AND (:cliente_lista = '' OR sc5.c5_cliente IN __CLIENTE_IN__)
              AND (
                    :emissao_ini = '' OR :emissao_fim = ''
                 OR sc5.c5_emissao::date BETWEEN NULLIF(:emissao_ini, '')::date AND NULLIF(:emissao_fim, '')::date
              )
              AND (
                    :entrega_ini = '' OR :entrega_fim = ''
                 OR sc5.c5_data1::date BETWEEN NULLIF(:entrega_ini, '')::date AND NULLIF(:entrega_fim, '')::date
              )
              AND (:naturezas = '' OR TRIM(sc5.c5_naturez) = ANY (string_to_array(:naturezas, ';')))
        ) base
    ) vw
    WHERE vw.statusped NOT IN ('CANCELADO', 'DEVOLUCAO - ENCERRADO', 'ELIMINADO RESIDUO', 'FATURADO TOTAL')
      AND vw.qtdaent <> 0
) vw2
ORDER BY vw2.c5_filial, vw2.a1_cod, vw2.a1_loja, vw2.c6_num, vw2.c6_item
"""

_CAMPOS_OPCIONAIS = ("emissao_ini", "emissao_fim", "entrega_ini", "entrega_fim", "naturezas")


def _serializar(valor):
    if isinstance(valor, Decimal):
        return float(valor)
    return valor


def _buscar_pedidos(filiais: list[str], clientes: list[str], opcionais: dict[str, str]) -> tuple[list[str], list[tuple]]:
    clausula_filial, binds_filial = clausula_in("filial", filiais)
    clausula_cliente, binds_cliente = clausula_in("cliente", clientes) if clientes else ("('')", {})

    opcionais["cliente_lista"] = ",".join(clientes)

    sql = _QUERY.replace("__FILIAL_IN__", clausula_filial).replace("__CLIENTE_IN__", clausula_cliente)

    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, **opcionais, **binds_filial, **binds_cliente)
        colunas = [descricao[0] for descricao in cursor.description]
        linhas = cursor.fetchall()
    return colunas, linhas


def _parametros_da_query(request: Request) -> tuple[list[str], list[str], dict[str, str]] | None:
    filial_bruto = request.query_params.get("filial", "").strip()
    filiais = [item.strip() for item in filial_bruto.split(",") if item.strip()]
    if not filiais:
        return None

    cliente_bruto = request.query_params.get("cliente", "").strip()
    clientes = [item.strip() for item in cliente_bruto.split(",") if item.strip()]

    opcionais = {chave: request.query_params.get(chave, "").strip() for chave in _CAMPOS_OPCIONAIS}
    return filiais, clientes, opcionais


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/contas-receber-produto", methods=["GET", "OPTIONS"])
    async def listar_contas_receber_produto_route(request: Request) -> JSONResponse:
        """RELATÓRIO: Contas a Receber com Descrição do Produto — endpoint JSON usado pela tela."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse({"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS)

        colunas, linhas = _buscar_pedidos(*parametros)
        dados = [dict(zip(colunas, (_serializar(valor) for valor in linha))) for linha in linhas]
        return JSONResponse(dados, headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/contas-receber-produto/exportar", methods=["GET", "OPTIONS"])
    async def exportar_contas_receber_produto_route(request: Request) -> Response:
        """RELATÓRIO: Contas a Receber com Descrição do Produto — exportação em Excel."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse({"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS)

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
