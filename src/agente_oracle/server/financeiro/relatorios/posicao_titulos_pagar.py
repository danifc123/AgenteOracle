"""RELATÓRIO: Posição dos Títulos a Pagar (FINR150)

Tradução do ADVPL (`FINR150.PRX`) — é o espelho, para contas a pagar, do
FINR130/"Posição dos Títulos" (`posicao_titulos.py`, contas a receber): mesma
arquitetura de `TReport`, mesmo uso de FJU (títulos excluídos) e FK7/FKD
(Valores Acessórios), só que em cima de SE2 (títulos a pagar) e SA2
(fornecedores) em vez de SE1/SA1. Valem as mesmas simplificações já
combinadas para aquele relatório e pelo mesmo motivo: Gestão Corporativa
(multi-empresa), templates de desconto, multi-moeda e retenção de impostos
na baixa ficam de fora porque o Grupo Conceito opera com uma única
empresa/filial e não temos como validar esses módulos nesse banco de teste.

O que TEM fidelidade real com o ADVPL original:
- Todos os filtros em faixa (fornecedor, prefixo, título, banco, vencimento,
  natureza, emissão, loja) + filial multi-select.
- Saldo do título: atual (E2_SALDO+E2_SDACRES-E2_SDDECRE) OU **retroativo**,
  reconstruído somando as baixas reais em SE5010 (E5_RECPAG='P') até a
  data-base — equivalente ao MV_PAR21/SaldoTit() do original.
- Split vencido/a vencer com base em E2_VENCTO/E2_VENCREA vs a data-base.
- **Abatimento**: títulos-filho (E2_TITPAI apontando pro título-pai) com
  saldo em aberto são deduzidos do saldo do pai — mesma lógica do FINR130.
  O banco de teste não tem título do tipo abatimento hoje, então esse valor
  sempre dá zero aqui.
- **Reconstrução de títulos excluídos (FJU)**: quando `considerar_excluidos`
  está ligado, títulos com D_E_L_E_T_='*' que tenham um registro em FJU
  cuja janela (FJU_EMIS <= data-base <= FJU_DTEXCL, **FJU_CART='P'** — é
  essa marcação que distingue títulos a pagar dos a receber na mesma
  tabela FJU) ainda esteja "válida" voltam a aparecer no relatório.
- **Gate de Valores Acessórios (VA)**: verificamos se o título tem vínculo
  em FK7/FKD (`tem_valor_acessorio`) usando a mesma FK7_CHAVE do original,
  só que com prefixo "SE2" em vez de "SE1"
  (`"SE2"+filial+"|"+prefixo+"|"+num+"|"+parcela+"|"+tipo+"|"+fornecedor+"|"+loja`).
  O VALOR do VA (`FValAcess()`) é externo e desconhecido, igual ao FINR130 —
  `valor_acessorio` fica sempre 0 aqui.

O que ficou de fora e por quê (diferença real em relação ao FINR130, não
simplificação nossa): o ADVPL original calcula juros/permanência via
`Fa080Juros()`, uma função de rateio de taxa de mora que não está nesse
arquivo (é externa) e — diferente do FINR130, que usa campos armazenados
por título em SE1 (E1_PORCJUR/E1_VALJUR/E1_MULTA) — o FINR150 não referencia
nenhum campo equivalente em SE2 para este cálculo. Sem a fórmula real nem um
campo por título pra basear o valor, não incluímos "juros" no resultado
aqui: inventar um número pareceria fiel mas estaria errado.

Atenção: só roda com DB_BACKEND=postgres (cast ::date). Datas em SE2/SE5010
nesse banco de teste são VARCHAR (formato "YYYYMMDD").

Particularidade do dado de teste: SE2 foi criada nesta sessão só com as
colunas usadas por este relatório (ao contrário de SE1010/SA1010/SA2010,
que já tinham a estrutura real completa) — colunas de controle
(R_E_C_D_E_L_/S_T_A_M_P_/I_N_S_D_T_) e os campos E2_SDACRES/E2_SDDECRE/
E2_PORTADO/E2_HIST/E2_TITPAI foram adicionados agora para viabilizar esta
tradução com fidelidade.
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
    "fornecedor": "fornecedor_codigo, fornecedor_loja",
    "numero": "e2_num, e2_prefixo, e2_parcela",
    "vencimento": "e2_vencrea",
    "natureza": "e2_naturez",
    "banco": "e2_portado",
}

_QUERY = """
-- =====================================================================
-- RELATORIO: Posicao dos Titulos a Pagar (FINR150) — versao simplificada
-- (sem Gestao Corporativa/GEM/multi-moeda/retencao de impostos na baixa)
-- =====================================================================
WITH titulos AS (
    SELECT
        se2.e2_filial, se2.e2_prefixo, se2.e2_num, se2.e2_parcela, se2.e2_tipo,
        se2.e2_fornece AS fornecedor_codigo, se2.e2_loja AS fornecedor_loja,
        se2.e2_naturez, se2.e2_emissao, se2.e2_vencto, se2.e2_vencrea,
        se2.e2_portado, se2.e2_hist,
        se2.e2_valor, se2.e2_saldo, se2.e2_sdacres, se2.e2_sddecre,
        se2.e2_titpai,
        se2.r_e_c_n_o_,
        FALSE AS titulo_reconstituido
    FROM se2
    WHERE COALESCE(se2.d_e_l_e_t_, ' ') = ' '
      AND TRIM(se2.e2_filial) IN __FILIAL_IN__
      AND (:fornecedor_ini = '' OR se2.e2_fornece >= :fornecedor_ini)
      AND (:fornecedor_fim = '' OR se2.e2_fornece <= :fornecedor_fim)
      AND (:prefixo_ini = '' OR se2.e2_prefixo >= :prefixo_ini)
      AND (:prefixo_fim = '' OR se2.e2_prefixo <= :prefixo_fim)
      AND (:titulo_ini = '' OR se2.e2_num >= :titulo_ini)
      AND (:titulo_fim = '' OR se2.e2_num <= :titulo_fim)
      AND (:banco_ini = '' OR se2.e2_portado >= :banco_ini)
      AND (:banco_fim = '' OR se2.e2_portado <= :banco_fim)
      AND (:natureza_ini = '' OR se2.e2_naturez >= :natureza_ini)
      AND (:natureza_fim = '' OR se2.e2_naturez <= :natureza_fim)
      AND (:loja_ini = '' OR se2.e2_loja >= :loja_ini)
      AND (:loja_fim = '' OR se2.e2_loja <= :loja_fim)
      AND (
            :vencimento_ini = '' OR :vencimento_fim = ''
         OR se2.e2_vencrea::date BETWEEN NULLIF(:vencimento_ini, '')::date AND NULLIF(:vencimento_fim, '')::date
      )
      AND (
            :emissao_ini = '' OR :emissao_fim = ''
         OR se2.e2_emissao::date BETWEEN NULLIF(:emissao_ini, '')::date AND NULLIF(:emissao_fim, '')::date
      )

    UNION ALL

    SELECT
        se2.e2_filial, se2.e2_prefixo, se2.e2_num, se2.e2_parcela, se2.e2_tipo,
        se2.e2_fornece AS fornecedor_codigo, se2.e2_loja AS fornecedor_loja,
        se2.e2_naturez, se2.e2_emissao, se2.e2_vencto, se2.e2_vencrea,
        se2.e2_portado, se2.e2_hist,
        se2.e2_valor, se2.e2_saldo, se2.e2_sdacres, se2.e2_sddecre,
        se2.e2_titpai,
        se2.r_e_c_n_o_,
        TRUE AS titulo_reconstituido
    FROM se2
    INNER JOIN fju ON fju.fju_recori = se2.r_e_c_n_o_
                  AND fju.fju_cart = 'P'
                  AND COALESCE(fju.d_e_l_e_t_, ' ') = ' '
                  AND fju.fju_emis <= :data_base
                  AND fju.fju_dtexcl >= :data_base
    WHERE se2.d_e_l_e_t_ = '*'
      AND :considerar_excluidos = '1'
      AND TRIM(se2.e2_filial) IN __FILIAL_IN__
      AND (:fornecedor_ini = '' OR se2.e2_fornece >= :fornecedor_ini)
      AND (:fornecedor_fim = '' OR se2.e2_fornece <= :fornecedor_fim)
      AND (:prefixo_ini = '' OR se2.e2_prefixo >= :prefixo_ini)
      AND (:prefixo_fim = '' OR se2.e2_prefixo <= :prefixo_fim)
      AND (:titulo_ini = '' OR se2.e2_num >= :titulo_ini)
      AND (:titulo_fim = '' OR se2.e2_num <= :titulo_fim)
)
SELECT
    t.e2_filial,
    t.e2_prefixo,
    t.e2_num,
    t.e2_parcela,
    t.e2_tipo,
    t.fornecedor_codigo,
    sa2.a2_nome AS nome_fornecedor,
    t.e2_naturez,
    sed.ed_descric AS nome_natureza,
    t.e2_emissao,
    t.e2_vencto,
    t.e2_vencrea,
    t.e2_portado,
    sa6.a6_nreduz AS nome_banco,
    t.e2_valor,
    (
        CASE WHEN :saldo_retroativo = '1' THEN
            GREATEST(0, t.e2_valor - COALESCE((
                SELECT SUM(se5.e5_valor)
                FROM se5010 se5
                WHERE se5.e5_filial = t.e2_filial AND se5.e5_prefixo = t.e2_prefixo
                  AND se5.e5_numero = t.e2_num AND se5.e5_parcela = t.e2_parcela
                  AND se5.e5_tipo = t.e2_tipo AND se5.e5_clifor = t.fornecedor_codigo
                  AND se5.e5_loja = t.fornecedor_loja
                  AND se5.e5_recpag = 'P'
                  AND COALESCE(se5.d_e_l_e_t_, ' ') = ' '
                  AND se5.e5_data::date <= :data_base::date
            ), 0))
        ELSE t.e2_saldo + COALESCE(t.e2_sdacres, 0) - COALESCE(t.e2_sddecre, 0)
        END
    ) AS saldo,
    COALESCE((
        SELECT SUM(ab.e2_saldo)
        FROM se2 ab
        WHERE COALESCE(ab.d_e_l_e_t_, ' ') = ' '
          AND TRIM(ab.e2_tipo) = ANY (string_to_array(:tipos_abatimento, '|'))
          AND ab.e2_titpai = TRIM(t.e2_prefixo) || TRIM(t.e2_num) || TRIM(t.e2_parcela) || TRIM(t.e2_tipo) || TRIM(t.fornecedor_codigo) || TRIM(t.fornecedor_loja)
    ), 0) AS abatimento,
    (:data_base::date - t.e2_vencto::date) AS dias_atraso,
    (:data_base::date > t.e2_vencrea::date) AS vencido,
    t.e2_hist,
    t.titulo_reconstituido,
    EXISTS (
        SELECT 1 FROM fk7
        WHERE fk7.fk7_filial = t.e2_filial
          AND COALESCE(fk7.d_e_l_e_t_, ' ') = ' '
          AND fk7.fk7_chave = 'SE2' || TRIM(t.e2_filial) || '|' || TRIM(t.e2_prefixo) || '|' || TRIM(t.e2_num) || '|' || TRIM(t.e2_parcela) || '|' || TRIM(t.e2_tipo) || '|' || TRIM(t.fornecedor_codigo) || '|' || TRIM(t.fornecedor_loja)
    ) AS tem_valor_acessorio,
    0 AS valor_acessorio
