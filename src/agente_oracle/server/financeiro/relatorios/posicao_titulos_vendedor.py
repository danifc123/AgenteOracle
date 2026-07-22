"""RELATÓRIO: Posição dos Títulos a Receber por Vendedor (FINR137)

Tradução do ADVPL (`FINR137.PRX`) — parente do FINR130/"Posição dos Títulos"
(`posicao_titulos.py`), mas organizado por vendedor em vez de por cliente: um
mesmo título aparece uma vez para CADA vendedor preenchido nele (E1_VEND1 até
E1_VEND5) — o saldo mostrado é sempre o saldo CHEIO do título, não dividido
entre os vendedores (`R137TR4` no original grava o saldo cheio pra cada
vendedor; isso é um relatório de "posição", não de rateio de comissão).

O que TEM fidelidade real com o ADVPL original:
- Explosão por vendedor: união das 5 colunas de vendedor, virando uma linha
  própria por vendedor preenchido, com o saldo cheio do título.
- Saldo do título: atual (E1_SALDO+E1_SDACRES-E1_SDDECRE) OU **retroativo**,
  reconstruído somando as baixas reais em SE5010 até a data-base — mesmo
  padrão de `posicao_titulos.py` (MV_PAR15/SaldoTit() do original).
- Filtros em faixa: cliente, loja, emissão, vencimento, vendedor — mais
  filial (seleção múltipla).
- Tipos a considerar / a não considerar (MV_PAR11/MV_PAR12 do ADVPL) — campos
  de texto com códigos separados por `;`, igual ao original (esse relatório
  nunca teve um seletor múltiplo pra isso, sempre foi texto puro).
- Títulos de tipo abatimento (`AB|FA`, mesma lista-padrão já usada nos outros
  relatórios) são sempre excluídos, sem opção pra desligar — o ADVPL original
  (`If ! E1_TIPO $ MVABATIM`) também não tem toggle pra isso, é incondicional.
- Dias de atraso, natureza (nome via SED010), "título liquidado" (E1_NUMLIQ
  cru).
- Juros/multa expostos como os campos brutos já armazenados em SE1010
  (E1_PORCJUR/E1_VALJUR/E1_MULTA) — mesma solução do FINR130 e pelo mesmo
  motivo: o juro acumulado real é calculado por uma função externa
  (`Fa070Juros()`) que não está disponível aqui.
- Gate de Valor Acessório (`tem_valor_acessorio` via EXISTS em FK7), igual
  aos outros dois relatórios — o VALOR do VA (`FValAcess()`) é externo e
  desconhecido, fica sempre 0.

Uma diferença deliberada em relação ao ADVPL original: o nome do cliente vem
de um JOIN em SA1010 (`sa1.a1_nome`), não do campo cru `E1_NOMCLI` que o
TRCell original usa — E1_NOMCLI é um campo "cache" desnormalizado que está
sempre vazio nesse banco de teste (e não é incomum estar desatualizado em
Protheus real também); SA1010 é a fonte de verdade, mesma solução já usada
em `posicao_titulos.py`.

O que ficou de fora (documentado, não escondido):
- **Cadeia de liquidação** (`TitPrinc`/`Vendedor137` do original, via
  FK1/FK7): quando um título já foi liquidado (E1_NUMLIQ preenchido) e o
  vendedor "correto" está no título ORIGINAL (que não está mais em aberto),
  o ADVPL busca essa cadeia recursivamente com duas queries customizadas
  (UNION de "título liquidado direto" + "reliquidado em cascata"). O banco
  de teste não tem nenhum título com E1_NUMLIQ preenchido — sem dado real
  pra validar essa tradução, preferimos deixar essa parte de fora a inventar
  uma tradução que pareceria fiel mas poderia estar errada. Na prática: se
  um título passou por liquidação, o vendedor dele pode não aparecer aqui.
- Dedução de "abatimento" contra o saldo do título antes de decidir se ele
  aparece (`SomaAbat()`, função externa) — mesmo motivo.
- "Saldo Corrente" (saldo + juros + valor acessório) não virou coluna
  calculada: como juros e VA não são calculados de verdade aqui, somar daria
  uma impressão de precisão que não existe.
- Multi-moeda, Gestão Corporativa, "salta página por vendedor" (é só
  formatação de impressão) — mesma exclusão já justificada nos outros
  relatórios (Grupo Conceito opera com empresa/filial única).

Atenção: só roda com DB_BACKEND=postgres (cast ::date). Datas em SE1010/
SE5010 nesse banco de teste são VARCHAR (formato "YYYYMMDD").
"""

