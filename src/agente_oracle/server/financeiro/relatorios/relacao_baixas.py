"""RELATÓRIO: Relação de Baixas (FINR190)

Tradução do ADVPL (`FINR190.PRX`, ~2.700 linhas) — o mais complexo já
traduzido nesta série, maior até que o FINR130. Lista as baixas (liquidações)
de títulos em `SE5010` — a receber ou a pagar, conforme `tipo_movimento`
(equivalente ao MV_PAR11) — dentro de uma faixa de datas, enriquecidas com
dados do título original (`SE1010`/`SE2`).

O núcleo do ADVP original (`FA190ImpR4`, ~1.400 linhas sozinha) cobre dezenas
de ramificações que não se aplicam ao Grupo Conceito e ficaram de fora
(documentado, não é atalho silencioso):
- Multi-moeda com taxa histórica por baixa — banco de teste é mono-moeda
  (BRL), então a "correção" por conversão sempre daria 0 mesmo no original.
- Retenção de impostos na baixa (PIS/COFINS/CSLL/ISS/IRRF/INSS) — depende de
  parametrização (MV_BX10925, A2_CALCIRF, MV_MRETISS) que não temos como
  confirmar; `imposto` fica sempre 0 aqui.
- Empréstimos (SEH/SEI, tipos EP/PE), troco de loja (MV_LJTROCO), estorno de
  transferência com histórico mágico, cheques (DeleteChq) — nenhum desses
  módulos tem dado no banco de teste.
- Baixas manuais sem título (E5_TIPODOC/E5_NUMERO vazios) — não existem no
  banco de teste; se existissem no futuro, não apareceriam aqui.
- Gestão Corporativa multi-empresa e o desvio para FINR199 quando o título é
  "multi-natureza" (E2_MULTNAT) — Grupo Conceito é single empresa/filial.
- As 8 ordens de impressão/quebra do ADVPL original viraram um único filtro
  `ordenar_por`, e os totalizadores por quebra/filial/geral do relatório
  impresso não são replicados — nosso resultado é uma tabela plana, não um
  relatório paginado.

O que TEM fidelidade real:
- Filtros em faixa (banco, natureza, cliente/fornecedor, prefixo, loja,
  lote, data de digitação, vencimento do título) + filial + faixa de data
  de baixa (obrigatória, equivalente a MV_PAR01/02).
- **Valor original** = valor cheio do título (E1_VALOR/E2_VALOR), igual ao
  ADVPL original (a coluna "Valor Original" mostra o valor do título inteiro
  em cada linha de baixa, não a fração paga — é assim mesmo no original).
- **Total baixado** = soma real de E5_VALOR do(s) registro(s) de baixa que
  formam esse evento (uma baixa pode gerar múltiplos registros SE5 com o
  mesmo prefixo+número+parcela+tipo+cliente/fornecedor+data+seq+numcheq —
  agrupamos exatamente por essa chave, igual ao laço interno do original).
- **Juros/multa e desconto reais**, somados de E5_VLJUROS+E5_VLMULTA e
  E5_VLDESCO dentro do mesmo agrupamento.
- **Abatimento reconstruído**: quando o título já está com saldo zerado,
  soma o saldo de títulos-filho do tipo abatimento (E1_TITPAI/E2_TITPAI
  apontando para este título) — mesma lógica de SomaAbat/SumAbatRec do
  original, simplificada para usar o saldo atual em vez de reconstrução
  ponto-no-tempo (mesma simplificação já aplicada no FINR130/150). Banco de
  teste não tem título tipo abatimento, então dá sempre 0 — mas a fórmula
  está pronta.
- **Valor Acessório (VA) real** — ao contrário do FINR130/150 (que só tinha
  um "gate" de existência via FK7/FKD), aqui o VA tem **valor calculado de
  verdade**: soma de `FK6.FK6_VALMOV` (sinal conforme `FK6_ACAO`), vinculado
  via `SE5010.E5_IDORIG` → `FK1.FK1_IDFK1` (recebimento) ou
  `FK2.FK2_IDFK2` (pagamento). `FK2` e a coluna `FK1_IDFK1` não existiam no
  banco fictício — foram criadas agora; `FK6` também é nova (não existe
  ainda no banco fictício, mas os nomes de campo seguem a convenção real do
  Protheus para o módulo de Valores Acessórios/movimentação).

Atenção: só roda com DB_BACKEND=postgres (cast ::date). Datas em SE5010/
SE1010/SE2 nesse banco de teste são VARCHAR (formato "YYYYMMDD").
"""

