"""RELATÓRIO: Contas a Receber com Descrição do Produto

Tradução direta de uma consulta SQL já pronta, enviada pelo desenvolvedor
sênior de ADVPL da empresa (não um `.prx`/`.prw` de tela como os outros
relatórios) — junta cada título a receber (SE1010) com os itens da nota
fiscal de saída que o originou (SD2010 + SB1010 pra descrição do produto),
distribuindo o saldo em aberto do título proporcionalmente entre os produtos
da nota.

Fidelidade ao SQL enviado:
- Inversão de sinal pra títulos do tipo NCC/RA (nota de crédito/devolução):
  valor, saldo, acréscimo e decréscimo saem negativos — mesma lógica do
  `CASE WHEN E1_TIPO IN ('NCC','RA') THEN -1 ELSE 1 END` original.
- `valor_pago` = valor - saldo (com o mesmo sinal invertido acima).
- `totapagar1` e `totapagar`: duas colunas com a mesma fórmula (saldo +
  acréscimo - decréscimo) — mantidas as duas, como vieram na consulta
  original (parecem redundantes, mas replicamos por fidelidade).
- Split proporcional por item da nota: cada item recebe uma fatia do saldo
  em aberto do título proporcional ao peso dele na nota (`d2_total/e1_valor`),
  daí `qtd_a_rec`, `qtd_receb`, `vlr_a_pagar`, `vlr_pago`.
- `soma_d2_quant`: soma da quantidade de todos os itens da mesma nota
  (window function particionada por filial+documento+cliente+loja) — vem na
  consulta original mas não é usada em nenhum outro cálculo; mantida como
  coluna informativa mesmo assim, por fidelidade.
- O JOIN com SF2010 (cabeçalho da nota) está na consulta original mas
  nenhuma coluna dele é usada — mantido só pra não alterar o conjunto de
  linhas retornado (é 1:1 com o item da SD2010, não deveria multiplicar
  linha nenhuma).

Diferenças em relação à consulta literal enviada (generalização necessária
pra virar um relatório com filtro, não uma consulta com valor fixo):
- A consulta original veio com os filtros já resolvidos em valores literais
  (`E1_FILIAL IN ('0101')`, `A1_COD IN ('150391378')`, datas fixas, e uma
  sequência de `( 1=1 )` nos filtros que não estavam em uso naquela consulta
  específica). Só os filtros que apareciam ativos foram parametrizados aqui:
  filial (seleção múltipla, igual aos outros relatórios), cliente, emissão
  (faixa de datas), vencimento (faixa de datas) e tipo a não considerar
  (na consulta original vinha fixo em `NOT IN ('RA','NCC')`; aqui virou
  filtro configurável — texto com códigos separados por `;`, mesmo padrão já
  usado no relatório de Títulos a Receber por Vendedor). `E1_SALDO <> 0`
  ficou fixo (sempre só título em aberto), igual na consulta original.
  Os `(1=1)` restantes não foram identificados (não sabemos a que campo
  cada um correspondia na tela original) — se depois for preciso adicionar
  algum filtro extra (natureza, prefixo etc.), é só entrar em contato.
- "Cliente" virou um único campo de seleção (não faixa De/Até como nos
  outros relatórios) porque a consulta original usa `IN (...)`, não
  `BETWEEN` — a rota aceita mais de um código separado por vírgula
  (`?cliente=COD1,COD2`), mas a tela por enquanto só permite escolher um.
- Divisões protegidas com `NULLIF(..., 0)`: a consulta original divide por
  `e1_valor` e por `d2_prcven` sem proteção — no Postgres (diferente de
  outros bancos), dividir por zero é erro, não NULL. Título/item com valor
  zero agora vira NULL nessas colunas em vez de derrubar a consulta inteira.
- `d_e_l_e_t_ = ' '` virou `COALESCE(d_e_l_e_t_, ' ') = ' '` em todos os
  JOINs/WHERE — mesmo ajuste já feito em todos os outros relatórios desse
  módulo, porque nesse banco de teste esse campo às vezes vem `NULL` em vez
  de espaço (ex: SB1010 tem produto com `d_e_l_e_t_` nulo — sem o COALESCE,
  a comparação com `' '` dá falso e o produto nunca casa no JOIN).
- `E1_ACRESC`/`E1_DECRESC` protegidos com `COALESCE(..., 0)`: em Protheus
  real esses campos numéricos nunca vêm nulos (SX3 garante default 0), mas
  nesse banco de teste alguns títulos têm `NULL` — sem a proteção, qualquer
  conta em cima deles (`totapagar`/`totapagar1`) vira `NULL` também.

Atenção: só roda com DB_BACKEND=postgres (cast ::date). Datas em SE1010
nesse banco de teste são VARCHAR (formato "YYYYMMDD").

Particularidade do dado de teste: SD2010 já existia no banco (20 linhas),
mas nenhuma delas tinha as chaves (filial+prefixo/série+número/doc+cliente+
loja) batendo com nenhum título de SE1010 — sem isso o JOIN nunca traz
produto nenhum. Criei algumas linhas de SD2010 ligadas a títulos reais de
SE1010 só pra dar algo pra validar (veja o script que rodei na conversa).
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
    vw.*,
    (vw.e1_valor - vw.valor_pago + vw.e1_acresc - vw.e1_decresc) AS totapagar1,
    (vw.e1_acresc - vw.e1_decresc + vw.e1_saldo) AS totapagar,
    (vw.d2_quant - ROUND((vw.d2_total * vw.e1_saldo / NULLIF(vw.e1_valor, 0)) / NULLIF(vw.d2_prcven, 0), 0)) AS qtd_receb,
    ROUND((vw.d2_total * vw.e1_saldo / NULLIF(vw.e1_valor, 0)) / NULLIF(vw.d2_prcven, 0), 0) AS qtd_a_rec,
    ROUND((vw.d2_total * vw.e1_saldo / NULLIF(vw.e1_valor, 0)), 2) AS vlr_a_pagar,
    ROUND((vw.d2_total - (vw.d2_total * vw.e1_saldo / NULLIF(vw.e1_valor, 0))), 2) AS vlr_pago
FROM (
    SELECT
        se1.e1_filial,
        sa1.a1_cod, sa1.a1_loja, sa1.a1_nome, sa1.a1_nreduz,
        sa1.a1_tel, sa1.a1_cgc, sa1.a1_inscr, sa1.a1_mun, sa1.a1_est, sa1.a1_email,
        se1.e1_xsafra, se1.e1_naturez, se1.e1_tipo, se1.e1_prefixo, se1.e1_num, se1.e1_parcela,
        se1.e1_emissao, se1.e1_vencto, se1.e1_vencrea,
        se1.e1_valor * (CASE WHEN se1.e1_tipo IN ('NCC', 'RA') THEN -1 ELSE 1 END) AS e1_valor,
        (se1.e1_valor - se1.e1_saldo) * (CASE WHEN se1.e1_tipo IN ('NCC', 'RA') THEN -1 ELSE 1 END) AS valor_pago,
        COALESCE(se1.e1_acresc, 0) * (CASE WHEN se1.e1_tipo IN ('NCC', 'RA') THEN -1 ELSE 1 END) AS e1_acresc,
        COALESCE(se1.e1_decresc, 0) * (CASE WHEN se1.e1_tipo IN ('NCC', 'RA') THEN -1 ELSE 1 END) AS e1_decresc,
        se1.e1_saldo * (CASE WHEN se1.e1_tipo IN ('NCC', 'RA') THEN -1 ELSE 1 END) AS e1_saldo,
        se1.e1_hist,
        sd2.d2_doc, sd2.d2_serie, sd2.d2_item, sd2.d2_cf, sd2.d2_cod,
        sb1.b1_desc, sd2.d2_prcven, sd2.d2_quant,
        SUM(sd2.d2_quant) OVER (PARTITION BY se1.e1_filial, sd2.d2_doc, sd2.d2_serie, sd2.d2_cliente, sd2.d2_loja) AS soma_d2_quant,
        sd2.d2_total
    FROM se1010 se1
    LEFT JOIN sa1010 sa1
        ON COALESCE(sa1.d_e_l_e_t_, ' ') = ' ' AND sa1.a1_cod = se1.e1_cliente AND sa1.a1_loja = se1.e1_loja
    LEFT JOIN sd2010 sd2
        ON COALESCE(sd2.d_e_l_e_t_, ' ') = ' '
       AND se1.e1_filial = sd2.d2_filial AND se1.e1_prefixo = sd2.d2_serie AND se1.e1_num = sd2.d2_doc
       AND se1.e1_cliente = sd2.d2_cliente AND se1.e1_loja = sd2.d2_loja
    LEFT JOIN sf2010 sf2
        ON COALESCE(sf2.d_e_l_e_t_, ' ') = ' '
       AND sf2.f2_filial = sd2.d2_filial AND sf2.f2_doc = sd2.d2_doc AND sf2.f2_serie = sd2.d2_serie
       AND sf2.f2_cliente = sd2.d2_cliente AND sf2.f2_loja = sd2.d2_loja
    LEFT JOIN sb1010 sb1
        ON COALESCE(sb1.d_e_l_e_t_, ' ') = ' ' AND sb1.b1_cod = sd2.d2_cod
    WHERE COALESCE(se1.d_e_l_e_t_, ' ') = ' '
      AND TRIM(se1.e1_filial) IN __FILIAL_IN__
      AND (:cliente_lista = '' OR se1.e1_cliente IN __CLIENTE_IN__)
      AND (
            :emissao_ini = '' OR :emissao_fim = ''
         OR se1.e1_emissao::date BETWEEN NULLIF(:emissao_ini, '')::date AND NULLIF(:emissao_fim, '')::date
      )
      AND (
            :vencimento_ini = '' OR :vencimento_fim = ''
         OR se1.e1_vencto::date BETWEEN NULLIF(:vencimento_ini, '')::date AND NULLIF(:vencimento_fim, '')::date
      )
      AND se1.e1_saldo <> 0
      AND (:tipos_excluir = '' OR NOT (TRIM(se1.e1_tipo) = ANY (string_to_array(:tipos_excluir, ';'))))
) vw
ORDER BY vw.e1_filial, vw.a1_cod, vw.a1_loja, vw.d2_doc, vw.d2_serie, vw.d2_item
"""

_CAMPOS_OPCIONAIS = ("emissao_ini", "emissao_fim", "vencimento_ini", "vencimento_fim", "tipos_excluir")


def _serializar(valor):
    if isinstance(valor, Decimal):
        return float(valor)
    return valor


def _buscar_titulos(filiais: list[str], clientes: list[str], opcionais: dict[str, str]) -> tuple[list[str], list[tuple]]:
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

        colunas, linhas = _buscar_titulos(*parametros)
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

        colunas, linhas = _buscar_titulos(*parametros)
        conteudo_xlsx = gerar_xlsx(colunas, linhas, titulo="Contas a Receber com Descrição do Produto")
        return Response(
            content=conteudo_xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="contas_receber_produto.xlsx"',
                **CORS_HEADERS,
            },
        )
