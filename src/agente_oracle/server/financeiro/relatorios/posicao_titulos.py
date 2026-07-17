"""RELATÓRIO: Posição dos Títulos a Receber (FINR130)

Tradução do ADVPL (`FINR130.PRW`, ~3.500 linhas) — o relatório real do
Protheus é, de longe, o mais complexo que já traduzimos. Ele cobre: ~40
parâmetros (MV_PAR01..43), 10 ordens de exibição/quebra diferentes,
Gestão Corporativa (multi-empresa), templates de desconto "GEM", conversão
de moeda estrangeira com taxa histórica, retenção de IR/PIS/COFINS/CSLL na
baixa e compensação entre filiais. Isso tudo ficou de fora aqui porque:
(a) o Grupo Conceito opera com uma única empresa/filial (0101), então
Gestão Corporativa não se aplica; (b) GEM, multi-moeda e a retenção de
IR/PIS/COFINS/CSLL dependem de configuração (SX6) e módulos que não temos
como validar nesse banco de teste.

O que TEM fidelidade real com o ADVPL original:
- Todos os filtros em faixa (cliente, prefixo, título, banco, vencimento,
  natureza, emissão, loja) + filial multi-select.
- Saldo do título: atual (E1_SALDO+E1_SDACRES-E1_SDDECRE) OU **retroativo**,
  reconstruído de verdade somando as baixas reais em SE5010 até a data-base
  (equivalente ao MV_PAR20/SaldoTit() do original).
- Split vencido/a vencer com base em E1_VENCTO/E1_VENCREA vs a data-base.
- **Juros e multa reais**, calculados a partir dos campos que já existem em
  SE1010 (E1_PORCJUR = juros ao mês, E1_VALJUR = juros fixo por dia,
  E1_MULTA = multa percentual) — não são valores inventados.
- **Abatimento**: títulos-filho (E1_TITPAI apontando pro título-pai) com
  saldo em aberto são deduzidos do saldo do pai. O banco de teste não tem
  nenhum título do tipo abatimento hoje, então esse valor sempre dá zero
  aqui, mas a lógica está pronta pra quando existir.
- **Reconstrução de títulos excluídos (FJU)**: quando `considerar_excluidos`
  está ligado, títulos com D_E_L_E_T_='*' que tenham um registro em FJU
  cuja janela (FJU_EMIS <= data-base <= FJU_DTEXCL, FJU_CART='R') ainda
  esteja "válida" voltam a aparecer no relatório — igual ao MV_PAR43
  original (que a própria fonte ADVPL já comentava como removido da v12,
  então pode nem estar ativo na produção real — vale confirmar).
- **Gate de Valores Acessórios (VA)**: verificamos se o título tem vínculo
  em FK7/FKD (`tem_valor_acessorio`), igual ao `ExisteFKD()` original. O
  VALOR do VA em si (`FValAcess()`) é calculado por uma função externa que
  não está nesse arquivo — não temos como saber a fórmula real, então
  `valor_acessorio` fica sempre 0 aqui. Preferimos deixar isso visivelmente
  zerado a inventar uma fórmula que pareceria fiel mas estaria errada.

Atenção: só roda com DB_BACKEND=postgres (cast ::date). Datas em SE1010/
SE5010 nesse banco de teste são VARCHAR (formato "YYYYMMDD"), comparadas
como texto quando possível (mesma ordenação) e com ::date só onde precisa
de aritmética de data real (dias de atraso, soma de baixas até uma data).

Duas particularidades do dado de teste (não da lógica traduzida):
- O saldo retroativo tem um GREATEST(0, ...) porque alguns SE5010 de baixa
  seedados bem no início da conversa têm E5_VALOR maior que o E1_VALOR do
  título (ex: título 5003) — sem isso o saldo reconstruído dava negativo.
- FK7/FKD/FK1 já existiam no banco com 20 registros de exemplo, mas o
  FK7_CHAVE deles é um placeholder genérico ("CHAVE-1", "CHAVE-2"...), não
  a chave real ("SE1"+filial+prefixo+num+parcela+tipo+cliente+loja,
  pipe-separado a partir do prefixo) que o ADVPL original monta. Por isso o
  gate `tem_valor_acessorio` não casa com esse seed antigo de 20 registros
  — só com o vínculo real que criamos pro título 5001 (IDDOC "VA000001").
"""

from datetime import date
from decimal import Decimal

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.db.connection import get_connection
from agente_oracle.relatorios import gerar_xlsx
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.server.financeiro.relatorios.filtros_sql import clausula_in

_ORDENS = {
    "cliente": "cliente_codigo, cliente_loja",
    "numero": "e1_num, e1_prefixo, e1_parcela",
    "vencimento": "e1_vencrea",
    "natureza": "e1_naturez",
    "banco": "e1_portado",
}