from decimal import Decimal

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.db.connection import get_connection
from agente_oracle.relatorios import gerar_xlsx
from agente_oracle.server.auth.dependencia import exigir_usuario
from agente_oracle.server.cors import CORS_HEADERS, resposta_preflight
from agente_oracle.server.financeiro.relatorios.filtros_sql import clausula_in

_ORDENS = {
    "data_baixa": "b.e5_data",
    "banco": "b.e5_banco, b.e5_agencia, b.e5_conta",
    "natureza": "b.e5_naturez",
    "clifor": "nome_clifor",
    "numero": "b.e5_numero",
    "dt_digitacao": "b.e5_dtdigit",
    "lote": "b.e5_lote",
}

_QUERY = """
-- =====================================================================
-- RELATORIO: Relacao de Baixas (FINR190) — versao simplificada
-- (sem multi-moeda/retencao de impostos na baixa/emprestimos/troco/Gestao Corporativa)
-- =====================================================================
WITH baixas AS (
    SELECT
        se5.e5_filial, se5.e5_prefixo, se5.e5_numero, se5.e5_parcela, se5.e5_tipo,
        se5.e5_clifor, se5.e5_loja, se5.e5_recpag, se5.e5_data, se5.e5_seq, se5.e5_numcheq,
        MIN(se5.e5_tipodoc) AS e5_tipodoc,
        MIN(COALESCE(se5.e5_filorig, se5.e5_filial)) AS e5_filorig,
        MIN(COALESCE(NULLIF(se5.e5_motbx, ''), 'NOR')) AS e5_motbx,
        MIN(se5.e5_banco) AS e5_banco,
        MIN(se5.e5_agencia) AS e5_agencia,
        MIN(se5.e5_conta) AS e5_conta,
        MIN(se5.e5_dtdigit) AS e5_dtdigit,
        MIN(se5.e5_lote) AS e5_lote,
        MIN(se5.e5_naturez) AS e5_naturez,
        MIN(se5.e5_benef) AS e5_benef,
        MIN(se5.e5_histor) AS e5_histor,
        MIN(se5.e5_idorig) AS e5_idorig,
        SUM(se5.e5_valor) AS valor_total,
        SUM(COALESCE(se5.e5_vljuros, 0) + COALESCE(se5.e5_vlmulta, 0)) AS juros_multa,
        SUM(COALESCE(se5.e5_vlcorre, 0)) AS correcao,
        SUM(COALESCE(se5.e5_vldesco, 0)) AS desconto
    FROM se5010 se5
    WHERE COALESCE(se5.d_e_l_e_t_, ' ') = ' '
      AND se5.e5_recpag = :tipo_movimento
      AND COALESCE(se5.e5_motbx, '') <> 'DSD'
      AND TRIM(se5.e5_filial) IN __FILIAL_IN__
      AND se5.e5_data::date BETWEEN :data_baixa_ini::date AND :data_baixa_fim::date
      AND (:banco_ini = '' OR se5.e5_banco >= :banco_ini)
      AND (:banco_fim = '' OR se5.e5_banco <= :banco_fim)
      AND (:natureza_ini = '' OR se5.e5_naturez >= :natureza_ini)
      AND (:natureza_fim = '' OR se5.e5_naturez <= :natureza_fim)
      AND (:clifor_ini = '' OR se5.e5_clifor >= :clifor_ini)
      AND (:clifor_fim = '' OR se5.e5_clifor <= :clifor_fim)
      AND (:prefixo_ini = '' OR se5.e5_prefixo >= :prefixo_ini)
      AND (:prefixo_fim = '' OR se5.e5_prefixo <= :prefixo_fim)
      AND (:loja_ini = '' OR se5.e5_loja >= :loja_ini)
      AND (:loja_fim = '' OR se5.e5_loja <= :loja_fim)
      AND (:lote_ini = '' OR COALESCE(se5.e5_lote, '') >= :lote_ini)
      AND (:lote_fim = '' OR COALESCE(se5.e5_lote, '') <= :lote_fim)
      AND (
            :dt_digitacao_ini = '' OR :dt_digitacao_fim = ''
         OR se5.e5_dtdigit::date BETWEEN NULLIF(:dt_digitacao_ini, '')::date AND NULLIF(:dt_digitacao_fim, '')::date
      )
    GROUP BY se5.e5_filial, se5.e5_prefixo, se5.e5_numero, se5.e5_parcela, se5.e5_tipo,
             se5.e5_clifor, se5.e5_loja, se5.e5_recpag, se5.e5_data, se5.e5_seq, se5.e5_numcheq
)
SELECT
    b.e5_filial,
    b.e5_prefixo,
    b.e5_numero,
    b.e5_parcela,
    b.e5_tipo,
    b.e5_tipodoc,
    b.e5_recpag,
    b.e5_clifor,
    b.e5_loja,
    COALESCE(
        CASE WHEN b.e5_recpag = 'R' THEN sa1.a1_nome ELSE sa2.a2_nome END,
        NULLIF(b.e5_benef, '')
    ) AS nome_clifor,
    b.e5_naturez,
    sed.ed_descric AS nome_natureza,
    CASE WHEN b.e5_recpag = 'R' THEN se1.e1_vencrea ELSE se2.e2_vencrea END AS vencimento,
    COALESCE(NULLIF(b.e5_histor, ''), CASE WHEN b.e5_recpag = 'R' THEN se1.e1_hist ELSE se2.e2_hist END) AS historico,
    b.e5_data AS data_baixa,
    CASE WHEN b.e5_recpag = 'R' THEN se1.e1_valor ELSE se2.e2_valor END AS valor_original,
    b.juros_multa,
    b.correcao,
    b.desconto,
    COALESCE((
        CASE
            WHEN b.e5_recpag = 'R' AND se1.e1_saldo = 0 THEN (
                SELECT SUM(ab.e1_saldo) FROM se1010 ab
                WHERE COALESCE(ab.d_e_l_e_t_, ' ') = ' '
                  AND TRIM(ab.e1_tipo) = ANY (string_to_array(:tipos_abatimento, '|'))
                  AND ab.e1_titpai = TRIM(b.e5_prefixo) || TRIM(b.e5_numero) || TRIM(b.e5_parcela) || TRIM(b.e5_tipo) || TRIM(b.e5_clifor) || TRIM(b.e5_loja)
            )
            WHEN b.e5_recpag = 'P' AND se2.e2_saldo = 0 THEN (
                SELECT SUM(ab.e2_saldo) FROM se2 ab
                WHERE COALESCE(ab.d_e_l_e_t_, ' ') = ' '
                  AND TRIM(ab.e2_tipo) = ANY (string_to_array(:tipos_abatimento, '|'))
                  AND ab.e2_titpai = TRIM(b.e5_prefixo) || TRIM(b.e5_numero) || TRIM(b.e5_parcela) || TRIM(b.e5_tipo) || TRIM(b.e5_clifor) || TRIM(b.e5_loja)
            )
            ELSE 0
        END
    ), 0) AS abatimento,
    0 AS imposto,
    b.valor_total AS total_baixado,
    b.e5_banco,
    sa6.a6_nreduz AS nome_banco,
    b.e5_agencia,
    b.e5_conta,
    b.e5_dtdigit AS data_digitacao,
    b.e5_motbx AS motivo,
    b.e5_filorig AS filial_origem,
    b.e5_lote AS lote,
    COALESCE((
        SELECT SUM(CASE WHEN fk6.fk6_acao = '1' THEN fk6.fk6_valmov ELSE -fk6.fk6_valmov END)
        FROM fk6
        WHERE COALESCE(fk6.d_e_l_e_t_, ' ') = ' '
          AND fk6.fk6_tpdoc = 'VA'
          AND fk6.fk6_filial = b.e5_filial
          AND (
                (b.e5_recpag = 'R' AND fk6.fk6_tabori = 'FK1' AND fk6.fk6_idorig IN (
                    SELECT fk1.fk1_idfk1 FROM fk1
                    WHERE fk1.fk1_filial = b.e5_filial AND fk1.fk1_idfk1 = b.e5_idorig AND COALESCE(fk1.d_e_l_e_t_, ' ') = ' '
                ))
             OR (b.e5_recpag = 'P' AND fk6.fk6_tabori = 'FK2' AND fk6.fk6_idorig IN (
                    SELECT fk2.fk2_idfk2 FROM fk2
                    WHERE fk2.fk2_filial = b.e5_filial AND fk2.fk2_idfk2 = b.e5_idorig AND COALESCE(fk2.d_e_l_e_t_, ' ') = ' '
                ))
          )
    ), 0) AS valor_acessorio
FROM baixas b
LEFT JOIN se1010 se1 ON b.e5_recpag = 'R' AND se1.e1_filial = b.e5_filial AND se1.e1_prefixo = b.e5_prefixo
    AND se1.e1_num = b.e5_numero AND se1.e1_parcela = b.e5_parcela AND se1.e1_tipo = b.e5_tipo
    AND se1.e1_cliente = b.e5_clifor AND se1.e1_loja = b.e5_loja
LEFT JOIN se2 se2 ON b.e5_recpag = 'P' AND se2.e2_filial = b.e5_filial AND se2.e2_prefixo = b.e5_prefixo
    AND se2.e2_num = b.e5_numero AND se2.e2_parcela = b.e5_parcela AND se2.e2_tipo = b.e5_tipo
    AND se2.e2_fornece = b.e5_clifor AND se2.e2_loja = b.e5_loja
LEFT JOIN sa1010 sa1 ON b.e5_recpag = 'R' AND sa1.a1_cod = b.e5_clifor AND sa1.a1_loja = b.e5_loja
LEFT JOIN sa2010 sa2 ON b.e5_recpag = 'P' AND sa2.a2_cod = b.e5_clifor AND sa2.a2_loja = b.e5_loja
LEFT JOIN sed010 sed ON sed.ed_codigo = b.e5_naturez
LEFT JOIN sa6010 sa6 ON sa6.a6_cod = b.e5_banco AND sa6.a6_agencia = b.e5_agencia AND sa6.a6_numcon = b.e5_conta
WHERE (
        :vencimento_ini = '' OR :vencimento_fim = ''
     OR (CASE WHEN b.e5_recpag = 'R' THEN se1.e1_vencrea ELSE se2.e2_vencrea END)::date
        BETWEEN NULLIF(:vencimento_ini, '')::date AND NULLIF(:vencimento_fim, '')::date
      )
ORDER BY __ORDEM__
"""

