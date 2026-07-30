"""Rotas das telas de Previsão do Financeiro (Vendas e Fluxo de Caixa) — ver
`pages/modulos/financeiro/vendas` e `pages/modulos/financeiro/fluxo-caixa`
no frontend, que hoje consomem exatamente o shape de resposta usado aqui.

Toda a SQL agrupa por mês/calcula prazo de um jeito portável entre Oracle e
Postgres — `TO_CHAR(coluna, 'YYYY-MM')` pras colunas DATE de verdade
(`data_vencimento`/`data_emissao` em vw_titulos_receber/vw_titulos_pagar),
`SUBSTR`/`||` pra `data_emissao` de vw_faturamento (texto "YYYYMMDD",
convenção TOTVS, não DATE) e `TO_DATE(coluna, 'YYYYMMDD')` quando essa mesma
coluna texto precisa entrar numa subtração de datas — nunca `FILTER (WHERE
...)` nem casts `::tipo`, que são exclusivos do Postgres (ver aviso em
`relatorios/fluxo_caixa_realizado.py`, que só roda com DB_BACKEND=postgres
por causa disso).

As duas rotas respondem em NDJSON (uma linha JSON por etapa concluída,
terminando em `{"tipo": "resultado", "dados": {...}}`) em vez de um JSON
único — a geração da previsão do Fluxo de Caixa envolve várias consultas
mais a chamada de IA no fim, e o frontend usa esse streaming pra mostrar o
progresso real em vez de um "carregando" genérico parado."""

import json
from datetime import date, timedelta

from ollama import AsyncClient
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from agente_oracle.agent.financeiro.projecoes import gerar_analise, projetar_tendencia_linear, proximos_meses
from agente_oracle.config import settings
from agente_oracle.db.connection import get_connection
from agente_oracle.server.auth.dependencia import exigir_modulo_financeiro
from agente_oracle.server.cors import CORS_HEADERS, resposta_preflight
from agente_oracle.server.financeiro.relatorios import _comum
from agente_oracle.server.financeiro.relatorios.filtros_sql import clausula_in

_MESES_HISTORICO = 12
_MESES_PROJECAO = 3
_MESES_JANELA_FLUXO_CAIXA = 6
_DIAS_CORTE_PERIODO = 90
_PRAZO_MEDIO_PADRAO_DIAS = 30.0


def _linha_ndjson(objeto: dict) -> str:
    return json.dumps(objeto, ensure_ascii=False) + "\n"


def _mes_menos(mes_referencia: str, quantidade: int) -> str:
    """Inverso de `proximos_meses`: rótulo "YYYY-MM" `quantidade` meses antes
    de `mes_referencia`."""
    ano, mes = (int(parte) for parte in mes_referencia.split("-"))
    total_meses = ano * 12 + (mes - 1) - quantidade
    ano_resultado, mes_resultado = divmod(total_meses, 12)
    return f"{ano_resultado:04d}-{mes_resultado + 1:02d}"


def _janela_meses_historico(quantidade: int) -> list[str]:
    """Os `quantidade` rótulos "YYYY-MM" mais recentes, em ordem crescente,
    terminando no mês atual — janela usada tanto pro histórico de
    faturamento (Vendas) quanto pro histórico de novos títulos a pagar."""
    mes_atual = date.today().strftime("%Y-%m")
    meses = [mes_atual, *[_mes_menos(mes_atual, passo) for passo in range(1, quantidade)]]
    meses.reverse()
    return meses


