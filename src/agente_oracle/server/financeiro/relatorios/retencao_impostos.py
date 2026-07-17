"""RELATÓRIO: Relação de Títulos a Pagar com Retenção de Impostos (FINR865)

Tradução do ADVPL (`FINR865.PRW`) — lista títulos de `SE2` (contas a pagar)
que tiveram algum imposto retido (PIS/COFINS/CSLL/IRRF/ISS/INSS/SEST),
agrupados por fornecedor, com o valor original, cada imposto retido e o
valor líquido por título.

Duas configurações de sistema do ADVPL original (parâmetros `MV_BX10925` e
`MV_MRETISS`) decidem, globalmente, se PIS/COFINS/CSLL e ISS são retidos na
emissão do título ou só depois, na baixa. Não temos como saber o valor real
desses parâmetros no Protheus do Grupo Conceito, então usamos os **defaults**
do ADVPL quando o parâmetro não está configurado (`_LPCC_BAIXA = False`,
`_LCALC_ISS_BX = False` abaixo) — ou seja, PIS/COFINS/CSLL e ISS sempre
retidos na emissão. Isso não é um atalho: são exatamente os valores que o
relatório original assume na ausência de configuração.

Já a retenção de IRRF na baixa **não** depende de nenhum parâmetro global —
é definida por fornecedor (`SA2.A2_CALCIRF = '2'`), e por isso fica com
fidelidade real aqui (o "fidelidade máxima" pedido): quando o fornecedor usa
esse modo, o título mostra o valor efetivamente retido (`E2_VRETIRF`) se já
baixado, ou o valor calculado na emissão (`E2_IRRF`) se ainda em aberto e o
filtro `considera_impostos` pedir isso — equivalente ao MV_PAR17/nFiltRet do
original, só que sem checar remessa bancária (`VLDBOR`, tabela de borderô
que não existe nesse schema): aproximamos "ainda não foi gerado o título de
retenção" simplesmente como "título ainda em aberto" (`E2_BAIXA` vazio).

`SA2.A2_MINIRF = '2'` (fornecedor com valor mínimo de retenção de IRRF) também
tem fidelidade real, mas de um jeito mais direto que o original: no ADVPL,
esse ramo acumula `nTotRetIr` entre títulos do mesmo fornecedor, mas essa
variável nunca é lida por nenhuma célula impressa nem persistida — é
bookkeeping morto, sem efeito observável no relatório. O valor realmente
mostrado, nesse ramo, é sempre `E2_IRRF` (o calculado), então é isso que
replicamos, sem a variável de acumulação (que não muda nada).

O que ficou de fora (documentado, não é atalho silencioso):
- Filtro por código de retenção (`FR865CodRet`/`FR865FilCRet`) — usa `TxSeek`
  para achar títulos-filho de imposto gerados no mesmo lote, indexados por
  natureza (`MV_PISNAT`/`MV_COFINS`/etc.) — mecanismo de índice temporário
  específico do Protheus sem equivalente no nosso schema.
- Coluna TIPORET (A/B/C) e a legenda de rodapé (`F865Legenda`) — são
  marcadores textuais de UI para um relatório impresso paginado; não fazem
  sentido numa tabela plana JSON/Excel.
- Gestão Corporativa multi-filial (`AdmGetFil`/quebra e totalização por
  filial, `FR865QuebraFil`) — Grupo Conceito é filial única.
- Títulos do tipo "pagamento antecipado" (`MVPAGANT`/`MV_PABRUTO`) — lista de
  tipos de título tratada como um parâmetro de sistema externo; assumimos que
  nenhum título processado é desse tipo (Grupo Conceito não usa adiantamento
  a fornecedor nesse fluxo), o que simplifica os ajustes de base/líquido do
  IRRF sem mudar o resultado dos casos normais.
- `MV_VL10925` (limiar de retenção obrigatória de PIS/COFINS/CSLL, Lei
  10.925) fica hardcoded em R$ 5.000 — é o valor default do próprio ADVPL.

O que TEM fidelidade real:
- Filtro por fornecedor/loja, tipo de pessoa (física/jurídica), faixa de
  emissão e de vencimento, além do filtro-base do relatório original: só
  aparecem títulos com pelo menos um imposto (INSS/ISS/PIS/COFINS/CSLL/SEST
  calculado, ou IRRF calculado/retido) diferente de zero.
- Valor original (com IRRF, ISS e PCC recompostos de volta pro bruto,
  conforme o tipo de retenção do título) e valor líquido (com PCC/IRRF
  descontados quando cabível, mais acréscimo e menos decréscimo) — mesma
  fórmula usada no ADVPL original (`nValBase`/`nValLiq`).
- IRRF/INSS/PIS/COFINS/CSLL retidos, com o desvio "retido em outro título"
  (`E2_PRET* = '1'`): mostra o valor calculado no próprio título mesmo sem
  ter sido fisicamente retido nele, exatamente como o `TReport` original.

Atenção: só roda com DB_BACKEND=postgres (cast ::date). Datas em SE2 nesse
banco de teste são VARCHAR (formato "YYYYMMDD").

Particularidade do dado de teste: as colunas de imposto (E2_IRRF, E2_ISS,
E2_INSS, E2_PIS, E2_COFINS, E2_CSLL, E2_SEST, E2_VRETIRF, E2_VRETINS,
E2_VRETPIS, E2_VRETCOF, E2_VRETCSL, E2_PRETIRF, E2_PRETINS, E2_PRETPIS,
E2_PRETCOF, E2_PRETCSL, E2_ACRESC, E2_JUROS, E2_MULTA, E2_DECRESC,
E2_DESCONT) foram adicionadas nesta sessão — SE2 não tinha nenhuma delas
antes, só os campos usados pelos relatórios anteriores (FINR130/150).
"""

