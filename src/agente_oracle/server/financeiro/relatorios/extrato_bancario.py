"""RELATÓRIO: Extrato Bancário (FINR470)

Tradução do ADVPL (`FINR470.PRW`) — lista as movimentações de `SE5010`
("Movimento Bancário") de uma conta bancária específica (banco+agência+
conta) dentro de uma faixa de data de disponibilidade (E5_DTDISPO), com
saldo corrente linha a linha, igual a um extrato de banco de verdade.

O que ficou de fora (documentado, não é atalho silencioso):
- Multi-moeda com taxa de conversão histórica (MV_PAR06/09/12) — banco de
  teste é mono-moeda (BRL).
- SPB (Sistema de Pagamentos Brasileiro, janela alternativa de datas) e o
  desvio específico para Argentina (`FinModProc`) — módulos não aplicáveis.
- Gestão Corporativa multi-empresa (`AdmGetFil`/`FinSelFil`) — Grupo
  Conceito é single empresa/filial; ainda assim aceitamos filial
  multi-select, igual aos outros relatórios.
- Quebra de página por "linhas por página" (MV_PAR08) — conceito de
  relatório impresso paginado, não se aplica a uma tabela JSON/Excel.
- Os totalizadores de rodapé do relatório original (Saldo Inicial /
  Recebimentos conciliados e não conciliados / Pagamentos conciliados e
  não conciliados / Limite de Crédito / Saldo Final) não são replicados
  como linhas separadas — mesma decisão já tomada no FINR190: nosso
  resultado é uma tabela plana, não um relatório paginado com quebras. O
  **saldo corrente por linha** (que é o cerne de um extrato) fica, sim,
  100% real.

O que TEM fidelidade real:
- Filtro de conta bancária exata (banco+agência+conta, igual ao
  `SA6->(DbSeek(...))` original) + faixa de data de disponibilidade
  (E5_DTDISPO, obrigatória) + filtro de conciliação (`saldo_tipo`,
  equivalente a MV_PAR07: 1=Saldo Atual/todos, 2=só conciliados,
  3=só não conciliados).
- Exclui os mesmos tipos de documento que não são movimentação bancária de
  verdade (`E5_TIPODOC NOT IN (...)`, valor zero, situação cancelada) —
  mesma lista do ADVPL original.
- **Saldo corrente real**, calculado com `SUM() OVER (ORDER BY ...)` —
  window function do Postgres, equivalente ao acumulador `nSaldoAtu` do
  laço ADVPL original.
- **Saldo inicial reconstruído** a partir do próprio histórico de
  SE5010 (soma de todas as movimentações anteriores à data inicial da
  faixa, com os mesmos filtros). O ADVPL original lê isso de um snapshot
  periódico (`SE8`, "Saldos Bancários") — essa tabela não existe no banco
  fictício (não há como confirmar se o Grupo Conceito sequer usa esse
  módulo), então reconstruímos do zero a partir da movimentação real em
  vez de usar um valor pré-calculado. Resultado idêntico quando não há
  gaps de histórico antes do range consultado.
- **Identificação do documento/título por linha**: número de cheque ou
  documento (`E5_NUMCHEQ`/`E5_DOCUMEN`) e o título vinculado
  (prefixo-número-parcela), com o mesmo desvio para `SEF` (cheques
  avulsos) quando `E5_TIPODOC='CH'`.

Atenção: só roda com DB_BACKEND=postgres (cast ::date). Datas em SE5010
nesse banco de teste são VARCHAR (formato "YYYYMMDD").
"""

from decimal import Decimal

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.db.connection import get_connection
from agente_oracle.relatorios import gerar_xlsx
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.server.financeiro.relatorios.filtros_sql import clausula_in

_TIPODOC_EXCLUIDOS_IN = "('DC','JR','MT','CM','D2','J2','M2','V2','C2','CP','TL','BA','I2','EI','VA')"

