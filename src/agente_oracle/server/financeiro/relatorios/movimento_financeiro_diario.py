"""RELATÓRIO: Resumo Bancário / Movimento Financeiro Diário (FINR530)

Tradução do ADVPL (`FINR530.PRW`) — para uma data de referência única
(`MV_PAR01`), lista, por conta bancária (`SA6010`), o saldo inicial, as
entradas, as saídas, as aplicações financeiras do dia e o saldo disponível
resultante. É o "resumo do dia" — prima do FINR470/Extrato Bancário
(`extrato_bancario.py`), que lista o extrato linha a linha; aqui é só o
totalizador por conta, para uma data só.

Igual ao FINR470, o saldo inicial no ADVPL original vem de um snapshot
(`SE8`, "Saldos Bancários", lido com `E8_SALATUA`/`DbSkip(-1)` pra pegar o
saldo do dia anterior) — essa tabela não existe nesse banco fictício, então
reconstruímos a partir do próprio histórico de `SE5010` (soma de tudo antes
da data de referência), mesma substituição documentada lá.

O que ficou de fora (documentado, não é atalho silencioso):
- Multi-moeda (`MV_PAR02`/`MV_PAR04`, `xMoeda`/`RecMoeda`) — banco de teste é
  mono-moeda (BRL), mesma simplificação do FINR470.
- Gestão Corporativa multi-empresa (toda a lógica de `FWModeAccess`/
  `cMAEmp*`/`cMAUni*`/`cMAFil*`/`lSE5Compar`/`lSE8Compar`/`lSA6Compar`, que
  decide como cruzar SA6/SE5/SE8 quando essas tabelas são compartilhadas
  entre empresas/unidades de negócio) — Grupo Conceito é filial única;
  usamos o mesmo seletor de filial multi-select dos outros relatórios.
- Caixa de loja (`MV_CXLJFIN`/`IsCaixaLoja()`) e o tratamento fino de
  transferência (TR/TE) por numerário/moeda (`SX5` tabela "14", cheques com
  "*" de prefixo) — módulos de varejo/tesouraria não usados pelo Grupo
  Conceito (distribuidor agro, sem PDV).
- `E5_MOTBX`/`MovBcoBx()` — função externa que decide se um motivo de baixa
  específico exclui o lançamento; não temos a fórmula real nem uma tabela de
  motivos nesse banco de teste, então não filtramos por ela (mesmo tipo de
  gap documentado do `Fa080Juros()` no FINR150 — inventar o critério
  pareceria fiel mas estaria errado).

O que TEM fidelidade real:
- Filtro de data de referência (obrigatório) — o campo é uma faixa na tela
  (`periodo-data`, como os outros relatórios), mas só a data inicial é usada
  como referência, igual ao MV_PAR01 original (que é uma data única, não uma
  faixa).
- "Considera Limite de Crédito" (`MV_PAR03`/`A6_LIMCRED`) — soma o limite de
  crédito da conta ao saldo inicial quando ligado.
- Exclui os mesmos tipos de documento que não são movimentação bancária real
  (`E5_TIPODOC NOT IN (...)`, valor zero, situação cancelada) — mesma lista
  do FINR470 (`Fr530Skip`/`_TIPODOC_EXCLUIDOS_IN`).
- **Aplicações financeiras** tratadas à parte: título com `E5_TIPODOC='AP'`
  soma ao total de aplicações quando é uma saída de caixa (`E5_RECPAG='P'`,
  dinheiro indo para a aplicação) e subtrai quando é uma entrada
  (`E5_RECPAG='R'`, resgate) — mesma lógica do bloco `IF/ELSE` do ADVPL
  original. Aplicações não entram nos totais de entradas/saídas comuns.
- **Saldo disponível** = saldo inicial (+ limite de crédito, se marcado) +
  entradas - saídas - aplicações — mesma fórmula do `nDisponiv` original.

Atenção: só roda com DB_BACKEND=postgres (cast ::date). Datas em SE5010
nesse banco de teste são VARCHAR (formato "YYYYMMDD").
"""

from decimal import Decimal

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.db.connection import get_connection
from agente_oracle.relatorios import gerar_xlsx
from agente_oracle.server.auth.dependencia import exigir_usuario
from agente_oracle.server.cors import CORS_HEADERS, resposta_preflight
from agente_oracle.server.financeiro.relatorios.filtros_sql import clausula_in

# Mesma lista do FINR470 (Fr530Skip/_TIPODOC_EXCLUIDOS_IN): tipos de
# documento que são baixas de título, não movimentação bancária real.
_TIPODOC_EXCLUIDOS_IN = "('DC','JR','MT','CM','D2','J2','M2','V2','C2','CP','TL','BA','I2','EI','VA')"

