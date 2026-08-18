"""Clima regional via Open-Meteo — usado pelo Score de Inadimplência
(`score_inadimplencia.py`) como um dos fatores de risco. Gratuito, sem
chave de API (testado ao vivo antes de escrever isto: geocodificação por
nome de cidade e histórico diário de precipitação, ambos funcionando sem
autenticação — https://open-meteo.com/).

Geolocalização é por MUNICÍPIO, não por fazenda exata:
`STAGE.PESSOA.LATITUDE/LONGITUDE` existem mas 9.854 de 9.855 clientes têm
só `'-'` (placeholder, inútil) — confirmado direto no Oracle. A precisão
real disponível é a do município do cliente (`vw_clientes.municipio_nome`).

Qualquer falha (cidade não encontrada, API fora do ar, timeout) devolve
`classificacao='indisponivel'` — nunca levanta erro pra quem chamou,
mesmo espírito de `tools/auth/eventos_seguranca.py::registrar` (uma
falha aqui não pode derrubar o cálculo do score)."""

from dataclasses import dataclass
from datetime import date, timedelta

import httpx

_DIAS_JANELA_CLIMA = 30
_ANOS_HISTORICO_CLIMA = 5
_LIMIAR_SECA_PERCENTUAL = -50.0  # 50% menos chuva que a média histórica
_LIMIAR_EXCESSO_PERCENTUAL = 100.0  # o dobro (ou mais) da média histórica

_URL_GEOCODIFICACAO = "https://geocoding-api.open-meteo.com/v1/search"
_URL_HISTORICO = "https://archive-api.open-meteo.com/v1/archive"


@dataclass(frozen=True)
class IndicadorClima:
    municipio_nome: str
    uf: str
    anomalia_precipitacao_percentual: float | None
    classificacao: str  # "seca" | "normal" | "excesso_chuva" | "indisponivel"


def _classificar(anomalia_percentual: float | None) -> str:
    if anomalia_percentual is None:
        return "indisponivel"
    if anomalia_percentual <= _LIMIAR_SECA_PERCENTUAL:
        return "seca"
    if anomalia_percentual >= _LIMIAR_EXCESSO_PERCENTUAL:
        return "excesso_chuva"
    return "normal"


async def _geocodificar(http_client: httpx.AsyncClient, municipio_nome: str) -> tuple[float, float] | None:
    try:
        resposta = await http_client.get(
            _URL_GEOCODIFICACAO,
            params={"name": municipio_nome, "count": 1, "language": "pt", "format": "json", "country": "BR"},
        )
        resposta.raise_for_status()
        resultados = resposta.json().get("results")
    except Exception:
        return None

    if not resultados:
        return None
    primeiro = resultados[0]
    return primeiro.get("latitude"), primeiro.get("longitude")


async def _precipitacao_total(
    http_client: httpx.AsyncClient, latitude: float, longitude: float, inicio: date, fim: date
) -> float | None:
    try:
        resposta = await http_client.get(
            _URL_HISTORICO,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "start_date": inicio.isoformat(),
                "end_date": fim.isoformat(),
                "daily": "precipitation_sum",
                "timezone": "auto",
            },
        )
        resposta.raise_for_status()
        valores = resposta.json().get("daily", {}).get("precipitation_sum")
    except Exception:
        return None

    if not valores:
        return None
    return sum(valor for valor in valores if valor is not None)


async def buscar_indicador_clima(
    http_client: httpx.AsyncClient, municipio_nome: str, uf: str, hoje: date | None = None
) -> IndicadorClima:
    """Compara a precipitação dos últimos `_DIAS_JANELA_CLIMA` dias contra
    a média do MESMO período de calendário nos últimos `_ANOS_HISTORICO_CLIMA`
    anos, pro mesmo município (comparação por dias corridos, não
    `date.replace(year=...)`, pra não quebrar em 29 de fevereiro) — nunca
    levanta erro, devolve `classificacao='indisponivel'` em qualquer
    falha (cidade não encontrada, API fora do ar, sem histórico
    suficiente)."""
    hoje = hoje or date.today()
    coordenadas = await _geocodificar(http_client, municipio_nome)
    if coordenadas is None:
        return IndicadorClima(municipio_nome, uf, None, "indisponivel")
    latitude, longitude = coordenadas

    fim_recente = hoje - timedelta(days=1)  # ontem — hoje pode não ter dado fechado ainda
    inicio_recente = fim_recente - timedelta(days=_DIAS_JANELA_CLIMA - 1)
    precipitacao_recente = await _precipitacao_total(
        http_client, latitude, longitude, inicio_recente, fim_recente
    )
    if precipitacao_recente is None:
        return IndicadorClima(municipio_nome, uf, None, "indisponivel")

    totais_historicos = []
    for anos_atras in range(1, _ANOS_HISTORICO_CLIMA + 1):
        deslocamento = timedelta(days=365 * anos_atras)
        total = await _precipitacao_total(
            http_client, latitude, longitude, inicio_recente - deslocamento, fim_recente - deslocamento
        )
        if total is not None:
            totais_historicos.append(total)

    if not totais_historicos:
        return IndicadorClima(municipio_nome, uf, None, "indisponivel")

    media_historica = sum(totais_historicos) / len(totais_historicos)
    if media_historica == 0:
        return IndicadorClima(municipio_nome, uf, None, "indisponivel")

    anomalia_percentual = round((precipitacao_recente - media_historica) / media_historica * 100, 1)
    return IndicadorClima(municipio_nome, uf, anomalia_percentual, _classificar(anomalia_percentual))