_QUERY = """
-- =====================================================================
-- RELATORIO: Extrato Bancario (FINR470) — versao simplificada
-- (sem multi-moeda/SPB/Gestao Corporativa/quebra de pagina)
-- =====================================================================
WITH saldo_inicial AS (
    SELECT COALESCE(SUM(CASE WHEN se5.e5_recpag = 'R' THEN se5.e5_valor ELSE -se5.e5_valor END), 0) AS valor
    FROM se5010 se5
    WHERE se5.e5_banco = :banco AND se5.e5_agencia = :agencia AND se5.e5_conta = :conta
      AND COALESCE(se5.d_e_l_e_t_, ' ') = ' '
      AND TRIM(se5.e5_filial) IN __FILIAL_IN__
      AND se5.e5_dtdispo::date < :data_ini::date
      AND se5.e5_valor <> 0
      AND COALESCE(se5.e5_situaca, ' ') <> 'C'
      AND se5.e5_tipodoc NOT IN __TIPODOC_EXCLUIDOS__
      AND (:saldo_tipo <> '2' OR COALESCE(se5.e5_reconc, '') <> '')
      AND (:saldo_tipo <> '3' OR COALESCE(se5.e5_reconc, '') = '')
),
movimentos AS (
    SELECT
        se5.r_e_c_n_o_,
        se5.e5_filial, se5.e5_dtdispo, se5.e5_histor, se5.e5_documen, se5.e5_numcheq,
        se5.e5_prefixo, se5.e5_numero, se5.e5_parcela, se5.e5_tipodoc, se5.e5_recpag,
        se5.e5_valor,
        (COALESCE(se5.e5_reconc, '') <> '') AS conciliado,
        CASE WHEN se5.e5_recpag = 'R' THEN se5.e5_valor ELSE 0 END AS valor_entrada,
        CASE WHEN se5.e5_recpag = 'P' THEN se5.e5_valor ELSE 0 END AS valor_saida
    FROM se5010 se5
    WHERE se5.e5_banco = :banco AND se5.e5_agencia = :agencia AND se5.e5_conta = :conta
      AND COALESCE(se5.d_e_l_e_t_, ' ') = ' '
      AND TRIM(se5.e5_filial) IN __FILIAL_IN__
      AND se5.e5_dtdispo::date BETWEEN :data_ini::date AND :data_fim::date
      AND se5.e5_valor <> 0
      AND COALESCE(se5.e5_situaca, ' ') <> 'C'
      AND se5.e5_tipodoc NOT IN __TIPODOC_EXCLUIDOS__
      AND (:saldo_tipo <> '2' OR COALESCE(se5.e5_reconc, '') <> '')
      AND (:saldo_tipo <> '3' OR COALESCE(se5.e5_reconc, '') = '')
)
SELECT
    m.e5_dtdispo AS data_disponivel,
    m.e5_histor AS historico,
    COALESCE(NULLIF(m.e5_numcheq, ''), m.e5_documen) AS documento,
    CASE
        WHEN m.e5_tipodoc = 'CH' THEN (
            SELECT TRIM(sef.ef_prefixo) || '-' || TRIM(sef.ef_titulo) || '-' || TRIM(sef.ef_parcela)
            FROM sef
            WHERE sef.ef_num = m.e5_numcheq AND sef.ef_banco = :banco AND sef.ef_agencia = :agencia AND sef.ef_conta = :conta
              AND COALESCE(sef.d_e_l_e_t_, ' ') = ' ' AND COALESCE(sef.ef_tipo, '') <> ''
            LIMIT 1
        )
        ELSE TRIM(m.e5_prefixo) || '-' || TRIM(m.e5_numero) || '-' || TRIM(m.e5_parcela)
    END AS titulo,
    m.valor_entrada,
    m.valor_saida,
    (
        (SELECT valor FROM saldo_inicial)
        + SUM(m.valor_entrada - m.valor_saida) OVER (ORDER BY m.e5_dtdispo, m.r_e_c_n_o_ ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
    ) AS saldo_atual,
    m.conciliado
FROM movimentos m
ORDER BY m.e5_dtdispo, m.r_e_c_n_o_
"""

_CAMPOS_OPCIONAIS = ("banco", "agencia", "conta", "data_ini", "data_fim", "saldo_tipo")


def _serializar(valor):
    if isinstance(valor, Decimal):
        return float(valor)
    return valor


def _buscar_extrato(filiais: list[str], opcionais: dict[str, str]) -> tuple[list[str], list[tuple]]:
    clausula_filial, binds_filial = clausula_in("filial", filiais)

    opcionais.setdefault("saldo_tipo", "1")

    sql = (
        _QUERY.replace("__FILIAL_IN__", clausula_filial)
        .replace("__TIPODOC_EXCLUIDOS__", _TIPODOC_EXCLUIDOS_IN)
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

    conta_bancaria = request.query_params.get("conta_bancaria", "").strip()
    partes = conta_bancaria.split("|")
    if len(partes) != 3 or not all(partes):
        return None

    opcionais = {chave: request.query_params.get(chave, "").strip() for chave in _CAMPOS_OPCIONAIS if chave not in ("banco", "agencia", "conta")}
    opcionais["banco"], opcionais["agencia"], opcionais["conta"] = partes

    if not opcionais.get("data_ini") or not opcionais.get("data_fim"):
        return None

    return filiais, opcionais


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/extrato-bancario", methods=["GET"])
    async def listar_extrato_bancario_route(request: Request) -> JSONResponse:
        """RELATÓRIO: Extrato Bancário (FINR470) — endpoint JSON usado pela tela."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse({"erro": "Informe filial, conta bancária e a faixa de data."}, status_code=400, headers=CORS_HEADERS)

        colunas, linhas = _buscar_extrato(*parametros)
        dados = [dict(zip(colunas, (_serializar(valor) for valor in linha))) for linha in linhas]
        return JSONResponse(dados, headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/extrato-bancario/exportar", methods=["GET"])
    async def exportar_extrato_bancario_route(request: Request) -> Response:
        """RELATÓRIO: Extrato Bancário (FINR470) — exportação em Excel."""
        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse({"erro": "Informe filial, conta bancária e a faixa de data."}, status_code=400, headers=CORS_HEADERS)

        colunas, linhas = _buscar_extrato(*parametros)
        conteudo_xlsx = gerar_xlsx(colunas, linhas, titulo="Extrato Bancário")
        return Response(
            content=conteudo_xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="extrato_bancario.xlsx"',
                **CORS_HEADERS,
            },
        )