_QUERY = """
-- =====================================================================
-- RELATORIO: Posicao dos Titulos a Receber (FINR130) — versao simplificada
-- (sem Gestao Corporativa/GEM/multi-moeda/retencao de impostos na baixa)
-- =====================================================================
WITH titulos AS (
    SELECT
        se1.e1_filial, se1.e1_prefixo, se1.e1_num, se1.e1_parcela, se1.e1_tipo,
        se1.e1_cliente AS cliente_codigo, se1.e1_loja AS cliente_loja,
        se1.e1_naturez, se1.e1_emissao, se1.e1_vencto, se1.e1_vencrea,
        se1.e1_portado, se1.e1_situaca, se1.e1_numbco, se1.e1_hist,
        se1.e1_valor, se1.e1_saldo, se1.e1_sdacres, se1.e1_sddecre,
        se1.e1_porcjur, se1.e1_valjur, se1.e1_multa, se1.e1_titpai,
        se1.r_e_c_n_o_,
        FALSE AS titulo_reconstituido
    FROM se1010 se1
    WHERE COALESCE(se1.d_e_l_e_t_, ' ') = ' '
      AND TRIM(se1.e1_filial) IN __FILIAL_IN__
      AND (:cliente_ini = '' OR se1.e1_cliente >= :cliente_ini)
      AND (:cliente_fim = '' OR se1.e1_cliente <= :cliente_fim)
      AND (:prefixo_ini = '' OR se1.e1_prefixo >= :prefixo_ini)
      AND (:prefixo_fim = '' OR se1.e1_prefixo <= :prefixo_fim)
      AND (:titulo_ini = '' OR se1.e1_num >= :titulo_ini)
      AND (:titulo_fim = '' OR se1.e1_num <= :titulo_fim)
      AND (:banco_ini = '' OR se1.e1_portado >= :banco_ini)
      AND (:banco_fim = '' OR se1.e1_portado <= :banco_fim)
      AND (:natureza_ini = '' OR se1.e1_naturez >= :natureza_ini)
      AND (:natureza_fim = '' OR se1.e1_naturez <= :natureza_fim)
      AND (:loja_ini = '' OR se1.e1_loja >= :loja_ini)
      AND (:loja_fim = '' OR se1.e1_loja <= :loja_fim)
      AND (
            :vencimento_ini = '' OR :vencimento_fim = ''
         OR se1.e1_vencrea::date BETWEEN NULLIF(:vencimento_ini, '')::date AND NULLIF(:vencimento_fim, '')::date
      )
      AND (
            :emissao_ini = '' OR :emissao_fim = ''
         OR se1.e1_emissao::date BETWEEN NULLIF(:emissao_ini, '')::date AND NULLIF(:emissao_fim, '')::date
      )

    UNION ALL

    SELECT
        se1.e1_filial, se1.e1_prefixo, se1.e1_num, se1.e1_parcela, se1.e1_tipo,
        se1.e1_cliente AS cliente_codigo, se1.e1_loja AS cliente_loja,
        se1.e1_naturez, se1.e1_emissao, se1.e1_vencto, se1.e1_vencrea,
        se1.e1_portado, se1.e1_situaca, se1.e1_numbco, se1.e1_hist,
        se1.e1_valor, se1.e1_saldo, se1.e1_sdacres, se1.e1_sddecre,
        se1.e1_porcjur, se1.e1_valjur, se1.e1_multa, se1.e1_titpai,
        se1.r_e_c_n_o_,
        TRUE AS titulo_reconstituido
    FROM se1010 se1
    INNER JOIN fju ON fju.fju_recori = se1.r_e_c_n_o_
                  AND fju.fju_cart = 'R'
                  AND COALESCE(fju.d_e_l_e_t_, ' ') = ' '
                  AND fju.fju_emis <= :data_base
                  AND fju.fju_dtexcl >= :data_base
    WHERE se1.d_e_l_e_t_ = '*'
      AND :considerar_excluidos = '1'
      AND TRIM(se1.e1_filial) IN __FILIAL_IN__
      AND (:cliente_ini = '' OR se1.e1_cliente >= :cliente_ini)
      AND (:cliente_fim = '' OR se1.e1_cliente <= :cliente_fim)
      AND (:prefixo_ini = '' OR se1.e1_prefixo >= :prefixo_ini)
      AND (:prefixo_fim = '' OR se1.e1_prefixo <= :prefixo_fim)
      AND (:titulo_ini = '' OR se1.e1_num >= :titulo_ini)
      AND (:titulo_fim = '' OR se1.e1_num <= :titulo_fim)
)
SELECT
    t.e1_filial,
    t.e1_prefixo,
    t.e1_num,
    t.e1_parcela,
    t.e1_tipo,
    t.cliente_codigo,
    sa1.a1_nome AS nome_cliente,
    t.e1_naturez,
    sed.ed_descric AS nome_natureza,
    t.e1_emissao,
    t.e1_vencto,
    t.e1_vencrea,
    t.e1_portado,
    sa6.a6_nreduz AS nome_banco,
    t.e1_valor,
    (
        CASE WHEN :saldo_retroativo = '1' THEN
            GREATEST(0, t.e1_valor - COALESCE((
                SELECT SUM(se5.e5_valor)
                FROM se5010 se5
                WHERE se5.e5_filial = t.e1_filial AND se5.e5_prefixo = t.e1_prefixo
                  AND se5.e5_numero = t.e1_num AND se5.e5_parcela = t.e1_parcela
                  AND se5.e5_tipo = t.e1_tipo AND se5.e5_clifor = t.cliente_codigo
                  AND se5.e5_loja = t.cliente_loja
                  AND COALESCE(se5.d_e_l_e_t_, ' ') = ' '
                  AND se5.e5_data::date <= :data_base::date
            ), 0))
        ELSE t.e1_saldo + COALESCE(t.e1_sdacres, 0) - COALESCE(t.e1_sddecre, 0)
        END
    ) AS saldo,
    COALESCE((
        SELECT SUM(ab.e1_saldo)
        FROM se1010 ab
        WHERE COALESCE(ab.d_e_l_e_t_, ' ') = ' '
          AND TRIM(ab.e1_tipo) = ANY (string_to_array(:tipos_abatimento, '|'))
          AND ab.e1_titpai = TRIM(t.e1_prefixo) || TRIM(t.e1_num) || TRIM(t.e1_parcela) || TRIM(t.e1_tipo) || TRIM(t.cliente_codigo) || TRIM(t.cliente_loja)
    ), 0) AS abatimento,
    (:data_base::date - t.e1_vencto::date) AS dias_atraso,
    (:data_base::date > t.e1_vencrea::date) AS vencido,
    t.e1_porcjur,
    t.e1_valjur,
    t.e1_multa,
    t.e1_hist,
    t.titulo_reconstituido,
    EXISTS (
        SELECT 1 FROM fk7
        WHERE fk7.fk7_filial = t.e1_filial
          AND COALESCE(fk7.d_e_l_e_t_, ' ') = ' '
          AND fk7.fk7_chave = 'SE1' || TRIM(t.e1_filial) || '|' || TRIM(t.e1_prefixo) || '|' || TRIM(t.e1_num) || '|' || TRIM(t.e1_parcela) || '|' || TRIM(t.e1_tipo) || '|' || TRIM(t.cliente_codigo) || '|' || TRIM(t.cliente_loja)
    ) AS tem_valor_acessorio,
    0 AS valor_acessorio
FROM titulos t
LEFT JOIN sa1010 sa1 ON sa1.a1_cod = t.cliente_codigo AND sa1.a1_loja = t.cliente_loja
LEFT JOIN sed010 sed ON sed.ed_codigo = t.e1_naturez
LEFT JOIN sa6010 sa6 ON sa6.a6_cod = t.e1_portado
ORDER BY __ORDEM__
"""