from datetime import date
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
-- RELATORIO: Posicao dos Titulos a Receber por Vendedor (FINR137)
-- (sem cadeia de liquidacao/Gestao Corporativa/multi-moeda)
-- =====================================================================
WITH titulos_base AS (
    SELECT
        se1.e1_filial, se1.e1_prefixo, se1.e1_num, se1.e1_parcela, se1.e1_tipo,
        se1.e1_cliente AS cliente_codigo, se1.e1_loja AS cliente_loja,
        se1.e1_naturez, se1.e1_emissao, se1.e1_vencto,
        se1.e1_valor, se1.e1_saldo, se1.e1_sdacres, se1.e1_sddecre,
        se1.e1_porcjur, se1.e1_valjur, se1.e1_multa, se1.e1_numliq,
        se1.e1_vend1, se1.e1_vend2, se1.e1_vend3, se1.e1_vend4, se1.e1_vend5
    FROM se1010 se1
    WHERE COALESCE(se1.d_e_l_e_t_, ' ') = ' '
      AND TRIM(se1.e1_filial) IN __FILIAL_IN__
      AND (:cliente_ini = '' OR se1.e1_cliente >= :cliente_ini)
      AND (:cliente_fim = '' OR se1.e1_cliente <= :cliente_fim)
      AND (:loja_ini = '' OR se1.e1_loja >= :loja_ini)
      AND (:loja_fim = '' OR se1.e1_loja <= :loja_fim)
      AND (
            :emissao_ini = '' OR :emissao_fim = ''
         OR se1.e1_emissao::date BETWEEN NULLIF(:emissao_ini, '')::date AND NULLIF(:emissao_fim, '')::date
      )
      AND (
            :vencimento_ini = '' OR :vencimento_fim = ''
         OR se1.e1_vencto::date BETWEEN NULLIF(:vencimento_ini, '')::date AND NULLIF(:vencimento_fim, '')::date
      )
      AND NOT (TRIM(se1.e1_tipo) = ANY (string_to_array(:tipos_abatimento, '|')))
      AND (:tipos_incluir = '' OR TRIM(se1.e1_tipo) = ANY (string_to_array(:tipos_incluir, ';')))
      AND (:tipos_excluir = '' OR NOT (TRIM(se1.e1_tipo) = ANY (string_to_array(:tipos_excluir, ';'))))
),
titulos_vendedor AS (
    SELECT tb.*, tb.e1_vend1 AS vendedor_codigo FROM titulos_base tb WHERE TRIM(COALESCE(tb.e1_vend1, '')) <> ''
    UNION ALL
    SELECT tb.*, tb.e1_vend2 FROM titulos_base tb WHERE TRIM(COALESCE(tb.e1_vend2, '')) <> ''
    UNION ALL
    SELECT tb.*, tb.e1_vend3 FROM titulos_base tb WHERE TRIM(COALESCE(tb.e1_vend3, '')) <> ''
    UNION ALL
    SELECT tb.*, tb.e1_vend4 FROM titulos_base tb WHERE TRIM(COALESCE(tb.e1_vend4, '')) <> ''
    UNION ALL
    SELECT tb.*, tb.e1_vend5 FROM titulos_base tb WHERE TRIM(COALESCE(tb.e1_vend5, '')) <> ''
)
SELECT
    tv.vendedor_codigo,
    sa3.a3_nome AS nome_vendedor,
    tv.e1_filial,
    tv.e1_prefixo,
    tv.e1_num,
    tv.e1_parcela,
    tv.e1_tipo,
    tv.cliente_codigo,
    tv.cliente_loja,
    sa1.a1_nome AS nome_cliente,
    tv.e1_emissao,
    tv.e1_vencto,
    tv.e1_valor,
    (
        CASE WHEN :saldo_retroativo = '1' THEN
            GREATEST(0, tv.e1_valor - COALESCE((
                SELECT SUM(se5.e5_valor)
                FROM se5010 se5
                WHERE se5.e5_filial = tv.e1_filial AND se5.e5_prefixo = tv.e1_prefixo
                  AND se5.e5_numero = tv.e1_num AND se5.e5_parcela = tv.e1_parcela
                  AND se5.e5_tipo = tv.e1_tipo AND se5.e5_clifor = tv.cliente_codigo
                  AND se5.e5_loja = tv.cliente_loja
                  AND COALESCE(se5.d_e_l_e_t_, ' ') = ' '
                  AND se5.e5_data::date <= :data_base::date
            ), 0))
        ELSE tv.e1_saldo + COALESCE(tv.e1_sdacres, 0) - COALESCE(tv.e1_sddecre, 0)
        END
    ) AS saldo,
    tv.e1_naturez,
    sed.ed_descric AS nome_natureza,
    tv.e1_porcjur,
    tv.e1_valjur,
    tv.e1_multa,
    tv.e1_numliq AS titulo_liquidado,
    GREATEST(0, :data_base::date - tv.e1_vencto::date) AS dias_atraso,
    EXISTS (
        SELECT 1 FROM fk7
        WHERE fk7.fk7_filial = tv.e1_filial
          AND COALESCE(fk7.d_e_l_e_t_, ' ') = ' '
          AND fk7.fk7_chave = 'SE1' || TRIM(tv.e1_filial) || '|' || TRIM(tv.e1_prefixo) || '|' || TRIM(tv.e1_num) || '|' || TRIM(tv.e1_parcela) || '|' || TRIM(tv.e1_tipo) || '|' || TRIM(tv.cliente_codigo) || '|' || TRIM(tv.cliente_loja)
    ) AS tem_valor_acessorio,
    0 AS valor_acessorio
