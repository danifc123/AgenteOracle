"""Rotas das telas de Previsão do Financeiro (Vendas e Fluxo de Caixa) — ver
`pages/modulos/financeiro/vendas` e `pages/modulos/financeiro/fluxo-caixa`
no frontend, que hoje consomem exatamente o shape de resposta usado aqui.

Toda a SQL agrupa por mês de um jeito portável entre Oracle e Postgres —
`TO_CHAR(coluna, 'YYYY-MM')` pras colunas DATE de verdade (`data_vencimento`
em vw_titulos_receber/vw_titulos_pagar), e `SUBSTR`/`||` pra `data_emissao`
de vw_faturamento, que vem como texto "YYYYMMDD" (convenção TOTVS), não como
DATE — nunca `FILTER (WHERE ...)` nem casts `::tipo`, que são exclusivos do
Postgres (ver aviso em `relatorios/fluxo_caixa_realizado.py`, que só roda com
DB_BACKEND=postgres por causa disso)."""

from datetime import date, timedelta

from ollama import AsyncClient
from starlette.requests import Request
from starlette.responses import JSONResponse

from agente_oracle.agent.financeiro.projecoes import gerar_analise, projetar_tendencia_linear, proximos_meses
from agente_oracle.config import settings
from agente_oracle.db.connection import get_connection
from agente_oracle.server.auth.dependencia import exigir_modulo_financeiro
from agente_oracle.server.cors import CORS_HEADERS, resposta_preflight
from agente_oracle.server.financeiro.relatorios import _comum
from agente_oracle.server.financeiro.relatorios.filtros_sql import clausula_in

_MESES_HISTORICO_VENDAS = 12
_MESES_PROJECAO_VENDAS = 3
_MESES_JANELA_FLUXO_CAIXA = 6
_DIAS_CORTE_PERIODO = 90


def _mes_menos(mes_referencia: str, quantidade: int) -> str:
    """Inverso de `proximos_meses`: rótulo "YYYY-MM" `quantidade` meses antes
    de `mes_referencia`."""
    ano, mes = (int(parte) for parte in mes_referencia.split("-"))
    total_meses = ano * 12 + (mes - 1) - quantidade
    ano_resultado, mes_resultado = divmod(total_meses, 12)
    return f"{ano_resultado:04d}-{mes_resultado + 1:02d}"


def _buscar_faturamento_mensal(filiais: list[str], mes_inicio: str) -> dict[str, float]:
    # `data_emissao` em vw_faturamento vem como texto "YYYYMMDD" (convenção
    # TOTVS de data em CHAR), não como DATE/TIMESTAMP — por isso usa SUBSTR
    # em vez de TO_CHAR aqui (SUBSTR/`||` funcionam igual em Oracle e
    # Postgres; TO_CHAR sobre uma coluna texto dá erro nos dois bancos).
    clausula_filial, binds_filial = clausula_in("filial", filiais)
    mes_expressao = "SUBSTR(data_emissao, 1, 4) || '-' || SUBSTR(data_emissao, 5, 2)"
    sql = f"""
        SELECT {mes_expressao} AS mes, SUM(valor_liquido) AS total
        FROM vw_faturamento
        WHERE filial IN {clausula_filial}
          AND {mes_expressao} >= :mes_inicio
        GROUP BY {mes_expressao}
    """
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, mes_inicio=mes_inicio, **binds_filial)
        linhas = cursor.fetchall()
    return {mes: _comum.serializar(total) for mes, total in linhas}


def _buscar_bucket_mensal(view: str, coluna_valor: str, filiais: list[str], hoje: date, mes_fim: str) -> dict[str, float]:
    clausula_filial, binds_filial = clausula_in("filial", filiais)
    sql = f"""
        SELECT
            CASE WHEN data_vencimento < :hoje THEN 'vencido' ELSE TO_CHAR(data_vencimento, 'YYYY-MM') END AS mes,
            SUM({coluna_valor}) AS total
        FROM {view}
        WHERE filial IN {clausula_filial}
          AND saldo_aberto > 0
          AND (data_vencimento < :hoje OR TO_CHAR(data_vencimento, 'YYYY-MM') <= :mes_fim)
        GROUP BY CASE WHEN data_vencimento < :hoje THEN 'vencido' ELSE TO_CHAR(data_vencimento, 'YYYY-MM') END
    """
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, hoje=hoje, mes_fim=mes_fim, **binds_filial)
        linhas = cursor.fetchall()
    return {mes: _comum.serializar(total) for mes, total in linhas}