from decimal import Decimal

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.db.connection import get_connection
from agente_oracle.relatorios import gerar_xlsx
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.server.financeiro.relatorios.filtros_sql import clausula_in

# Defaults do ADVPL quando MV_BX10925/MV_MRETISS não estão configurados:
# PIS/COFINS/CSLL e ISS retidos na emissão do título, não na baixa.
_LPCC_BAIXA = False
_LCALC_ISS_BX = False

# MV_VL10925 (SuperGetMv("MV_VL10925", , 5000)) — limiar da Lei 10.925.
_LIMIAR_10925 = 5000

_ORDENS = {
    "codigo": "v.fornecedor_codigo, v.fornecedor_loja, v.e2_prefixo, v.e2_num, v.e2_parcela",
    "nome": "v.nome_fornecedor, v.e2_prefixo, v.e2_num, v.e2_parcela",
}

_QUERY = """
-- =====================================================================
-- RELATORIO: Relacao de Titulos a Pagar com Retencao de Impostos (FINR865)
-- versao simplificada (sem filtro por codigo de retencao/Gestao Corporativa)
-- =====================================================================
WITH titulos AS (
    SELECT
        se2.e2_filial, se2.e2_prefixo, se2.e2_num, se2.e2_parcela, se2.e2_tipo,
        se2.e2_fornece AS fornecedor_codigo, se2.e2_loja AS fornecedor_loja,
        se2.e2_naturez, se2.e2_emissao, se2.e2_vencrea, se2.e2_valor,
        COALESCE(se2.e2_irrf, 0) AS e2_irrf,
        COALESCE(se2.e2_iss, 0) AS e2_iss,
        COALESCE(se2.e2_inss, 0) AS e2_inss,
        COALESCE(se2.e2_pis, 0) AS e2_pis,
        COALESCE(se2.e2_cofins, 0) AS e2_cofins,
        COALESCE(se2.e2_csll, 0) AS e2_csll,
        COALESCE(se2.e2_sest, 0) AS e2_sest,
        COALESCE(se2.e2_vretirf, 0) AS e2_vretirf,
        COALESCE(se2.e2_vretins, 0) AS e2_vretins,
        COALESCE(se2.e2_vretpis, 0) AS e2_vretpis,
        COALESCE(se2.e2_vretcof, 0) AS e2_vretcof,
        COALESCE(se2.e2_vretcsl, 0) AS e2_vretcsl,
        COALESCE(se2.e2_pretirf, '') AS e2_pretirf,
        COALESCE(se2.e2_pretins, '') AS e2_pretins,
        COALESCE(se2.e2_pretpis, '') AS e2_pretpis,
        COALESCE(se2.e2_pretcof, '') AS e2_pretcof,
        COALESCE(se2.e2_pretcsl, '') AS e2_pretcsl,
        COALESCE(se2.e2_acresc, 0) AS e2_acresc,
        COALESCE(se2.e2_juros, 0) AS e2_juros,
        COALESCE(se2.e2_multa, 0) AS e2_multa,
        COALESCE(se2.e2_decresc, 0) AS e2_decresc,
        COALESCE(se2.e2_descont, 0) AS e2_descont,
        COALESCE(se2.e2_baixa, '') AS e2_baixa,
        sa2.a2_nome AS nome_fornecedor,
        sa2.a2_cgc,
        COALESCE(sa2.a2_calcirf, '') AS a2_calcirf,
        COALESCE(sa2.a2_minirf, '') AS a2_minirf,
        (COALESCE(sed.ed_dedinss, '') = '1') AS dedinss
    FROM se2
    INNER JOIN sa2010 sa2
        ON sa2.a2_cod = se2.e2_fornece AND sa2.a2_loja = se2.e2_loja
       AND COALESCE(sa2.d_e_l_e_t_, ' ') = ' '
    LEFT JOIN sed010 sed ON sed.ed_codigo = se2.e2_naturez
    WHERE COALESCE(se2.d_e_l_e_t_, ' ') = ' '
      AND TRIM(se2.e2_filial) IN __FILIAL_IN__
      AND (:fornecedor_ini = '' OR se2.e2_fornece >= :fornecedor_ini)
      AND (:fornecedor_fim = '' OR se2.e2_fornece <= :fornecedor_fim)
      AND (:loja_ini = '' OR se2.e2_loja >= :loja_ini)
      AND (:loja_fim = '' OR se2.e2_loja <= :loja_fim)
      AND (:tipo_pessoa = '' OR sa2.a2_tipo = :tipo_pessoa)
      AND (
            :vencimento_ini = '' OR :vencimento_fim = ''
         OR se2.e2_vencrea::date BETWEEN :vencimento_ini::date AND :vencimento_fim::date
      )
      AND (
            :emissao_ini = '' OR :emissao_fim = ''
         OR se2.e2_emissao::date BETWEEN :emissao_ini::date AND :emissao_fim::date
      )
      AND se2.e2_emissao::date <= CURRENT_DATE
      AND (
            COALESCE(se2.e2_inss, 0) > 0 OR COALESCE(se2.e2_iss, 0) > 0 OR COALESCE(se2.e2_pis, 0) > 0
         OR COALESCE(se2.e2_cofins, 0) > 0 OR COALESCE(se2.e2_csll, 0) > 0 OR COALESCE(se2.e2_sest, 0) > 0
         OR (COALESCE(se2.e2_irrf, 0) > 0 OR (COALESCE(se2.e2_vretirf, 0) > 0 AND COALESCE(se2.e2_pretirf, '') <> '1'))
      )
),
calc AS (
    SELECT t.*,
        (t.a2_calcirf = '2') AS irpf_na_baixa,
        (
            CASE
                WHEN t.a2_calcirf = '2' THEN
                    CASE
                        WHEN :considera_impostos = '2' AND t.e2_vretirf = 0 AND t.e2_baixa = '' THEN t.e2_irrf
                        ELSE t.e2_vretirf
                    END
                ELSE
                    CASE WHEN t.a2_minirf = '2' THEN t.e2_irrf ELSE t.e2_vretirf END
            END
        ) AS v_irrf,
        (CASE WHEN t.e2_pretins <> '1' THEN t.e2_vretins ELSE t.e2_inss END) AS v_inss,
        (CASE WHEN t.e2_pretpis <> '1' THEN t.e2_vretpis ELSE t.e2_pis END) AS v_pis,
        (CASE WHEN t.e2_pretcof <> '1' THEN t.e2_vretcof ELSE t.e2_cofins END) AS v_cofins,
        (CASE WHEN t.e2_pretcsl <> '1' THEN t.e2_vretcsl ELSE t.e2_csll END) AS v_csll,
        t.e2_iss AS v_iss,
        t.e2_sest AS v_sest,
        (
            (t.e2_pretpis NOT IN ('2', '3', '4') OR t.e2_pretcof NOT IN ('2', '3', '4') OR t.e2_pretcsl NOT IN ('2', '3', '4'))
            AND (t.e2_pis + t.e2_cofins + t.e2_csll) > 0
        ) AS pcc_retido_aqui,
        (t.e2_vretpis + t.e2_vretcof + t.e2_vretcsl - (t.e2_pis + t.e2_cofins + t.e2_csll)) AS descont_pcc,
        (CASE WHEN t.e2_juros > 0 THEN t.e2_juros + t.e2_multa ELSE t.e2_acresc + t.e2_multa END) AS valor_acrescimo,
        (CASE WHEN t.e2_descont > 0 THEN t.e2_descont ELSE t.e2_decresc END) AS valor_decrescimo
    FROM titulos t
),
valores AS (
    SELECT c.*,
        (
            c.e2_valor
            + CASE WHEN c.dedinss THEN c.e2_inss ELSE 0 END
            + c.e2_iss
            + CASE WHEN c.v_irrf <> 0 AND NOT c.irpf_na_baixa THEN c.v_irrf ELSE 0 END
            + CASE
                WHEN (c.e2_pretpis = '' OR c.e2_pretcof = '' OR c.e2_pretcsl = '') AND (c.e2_pis + c.e2_cofins + c.e2_csll) > 0
                THEN c.e2_vretpis + c.e2_vretcof + c.e2_vretcsl
                ELSE 0
              END
            + c.e2_sest
        ) AS valor_base_prelim,
        (
            c.e2_valor
            - CASE
                WHEN (c.e2_pretpis = '2' OR c.e2_pretcof = '2' OR c.e2_pretcsl = '2') AND (c.e2_pis + c.e2_cofins + c.e2_csll) > 0
                THEN c.e2_pis + c.e2_cofins + c.e2_csll
                ELSE 0
              END
            - CASE WHEN c.irpf_na_baixa AND c.e2_pretirf IN ('1', '7', '', '4') THEN c.v_irrf ELSE 0 END
        ) AS valor_liq_prelim
    FROM calc c
)
SELECT
    v.e2_filial,
    v.e2_prefixo,
    v.e2_num,
    v.e2_parcela,
    v.e2_tipo,
    v.fornecedor_codigo,
    v.fornecedor_loja,
    v.nome_fornecedor,
    v.a2_cgc,
    v.e2_naturez,
    v.e2_emissao,
    v.e2_vencrea,
    (
        v.valor_base_prelim
        + CASE WHEN v.pcc_retido_aqui THEN v.descont_pcc ELSE 0 END
        + CASE
            WHEN v.pcc_retido_aqui AND v.valor_base_prelim > __LIMIAR_10925__ AND NOT v.irpf_na_baixa
             AND (v.e2_pretpis <> '' OR v.e2_pretcof <> '' OR v.e2_pretcsl <> '')
            THEN v.descont_pcc ELSE 0
          END
    ) AS valor_original,
    v.valor_acrescimo,
    v.valor_decrescimo,
    v.v_sest AS valor_sest,
    v.v_irrf AS valor_irrf,
    v.v_iss AS valor_iss,
    v.v_inss AS valor_inss,
    v.v_pis AS valor_pis,
    v.v_cofins AS valor_cofins,
    v.v_csll AS valor_csll,
    (
        v.valor_liq_prelim
        + CASE WHEN v.pcc_retido_aqui THEN v.descont_pcc ELSE 0 END
        + v.valor_acrescimo
        - v.valor_decrescimo
    ) AS valor_liquido
FROM valores v
ORDER BY __ORDEM__
"""