_CAMPOS_OPCIONAIS = (
    "tipo_movimento", "data_baixa_ini", "data_baixa_fim",
    "banco_ini", "banco_fim", "natureza_ini", "natureza_fim",
    "clifor_ini", "clifor_fim", "prefixo_ini", "prefixo_fim",
    "loja_ini", "loja_fim", "lote_ini", "lote_fim",
    "dt_digitacao_ini", "dt_digitacao_fim", "vencimento_ini", "vencimento_fim",
    "ordenar_por",
)

_TIPOS_ABATIMENTO_PADRAO = "AB|FA"


def _serializar(valor):
    if isinstance(valor, Decimal):
        return float(valor)
    return valor


def _buscar_baixas(filiais: list[str], opcionais: dict[str, str]) -> tuple[list[str], list[tuple]]:
    clausula_filial, binds_filial = clausula_in("filial", filiais)

    ordenar_por = opcionais.pop("ordenar_por", "") or "data_baixa"
    ordem_sql = _ORDENS.get(ordenar_por, _ORDENS["data_baixa"])

    opcionais.setdefault("tipo_movimento", "R")
    if opcionais["tipo_movimento"] not in ("R", "P"):
        opcionais["tipo_movimento"] = "R"

    opcionais["tipos_abatimento"] = _TIPOS_ABATIMENTO_PADRAO

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
    if not opcionais.get("data_baixa_ini") or not opcionais.get("data_baixa_fim"):
        return None

    return filiais, opcionais


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/relacao-baixas", methods=["GET", "OPTIONS"])
    async def listar_relacao_baixas_route(request: Request) -> JSONResponse:
        """RELATÓRIO: Relação de Baixas (FINR190) — endpoint JSON usado pela tela."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse({"erro": "Informe ao menos uma filial e a faixa de data da baixa."}, status_code=400, headers=CORS_HEADERS)

        colunas, linhas = _buscar_baixas(*parametros)
        dados = [dict(zip(colunas, (_serializar(valor) for valor in linha))) for linha in linhas]
        return JSONResponse(dados, headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/relacao-baixas/exportar", methods=["GET", "OPTIONS"])
    async def exportar_relacao_baixas_route(request: Request) -> Response:
        """RELATÓRIO: Relação de Baixas (FINR190) — exportação em Excel."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse({"erro": "Informe ao menos uma filial e a faixa de data da baixa."}, status_code=400, headers=CORS_HEADERS)

        colunas, linhas = _buscar_baixas(*parametros)
        conteudo_xlsx = gerar_xlsx(colunas, linhas, titulo="Relação de Baixas")
        return Response(
            content=conteudo_xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="relacao_baixas.xlsx"',
                **CORS_HEADERS,
            },
        )