_QUERY = """
-- =====================================================================
-- RELATORIO: Resumo Bancario / Movimento Financeiro Diario (FINR530)
-- versao simplificada (sem multi-moeda/Gestao Corporativa/caixa de loja)
-- =====================================================================
WITH contas AS (
    SELECT sa6.a6_filial, sa6.a6_cod, sa6.a6_agencia, sa6.a6_numcon, sa6.a6_nreduz,
           COALESCE(sa6.a6_limcred, 0) AS a6_limcred
    FROM sa6010 sa6
    WHERE COALESCE(sa6.d_e_l_e_t_, ' ') = ' '
      AND TRIM(sa6.a6_filial) IN __FILIAL_IN__
),
saldo_inicial AS (
    SELECT c.a6_cod, c.a6_agencia, c.a6_numcon,
        COALESCE(SUM(CASE WHEN se5.e5_recpag = 'R' THEN se5.e5_valor ELSE -se5.e5_valor END), 0) AS valor
    FROM contas c
    LEFT JOIN se5010 se5
        ON se5.e5_banco = c.a6_cod AND se5.e5_agencia = c.a6_agencia AND se5.e5_conta = c.a6_numcon
       AND COALESCE(se5.d_e_l_e_t_, ' ') = ' '
       AND TRIM(se5.e5_filial) IN __FILIAL_IN__
       AND se5.e5_dtdispo::date < :data_ini::date
       AND se5.e5_valor <> 0
       AND COALESCE(se5.e5_situaca, ' ') <> 'C'
       AND se5.e5_tipodoc NOT IN __TIPODOC_EXCLUIDOS__
    GROUP BY c.a6_cod, c.a6_agencia, c.a6_numcon
),
movimento_dia AS (
    SELECT c.a6_cod, c.a6_agencia, c.a6_numcon,
        COALESCE(SUM(CASE WHEN se5.e5_recpag = 'R' AND se5.e5_tipodoc <> 'AP' THEN se5.e5_valor ELSE 0 END), 0) AS entradas,
        COALESCE(SUM(CASE WHEN se5.e5_recpag = 'P' AND se5.e5_tipodoc <> 'AP' THEN se5.e5_valor ELSE 0 END), 0) AS saidas,
        COALESCE(SUM(
            CASE WHEN se5.e5_tipodoc = 'AP'
                THEN CASE WHEN se5.e5_recpag = 'P' THEN se5.e5_valor ELSE -se5.e5_valor END
                ELSE 0
            END
        ), 0) AS aplicacoes
    FROM contas c
    LEFT JOIN se5010 se5
        ON se5.e5_banco = c.a6_cod AND se5.e5_agencia = c.a6_agencia AND se5.e5_conta = c.a6_numcon
       AND COALESCE(se5.d_e_l_e_t_, ' ') = ' '
       AND TRIM(se5.e5_filial) IN __FILIAL_IN__
       AND se5.e5_dtdispo::date = :data_ini::date
       AND se5.e5_valor <> 0
       AND COALESCE(se5.e5_situaca, ' ') <> 'C'
       AND se5.e5_tipodoc NOT IN __TIPODOC_EXCLUIDOS__
    GROUP BY c.a6_cod, c.a6_agencia, c.a6_numcon
)
SELECT
    c.a6_cod,
    c.a6_agencia,
    c.a6_numcon,
    c.a6_nreduz,
    (
        COALESCE(si.valor, 0)
        + CASE WHEN :considera_limite = '1' THEN c.a6_limcred ELSE 0 END
    ) AS saldo_inicial,
    COALESCE(md.entradas, 0) AS entradas,
    COALESCE(md.saidas, 0) AS saidas,
    COALESCE(md.aplicacoes, 0) AS aplicacoes,
    (
        COALESCE(si.valor, 0)
        + CASE WHEN :considera_limite = '1' THEN c.a6_limcred ELSE 0 END
        + COALESCE(md.entradas, 0) - COALESCE(md.saidas, 0) - COALESCE(md.aplicacoes, 0)
    ) AS saldo_disponivel
FROM contas c
LEFT JOIN saldo_inicial si ON si.a6_cod = c.a6_cod AND si.a6_agencia = c.a6_agencia AND si.a6_numcon = c.a6_numcon
LEFT JOIN movimento_dia md ON md.a6_cod = c.a6_cod AND md.a6_agencia = c.a6_agencia AND md.a6_numcon = c.a6_numcon
ORDER BY c.a6_cod, c.a6_agencia, c.a6_numcon
"""

_CAMPOS_OPCIONAIS = ("data_ini", "data_fim", "considera_limite")


def _serializar(valor):
    if isinstance(valor, Decimal):
        return float(valor)
    return valor


def _buscar_movimento(filiais: list[str], opcionais: dict[str, str]) -> tuple[list[str], list[tuple]]:
    clausula_filial, binds_filial = clausula_in("filial", filiais)

    opcionais.pop("data_fim", None)
    opcionais.setdefault("considera_limite", "2")

    sql = _QUERY.replace("__FILIAL_IN__", clausula_filial).replace("__TIPODOC_EXCLUIDOS__", _TIPODOC_EXCLUIDOS_IN)

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
    if not opcionais.get("data_ini"):
        return None

    return filiais, opcionais


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/movimento-financeiro-diario", methods=["GET", "OPTIONS"])
    async def listar_movimento_financeiro_diario_route(request: Request) -> JSONResponse:
        """RELATÓRIO: Resumo Bancário / Movimento Financeiro Diário (FINR530) — endpoint JSON usado pela tela."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse({"erro": "Informe filial e a data de referência."}, status_code=400, headers=CORS_HEADERS)

        colunas, linhas = _buscar_movimento(*parametros)
        dados = [dict(zip(colunas, (_serializar(valor) for valor in linha))) for linha in linhas]
        return JSONResponse(dados, headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/movimento-financeiro-diario/exportar", methods=["GET", "OPTIONS"])
    async def exportar_movimento_financeiro_diario_route(request: Request) -> Response:
        """RELATÓRIO: Resumo Bancário / Movimento Financeiro Diário (FINR530) — exportação em Excel."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_usuario(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        parametros = _parametros_da_query(request)
        if parametros is None:
            return JSONResponse({"erro": "Informe filial e a data de referência."}, status_code=400, headers=CORS_HEADERS)

        colunas, linhas = _buscar_movimento(*parametros)
        conteudo_xlsx = gerar_xlsx(colunas, linhas, titulo="Resumo Bancário / Movimento Financeiro Diário")
        return Response(
            content=conteudo_xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="movimento_financeiro_diario.xlsx"',
                **CORS_HEADERS,
            },
        )