FROM titulos t
LEFT JOIN sa2010 sa2 ON sa2.a2_cod = t.fornecedor_codigo AND sa2.a2_loja = t.fornecedor_loja
LEFT JOIN sed010 sed ON sed.ed_codigo = t.e2_naturez
LEFT JOIN sa6010 sa6 ON sa6.a6_cod = t.e2_portado
ORDER BY __ORDEM__
"""

_CAMPOS_OPCIONAIS = (
    "fornecedor_ini", "fornecedor_fim", "prefixo_ini", "prefixo_fim",
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

    ordenar_por = opcionais.pop("ordenar_por", "") or "fornecedor"
    ordem_sql = _ORDENS.get(ordenar_por, _ORDENS["fornecedor"])

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
    @mcp.custom_route("/api/financeiro/posicao-titulos-pagar", methods=["GET"])
    async def listar_posicao_titulos_pagar_route(request: Request) -> JSONResponse:
        """RELATÓRIO: Posição dos Títulos a Pagar (FINR150) — endpoint JSON usado pela tela."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse({"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS)

        colunas, linhas = _buscar_titulos(*parametros)
        dados = [dict(zip(colunas, (_serializar(valor) for valor in linha))) for linha in linhas]
        return JSONResponse(dados, headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/posicao-titulos-pagar/exportar", methods=["GET"])
    async def exportar_posicao_titulos_pagar_route(request: Request) -> Response:
        """RELATÓRIO: Posição dos Títulos a Pagar (FINR150) — exportação em Excel."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse({"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS)

        colunas, linhas = _buscar_titulos(*parametros)
        conteudo_xlsx = gerar_xlsx(colunas, linhas, titulo="Posição dos Títulos a Pagar")
        return Response(
            content=conteudo_xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="posicao_titulos_pagar.xlsx"',
                **CORS_HEADERS,
            },
        )