def _buscar_corte_periodo(view: str, filiais: list[str], data_corte: date) -> tuple[float, float]:
    clausula_filial, binds_filial = clausula_in("filial", filiais)
    sql = f"""
        SELECT
            SUM(CASE WHEN data_vencimento <= :data_corte THEN saldo_aberto ELSE 0 END) AS no_periodo,
            SUM(CASE WHEN data_vencimento > :data_corte THEN saldo_aberto ELSE 0 END) AS fora_periodo
        FROM {view}
        WHERE filial IN {clausula_filial} AND saldo_aberto > 0
    """
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, data_corte=data_corte, **binds_filial)
        no_periodo, fora_periodo = cursor.fetchone()
    return _comum.serializar(no_periodo) or 0.0, _comum.serializar(fora_periodo) or 0.0


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/previsao/vendas", methods=["GET", "OPTIONS"])
    async def previsao_vendas_route(request: Request) -> JSONResponse:
        """Faturamento dos últimos 12 meses + projeção dos próximos 3 por
        regressão linear + análise curta da IA em cima desses números."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_modulo_financeiro(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        filiais = _comum.filiais_da_query(request)
        if filiais is None:
            return JSONResponse({"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS)

        mes_atual = date.today().strftime("%Y-%m")
        meses_historico = [mes_atual, *[_mes_menos(mes_atual, passo) for passo in range(1, _MESES_HISTORICO_VENDAS)]]
        meses_historico.reverse()

        faturamento_por_mes = _buscar_faturamento_mensal(filiais, meses_historico[0])
        historico = [{"mes": mes, "valor": faturamento_por_mes.get(mes, 0.0)} for mes in meses_historico]

        valores_projetados = projetar_tendencia_linear([item["valor"] for item in historico], _MESES_PROJECAO_VENDAS)
        meses_projecao = proximos_meses(mes_atual, _MESES_PROJECAO_VENDAS)
        projecao = [{"mes": mes, "valor": valor} for mes, valor in zip(meses_projecao, valores_projetados)]

        contexto = (
            "Faturamento mensal dos últimos "
            f"{len(historico)} meses: "
            + ", ".join(f"{item['mes']}: R$ {item['valor']:.2f}" for item in historico)
            + ". Projeção (regressão linear) para os próximos meses: "
            + ", ".join(f"{item['mes']}: R$ {item['valor']:.2f}" for item in projecao)
            + "."
        )
        analise = await gerar_analise(AsyncClient(host=settings.ollama_host), settings.ollama_model, contexto)

        return JSONResponse({"historico": historico, "projecao": projecao, "analise": analise}, headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/previsao/fluxo-caixa", methods=["GET", "OPTIONS"])
    async def previsao_fluxo_caixa_route(request: Request) -> JSONResponse:
        """Títulos em aberto (a receber/a pagar): bucket mensal (vencido +
        próximos 6 meses) pro gráfico de barras, totais gerais e o corte de
        90 dias (no período / fora do período) pros donuts — tudo dado real
        já lançado, sem IA nem regressão envolvida. A análise da IA só narra
        esses números prontos."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_modulo_financeiro(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        filiais = _comum.filiais_da_query(request)
        if filiais is None:
            return JSONResponse({"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS)

        hoje = date.today()
        mes_atual = hoje.strftime("%Y-%m")
        meses_janela = [mes_atual, *proximos_meses(mes_atual, _MESES_JANELA_FLUXO_CAIXA - 1)]
        data_corte = hoje + timedelta(days=_DIAS_CORTE_PERIODO)

        bucket_receber = _buscar_bucket_mensal("vw_titulos_receber", "saldo_aberto", filiais, hoje, meses_janela[-1])
        bucket_pagar = _buscar_bucket_mensal("vw_titulos_pagar", "saldo_aberto", filiais, hoje, meses_janela[-1])
        meses = [
            {
                "mes": mes,
                "a_receber": bucket_receber.get(mes, 0.0),
                "a_pagar": bucket_pagar.get(mes, 0.0),
            }
            for mes in ["vencido", *meses_janela]
        ]

        receber_no_periodo, receber_fora_periodo = _buscar_corte_periodo("vw_titulos_receber", filiais, data_corte)
        pagar_no_periodo, pagar_fora_periodo = _buscar_corte_periodo("vw_titulos_pagar", filiais, data_corte)

        contexto = (
            f"Títulos a receber em aberto: R$ {receber_no_periodo + receber_fora_periodo:.2f} no total, sendo "
            f"R$ {receber_no_periodo:.2f} com vencimento nos próximos {_DIAS_CORTE_PERIODO} dias. "
            f"Títulos a pagar em aberto: R$ {pagar_no_periodo + pagar_fora_periodo:.2f} no total, sendo "
            f"R$ {pagar_no_periodo:.2f} com vencimento nos próximos {_DIAS_CORTE_PERIODO} dias. "
            f"Já vencido e ainda em aberto: R$ {meses[0]['a_receber']:.2f} a receber e "
            f"R$ {meses[0]['a_pagar']:.2f} a pagar."
        )
        analise = await gerar_analise(AsyncClient(host=settings.ollama_host), settings.ollama_model, contexto)

        return JSONResponse(
            {
                "meses": meses,
                "total_a_receber": receber_no_periodo + receber_fora_periodo,
                "total_a_pagar": pagar_no_periodo + pagar_fora_periodo,
                "fatias_a_receber": [
                    {"nome": "No período", "valor": receber_no_periodo},
                    {"nome": "Fora do período", "valor": receber_fora_periodo},
                ],
                "fatias_a_pagar": [
                    {"nome": "No período", "valor": pagar_no_periodo},
                    {"nome": "Fora do período", "valor": pagar_fora_periodo},
                ],
                "analise": analise,
            },
            headers=CORS_HEADERS,
        )