def _historico_e_projecao(
    valores_por_mes: dict[str, float], meses_historico: list[str], meses_futuros: int
) -> tuple[list[dict], list[dict]]:
    """Monta a série histórica (preenchendo meses sem dado com 0) e projeta
    `meses_futuros` à frente por regressão linear — usada tanto pro
    faturamento (Vendas) quanto pros novos títulos a pagar (Fluxo de Caixa)."""
    historico = [{"mes": mes, "valor": valores_por_mes.get(mes, 0.0)} for mes in meses_historico]
    valores_projetados = projetar_tendencia_linear([item["valor"] for item in historico], meses_futuros)
    meses_projecao = proximos_meses(meses_historico[-1], meses_futuros)
    projecao = [{"mes": mes, "valor": valor} for mes, valor in zip(meses_projecao, valores_projetados)]
    return historico, projecao


def _distribuir_estimativa(projecao: list[dict], deslocamento_meses: int, meses_janela: list[str]) -> dict[str, float]:
    """Desloca cada mês projetado em `deslocamento_meses` (aproximação de
    prazo médio em dias -> meses, uma simplificação de MVP, não uma
    simulação dia-a-dia) e soma no mês de destino, descartando o que cair
    fora de `meses_janela`. Função pura, sem I/O."""
    janela = set(meses_janela)
    estimativa: dict[str, float] = {}
    for item in projecao:
        mes_destino = proximos_meses(item["mes"], deslocamento_meses)[-1] if deslocamento_meses > 0 else item["mes"]
        if mes_destino in janela:
            estimativa[mes_destino] = estimativa.get(mes_destino, 0.0) + item["valor"]
    return estimativa


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


