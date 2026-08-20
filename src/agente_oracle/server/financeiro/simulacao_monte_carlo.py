"""Rota da Simulação de Cenários Monte Carlo (FP&A) — a lógica de bootstrap
mora em `agent/financeiro/simulacao_monte_carlo.py`; este módulo só busca o
histórico mensal de caixa líquido (recebido - pago) e monta a resposta
HTTP, mesmo espírito de `server/financeiro/previsao.py` (mas em JSON
simples: diferente do Fluxo de Caixa, aqui é uma única passada de cálculo,
rápida, não precisa do streaming NDJSON de progresso)."""

from datetime import date

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.agent.financeiro.projecoes import proximos_meses
from agente_oracle.agent.financeiro.simulacao_monte_carlo import (
    probabilidade_caixa_negativo,
    resumir_percentis,
    simular_cenarios,
)
from agente_oracle.db.connection import get_connection
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.server.financeiro.relatorios import _comum
from agente_oracle.server.financeiro.relatorios.filtros_sql import clausula_in

_MESES_HISTORICO = 24
_MESES_FUTUROS = 6
_NUM_SIMULACOES = 2000


def _janela_meses_historico(quantidade: int) -> list[str]:
    """Os `quantidade` rótulos "YYYY-MM" mais recentes, em ordem crescente,
    terminando no mês atual (mesma lógica de `server/financeiro/previsao.py`,
    duplicada aqui porque é privada lá — cada rota do Financeiro é
    self-contida, sem módulo de suporte compartilhado pra isso)."""
    mes_atual = date.today().strftime("%Y-%m")
    meses = [mes_atual, *[_mes_menos(mes_atual, passo) for passo in range(1, quantidade)]]
    meses.reverse()
    return meses


def _mes_menos(mes_referencia: str, quantidade: int) -> str:
    ano, mes = (int(parte) for parte in mes_referencia.split("-"))
    total_meses = ano * 12 + (mes - 1) - quantidade
    ano_resultado, mes_resultado = divmod(total_meses, 12)
    return f"{ano_resultado:04d}-{mes_resultado + 1:02d}"


def _buscar_titulos_mensal(view: str, filiais: list[str], mes_inicio: str) -> dict[str, float]:
    """Total de `valor_original` por mês de emissão — mesma consulta pro
    lado receber e pro lado pagar (só troca a view)."""
    clausula_filial, binds_filial = clausula_in("filial", filiais)
    sql = f"""
        SELECT TO_CHAR(data_emissao, 'YYYY-MM') AS mes, SUM(valor_original) AS total
        FROM {view}
        WHERE filial IN {clausula_filial}
          AND TO_CHAR(data_emissao, 'YYYY-MM') >= :mes_inicio
        GROUP BY TO_CHAR(data_emissao, 'YYYY-MM')
    """
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, mes_inicio=mes_inicio, **binds_filial)
        linhas = cursor.fetchall()
    return {mes: _comum.serializar(total) for mes, total in linhas}


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/fpa/simulacao-monte-carlo", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def simulacao_monte_carlo_route(request: Request, usuario: dict) -> Response:
        """Simula `_NUM_SIMULACOES` cenários de caixa líquido (recebido -
        pago) pros próximos `_MESES_FUTUROS` meses, por reamostragem
        (bootstrap) da variação histórica real dos últimos `_MESES_HISTORICO`
        meses — sem IA, número não depende do Ollama estar no ar."""
        filiais = _comum.filiais_da_query(request)
        if filiais is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS
            )

        meses_historico = _janela_meses_historico(_MESES_HISTORICO)
        receber_por_mes = _buscar_titulos_mensal("vw_titulos_receber", filiais, meses_historico[0])
        pagar_por_mes = _buscar_titulos_mensal("vw_titulos_pagar", filiais, meses_historico[0])
        serie_historica = [
            receber_por_mes.get(mes, 0.0) - pagar_por_mes.get(mes, 0.0) for mes in meses_historico
        ]

        matriz = simular_cenarios(serie_historica, _MESES_FUTUROS, _NUM_SIMULACOES)
        bandas_percentis = resumir_percentis(matriz)
        meses_futuros = proximos_meses(meses_historico[-1], _MESES_FUTUROS)
        bandas = [{"mes": mes, **banda} for mes, banda in zip(meses_futuros, bandas_percentis, strict=True)]

        _comum.registrar_acesso(usuario, "simulacao_monte_carlo:simular", len(bandas))
        return JSONResponse(
            {
                "historico": [
                    {"mes": mes, "valor": valor}
                    for mes, valor in zip(meses_historico, serie_historica, strict=True)
                ],
                "bandas": bandas,
                "probabilidade_caixa_negativo": probabilidade_caixa_negativo(matriz),
            },
            headers=CORS_HEADERS,
        )