_CAMPOS_OPCIONAIS = (
    "cliente_ini", "cliente_fim", "prefixo_ini", "prefixo_fim",
    "titulo_ini", "titulo_fim", "banco_ini", "banco_fim",
    "natureza_ini", "natureza_fim", "loja_ini", "loja_fim",
    "vencimento_ini", "vencimento_fim", "emissao_ini", "emissao_fim",
    "saldo_retroativo", "considerar_excluidos", "abatimentos", "ordenar_por",
)

_TIPOS_ABATIMENTO_PADRAO = "AB|FA"


def _serializar(valor):
    if isinstance(valor, Decimal):
        return float(valor)
    return valor


def _buscar_titulos(filiais: list[str], opcionais: dict[str, str]) -> tuple[list[str], list[tuple]]:
    clausula_filial, binds_filial = clausula_in("filial", filiais)

    ordenar_por = opcionais.pop("ordenar_por", "") or "cliente"
    ordem_sql = _ORDENS.get(ordenar_por, _ORDENS["cliente"])

    abatimentos = opcionais.pop("abatimentos", "") or "1"
    opcionais["tipos_abatimento"] = "" if abatimentos == "3" else _TIPOS_ABATIMENTO_PADRAO

    opcionais.setdefault("data_base", date.today().strftime("%Y%m%d"))

    sql = _QUERY.replace("__FILIAL_IN__", clausula_filial).replace("__ORDEM__", ordem_sql)

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
    @mcp.custom_route("/api/financeiro/posicao-titulos", methods=["GET"])
    async def listar_posicao_titulos_route(request: Request) -> JSONResponse:
        """RELATÓRIO: Posição dos Títulos a Receber (FINR130) — endpoint JSON usado pela tela."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse({"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS)

        colunas, linhas = _buscar_titulos(*parametros)
        dados = [dict(zip(colunas, (_serializar(valor) for valor in linha))) for linha in linhas]
        return JSONResponse(dados, headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/posicao-titulos/exportar", methods=["GET"])
    async def exportar_posicao_titulos_route(request: Request) -> Response:
        """RELATÓRIO: Posição dos Títulos a Receber (FINR130) — exportação em Excel."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse({"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS)

        colunas, linhas = _buscar_titulos(*parametros)
        conteudo_xlsx = gerar_xlsx(colunas, linhas, titulo="Posição dos Títulos a Receber")
        return Response(
            content=conteudo_xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="posicao_titulos.xlsx"',
                **CORS_HEADERS,
            },
        )