def _buscar_titulos_pagar_mensal(filiais: list[str], mes_inicio: str) -> dict[str, float]:
    # Diferente de vw_faturamento, `data_emissao` aqui já é DATE de verdade
    # (confirmado contra o Postgres de teste) — TO_CHAR direto funciona.
    clausula_filial, binds_filial = clausula_in("filial", filiais)
    sql = f"""
        SELECT TO_CHAR(data_emissao, 'YYYY-MM') AS mes, SUM(valor_original) AS total
        FROM vw_titulos_pagar
        WHERE filial IN {clausula_filial}
          AND TO_CHAR(data_emissao, 'YYYY-MM') >= :mes_inicio
        GROUP BY TO_CHAR(data_emissao, 'YYYY-MM')
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


def _prazo_medio_recebimento_dias(filiais: list[str]) -> float:
    """Média de dias entre a emissão da nota fiscal (vw_faturamento) e o
    vencimento do título que ela gerou (vw_titulos_receber, tipo='NF'),
    usando o relacionamento declarado em `agent/financeiro/schema.py`.
    `TO_DATE(..., 'YYYYMMDD')` converte o texto de data_emissao pra DATE de
    verdade — subtração entre DATEs devolve dias direto, sem função de
    date-diff especial, portável entre Oracle e Postgres."""
    clausula_filial, binds_filial = clausula_in("filial", filiais)
    sql = f"""
        WITH notas AS (
            SELECT DISTINCT filial, nota_fiscal, serie, cliente_codigo, cliente_loja,
                   TO_DATE(data_emissao, 'YYYYMMDD') AS data_emissao
            FROM vw_faturamento
            WHERE filial IN {clausula_filial}
        )
        SELECT AVG(t.data_vencimento - n.data_emissao)
        FROM vw_titulos_receber t
        JOIN notas n
          ON t.filial = n.filial
         AND t.numero = n.nota_fiscal
         AND t.prefixo = n.serie
         AND t.cliente_codigo = n.cliente_codigo
         AND t.cliente_loja = n.cliente_loja
        WHERE t.tipo = 'NF' AND t.filial IN {clausula_filial}
    """
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, **binds_filial)
        (media,) = cursor.fetchone()
    media_serializada = _comum.serializar(media)
    return float(media_serializada) if media_serializada is not None else _PRAZO_MEDIO_PADRAO_DIAS


def _prazo_medio_pagamento_dias(filiais: list[str]) -> float:
    """Média de dias entre emissão e vencimento dos títulos a pagar — aqui
    os dois campos já são DATE de verdade na própria view, sem precisar de
    join com nenhuma outra (não existe view de compras/pedido de compra no
    sistema pra comparar)."""
    clausula_filial, binds_filial = clausula_in("filial", filiais)
    sql = f"""
        SELECT AVG(data_vencimento - data_emissao)
        FROM vw_titulos_pagar
        WHERE filial IN {clausula_filial}
    """
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, **binds_filial)
        (media,) = cursor.fetchone()
    media_serializada = _comum.serializar(media)
    return float(media_serializada) if media_serializada is not None else _PRAZO_MEDIO_PADRAO_DIAS


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/previsao/vendas", methods=["GET", "OPTIONS"])
    async def previsao_vendas_route(request: Request) -> Response:
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

        async def gerador():
            meses_historico = _janela_meses_historico(_MESES_HISTORICO)
            faturamento_por_mes = _buscar_faturamento_mensal(filiais, meses_historico[0])
            historico, projecao = _historico_e_projecao(faturamento_por_mes, meses_historico, _MESES_PROJECAO)
            yield _linha_ndjson({"tipo": "etapa", "id": "historico"})
            yield _linha_ndjson({"tipo": "etapa", "id": "projecao"})

            contexto = (
                "Faturamento mensal dos últimos "
                f"{len(historico)} meses: "
                + ", ".join(f"{item['mes']}: R$ {item['valor']:.2f}" for item in historico)
                + ". Projeção (regressão linear) para os próximos meses: "
                + ", ".join(f"{item['mes']}: R$ {item['valor']:.2f}" for item in projecao)
                + "."
            )
            analise = await gerar_analise(AsyncClient(host=settings.ollama_host), settings.ollama_model, contexto)
            yield _linha_ndjson({"tipo": "etapa", "id": "analise_ia"})

            yield _linha_ndjson(
                {"tipo": "resultado", "dados": {"historico": historico, "projecao": projecao, "analise": analise}}
            )

        return StreamingResponse(gerador(), media_type="application/x-ndjson", headers=CORS_HEADERS)

    @mcp.custom_route("/api/financeiro/previsao/fluxo-caixa", methods=["GET", "OPTIONS"])
    async def previsao_fluxo_caixa_route(request: Request) -> Response:
        """Títulos em aberto (a receber/a pagar): bucket mensal (vencido +
        próximos 6 meses) pro gráfico, totais + corte de 90 dias pros
        donuts — tudo dado real já lançado. Em cima disso, soma uma
        estimativa do que ainda vai virar título (venda projetada
        convertida em caixa pelo prazo médio de recebimento; tendência
        histórica de novas contas a pagar) — só o "*_estimado" carrega essa
        parte; os campos sem sufixo continuam sendo só o confirmado, como
        antes. A IA só narra os números prontos, nunca calcula nada disso."""
        if request.method == "OPTIONS":
            return resposta_preflight("GET, OPTIONS")

        usuario_ou_erro = exigir_modulo_financeiro(request)
        if isinstance(usuario_ou_erro, JSONResponse):
            return usuario_ou_erro

        filiais = _comum.filiais_da_query(request)
        if filiais is None:
            return JSONResponse({"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS)

        async def gerador():
            hoje = date.today()
            mes_atual = hoje.strftime("%Y-%m")
            meses_janela = [mes_atual, *proximos_meses(mes_atual, _MESES_JANELA_FLUXO_CAIXA - 1)]
            data_corte = hoje + timedelta(days=_DIAS_CORTE_PERIODO)

            bucket_receber = _buscar_bucket_mensal("vw_titulos_receber", "saldo_aberto", filiais, hoje, meses_janela[-1])
            bucket_pagar = _buscar_bucket_mensal("vw_titulos_pagar", "saldo_aberto", filiais, hoje, meses_janela[-1])
            receber_no_periodo, receber_fora_periodo = _buscar_corte_periodo("vw_titulos_receber", filiais, data_corte)
            pagar_no_periodo, pagar_fora_periodo = _buscar_corte_periodo("vw_titulos_pagar", filiais, data_corte)
            yield _linha_ndjson({"tipo": "etapa", "id": "titulos_abertos"})

            prazo_recebimento = _prazo_medio_recebimento_dias(filiais)
            prazo_pagamento = _prazo_medio_pagamento_dias(filiais)
            yield _linha_ndjson({"tipo": "etapa", "id": "prazo_medio"})

            meses_historico = _janela_meses_historico(_MESES_HISTORICO)
            faturamento_por_mes = _buscar_faturamento_mensal(filiais, meses_historico[0])
            _, projecao_vendas = _historico_e_projecao(faturamento_por_mes, meses_historico, _MESES_PROJECAO)
            titulos_pagar_por_mes = _buscar_titulos_pagar_mensal(filiais, meses_historico[0])
            _, projecao_pagar = _historico_e_projecao(titulos_pagar_por_mes, meses_historico, _MESES_PROJECAO)

            deslocamento_receber = round(prazo_recebimento / 30)
            deslocamento_pagar = round(prazo_pagamento / 30)
            estimado_receber = _distribuir_estimativa(projecao_vendas, deslocamento_receber, meses_janela)
            estimado_pagar = _distribuir_estimativa(projecao_pagar, deslocamento_pagar, meses_janela)
            yield _linha_ndjson({"tipo": "etapa", "id": "projecao_futura"})

            meses = [
                {
                    "mes": mes,
                    "a_receber": bucket_receber.get(mes, 0.0),
                    "a_pagar": bucket_pagar.get(mes, 0.0),
                    "a_receber_estimado": bucket_receber.get(mes, 0.0) + estimado_receber.get(mes, 0.0),
                    "a_pagar_estimado": bucket_pagar.get(mes, 0.0) + estimado_pagar.get(mes, 0.0),
                }
                for mes in ["vencido", *meses_janela]
            ]

            total_estimado_receber = sum(estimado_receber.values())
            total_estimado_pagar = sum(estimado_pagar.values())
            contexto = (
                f"Títulos a receber em aberto: R$ {receber_no_periodo + receber_fora_periodo:.2f} no total, sendo "
                f"R$ {receber_no_periodo:.2f} com vencimento nos próximos {_DIAS_CORTE_PERIODO} dias. "
                f"Títulos a pagar em aberto: R$ {pagar_no_periodo + pagar_fora_periodo:.2f} no total, sendo "
                f"R$ {pagar_no_periodo:.2f} com vencimento nos próximos {_DIAS_CORTE_PERIODO} dias. "
                f"Já vencido e ainda em aberto: R$ {meses[0]['a_receber']:.2f} a receber e "
                f"R$ {meses[0]['a_pagar']:.2f} a pagar. "
                f"Prazo médio de recebimento (venda até o vencimento do título): {prazo_recebimento:.0f} dias. "
                f"Prazo médio de novas contas a pagar (emissão até o vencimento): {prazo_pagamento:.0f} dias. "
                "Estimativa adicional de venda/conta que ainda não foi lançada, baseada na tendência histórica, "
                f"pros próximos meses: R$ {total_estimado_receber:.2f} a receber e R$ {total_estimado_pagar:.2f} a pagar."
            )
            analise = await gerar_analise(AsyncClient(host=settings.ollama_host), settings.ollama_model, contexto)
            yield _linha_ndjson({"tipo": "etapa", "id": "analise_ia"})

            yield _linha_ndjson(
                {
                    "tipo": "resultado",
                    "dados": {
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
                        "prazo_medio_recebimento_dias": prazo_recebimento,
                        "prazo_medio_pagamento_dias": prazo_pagamento,
                        "analise": analise,
                    },
                }
            )

        return StreamingResponse(gerador(), media_type="application/x-ndjson", headers=CORS_HEADERS)