FROM titulos_vendedor tv
LEFT JOIN sa3 ON sa3.a3_cod = tv.vendedor_codigo
LEFT JOIN sa1010 sa1 ON sa1.a1_cod = tv.cliente_codigo AND sa1.a1_loja = tv.cliente_loja
LEFT JOIN sed010 sed ON sed.ed_codigo = tv.e1_naturez
WHERE (:vendedor_ini = '' OR tv.vendedor_codigo >= :vendedor_ini)
  AND (:vendedor_fim = '' OR tv.vendedor_codigo <= :vendedor_fim)
ORDER BY tv.vendedor_codigo, tv.e1_prefixo, tv.e1_num, tv.e1_parcela, tv.e1_tipo
"""

_CAMPOS_OPCIONAIS = (
    "cliente_ini", "cliente_fim", "loja_ini", "loja_fim",
    "emissao_ini", "emissao_fim", "vencimento_ini", "vencimento_fim",
    "vendedor_ini", "vendedor_fim",
    "tipos_incluir", "tipos_excluir",
    "saldo_retroativo",
)

_TIPOS_ABATIMENTO_PADRAO = "AB|FA"


def _serializar(valor):
    if isinstance(valor, Decimal):
        return float(valor)
    return valor


def _buscar_titulos(filiais: list[str], opcionais: dict[str, str]) -> tuple[list[str], list[tuple]]:
    clausula_filial, binds_filial = clausula_in("filial", filiais)

    opcionais["tipos_abatimento"] = _TIPOS_ABATIMENTO_PADRAO
    opcionais.setdefault("data_base", date.today().strftime("%Y%m%d"))

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
    @mcp.custom_route("/api/financeiro/posicao-titulos-vendedor", methods=["GET", "OPTIONS"])
    async def listar_posicao_titulos_vendedor_route(request: Request) -> JSONResponse:
        """RELATÓRIO: Posição dos Títulos a Receber por Vendedor (FINR137) — endpoint JSON usado pela tela."""
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

    @mcp.custom_route("/api/financeiro/posicao-titulos-vendedor/exportar", methods=["GET", "OPTIONS"])
    async def exportar_posicao_titulos_vendedor_route(request: Request) -> Response:
        """RELATÓRIO: Posição dos Títulos a Receber por Vendedor (FINR137) — exportação em Excel."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse({"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS)

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
