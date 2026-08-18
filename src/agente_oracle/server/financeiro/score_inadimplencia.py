"""Rota do Score de Inadimplência — comportamento de pagamento mora em
`agent/financeiro/score_inadimplencia.py`, clima regional em
`agent/financeiro/clima_regional.py` (cache em `tools/financeiro/
clima_cache.py`, TTL de 24h por município). Este módulo só busca dado do
Oracle, monta o client HTTP da Open-Meteo e a resposta HTTP — roda sob
demanda, nunca em background, mesmo espírito de `despesas_suspeitas.py`."""

from datetime import date, timedelta

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agente_oracle.agent.financeiro.clima_regional import IndicadorClima, buscar_indicador_clima
from agente_oracle.agent.financeiro.score_inadimplencia import (
    ScoreInadimplencia,
    TituloReceberLiquidado,
    calcular_score,
    comportamento_por_cliente,
)
from agente_oracle.db.connection import get_connection
from agente_oracle.server.auth.decorador_rota import rota_protegida
from agente_oracle.server.cors import CORS_HEADERS
from agente_oracle.server.financeiro.relatorios import _comum
from agente_oracle.server.financeiro.relatorios.filtros_sql import clausula_in
from agente_oracle.tools.financeiro import clima_cache

_DIAS_HISTORICO = 180
_TIMEOUT_HTTP_SEGUNDOS = 10.0


def _data(valor):
    return valor.date() if hasattr(valor, "date") else valor


def _buscar_liquidados(filiais: list[str], desde: date) -> list[TituloReceberLiquidado]:
    clausula_filial, binds_filial = clausula_in("filial", filiais)
    sql = f"""
        SELECT cliente_codigo, cliente_nome, data_vencimento, data_baixa
        FROM vw_titulos_receber
        WHERE filial IN {clausula_filial}
          AND data_baixa IS NOT NULL
          AND data_baixa >= :desde
    """
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, desde=desde, **binds_filial)
        linhas = cursor.fetchall()
    return [
        TituloReceberLiquidado(
            cliente_codigo=cliente_codigo,
            cliente_nome=cliente_nome,
            data_vencimento=_data(data_vencimento),
            data_baixa=_data(data_baixa),
        )
        for (cliente_codigo, cliente_nome, data_vencimento, data_baixa) in linhas
    ]


def _buscar_municipios(clientes_codigos: list[str]) -> dict[str, tuple[str, str]]:
    """cliente_codigo -> (municipio_nome, uf), só pros clientes informados
    — cliente sem município cadastrado não entra no dict (clima fica
    indisponível pra ele)."""
    if not clientes_codigos:
        return {}
    clausula_cliente, binds_cliente = clausula_in("cliente", clientes_codigos)
    sql = f"""
        SELECT codigo, municipio_nome, estado
        FROM vw_clientes
        WHERE codigo IN {clausula_cliente}
    """
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, **binds_cliente)
        linhas = cursor.fetchall()
    return {codigo: (municipio_nome, estado) for codigo, municipio_nome, estado in linhas if municipio_nome}


async def _climas_por_municipio(
    municipios: set[tuple[str, str]],
) -> dict[tuple[str, str], IndicadorClima]:
    """Um indicador por município ÚNICO (não por cliente) — usa cache
    (`tools/financeiro/clima_cache.py`) antes de chamar a Open-Meteo de
    verdade."""
    climas: dict[tuple[str, str], IndicadorClima] = {}
    async with httpx.AsyncClient(timeout=_TIMEOUT_HTTP_SEGUNDOS) as http_client:
        for municipio_nome, uf in municipios:
            indicador = clima_cache.buscar_cache(municipio_nome, uf)
            if indicador is None:
                indicador = await buscar_indicador_clima(http_client, municipio_nome, uf)
                clima_cache.salvar_cache(indicador)
            climas[(municipio_nome, uf)] = indicador
    return climas


def _score_para_json(score: ScoreInadimplencia) -> dict:
    return {
        "cliente_codigo": score.cliente_codigo,
        "cliente_nome": score.cliente_nome,
        "score": score.score,
        "comportamento": {
            "percentual_atraso_recente": score.comportamento.percentual_atraso_recente,
            "percentual_atraso_anterior": score.comportamento.percentual_atraso_anterior,
            "dias_atraso_medio": score.comportamento.dias_atraso_medio,
            "tendencia": score.comportamento.tendencia,
        },
        "clima": (
            {
                "municipio_nome": score.clima.municipio_nome,
                "uf": score.clima.uf,
                "classificacao": score.clima.classificacao,
            }
            if score.clima is not None
            else None
        ),
        "fatores": list(score.fatores),
    }


def registrar(mcp) -> None:
    @mcp.custom_route("/api/financeiro/score-inadimplencia", methods=["GET", "OPTIONS"])
    @rota_protegida("GET, OPTIONS", exigir=_comum.exigir_filiais_liberadas)
    async def score_inadimplencia_route(request: Request, usuario: dict) -> Response:
        """Comportamento de pagamento (`vw_titulos_receber`, últimos
        `_DIAS_HISTORICO` dias) + clima regional (Open-Meteo, por
        município do cliente via `vw_clientes`) — indicador composto por
        regra, sem IA (ver docstring de `agent/financeiro/
        score_inadimplencia.py`)."""
        filiais = _comum.filiais_da_query(request)
        if filiais is None:
            return JSONResponse(
                {"erro": "Informe ao menos uma filial."}, status_code=400, headers=CORS_HEADERS
            )

        desde = date.today() - timedelta(days=_DIAS_HISTORICO)
        comportamentos = comportamento_por_cliente(_buscar_liquidados(filiais, desde), date.today())

        municipios_por_cliente = _buscar_municipios([c.cliente_codigo for c in comportamentos])
        municipios_unicos = set(municipios_por_cliente.values())
        climas = await _climas_por_municipio(municipios_unicos)

        scores = []
        for comportamento in comportamentos:
            chave_municipio = municipios_por_cliente.get(comportamento.cliente_codigo)
            clima = climas.get(chave_municipio) if chave_municipio else None
            scores.append(calcular_score(comportamento, clima))
        scores.sort(key=lambda score: score.score, reverse=True)

        _comum.registrar_acesso(usuario, "score_inadimplencia:calcular", len(scores))
        return JSONResponse([_score_para_json(score) for score in scores], headers=CORS_HEADERS)
