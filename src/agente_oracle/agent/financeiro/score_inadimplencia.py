"""Score de Inadimplência — comportamento de pagamento + clima regional.

IMPORTANTE, pra não prometer mais do que existe: isto é um indicador
composto por REGRA clara (comportamento + clima), não um modelo de
machine learning treinado com resultado histórico rotulado — não existe
pipeline de treino/validação neste projeto, e criar um de verdade seria
uma frente bem maior, separada desta. Cada fator do score vira uma frase
legível em `fatores`, nunca uma caixa preta.

Comportamento de pagamento é 100% cálculo sobre títulos já liquidados de
`vw_titulos_receber` (sem IA). Clima regional vem de `clima_regional.py`
(Open-Meteo, opcional — `None`/`indisponivel` nunca derruba o score)."""

from dataclasses import dataclass
from datetime import date, timedelta

from agente_oracle.agent.financeiro.clima_regional import IndicadorClima

_DIAS_JANELA_RECENTE = 90
_DIAS_JANELA_ANTERIOR = 90  # os 90 dias imediatamente antes da janela recente
_LIMIAR_TENDENCIA_PERCENTUAL = 10.0

_PONTOS_MAXIMO_COMPORTAMENTO = 70
_PONTOS_MAXIMO_CLIMA = 30
_BONUS_TENDENCIA_PIORANDO = 15


@dataclass(frozen=True)
class TituloReceberLiquidado:
    cliente_codigo: str
    cliente_nome: str
    data_vencimento: date
    data_baixa: date


@dataclass(frozen=True)
class ComportamentoPagamentoCliente:
    cliente_codigo: str
    cliente_nome: str
    percentual_atraso_recente: float
    percentual_atraso_anterior: float
    dias_atraso_medio: float
    tendencia: str  # "piorando" | "estavel" | "melhorando"


@dataclass(frozen=True)
class ScoreInadimplencia:
    cliente_codigo: str
    cliente_nome: str
    score: int
    comportamento: ComportamentoPagamentoCliente
    clima: IndicadorClima | None
    fatores: tuple[str, ...]


def _percentual_atraso(titulos: list[TituloReceberLiquidado]) -> float:
    if not titulos:
        return 0.0
    atrasados = sum(1 for titulo in titulos if titulo.data_baixa > titulo.data_vencimento)
    return round(atrasados / len(titulos) * 100, 1)


def _tendencia(percentual_recente: float, percentual_anterior: float) -> str:
    diferenca = percentual_recente - percentual_anterior
    if diferenca >= _LIMIAR_TENDENCIA_PERCENTUAL:
        return "piorando"
    if diferenca <= -_LIMIAR_TENDENCIA_PERCENTUAL:
        return "melhorando"
    return "estavel"


def comportamento_por_cliente(
    liquidados: list[TituloReceberLiquidado], hoje: date
) -> list[ComportamentoPagamentoCliente]:
    """Compara os últimos `_DIAS_JANELA_RECENTE` dias contra os
    `_DIAS_JANELA_ANTERIOR` dias imediatamente antes disso, por cliente —
    cliente sem título liquidado em nenhuma das duas janelas não aparece
    no resultado (não tem comportamento recente pra avaliar)."""
    corte_recente = hoje - timedelta(days=_DIAS_JANELA_RECENTE)
    corte_anterior = corte_recente - timedelta(days=_DIAS_JANELA_ANTERIOR)

    por_cliente: dict[str, list[TituloReceberLiquidado]] = {}
    for titulo in liquidados:
        por_cliente.setdefault(titulo.cliente_codigo, []).append(titulo)

    resultado = []
    for cliente_codigo, titulos in por_cliente.items():
        recentes = [titulo for titulo in titulos if titulo.data_baixa >= corte_recente]
        anteriores = [titulo for titulo in titulos if corte_anterior <= titulo.data_baixa < corte_recente]
        if not recentes and not anteriores:
            continue

        percentual_recente = _percentual_atraso(recentes)
        percentual_anterior = _percentual_atraso(anteriores)
        atrasados_recentes = [titulo for titulo in recentes if titulo.data_baixa > titulo.data_vencimento]
        dias_atraso_medio = (
            sum((titulo.data_baixa - titulo.data_vencimento).days for titulo in atrasados_recentes)
            / len(atrasados_recentes)
            if atrasados_recentes
            else 0.0
        )

        resultado.append(
            ComportamentoPagamentoCliente(
                cliente_codigo=cliente_codigo,
                cliente_nome=titulos[0].cliente_nome,
                percentual_atraso_recente=percentual_recente,
                percentual_atraso_anterior=percentual_anterior,
                dias_atraso_medio=round(dias_atraso_medio, 1),
                tendencia=_tendencia(percentual_recente, percentual_anterior),
            )
        )
    return resultado


def calcular_score(
    comportamento: ComportamentoPagamentoCliente, clima: IndicadorClima | None
) -> ScoreInadimplencia:
    """Pontuação 0–100 (maior = mais risco): até `_PONTOS_MAXIMO_COMPORTAMENTO`
    pontos vêm do percentual de atraso recente (mais bônus se a tendência
    for piorando), até `_PONTOS_MAXIMO_CLIMA` pontos vêm de anomalia
    climática extrema (seca ou excesso de chuva) na região do cliente."""
    fatores = [
        f"{comportamento.percentual_atraso_recente:.0f}% dos títulos pagos com atraso nos últimos 90 dias"
    ]

    pontos_comportamento = min(
        float(_PONTOS_MAXIMO_COMPORTAMENTO),
        comportamento.percentual_atraso_recente / 100 * _PONTOS_MAXIMO_COMPORTAMENTO,
    )
    if comportamento.tendencia == "piorando":
        pontos_comportamento = min(
            float(_PONTOS_MAXIMO_COMPORTAMENTO), pontos_comportamento + _BONUS_TENDENCIA_PIORANDO
        )
        fatores.append("comportamento de pagamento piorando em relação ao período anterior")
    elif comportamento.tendencia == "melhorando":
        fatores.append("comportamento de pagamento melhorando em relação ao período anterior")

    pontos_clima = 0.0
    if clima is not None and clima.classificacao in ("seca", "excesso_chuva"):
        pontos_clima = float(_PONTOS_MAXIMO_CLIMA)
        rotulo_clima = "seca" if clima.classificacao == "seca" else "excesso de chuva"
        fatores.append(f"{rotulo_clima} na região ({clima.municipio_nome}/{clima.uf})")
    elif clima is None or clima.classificacao == "indisponivel":
        fatores.append("clima regional indisponível no momento")

    return ScoreInadimplencia(
        cliente_codigo=comportamento.cliente_codigo,
        cliente_nome=comportamento.cliente_nome,
        score=round(pontos_comportamento + pontos_clima),
        comportamento=comportamento,
        clima=clima,
        fatores=tuple(fatores),
    )