_CAMPOS_OPCIONAIS = (
    "fornecedor_ini", "fornecedor_fim", "loja_ini", "loja_fim", "tipo_pessoa",
    "vencimento_ini", "vencimento_fim", "emissao_ini", "emissao_fim",
    "considera_impostos", "ordenar_por",
)


def _serializar(valor):
    if isinstance(valor, Decimal):
        return float(valor)
    return valor


def _buscar_titulos(filiais: list[str], opcionais: dict[str, str]) -> tuple[list[str], list[tuple]]:
    clausula_filial, binds_filial = clausula_in("filial", filiais)

    ordenar_por = opcionais.pop("ordenar_por", "") or "codigo"
    ordem_sql = _ORDENS.get(ordenar_por, _ORDENS["codigo"])

    opcionais.setdefault("considera_impostos", "1")

    sql = (
        _QUERY.replace("__FILIAL_IN__", clausula_filial)
        .replace("__ORDEM__", ordem_sql)
        .replace("__LIMIAR_10925__", str(_LIMIAR_10925))
    )

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
    @mcp.custom_route("/api/financeiro/retencao-impostos", methods=["GET"])
    async def listar_retencao_impostos_route(request: Request) -> JSONResponse:
        """RELATÓRIO: Relação de Títulos a Pagar com Retenção de Impostos (FINR865) — endpoint JSON usado pela tela."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse({"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS)

        colunas, linhas = _buscar_titulos(*parametros)
        dados = [dict(zip(colunas, (_serializar(valor) for valor in linha))) for linha in linhas]
        return JSONResponse(dados, headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/retencao-impostos/exportar", methods=["GET"])
    async def exportar_retencao_impostos_route(request: Request) -> Response:
        """RELATÓRIO: Relação de Títulos a Pagar com Retenção de Impostos (FINR865) — exportação em Excel."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse({"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS)

        colunas, linhas = _buscar_titulos(*parametros)
        conteudo_xlsx = gerar_xlsx(colunas, linhas, titulo="Relação de Títulos a Pagar com Retenção de Impostos")
        return Response(
            content=conteudo_xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="retencao_impostos.xlsx"',
                **CORS_HEADERS,
            },
        )
